# Configuration

## The API key

Create an API key in the Yama portal under **Settings › API keys**. `Yama()` reads it from the `YAMA_API_KEY` environment variable:

```python
from yama import Yama

client = Yama()  # reads YAMA_API_KEY
```

Or pass it from wherever you keep secrets, as `Yama(api_key=...)`. A key passed as `None` or `""`, or a missing `YAMA_API_KEY`, raises `YamaError` straight away. The key never appears in a `repr`, log record or error message.

A good first call is the key's own record, which says what the key may do:

```python
key_details = client.api_key.get()
print(key_details.name, key_details.expires_at)
print(key_details.permissions.codes)  # none, read or write
print(key_details.unit_access.type)  # all, buildings or units
```

## Client options

`Yama()` takes these arguments, all optional:

| Argument | Default | Meaning |
|---|---|---|
| `api_key` | `YAMA_API_KEY` | The API key. |
| `base_url` | `YAMA_API_BASE_URL`, else [`DEFAULT_BASE_URL`][yama.DEFAULT_BASE_URL] | Where requests go. It must use `https://`; plain `http://` is accepted only for `localhost`, `127.0.0.1` or `[::1]`, such as a local development server, and then proxies set in the environment aren't used, so your API key isn't sent unencrypted over a network. If you pass your own `http_client`, its proxy settings are yours. |
| `timeout` | `30.0` | Seconds allowed for each phase of an attempt: connecting, writing, reading, and waiting for a pooled connection. Pass an `httpx.Timeout` to set the phases one by one, or `httpx.Timeout(None)` for no limit. |
| `max_retries` | `2` | Retries after a 429, a 5xx or a network error. See [Errors and retries](errors.md). |
| `http_client` | a new `httpx.Client` | Your own client to send through. It must be an `httpx.Client`: the client isn't async yet (see [Async code](web-apps-and-jobs.md#async-code)). |

```python
import httpx

from yama import Yama

client = Yama(timeout=httpx.Timeout(10.0, connect=3.0), max_retries=4)
```

## A copy with other settings

`with_options()` returns a copy with a different `timeout` or `max_retries` that shares the original's connections, API key and base URL. It's cheap, so use it where one call site needs different settings, such as a web view that should fail fast:

```python
fast = client.with_options(timeout=5.0, max_retries=0)
building = next(fast.buildings.list())
```

Closing the copy leaves the connections open; closing the original closes them for both.

## Your own httpx client

Pass an `httpx.Client` to configure the transport yourself: a proxy, a custom CA bundle, or event hooks. The client applies its own URL, timeout and headers to each request, and leaves closing your `httpx.Client` to you. Your client's `auth` isn't used for API requests: they always carry your API key.

Leave raising for status to the client. If a response hook calls `raise_for_status()`, you still get the matching error, such as `NotFoundError`, but httpx closes the response before its body is read, so the error has no `detail` from the API or field errors.

```python
import httpx

from yama import Yama

with httpx.Client(proxy="http://proxy.example:3128") as http:
    client = Yama(http_client=http)
```

## Closing

A client holds a connection pool. Use it as a context manager, or call `close()` when you're done; using it afterwards raises `ValueError`. One client is safe to share between threads, so most programs need only one. See [Web apps and background jobs](web-apps-and-jobs.md).

```python
with Yama() as client:
    for building in client.buildings.list():
        print(building.name)
```
