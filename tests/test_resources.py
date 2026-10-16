import contextlib
import inspect
import json
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
import pytest

from tests.mock import make_client, recorder, respond
from tests.schema import operations
from yama import AccessCodeCreate, AccessCodeUpdate, Yama, YamaError
from yama.models import AccessCode, DoorDigit

UNIT = "dd1053d5-0a4b-4c0d-a619-6a1457d97de6"
CODE_ID = "1dc19ab9-2785-4999-930a-0096ce94c485"
CODE = {"uuid": CODE_ID, "unit": UNIT, "code": "4321", "name": None, "expires_at": None}
BASE = "https://app.yamasystems.com/api/v2/"


def page(*items: dict[str, Any], next_url: str | None = None) -> httpx.Response:
    return respond(body={"count": len(items), "next": next_url, "results": list(items)})


def call(n: int) -> dict[str, Any]:
    return {
        "uuid": f"00000000-0000-4000-8000-{n:012d}",
        "unit": UNIT,
        "building": None,
        "reference": f"REF{n}",
        "started_at": "2026-10-10T22:09:11Z",
        "duration_seconds": None,
        "result": "hung_up",
        "result_label": "Hung up",
        "summary": "Hung up",
        "imported": False,
        "steps": [],
    }


def methods(client: Yama) -> dict[str, Callable[..., Any]]:
    """The client method for each operation in the schema."""
    return {
        "api_key_retrieve": client.api_key.get,
        "buildings_list": client.buildings.list,
        "buildings_retrieve": client.buildings.get,
        "units_list": client.units.list,
        "units_retrieve": client.units.get,
        "contacts_list": client.contacts.list,
        "contacts_retrieve": client.contacts.get,
        "codes_list": client.codes.list,
        "codes_retrieve": client.codes.get,
        "codes_create": client.codes.create,
        "codes_update": client.codes.replace,
        "codes_partial_update": client.codes.update,
        "codes_destroy": client.codes.delete,
        "calls_list": client.calls.list,
        "calls_retrieve": client.calls.get,
    }


# Coverage


def test_ops_1_has_a_method_for_every_operation_with_every_filter() -> None:
    client, _ = make_client(recorder(respond())[0])
    by_operation = methods(client)
    assert set(by_operation) == set(operations())
    for operation_id, operation in operations().items():
        filters = {
            p["name"]
            for p in operation.get("parameters", [])
            if p["in"] == "query" and p["name"] not in ("limit", "offset")
        }
        signature = inspect.signature(by_operation[operation_id])
        keyword_only = {
            name
            for name, param in signature.parameters.items()
            if param.kind is inspect.Parameter.KEYWORD_ONLY
        }
        assert filters <= keyword_only, operation_id
        assert all(signature.parameters[f].default is None for f in filters), operation_id


@pytest.mark.parametrize(
    ("call_method", "method", "path", "status", "body"),
    [
        (lambda c: c.api_key.get(), "GET", "api-key/", 200, {}),
        (lambda c: c.buildings.get(CODE_ID), "GET", f"buildings/{CODE_ID}/", 200, {}),
        (lambda c: c.units.get(UUID(CODE_ID)), "GET", f"units/{CODE_ID}/", 200, {}),
        (lambda c: c.contacts.get(CODE_ID), "GET", f"contacts/{CODE_ID}/", 200, {}),
        (lambda c: c.codes.get(CODE_ID.upper()), "GET", f"codes/{CODE_ID}/", 200, CODE),
        (lambda c: c.calls.get(CODE_ID), "GET", f"calls/{CODE_ID}/", 200, {}),
        (lambda c: c.codes.delete(CODE_ID), "DELETE", f"codes/{CODE_ID}/", 204, None),
    ],
)
def test_ops_1_sends_each_single_object_operation(
    call_method: Callable[[Yama], Any], method: str, path: str, status: int, body: Any
) -> None:
    response = httpx.Response(status) if body is None else respond(status, body)
    handler, requests = recorder(response)
    client, _ = make_client(handler)
    result: Any = ...
    with contextlib.suppress(YamaError):  # an empty body isn't a valid model; the request is
        result = call_method(client)
    assert (requests[0].method, str(requests[0].url)) == (method, BASE + path)
    if method == "DELETE":
        assert result is None


@pytest.mark.parametrize("bad", ["../api-key", "", "not-a-uuid"])
def test_err_4_rejects_a_uuid_that_is_not_one_without_sending(bad: str) -> None:
    handler, requests = recorder(respond())
    client, _ = make_client(handler)
    with pytest.raises(ValueError):
        client.codes.get(bad)
    with pytest.raises(TypeError):
        client.codes.delete(42)  # type: ignore[arg-type]
    assert requests == []


def test_err_4_rejects_request_data_of_the_wrong_model() -> None:
    handler, requests = recorder(respond())
    client, _ = make_client(handler)
    with pytest.raises(TypeError):
        client.codes.create({"unit": UNIT, "code": "4321"})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        client.codes.update(CODE_ID, AccessCodeCreate(unit=UNIT, code="4321"))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        client.calls.list(start=datetime(2026, 10, 1, tzinfo=timezone.utc), end=date(2026, 10, 2))
    assert requests == []


# Requests


def test_http_3_sends_only_the_filters_the_caller_sets() -> None:
    handler, requests = recorder(page())
    client, _ = make_client(handler)
    list(client.units.list(building=UUID(UNIT), door_digit=DoorDigit.NINE))
    list(client.units.list(search=""))
    list(client.codes.list())
    assert [dict(r.url.params) for r in requests] == [
        {"building": UNIT, "door_digit": "9", "limit": "500"},
        {"search": "", "limit": "500"},
        {"limit": "500"},
    ]


