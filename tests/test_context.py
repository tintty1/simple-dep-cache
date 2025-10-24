"""Tests for simple_dep_cache.context module."""

from simple_dep_cache.context import (
    add_dependency,
    clear_current_dependencies,
    current_cache_key,
    get_all_dependencies,
    get_cache_manager,
    get_cache_ttl,
    get_current_dependencies,
    get_dependencies_for_manager,
    pop_operation_context,
    push_operation_context,
    reset,
    set_cache_manager,
    set_cache_ttl,
    set_current_cache_key,
)


class TestContextStackOperations:
    """Test cases for context stack management."""

    def setup_method(self):
        """Reset context before each test."""
        reset()

    def test_push_and_pop_operation_context(self):
        """Test pushing and popping operation contexts."""
        # Push first operation
        push_operation_context(
            manager_name="manager1",
            cache_key="key1",
            cache_manager=None,
            cache_ttl=60,
            dependencies={"dep1"},
        )

        assert current_cache_key() == "key1"
        assert get_current_dependencies() == {"dep1"}
        assert get_cache_ttl() == 60

        # Push second operation (nested)
        push_operation_context(
            manager_name="manager1",
            cache_key="key2",
            cache_manager=None,
            cache_ttl=30,
            dependencies={"dep2"},
        )

        assert current_cache_key() == "key2"
        assert get_current_dependencies() == {"dep2"}
        assert get_cache_ttl() == 30

        # Pop second operation
        popped_deps = pop_operation_context()
        assert popped_deps == {"manager1": {"dep2"}}

        # Should be back to first operation, but dependencies are merged
        assert current_cache_key() == "key1"
        assert get_current_dependencies() == {"dep1", "dep2"}  # Dependencies merged from child
        assert get_cache_ttl() == 60

        # Pop first operation
        popped_deps = pop_operation_context()
        assert popped_deps == {
            "manager1": {"dep1", "dep2"}
        }  # Parent has accumulated merged dependencies

        # No more operations
        assert current_cache_key() is None
        assert get_current_dependencies() == set()
        assert get_cache_ttl() is None

    def test_dependency_merging_on_pop(self):
        """Test that dependencies are merged to parent operation when popping."""
        # Push parent operation
        push_operation_context(
            manager_name="manager1",
            cache_key="parent_key",
            cache_manager=None,
            dependencies={"parent_dep"},
        )

        # Push child operation
        push_operation_context(
            manager_name="manager1",
            cache_key="child_key",
            cache_manager=None,
            dependencies={"child_dep1", "child_dep2"},
        )

        # Add dependency to child
        add_dependency("child_dep3")

        # Pop child operation
        popped_deps = pop_operation_context()

        # Parent should have both parent and child dependencies
        assert get_current_dependencies() == {
            "parent_dep",
            "child_dep1",
            "child_dep2",
            "child_dep3",
        }

    def test_pop_empty_stack(self):
        """Test popping from an empty stack."""
        result = pop_operation_context()
        assert result == {}

    def test_multiple_managers_dependency_merging(self):
        """Test dependency merging across multiple managers."""
        # Push operation with manager1
        push_operation_context(
            manager_name="manager1", cache_key="key1", cache_manager=None, dependencies={"dep1"}
        )

        # Push nested operation with different managers
        push_operation_context(
            manager_name="manager2", cache_key="key2", cache_manager=None, dependencies={"dep2"}
        )

        # Add dependency to manager2
        add_dependency("dep3", manager="manager2")

        # Add dependency to manager1 from nested context
        add_dependency("dep4", manager="manager1")

        # Pop nested operation
        popped_deps = pop_operation_context()

        # Should have dependencies for both managers
        all_deps = get_all_dependencies()
        assert all_deps == {"manager1": {"dep1", "dep4"}, "manager2": {"dep2", "dep3"}}


class TestCacheKeyOperations:
    """Test cases for cache key operations."""

    def setup_method(self):
        """Reset context before each test."""
        reset()

    def test_set_and_get_current_cache_key(self):
        """Test setting and getting the current cache key."""
        # Initially should be None
        assert current_cache_key() is None

        # Push an operation context
        push_operation_context("manager", "initial_key", None)

        assert current_cache_key() == "initial_key"

        # Change the cache key
        set_current_cache_key("new_key")
        assert current_cache_key() == "new_key"

    def test_set_cache_key_without_context(self):
        """Test setting cache key when there's no active context."""
        # Should not raise an error, just do nothing
        set_current_cache_key("some_key")
        assert current_cache_key() is None


