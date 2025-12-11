import os
import pytest

from objectstore.async_client import AsyncRestStore


@pytest.fixture
async def async_store():
    """Create a test AsyncRestStore instance"""
    store = AsyncRestStore.create(
        base_url='http://localhost:8000',
        api_key=os.environ.get('TEST_API_KEY', 'test_api_key'),
    )
    try:
        yield store
    finally:
        # Clean up any test data
        keys = []
        async for key in store.keys():
            keys.append(key)
        for key in keys:
            if key.startswith('test_'):
                try:
                    await store.delete(key)
                except KeyError:
                    pass
        if isinstance(store, AsyncRestStore):
            await store.close()

@pytest.mark.asyncio
async def test_crud_operations(async_store):
    """Test basic CRUD operations (async)"""
    key = 'test_object'
    data = b'Hello, World!'

    # Test put and exists
    assert not await async_store.exists(key)
    await async_store.put(key, data)
    assert await async_store.exists(key)

    # Test get
    retrieved = await async_store.get(key)
    assert retrieved == data

    # Test delete
    await async_store.delete(key)
    assert not await async_store.exists(key)
    with pytest.raises(KeyError):
        await async_store.get(key)

@pytest.mark.asyncio
async def test_list_keys(async_store):
    """Test listing keys (async)"""
    # Create some test objects
    test_data = {
        'test_1': b'data1',
        'test_2': b'data2',
        'test_3': b'data3',
    }

    for key, data in test_data.items():
        await async_store.put(key, data)

    # Get all keys and filter test keys
    keys = set()
    async for k in async_store.keys():
        if k.startswith('test_'):
            keys.add(k)
    assert keys == set(test_data.keys())

@pytest.mark.asyncio
async def test_nonexistent_key(async_store):
    """Test operations with nonexistent keys (async)"""
    key = 'test_nonexistent'

    assert not await async_store.exists(key)

    with pytest.raises(KeyError):
        await async_store.get(key)

    with pytest.raises(KeyError):
        await async_store.delete(key)

@pytest.mark.asyncio
async def test_binary_data(async_store):
    """Test storing and retrieving binary data (async)"""
    key = 'test_binary'
    data = bytes([0, 1, 2, 3, 255, 254, 253, 252])

    await async_store.put(key, data)
    retrieved = await async_store.get(key)
    assert retrieved == data

@pytest.mark.asyncio
async def test_special_characters_in_keys(async_store):
    """Test keys with special characters (async)"""
    key = 'test_special/characters !@#$%^&*()_+'
    data = b'Special characters'

    await async_store.put(key, data)
    retrieved = await async_store.get(key)
    assert retrieved == data

if __name__ == '__main__':
    # Allow running directly with pytest
    pytest.main([__file__])