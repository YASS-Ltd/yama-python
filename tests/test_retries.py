import random

import httpx
import pytest

from tests.mock import make_client, recorder, respond
from yama import (
    AccessCodeCreate,
    AccessCodeUpdate,
    APIConnectionError,
    APIStatusError,
    ConflictError,
    NotFoundError,
    RateLimitError,
    ServerError,
)

UNIT = "dd1053d5-0a4b-4c0d-a619-6a1457d97de6"


@pytest.mark.parametrize(
    "failure",
    [
        respond(429),
        respond(500),
        respond(502),
        respond(503),
        httpx.ConnectError("refused"),
        httpx.ConnectTimeout("slow"),
        httpx.ReadTimeout("slow"),
        httpx.ReadError("reset"),
        httpx.WriteError("broken pipe"),
        httpx.RemoteProtocolError("server disconnected"),
    ],
    ids=["429", "500", "502", "503", "connect", "timeout", "read-timeout", "read", "write", "eof"],
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


@pytest.mark.parametrize(
    "failure",
    [
        httpx.LocalProtocolError("bad header"),
        httpx.UnsupportedProtocol("no ftp"),
        httpx.ProxyError("proxy refused"),
        httpx.TooManyRedirects("loop"),
    ],
)
def test_rty_1_does_not_retry_errors_that_are_not_transport_failures(failure: Exception) -> None:
    handler, requests = recorder(failure)
    client, sleeps = make_client(handler)
    with pytest.raises(APIConnectionError):
        client._request("GET", "codes/")
    assert len(requests) == 1
    assert sleeps == []


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


def test_rty_2_waits_for_retry_after_on_a_409_with_an_idempotency_key() -> None:
    conflict = respond(409, {"detail": "In progress."}, headers={"Retry-After": "3"})
    handler, requests = recorder(conflict, respond(201))
    client, sleeps = make_client(handler)
    client._request("POST", "codes/", json={}, headers={"Idempotency-Key": "k"})
    assert sleeps == [3]
    assert len(requests) == 2


def test_rty_3_raises_a_409_without_waiting_when_retry_after_exceeds_sixty_seconds() -> None:
    conflict = respond(409, {"detail": "In progress."}, headers={"Retry-After": "61"})
    handler, requests = recorder(conflict)
    client, sleeps = make_client(handler)
    with pytest.raises(ConflictError):
        client._request("POST", "codes/", json={}, headers={"Idempotency-Key": "k"})
    assert (len(requests), sleeps) == (1, [])


def test_rty_6_retries_a_409_with_an_idempotency_key_counting_against_max_retries() -> None:
    handler, requests = recorder(respond(409, {"detail": "In progress."}))
    client, sleeps = make_client(handler)
    with pytest.raises(ConflictError):
        client._request("POST", "codes/", json={}, headers={"Idempotency-Key": "k"})
    assert len(requests) == 3
    assert len(sleeps) == 2
    assert all(0 <= wait <= 1 for wait in sleeps)


def test_rty_6_retries_a_create_that_gets_a_409() -> None:
    code = {"uuid": UNIT, "unit": UNIT, "code": "4321", "name": None, "expires_at": None}
    handler, requests = recorder(respond(409, {"detail": "In progress."}), respond(201, code))
    client, sleeps = make_client(handler)
    created = client.codes.create(AccessCodeCreate(unit=UNIT, code="4321"))
    assert str(created.uuid) == UNIT
    assert len(requests) == 2
    assert len(sleeps) == 1


AMBIGUOUS = [
    respond(500),
    respond(503),
    httpx.ReadTimeout("slow"),
    httpx.WriteTimeout("slow"),
    httpx.ReadError("reset"),
    httpx.WriteError("broken pipe"),
    httpx.RemoteProtocolError("server disconnected"),
]
AMBIGUOUS_IDS = ["500", "503", "read-timeout", "write-timeout", "read", "write", "eof"]


@pytest.mark.parametrize("failure", AMBIGUOUS, ids=AMBIGUOUS_IDS)
def test_rty_7_does_not_retry_an_ambiguous_failure_of_a_post_without_a_key(
    failure: httpx.Response | Exception,
) -> None:
    handler, requests = recorder(failure, respond(201))
    client, sleeps = make_client(handler)
    with pytest.raises((ServerError, APIConnectionError)):
        client._request("POST", "codes/", json={})
    assert (len(requests), sleeps) == (1, [])


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("failure", AMBIGUOUS, ids=AMBIGUOUS_IDS)
def test_rty_7_retries_an_ambiguous_failure_of_a_put_patch_or_delete(
    method: str, failure: httpx.Response | Exception
) -> None:
    handler, requests = recorder(failure, httpx.Response(204))
    client, sleeps = make_client(handler)
    client._request(method, f"codes/{UNIT}/", json=None if method == "DELETE" else {})
    assert (len(requests), len(sleeps)) == (2, 1)
    assert len({r.content for r in requests}) == 1


@pytest.mark.parametrize("failure", AMBIGUOUS, ids=AMBIGUOUS_IDS)
def test_rty_7_retries_an_ambiguous_failure_of_a_request_with_an_idempotency_key(
    failure: httpx.Response | Exception,
) -> None:
    handler, requests = recorder(failure, respond(201))
    client, _ = make_client(handler)
    client._request("POST", "codes/", json={}, headers={"Idempotency-Key": "k"})
    assert len(requests) == 2


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "failure",
    [
        respond(429),
        httpx.ConnectError("refused"),
        httpx.ConnectTimeout("slow"),
        httpx.PoolTimeout("busy"),
    ],
    ids=["429", "connect", "connect-timeout", "pool-timeout"],
)
def test_rty_7_retries_any_method_when_the_api_never_ran_the_request(
    method: str, failure: httpx.Response | Exception
) -> None:
    handler, requests = recorder(failure, httpx.Response(204))
    client, _ = make_client(handler)
    client._request(method, f"codes/{UNIT}/")
    assert len(requests) == 2


