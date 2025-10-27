# simple-dep-cache

A flexible caching library with dependency tracking for Python applications.

## Overview

Cache function results and automatically invalidate related caches when dependencies change. Supports multiple cache backends (including Redis) and works seamlessly with both sync and async functions.

## Installation

```bash
pip install simple-dep-cache
```

## Quick Start

### Basic Usage

```python
from simple_dep_cache import cache_with_deps, add_dependency, get_cache_manager, get_or_create_cache_manager

# Initialize cache manager (optional - will be created automatically if not provided)
from simple_dep_cache import create_redis_backend, RedisConfig

redis_config = RedisConfig()
redis_backend = create_redis_backend(redis_config)
cache = get_or_create_cache_manager(
    name="my_cache",
    config=redis_config,
    backend=redis_backend
)

# Or use the simplified factory function
# cache = get_or_create_cache_manager()  # Uses default Redis configuration

# Important: If a manager with the same name already exists in the registry,
# the existing manager is returned and all other parameters (config, backend, etc.)
# are ignored.

@cache_with_deps(name="my_cache", ttl=300)
def get_user_profile(user_id):
    # This function's result depends on user data
    add_dependency(f"user:{user_id}")

    # Expensive operation (e.g., database query, API call)
    return fetch_user_from_database(user_id)

@cache_with_deps(ttl=600)  # No name - will use default cache manager
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

### Nested Dependencies

When cached functions call other cached functions, dependencies from inner functions are automatically collected by the outer function:

```python
@cache_with_deps(ttl=300)
def get_user_data(user_id):
    # This inner function adds its own dependencies
    user_profile = get_user_profile(user_id)
    user_settings = get_user_settings(user_id)

    # The parent function automatically inherits dependencies
    # from both get_user_profile and get_user_settings
    return {
        "profile": user_profile,
        "settings": user_settings
    }

@cache_with_deps(ttl=600)
def get_user_profile(user_id):
    add_dependency(f"user:{user_id}")
    add_dependency(f"profile:{user_id}")
    return fetch_user_profile(user_id)

@cache_with_deps(ttl=300)
def get_user_settings(user_id):
    add_dependency(f"user:{user_id}")
    add_dependency(f"settings:{user_id}")
    return fetch_user_settings(user_id)

# When you invalidate user data, all related caches are invalidated
cache.invalidate_dependency("user:123")
# This invalidates: get_user_data, get_user_profile, get_user_settings for user 123
```

**Key benefits of nested dependencies:**

- **Automatic collection**: Parent functions automatically inherit dependencies from child functions
- **No manual tracking**: You don't need to manually aggregate dependencies from inner calls
- **Granular invalidation**: Cache invalidation is precise and cascades properly through the call hierarchy
- **Mixed sync/async**: Works seamlessly with both sync and async function calls

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

The same `@cache_with_deps` decorator works for both synchronous and asynchronous functions:

```python
from simple_dep_cache import cache_with_deps, add_dependency, get_or_create_cache_manager

cache = get_or_create_cache_manager()  # Uses default Redis configuration

@cache_with_deps(name="my_cache", ttl=300)
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
@cache_with_deps(
    cache_exception_types=[aiohttp.ClientError, asyncio.TimeoutError]
)
async def fetch_async_data(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=5) as response:
            if response.status != 200:
                raise aiohttp.ClientError(f"HTTP {response.status}")
            return await response.json()
```

### Custom Cache Backends

The library supports pluggable cache backends beyond Redis. You can implement custom backends for any storage system:

```python
from simple_dep_cache import CacheBackend, AsyncCacheBackend, ConfigBase
from simple_dep_cache.types import CacheValue

class MemoryBackend(CacheBackend):
    """Simple in-memory cache backend for testing or small applications."""

    def __init__(self, config: ConfigBase):
        super().__init__(config)
        self._cache = {}
        self._dependencies = {}  # {dependency: set_of_cache_keys}

    def set(self, key: str, value: CacheValue, ttl: int | None = None,
            dependencies: Iterable[str] | None = None) -> None:
        cache_key = self._cache_key(key)
        self._cache[cache_key] = value

        # Track dependencies
        for dep in dependencies or []:
            deps_key = self._deps_key(dep)
            if deps_key not in self._dependencies:
                self._dependencies[deps_key] = set()
            self._dependencies[deps_key].add(cache_key)

    def get(self, key: str) -> CacheValue | None:
        return self._cache.get(self._cache_key(key))

    def invalidate_dependency(self, dependency: str) -> int:
        deps_key = self._deps_key(dependency)
        affected_keys = self._dependencies.get(deps_key, set())
        count = len(affected_keys)

        for cache_key in affected_keys:
            self._cache.pop(cache_key, None)
        self._dependencies[deps_key] = set()
        return count

