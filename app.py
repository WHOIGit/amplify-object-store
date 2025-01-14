from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Response, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import base64
import time
from datetime import datetime
import json

app = FastAPI(title="Object Store API")

# Pydantic models for responses
class ObjectMetadata(BaseModel):
    key: str
    size: int
    created_at: datetime

class ListObjectsResponse(BaseModel):
    keys: list[str]
    next_cursor: Optional[str] = None
    has_more: bool

class ErrorResponse(BaseModel):
    error: dict

def validate_api_key(api_key: str = Header(..., alias="Authorization")) -> str:
    """Validate the API key from the Authorization header"""
    if not api_key.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    token = api_key.split(" ")[1]
    # TODO: Implement actual API key validation
    return token

def get_store(request: Request):
    """Helper to get the object store from app state"""
    if not hasattr(request.app.state, "store"):
        raise HTTPException(
            status_code=500, 
            detail="Object store not configured"
        )
    return request.app.state.store

def encode_cursor(last_key: str) -> str:
    """Create a base64 encoded cursor from the last key"""
    cursor_data = {"last_key": last_key}
    return base64.b64encode(json.dumps(cursor_data).encode()).decode()

def decode_cursor(cursor: str) -> str:
    """Decode a cursor to get the last key"""
    try:
        cursor_data = json.loads(base64.b64decode(cursor).decode())
        return cursor_data["last_key"]
    except:
        raise HTTPException(status_code=400, detail="Invalid cursor")

@app.put("/objects/{key}")
async def put_object(
    key: str,
    request: Request,
    api_key: str = Header(..., alias="Authorization")
):
    """Store an object"""
    validate_api_key(api_key)
    store = get_store(request)
    
    # Read request body
    data = await request.body()
    
    try:
        store.put(key, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ObjectMetadata(
        key=key,
        size=len(data),
        created_at=datetime.utcnow()
    )

@app.get("/objects/{key}")
async def get_object(
    key: str,
    request: Request,
    api_key: str = Header(..., alias="Authorization")
):
    """Retrieve an object"""
    validate_api_key(api_key)
    store = get_store(request)
    
    try:
        data = store.get(key)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Object {key} not found")
    
    # Return a streaming response for potentially large objects
    return StreamingResponse(
        iter([data]),
        media_type=request.headers.get("Accept", "application/octet-stream")
    )

@app.head("/objects/{key}")
async def head_object(
    key: str,
    request: Request,
    api_key: str = Header(..., alias="Authorization")
):
    """Check if an object exists"""
    validate_api_key(api_key)
    store = get_store(request)
    
    if not store.exists(key):
        raise HTTPException(status_code=404)
    
    return Response(status_code=200)

@app.delete("/objects/{key}")
async def delete_object(
    key: str,
    request: Request,
    api_key: str = Header(..., alias="Authorization")
):
    """Delete an object"""
    validate_api_key(api_key)
    store = get_store(request)
    
    try:
        store.delete(key)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Object {key} not found")
    
    return Response(status_code=204)

@app.get("/objects")
async def list_objects(
    request: Request,
    prefix: Optional[str] = None,
    limit: int = 100,
    cursor: Optional[str] = None,
    api_key: str = Header(..., alias="Authorization")
):
    """List objects with pagination"""
    validate_api_key(api_key)
    store = get_store(request)
    
    try:
        # Get all keys and sort them for consistent pagination
        all_keys = sorted(store.keys())
    except NotImplementedError:
        raise HTTPException(
            status_code=501,
            detail="This store does not support listing keys"
        )

    # Filter by prefix if specified
    if prefix:
        all_keys = [k for k in all_keys if k.startswith(prefix)]
    
    # Apply cursor-based pagination
    start_idx = 0
    if cursor:
        last_key = decode_cursor(cursor)
        try:
            start_idx = all_keys.index(last_key) + 1
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid cursor")
    
    # Get the requested page of results
    end_idx = start_idx + limit
    keys = all_keys[start_idx:end_idx]
    
    # Prepare the response
    has_more = end_idx < len(all_keys)
    next_cursor = None
    if has_more and keys:
        next_cursor = encode_cursor(keys[-1])
    
    return ListObjectsResponse(
        keys=keys,
        next_cursor=next_cursor,
        has_more=has_more
    )

# Example middleware for rate limiting
@app.middleware("http")
async def add_rate_limit_headers(request: Request, call_next):
    """Add rate limit headers to responses"""
    response = await call_next(request)
    
    # TODO: Implement actual rate limiting
    response.headers["X-RateLimit-Limit"] = "1000"
    response.headers["X-RateLimit-Remaining"] = "999"
    response.headers["X-RateLimit-Reset"] = str(int(time.time() + 3600))
    
    return response

# Error handling
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return Response(
        content=json.dumps({
            "error": {
                "code": str(exc.status_code),
                "message": exc.detail
            }
        }),
        status_code=exc.status_code,
        media_type="application/json"
    )

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    # This is where you would initialize your object store
    # Example:
    from storage.object import DictStore
    app.state.store = DictStore()
    yield
    # This is where you would clean up your object store if needed

