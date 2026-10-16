# Web apps and background jobs

## One client per process

A `Yama` client holds a pool of connections and is safe to share between threads, so create one per process and reuse it. Create it on first use, never at import time: Celery's prefork workers and gunicorn with `--preload` fork after importing your code, and a client created before the fork would share its connections between processes. One way is a cached factory:

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


building = next(view_client().buildings.list())
```

## Async code

The client is synchronous for now: each call blocks until it has an answer, and `http_client` must be an `httpx.Client`, not an `httpx.AsyncClient`. Async support is planned for a later release. Until then, run calls in a worker thread so they don't block the event loop. The client is safe to share between threads, so one client still serves the whole process.

Lists make their requests as you iterate, so iterate them inside the worker thread too, or the requests run on the event loop:

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
