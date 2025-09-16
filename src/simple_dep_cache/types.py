import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import orjson

try:
    import orjson

    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

CacheValue = str | int | float | bool | dict | list | None


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
