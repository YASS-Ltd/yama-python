# Interface Spec: yama-python v0.1

The public interface of the client, so everyone building it uses the same names. The vendored schema (`tests/fixtures/openapi.yaml`) is the source of truth for fields, filters and statuses; this doc settles what the schema can't: names, shapes and behaviour. Change it in the same PR as any code that departs from it.

Anything not listed here is private. Keep it lightweight: the whole package should stay a few hundred lines.

## Layout

```
src/yama/
  __init__.py      # re-exports everything public below, plus __version__
  _client.py       # Yama: config, auth, request, retries
  _pagination.py   # Paginator, Page
  _resources.py    # one small class per resource
  _errors.py       # exception classes
  models.py        # Pydantic models and enums (public module)
```

## Quick Look

```python
from datetime import date, datetime, timezone
from yama import Yama, AccessCodeCreate, AccessCodeUpdate, NotFoundError

with Yama() as client:                       # api_key from YAMA_API_KEY
    key = client.api_key.get()               # first call: what can this key do?

    for unit in client.units.list(building=building_uuid):
        ...

    code = client.codes.create(AccessCodeCreate(unit=unit.uuid, code="4321", name="Cleaner"))
    client.codes.update(code.uuid, AccessCodeUpdate(expires_at=None))   # clear the expiry
    client.codes.delete(code.uuid)

    for call in client.calls.list(start=date(2026, 10, 1), end=date(2026, 10, 31)):
        ...
```

## Client

```python
Yama(
    api_key: str | None = None,          # falls back to YAMA_API_KEY
    *,
    base_url: str | None = None,         # falls back to YAMA_API_BASE_URL, then DEFAULT_BASE_URL
    timeout: float = 30.0,               # seconds, per request
    max_retries: int = 2,                # retries after the first attempt
    http_client: httpx.Client | None = None,  # for tests and custom transports
)
```

- No key from either source raises `YamaError` at construction.
- `DEFAULT_BASE_URL` (in `_client.py`, currently `https://app.getyama.ca`) is the only place in the code that names Yama's domain.
- `Yama` is a context manager and has `close()`. It closes the `httpx.Client` only if it created it.
- Attributes: `api_key`, `buildings`, `units`, `contacts`, `codes`, `calls` (resources, below). The key string itself is private (`_key`) and appears in no `repr`, log line, exception or URL.
- Every request sends `Authorization: Bearer <key>`, `Accept: application/json` and `User-Agent: yama-python/<version> python/<major.minor>`.

## Resources

Paths are relative to `/api/v2/`. `uuid` parameters accept `UUID | str`. Filters are keyword-only and are sent only when not `None`, so a call never sends a parameter the caller didn't set.

| Call | HTTP | Returns |
|---|---|---|
| `api_key.get()` | `GET api-key/` | `ApiKey` |
| `buildings.list(*, page_size)` | `GET buildings/` | `Paginator[Building]` |
| `buildings.get(uuid)` | `GET buildings/{uuid}/` | `Building` |
| `units.list(*, building, door_digit, search, page_size)` | `GET units/` | `Paginator[Unit]` |
| `units.get(uuid)` | `GET units/{uuid}/` | `Unit` |
| `contacts.list(*, unit, number, menu_digit, page_size)` | `GET contacts/` | `Paginator[Contact]` |
| `contacts.get(uuid)` | `GET contacts/{uuid}/` | `Contact` |
| `codes.list(*, unit, code, name, search, page_size)` | `GET codes/` | `Paginator[AccessCode]` |
| `codes.get(uuid)` | `GET codes/{uuid}/` | `AccessCode` |
| `codes.create(data: AccessCodeCreate)` | `POST codes/` | `AccessCode` |
| `codes.replace(uuid, data: AccessCodeCreate)` | `PUT codes/{uuid}/` | `AccessCode` |
| `codes.update(uuid, data: AccessCodeUpdate)` | `PATCH codes/{uuid}/` | `AccessCode` |
| `codes.delete(uuid)` | `DELETE codes/{uuid}/` | `None` |
| `calls.list(*, start, end, unit, building, result, page_size)` | `GET calls/` | `Paginator[CallLogEntry]` |
| `calls.get(uuid)` | `GET calls/{uuid}/` | `CallLogEntry` |

