import random

import httpx
import pytest

from tests.mock import make_client, recorder, respond
from yama import APIStatusError, RateLimitError, ServerError


@pytest.mark.parametrize(
    "failure",
    [respond(429), respond(500), respond(502), respond(503), httpx.ConnectError("refused")],
    ids=["429", "500", "502", "503", "network"],
)
def test_rty_1_retries_and_succeeds(failure: httpx.Response | Exception) -> None:
    handler, requests = recorder(failure, respond(body={"ok": True}))
    client, sleeps = make_client(handler)
    assert client._request("GET", "codes/") == {"ok": True}
    assert len(requests) == 2
    assert len(sleeps) == 1


@pytest.mark.parametrize(("max_retries", "attempts"), [(None, 3), (0, 1), (5, 6)])
def test_rty_1_gives_up_after_max_retries(max_retries: int | None, attempts: int) -> None:
    handler, requests = recorder(respond(503, {"detail": "Down."}))
    kwargs = {} if max_retries is None else {"max_retries": max_retries}
    client, sleeps = make_client(handler, **kwargs)
    with pytest.raises(ServerError):
        client._request("GET", "codes/")
    assert len(requests) == attempts
    assert len(sleeps) == attempts - 1


def test_rty_2_waits_for_retry_after() -> None:
    handler, _ = recorder(respond(429, headers={"Retry-After": "7"}), respond())
    client, sleeps = make_client(handler)
    client._request("GET", "codes/")
    assert sleeps == [7]


def test_rty_2_waits_up_to_sixty_seconds() -> None:
    handler, _ = recorder(respond(429, headers={"Retry-After": "60"}), respond())
    client, sleeps = make_client(handler)
    client._request("GET", "codes/")
    assert sleeps == [60]


def test_rty_3_raises_without_waiting_when_retry_after_exceeds_sixty_seconds() -> None:
    body = {"detail": "Request was throttled. Expected available in 61 seconds."}
    handler, requests = recorder(respond(429, body, headers={"Retry-After": "61"}))
    client, sleeps = make_client(handler)
    with pytest.raises(RateLimitError) as caught:
        client._request("GET", "codes/")
    assert caught.value.retry_after == 61
    assert sleeps == []
    assert len(requests) == 1


def test_rty_4_backs_off_with_increasing_jittered_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    bounds: list[tuple[float, float]] = []

    def uniform(low: float, high: float) -> float:
        bounds.append((low, high))
        return high / 2

    monkeypatch.setattr(random, "uniform", uniform)
    handler, _ = recorder(respond(503))
    client, sleeps = make_client(handler, max_retries=6)
    with pytest.raises(ServerError):
        client._request("GET", "codes/")
    assert bounds == [(0, 0.5), (0, 1), (0, 2), (0, 4), (0, 8), (0, 8)]
    assert sleeps == [high / 2 for _, high in bounds]


def test_rty_4_backs_off_when_a_429_has_no_retry_after() -> None:
    handler, _ = recorder(respond(429), respond())
    client, sleeps = make_client(handler)
    client._request("GET", "codes/")
    assert 0 <= sleeps[0] <= 0.5


@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 409, 415, 422])
def test_rty_5_does_not_retry_other_4xx(status: int) -> None:
    handler, requests = recorder(respond(status, {"detail": "No."}))
    client, sleeps = make_client(handler)
    with pytest.raises(APIStatusError):
        client._request("POST", "codes/", json={})
    assert len(requests) == 1
    assert sleeps == []
