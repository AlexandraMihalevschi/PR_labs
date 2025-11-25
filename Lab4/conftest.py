"""
Pytest configuration for async tests.
This ensures all async test functions are automatically handled by pytest-asyncio.
"""
import pytest

# Configure pytest-asyncio to use the default event loop policy
pytest_plugins = ('pytest_asyncio',)


