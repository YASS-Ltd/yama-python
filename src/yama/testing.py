"""An in-memory Yama API, for testing code that uses the client without a network or an API key.

    import httpx
    from yama import Yama
    from yama.testing import fake_transport

    http = httpx.Client(transport=fake_transport())
    client = Yama(api_key="test", http_client=http, max_retries=0)

The fake holds a few made-up buildings, units, contacts, access codes and calls, and behaves
like the real API: lists take the same filters; access codes can be created, replaced,
updated and deleted; bad input, such as an expiry in the past (other than a code's current
one, sent back), gets a 400 in the API's format, and a missing object a 404. A create
repeating an idempotency key replays the first answer, or gets a 422 when its body differs,
or a 410 when the code it created has since been deleted.
Any API key works, except `rate-limited`, which gets a 429 with a `Retry-After` longer than the
client waits, on every request.
"""

from __future__ import annotations

import copy
import json
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from yama.models import _CODE_PATTERN, _NAME_MAX

__all__ = ["fake_transport"]


def fake_transport() -> httpx.MockTransport:
    """An `httpx.MockTransport` serving a new in-memory Yama API with its own made-up data."""
    return httpx.MockTransport(_FakeAPI().handle)


def _id(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


def _step(kind: str, at: str, text: str, **facts: str) -> dict[str, Any]:
    empty = dict.fromkeys(
        ("attempt_result", "entered_digits", "code_name", "contact_name", "dial_status")
    )
    return {"kind": kind, "at": at, "text": text, **empty, **facts}


def _call(n: int, unit: str, building: str, at: str, result: str, summary: str) -> dict[str, Any]:
    steps = [_step("received", at, "Call started"), _step("completed", at, "Call ended")]
    return {
        "uuid": _id(n),
        "unit": unit,
        "building": building,
        "reference": f"FAKE{n:02d}",
        "started_at": at,
        "duration_seconds": 12,
        "result": result,
        "result_label": result.replace("_", " ").capitalize(),
        "summary": summary,
        "imported": False,
        "steps": steps,
    }


B1, B2, U1, U2, U3 = _id(1), _id(2), _id(11), _id(12), _id(21)
_API_KEY = {
    "uuid": _id(99),
    "name": "Test key",
    "created_at": "2026-01-01T00:00:00Z",
    "expires_at": "2099-01-01T00:00:00Z",
    "last_used_at": "2026-10-01T00:00:00Z",
    "permissions": {"codes": "write", "contacts": "read", "call_log": "read", "buildings": "read"},
    "scopes": [
        "buildings:read",
        "call_log:read",
        "codes:read",
        "codes:write",
        "contacts:read",
        "units:read",
    ],
    "unit_access": {"type": "all", "buildings": [], "units": []},
}
_DATA: dict[str, list[dict[str, Any]]] = {
    "buildings": [
        {
            "uuid": B1,
            "name": "Example Tower",
            "address": "1 Example St, Vancouver, BC",
            "caller_id": "+16045550100",
            "unit_count": 2,
        },
        {
            "uuid": B2,
            "name": "Sample Court",
            "address": "2 Sample Ave, Vancouver, BC",
            "caller_id": "+16045550200",
            "unit_count": 1,
        },
    ],
    "units": [
        {
            "uuid": U1,
            "building": B1,
            "name": "Unit 101",
            "door_digit": "9",
            "dial_in_number": "+16045550101",
        },
        {
            "uuid": U2,
            "building": B1,
            "name": "Unit 102",
            "door_digit": "9",
            "dial_in_number": "+16045550102",
        },
        {"uuid": U3, "building": B2, "name": "Unit 201", "door_digit": "5", "dial_in_number": None},
    ],
    "contacts": [
        {
            "uuid": _id(31),
            "unit": U1,
            "number": "+16045550111",
            "menu_digit": "1",
            "name": "Concierge",
        },
        {
            "uuid": _id(32),
            "unit": U2,
            "number": "+16045550122",
            "menu_digit": "1",
            "name": "Resident",
        },
    ],
    "codes": [
        {"uuid": _id(41), "unit": U1, "code": "1234", "name": "Primary", "expires_at": None},
        {
            "uuid": _id(42),
            "unit": U1,
            "code": "5678",
            "name": "Visitor",
            "expires_at": "2099-12-31T00:00:00Z",
        },
        {
            "uuid": _id(43),
            "unit": U3,
            "code": "2468",
            "name": None,
            "expires_at": "2020-01-01T00:00:00Z",
        },
    ],
    "calls": [
        _call(51, U1, B1, "2026-10-10T22:09:11Z", "code_accepted", "Primary · Accepted"),
        _call(52, U2, B1, "2026-10-09T18:30:00Z", "forwarded", "Forwarded to a contact"),
        _call(53, U1, B1, "2026-10-08T07:15:42Z", "code_not_accepted", "9999 · Not accepted"),
        _call(54, U3, B2, "2026-09-30T12:00:00Z", "hung_up", "Hung up"),
    ],
}
_FILTERS = {
    "buildings": (),
    "units": ("building", "door_digit", "search"),
    "contacts": ("unit", "number", "menu_digit"),
    "codes": ("unit", "code", "name", "search"),
    "calls": ("unit", "building", "result", "start", "end"),
}
_NAMES = {
    "buildings": "Building",
    "units": "Unit",
    "contacts": "Contact",
    "codes": "AccessCode",
    "calls": "CallLogEntry",
}
_CODE_FIELDS = ("unit", "code", "name", "expires_at")


def _json(
    status: int, body: object = None, headers: dict[str, str] | None = None
) -> httpx.Response:
    headers = {"API-Version": "v2", **(headers or {})}
    if body is None:
        return httpx.Response(status, headers=headers)
    return httpx.Response(status, json=body, headers=headers)


class _FakeAPI:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data = {name: {i["uuid"]: i for i in copy.deepcopy(v)} for name, v in _DATA.items()}
        self._created: dict[str, tuple[object, int, Any]] = {}  # by Idempotency-Key

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") == "Bearer rate-limited":
            detail = "Request was throttled. Expected available in 120 seconds."
            return _json(429, {"detail": detail}, {"Retry-After": "120"})
        with self._lock:
            return self._route(request)

    def _route(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        parts = path.removeprefix("/api/v2/").strip("/").split("/")
        resource = parts[0]
        if not path.startswith("/api/v2/") or len(parts) > 2:
            return _json(404, {"detail": "Not found."})
        if parts == ["api-key"] and method == "GET":
            return _json(200, _API_KEY)
        elif resource in self._data and len(parts) == 1:
            if method == "GET":
                return self._list(request.url, resource)
            if method == "POST" and resource == "codes":
                return self._write_code(request, None)
            return _json(405, {"detail": f'Method "{method}" not allowed.'})
        elif resource in self._data:
            item = self._data[resource].get(parts[1])
            if item is None:
                return _json(404, {"detail": f"No {_NAMES[resource]} matches the given query."})
            if method == "GET":
                return _json(200, item)
            if resource == "codes" and method == "DELETE":
                del self._data["codes"][item["uuid"]]
                return _json(204)
            if resource == "codes" and method in ("PUT", "PATCH"):
                return self._write_code(request, item)
            return _json(405, {"detail": f'Method "{method}" not allowed.'})
        return _json(404, {"detail": "Not found."})

    def _list(self, url: httpx.URL, resource: str) -> httpx.Response:
        query = dict(url.params)
        known = (*_FILTERS[resource], "limit", "offset")
        errors = {k: ["Unknown query parameter."] for k in query if k not in known}
        limit, offset = query.pop("limit", "100"), query.pop("offset", "0")
        if not (limit.isdigit() and 1 <= int(limit) <= 500):
            errors["limit"] = ["Enter a whole number from 1 to 500."]
        if not offset.isdigit():
            errors["offset"] = ["Enter a whole number, 0 or more."]
        items = list(self._data[resource].values())
        if resource == "calls":
            first, last = _date_range(query.pop("start", None), query.pop("end", None), errors)
            items = [c for c in items if first <= c["started_at"][:10] <= last]
            items.sort(key=lambda c: c["started_at"], reverse=True)  # newest first, as the API
        if errors:
            return _json(400, errors)
        search = query.pop("search", None)
        if search is not None:
            items = [item for item in items if search.lower() in (item["name"] or "").lower()]
        items = [item for item in items if all(str(item[k]) == v for k, v in query.items())]
        start, size = int(offset), int(limit)
        more = start + size < len(items)
        return _json(
            200,
            {
                "count": len(items),
                "next": str(url.copy_set_param("offset", start + size)) if more else None,
                "previous": str(url.copy_set_param("offset", max(start - size, 0)))
                if start
                else None,
                "results": items[start : start + size],
            },
        )

    def _write_code(self, request: httpx.Request, current: dict[str, Any] | None) -> httpx.Response:
        try:
            body = json.loads(request.content)
        except ValueError:
            body = None
        key = request.headers.get("Idempotency-Key") if current is None else None
        if key is not None and key in self._created:
            return self._replay(body, *self._created[key])
        response = self._apply_code(request, body, current)
        if key is not None:
            outcome = response.json()
            saved = outcome["uuid"] if response.status_code == 201 else outcome
            self._created[key] = (body, response.status_code, saved)
        return response

    def _replay(self, body: object, first_body: object, status: int, saved: Any) -> httpx.Response:
        """The answer to a create repeating an earlier `Idempotency-Key`."""
        if body != first_body:
            detail = "This Idempotency-Key was already used with a different request."
            return _json(422, {"detail": detail})
        replayed = {"Idempotent-Replayed": "true"}
        if status != 201:
            return _json(status, saved, replayed)
        code = self._data["codes"].get(saved)
        if code is None:
            detail = "The object this request created has since been deleted."
            return _json(410, {"detail": detail}, replayed)
        return _json(201, code, replayed)

    def _apply_code(
        self, request: httpx.Request, body: object, current: dict[str, Any] | None
    ) -> httpx.Response:
        """Create, replace or update a code from `body`, or answer 400."""
        if not isinstance(body, dict):
            return _json(400, {"non_field_errors": ["Send a JSON object."]})
        errors = {k: ["Unknown field."] for k in body if k not in _CODE_FIELDS}
        if "uuid" in body:
            errors["uuid"] = ["This field is read-only."]
        if request.method != "PATCH":
            errors |= {k: ["This field is required."] for k in ("unit", "code") if k not in body}
        if "unit" in body and body["unit"] not in self._data["units"]:
            errors["unit"] = ["Unit does not exist."]
        code = body.get("code", "000")
        if not (isinstance(code, str) and re.fullmatch(_CODE_PATTERN, code)):
            errors["code"] = ["Enter 3 to 15 digits."]
        if isinstance(name := body.get("name"), str) and len(name) > _NAME_MAX:
            errors["name"] = [f"Ensure this field has no more than {_NAME_MAX} characters."]
        try:
            expiry = _instant(body.get("expires_at"))
            # A code's current expiry, sent back unchanged, is accepted even once it has passed.
            current_expiry = _instant((current or {}).get("expires_at"))
            if expiry and expiry <= datetime.now(timezone.utc) and expiry != current_expiry:
                errors["expires_at"] = ["Expiry must be in the future."]
        except ValueError:
            errors["expires_at"] = ["Enter a valid date and time."]
        new = {"uuid": str(uuid.uuid4()), "name": None, "expires_at": None, **(current or {})}
        new |= body
        if not errors and any(
            (c["unit"], c["code"]) == (new["unit"], new["code"]) and c["uuid"] != new["uuid"]
            for c in self._data["codes"].values()
        ):
            errors["code"] = ["Access code already exists for this unit."]
        if errors:
            return _json(400, errors)
        self._data["codes"][new["uuid"]] = new
        return _json(201 if current is None else 200, new)


def _instant(value: object) -> datetime | None:
    """An ISO 8601 time as an aware datetime (UTC if it has no offset), or None for None.
    Raises `ValueError` for anything else."""
    if value is None:
        return None
    when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _date_range(
    start: str | None, end: str | None, errors: dict[str, list[str]]
) -> tuple[str, str]:
    """The call log's range of UTC dates, as ISO strings; the last 30 days by default."""
    if start is None and end is None:
        today = datetime.now(timezone.utc).date()
        return (today - timedelta(days=29)).isoformat(), today.isoformat()
    dates = {"start": start, "end": end}
    for name, value in dates.items():
        try:
            dates[name] = date.fromisoformat(value or "").isoformat()
        except ValueError:
            errors[name] = ["Enter both dates."] if value is None else ["Enter a valid date."]
    return dates["start"] or "", dates["end"] or ""
