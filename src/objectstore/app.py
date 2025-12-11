from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Response, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import base64
import time
from datetime import datetime, timezone
import json
from contextlib import asynccontextmanager


from .auth_fastapi import scoped_get, scoped_head, scoped_put, scoped_delete


class AsyncDictStore:
    """A simple in-memory async object store for demonstration purposes."""
    def __init__(self):
        self.store = {}

    async def put(self, key: str, data: bytes) -> None:
        self.store[key] = data

    async def get(self, key: str) -> bytes:
        if key not in self.store:
            raise KeyError(f"Object {key} not found")
        return self.store[key]

    async def exists(self, key: str) -> bool:
        return key in self.store

    async def delete(self, key: str) -> None:
        if key not in self.store:
            raise KeyError(f"Object {key} not found")
        del self.store[key]

    async def keys(self):
        for key in self.store.keys():
            yield key


@asynccontextmanager
async def lifespan(app):
    # This is where you would initialize your object store
    # Example:
    app.state.store = AsyncDictStore()
    yield
    # This is where you would clean up your object store if needed

app = FastAPI(title="Object Store API", lifespan=lifespan)

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


@scoped_put(app, "/objects/{key:path}", scopes=["write"])
async def put_object(
    key: str,
    request: Request,
):
    """Store an object"""
    store = get_store(request)
    
    # Read request body
    data = await request.body()
    
    try:
        await store.put(key, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ObjectMetadata(
        key=key,
        size=len(data),
        created_at=datetime.now(timezone.utc)
    )


@scoped_get(app, "/objects/{key:path}", scopes=["read"])
async def get_object(
    key: str,
    request: Request,
):
    """Retrieve an object"""
    store = get_store(request)
    
    try:
        data = await store.get(key)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Object {key} not found")
    
    # Return a streaming response for potentially large objects
    return StreamingResponse(
        iter([data]),
        media_type=request.headers.get("Accept", "application/octet-stream")
    )


@scoped_head(app, "/objects/{key:path}", scopes=["read"])
async def head_object(
    key: str,
    request: Request,
):
    """Check if an object exists"""
    store = get_store(request)
    
    if not await store.exists(key):
        raise HTTPException(status_code=404)
    
    return Response(status_code=200)


@scoped_delete(app, "/objects/{key:path}", scopes=["delete"])
async def delete_object(
    key: str,
    request: Request,
):
    """Delete an object"""
    store = get_store(request)
    
    try:
        await store.delete(key)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Object {key} not found")
    
    return Response(status_code=204)


@scoped_get(app, "/objects", scopes=["read"])
async def list_objects(
    request: Request,
    prefix: Optional[str] = None,
    limit: int = 100,
    cursor: Optional[str] = None,
):
    """List objects with pagination"""
    store = get_store(request)
    
    try:
        # Get all keys and sort them for consistent pagination
        all_keys = sorted([key async for key in store.keys()])
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



