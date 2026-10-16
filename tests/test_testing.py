from typing import Any

import httpx
import pytest

from tests.schema import validate_response
from yama import RateLimitError, Yama
from yama.testing import fake_transport

MISSING = "00000000-0000-4000-8000-ffffffffffff"
LISTS = ["buildings/", "units/", "contacts/", "codes/", "calls/"]


@pytest.fixture
def api() -> httpx.Client:
    """A plain httpx client on the fake API that checks every response against the schema."""
    fake = fake_transport()

    def checked(request: httpx.Request) -> httpx.Response:
        response = fake.handle_request(request)
        response.read()
        response.request = request
        validate_response(response)
        return response

    return httpx.Client(
        transport=httpx.MockTransport(checked),
        base_url="https://fake.example/api/v2/",
        headers={"Authorization": "Bearer test"},
    )


def everything(api: httpx.Client, path: str, **params: Any) -> list[dict[str, Any]]:
    """Every item of a list, one item per page, following `next`."""
    items: list[dict[str, Any]] = []
    url: str | None = path
    query: dict[str, Any] | None = {"limit": 1, **params}
    while url:
        response = api.get(url, params=query)
        assert response.status_code == 200, response.text
        page = response.json()
        items += page["results"]
        url, query = page["next"], None
    return items


def test_test_1_serves_the_fake_api_to_a_client() -> None:
    transport = fake_transport()
    assert isinstance(transport, httpx.MockTransport)
    with Yama(api_key="test", http_client=httpx.Client(transport=transport)) as client:
        assert client._request("GET", "api-key/")["permissions"]["codes"] == "write"


def test_test_1_each_transport_has_its_own_data() -> None:
    first, second = (httpx.Client(transport=fake_transport()) for _ in range(2))
    url = "https://fake.example/api/v2/codes/"
    code = first.get(url).json()["results"][0]
    assert first.delete(f"{url}{code['uuid']}/").status_code == 204
    assert second.get(f"{url}{code['uuid']}/").status_code == 200


def test_test_1_gives_each_response_its_own_request_id(api: httpx.Client) -> None:
    first, second = (api.get(f"codes/{MISSING}/").headers["Request-Id"] for _ in range(2))
    assert first.startswith("req_")
    assert first != second


def test_test_1_reads_the_api_key(api: httpx.Client) -> None:
    assert api.get("api-key/").status_code == 200


@pytest.mark.parametrize("path", LISTS)
def test_test_1_pages_every_list_and_gets_each_item(api: httpx.Client, path: str) -> None:
    params = {"start": "2000-01-01", "end": "2100-01-01"} if path == "calls/" else {}
    items = everything(api, path, **params)
    assert len(items) >= 2
    assert len({item["uuid"] for item in items}) == len(items)
    for item in items:
        assert api.get(f"{path}{item['uuid']}/").json() == item
    response = api.get(f"{path}{MISSING}/")
    assert response.status_code == 404


def test_test_1_filters_lists(api: httpx.Client) -> None:
    building = everything(api, "buildings/")[0]["uuid"]
    units = everything(api, "units/", building=building)
    assert units and all(u["building"] == building for u in units)
    unit = units[0]["uuid"]
    assert all(c["unit"] == unit for c in everything(api, "codes/", unit=unit))
    assert everything(api, "units/", search=units[0]["name"].upper()) == [units[0]]
    calls = everything(api, "calls/", start="2000-01-01", end="2100-01-01", unit=unit)
    assert calls and all(c["unit"] == unit for c in calls)
    assert everything(api, "calls/", start="2000-01-01", end="2000-01-31") == []


def test_test_1_lists_calls_newest_first(api: httpx.Client) -> None:
    calls = everything(api, "calls/", start="2000-01-01", end="2100-01-01")
    times = [c["started_at"] for c in calls]
    assert times == sorted(times, reverse=True)


def test_test_1_searches_codes_that_have_no_name(api: httpx.Client) -> None:
    unit = everything(api, "units/")[0]["uuid"]
    body = {"unit": unit, "code": "98765", "name": None}
    assert api.post("codes/", json=body).status_code == 201
    names = [c["name"] for c in everything(api, "codes/", search="")]
    assert None in names
    assert everything(api, "codes/", search="no such name") == []


@pytest.mark.parametrize(
    ("path", "params", "field"),
    [
        ("units/", {"buildling": "x"}, "buildling"),
        ("codes/", {"limit": "0"}, "limit"),
        ("codes/", {"offset": "x"}, "offset"),
        ("calls/", {"start": "2026-10-01"}, "end"),
        ("calls/", {"start": "October", "end": "2026-10-31"}, "start"),
    ],
)
def test_test_1_rejects_bad_query_parameters(
    api: httpx.Client, path: str, params: dict[str, str], field: str
) -> None:
    response = api.get(path, params=params)
    assert response.status_code == 400
    assert field in response.json()


def test_test_1_creates_updates_and_deletes_a_code(api: httpx.Client) -> None:
    unit = everything(api, "units/")[0]["uuid"]
    body = {"unit": unit, "code": "98765", "name": "Cleaner", "expires_at": None}
    created = api.post("codes/", json=body)
    assert created.status_code == 201
    code = created.json()
    assert code == {"uuid": code["uuid"], **body}
    url = f"codes/{code['uuid']}/"

    patched = api.patch(url, json={"name": None})
    assert patched.json() == {**code, "name": None}

    expiry = "2099-01-01T00:00:00Z"
    replaced = api.put(url, json={"unit": unit, "code": "98766", "expires_at": expiry})
    assert replaced.json() == {**code, "code": "98766", "name": None, "expires_at": expiry}
    assert api.put(url, json={"unit": unit, "code": "98766"}).json()["expires_at"] == expiry

    assert api.delete(url).status_code == 204
    assert api.get(url).status_code == 404
    assert api.delete(url).status_code == 404