@pytest.mark.parametrize(
    "failure",
    [respond(503), httpx.ReadTimeout("slow"), httpx.ReadError("reset")],
    ids=["503", "timeout", "read"],
)
def test_rty_8_treats_a_404_on_a_retried_delete_as_done(
    failure: httpx.Response | Exception,
) -> None:
    handler, requests = recorder(failure, respond(404, {"detail": "Not found."}))
    client, _ = make_client(handler)
    client.codes.delete(UNIT)  # no NotFoundError
    assert len(requests) == 2


@pytest.mark.parametrize(
    "failure",
    [respond(429), httpx.ConnectError("refused"), httpx.PoolTimeout("busy")],
    ids=["429", "connect", "pool-timeout"],
)
def test_rty_8_raises_not_found_when_no_earlier_attempt_can_have_run(
    failure: httpx.Response | Exception,
) -> None:
    handler, requests = recorder(failure, respond(404, {"detail": "Not found."}))
    client, _ = make_client(handler)
    with pytest.raises(NotFoundError):
        client.codes.delete(UNIT)
    assert len(requests) == 2


def test_rty_8_a_404_after_a_429_that_follows_a_5xx_counts_as_done() -> None:
    handler, requests = recorder(respond(503), respond(429), respond(404, {"detail": "Not found."}))
    client, _ = make_client(handler)
    client.codes.delete(UNIT)
    assert len(requests) == 3


def test_rty_8_a_delete_whose_first_attempt_gets_a_404_raises_not_found() -> None:
    handler, requests = recorder(respond(404, {"detail": "Not found."}))
    client, sleeps = make_client(handler)
    with pytest.raises(NotFoundError):
        client.codes.delete(UNIT)
    assert (len(requests), sleeps) == (1, [])


def test_rty_8_a_404_on_a_retry_of_anything_but_a_delete_still_raises() -> None:
    handler, _ = recorder(respond(503), respond(404, {"detail": "Not found."}))
    client, _ = make_client(handler)
    with pytest.raises(NotFoundError):
        client.codes.update(UNIT, AccessCodeUpdate(name="Cleaner"))
