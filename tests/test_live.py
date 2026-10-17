"""The scenario against a local Yama API: `just test-live <base-url>`, with `YAMA_API_KEY` set.

Skipped unless both are given, and never run in CI. Only a server on this machine is accepted
(a django-poc checkout with seed data), so the tests can't reach production or a shared server.
Read-only unless `YAMA_LIVE_WRITE=1`, which creates one access code on the first unit and deletes
it again.
"""

import os
import random
from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest

from yama import (
    AccessCodeCreate,
    AuthenticationError,
    BadRequestError,
    GoneError,
    NotFoundError,
    UnprocessableEntityError,
    Yama,
)

BASE_URL = os.environ.get("YAMA_LIVE_BASE_URL", "")
WRITE = os.environ.get("YAMA_LIVE_WRITE") == "1"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (BASE_URL and os.environ.get("YAMA_API_KEY")),
        reason="live tests need `just test-live <base-url>` and YAMA_API_KEY",
    ),
]


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def is_local(url: str) -> bool:
    """Whether `url` is a server on this machine, parsed as the client parses it."""
    try:
        return httpx.URL(url).host in LOCAL_HOSTS
    except (httpx.InvalidURL, ValueError):  # ValueError: malformed IDNA, such as "xn--a-"
        return False


@pytest.fixture(scope="module")
def client() -> Iterator[Yama]:
    if not is_local(BASE_URL):
        pytest.fail("Live tests only run against a local server: localhost, 127.0.0.1 or ::1.")
    # No proxy from the environment, which would resolve "localhost" on another machine.
    with httpx.Client(trust_env=False) as http, Yama(base_url=BASE_URL, http_client=http) as c:
        yield c


def test_live_reads_every_resource(client: Yama) -> None:
    assert client.api_key.get().scopes
    buildings = list(client.buildings.list())
    assert buildings, "the API key sees at least one building"
    assert client.buildings.get(buildings[0].uuid) == buildings[0]
    for building in buildings:
        assert all(u.building == building.uuid for u in client.units.list(building=building.uuid))
    unit = next(client.units.list())
    assert client.units.get(unit.uuid) == unit
    for contact in client.contacts.list(unit=unit.uuid):
        assert client.contacts.get(contact.uuid) == contact
        break
    for code in client.codes.list():
        assert client.codes.get(code.uuid) == code
        break
    for call in client.calls.list():
        assert client.calls.get(call.uuid).uuid == call.uuid
        break


def test_live_errors(client: Yama) -> None:
    with pytest.raises(NotFoundError):
        client.buildings.get(uuid4())
    with pytest.raises(BadRequestError) as caught:  # an unknown unit, so nothing is created
        client.codes.create(AccessCodeCreate(unit=uuid4(), code="4321"))
    assert caught.value.errors
    with (
        Yama("yk_not.a-real-key", base_url=BASE_URL) as stranger,
        pytest.raises(AuthenticationError),
    ):
        stranger.api_key.get()


@pytest.mark.skipif(not WRITE, reason="writes need YAMA_LIVE_WRITE=1, never against production")
def test_live_idempotent_create_and_delete(client: Yama) -> None:
    unit = next(client.units.list())
    digits = f"{random.randrange(10**6):06d}"
    data = AccessCodeCreate(unit=unit.uuid, name="yama-python live test", code=digits)
    key = str(uuid4())
    code = client.codes.create(data, idempotency_key=key)
    try:
        assert client.codes.create(data, idempotency_key=key).uuid == code.uuid
        assert [c.uuid for c in client.codes.list(unit=unit.uuid, code=digits)] == [code.uuid]
        fast = client.with_options(timeout=5, max_retries=0)
        assert fast.codes.get(code.uuid).uuid == code.uuid
        with pytest.raises(UnprocessableEntityError):
            client.codes.create(data.model_copy(update={"name": "changed"}), idempotency_key=key)
    finally:
        client.codes.delete(code.uuid)
    with pytest.raises(GoneError):
        client.codes.create(data, idempotency_key=key)