def test_test_1_replays_a_create_with_the_same_idempotency_key(api: httpx.Client) -> None:
    unit = everything(api, "units/")[0]["uuid"]
    headers = {"Idempotency-Key": "a3c1e4d2-7a54-4d0b-9a77-1f6c2b9e0d11"}
    first = api.post("codes/", json={"unit": unit, "code": "55555"}, headers=headers)
    again = api.post("codes/", json={"unit": unit, "code": "55555"}, headers=headers)
    assert (first.status_code, again.status_code) == (201, 201)
    assert first.json() == again.json()
    assert [c["code"] for c in everything(api, "codes/", unit=unit)].count("55555") == 1


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"colour": "red"}, "colour"),
        ({"uuid": MISSING}, "uuid"),
        ({"unit": MISSING}, "unit"),
        ({"code": None}, "code"),
    ],
)
def test_test_1_rejects_bad_codes(api: httpx.Client, change: dict[str, Any], field: str) -> None:
    existing = everything(api, "codes/")[0]
    body = {"unit": existing["unit"], "code": "24680"} | change
    for response in (
        api.post("codes/", json=body),
        api.put(f"codes/{existing['uuid']}/", json=body),
        api.patch(f"codes/{existing['uuid']}/", json=change),
    ):
        assert response.status_code == 400
        assert field in response.json()


def test_test_1_rejects_a_code_the_unit_already_has(api: httpx.Client) -> None:
    first, second = everything(api, "codes/")[:2]
    assert first["unit"] == second["unit"]
    for response in (
        api.post("codes/", json={"unit": first["unit"], "code": first["code"]}),
        api.patch(f"codes/{second['uuid']}/", json={"code": first["code"]}),
    ):
        assert response.status_code == 400
        assert response.json() == {"code": ["Access code already exists for this unit."]}


def test_test_1_rejects_an_expiry_in_the_past(api: httpx.Client) -> None:
    existing = everything(api, "codes/")[0]
    url = f"codes/{existing['uuid']}/"
    past = {"expires_at": "2020-01-01T00:00:00Z"}
    body = {"unit": existing["unit"], "code": "24680", **past}
    for response in (
        api.post("codes/", json=body),
        api.put(url, json=body),
        api.patch(url, json=past),
    ):
        assert response.status_code == 400
        assert response.json() == {"expires_at": ["Expiry must be in the future."]}


def test_test_1_accepts_a_codes_current_expiry_sent_back_after_it_passed(
    api: httpx.Client,
) -> None:
    expired = next(
        c for c in everything(api, "codes/") if c["expires_at"] == "2020-01-01T00:00:00Z"
    )
    url = f"codes/{expired['uuid']}/"
    fields = {k: v for k, v in expired.items() if k != "uuid"}
    assert api.put(url, json=fields).status_code == 200
    assert api.patch(url, json={"expires_at": "2020-01-01T00:00:00+00:00"}).status_code == 200
    assert api.patch(url, json={"expires_at": "2020-01-02T00:00:00Z"}).status_code == 400


def test_test_1_requires_unit_and_code_to_create(api: httpx.Client) -> None:
    response = api.post("codes/", json={"name": "No code"})
    assert response.status_code == 400
    assert set(response.json()) == {"unit", "code"}


def test_test_1_rate_limits_on_demand(api: httpx.Client) -> None:
    response = api.get("codes/", headers={"Authorization": "Bearer rate-limited"})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 60
    client = Yama(api_key="rate-limited", http_client=httpx.Client(transport=fake_transport()))
    with pytest.raises(RateLimitError):
        client._request("GET", "codes/")


def test_test_1_replays_a_create_with_its_current_state(api: httpx.Client) -> None:
    unit = everything(api, "units/")[0]["uuid"]
    headers = {"Idempotency-Key": "replay-current"}
    body = {"unit": unit, "code": "55555"}
    code = api.post("codes/", json=body, headers=headers).json()
    api.patch(f"codes/{code['uuid']}/", json={"name": "Renamed"})
    again = api.post("codes/", json=body, headers=headers)
    assert again.status_code == 201
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["name"] == "Renamed"


def test_test_1_replays_a_rejected_create(api: httpx.Client) -> None:
    headers = {"Idempotency-Key": "replay-400"}
    first = api.post("codes/", json={"code": "1"}, headers=headers)
    again = api.post("codes/", json={"code": "1"}, headers=headers)
    assert (first.status_code, again.status_code) == (400, 400)
    assert first.json() == again.json()


def test_test_1_rejects_a_reused_idempotency_key_with_a_different_body(api: httpx.Client) -> None:
    unit = everything(api, "units/")[0]["uuid"]
    headers = {"Idempotency-Key": "reused"}
    assert api.post("codes/", json={"unit": unit, "code": "55555"}, headers=headers).is_success
    response = api.post("codes/", json={"unit": unit, "code": "55556"}, headers=headers)
    assert response.status_code == 422
    assert "Idempotency-Key" in response.json()["detail"]


def test_test_1_answers_410_when_a_replayed_create_was_deleted(api: httpx.Client) -> None:
    unit = everything(api, "units/")[0]["uuid"]
    headers = {"Idempotency-Key": "gone"}
    body = {"unit": unit, "code": "55555"}
    code = api.post("codes/", json=body, headers=headers).json()
    assert api.delete(f"codes/{code['uuid']}/").status_code == 204
    response = api.post("codes/", json=body, headers=headers)
    assert response.status_code == 410
