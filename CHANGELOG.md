# Changelog

All notable changes to this project will be documented in this file.

## v0.1.3 - 2025-09-19

### Added

- **Exception Caching**: Added support for caching specific exception types to avoid repeated expensive operations that fail
  - New `cache_exception_types` parameter for both `@cache_with_deps` and `@async_cache_with_deps` decorators
  - Exceptions follow the same TTL and dependency rules as successful results
  - Exception inheritance is respected (child exceptions are cached if parent type is listed)
  - Only exceptions listed in `cache_exception_types` are cached; if None or empty, no exceptions are cached

- **Custom Serializers**: Added support for custom serialization strategies
  - New `BaseSerializer` abstract base class for implementing custom serializers
  - `JSONSerializer` as the default serializer with exception support
  - Configuration via `DEP_CACHE_SERIALIZER` environment variable
  - Built-in support for preserving exception details through serialization

- **Enhanced Documentation**: Comprehensive documentation updates including:
  - Exception caching examples and usage patterns
  - Custom serializer implementation guide
  - Async exception caching examples
  - Security considerations for custom serializers

### Changed

- **Manager Classes**: Updated `CacheManager` and `AsyncCacheManager` to use configurable serializers
  - Replaced direct `serialize_value`/`deserialize_value` calls with serializer instances
  - Automatic serializer instance creation based on configuration

- **Type System**: Expanded `CacheValue` type to include `Exception` objects
  - Updated type hints to reflect exception caching capabilities

### Technical Details

- Added `get_serializer()` and `get_serializer_class()` functions for serializer management
- Enhanced `JSONSerializer` with exception serialization/deserialization support
- Dynamic exception type recreation for cases where original exception class is not available
- Comprehensive test coverage for exception caching scenarios including inheritance patterns
- Added test coverage for custom JSON serializer functionality

## v0.1.2 - 2025-09-19

### Added

- **Custom Cache Key Generation**: Enhanced cache key generation for complex objects with the following priority order:
  1. `__cache_key__()` method - custom cache key generation method
  2. `_cache_key` attribute - custom cache key attribute
  3. `pk` attribute - Django-style primary key support
  4. `id` attribute - general ID attribute support
  5. `str()` representation - fallback for all other objects

### Changed

- Cache key generation now uses more stable representations for complex objects instead of relying solely on `str()` representation
- Objects with same logical identity (e.g., same ID) will now generate identical cache keys even if they are different instances

### Technical Details

- Added `_get_cache_key_for_arg()` function to handle cache key generation for individual arguments
- Updated `_generate_cache_key()` to use the new cache key generation logic for both positional and keyword arguments
- Comprehensive test coverage for all cache key generation scenarios including mixed argument types
