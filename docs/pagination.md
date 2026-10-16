# Lists and the call log

## Lists

Every `list()` method returns an iterator of items. It requests nothing until you start iterating, then fetches more as it goes. Stop iterating, and it stops requesting.

```python
from yama import Yama

client = Yama()

for unit in client.units.list():
    print(unit.name, unit.door_digit)

first_building = next(client.buildings.list())  # fetches one page only
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

`calls.list()` takes a range of timezone-aware datetimes: it yields calls with `start <= started_at < end`, newest first. The range is half-open, so back-to-back ranges never miss or repeat a call, and one local day runs from its midnight to the next, in any time zone:

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

To keep your own copy of the call log up to date, follow the [call-log sync recipe](production.md#syncing-the-call-log).
