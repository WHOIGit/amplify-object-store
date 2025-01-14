import time
from typing import Iterable, Optional
import requests
from requests.exceptions import RequestException
from storage.object import ObjectStore

class RestStoreError(Exception):
    """Base exception for REST store errors"""
    pass

class RestStore(ObjectStore):
    """
    REST client implementation of ObjectStore interface.
    
    This client implements the ObjectStore interface by making HTTP requests
    to a compatible REST API endpoint.
    """
    def __init__(
        self, 
        base_url: str, 
        api_key: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize the REST store client.
        
        Args:
            base_url: Base URL of the REST API (e.g., "https://api.objectstore.example/v1")
            api_key: API key for authentication
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts for failed requests
            retry_delay: Initial delay between retries (doubles after each attempt)
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Set up a requests session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}'
        })

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()

    def _make_request(self, method: str, path: str, **kwargs) -> requests.Response:
        """
        Make an HTTP request with retry logic.
        
        Handles retrying failed requests with exponential backoff.
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        kwargs.setdefault('timeout', self.timeout)
        
        last_error = None
        delay = self.retry_delay
        
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(method, url, **kwargs)
                
                # Check for rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', delay))
                    time.sleep(retry_after)
                    continue
                
                # Raise for error status codes
                if response.status_code >= 400:
                    error_data = response.json().get('error', {})
                    raise RestStoreError(
                        f"HTTP {response.status_code}: {error_data.get('message', 'Unknown error')}"
                    )
                
                return response
                
            except RequestException as e:
                last_error = e
                # Only retry on connection errors and rate limits
                if attempt < self.max_retries - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise RestStoreError(f"Request failed after {self.max_retries} attempts") from e
            
        if last_error:
            raise RestStoreError(f"Request failed after {self.max_retries} attempts") from last_error
        
        raise RestStoreError("Unexpected error in request retry loop")

    def put(self, key: str, data: bytes) -> None:
        """Store an object."""
        try:
            self._make_request('PUT', f'objects/{key}', data=data)
        except RestStoreError as e:
            raise KeyError(f"Failed to store object {key}: {str(e)}")

    def get(self, key: str) -> bytes:
        """Retrieve an object."""
        try:
            response = self._make_request('GET', f'objects/{key}')
            return response.content
        except RestStoreError as e:
            raise KeyError(f"Failed to retrieve object {key}: {str(e)}")

    def exists(self, key: str) -> bool:
        """Check if an object exists."""
        try:
            self._make_request('HEAD', f'objects/{key}')
            return True
        except (RestStoreError, KeyError):
            return False

    def delete(self, key: str) -> None:
        """Delete an object."""
        try:
            self._make_request('DELETE', f'objects/{key}')
        except RestStoreError as e:
            raise KeyError(f"Failed to delete object {key}: {str(e)}")

    def keys(self) -> Iterable[str]:
        """List all object keys with pagination."""
        cursor: Optional[str] = None
        
        while True:
            try:
                params = {'limit': 100}
                if cursor:
                    params['cursor'] = cursor
                
                response = self._make_request('GET', 'objects', params=params)
                data = response.json()
                
                for key in data['keys']:
                    yield key
                
                if not data.get('has_more'):
                    break
                    
                cursor = data.get('next_cursor')
                if not cursor:
                    break
                    
            except RestStoreError as e:
                raise NotImplementedError(f"Failed to list keys: {str(e)}")


# Example usage:
if __name__ == '__main__':
    # Create a store client
    store = RestStore(
        base_url='https://api.objectstore.example/v1',
        api_key='your-api-key'
    )
    
    # Use it like any other ObjectStore
    store.put('example-key', b'Hello, World!')
    data = store.get('example-key')
    print(data.decode())  # Hello, World!
    
    # List all keys
    for key in store.keys():
        print(key)
        
    # Use as context manager
    with RestStore(base_url='https://api.objectstore.example/v1', api_key='your-api-key') as store:
        store.put('temp-key', b'temporary data')
        # Session automatically closed after context
