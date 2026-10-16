# Web apps and background jobs

## One client per process

A `Yama` client holds a pool of connections and is safe to share between threads, so create one per process and reuse it. Create it on first use, never at import time: Celery's prefork workers and gunicorn with `--preload` fork after importing your code, and a client created before the fork would share its connections between processes. A cached factory does this:

```python
from functools import cache

from yama import Yama


@cache
def yama_client() -> Yama:
    """The process's client, created on first use."""
    return Yama()
```

Call `yama_client()` inside views and tasks, which run after the fork, and not at module level or in a server hook that runs before it.

## Short timeouts in web requests

The defaults suit background work: 30 seconds per phase of an attempt and 2 retries. A web request usually can't wait that long, so in views use a copy that fails fast. `with_options()` is cheap, and the copy shares the process's connections:

```python
def view_client() -> Yama:
    return yama_client().with_options(timeout=5.0, max_retries=0)


units = list(view_client().units.list())
```

## Async code

The client is synchronous for now: each call blocks until it has an answer, and `http_client` must be an `httpx.Client`, not an `httpx.AsyncClient`. Async support is planned for a later release. Until then, run calls in a worker thread so they don't block the event loop. The client is safe to share between threads, so one client still serves the whole process.

`asyncio.to_thread()` runs a call in a thread and awaits the result. Lists are fetched lazily as you iterate, so collect them inside the thread with `list()`, or the pages are fetched on the event loop:

```python
import asyncio

from yama import Yama

client = Yama()


async def unit_names() -> list[str]:
    units = await asyncio.to_thread(lambda: list(client.units.list()))
    return [unit.name for unit in units]


async def dashboard() -> None:
    names, codes = await asyncio.gather(
        unit_names(),
        asyncio.to_thread(lambda: list(client.codes.list())),
    )
    print(f"{len(names)} units, {len(codes)} codes")


asyncio.run(dashboard())
```

Cancelling the awaiting task doesn't stop a call already running in its thread: it carries on, within its timeout and retries, and its result is dropped. That matters for a create, which may still happen. Pass an `idempotency_key` you can repeat (see [Creates that are safe to repeat](errors.md#creates-that-are-safe-to-repeat)).

## Creates in jobs that may re-run

A job queue may run a task twice: a retry after a timeout, a worker that died part-way, or at-least-once delivery. Give such a create a stable `idempotency_key`, derived from your own record, so a repeat within 24 hours returns the code made the first time instead of making a second one (see [Creates that are safe to repeat](errors.md#creates-that-are-safe-to-repeat)):

- **Send the same data with the same key.** Work out anything that changes from run to run, such as an `expires_at` computed from the current time, once, outside the part that re-runs, and pass it in.
- **After a `BadRequestError`, use a new key.** The API replays a 400 for the key that got it, for 24 hours, so a corrected create needs a key of its own.

With Celery, compute `expires_at` when you enqueue the task, and pass it as a string so it serialises as JSON:

<!-- not run -->

```python
from datetime import datetime, timedelta, timezone

from celery import shared_task

from myapp.clients import yama_client
from yama import AccessCodeCreate, APIConnectionError, ConflictError, ServerError


@shared_task(bind=True, max_retries=5)
def create_guest_code(self, booking_id: int, unit: str, code: str, expires_at: str) -> str:
    data = AccessCodeCreate(unit=unit, code=code, name="Guest", expires_at=expires_at)
    try:
        created = yama_client().codes.create(data, idempotency_key=f"booking-{booking_id}")
    except (APIConnectionError, ConflictError, ServerError) as error:
        raise self.retry(exc=error, countdown=60)  # same key and data next time
    return str(created.uuid)


expires_at = datetime.now(timezone.utc) + timedelta(days=7)  # once, before enqueueing
create_guest_code.delay(booking.id, str(unit.uuid), "4821", expires_at.isoformat())
```

If you let the client generate the key instead, read it from the error inside the task, as `error.idempotency_key`, and pass it on to the retry. Don't rely on it outside the task: Celery's JSON result backend rebuilds an exception from its arguments only, so the attribute is gone by the time a caller looks at the task's result.

## Creates from web forms

A form can be submitted twice, by a double click or a retried request. Generate a key when you render the form and carry it in a hidden field, so a second submit of the same form returns the same code. When the API answers 400, show the form again with a new key, since the corrected submit is different data. In Django, a bound form re-renders the posted value, so replace it:

<!-- not run -->

```python
import uuid

from django import forms
from django.shortcuts import redirect, render

from myapp.clients import yama_client
from yama import AccessCodeCreate, BadRequestError


class CodeForm(forms.Form):
    code = forms.CharField()
    name = forms.CharField(required=False)
    idempotency_key = forms.CharField(widget=forms.HiddenInput)


def new_code(request, unit):
    if request.method != "POST":
        form = CodeForm(initial={"idempotency_key": str(uuid.uuid4())})
        return render(request, "new_code.html", {"form": form})
    form = CodeForm(request.POST)
    if form.is_valid():
        data = AccessCodeCreate(
            unit=unit, code=form.cleaned_data["code"], name=form.cleaned_data["name"] or None
        )
        key = form.cleaned_data["idempotency_key"]
        try:
            yama_client().with_options(timeout=5.0).codes.create(data, idempotency_key=key)
            return redirect("codes")
        except BadRequestError as error:
            for field, messages in error.errors.items():
                form.add_error(field if field in form.fields else None, messages)
            form.data = form.data.copy()
            form.data["idempotency_key"] = str(uuid.uuid4())  # corrected data, new key
    return render(request, "new_code.html", {"form": form})
```

## Syncing the call log

To keep your own copy of the call log, sync it on a schedule with overlapping ranges:

- **Start each sync at least 48 hours before the last one ended.** Some calls are added to the log afterwards, rebuilt from the phone carrier's records (these have `imported` set). They appear in their `started_at` place, which a sync starting where the last one ended has already passed.
- **Upsert by `uuid`.** Overlapping ranges return calls you already have, and a call's details can change.
- **Fetch in-progress calls again later.** A call whose `result` is `in_progress` gets its final result when it ends; `calls.get(uuid)` returns it.
- **Re-sync a wider range after a long API outage.** Calls from during the outage can be rebuilt later than usual, so once the API is back, run one sync starting 48 hours before the outage began.
- **Use timezone-aware datetimes.** Ranges are half-open, `start <= started_at < end`, so take `end` once per sync and save it as the next sync's reference point.

```python
from datetime import datetime, timedelta, timezone
from uuid import UUID

from yama import CallLogEntry, CallResult

OVERLAP = timedelta(hours=48)
calls: dict[UUID, CallLogEntry] = {}  # your database table, keyed by uuid


def sync_calls(last_end: datetime) -> datetime:
    """Sync from 48 hours before `last_end` to now, and return the new end to save."""
    client = yama_client()
    end = datetime.now(timezone.utc)
    for call in client.calls.list(start=last_end - OVERLAP, end=end):
        calls[call.uuid] = call  # upsert
    for uuid, call in list(calls.items()):
        if call.result == CallResult.IN_PROGRESS:
            calls[uuid] = client.calls.get(uuid)
    return end


last_end = sync_calls(datetime(2026, 10, 9, tzinfo=timezone.utc))
```
