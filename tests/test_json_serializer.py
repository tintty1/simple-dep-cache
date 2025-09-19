import json
from unittest.mock import patch

import pytest

from simple_dep_cache.types import HAS_ORJSON, JSONSerializer


class CustomException(Exception):
    """Custom exception for testing."""

    pass


class NonSerializableObject:
    """Object that cannot be serialized by JSON."""

    def __init__(self, data):
        self.data = data


class TestJSONSerializer:
    """Test cases for JSONSerializer class."""

    @pytest.fixture
    def serializer(self):
        """Create a JSONSerializer instance for testing."""
        return JSONSerializer()

    def test_dump_basic_types(self, serializer):
        """Test serialization of basic Python types."""
        assert serializer.dump("hello") == "hello"
        assert serializer.dump(42) == "42"
        assert serializer.dump(3.14) == "3.14"
        assert serializer.dump(True) == "true"
        assert serializer.dump(False) == "false"
        assert serializer.dump(None) == "null"

    def test_dump_collections(self, serializer):
        """Test serialization of lists and dictionaries."""
        test_list = [1, 2, 3, "test"]
        result = serializer.dump(test_list)
        assert json.loads(result) == test_list

        test_dict = {"key": "value", "number": 42, "nested": {"inner": True}}
        result = serializer.dump(test_dict)
        assert json.loads(result) == test_dict

    def test_load_basic_types(self, serializer):
        """Test deserialization of basic Python types."""
        assert serializer.load('"hello"') == "hello"
        assert serializer.load("42") == 42
        assert serializer.load("3.14") == 3.14
        assert serializer.load("true") is True
        assert serializer.load("false") is False
        assert serializer.load("null") is None

    def test_load_collections(self, serializer):
        """Test deserialization of lists and dictionaries."""
        test_list = [1, 2, 3, "test"]
        serialized = json.dumps(test_list)
        assert serializer.load(serialized) == test_list

        test_dict = {"key": "value", "number": 42, "nested": {"inner": True}}
        serialized = json.dumps(test_dict)
        assert serializer.load(serialized) == test_dict

    def test_round_trip_serialization(self, serializer):
        """Test that dump/load round trip preserves data."""
        test_data = {
            "string": "hello world",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "null": None,
            "list": [1, 2, 3],
            "nested": {"inner": "value"},
        }

        serialized = serializer.dump(test_data)
        deserialized = serializer.load(serialized)
        assert deserialized == test_data

    def test_load_invalid_json_returns_original(self, serializer):
        """Test that invalid JSON strings are returned as-is."""
        invalid_json = "not valid json"
        result = serializer.load(invalid_json)
        assert result == invalid_json

        partially_valid = '{"incomplete": '
        result = serializer.load(partially_valid)
        assert result == partially_valid

    def test_dump_exception_basic(self, serializer):
        """Test serialization of basic exceptions."""
        exc = ValueError("Test error message")
        result = serializer.dump(exc)

        # Should be valid JSON
        data = json.loads(result)
        assert data["type"] == "cached_exception"
        assert data["exception_class"] == "ValueError"
        assert data["exception_module"] == "builtins"
        assert data["message"] == "Test error message"

    def test_dump_custom_exception(self, serializer):
        """Test serialization of custom exceptions."""
        exc = CustomException("Custom error")
        result = serializer.dump(exc)

        data = json.loads(result)
        assert data["type"] == "cached_exception"
        assert data["exception_class"] == "CustomException"
        assert data["exception_module"] == __name__
        assert data["message"] == "Custom error"

    def test_load_exception_basic(self, serializer):
        """Test deserialization of basic exceptions."""
        exc_data = {
            "type": "cached_exception",
            "exception_class": "ValueError",
            "exception_module": "builtins",
            "message": "Test error",
        }
        serialized = json.dumps(exc_data)

        result = serializer.load(serialized)
        assert isinstance(result, ValueError)
        assert str(result) == "Test error"

    def test_load_exception_custom(self, serializer):
        """Test deserialization of custom exceptions."""
        exc_data = {
            "type": "cached_exception",
            "exception_class": "CustomException",
            "exception_module": __name__,
            "message": "Custom error",
        }
        serialized = json.dumps(exc_data)

        result = serializer.load(serialized)
        assert isinstance(result, CustomException)
        assert str(result) == "Custom error"

    def test_load_exception_missing_class_creates_dynamic(self, serializer):
        """Test that missing exception classes create dynamic exceptions."""
        exc_data = {
            "type": "cached_exception",
            "exception_class": "NonExistentException",
            "exception_module": "non.existent.module",
            "message": "Dynamic error",
        }
        serialized = json.dumps(exc_data)

        result = serializer.load(serialized)
        assert isinstance(result, Exception)
        assert type(result).__name__ == "NonExistentException"
        assert type(result).__module__ == "non.existent.module"
        assert str(result) == "Dynamic error"

    def test_exception_round_trip(self, serializer):
        """Test exception serialization round trip."""
        original_exc = ValueError("Original message")

        # Serialize and deserialize
        serialized = serializer.dump(original_exc)
        deserialized = serializer.load(serialized)

        # Should be equivalent
        assert isinstance(deserialized, ValueError)
        assert str(deserialized) == str(original_exc)
        assert type(deserialized) is type(original_exc)

    def test_custom_exception_round_trip(self, serializer):
        """Test custom exception serialization round trip."""
        original_exc = CustomException("Custom message")

        # Serialize and deserialize
        serialized = serializer.dump(original_exc)
        deserialized = serializer.load(serialized)

        # Should be equivalent
        assert isinstance(deserialized, CustomException)
        assert str(deserialized) == str(original_exc)
        assert type(deserialized) is type(original_exc)

    def test_non_exception_dict_with_cached_exception_type(self, serializer):
        """Test that regular dicts with 'cached_exception' type are handled correctly."""
        # This is a regular dict that happens to have the cached_exception structure
        # but isn't actually from an exception
        regular_dict = {
            "type": "cached_exception",
            "exception_class": "ValueError",
            "exception_module": "builtins",
            "message": "This is just a dict",
            "extra_field": "should be preserved",
        }

        serialized = serializer.dump(regular_dict)
        deserialized = serializer.load(serialized)

        # Should be treated as exception and recreated as ValueError
        assert isinstance(deserialized, ValueError)
        assert str(deserialized) == "This is just a dict"

    @pytest.mark.skipif(not HAS_ORJSON, reason="orjson not available")
    def test_orjson_serialization(self, serializer):
        """Test that orjson is used when available."""
        test_data = {"key": "value", "number": 42}

        with patch("simple_dep_cache.types.HAS_ORJSON", True):
            with patch("simple_dep_cache.types.orjson") as mock_orjson:
                mock_orjson.dumps.return_value = b'{"mocked": "result"}'

                result = serializer.dump(test_data)

                mock_orjson.dumps.assert_called_once_with(test_data)
                assert result == '{"mocked": "result"}'

    @pytest.mark.skipif(not HAS_ORJSON, reason="orjson not available")
    def test_orjson_deserialization(self, serializer):
        """Test that orjson is used for deserialization when available."""
        test_json = '{"key": "value"}'
        expected_result = {"key": "value"}

        with patch("simple_dep_cache.types.HAS_ORJSON", True):
            with patch("simple_dep_cache.types.orjson") as mock_orjson:
                mock_orjson.loads.return_value = expected_result
                mock_orjson.JSONDecodeError = json.JSONDecodeError

                result = serializer.load(test_json)

                mock_orjson.loads.assert_called_once_with(test_json)
                assert result == expected_result

    def test_string_values_returned_directly(self, serializer):
        """Test that string values are returned directly without JSON encoding."""
        test_string = "simple string"
        result = serializer.dump(test_string)
        assert result == test_string
        assert not result.startswith('"')  # Not JSON-encoded

    def test_exception_with_empty_message(self, serializer):
        """Test serialization of exceptions with empty messages."""
        exc = ValueError("")
        result = serializer.dump(exc)

        data = json.loads(result)
        assert data["message"] == ""

        # Round trip test
        deserialized = serializer.load(result)
        assert isinstance(deserialized, ValueError)
        assert str(deserialized) == ""

    def test_exception_with_complex_message(self, serializer):
        """Test serialization of exceptions with complex messages."""
        complex_message = "Error with 'quotes' and \"double quotes\" and\nnewlines\tand\ttabs"
        exc = RuntimeError(complex_message)

        result = serializer.dump(exc)
        deserialized = serializer.load(result)

        assert isinstance(deserialized, RuntimeError)
        assert str(deserialized) == complex_message

    def test_load_exception_import_error_fallback(self, serializer):
        """Test fallback behavior when exception module can't be imported."""
        exc_data = {
            "type": "cached_exception",
            "exception_class": "SomeException",
            "exception_module": "definitely.not.a.real.module",
            "message": "Fallback test",
        }
        serialized = json.dumps(exc_data)

        result = serializer.load(serialized)

        # Should create a dynamic exception
        assert isinstance(result, Exception)
        assert type(result).__name__ == "SomeException"
        assert type(result).__module__ == "definitely.not.a.real.module"
        assert str(result) == "Fallback test"

    def test_load_exception_attribute_error_fallback(self, serializer):
        """Test fallback when exception class doesn't exist in module."""
        exc_data = {
            "type": "cached_exception",
            "exception_class": "NonExistentException",
            "exception_module": "builtins",  # Valid module, but class doesn't exist
            "message": "Fallback test",
        }
        serialized = json.dumps(exc_data)

        result = serializer.load(serialized)

        # Should create a dynamic exception
        assert isinstance(result, Exception)
        assert type(result).__name__ == "NonExistentException"
        assert type(result).__module__ == "builtins"
        assert str(result) == "Fallback test"