class AsyncMemoryBackend(AsyncCacheBackend):
    """Async version of MemoryBackend."""

    def __init__(self, config: ConfigBase):
        super().__init__(config)
        self._cache = {}
        self._dependencies = {}

    async def set(self, key: str, value: CacheValue, ttl: int | None = None,
                  dependencies: Iterable[str] | None = None) -> None:
        # Similar implementation to sync version
        pass

    async def get(self, key: str) -> CacheValue | None:
        # Similar implementation to sync version
        pass

    async def invalidate_dependency(self, dependency: str) -> int:
        # Similar implementation to sync version
        pass

# Usage with custom backend
from simple_dep_cache import get_or_create_cache_manager, ConfigBase

config = ConfigBase(prefix="my_cache")
memory_backend = MemoryBackend(config)
cache = get_or_create_cache_manager(
    name="my_cache",
    config=config,
    backend=memory_backend
)
```

**Backend Configuration**

Configure backends via environment variables:

```bash
# Custom backend classes
DEP_CACHE_BACKEND_CLASS=myapp.backends.MyCustomBackend
DEP_CACHE_ASYNC_BACKEND_CLASS=myapp.backends.MyAsyncBackend

# Built-in Redis backend (default)
DEP_CACHE_BACKEND_CLASS=simple_dep_cache.redis_backends.RedisCacheBackend
```

**Available built-in backends:**

- `RedisCacheBackend` (default) - Redis-based caching
- `AsyncRedisCacheBackend` (default) - Async Redis caching
- `FakeCacheBackend` - In-memory cache for testing
- `FakeAsyncCacheBackend` - Async in-memory cache for testing

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

### Multiple Cache Managers

You can use multiple cache managers with different backends and configurations:

```python
from simple_dep_cache import cache_with_deps, get_or_create_cache_manager

# Redis-based cache for user data
from simple_dep_cache import RedisConfig, create_redis_backend
user_redis_config = RedisConfig(prefix="users")
user_backend = create_redis_backend(user_redis_config)
user_cache = get_or_create_cache_manager(
    name="users",
    config=user_redis_config,
    backend=user_backend
)

# In-memory cache for frequently accessed data
from simple_dep_cache import ConfigBase, FakeCacheBackend
fast_cache = get_or_create_cache_manager(
    name="fast",
    config=ConfigBase(prefix="fast"),
    backend=FakeCacheBackend(ConfigBase(prefix="fast"))
)

# Use specific cache managers by name
@cache_with_deps(name="users", ttl=300)
def get_user_profile(user_id):
    add_dependency(f"user:{user_id}")
    return fetch_user_from_db(user_id)

@cache_with_deps(name="fast", ttl=60)  # Short TTL for frequently changing data
def get_popular_items():
    add_dependency("popular_items")
    return fetch_popular_items()

# Each cache manager operates independently
user_cache.invalidate_dependency("user:123")  # Only affects user cache
fast_cache.invalidate_dependency("popular_items")  # Only affects fast cache
```

**Cross-Manager Dependencies**

The `manager` parameter in `add_dependency` allows nested functions to add dependencies to specific managers. Dependencies are only active when that manager's operation is active:

```python
@cache_with_deps(name="users")
def get_user_profile(user_id):
    add_dependency(f"user:{user_id}")  # Tracked by 'users' manager
    add_dependency(f"user_data_cache:{user_id}", manager="other_manager")  # Only affects 'other_manager' when it's active
    return fetch_user_from_db(user_id)

@cache_with_deps(name="other_manager")
def get_user_content(user_id):
    # This calls get_user_profile, so both 'users' and 'other_manager' dependencies are active
    profile = get_user_profile(user_id) # be careful here, see the note below
    content = get_user_content_data(user_id)
    return {"profile": profile, "content": content}

