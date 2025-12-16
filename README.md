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

### Step 1: Create Authentication Tokens

```bash
python -m objectstore.auth_tokens add api-user --ttl 365 --scope read --scope write --scope delete
```

This creates a `tokens.json` file with your API credentials.

### Step 2: Configure Environment

Create a `.env` file from the template:

```bash
cp dotenv.template .env
```

Edit `.env` based on your storage backend choice (see below).

### Step 3: Choose Your Storage Backend

#### Option A: In-Memory Storage (Testing Only)

**Use case:** Quick testing, data is NOT persisted

**Configuration:**
- Leave `STORAGE_CONFIG` commented out in `.env`
- No changes needed to `docker-compose.yml`

```bash
docker compose up -d
```

#### Option B: Filesystem Storage

**Use case:** Persistent local file storage

**Configuration:**

1. In `.env`, uncomment and set:
   ```bash
   STORAGE_CONFIG=./storage.yaml
   HOST_STORAGE_PATH=./data
   ```

2. In `docker-compose.yml`, uncomment both volume mounts:
   ```yaml
   # Optional: Uncomment for YAML-based storage config (S3, etc.)
   - ${STORAGE_CONFIG}:/app/storage.yaml:ro

   # Optional: Uncomment for filesystem-based storage
   - ${HOST_STORAGE_PATH}:/data
   ```

3. Create storage config:
   ```bash
   cp storage.yaml.template storage.yaml
   ```
   The default config uses `AsyncFilesystemStore` with `/data` as the root path.

4. Start the service:
   ```bash
   docker compose up -d
   ```

#### Option C: S3-Compatible Storage

**Use case:** AWS S3, MinIO, or other S3-compatible object storage

**Note:** S3 storage requires additional dependencies. Before deploying, modify `pyproject.toml`:
```python
"amplify-storage-utils[s3] @ git+https://github.com/WHOIGit/amplify-storage-utils@v1.4.1"
```
Then rebuild the Docker image.

**Configuration:**

1. Create an S3 storage config file `storage.yaml`:
   ```yaml
   stores:
     s3:
       type: AsyncBucketStore
       config:
         bucket_name: ${S3_BUCKET}
         endpoint_url: ${S3_ENDPOINT}
         s3_access_key: ${S3_ACCESS_KEY}
         s3_secret_key: ${S3_SECRET_KEY}

   main: s3
   ```

2. In `.env`, set:
   ```bash
   STORAGE_CONFIG=./storage.yaml

   # S3 credentials (adjust as needed)
   S3_BUCKET=your-bucket-name
   S3_ENDPOINT=https://s3.amazonaws.com
   S3_ACCESS_KEY=your-access-key
   S3_SECRET_KEY=your-secret-key
   ```

3. In `docker-compose.yml`, uncomment the storage config volume mount:
   ```yaml
   # Optional: Uncomment for YAML-based storage config (S3, etc.)
   - ${STORAGE_CONFIG}:/app/storage.yaml:ro
   ```

4. Start the service:
   ```bash
   docker compose up -d
   ```

#### Custom Storage Backends

You can use any storage backend provided by [amplify-storage-utils](https://github.com/WHOIGit/amplify-storage-utils) by creating a `storage.yaml` file with the appropriate configuration. See the amplify-storage-utils documentation for available store types and their configuration options. All stores follow the same YAML format shown in the examples above.

### Verifying Deployment

```bash
# Check service health
curl http://localhost:8000/health

# Check logs
docker compose logs -f object-store
```

## Environment Variables

Environment variables can be configured in the `.env` file (copy from `dotenv.template`).

### Host-Side Variables

- `HOST_PORT` - Port exposed on host (default: 8000)
- `TOKENS_FILE` - Path to tokens.json on host (default: ./tokens.json)
- `STORAGE_CONFIG` - Path to storage YAML on host (optional, requires volume mount)
- `HOST_STORAGE_PATH` - Path to data directory on host for filesystem storage (optional, requires volume mount)

### Container-Side Variables

- `WORKERS` - Number of uvicorn workers (default: 1)
- `LOG_LEVEL` - Logging level: debug, info, warning, error (default: info)
- `STORAGE_NAME` - Specific store name from config when multiple stores are defined (optional)

## Running Tests

The project includes a comprehensive test suite. To use it, make sure you install the "test" optional dependencies

You will need a running service to test against (see above) and a token with read, write, and delete scopes.

You can create the token as follows:

```bash
python -m objectstore.auth_tokens add my-token --ttl 30 --scope read --scope write --scope delete
```

This will print a token, which you should then set as the value of the `TEST_API_KEY` environment variable:

```bash
export TEST_API_KEY={your token here}
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