class TestDependencyOperations:
    """Test cases for dependency management operations."""

    def setup_method(self):
        """Reset context before each test."""
        reset()

    def test_add_dependency_with_context(self):
        """Test adding a dependency when there's an active context."""
        push_operation_context("manager1", "key1", None, dependencies={"initial_dep"})

        add_dependency("new_dep")
        assert get_current_dependencies() == {"initial_dep", "new_dep"}

    def test_add_dependency_without_context(self):
        """Test adding a dependency when there's no active context."""
        # Should not raise an error, just do nothing
        add_dependency("some_dep")
        assert get_current_dependencies() == set()

    def test_add_dependency_for_specific_manager(self):
        """Test adding a dependency for a specific manager."""
        push_operation_context("manager1", "key1", None)

        # Add dependency for default manager
        add_dependency("dep1")
        assert get_current_dependencies() == {"dep1"}

        # Add dependency for different manager
        add_dependency("dep2", manager="manager2")

        all_deps = get_all_dependencies()
        assert all_deps == {"manager1": {"dep1"}, "manager2": {"dep2"}}

    def test_add_dependency_without_manager_name(self):
        """Test adding dependency when no manager name is available."""
        push_operation_context(None, "key1", None)

        # Initially should have empty set for None key from push_operation_context
        assert get_all_dependencies() == {None: set()}

        # add_dependency should return early since target_manager is None, so no change
        add_dependency("some_dep")
        assert get_all_dependencies() == {None: set()}  # Should remain unchanged

    def test_get_current_dependencies(self):
        """Test getting current dependencies."""
        push_operation_context("manager1", "key1", None, dependencies={"dep1", "dep2"})
        assert get_current_dependencies() == {"dep1", "dep2"}

    def test_get_current_dependencies_no_context(self):
        """Test getting dependencies when there's no context."""
        assert get_current_dependencies() == set()

    def test_get_dependencies_for_manager(self):
        """Test getting dependencies for a specific manager."""
        push_operation_context("manager1", "key1", None, dependencies={"dep1"})
        add_dependency("dep2", manager="manager2")

        assert get_dependencies_for_manager("manager1") == {"dep1"}
        assert get_dependencies_for_manager("manager2") == {"dep2"}
        assert get_dependencies_for_manager("nonexistent") == set()

    def test_get_dependencies_for_manager_no_context(self):
        """Test getting dependencies when there's no context."""
        assert get_dependencies_for_manager("any_manager") == set()

    def test_get_all_dependencies(self):
        """Test getting all dependencies for all managers."""
        push_operation_context("manager1", "key1", None, dependencies={"dep1"})
        add_dependency("dep2", manager="manager2")
        add_dependency("dep3", manager="manager2")

        all_deps = get_all_dependencies()
        assert all_deps == {"manager1": {"dep1"}, "manager2": {"dep2", "dep3"}}

    def test_get_all_dependencies_no_context(self):
        """Test getting all dependencies when there's no context."""
        assert get_all_dependencies() == {}

    def test_clear_current_dependencies(self):
        """Test clearing current dependencies."""
        push_operation_context("manager1", "key1", None, dependencies={"dep1", "dep2"})
        add_dependency("dep3", manager="manager2")

        assert get_current_dependencies() == {"dep1", "dep2"}
        assert get_dependencies_for_manager("manager2") == {"dep3"}

        clear_current_dependencies()

        assert get_current_dependencies() == set()
        assert get_dependencies_for_manager("manager2") == set()
        assert get_all_dependencies() == {}

    def test_clear_dependencies_no_context(self):
        """Test clearing dependencies when there's no context."""
        # Should not raise an error
        clear_current_dependencies()
        assert get_all_dependencies() == {}


class TestCacheManagerOperations:
    """Test cases for cache manager operations."""

    def setup_method(self):
        """Reset context before each test."""
        reset()

    def test_set_and_get_cache_manager(self):
        """Test setting and getting the cache manager."""
        mock_manager = "mock_manager"

        # Initially should be None
        assert get_cache_manager() is None

        # Push an operation context
        push_operation_context("manager", "key1", mock_manager)

        assert get_cache_manager() == mock_manager

        # Change the cache manager
        new_manager = "new_manager"
        set_cache_manager(new_manager)
        assert get_cache_manager() == new_manager

    def test_set_cache_manager_without_context(self):
        """Test setting cache manager when there's no active context."""
        # Should not raise an error, just do nothing
        set_cache_manager("some_manager")
        assert get_cache_manager() is None


class TestCacheTTLOperations:
    """Test cases for cache TTL operations."""

    def setup_method(self):
        """Reset context before each test."""
        reset()

    def test_set_and_get_cache_ttl(self):
        """Test setting and getting the cache TTL."""
        # Initially should be None
        assert get_cache_ttl() is None

        # Push an operation context
        push_operation_context("manager", "key1", None, cache_ttl=60)

        assert get_cache_ttl() == 60

        # Change the TTL
        set_cache_ttl(120)
        assert get_cache_ttl() == 120

    def test_set_cache_ttl_without_context(self):
        """Test setting cache TTL when there's no active context."""
        # Should not raise an error, just do nothing
        set_cache_ttl(30)
        assert get_cache_ttl() is None


class TestResetOperation:
    """Test cases for reset operation."""

    def setup_method(self):
        """Setup a context before reset tests."""
        push_operation_context("manager1", "key1", None, dependencies={"dep1"})
        add_dependency("dep2")
        set_current_cache_key("test_key")
        set_cache_ttl(60)

    def test_reset_clears_all_context(self):
        """Test that reset clears all context information."""
        # Verify context is set up
        assert current_cache_key() == "test_key"
        assert get_current_dependencies() == {"dep1", "dep2"}
        assert get_cache_ttl() == 60
        assert get_all_dependencies() == {"manager1": {"dep1", "dep2"}}

        # Reset context
        reset()

        # Everything should be cleared
        assert current_cache_key() is None
        assert get_current_dependencies() == set()
        assert get_cache_ttl() is None
        assert get_all_dependencies() == {}

    def test_reset_empty_context(self):
        """Test resetting when context is already empty."""
        reset()  # Should not raise an error
        reset()  # Should still not raise an error
