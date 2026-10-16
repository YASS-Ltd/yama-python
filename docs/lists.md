# Lists and the call log

## Lists

Every `list()` method returns an iterator of items. It requests nothing until you start iterating, then fetches more as it goes. Stop iterating, and it stops requesting.

```python
from yama import Yama

client = Yama()

for unit in client.units.list():
    print(unit.name, unit.door_digit)

first_building = next(client.buildings.list())
```

## Filters

Filters are keyword arguments with the API's names. Leave one out to not filter by it. UUIDs can be `UUID` objects or strings, and enum filters take the enum or its string value.

```python
from yama import DoorDigit

building = next(client.buildings.list())
for unit in client.units.list(building=building.uuid, door_digit=DoorDigit.NINE):
    print(unit.name)

cleaners = list(client.codes.list(search="clean"))  # names containing "clean", any case
```

A UUID filter that isn't a valid UUID raises `ValueError` without sending a request.

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
