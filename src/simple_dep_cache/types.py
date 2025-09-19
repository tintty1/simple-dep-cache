import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import orjson

try:
    import orjson

    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

CacheValue = str | int | float | bool | dict | list | None | Exception


def serialize_value(value: CacheValue) -> str:
    """Serialize a cache value to string for Redis storage."""
    if isinstance(value, str):
        return value
    if HAS_ORJSON:
        return orjson.dumps(value).decode("utf-8")
    return json.dumps(value)


def deserialize_value(value: str) -> CacheValue:
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
    def dump(self, obj: Any) -> str:
        """Serialize an object to string for Redis storage."""

    @abstractmethod
    def load(self, data: str) -> Any:
        """Deserialize a string from Redis back to Python object."""


class JSONSerializer(BaseSerializer):
    """Default JSON-based serializer with exception support."""

    def dump(self, obj: Any) -> str:
        """Serialize an object to string for Redis storage."""
        if isinstance(obj, Exception):
            return self._dump_exception(obj)
        return serialize_value(obj)

    def load(self, data: str) -> Any:
        """Deserialize a string from Redis back to Python object."""
        # Try to parse as JSON first
        parsed = deserialize_value(data)
        if isinstance(parsed, dict) and parsed.get("type") == "cached_exception":
            return self._load_exception(parsed)
        return parsed

    def _dump_exception(self, exc: Exception) -> str:
        """Serialize an exception to JSON string."""
        exception_data = {
            "type": "cached_exception",
            "exception_class": type(exc).__name__,
            "exception_module": type(exc).__module__,
            "message": str(exc),
        }
        if HAS_ORJSON:
            return orjson.dumps(exception_data).decode("utf-8")
        return json.dumps(exception_data)

    def _load_exception(self, data: dict) -> Exception:
        """Deserialize an exception from JSON data."""
        try:
            # Try to import the exception class
            module = __import__(data["exception_module"], fromlist=[data["exception_class"]])
            exc_class = getattr(module, data["exception_class"])
            # Recreate with the original message
            return exc_class(data["message"])
        except (ImportError, AttributeError, TypeError):
            # Create a dynamic exception class that preserves the original type name
            exception_class_name = data["exception_class"]

            # Create a dynamic exception class
            DynamicExceptionType = type(
                exception_class_name,
                (Exception,),
                {
                    "__module__": data["exception_module"],
                    "__qualname__": exception_class_name,
                },
            )

            return DynamicExceptionType(data["message"])


def get_serializer_class() -> type[BaseSerializer]:
    """Get serializer class from configuration."""
    from .config import config

    serializer_path = config.serializer_class
    if not serializer_path:
        return JSONSerializer

    try:
        module_path, class_name = serializer_path.rsplit(".", 1)
        module = __import__(module_path, fromlist=[class_name])
        serializer_class = getattr(module, class_name)

        # Validate that it's a subclass of BaseSerializer
        if not issubclass(serializer_class, BaseSerializer):
            raise ValueError(f"Serializer class {serializer_path} must inherit from BaseSerializer")

        return serializer_class
    except (ImportError, AttributeError, ValueError) as e:
        # Fallback to JSONSerializer if there's any issue
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            f"Failed to load serializer class {serializer_path}: {e}. Using JSONSerializer."
        )
        return JSONSerializer


def get_serializer() -> BaseSerializer:
    """Get configured serializer instance."""
    serializer_class = get_serializer_class()
    return serializer_class()
