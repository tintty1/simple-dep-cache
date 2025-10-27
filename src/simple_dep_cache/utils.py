"""
Utilities for dynamic module and class importing.
"""

import importlib
from typing import Any


class DynamicImporter:
    """Utility class for dynamic module and class importing."""

    @staticmethod
    def load_class(class_path: str) -> type:
        """
        Load a class from a string like 'package.module.ClassName'.

        Args:
            class_path: Fully qualified class name

        Returns:
            The class object

        Raises:
            ImportError: If module cannot be imported
            AttributeError: If class is not found in module
        """
        module_path, class_name = class_path.rsplit(".", 1)
        return DynamicImporter.load_attribute(module_path, class_name)

    @staticmethod
    def load_attribute(module_path: str, attribute_name: str) -> Any:
        """
        Load an attribute from a module.

        Args:
            module_path: Module import path
            attribute_name: Name of the attribute to load

        Returns:
            The attribute object

        Raises:
            ImportError: If module cannot be imported
            AttributeError: If attribute is not found in module
        """
        module = importlib.import_module(module_path)
        return getattr(module, attribute_name)

    @staticmethod
    def load_exception(exception_module: str, exception_class: str) -> None | type[Exception]:
        """
        Load an exception class from module and class name.

        Args:
            exception_module: Module containing the exception
            exception_class: Name of the exception class

        Returns:
            The exception class

        Raises:
            ImportError: If module cannot be imported
            AttributeError: If exception class is not found
        """
        try:
            return DynamicImporter.load_attribute(exception_module, exception_class)
        except (ImportError, AttributeError):
            # Return None to indicate failure, caller can handle fallback
            return None

    @staticmethod
    def create_dynamic_exception(
        exception_class_name: str, exception_module: str, message: str
    ) -> Exception:
        """
        Create a dynamic exception class when the original cannot be imported.

        Args:
            exception_class_name: Name of the exception class
            exception_module: Module name for metadata
            message: Exception message

        Returns:
            Dynamic exception instance
        """
        DynamicExceptionType = type(
            exception_class_name,
            (Exception,),
            {
                "__module__": exception_module,
                "__qualname__": exception_class_name,
            },
        )
        return DynamicExceptionType(message)

    @staticmethod
    def safe_load_exception(exception_module: str, exception_class: str, message: str) -> Exception:
        """
        Load an exception class, falling back to dynamic creation if import fails.

        Args:
            exception_module: Module containing the exception
            exception_class: Name of the exception class
            message: Exception message

        Returns:
            Exception instance (original or dynamic)
        """
        exc_cls = DynamicImporter.load_exception(exception_module, exception_class)
        if exc_cls is not None:
            return exc_cls(message)
        else:
            return DynamicImporter.create_dynamic_exception(
                exception_class, exception_module, message
            )
