import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, Self, runtime_checkable

from .config import ConfigBase
from .utils import DynamicImporter

if TYPE_CHECKING:
    import orjson

try:
    import orjson

    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False


@runtime_checkable
class CacheableValue(Protocol):
    """Protocol for cacheable values."""

    def cache_serialize(self) -> str | bytes:
        """Serialize the value for caching."""
        ...

    @classmethod
    def cache_deserialize(cls, data: str | bytes) -> Self:
        """Deserialize the value from cached data."""
        ...


CacheValue = str | int | float | bool | dict | list | None | Exception | CacheableValue


def serialize_value(value: Any) -> str | bytes:
    """Serialize a cache value to string for Redis storage."""
    if HAS_ORJSON:
        return orjson.dumps(value)
    return json.dumps(value)


def deserialize_value(value: str | bytes) -> Any:
    """Deserialize a string value from Redis back to Python object."""
    JSONDecodeError = orjson.JSONDecodeError if HAS_ORJSON else json.JSONDecodeError
    try:
        if HAS_ORJSON:
            return orjson.loads(value)
        return json.loads(value)
    except JSONDecodeError:
        return value


class BaseSerializer(ABC):
    """Abstract base class for cache value serializers."""

    @abstractmethod
    def dump(self, obj: Any) -> str | bytes:
        """Serialize an object to string or bytes for storage."""

    @abstractmethod
    def load(self, data: str | bytes) -> Any:
        """Deserialize a string or bytes back to Python object."""

    def exception_to_dict(self, exc: Exception) -> dict:
        """Convert an exception to a dictionary representation."""
        return {
            "type": "cached_exception",
            "exception_class": type(exc).__name__,
            "exception_module": type(exc).__module__,
            "message": str(exc),
        }

    def dict_to_exception(self, data: dict) -> Exception:
        """Convert a dictionary representation back to an exception."""
        return DynamicImporter.safe_load_exception(
            data["exception_module"], data["exception_class"], data["message"]
        )

    def is_exception_dict(self, data: dict) -> bool:
        """Check if a dictionary represents a cached exception."""
        return data.get("type") == "cached_exception"

    def cacheable_value_to_dict(self, value: CacheableValue) -> dict:
        """Convert a CacheableValue to a dictionary for serialization."""
        return {
            "type": "cacheable_value",
            "class": type(value).__name__,
            "module": type(value).__module__,
            "data": value.cache_serialize(),
        }

    def dict_to_cacheable_value(self, data: dict) -> CacheableValue:
        """Convert a dictionary back to a CacheableValue."""
        try:
            value_class = DynamicImporter.load_attribute(data["module"], data["class"])
            return value_class.cache_deserialize(data["data"])
        except (ImportError, AttributeError, TypeError):
            raise ValueError(f"Cannot deserialize CacheableValue of type {data['class']}") from None

    def is_cacheable_value_dict(self, data: dict) -> bool:
        """Check if a dictionary represents a CacheableValue."""
        return data.get("type") == "cacheable_value"


class JSONSerializer(BaseSerializer):
    """Default JSON-based serializer with exception support."""

    def dump(self, obj: Any) -> str | bytes:
        """Serialize an object to string for Redis storage."""
        if isinstance(obj, Exception):
            return self.dump(self.exception_to_dict(obj))
        elif isinstance(obj, CacheableValue):
            return self.dump(self.cacheable_value_to_dict(obj))
        return serialize_value(obj)

    def load(self, data: str | bytes) -> Any:
        """Deserialize a string from Redis back to Python object."""
        # Try to parse as JSON first
        parsed = deserialize_value(data)
        if isinstance(parsed, dict):
            if self.is_cacheable_value_dict(parsed):
                return self.dict_to_cacheable_value(parsed)
            elif self.is_exception_dict(parsed):
                return self.dict_to_exception(parsed)
        return parsed


def get_serializer_class(config: ConfigBase) -> type[BaseSerializer]:
    """Get serializer class from configuration."""

    serializer_path = config.serializer_class
    if not serializer_path:
        return JSONSerializer

    try:
        serializer_class = DynamicImporter.load_class(serializer_path)

        # Validate that it's a subclass of BaseSerializer
        if not issubclass(serializer_class, BaseSerializer):
            raise ValueError(f"Serializer class {serializer_path} must inherit from BaseSerializer")

        return serializer_class
    except (ImportError, AttributeError, ValueError) as e:
        # Fallback to JSONSerializer if there's any issue
        import warnings

        warnings.warn(
            f"Failed to load serializer class {serializer_path}: {e}. Using JSONSerializer.",
            UserWarning,
            stacklevel=2,
        )
        return JSONSerializer


def get_serializer(config: ConfigBase) -> BaseSerializer:
    """Get configured serializer instance."""
    serializer_class = get_serializer_class(config)
    return serializer_class()
