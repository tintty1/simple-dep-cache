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
from simple_dep_cache import cache_with_deps, add_dependency, CacheManager

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
```

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

## Configuration

```bash
REDIS_URL=redis://localhost:6379/0    # Full Redis URL (preferred)
REDIS_HOST=localhost                  # Or individual settings
REDIS_PORT=6379
REDIS_PASSWORD=secret
DEP_CACHE_ENABLED=true                # Disable caching entirely
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

- `@cache_with_deps(cache_manager, ttl, key_prefix, dependencies)`
- `@async_cache_with_deps(cache_manager, ttl, key_prefix, dependencies)`

If `cache_manager` is not provided, one will be created automatically using configured environment variables or defaults.

**Context:**

- `add_dependency(dependency)` - Track dependency in current function
- `current_cache_key()` - Get current cache key

**Managers:**

- `CacheManager(redis_client, prefix)` - Sync Redis cache manager
- `AsyncCacheManager(redis_client, prefix)` - Async Redis cache manager

**Monitoring:**

- `StatsCollector()` - Cache statistics

## Requirements

- Python 3.10+
- Redis server
- `redis` package

## License

MIT
