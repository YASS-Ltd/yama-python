# Testing

Test your own code against `yama.testing.fake_transport()`: an in-memory Yama API that needs no network or API key. It's an `httpx.MockTransport`, so you pass it in through an `httpx.Client`:

```python
import httpx

from yama import Yama
from yama.testing import fake_transport

client = Yama(api_key="test", http_client=httpx.Client(transport=fake_transport()), max_retries=0)
for code in client.codes.list():
    print(code.code, code.name)
```

The fake behaves like the API: lists take the same filters, codes can be created, replaced, updated and deleted, bad input gets 400s in the API's format, a missing object gets a 404, a method the endpoint doesn't offer gets a 405, and a body that isn't JSON gets a 415. Creates honour idempotency keys, including the 422 for a key reused with different data and the 410 for a code deleted since. Each call to `fake_transport()` starts from its own fresh copy of the data, so tests don't affect each other.

Any API key works, except `rate-limited`, which gets a 429 with a `Retry-After` of 120 seconds on every request, so you can test your handling of `RateLimitError` without waiting.

## Turn retries off

Pass `max_retries=0` in tests, or call `client.with_options(max_retries=0)` on a client your code built. A simulated 5xx or timeout then raises at once, instead of being retried after real waits.

A pytest fixture:

```python
import httpx
import pytest

from yama import Yama
from yama.testing import fake_transport


@pytest.fixture
def yama_client():
    http = httpx.Client(transport=fake_transport())
    with Yama(api_key="test", http_client=http, max_retries=0) as client:
        yield client
```

## Seed data

Every fake starts with the same made-up data. UUIDs all start `00000000-0000-4000-8000-`, followed by the 12-digit suffix shown.

| Building | UUID suffix | Units |
|---|---|---|
| Example Tower | `000000000001` | Unit 101, Unit 102 |
| Sample Court | `000000000002` | Unit 201 |

| Unit | UUID suffix | Building | Door digit |
|---|---|---|---|
| Unit 101 | `000000000011` | Example Tower | 9 |
| Unit 102 | `000000000012` | Example Tower | 9 |
| Unit 201 | `000000000021` | Sample Court | 5 |

| Contact | UUID suffix | Unit | Number | Menu digit |
|---|---|---|---|---|
| Concierge | `000000000031` | Unit 101 | +16045550111 | 1 |
| Resident | `000000000032` | Unit 102 | +16045550122 | 1 |

| Access code UUID suffix | Unit | Code | Name | Expires |
|---|---|---|---|---|
| `000000000041` | Unit 101 | 1234 | Primary | never |
| `000000000042` | Unit 101 | 5678 | Visitor | 2099-12-31 |
| `000000000043` | Unit 201 | 2468 | none | 2020-01-01 (expired) |

| Call UUID suffix | Unit | Started (UTC) | Result |
|---|---|---|---|
| `000000000051` | Unit 101 | 2026-10-10 22:09:11 | `code_accepted` |
| `000000000052` | Unit 102 | 2026-10-09 18:30:00 | `forwarded` |
| `000000000053` | Unit 101 | 2026-10-08 07:15:42 | `code_not_accepted` |
| `000000000054` | Unit 201 | 2026-09-30 12:00:00 | `hung_up` |

The API key may write codes, read everything else, and reaches all units.

```python
from uuid import UUID

EXAMPLE_TOWER = UUID("00000000-0000-4000-8000-000000000001")
UNIT_101 = UUID("00000000-0000-4000-8000-000000000011")

assert client.units.get(UNIT_101).building == EXAMPLE_TOWER
```

## Simulating failures

To see how your code handles an error the fake doesn't produce, wrap `fake_transport()` in a transport of your own that fails some requests and passes the rest through:

```python
def failing(failure: int | type[httpx.TransportError], method: str = "") -> httpx.MockTransport:
    """The fake API, except that requests with `method` (or all) fail with a status or error."""
    fake = fake_transport()

    def handle(request: httpx.Request) -> httpx.Response:
        if method in ("", request.method):
            if isinstance(failure, int):
                return httpx.Response(failure, json={"detail": "Simulated failure."})
            raise failure("Simulated failure.", request=request)
        return fake.handle_request(request)

    return httpx.MockTransport(handle)
```

Then each failure raises its error:

```python
from yama import (
    AccessCodeCreate,
    APITimeoutError,
    AuthenticationError,
    PermissionDeniedError,
    ServerError,
)

cases = [
    (failing(401), AuthenticationError),  # bad or expired key
    (failing(403), PermissionDeniedError),  # key without permission
    (failing(503, method="POST"), ServerError),  # only creates fail
    (failing(httpx.ReadTimeout), APITimeoutError),
]
for transport, error in cases:
    client = Yama(api_key="test", http_client=httpx.Client(transport=transport), max_retries=0)
    with pytest.raises(error):
        client.codes.create(AccessCodeCreate(unit=UNIT_101, code="97531"))
```
