"""The scenario against a real Yama API: `just test-live <base-url>`, with `YAMA_API_KEY` set.

Skipped unless both are given, and never run in CI. Read-only unless `YAMA_LIVE_WRITE=1`, which
creates one access code on the first unit and deletes it again. Never set it against production:
the code opens a real door while it exists.
"""

import os
import random
import socket
from collections.abc import Iterator
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from yama import (
    DEFAULT_BASE_URL,
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


def _addresses(host: str) -> set[str]:
    try:
        return {str(info[4][0]) for info in socket.getaddrinfo(host, 443)}
    except (socket.gaierror, UnicodeError):
        return set()


def is_production(url: str) -> bool:
    """Whether `url` is production by name, or by any address its host shares with production,
    which catches a trailing dot, an IP address or another alias."""
    host = (urlsplit(url).hostname or "").rstrip(".")
    production = urlsplit(DEFAULT_BASE_URL).hostname or ""
    return host == production or bool(_addresses(host) & _addresses(production))


@pytest.fixture(scope="module")
def client() -> Iterator[Yama]:
    if is_production(BASE_URL):
        pytest.fail("Live tests never run against production.")
    with Yama(base_url=BASE_URL) as c:
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
