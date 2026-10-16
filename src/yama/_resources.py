"""One small class per API resource, each method one operation."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from yama._errors import YamaError
from yama._pagination import parse
from yama.models import (
    AccessCode,
    AccessCodeCreate,
    AccessCodeUpdate,
    ApiKeyDetails,
    Building,
    CallLogEntry,
    CallResult,
    Contact,
    DoorDigit,
    Unit,
)

if TYPE_CHECKING:
    from yama._client import Yama

_EARLIEST = date(2000, 1, 1)  # for an open `start`: before any call the API holds (CALL-2)


def _uuid(value: UUID | str) -> str:
    """`value` as a canonical UUID string, so it can't change the path it goes in."""
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, str):
        raise TypeError(f"Expected a UUID or str, not {type(value).__name__}.")
    return str(UUID(value))


def _uuid_filter(value: UUID | str | None) -> str | None:
    return None if value is None else _uuid(value)


def _filters(**filters: object) -> dict[str, str]:
    """The filters the caller set, as query parameters (HTTP-3)."""
    return {
        name: value.value if isinstance(value, Enum) else str(value)
        for name, value in filters.items()
        if value is not None
    }


def _date(name: str, value: date | None, default: date) -> str:
    if value is None:
        return default.isoformat()
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError(f"{name} must be a date, not {type(value).__name__}.")
    return value.isoformat()


def _body(data: AccessCodeCreate | AccessCodeUpdate, model: type) -> object:
    """The fields the caller set, as JSON (CODE-3)."""
    if not isinstance(data, model):
        raise TypeError(f"data must be an {model.__name__}, not {type(data).__name__}.")
    return data.model_dump(mode="json", exclude_unset=True)


class _Resource:
    def __init__(self, client: Yama) -> None:
        self._client = client


class ApiKeyResource(_Resource):
    """The API key the client uses."""

    def get(self) -> ApiKeyDetails:
        """What the key may do: its permissions, scopes, unit access and expiry. Any valid
        key can read this, so it's a good first call."""
        return parse(ApiKeyDetails, self._client._request("GET", "api-key/"))


class Buildings(_Resource):
    """Your buildings (read-only)."""

    def list(self) -> Iterator[Building]:
        """Every building, fetched page by page as you iterate."""
        return self._client._list("buildings/", Building)

    def get(self, uuid: UUID | str) -> Building:
        """One building. Raises `NotFoundError` if it isn't within the key's reach."""
        return parse(Building, self._client._request("GET", f"buildings/{_uuid(uuid)}/"))


class Units(_Resource):
    """Your units (read-only)."""

    def list(
        self,
        *,
        building: UUID | str | None = None,
        door_digit: DoorDigit | str | None = None,
        search: str | None = None,
    ) -> Iterator[Unit]:
        """Every unit, or only those in `building`, with `door_digit`, or whose name contains
        `search` (case-insensitive)."""
        params = _filters(building=_uuid_filter(building), door_digit=door_digit, search=search)
        return self._client._list("units/", Unit, params)

    def get(self, uuid: UUID | str) -> Unit:
        """One unit. Raises `NotFoundError` if it isn't within the key's reach."""
        return parse(Unit, self._client._request("GET", f"units/{_uuid(uuid)}/"))


class Contacts(_Resource):
    """The contacts a visitor can be forwarded to (read-only)."""

    def list(
        self,
        *,
        unit: UUID | str | None = None,
        number: str | None = None,
        menu_digit: str | None = None,
    ) -> Iterator[Contact]:
        """Every contact, or only those on `unit`, with phone `number` (E.164), or reached
        with `menu_digit`."""
        params = _filters(unit=_uuid_filter(unit), number=number, menu_digit=menu_digit)
        return self._client._list("contacts/", Contact, params)

    def get(self, uuid: UUID | str) -> Contact:
        """One contact. Raises `NotFoundError` if it isn't within the key's reach."""
        return parse(Contact, self._client._request("GET", f"contacts/{_uuid(uuid)}/"))