- `page_size: int | None` is sent as `limit` (1-500; the API defaults to 100). There is no `offset` argument: the paginator follows `next`.
- `calls.list`: `start` and `end` are `datetime.date`s, sent as ISO dates, and go together: passing only one raises `ValueError` before any request. Without them the API returns the last 30 days. The paginator skips any call whose `uuid` it has already yielded, because new calls shift pages while you read.
- `codes.update` sends only the fields set on the model (`model_dump(exclude_unset=True)`), so `AccessCodeUpdate(expires_at=None)` clears the expiry and `AccessCodeUpdate(name="Cleaner")` leaves it alone.

## Pagination

```python
class Paginator(Generic[T]):        # returned by every list()
    def __iter__(self) -> Iterator[T]        # every item, lazily, following `next`
    def pages(self) -> Iterator[Page[T]]     # page by page

class Page(BaseModel, Generic[T]):
    count: int
    next: str | None
    previous: str | None
    results: list[T]
```

Nothing is requested until iteration starts. Each `next` URL is requested as given, never rebuilt. Iterating twice makes the requests twice.

## Models (`yama.models`)

Response models mirror the schema's components field for field: `ApiKey` (with `ApiKeyPermissions`, `ApiKeyUnitAccess`), `Building`, `Unit`, `Contact`, `AccessCode`, `CallLogEntry`, `CallLogStep`.

- **Responses** are frozen and keep unknown fields (`ConfigDict(extra="allow", frozen=True)`), so a field added within v2 is readable before the client knows about it.
- **Requests** forbid unknown fields (`extra="forbid"`), catching typos before the API's 400 would. `AccessCodeCreate`: `unit: UUID`, `code: str`, `name: str | None = None`, `expires_at: AwareDatetime | None = None`. `AccessCodeUpdate`: the same fields, all optional.
- **Types:** `uuid` fields are `UUID`, datetimes are timezone-aware `datetime`s, and the dates the client sends are `date`s.
- **Enums** are `str` enums, so members equal their string values: `CallResult`, `CallStepKind`, `CodeAttemptResult`, `DialStatus`, `DoorDigit`, `AccessLevel` (`none`/`read`/`write`) and `UnitAccessType`. Response fields are typed `Enum | str` with left-to-right union mode, so a value the client doesn't know arrives as a plain `str` rather than an error.

## Errors

```
YamaError                       # base; also raised for client misconfiguration
├── APIConnectionError          # network failure or timeout, after retries
└── APIStatusError              # any non-2xx response
    ├── BadRequestError         # 400; .errors: dict[str, list[str]]
    ├── AuthenticationError     # 401: bad, expired or missing key
    ├── PermissionDeniedError   # 403: the key lacks the permission
    ├── NotFoundError           # 404
    ├── RateLimitError          # 429; .retry_after: int | None (seconds)
    └── ServerError             # 5xx
```

`APIStatusError` carries `status_code`, `detail` (the body's `detail` string, if any), `body` (parsed JSON, or text) and `api_version` (the `API-Version` header). Its message is `"<status> <detail>"`, and never includes the key or request headers. Other statuses (405, 415) raise `APIStatusError` itself.

## Retries

- Retried: 429, 5xx, and `httpx.TransportError`, up to `max_retries` times.
- Wait: a 429's `Retry-After` when present. Otherwise exponential backoff with jitter, starting at 0.5 s and capped at 8 s. A `Retry-After` over 60 s isn't waited out: the client raises `RateLimitError` straight away.
- `POST` (creating a code) is retried only on 429 and on connection errors raised before the request was sent (`httpx.ConnectError`, `httpx.ConnectTimeout`). After a 5xx or a read timeout the code may or may not exist, and retrying could create it twice, so the client raises instead, and the error's message says the code may have been created. Once the API accepts an idempotency key, the client will send one with every create and retry it like any other request.
- Waiting goes through `Yama._sleep` (default `time.sleep`), so tests replace it rather than sleep.

## Out of Scope for v0.1

Async (the split between building a request and sending it should make `AsyncYama` a small addition later), a CLI, logging hooks, and anything the API doesn't expose.
