"""One integrator's session, end to end, through every operation against the fake API, with
every request and response checked against the vendored schema."""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest

from tests.schema import operation, operations, validate_request, validate_response
from yama import (
    AccessCodeCreate,
    AccessCodeUpdate,
    BadRequestError,
    GoneError,
    NotFoundError,
    UnprocessableEntityError,
    Yama,
)
from yama.models import AccessLevel, CallResult
from yama.testing import fake_transport


@pytest.fixture
def client() -> Iterator[Yama]:
    fake = fake_transport()
    seen: set[str] = set()

    def checked(request: httpx.Request) -> httpx.Response:
        validate_request(request)
        response = fake.handle_request(request)
        response.read()
        response.request = request
        validate_response(response)
        seen.add(operation(request)["operationId"])
        return response

    with Yama(
        api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(checked))
    ) as c:
        yield c
    assert seen == set(operations()), "the scenario uses every operation"


def test_scenario_drives_every_operation(client: Yama) -> None:
    key_details = client.api_key.get()
    assert key_details.permissions.codes == AccessLevel.WRITE

    buildings = list(client.buildings.list())
    assert client.buildings.get(buildings[0].uuid) == buildings[0]
    units = list(client.units.list(building=buildings[0].uuid))
    assert units and all(u.building == buildings[0].uuid for u in units)
    unit = client.units.get(units[0].uuid)
    assert list(client.units.list(door_digit=unit.door_digit, search=unit.name)) == [unit]

    contacts = list(client.contacts.list(unit=unit.uuid))
    contact = client.contacts.get(contacts[0].uuid)
    assert list(client.contacts.list(number=contact.number, menu_digit=contact.menu_digit)) == [
        contact
    ]

    codes = list(client.codes.list(unit=unit.uuid))
    assert client.codes.get(codes[0].uuid) == codes[0]
    assert list(client.codes.list(code=codes[0].code, name=codes[0].name, search="")) == codes[:1]

    expiry = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)
    key_for_job = str(uuid4())
    data = AccessCodeCreate(unit=unit.uuid, code="482915", name="Dog walker", expires_at=expiry)
    code = client.codes.create(data, idempotency_key=key_for_job)
    assert (code.code, code.name, code.expires_at) == ("482915", "Dog walker", expiry)
    assert client.codes.create(data, idempotency_key=key_for_job) == code  # a replay
    with pytest.raises(UnprocessableEntityError):
        client.codes.create(data.model_copy(update={"name": "Other"}), idempotency_key=key_for_job)
    with pytest.raises(BadRequestError) as caught:
        client.codes.create(AccessCodeCreate(unit=unit.uuid, code="482915"))
    assert caught.value.errors == {"code": ["Access code already exists for this unit."]}

    cleared = client.codes.update(code.uuid, AccessCodeUpdate(expires_at=None))
    assert (cleared.name, cleared.expires_at) == ("Dog walker", None)
    replaced = client.codes.replace(code.uuid, AccessCodeCreate(unit=unit.uuid, code="482916"))
    assert (replaced.code, replaced.name) == ("482916", "Dog walker")
    client.codes.delete(code.uuid)
    with pytest.raises(NotFoundError):
        client.codes.get(code.uuid)
    with pytest.raises(GoneError):
        client.codes.create(data, idempotency_key=key_for_job)

    calls = list(client.calls.list())
    assert calls and len({c.uuid for c in calls}) == len(calls)
    assert client.calls.get(calls[0].uuid) == calls[0]
    accepted = list(client.calls.list(result=CallResult.CODE_ACCEPTED, building=calls[0].building))
    assert accepted and all(c.result == CallResult.CODE_ACCEPTED for c in accepted)
    october = list(
        client.calls.list(
            start=datetime(2026, 10, 1, tzinfo=timezone.utc),
            end=datetime(2026, 11, 1, tzinfo=timezone.utc),
            unit=unit.uuid,
        )
    )
    assert october and all(c.unit == unit.uuid for c in october)