class Codes(_Resource):
    """The access codes on your units."""

    def list(
        self,
        *,
        unit: UUID | str | None = None,
        code: str | None = None,
        name: str | None = None,
        search: str | None = None,
    ) -> Iterator[AccessCode]:
        """Every access code, or only those on `unit`, with exactly the digits `code`, with
        exactly the name `name`, or whose name contains `search` (case-insensitive)."""
        params = _filters(unit=_uuid_filter(unit), code=code, name=name, search=search)
        return self._client._list("codes/", AccessCode, params)

    def get(self, uuid: UUID | str) -> AccessCode:
        """One access code. Raises `NotFoundError` if it isn't within the key's reach."""
        return parse(AccessCode, self._client._request("GET", f"codes/{_uuid(uuid)}/"))

    def create(self, data: AccessCodeCreate, *, idempotency_key: str | None = None) -> AccessCode:
        """Create an access code.

        The create is sent with an `Idempotency-Key`, so the client retries it after a timeout,
        a 5xx or a 409 without creating the code twice. Each call gets a new random key unless
        you pass `idempotency_key`: 1 to 255 printable ASCII characters, without spaces.

        Pass your own stable key when your code may repeat the create, such as a job that
        re-runs, and always send it with the same data: work out time fields such as
        `expires_at` once, outside the part that re-runs, since the same instant with a
        different UTC offset is different data. For a web form, generate the key when you
        render the form and carry it in a hidden field, which also makes a double submit safe.
        The API remembers a key for 24 hours. It remembers a 400 too and replays it for that
        key, so send corrected data with a new key.

        When the create fails, the error's `idempotency_key` is the key that was sent, even one
        the client generated, so you can retry with it.

        Raises:
            BadRequestError: A field is invalid, such as a code the unit already has.
            ConflictError: A create with this key was still running after the retries; retry
                later with the same key.
            APIConnectionError: The network failed after the retries, or, as `APITimeoutError`,
                the last attempt timed out, so the create may have happened; retry with the
                same key.
            GoneError: The create with this key did happen, but the code has since been
                deleted or is out of the key's reach. Don't repeat it with this key.
            UnprocessableEntityError: This key was already used with different data.
            ValueError: `idempotency_key` isn't 1 to 255 printable ASCII characters, without
                spaces.
        """
        if idempotency_key is not None and not isinstance(idempotency_key, str):
            raise TypeError("idempotency_key must be a str.")
        key = str(uuid4()) if idempotency_key is None else idempotency_key
        if not 1 <= len(key) <= 255 or not all("!" <= char <= "~" for char in key):
            raise ValueError(
                "idempotency_key must be 1 to 255 printable ASCII characters, without spaces."
            )
        body = _body(data, AccessCodeCreate)
        try:
            response = self._client._request(
                "POST", "codes/", json=body, headers={"Idempotency-Key": key}
            )
        except YamaError as error:
            error.idempotency_key = key  # so the caller can retry it (CODE-4)
            raise
        return parse(AccessCode, response)

    def replace(self, uuid: UUID | str, data: AccessCodeCreate) -> AccessCode:
        """Replace an access code. Leaving `expires_at` unset keeps the current expiry, and
        None clears it. The API doesn't say what leaving `name` unset does, so pass the name
        the code should have."""
        body = _body(data, AccessCodeCreate)
        return parse(AccessCode, self._client._request("PUT", f"codes/{_uuid(uuid)}/", json=body))

    def update(self, uuid: UUID | str, data: AccessCodeUpdate) -> AccessCode:
        """Change the fields of an access code set in `data`; set one to None to clear it,
        such as `AccessCodeUpdate(expires_at=None)` for a code that never expires."""
        body = _body(data, AccessCodeUpdate)
        path = f"codes/{_uuid(uuid)}/"
        return parse(AccessCode, self._client._request("PATCH", path, json=body))

    def delete(self, uuid: UUID | str) -> None:
        """Delete an access code; it stops working at once.

        A 404 on a retry counts as done, since an earlier attempt may have deleted it."""
        self._client._request("DELETE", f"codes/{_uuid(uuid)}/")


class Calls(_Resource):
    """The call log (read-only)."""

    def list(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        unit: UUID | str | None = None,
        building: UUID | str | None = None,
        result: CallResult | str | None = None,
    ) -> Iterator[CallLogEntry]:
        """Every call from `start` to `end`, inclusive UTC dates, newest first, or only those
        to `unit`, through `building`'s intercom, or with `result`.

        A date left out leaves that side of the range open, so with neither you get all
        history. A call that shifts onto a later page as new calls arrive is yielded once.
        """
        params = {
            "start": _date("start", start, _EARLIEST),
            "end": _date("end", end, datetime.now(timezone.utc).date()),
            **_filters(unit=_uuid_filter(unit), building=_uuid_filter(building), result=result),
        }
        return _unique(self._client._list("calls/", CallLogEntry, params))

    def get(self, uuid: UUID | str) -> CallLogEntry:
        """One call, whatever its date. Raises `NotFoundError` if it isn't within reach."""
        return parse(CallLogEntry, self._client._request("GET", f"calls/{_uuid(uuid)}/"))


def _unique(calls: Iterator[CallLogEntry]) -> Iterator[CallLogEntry]:
    """`calls` without any whose `uuid` was already yielded (CALL-1)."""
    seen: set[UUID] = set()
    for call in calls:
        if call.uuid not in seen:
            seen.add(call.uuid)
            yield call
