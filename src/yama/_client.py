"""The client: configuration, sending, retries and error mapping.

The rules (what to send, whether and how long to wait, what a response means) are plain
functions free of I/O; `Yama` only sends with httpx and sleeps.
"""

from __future__ import annotations

import logging
import os
import random
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from importlib.metadata import version
from types import TracebackType
from typing import Any

import httpx

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
from yama._pagination import T, paginate

DEFAULT_BASE_URL = "https://app.yamasystems.com"
"""Where the client sends requests unless `base_url` or `YAMA_API_BASE_URL` says otherwise."""

_USER_AGENT = f"yama-python/{version('yama')} python/{sys.version_info[0]}.{sys.version_info[1]}"
_MAX_RETRY_AFTER = 60
_ERRORS: dict[int, type[APIStatusError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    429: RateLimitError,
}
_OMITTED: Any = object()
_logger = logging.getLogger("yama")


def _backoff(attempt: int) -> float:
    """Full jitter: a random wait up to 0.5 s, doubling with each attempt, capped at 8 s."""
    return random.uniform(0, min(8.0, 0.5 * 2 ** (attempt - 1)))


def _retry_after(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After", "")
    return int(value) if value.isdigit() else None


def _retry_wait(attempt: int, max_retries: int, response: httpx.Response | None) -> float | None:
    """Seconds to wait before retrying after `attempt` (from 1) failed with `response`, or with
    a network error when it's None; None means don't retry."""
    if attempt > max_retries:
        return None
    if response is None:
        return _backoff(attempt)
    status = response.status_code
    if status != 429 and status < 500:
        return None
    retry_after = _retry_after(response) if status == 429 else None
    if retry_after is None:
        return _backoff(attempt)
    return retry_after if retry_after <= _MAX_RETRY_AFTER else None


def _status_error(response: httpx.Response) -> APIStatusError:
    """The error for a non-2xx response."""
    body: object
    try:
        body = response.json()
    except ValueError:
        body = response.text
    status = response.status_code
    detail = body.get("detail") if isinstance(body, dict) else None
    if not isinstance(detail, str):
        if isinstance(body, dict) and body:
            detail = "; ".join(
                f"{key}: {' '.join(map(str, value)) if isinstance(value, list) else value}"
                for key, value in body.items()
            )
        else:
            detail = response.reason_phrase
    args = (status, detail, body, response.headers.get("API-Version"))
    error_class = _ERRORS.get(status, ServerError if status >= 500 else APIStatusError)
    if error_class is RateLimitError:
        return RateLimitError(*args, retry_after=_retry_after(response))
    return error_class(*args)


def _success(request: httpx.Request, response: httpx.Response) -> Any:
    """The parsed JSON of a 2xx response, or None when it has no body."""
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        raise YamaError(
            f"Invalid JSON in the response to {request.method} {request.url.path}."
        ) from None


def _connection_error(request: httpx.Request, exc: httpx.HTTPError) -> APIConnectionError:
    where = f"{request.method} {request.url.path} ({type(exc).__name__})"
    if isinstance(exc, httpx.TimeoutException):
        error: APIConnectionError = APITimeoutError(f"Request timed out: {where}")
    else:
        error = APIConnectionError(f"Connection failed: {where}")
    error.__cause__ = exc
    return error


def _log(level: int, message: str, request: httpx.Request, **facts: object) -> None:
    """Log `message`, formatted with the request's method and path (never its query or
    headers) and `facts`, each also as a `yama_`-prefixed extra field."""
    if _logger.isEnabledFor(level):
        facts = {"method": request.method, "path": request.url.path, **facts}
        _logger.log(level, message, facts, extra={f"yama_{k}": v for k, v in facts.items()})


class Yama:
    """A client for the Yama API.

    Use it as a context manager, or call `close()` when done. One client can be shared
    between threads.

    Args:
        api_key: The API key. Only when it's omitted, `YAMA_API_KEY` is used.
        base_url: Where to send requests; else `YAMA_API_BASE_URL`, else `DEFAULT_BASE_URL`.
        timeout: Seconds allowed for each phase of an attempt (connect, write, read, pool),
            or an `httpx.Timeout` to set them one by one.
        max_retries: How many times to retry a request after a 429, a 5xx or a network error.
        http_client: Your own `httpx.Client` to send through. The client applies its own
            URL, timeout and headers to each request, and leaves closing it to you.

    Raises:
        YamaError: No API key was given.
    """

    def __init__(
        self,
        api_key: str | None = _OMITTED,
        *,
        base_url: str | None = None,
        timeout: float | httpx.Timeout = 30.0,
        max_retries: int = 2,
        http_client: httpx.Client | None = None,
    ) -> None:
        if api_key is _OMITTED:
            api_key = os.environ.get("YAMA_API_KEY")
        elif api_key is not None and not isinstance(api_key, str):
            raise TypeError("api_key must be a string.")
        if not api_key:
            raise YamaError("No API key: pass api_key, or set YAMA_API_KEY.")
        base_url = base_url or os.environ.get("YAMA_API_BASE_URL") or DEFAULT_BASE_URL
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("base_url must start with https:// or http://.")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float, httpx.Timeout)):
            raise TypeError("timeout must be a number of seconds or an httpx.Timeout.")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int):
            raise TypeError("max_retries must be an int.")
        if max_retries < 0:
            raise ValueError("max_retries must be 0 or more.")

        self._key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout if isinstance(timeout, httpx.Timeout) else httpx.Timeout(timeout)
        self._max_retries = max_retries
        self._owns_http = http_client is None
        self._http = http_client or httpx.Client()
        self._sleep: Callable[[float], None] = time.sleep

    def __repr__(self) -> str:
        return f"Yama(base_url={self._base_url!r})"

    def __enter__(self) -> Yama:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the client's connections, unless they belong to the `http_client` you passed."""
        if self._owns_http:
            self._http.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: object = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Send a request, retrying as the API allows, and return its parsed JSON.

        `path` is relative to `/api/v2/`, or a full URL such as a page's `next`.
        """
        url = path if "://" in path else f"{self._base_url}/api/v2/{path}"
        request = self._http.build_request(
            method,
            url,
            params={k: v for k, v in params.items() if v is not None} if params else None,
            json=json,
            headers={
                **(headers or {}),
                "Authorization": f"Bearer {self._key}",
                "User-Agent": _USER_AGENT,
            },
            timeout=self._timeout,
        )
        attempt = 0
        while True:
            attempt += 1
            started = time.monotonic()
            response: httpx.Response | None = None
            try:
                response = self._http.send(request)
            except httpx.HTTPError as exc:
                error: YamaError = _connection_error(request, exc)
                outcome = type(exc).__name__
            else:
                outcome = str(response.status_code)
            _log(
                logging.DEBUG,
                "%(method)s %(path)s %(outcome)s in %(elapsed).3fs (attempt %(attempt)d)",
                request,
                outcome=outcome,
                status=None if response is None else response.status_code,
                elapsed=time.monotonic() - started,
                attempt=attempt,
            )
            if response is not None:
                if response.is_success:
                    return _success(request, response)
                error = _status_error(response)
            wait = _retry_wait(attempt, self._max_retries, response)
            if wait is None:
                raise error
            _log(
                logging.INFO,
                "Retrying %(method)s %(path)s in %(wait).2fs (attempt %(attempt)d) "
                "after %(reason)s",
                request,
                reason=outcome,
                wait=wait,
                attempt=attempt + 1,
            )
            self._sleep(wait)

    def _list(
        self, path: str, model: type[T], params: Mapping[str, object] | None = None
    ) -> Iterator[T]:
        """A new iterator over every item of a list; it sends nothing until iterated."""
        return paginate(self._request, path, model, params)
