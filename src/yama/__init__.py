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
    GoneError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    UnprocessableEntityError,
    YamaError,
)
from yama.models import (
    AccessCode,
    AccessCodeCreate,
    AccessCodeUpdate,
    AccessLevel,
    ApiKeyDetails,
    ApiKeyPermissions,
    ApiKeyUnitAccess,
    Building,
    CallLogEntry,
    CallLogStep,
    CallResult,
    CallStepKind,
    CodeAttemptResult,
    Contact,
    DialStatus,
    DoorDigit,
    Unit,
    UnitAccessType,
)

__version__ = version("yama")

logging.getLogger("yama").addHandler(logging.NullHandler())

__all__ = [
    "DEFAULT_BASE_URL",
    "APIConnectionError",
    "APIStatusError",
    "APITimeoutError",
    "AccessCode",
    "AccessCodeCreate",
    "AccessCodeUpdate",
    "AccessLevel",
    "ApiKeyDetails",
    "ApiKeyPermissions",
    "ApiKeyUnitAccess",
    "AuthenticationError",
    "BadRequestError",
    "Building",
    "CallLogEntry",
    "CallLogStep",
    "CallResult",
    "CallStepKind",
    "CodeAttemptResult",
    "ConflictError",
    "Contact",
    "DialStatus",
    "DoorDigit",
    "GoneError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "ServerError",
    "Unit",
    "UnitAccessType",
    "UnprocessableEntityError",
    "Yama",
    "YamaError",
    "__version__",
]
