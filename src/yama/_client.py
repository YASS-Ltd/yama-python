"""The client: configuration, sending, retries and error mapping.

The rules (what to send, whether and how long to wait, what a response means) are plain
functions free of I/O; `Yama` only sends with httpx and sleeps.
"""

from __future__ import annotations

import copy
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
    GoneError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    UnprocessableEntityError,
    YamaError,
)
from yama._pagination import T, paginate
from yama._resources import ApiKeyResource, Buildings, Calls, Codes, Contacts, Units

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
    410: GoneError,
    422: UnprocessableEntityError,
    429: RateLimitError,
}
# Retried: the connection failed or broke, or an attempt timed out. Other httpx errors (an
# unsupported scheme, a bad header, a proxy refusal, too many redirects) would fail again.
_TRANSPORT_FAILURES = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)
# Of those, the ones where the request never left the client, so the API can't have run it.
_NOT_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
NOT_GIVEN: Any = object()  # an argument left out, where None means something else
_logger = logging.getLogger("yama")


def _backoff(attempt: int) -> float:
    """Full jitter: a random wait up to 0.5 s, doubling with each attempt, capped at 8 s."""
    return random.uniform(0, min(8.0, 0.5 * 2 ** (attempt - 1)))


def _retry_after(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After", "")
    return int(value) if value.isdigit() else None


def _retry_wait(
    attempt: int,
    max_retries: int,
    request: httpx.Request,
    result: httpx.Response | httpx.HTTPError,
) -> float | None:
    """Seconds to wait before retrying `request` after `attempt` (from 1) failed with
    `result`, a response or an httpx error; None means don't retry.

    A 429, or a failure to connect, means the API never ran the request, so any method is
    retried. A 5xx or any other network failure may come after the API ran it, so a POST is
    retried only with an `Idempotency-Key` (whose 409 means "still running"); every other
    method is safe to repeat.
    """
    if attempt > max_retries:
        return None
    keyed = "Idempotency-Key" in request.headers
    replayable = keyed or request.method != "POST"
    if isinstance(result, httpx.HTTPError):
        if isinstance(result, _NOT_SENT) or (
            replayable and isinstance(result, _TRANSPORT_FAILURES)
        ):
            return _backoff(attempt)
        return None
    status = result.status_code
    if status == 429 or (status == 409 and keyed):
        retry_after = _retry_after(result)
        if retry_after is not None:
            return retry_after if retry_after <= _MAX_RETRY_AFTER else None
        return _backoff(attempt)
    return _backoff(attempt) if status >= 500 and replayable else None


def _check_timeout(timeout: object) -> httpx.Timeout:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float, httpx.Timeout)):
        raise TypeError(
            "timeout must be a number of seconds or an httpx.Timeout; "
            "for no timeout at all, pass httpx.Timeout(None)."
        )
    return timeout if isinstance(timeout, httpx.Timeout) else httpx.Timeout(timeout)


def _check_max_retries(max_retries: object) -> int:
    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise TypeError("max_retries must be an int.")
    if max_retries < 0:
        raise ValueError("max_retries must be 0 or more.")
    return max_retries


def _status_error(request: httpx.Request, response: httpx.Response) -> APIStatusError:
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
    args = (
        status,
        detail,
        body,
        response.headers.get("API-Version"),
        request.method,
        request.url.path,
    )
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
    """The error for a failed attempt. It doesn't chain `exc`, which holds the request and so
    the key."""
    where = f"{request.method} {request.url.path} ({type(exc).__name__})"
    if isinstance(exc, httpx.TimeoutException):
        return APITimeoutError(f"Request timed out: {where}")
    return APIConnectionError(f"Connection failed: {where}")