# Now invalidating user data affects both caches
other_cache = get_or_create_cache_manager(name="other_manager")
other_cache.invalidate_dependency("user_data_cache:123")  # Invalidates get_user_content result
users_cache = get_or_create_cache_manager(name="users")
users_cache.invalidate_dependency("user:123")  # Invalidates get_user_profile result
```

**Important note**: For cross-manager dependency collection to work, `get_user_profile` must be a cache miss when called by `get_user_content`. If `get_user_profile` were a cache hit, the function wouldn't execute, so the `add_dependency(f"user_data_cache:{user_id}", manager="other_manager")` call wouldn't be triggered and the dependency wouldn't be collected.

**How it works:**

- `add_dependency(f"user:{user_id}")` in `get_user_profile` adds dependency to "users" manager
- `add_dependency(f"user_data_cache{user_id}", manager="other_manager")` in `get_user_profile` adds dependency to "other_manager"
- When `get_user_content()` (using "other_manager") calls `get_user_profile()`, both dependencies are merged into the parent operation
- Each manager only invalidates its own dependencies, enabling coordinated cache invalidation across managers

**Manager isolation and features:**

- **Independent backends**: Each manager can use different storage systems
- **Namespace separation**: Different prefixes prevent key collisions
- **Separate configurations**: TTL, serialization, and backend settings per manager
- **Cross-manager coordination**: Nested functions can add dependencies to parent operation's managers

## Configuration

```bash
# Redis connection (for Redis backends)
REDIS_URL=redis://localhost:6379/0    # Full Redis URL (preferred)
REDIS_HOST=localhost                  # Or individual settings
REDIS_PORT=6379
REDIS_PASSWORD=secret
REDIS_DB=0                            # Database number

# Cache behavior
DEP_CACHE_ENABLED=true                # Disable caching entirely
DEP_CACHE_PREFIX=cache                # Default cache key prefix
DEP_CACHE_SERIALIZER=simple_dep_cache.types.JSONSerializer  # Custom serializer class

# Custom backends
DEP_CACHE_BACKEND_CLASS=myapp.backends.MyCustomBackend
DEP_CACHE_ASYNC_BACKEND_CLASS=myapp.backends.MyAsyncBackend
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

### Callback Support

Monitor cache activity with callback functions:

```python
def cache_callback(**kwargs):
    hit_miss = "HIT" if kwargs['is_hit'] else "MISS"
    print(f"Cache {hit_miss} for {kwargs['func'].__name__}")

@cache_with_deps(cache_manager=cache, callback=cache_callback)
def expensive_function(x):
    return x * 2

# Async callbacks also supported
@async_cache_with_deps(cache_manager=async_cache, callback=cache_callback)
async def async_function(x):
    return await some_async_operation(x)
```

**Callback parameters:** `func`, `cache_manager`, `args`, `kwargs`, `is_hit`, `cached_result`

Callback exceptions are caught and logged.

**Decorators:**

- `@cache_with_deps(name, ttl, dependencies, cache_exception_types, callback)` - Works for both sync and async functions

**Parameters:**

- `name`: Cache manager name to use (optional, uses default if not provided)
- `ttl`: Time to live in seconds (optional)
- `dependencies`: Additional static dependencies to track (optional)
- `cache_exception_types`: List of exception types to cache (optional, no exceptions cached if None/empty)
- `callback`: Callback function invoked on cache hit/miss (optional)

**Context:**

- `add_dependency(dependency, *, manager=None)` - Track dependency in current function
  - Without `manager` param: Adds to current operation's manager
  - With `manager` param: Adds dependency to specified manager (for cross-manager invalidation)
- `current_cache_key()` - Get current cache key
- `get_cache_manager()` - Get current cache manager instance
- `set_cache_ttl(ttl)` - Set TTL for current function's cache entry

**Managers:**

- `get_or_create_cache_manager(name=None, config=None, backend=None, async_backend=None)` - **Primary entry point** - Get or create from registry. If a manager with the same name exists, returns the existing manager and ignores all other parameters.
- `CacheManager(config, name=None, backend=None, async_backend=None)` - Direct constructor (doesn't register)
- `create_redis_backend(config)` - Create Redis backend
- `create_async_redis_backend(config)` - Create async Redis backend

**Backends:**

- `CacheBackend` - Abstract base class for sync backends
- `AsyncCacheBackend` - Abstract base class for async backends
- `RedisCacheBackend` - Redis sync backend implementation
- `AsyncRedisCacheBackend` - Redis async backend implementation
- `FakeCacheBackend` - In-memory sync backend for testing
- `FakeAsyncCacheBackend` - In-memory async backend for testing

**Configuration:**

- `ConfigBase` - Base configuration class
- `RedisConfig` - Redis-specific configuration

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
