# Object Store API and Client

A simple object storage system with a FastAPI backend and Python client. The system provides a REST API for storing and retrieving binary objects, with support for pagination, prefix filtering, and proper error handling.

## Features

- Simple key-value object storage
- RESTful API with FastAPI backend
- Python client with retry logic and connection pooling
- Support for pagination when listing objects
- Proper error handling and status codes
- Rate limiting support
- API key authentication

## Installation

```bash
pip install .[deploy]
```

## Quick Start Guide

### Using the Python Client

The `RestStore` client provides a simple interface for interacting with the object store:

```python
from client import RestStore

# Initialize the client
store = RestStore.create(
    base_url='http://localhost:8000',
    api_key='your-api-key'
)

# Store an object
store.put('my-key', b'Hello, World!')

# Check if an object exists
if store.exists('my-key'):
    # Retrieve an object
    data = store.get('my-key')
    print(data.decode())  # Hello, World!

# Delete an object
store.delete('my-key')

# List all objects (with automatic pagination)
for key in store.keys():
    print(key)
```

### Using the Context Manager

For better resource management, you can use the client as a context manager:

```python
with RestStore.create(base_url='http://localhost:8000', api_key='your-api-key') as store:
    store.put('temp-key', b'temporary data')
    data = store.get('temp-key')
    # Connection is automatically closed after the context
```

### Client Configuration Options

When initializing the client, you can configure several parameters:

```python
store = RestStore.create(
    base_url='http://localhost:8000',
    api_key='your-api-key',
    timeout=30.0,        # Request timeout in seconds
    max_retries=3,       # Maximum number of retry attempts
    retry_delay=1.0      # Initial delay between retries (doubles after each attempt)
)
```

### Error Handling

The client provides proper error handling through exceptions:

```python
try:
    data = store.get('nonexistent-key')
except KeyError as e:
    print(f"Object not found: {e}")

try:
    for key in store.keys():
        print(key)
except NotImplementedError as e:
    print(f"Listing keys not supported: {e}")
```

## Running the Server

Start the FastAPI server using uvicorn:

```bash
uvicorn objectstore.app:app --host 0.0.0.0 --port 8000
```

## Docker Deployment

### Default Deployment

```bash
# Create tokens
python -m objectstore.auth_tokens add api-user --ttl 365 --scope read --scope write --scope delete

# Start service (uses in-memory store - data not persisted)
docker compose up -d

# Test it
curl http://localhost:8000/health
```

### Custom Object Store Deployment

Configure a storage backend for persistent data:

```bash
# 1. Create storage config
cp storage.yaml.template storage.yaml
# Edit storage.yaml to configure filesystem, S3, or other backend

# 2. Create .env and set storage config
cp dotenv.template .env
# Uncomment STORAGE_CONFIG=./storage.yaml in .env

# 3. Start service
docker compose up -d
```

**Port configuration:** Set `HOST_PORT` in `.env` file (copy from `dotenv.template`)

## Running Tests

The project includes a comprehensive test suite. To use it, make sure you install the "test" optional dependencies

You will need a running service to test against (see above) and a token with read, write, and delete scopes.

You can create the token as follows:

```bash
python -m objectstore.auth_tokens add my-token --ttl 30 --scope read --scope write --scope delete
```

This will print a token, which you should then set as the value of the `TEST_API_TOKEN` environment variable:

```bash
export TEST_API_TOKEN={your token here}
```

By default, token metadata is stored in `tokens.json`, which is where the server expects to find it.

Then run tests:

```bash
python tests/test.py
python tests/async_test.py
```

## API Endpoints

- `PUT /objects/{key}` - Store an object
- `GET /objects/{key}` - Retrieve an object
- `HEAD /objects/{key}` - Check if an object exists
- `DELETE /objects/{key}` - Delete an object
- `GET /objects` - List objects (supports pagination and prefix filtering)

Note that keys with special characters must be URL-encoded and decoded.
This is handled automatically by the client and server-side implementations.
