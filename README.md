# simple-dep-cache

A Redis-based caching library with dependency tracking for Python applications.

## Overview

Cache function results and automatically invalidate related caches when dependencies change. Uses Redis for distributed caching and supports both sync/async functions.

## Installation

```bash
pip install simple-dep-cache
```

## Quick Start

### Basic Usage

```python
from simple_dep_cache import cache_with_deps, add_dependency, get_cache_manager, CacheManager

# Initialize cache manager (optional - will be created automatically if not provided)
cache = CacheManager()

@cache_with_deps(cache_manager=cache, ttl=300)
def get_user_profile(user_id):
    # This function's result depends on user data
    add_dependency(f"user:{user_id}")

    # Expensive operation (e.g., database query, API call)
    return fetch_user_from_database(user_id)

@cache_with_deps(ttl=600)  # No cache_manager - will create one automatically
def get_user_posts(user_id):
    # This depends on both user and posts data
    add_dependency(f"user:{user_id}")
    add_dependency(f"posts:user:{user_id}")

    return fetch_user_posts_from_database(user_id)

# Use the cached functions
profile = get_user_profile("123")  # Cache miss - fetches from DB
profile = get_user_profile("123")  # Cache hit - returns cached result

posts = get_user_posts("123")     # Cache miss - fetches from DB
posts = get_user_posts("123")     # Cache hit - returns cached result

# When user data changes, invalidate the dependency
cache.invalidate_dependency("user:123")
# Now both get_user_profile("123") and get_user_posts("123") are invalidated!

profile = get_user_profile("123")  # Cache miss - will fetch fresh data

# Access the cache manager from within a cached function
@cache_with_deps()
def some_function():
    current_cache = get_cache_manager()  # Get the active cache manager
    current_cache.invalidate_dependency("some:dependency")
    return "result"
```

### Dynamic TTL Control

Use `set_cache_ttl()` to control cache TTL during function execution:

```python
from simple_dep_cache import cache_with_deps, set_cache_ttl

@cache_with_deps(ttl=300)
def get_data():
    set_cache_ttl(3600)    # Override decorator TTL
    return fetch_data()
```

**Note:** `set_cache_ttl()` takes precedence over decorator `ttl` parameter.

### Custom Cache Key Generation

For complex objects, you can control how cache keys are generated:

```python
class User:
    def __init__(self, user_id, email):
        self.id = user_id
        self.email = email

    def __cache_key__(self):
        """Define custom cache key generation for this object"""
        return f"User::{self.id}"

class Product:
    def __init__(self, product_id):
        self.pk = product_id  # Django-style primary key

    # No custom __cache_key__ needed - will automatically use "Product::{pk}"

@cache_with_deps()
def get_user_orders(user, product_filter=None):
    # Cache key will be generated using User.__cache_key__() and Product's pk
    add_dependency(f"user:{user.id}:orders")
    return fetch_orders(user.id, product_filter)

# Usage
user = User(123, "user@example.com")
product = Product(456)

orders1 = get_user_orders(user, product)  # Cache miss
orders2 = get_user_orders(user, product)  # Cache hit - same logical objects
```

**Cache Key Generation Priority:**

1. `__cache_key__()` method (if present)
2. `_cache_key` attribute (if present)
3. `pk` attribute for Django-style models
4. `id` attribute for objects with IDs
5. `str()` representation (fallback)

### Exception Caching

Cache specific exception types to avoid repeated expensive operations that fail:

```python
import requests
from simple_dep_cache import cache_with_deps

@cache_with_deps(
    ttl=300,
    cache_exception_types=[requests.RequestException, ValueError]
)
def fetch_external_data(api_url):
    # This might raise RequestException on network issues
    # or ValueError on invalid response format
    response = requests.get(api_url, timeout=5)
    response.raise_for_status()

    data = response.json()
    if not data.get("valid"):
        raise ValueError("Invalid response format")

    return data

# First call - may raise and cache the exception
try:
    result = fetch_external_data("https://api.example.com/data")
except requests.RequestException as e:
    print(f"Network error (cached): {e}")

# Second call - exception retrieved from cache (no network call made)
try:
    result = fetch_external_data("https://api.example.com/data")
except requests.RequestException as e:
    print(f"Network error (from cache): {e}")
```

**Exception caching rules:**

- Only exceptions listed in `cache_exception_types` are cached
- If `cache_exception_types` is `None` or empty, no exceptions are cached
- Exceptions follow the same TTL and dependency rules as successful results
- Exception inheritance is respected (child exceptions are cached if parent type is listed)

