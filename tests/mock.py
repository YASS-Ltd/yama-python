"""Helpers for tests that mock single HTTP exchanges."""

from collections.abc import Callable
from typing import Any

import httpx

from yama import Yama

KEY = "test-key-7f3a9c"  # made up; distinctive so tests can search for leaks
Handler = Callable[[httpx.Request], httpx.Response]


def respond(
    status: int = 200, body: Any = None, headers: dict[str, str] | None = None
) -> httpx.Response:
    """A JSON response carrying the `API-Version` header, as the API sends."""
    return httpx.Response(
        status, json={} if body is None else body, headers={"API-Version": "v2", **(headers or {})}
    )


def make_client(handler: Handler, **kwargs: Any) -> tuple[Yama, list[float]]:
    """A client whose requests go to `handler` and whose waits are recorded, not slept."""
    kwargs.setdefault("api_key", KEY)
    client = Yama(http_client=httpx.Client(transport=httpx.MockTransport(handler)), **kwargs)
    sleeps: list[float] = []
    client._sleep = sleeps.append
    return client, sleeps


def recorder(*responses: httpx.Response | Exception) -> tuple[Handler, list[httpx.Request]]:
    """A handler that returns (or raises) `responses` in turn, repeating the last one."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        result = responses[min(len(requests), len(responses)) - 1]
        if isinstance(result, Exception):
            raise result
        return httpx.Response(result.status_code, headers=result.headers, content=result.content)

    return handler, requests