def _origin(url: str) -> tuple[str, str, int | None] | None:
    """A URL's scheme, host and port, or None when it isn't a valid URL."""
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL:
        return None
    return parsed.scheme, parsed.host, parsed.port


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
        api_key: The API key. Defaults to `YAMA_API_KEY`; passing None doesn't fall back to it.
        base_url: Where to send requests; else `YAMA_API_BASE_URL`, else `DEFAULT_BASE_URL`.
        timeout: Seconds allowed for each phase of an attempt (connect, write, read, pool),
            or an `httpx.Timeout` to set them one by one.
        max_retries: How many times to retry a request after a 429, a 5xx or a network error.
        http_client: Your own `httpx.Client` to send through. The client applies its own
            URL, timeout and headers to each request, and leaves closing it to you.
            An `httpx.AsyncClient` isn't supported.

    Raises:
        YamaError: No API key was given.
        TypeError: `api_key` isn't a string, `timeout` isn't a number of seconds or an
            `httpx.Timeout`, `max_retries` isn't an int, or `http_client` isn't an
            `httpx.Client`.
        ValueError: The API key isn't printable ASCII without spaces, once stripped,
            `base_url` doesn't start with `https://` or `http://`, or `max_retries` is
            negative.
    """

    api_key: ApiKeyResource
    """The API key the client uses: what it may do."""
    buildings: Buildings
    """Your buildings."""
    units: Units
    """Your units."""
    contacts: Contacts
    """The contacts on your units."""
    codes: Codes
    """The access codes on your units."""
    calls: Calls
    """The call log."""

    def __init__(
        self,
        api_key: str | None = NOT_GIVEN,
        *,
        base_url: str | None = None,
        timeout: float | httpx.Timeout = 30.0,
        max_retries: int = 2,
        http_client: httpx.Client | None = None,
    ) -> None:
        if api_key is NOT_GIVEN:
            api_key = os.environ.get("YAMA_API_KEY")
        elif api_key is not None and not isinstance(api_key, str):
            raise TypeError("api_key must be a string.")
        api_key = (api_key or "").strip()
        if not api_key:
            raise YamaError("No API key: pass api_key, or set YAMA_API_KEY.")
        if not all("!" <= char <= "~" for char in api_key):
            raise ValueError("api_key must be printable ASCII without spaces.")
        base_url = base_url or os.environ.get("YAMA_API_BASE_URL") or DEFAULT_BASE_URL
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("base_url must start with https:// or http://.")
        if http_client is not None and not isinstance(http_client, httpx.Client):
            raise TypeError("http_client must be an httpx.Client: the client isn't async yet.")

        self._key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = _check_timeout(timeout)
        self._max_retries = _check_max_retries(max_retries)
        self._owns_http = http_client is None
        self._closed = False
        self._http = http_client or httpx.Client()
        self._sleep: Callable[[float], None] = time.sleep
        self._attach()

    def _attach(self) -> None:
        self.api_key = ApiKeyResource(self)
        self.buildings = Buildings(self)
        self.units = Units(self)
        self.contacts = Contacts(self)
        self.codes = Codes(self)
        self.calls = Calls(self)

    def with_options(
        self,
        *,
        timeout: float | httpx.Timeout = NOT_GIVEN,
        max_retries: int = NOT_GIVEN,
    ) -> Yama:
        """A copy of the client with a different `timeout` or `max_retries`, sharing its
        connections, key and base URL, such as a fail-fast client for a web view.

        Closing the copy leaves the connections open; closing this client closes them for
        both.
        """
        clone = copy.copy(self)
        if timeout is not NOT_GIVEN:
            clone._timeout = _check_timeout(timeout)
        if max_retries is not NOT_GIVEN:
            clone._max_retries = _check_max_retries(max_retries)
        clone._owns_http = False
        clone._attach()
        return clone

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
        """Close the client's connections, unless they belong to the `http_client` you passed.
        Using the client afterwards raises `ValueError`."""
        self._closed = True
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

        `path` is relative to `/api/v2/`, or a full URL such as a page's `next`, which must be
        on the base URL so the key never goes elsewhere.
        """
        if self._closed or self._http.is_closed:
            raise ValueError("The client is closed.")
        url = path if "://" in path else f"{self._base_url}/api/v2/{path}"
        origin = _origin(url)
        if origin is None or origin != _origin(self._base_url):
            raise YamaError("Refusing to follow a URL that isn't on the configured base URL.")
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
        may_have_run = False  # whether an earlier attempt may have reached the API (RTY-8)
        while True:
            attempt += 1
            started = time.monotonic()
            response: httpx.Response | None = None
            try:
                response = self._http.send(request)
            except httpx.HTTPError as exc:
                result: httpx.Response | httpx.HTTPError = exc
                error: YamaError = _connection_error(request, exc)
                outcome = type(exc).__name__
            else:
                result = response
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
                if may_have_run and request.method == "DELETE" and response.status_code == 404:
                    return None  # an earlier attempt deleted it (RTY-8)
                error = _status_error(request, response)
            wait = _retry_wait(attempt, self._max_retries, request, result)
            if wait is None:
                raise error
            # A 429 or a failure to connect means the API never ran it; anything else retried may.
            may_have_run |= not (
                isinstance(result, _NOT_SENT)
                or (response is not None and response.status_code == 429)
            )
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
