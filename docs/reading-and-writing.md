# Reading and writing

Your buildings, units, contacts and call log are read-only through the API. Access codes can also be created, changed and deleted.

## Reading

`get()` returns one object by its UUID, and raises `NotFoundError` if it isn't within your API key's reach. `list()` returns an iterator of every object. It requests nothing until you start iterating, then fetches more as it goes. Stop iterating, and it stops requesting.

A list shows changes made while you iterate it: deleting or changing the items you're listing can make it skip some, so finish the list before changing what's in it.

```python
from yama import Yama

client = Yama()

units = list(client.units.list())
for unit in units:
    print(unit.name, unit.door_digit)

building = client.buildings.get(units[0].building)
```

### Filters

Filters are keyword arguments with the API's names. Leave one out to not filter by it. UUIDs can be `UUID` objects or strings, and enum filters take the enum or its string value.

```python
from yama import DoorDigit

for unit in client.units.list(building=building.uuid, door_digit=DoorDigit.NINE):
    print(unit.name)

cleaners = list(client.codes.list(search="clean"))  # names containing "clean", any case
```

A UUID filter that isn't a valid UUID raises `ValueError` without sending a request. A `unit` or `building` filter your API key can't reach gives an empty list, not an error.

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

`calls.list()` takes an optional `start` and `end`, as timezone-aware datetimes. It yields the calls that started at or after `start` and before `end`, newest first. A call at exactly `end` is left out, so consecutive ranges never miss or repeat a call. A local day runs from its midnight to the next midnight, in any time zone:

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

- Calls rebuilt from the phone carrier's records, with `imported` set, can appear up to 48 hours after they started (longer after an API outage), listed by `started_at`, not by when they appeared.
- A call whose `result` is `in_progress` gets its final result when it ends.
- A call's other details can change too, so match calls by `uuid`.

## Creating

`codes.create()` takes an [`AccessCodeCreate`][yama.models.AccessCodeCreate]. Request models check fields, types and the values the schema allows as you build them: `code` is 3 to 15 digits, and `name` at most 255 characters (see [What a call raises](errors.md#what-a-call-raises)). Rules that depend on the API's data, such as a code being unique on its unit or `expires_at` being in the future, are checked by the API, which answers with `BadRequestError`.

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

`codes.update()` takes an [`AccessCodeUpdate`][yama.models.AccessCodeUpdate] and changes only the fields you set. Setting `name` or `expires_at` to `None` clears it; `code` and `unit` can't be cleared.

```python
from yama import AccessCodeUpdate

code = client.codes.update(code.uuid, AccessCodeUpdate(name="Cleaner (Mon-Fri)"))
code = client.codes.update(code.uuid, AccessCodeUpdate(expires_at=None))  # never expires
```

`codes.replace()` takes a whole `AccessCodeCreate`; leaving `name` or `expires_at` unset keeps its current value, and `None` clears it. To start from a code you fetched, copy only the fields the request model has, so this keeps working when the API adds fields to its responses:

```python
fields = code.model_dump(include=set(AccessCodeCreate.model_fields))
code = client.codes.replace(code.uuid, AccessCodeCreate(**(fields | {"code": "8642"})))
```

## Deleting

`codes.delete()` deletes a code, and it stops working at once:

```python
client.codes.delete(code.uuid)
```
