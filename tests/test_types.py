"""Tests for simple_dep_cache.types module."""

import pytest

from simple_dep_cache.types import (
    JSONSerializer,
    deserialize_value,
    get_serializer,
    get_serializer_class,
    serialize_value,
)


class TestJSONSerializer:
    """Test cases for JSONSerializer class."""

    @pytest.fixture
    def serializer(self):
        """Create a JSONSerializer instance for testing."""
        return JSONSerializer()

    def test_round_trip_serialization(self, serializer):
        """Test that dump/load round trip preserves data."""
        test_cases = [
            "simple string",
            42,
            3.14,
            True,
            False,
            None,
            [1, 2, 3, "test"],
            {"key": "value", "number": 42, "nested": {"inner": True}},
            ValueError("test error"),
        ]

        for original in test_cases:
            serialized = serializer.dump(original)
            deserialized = serializer.load(serialized)
            assert deserialized == original or (
                isinstance(original, Exception)
                and str(deserialized) == str(original)
                and type(deserialized).__name__ == type(original).__name__
            )

    def test_round_trip_for_cacheable_value(self, serializer):
        """Test CacheableValue round trip serialization."""

        class TestCacheable:
            def __init__(self, data):
                self.data = data

            def __eq__(self, other):
                return isinstance(other, TestCacheable) and self.data == other.data

            def cache_serialize(self):
                return f"test:{self.data}"

            @classmethod
            def cache_deserialize(cls, data):
                return cls(data[5:])

        # Make class available for dynamic import
        globals()["TestCacheable"] = TestCacheable

        try:
            original = TestCacheable("test_data")
            serialized = serializer.dump(original)
            deserialized = serializer.load(serialized)
            assert deserialized == original
        finally:
            globals().pop("TestCacheable", None)


class TestSerializeFunctions:
    """Test cases for serialize_value and deserialize_value functions."""

    def test_serialize_deserialize_round_trip(self):
        """Test that serialize_value/deserialize_value round trip preserves data."""
        test_cases = [
            "simple string",
            42,
            3.14,
            True,
            False,
            None,
            [1, 2, 3, "test"],
            {"key": "value", "number": 42, "nested": {"inner": True}},
        ]

        for original in test_cases:
            serialized = serialize_value(original)
            deserialized = deserialize_value(serialized)
            assert deserialized == original


class TestSerializerFactory:
    """Test cases for serializer factory functions."""

    def test_get_default_serializer_class(self):
        """Test getting default serializer class."""

        class MockConfig:
            serializer_class = None

        config = MockConfig()
        serializer_class = get_serializer_class(config)
        assert serializer_class is JSONSerializer

    def test_get_default_serializer_instance(self):
        """Test getting default serializer instance."""

        class MockConfig:
            serializer_class = None

        config = MockConfig()
        serializer = get_serializer(config)
        assert isinstance(serializer, JSONSerializer)

    def test_get_custom_serializer_class(self):
        """Test getting custom serializer class."""

        class CustomSerializer(JSONSerializer):
            pass

        class MockConfig:
            serializer_class = f"{__name__}.CustomSerializer"

        # Make class available for dynamic import
        globals()["CustomSerializer"] = CustomSerializer

        try:
            config = MockConfig()
            serializer_class = get_serializer_class(config)
            assert serializer_class is CustomSerializer
        finally:
            globals().pop("CustomSerializer", None)

    def test_get_custom_serializer_instance(self):
        """Test getting custom serializer instance."""

        class CustomSerializer(JSONSerializer):
            pass

        class MockConfig:
            serializer_class = f"{__name__}.CustomSerializer"

        # Make class available for dynamic import
        globals()["CustomSerializer"] = CustomSerializer

        try:
            config = MockConfig()
            serializer = get_serializer(config)
            assert isinstance(serializer, CustomSerializer)
        finally:
            globals().pop("CustomSerializer", None)