### Async Support

```python
from simple_dep_cache import async_cache_with_deps, add_dependency, AsyncCacheManager

cache = AsyncCacheManager()

@async_cache_with_deps(cache_manager=cache, ttl=300)
async def get_user_profile_async(user_id):
    add_dependency(f"user:{user_id}")
    return await fetch_user_from_database_async(user_id)

# Usage
profile = await get_user_profile_async("123")  # Cache miss
profile = await get_user_profile_async("123")  # Cache hit

# Invalidate dependency
await cache.invalidate_dependency("user:123")
```

**Async exception caching:**

```python
@async_cache_with_deps(
    cache_exception_types=[aiohttp.ClientError, asyncio.TimeoutError]
)
async def fetch_async_data(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=5) as response:
            if response.status != 200:
                raise aiohttp.ClientError(f"HTTP {response.status}")
            return await response.json()
```

### Monitoring

```python
from simple_dep_cache import StatsCollector, create_logger_callback

cache = CacheManager()
stats = StatsCollector()
cache.events.on_all(stats)
cache.events.on_all(create_logger_callback("my_cache"))

# Check statistics
print(stats.get_stats())  # hit_ratio, ops_per_second, etc.
```

### Custom Serializers

By default, cache values are serialized using JSON. For advanced use cases (like preserving full exception details or using more efficient serialization), you can implement custom serializers:

```python
from simple_dep_cache import BaseSerializer
import pickle
import base64

class PickleSerializer(BaseSerializer):
    """Custom serializer using pickle for full object preservation."""

    def dump(self, obj) -> str:
        pickled = pickle.dumps(obj)
        return base64.b64encode(pickled).decode('utf-8')

    def load(self, data: str):
        pickled = base64.b64decode(data.encode('utf-8'))
        return pickle.loads(pickled)

# Use via environment variable
# DEP_CACHE_SERIALIZER=myapp.serializers.PickleSerializer
```

**Built-in serializers:**

- `JSONSerializer` (default): Safe, human-readable, but may lose some exception details
- Custom serializers: Implement `BaseSerializer` for full control

**Serializer considerations:**

- **Security**: Pickle can execute arbitrary code - only use with trusted data
- **Compatibility**: Custom serializers must be available when deserializing
- **Performance**: JSON is fast for simple data, pickle preserves complex objects

## Configuration

```bash
REDIS_URL=redis://localhost:6379/0    # Full Redis URL (preferred)
REDIS_HOST=localhost                  # Or individual settings
REDIS_PORT=6379
REDIS_PASSWORD=secret
DEP_CACHE_ENABLED=true                # Disable caching entirely
DEP_CACHE_SERIALIZER=simple_dep_cache.types.JSONSerializer  # Custom serializer class
```

## Manual Cache Operations

```python
cache = CacheManager()

# Direct operations
cache.set("key", value, ttl=300, dependencies={"dep1"})
value = cache.get("key")
cache.delete("key")
cache.invalidate_dependency("dep1")  # Invalidates all dependent caches
```

## API Reference

**Decorators:**

- `@cache_with_deps(cache_manager, ttl, key_prefix, dependencies, cache_exception_types)`
- `@async_cache_with_deps(cache_manager, ttl, key_prefix, dependencies, cache_exception_types)`

**Parameters:**

- `cache_manager`: Cache manager instance (optional, auto-created if not provided)
- `ttl`: Time to live in seconds (optional)
- `key_prefix`: Custom prefix for cache keys (optional)
- `dependencies`: Additional static dependencies to track (optional)
- `cache_exception_types`: List of exception types to cache (optional, no exceptions cached if None/empty)

**Context:**

- `add_dependency(dependency)` - Track dependency in current function
- `current_cache_key()` - Get current cache key
- `get_cache_manager()` - Get current cache manager instance
- `set_cache_ttl(ttl)` - Set TTL for current function's cache entry

**Managers:**

- `CacheManager(redis_client, prefix)` - Sync Redis cache manager
- `AsyncCacheManager(redis_client, prefix)` - Async Redis cache manager

**Monitoring:**

- `StatsCollector()` - Cache statistics

**Serializers:**

- `BaseSerializer` - Abstract base class for custom serializers
- `JSONSerializer` - Default JSON-based serializer with exception support

## Requirements

- Python 3.10+
- Redis server
- `redis` package

## License

MIT
