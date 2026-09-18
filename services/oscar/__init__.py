"""Unified OscarTV API client package."""
from services.oscar.client import OscarClient, oscar_client
from services.oscar.exceptions import (
    OscarAPIError,
    OscarTimeoutError,
    OscarAuthError,
    OscarRateLimitError,
    OscarInvalidResponse,
)

__all__ = [
    "OscarClient",
    "oscar_client",
    "OscarAPIError",
    "OscarTimeoutError",
    "OscarAuthError",
    "OscarRateLimitError",
    "OscarInvalidResponse",
]
