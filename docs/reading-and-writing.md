# Reading and writing

Your buildings, units, contacts and call log are read-only through the API. Access codes can also be created, changed and deleted.

## Reading

`get()` returns one object by its UUID, and raises `NotFoundError` if it isn't within your key's reach. `list()` returns an iterator of every object. It requests nothing until you start iterating, then fetches more as it goes. Stop iterating, and it stops requesting.

```python
from yama import Yama

client = Yama()

for unit in client.units.list():
    print(unit.name, unit.door_digit)

first_building = next(client.buildings.list())
building = client.buildings.get(first_building.uuid)
```

### Filters

Filters are keyword arguments with the API's names. Leave one out to not filter by it. UUIDs can be `UUID` objects or strings, and enum filters take the enum or its string value.

```python
from yama import DoorDigit

for unit in client.units.list(building=building.uuid, door_digit=DoorDigit.NINE):
    print(unit.name)

cleaners = list(client.codes.list(search="clean"))  # names containing "clean", any case
```

A UUID filter that isn't a valid UUID raises `ValueError` without sending a request.

### What you get back

Every response is a frozen [Pydantic](https://docs.pydantic.dev/) model with the API's field names: UUIDs are `UUID`, and every time is a timezone-aware `datetime` in UTC.

```python
code = next(client.codes.list())
print(code.uuid, code.unit, code.code, code.name, code.expires_at)
print(code.model_dump(mode="json"))  # a dict, ready for JSON
```

The API adds fields and enum values over time without a new version, and the client is ready for them:

- A field the client doesn't know yet is still there: read it as an attribute, or from `code.model_extra`.
- An enum value the client doesn't know yet comes back as a plain string. Compare with `==`, which works for both: `call.result == CallResult.REJECTED`. Enum members format as their value, so `str()` and f-strings give `"rejected"` either way.

## The call log

`calls.list()` takes an optional `start` and `end`, as timezone-aware datetimes, and yields the calls that started at or after `start` and before `end`, newest first. Because a call at exactly `end` is left out, one range can end where the next begins without missing or repeating a call, so a local day runs from its midnight to the next midnight, in any time zone:

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from yama import CallResult

vancouver = ZoneInfo("America/Vancouver")
day = datetime(2026, 10, 10, tzinfo=vancouver)
for call in client.calls.list(start=day, end=day + timedelta(days=1)):
    print(call.started_at.astimezone(vancouver), call.result, call.summary)

rejected = list(client.calls.list(start=day, result=CallResult.REJECTED))
```

- A `date`, or a datetime without a time zone, raises before any request is sent.
- Leave out `start` or `end` to leave that side open; with neither, you get all history.
- With a `start`, polling for recent calls is cheap.
- Each call comes once, even when new calls arrive while you iterate.

If you keep your own copy of the call log, it changes after the fact:

- Calls rebuilt from the phone carrier's records, with `imported` set, can appear up to 48 hours after they started, in their `started_at` place, and later than that after an API outage.
- A call whose `result` is `in_progress` gets its final result when it ends.
- A call's other details can change too, so match calls by `uuid`.

## Creating

`codes.create()` takes an [`AccessCodeCreate`][yama.models.AccessCodeCreate]. Building it, or the `AccessCodeUpdate` below, raises `pydantic.ValidationError`, before anything is sent, for an unknown field or a datetime without a time zone. Rules about values, such as how many digits a code has, are left to the API.

```python
from datetime import datetime, timezone

from yama import AccessCodeCreate

unit = next(client.units.list())
expires = datetime(2027, 1, 1, tzinfo=timezone.utc)
code = client.codes.create(
    AccessCodeCreate(unit=unit.uuid, code="4321", name="Cleaner", expires_at=expires)
)
```

A create is safe to repeat with the same idempotency key; see [Creates that are safe to repeat](errors.md#creates-that-are-safe-to-repeat).

## Changing

`codes.update()` takes an [`AccessCodeUpdate`][yama.models.AccessCodeUpdate] and changes only the fields you set, so setting one to `None` clears it:

```python
from yama import AccessCodeUpdate

code = client.codes.update(code.uuid, AccessCodeUpdate(expires_at=None))  # never expires
```

`codes.replace()` takes a whole `AccessCodeCreate`. To replace a code with a changed copy of itself, build one from the fetched code with only the fields `AccessCodeCreate` takes. Listing them with `include` keeps this working when the API adds fields to responses, which the request model would reject:

```python
fields = code.model_dump(include=set(AccessCodeCreate.model_fields))
client.codes.replace(code.uuid, AccessCodeCreate(**{**fields, "name": "Cleaner (Mon-Fri)"}))
```

## Deleting

`codes.delete()` deletes a code, and it stops working at once:

```python
client.codes.delete(code.uuid)
```