def test_http_3_sends_every_filter_by_its_api_name() -> None:
    handler, requests = recorder(page())
    client, _ = make_client(handler)
    list(client.contacts.list(unit=UNIT, number="+16045550111", menu_digit="1"))
    list(client.codes.list(unit=UNIT, code="4321", name="Cleaner", search="clean"))
    list(client.calls.list(unit=UNIT, building=UNIT, result="hung_up"))
    params = [dict(r.url.params) for r in requests]
    assert params[0] == {"unit": UNIT, "number": "+16045550111", "menu_digit": "1", "limit": "500"}
    assert params[1] == {
        "unit": UNIT,
        "code": "4321",
        "name": "Cleaner",
        "search": "clean",
        "limit": "500",
    }
    assert {"unit": UNIT, "building": UNIT, "result": "hung_up"}.items() <= params[2].items()


# Access codes


def test_code_1_sends_a_new_random_idempotency_key_with_each_create() -> None:
    handler, requests = recorder(respond(201, CODE))
    client, _ = make_client(handler)
    data = AccessCodeCreate(unit=UNIT, code="4321")
    created = client.codes.create(data)
    client.codes.create(data)
    assert created == AccessCode.model_validate(CODE)
    keys = [r.headers["Idempotency-Key"] for r in requests]
    assert keys[0] != keys[1]
    assert all(UUID(key).version == 4 for key in keys)


def test_code_1_sends_the_callers_idempotency_key() -> None:
    handler, requests = recorder(respond(201, CODE))
    client, _ = make_client(handler)
    client.codes.create(AccessCodeCreate(unit=UNIT, code="4321"), idempotency_key="job-17")
    assert requests[0].headers["Idempotency-Key"] == "job-17"
    assert (requests[0].method, str(requests[0].url)) == ("POST", f"{BASE}codes/")
    assert json.loads(requests[0].content) == {"unit": UNIT, "code": "4321"}


@pytest.mark.parametrize(
    "failure", [respond(503), httpx.ReadTimeout("slow"), respond(409, {"detail": "In progress."})]
)
def test_code_2_sends_the_same_idempotency_key_on_every_retry(
    failure: httpx.Response | Exception,
) -> None:
    handler, requests = recorder(failure, failure, respond(201, CODE))
    client, _ = make_client(handler)
    client.codes.create(AccessCodeCreate(unit=UNIT, code="4321"))
    assert len(requests) == 3
    assert len({r.headers["Idempotency-Key"] for r in requests}) == 1
    assert len({r.content for r in requests}) == 1


def test_code_3_update_sends_only_the_fields_set_including_none() -> None:
    handler, requests = recorder(respond(body=CODE))
    client, _ = make_client(handler)
    updated = client.codes.update(CODE_ID, AccessCodeUpdate(expires_at=None))
    client.codes.update(CODE_ID, AccessCodeUpdate(name="Cleaner", code="9876"))
    assert updated.expires_at is None
    assert [(r.method, str(r.url)) for r in requests] == [("PATCH", f"{BASE}codes/{CODE_ID}/")] * 2
    assert [json.loads(r.content) for r in requests] == [
        {"expires_at": None},
        {"name": "Cleaner", "code": "9876"},
    ]
    assert "Idempotency-Key" not in requests[0].headers


def test_code_3_replace_sends_only_the_fields_set() -> None:
    handler, requests = recorder(respond(body=CODE))
    client, _ = make_client(handler)
    expiry = datetime(2026, 11, 1, tzinfo=timezone(timedelta(hours=-7)))
    client.codes.replace(CODE_ID, AccessCodeCreate(unit=UNIT, code="4321"))
    client.codes.replace(CODE_ID, AccessCodeCreate(unit=UNIT, code="4321", expires_at=expiry))
    assert [r.method for r in requests] == ["PUT", "PUT"]
    assert [json.loads(r.content) for r in requests] == [
        {"unit": UNIT, "code": "4321"},
        {"unit": UNIT, "code": "4321", "expires_at": "2026-11-01T00:00:00-07:00"},
    ]


# Call log


def test_call_1_skips_calls_already_yielded() -> None:
    page_2 = f"{BASE}calls/?offset=2"
    handler, _ = recorder(page(call(1), call(2), next_url=page_2), page(call(2), call(3)))
    client, _ = make_client(handler)
    calls = list(client.calls.list())
    assert [c.reference for c in calls] == ["REF1", "REF2", "REF3"]


def test_call_1_deduplicates_within_one_iteration_only() -> None:
    handler, _ = recorder(page(call(1)))
    client, _ = make_client(handler)
    assert len(list(client.calls.list())) == 1
    assert len(list(client.calls.list())) == 1


def test_call_2_treats_omitted_dates_as_an_open_range() -> None:
    handler, requests = recorder(page())
    client, _ = make_client(handler)
    today = datetime.now(timezone.utc).date().isoformat()
    list(client.calls.list())
    list(client.calls.list(start=date(2026, 10, 1)))
    list(client.calls.list(end=date(2026, 10, 31)))
    ranges = [(r.url.params["start"], r.url.params["end"]) for r in requests]
    assert ranges[0] == ("2000-01-01", today)
    assert ranges[1][0] == "2026-10-01"
    assert ranges[2] == ("2000-01-01", "2026-10-31")


def test_call_3_sends_dates_in_iso_8601() -> None:
    handler, requests = recorder(page())
    client, _ = make_client(handler)
    list(client.calls.list(start=date(2026, 1, 2), end=date(2026, 12, 31)))
    assert (requests[0].url.params["start"], requests[0].url.params["end"]) == (
        "2026-01-02",
        "2026-12-31",
    )
