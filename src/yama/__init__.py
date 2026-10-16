"""The official Python client for the Yama API."""

import logging
from importlib.metadata import version

from yama._client import DEFAULT_BASE_URL, Yama
from yama._errors import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    YamaError,
)

__version__ = version("yama")

logging.getLogger("yama").addHandler(logging.NullHandler())

__all__ = [
    "DEFAULT_BASE_URL",
    "APIConnectionError",
    "APIStatusError",
    "APITimeoutError",
    "AuthenticationError",
    "BadRequestError",
    "ConflictError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "ServerError",
    "Yama",
    "YamaError",
    "__version__",
]
