"""The exceptions the client raises. They hold plain fields only, so they pickle."""

from __future__ import annotations


class YamaError(Exception):
    """Base class for every error the client raises. Raised itself for misconfiguration, or a
    response the client can't read."""

    idempotency_key: str | None = None
    """The idempotency key a failed `codes.create` sent, so you can send it again with it;
    None for any other call."""


class APIConnectionError(YamaError):
    """The request failed at the network level, after retries. It may never have been sent."""


class APITimeoutError(APIConnectionError):
    """The last attempt timed out, after retries. The API may still have processed it."""


class APIStatusError(YamaError):
    """The base class for HTTP errors; raised itself for a status without its own class.
    Quote its `request_id` to Yama support when asking about a failed call."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        body: object,
        api_version: str | None,
        method: str,
        path: str,
        request_id: str | None = None,
    ) -> None:
        super().__init__(status_code, detail, body, api_version, method, path, request_id)
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
        self.request_id = request_id
        """The response's `Request-Id` header, which Yama support asks for to find the request;
        None when it has none."""

    def __str__(self) -> str:
        where = f"{self.method} {self.path}"
        if self.request_id:
            where += f", Request-Id {self.request_id}"
        return f"{self.status_code} {self.detail} ({where})"


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
    """404: no such object within the API key's reach."""


class ConflictError(APIStatusError):
    """409: a request with the same idempotency key is still being processed, after
    retries."""


class GoneError(APIStatusError):
    """410: a create repeated with its idempotency key did happen, but the code it created has
    since been deleted or is out of the API key's reach. Don't create it again with that
    idempotency key."""


class UnprocessableEntityError(APIStatusError):
    """422: the idempotency key was already used with a different request. Each create needs
    its own idempotency key."""


class RateLimitError(APIStatusError):
    """429: too many requests, after retries, or at once when the wait is over 60 seconds."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        body: object,
        api_version: str | None,
        method: str,
        path: str,
        request_id: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(status_code, detail, body, api_version, method, path, request_id)
        self.args = (*self.args, retry_after)
        self.retry_after = retry_after
        """Seconds the API asked the client to wait, from `Retry-After`; None when it didn't
        say."""


class ServerError(APIStatusError):
    """5xx: the API failed."""
