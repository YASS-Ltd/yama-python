# Interface Spec: yama-python v0.1

The public names and signatures of the client, so everyone building it uses the same ones. Behaviour is specified once, as requirements in `design/prd-v0.1.md` (IDs such as RTY-2 below point there). Fields, filters and statuses come from the vendored schema (`tests/fixtures/openapi.yaml`). Change this doc in the same PR as any code that departs from it.

Anything not listed here is private. The whole package should stay a few hundred lines.

## Layout

```
src/yama/
  __init__.py      # re-exports everything public below, plus __version__
  _client.py       # Yama, DEFAULT_BASE_URL
  _pagination.py   # Paginator
  _resources.py    # one small class per resource
  _errors.py       # exception classes
  models.py        # Pydantic models and enums (public module)
```

## Quick Look

```python
from datetime import date
from yama import Yama, AccessCodeCreate, AccessCodeUpdate

with Yama() as client:  # api_key from YAMA_API_KEY
    key = client.api_key.get()  # first call: what can this key do?

    for unit in client.units.list(building=building_uuid):
        ...

    code = client.codes.create(AccessCodeCreate(unit=unit.uuid, code="4321", name="Cleaner"))
    client.codes.update(code.uuid, AccessCodeUpdate(expires_at=None))  # clear the expiry
    client.codes.delete(code.uuid)

    for call in client.calls.list(start=date(2026, 10, 1), end=date(2026, 10, 31)):
        ...
```

## Client

```python
Yama(
    api_key: str | None = None,
    *,
    base_url: str | None = None,
    timeout: float = 30.0,
    max_retries: int = 2,
    http_client: httpx.Client | None = None,
)
```

- `DEFAULT_BASE_URL` is the only place in the code that names Yama's domain (CFG-3).
- `Yama` is a context manager and has `close()`.
- Resource attributes: `api_key`, `buildings`, `units`, `contacts`, `codes`, `calls`. The key string is private (`_key`).
- Logs go to `logging.getLogger("yama")`; `yama/__init__.py` adds a `NullHandler` to it (LOG-1 to LOG-3).
- Waits between retries go through `Yama._sleep` (default `time.sleep`), so tests replace it instead of sleeping.

## Resources

Paths are relative to `/api/v2/`. `uuid` parameters accept `UUID | str`. Filters are keyword-only and default to `None`.

| Call | HTTP | Returns |
|---|---|---|
| `api_key.get()` | `GET api-key/` | `ApiKey` |
| `buildings.list()` | `GET buildings/` | `Paginator[Building]` |
| `buildings.get(uuid)` | `GET buildings/{uuid}/` | `Building` |
| `units.list(*, building, door_digit, search)` | `GET units/` | `Paginator[Unit]` |
| `units.get(uuid)` | `GET units/{uuid}/` | `Unit` |
| `contacts.list(*, unit, number, menu_digit)` | `GET contacts/` | `Paginator[Contact]` |
| `contacts.get(uuid)` | `GET contacts/{uuid}/` | `Contact` |
| `codes.list(*, unit, code, name, search)` | `GET codes/` | `Paginator[AccessCode]` |
| `codes.get(uuid)` | `GET codes/{uuid}/` | `AccessCode` |
| `codes.create(data: AccessCodeCreate, *, idempotency_key: str \| None)` | `POST codes/` | `AccessCode` |
| `codes.replace(uuid, data: AccessCodeCreate)` | `PUT codes/{uuid}/` | `AccessCode` |
| `codes.update(uuid, data: AccessCodeUpdate)` | `PATCH codes/{uuid}/` | `AccessCode` |
| `codes.delete(uuid)` | `DELETE codes/{uuid}/` | `None` |
| `calls.list(*, start: date \| None, end: date \| None, unit, building, result)` | `GET calls/` | `Paginator[CallLogEntry]` |
| `calls.get(uuid)` | `GET calls/{uuid}/` | `CallLogEntry` |

Lists take no `limit` or `offset`: the paginator requests pages itself and follows `next` (PAG-1).

## Pagination

```python
class Paginator(Generic[T]):        # returned by every list()
    def __iter__(self) -> Iterator[T]
```

Iterating yields items, never pages (PAG-1). Pages are parsed with a private `_Page` model and never exposed.

## Models (`yama.models`)

- **Responses**, mirroring the schema's components field for field: `ApiKey` (with `ApiKeyPermissions`, `ApiKeyUnitAccess`), `Building`, `Unit`, `Contact`, `AccessCode`, `CallLogEntry`, `CallLogStep`. Frozen, with `extra="allow"` (MOD-2).
- **Requests:** `AccessCodeCreate` (`unit: UUID`, `code: str`, `name: str | None = None`, `expires_at: AwareDatetime | None = None`) and `AccessCodeUpdate` (the same fields, all optional). `extra="forbid"` (MOD-4).
- **Enums**, as `str` enums: `CallResult`, `CallStepKind`, `CodeAttemptResult`, `DialStatus`, `DoorDigit`, `AccessLevel` (`none`/`read`/`write`) and `UnitAccessType`. Response fields are typed `Enum | str` with left-to-right union mode (MOD-3).
- **Known schema bug:** `ApiKey.expires_at` and `last_used_at` are `datetime | None`, although the schema marks them non-nullable; the API really returns `null`. A fix is filed upstream. Until it lands, the contract tests allow this one difference.

## Errors

```
YamaError                       # base; also raised for misconfiguration (CFG-2)
├── APIConnectionError          # network failure or timeout, after retries
└── APIStatusError              # any other non-2xx: status_code, detail, body, api_version
    ├── BadRequestError         # 400; .errors: dict[str, list[str]]
    ├── AuthenticationError     # 401
    ├── PermissionDeniedError   # 403
    ├── NotFoundError           # 404
    ├── RateLimitError          # 429; .retry_after: int | None (seconds)
    └── ServerError             # 5xx
```

An error's message is `"<status> <detail>"`.

## Implementation Defaults

Choices that aren't requirements, recorded so they're consistent: every list requests the API's maximum page size (`limit=500`), for the fewest requests under the rate limit. An open `start` is sent as `2000-01-01` (CALL-2); the live tests confirm the API accepts it. Backoff starts at 0.5 s, doubles, is capped at 8 s, with full jitter. Async isn't in v0.1; keeping request building separate from sending should make an `AsyncYama` a small addition later.
