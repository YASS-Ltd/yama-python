"""The exceptions the client raises. They hold plain fields only, so they pickle."""

from __future__ import annotations


class YamaError(Exception):
    """Base class for every error the client raises, and raised itself for misconfiguration."""

    idempotency_key: str | None = None
    """The `Idempotency-Key` a failed `codes.create` sent, so you can retry with it; None for
    any other call."""


class APIConnectionError(YamaError):
    """The request failed at the network level, after retries. It may never have been sent."""


class APITimeoutError(APIConnectionError):
    """The last attempt timed out, after retries. The API may still have processed it."""


class APIStatusError(YamaError):
    """The API answered with a non-2xx status."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        body: object,
        api_version: str | None,
        method: str,
        path: str,
    ) -> None:
        super().__init__(status_code, detail, body, api_version, method, path)
        self.status_code = status_code
        """The HTTP status code."""
        self.detail = detail
        """The body's `detail`, or else its field errors joined, or else the HTTP reason."""
        self.body = body
        """The parsed JSON body, or its text when it isn't JSON."""
        self.api_version = api_version
        """The response's `API-Version` header."""
        self.method = method
        """The request's HTTP method."""
        self.path = path
        """The request's URL path, without its query string."""

    def __str__(self) -> str:
        return f"{self.status_code} {self.detail} ({self.method} {self.path})"


class BadRequestError(APIStatusError):
    """400: a field or query parameter is invalid, blank or unknown."""

    @property
    def errors(self) -> dict[str, list[str]]:
        """Each invalid field or query parameter (or a key such as `non_field_errors`),
        mapped to its messages."""
        if not isinstance(self.body, dict):
            return {}
        return {k: v for k, v in self.body.items() if isinstance(v, list)}


class AuthenticationError(APIStatusError):
    """401: the API key is malformed, unknown, deleted or expired."""


class PermissionDeniedError(APIStatusError):
    """403: the API key lacks the permission this operation needs."""


class NotFoundError(APIStatusError):
    """404: no such object within the key's reach."""


class ConflictError(APIStatusError):
    """409: a request with the same `Idempotency-Key` is still being processed, after
    retries."""


class GoneError(APIStatusError):
    """410: a create replayed with its `Idempotency-Key` did happen, but the code it created
    has since been deleted or is out of the key's reach. Don't create it again with that key."""


class UnprocessableEntityError(APIStatusError):
    """422: the `Idempotency-Key` was already used with a different request. Each create needs
    its own key."""


class RateLimitError(APIStatusError):
    """429: too many requests, after retries, or with a `Retry-After` too long to wait."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        body: object,
        api_version: str | None,
        method: str,
        path: str,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(status_code, detail, body, api_version, method, path)
        self.args = (*self.args, retry_after)
        self.retry_after = retry_after
        """Seconds the API asked the client to wait, from `Retry-After`."""


class ServerError(APIStatusError):
    """5xx: the API failed."""
