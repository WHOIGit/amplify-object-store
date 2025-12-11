import asyncio
from typing import AsyncIterator, Optional

import aiohttp
from aiohttp import ClientError


class AsyncRestStoreError(Exception):
    """Base exception for async REST store errors"""
    pass


class AsyncRestStore:
    """
    Async REST client.

    Mirrors RestStore in client.py but uses aiohttp and async/await.
    """

    @classmethod
    def create(cls, *args, **kwargs) -> "AsyncRestStore":
        """
        Factory method to create an async REST store.

        For the async client we return the raw AsyncRestStore instance to avoid
        wrapping it in any synchronous adapter.
        """
        return cls(*args, **kwargs)

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        """
        Initialize the async REST store client.

        Args mirror RestStore in client.py.
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self._external_session = session is not None
        self._session: Optional[aiohttp.ClientSession] = session

    # --------------------------------------------------------------------- #
    # Session / context management
    # --------------------------------------------------------------------- #
    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed and not self._external_session:
            await self._session.close()

    async def __aenter__(self) -> "AsyncRestStore":
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    # --------------------------------------------------------------------- #
    # Internal request helper with retries
    # --------------------------------------------------------------------- #
    async def _make_request(
        self,
        method: str,
        path: str,
        *,
        allow_404: bool = False,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """
        Make an HTTP request with retry logic (async).

        If allow_404 is True, a 404 response is returned to the caller
        instead of being turned into AsyncRestStoreError.
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        kwargs.setdefault("timeout", aiohttp.ClientTimeout(total=self.timeout))

        last_error: Optional[BaseException] = None
        delay = self.retry_delay

        session = await self._ensure_session()

        for attempt in range(self.max_retries):
            try:
                resp = await session.request(method, url, **kwargs)

                # Check for rate limiting
                if resp.status == 429:
                    retry_after = resp.headers.get("Retry-After")
                    try:
                        retry_after_val = int(retry_after) if retry_after is not None else delay
                    except ValueError:
                        retry_after_val = delay
                    await resp.release()
                    await asyncio.sleep(retry_after_val)
                    continue

                # Handle error status codes
                if resp.status >= 400:
                    if allow_404 and resp.status == 404:
                        # Caller is responsible for handling 404
                        return resp

                    # Try to read JSON error, but don't fail if it isn't JSON
                    try:
                        data = await resp.json()
                        error_data = data.get("error", {})
                        message = error_data.get("message", "Unknown error")
                    except Exception:
                        text = await resp.text()
                        message = f"{resp.status} error: {text}"
                    await resp.release()
                    raise AsyncRestStoreError(f"HTTP {resp.status}: {message}")

                return resp

            except (ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise AsyncRestStoreError(
                    f"Request failed after {self.max_retries} attempts"
                ) from e

        if last_error:
            raise AsyncRestStoreError(
                f"Request failed after {self.max_retries} attempts"
            ) from last_error

        raise AsyncRestStoreError("Unexpected error in request retry loop")

    # --------------------------------------------------------------------- #
    # Public async API (async analogs of RestStore methods)
    # --------------------------------------------------------------------- #
    async def put(self, key: str, data: bytes) -> None:
        """Store an object (async)."""
        try:
            resp = await self._make_request("PUT", f"objects/{key}", data=data)
            await resp.release()
        except AsyncRestStoreError as e:
            raise KeyError(f"Failed to store object {key}: {str(e)}")

    async def get(self, key: str) -> bytes:
        """Retrieve an object (async)."""
        try:
            resp = await self._make_request("GET", f"objects/{key}")
            async with resp:
                return await resp.read()
        except AsyncRestStoreError as e:
            raise KeyError(f"Failed to retrieve object {key}: {str(e)}")

    async def exists(self, key: str) -> bool:
        """Check if an object exists (async)."""
        try:
            resp = await self._make_request("HEAD", f"objects/{key}", allow_404=True)
            if resp.status == 404:
                await resp.release()
                return False
            await resp.release()
            return True
        except:
            raise

    async def delete(self, key: str) -> None:
        """Delete an object (async)."""
        try:
            # Allow 404 through so we can turn it into KeyError explicitly
            resp = await self._make_request(
                "DELETE",
                f"objects/{key}",
                allow_404=True,
            )
            if resp.status == 404:
                await resp.release()
                raise KeyError(f"Object {key} does not exist")
            await resp.release()
        except AsyncRestStoreError as e:
            raise AsyncRestStoreError(f"Failed to delete object {key}: {str(e)}")

    async def keys(self) -> AsyncIterator[str]:
        """List all object keys with pagination (async iterator)."""
        cursor: Optional[str] = None

        while True:
            try:
                params = {"limit": 100}
                if cursor:
                    params["cursor"] = cursor

                resp = await self._make_request("GET", "objects", params=params)
                async with resp:
                    data = await resp.json()

                for key in data.get("keys", []):
                    yield key

                if not data.get("has_more"):
                    break

                cursor = data.get("next_cursor")
                if not cursor:
                    break

            except AsyncRestStoreError as e:
                # Keep NotImplementedError to mirror sync behavior
                raise NotImplementedError(f"Failed to list keys: {str(e)}")

# Example usage (for reference only; do not run on import):
# async def main():
#     async with AsyncRestStore(
#         base_url="https://api.objectstore.example/v1",
#         api_key="your-api-key",
#     ) as store:
#         await store.put("example-key", b"Hello, Async World!")
#         data = await store.get("example-key")
#         print(data.decode())
#
#         async for key in store.keys():
#             print(key)
#
# if __name__ == "__main__":
#     asyncio.run(main())
