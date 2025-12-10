# auth_fastapi.py
import asyncio
import os
import threading

import hmac
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from auth_tokens import (
    TokenRecord,
    DEFAULT_TOKENS_FILE,
    hash_token,
    load_token_records,
)

security = HTTPBearer()

_TOKENS_FILE_PATH: Path = Path(os.environ.get("AUTH_TOKENS_FILE", DEFAULT_TOKENS_FILE))
_TOKENS_CACHE: List[TokenRecord] = []
_TOKENS_MTIME: Optional[float] = None
_TOKENS_LOCK: Optional[asyncio.Lock] = None
_LOCK_INIT_LOCK: threading.Lock = threading.Lock()


def _get_lock() -> asyncio.Lock:
    """Get or create the asyncio lock for coroutine-safe cache access."""
    global _TOKENS_LOCK
    if _TOKENS_LOCK is None:
        with _LOCK_INIT_LOCK:
            # Double-check locking pattern
            if _TOKENS_LOCK is None:
                _TOKENS_LOCK = asyncio.Lock()
    return _TOKENS_LOCK


async def set_tokens_file_path(path: Path) -> None:
    """
    Optionally override the tokens.json path used at runtime.
    Call this once at startup if needed.
    """
    global _TOKENS_FILE_PATH, _TOKENS_MTIME
    async with _get_lock():
        _TOKENS_FILE_PATH = path
        _TOKENS_MTIME = None


async def _reload_tokens_if_changed() -> List[TokenRecord]:
    global _TOKENS_CACHE, _TOKENS_MTIME

    async with _get_lock():
        try:
            mtime = _TOKENS_FILE_PATH.stat().st_mtime
        except FileNotFoundError:
            _TOKENS_CACHE = []
            _TOKENS_MTIME = None
            return _TOKENS_CACHE

        if _TOKENS_MTIME is None or mtime != _TOKENS_MTIME:
            _TOKENS_CACHE = load_token_records(_TOKENS_FILE_PATH)
            _TOKENS_MTIME = mtime

        return _TOKENS_CACHE


async def get_current_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenRecord:
    """
    FastAPI dependency to validate a Bearer token against tokens.json.
    Returns the TokenRecord (including scopes).
    """
    token = credentials.credentials
    token_hash = hash_token(token)
    records = await _reload_tokens_if_changed()

    now = datetime.now(timezone.utc)
    for rec in records:
        if hmac.compare_digest(rec.hash, token_hash):
            if rec.expires < now:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token expired",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return rec

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_scopes(required_scopes: List[str]):
    """
    Returns a dependency that ensures the current token has ALL required scopes.
    """
    required = set(required_scopes)

    def dependency(token: TokenRecord = Depends(get_current_token)) -> TokenRecord:
        token_scopes = set(token.scopes or [])
        missing = required - token_scopes
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scopes: {sorted(missing)}",
            )
        return token

    return dependency


# ---- Custom route decorators with scopes ----

def _merge_scope_dependency(scopes: List[str], kwargs: dict) -> dict:
    """
    Helper: merge a require_scopes(...) dependency into kwargs['dependencies'].
    Doesn't mutate the original kwargs.
    """
    new_kwargs = dict(kwargs)
    deps = list(new_kwargs.get("dependencies", []))
    deps.append(Depends(require_scopes(scopes)))
    new_kwargs["dependencies"] = deps
    return new_kwargs


def scoped_get(
    app: FastAPI,
    path: str,
    *,
    scopes: List[str],
    **kwargs,
):
    """
    Create a GET route that requires the given scopes.

    Usage:

        @scoped_get(app, "/admin", scopes=["admin"])
        def admin_route():
            ...
    """
    def decorator(func):
        route_kwargs = _merge_scope_dependency(scopes, kwargs)
        return app.get(path, **route_kwargs)(func)

    return decorator


def scoped_post(
    app: FastAPI,
    path: str,
    *,
    scopes: List[str],
    **kwargs,
):
    def decorator(func):
        route_kwargs = _merge_scope_dependency(scopes, kwargs)
        return app.post(path, **route_kwargs)(func)

    return decorator


def scoped_put(
    app: FastAPI,
    path: str,
    *,
    scopes: List[str],
    **kwargs,
):
    def decorator(func):
        route_kwargs = _merge_scope_dependency(scopes, kwargs)
        return app.put(path, **route_kwargs)(func)

    return decorator


def scoped_delete(
    app: FastAPI,
    path: str,
    *,
    scopes: List[str],
    **kwargs,
):
    def decorator(func):
        route_kwargs = _merge_scope_dependency(scopes, kwargs)
        return app.delete(path, **route_kwargs)(func)

    return decorator


def scoped_patch(
    app: FastAPI,
    path: str,
    *,
    scopes: List[str],
    **kwargs,
):
    def decorator(func):
        route_kwargs = _merge_scope_dependency(scopes, kwargs)
        return app.patch(path, **route_kwargs)(func)

    return decorator


def scoped_head(
    app: FastAPI,
    path: str,
    *,
    scopes: List[str],
    **kwargs,
):
    def decorator(func):
        route_kwargs = _merge_scope_dependency(scopes, kwargs)
        return app.head(path, **route_kwargs)(func)

    return decorator