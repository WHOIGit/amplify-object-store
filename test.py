import pytest
from client import RestStore

@pytest.fixture
def store():
    """Create a test RestStore instance"""
    store = RestStore(
        base_url='http://localhost:8000',
        api_key='test-key'
    )
    yield store
    # Clean up any test data
    for key in list(store.keys()):
        if key.startswith('test_'):
            try:
                store.delete(key)
            except KeyError:
                pass

def test_crud_operations(store):
    """Test basic CRUD operations"""
    key = 'test_object'
    data = b'Hello, World!'

    # Test put and exists
    assert not store.exists(key)
    store.put(key, data)
    assert store.exists(key)

    # Test get
    retrieved = store.get(key)
    assert retrieved == data

    # Test delete
    store.delete(key)
    assert not store.exists(key)
    with pytest.raises(KeyError):
        store.get(key)

def test_list_keys(store):
    """Test listing keys"""
    # Create some test objects
    test_data = {
        'test_1': b'data1',
        'test_2': b'data2',
        'test_3': b'data3'
    }
    
    for key, data in test_data.items():
        store.put(key, data)

    # Get all keys and filter test keys
    keys = set(k for k in store.keys() if k.startswith('test_'))
    assert keys == set(test_data.keys())

def test_nonexistent_key(store):
    """Test operations with nonexistent keys"""
    key = 'test_nonexistent'
    
    assert not store.exists(key)
    
    with pytest.raises(KeyError):
        store.get(key)
        
    with pytest.raises(KeyError):
        store.delete(key)

def test_binary_data(store):
    """Test storing and retrieving binary data"""
    key = 'test_binary'
    data = bytes([0, 1, 2, 3, 255, 254, 253, 252])
    
    store.put(key, data)
    retrieved = store.get(key)
    assert retrieved == data

if __name__ == '__main__':
    pytest.main([__file__])