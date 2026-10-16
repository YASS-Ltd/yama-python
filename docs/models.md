# Models

## What you get back

Every response is a frozen [Pydantic](https://docs.pydantic.dev/) model with the API's field names: UUIDs are `UUID`, and every time is a timezone-aware `datetime` in UTC.

```python
from yama import Yama

client = Yama()
code = next(client.codes.list())
print(code.uuid, code.unit, code.code, code.name, code.expires_at)
print(code.model_dump(mode="json"))  # a dict, ready for JSON
```

The API adds fields and enum values over time without a new version, and the client is ready for them:

- A field the client doesn't know yet is still there: read it as an attribute, or from `code.model_extra`.
- An enum value the client doesn't know yet comes back as a plain string. Compare with `==`, which works for both: `call.result == CallResult.REJECTED`. Enum members format as their value, so `str()` and f-strings give `"rejected"` either way.

## What you send

Creates and changes take request models: [`AccessCodeCreate`][yama.models.AccessCodeCreate] for `codes.create()` and `codes.replace()`, and [`AccessCodeUpdate`][yama.models.AccessCodeUpdate] for `codes.update()`. They reject unknown fields and datetimes without a time zone when you build them, before anything is sent, with `pydantic.ValidationError`. Rules about values, such as how many digits a code has, are left to the API.

```python
from datetime import datetime, timezone

from yama import AccessCodeCreate, AccessCodeUpdate

unit = next(client.units.list())
expires = datetime(2027, 1, 1, tzinfo=timezone.utc)
code = client.codes.create(
    AccessCodeCreate(unit=unit.uuid, code="4321", name="Cleaner", expires_at=expires)
)
```

`AccessCodeUpdate` sends only the fields you set, so setting one to `None` clears it:

```python
code = client.codes.update(code.uuid, AccessCodeUpdate(expires_at=None))  # never expires
```

## From a fetched code to a request

To replace a code with a changed copy of itself, turn it back into an `AccessCodeCreate` with only the fields that model takes. Listing them with `include` keeps this working when the API adds fields to responses, which the request model would reject:

```python
fields = code.model_dump(include=set(AccessCodeCreate.model_fields))
client.codes.replace(code.uuid, AccessCodeCreate(**{**fields, "name": "Cleaner (Mon-Fri)"}))
```
