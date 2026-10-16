# Interface Spec: yama-python v0.1

The public names and signatures of the client, so everyone building it uses the same ones. Behaviour is specified once, as requirements in `design/prd-v0.1.md` (IDs such as RTY-2 below point there). Fields, filters and statuses come from the vendored schema (`tests/fixtures/openapi.yaml`). Change this doc in the same PR as any code that departs from it.

Anything not listed here is private. The whole package should stay a few hundred lines.

## Layout

```
src/yama/
  __init__.py      # re-exports everything public below, plus __version__
  _client.py       # Yama, DEFAULT_BASE_URL
  _pagination.py   # the paging generator (private)
  _resources.py    # one small class per resource
  _errors.py       # exception classes
  models.py        # Pydantic models and enums (public module)
  testing.py       # fake_transport() (public module)
```

## Quick Look

```python
from datetime import datetime, timezone
from yama import Yama, AccessCodeCreate, AccessCodeUpdate

with Yama() as client:  # api_key from YAMA_API_KEY
    key_details = client.api_key.get()  # first call: what can this key do?

    for unit in client.units.list(building=building_uuid):
        ...

    code = client.codes.create(AccessCodeCreate(unit=unit.uuid, code="4321", name="Cleaner"))
    client.codes.update(code.uuid, AccessCodeUpdate(expires_at=None))  # clear the expiry
    client.codes.delete(code.uuid)

    start, end = (
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    for call in client.calls.list(start=start, end=end):  # start <= started_at < end
        ...
```

## Client

```python
Yama(
    api_key: str | None = <omitted>,   # private sentinel: only an omitted key falls back to YAMA_API_KEY (CFG-1)
    *,
    base_url: str | None = None,
    timeout: float | httpx.Timeout = 30.0,
    max_retries: int = 2,
    http_client: httpx.Client | None = None,
)
```

- `DEFAULT_BASE_URL` is the only place in the code that names Yama's domain (CFG-3).
- `Yama` is a context manager and has `close()`; using it after `close()` raises `ValueError` (ERR-4).
- The key is stripped of surrounding whitespace, and must then be printable ASCII without spaces, or `Yama()` raises `ValueError` (SEC-1).
- Resource attributes: `api_key`, `buildings`, `units`, `contacts`, `codes`, `calls`. The key string is private (`_key`).
- `with_options(*, timeout=<unchanged>, max_retries=<unchanged>) -> Yama` returns a copy with those settings that shares the original's connection pool, key, base URL and `http_client` (CFG-6), so one call site, such as a web view, can fail fast while background jobs keep the defaults. Closing the copy leaves the pool open; closing the original closes it for both.
- Logs go to `logging.getLogger("yama")`; `yama/__init__.py` adds a `NullHandler` to it (LOG-1 to LOG-3).
- Waits between retries go through `Yama._sleep` (default `time.sleep`), so tests replace it instead of sleeping.

## Resources

Paths are relative to `/api/v2/`. `uuid` parameters accept `UUID | str`. Filters are keyword-only and default to `None`.

| Call | HTTP | Returns |
|---|---|---|
| `api_key.get()` | `GET api-key/` | `ApiKeyDetails` |
| `buildings.list()` | `GET buildings/` | `Iterator[Building]` |
| `buildings.get(uuid)` | `GET buildings/{uuid}/` | `Building` |
| `units.list(*, building, door_digit, search)` | `GET units/` | `Iterator[Unit]` |
| `units.get(uuid)` | `GET units/{uuid}/` | `Unit` |
| `contacts.list(*, unit, number, menu_digit)` | `GET contacts/` | `Iterator[Contact]` |
| `contacts.get(uuid)` | `GET contacts/{uuid}/` | `Contact` |
| `codes.list(*, unit, code, name, search)` | `GET codes/` | `Iterator[AccessCode]` |
| `codes.get(uuid)` | `GET codes/{uuid}/` | `AccessCode` |
| `codes.create(data: AccessCodeCreate, *, idempotency_key: str \| None)` | `POST codes/` | `AccessCode` |
| `codes.replace(uuid, data: AccessCodeCreate)` | `PUT codes/{uuid}/` | `AccessCode` |
| `codes.update(uuid, data: AccessCodeUpdate)` | `PATCH codes/{uuid}/` | `AccessCode` |
| `codes.delete(uuid)` | `DELETE codes/{uuid}/` | `None` |
| `calls.list(*, start: datetime \| None, end: datetime \| None, unit, building, result)` | `GET calls/` | `Iterator[CallLogEntry]` |
| `calls.get(uuid)` | `GET calls/{uuid}/` | `CallLogEntry` |

A `uuid`, or a UUID filter such as `building` or `unit`, that isn't a valid UUID raises `ValueError` without sending a request. Filters take `str`, or `UUID` and enum members where the schema says so. An `idempotency_key` must be 1 to 255 printable ASCII characters without spaces (the API's limit), or `codes.create` raises `ValueError` without sending.

Every time the client takes or returns is a timezone-aware `datetime` (MOD-1, MOD-4). `calls.list` takes the range `start <= started_at < end` (CALL-4 to CALL-6), so one local day is midnight to the next midnight in any zone; it sends the API the whole UTC dates covering it and drops the calls outside it. The API returns calls newest first by `started_at`, so iteration stops, requesting no more pages, at the first call before `start` (CALL-7).

Lists take no `limit` or `offset`: the iterator requests pages itself and follows `next` (PAG-1).

## Pagination

Every `list()` returns a plain `Iterator[T]` (a generator) that yields items, never pages, fetching each page as iteration reaches it (PAG-1, PAG-2). A `next` URL off the configured base URL raises `YamaError` instead of being followed, so the key never goes elsewhere. It's single-use, like any Python iterator (PAG-5): to use the items twice, call `list(...)` on it. Pages are parsed with a private `_Page` model and never exposed.

## Testing (`yama.testing`)

```python
def fake_transport() -> httpx.MockTransport
```

Use: `Yama(api_key="test", http_client=httpx.Client(transport=fake_transport()))` (TEST-1). It implements the behaviours listed in the foundations doc's testing strategy. Any key works except `rate-limited`, which gets a 429 with a `Retry-After` of 120 seconds on every request, so a caller sees `RateLimitError` without waiting. The repo's own tests check its responses against the vendored schema.

## Models (`yama.models`)

- **Responses**, mirroring the schema's components field for field: `ApiKeyDetails` (the schema's `ApiKey`; it describes the key and never holds the key itself), with `ApiKeyPermissions` and `ApiKeyUnitAccess`, `Building`, `Unit`, `Contact`, `AccessCode`, `CallLogEntry`, `CallLogStep`. Frozen, with `extra="allow"` (MOD-2).
- **Requests:** `AccessCodeCreate` (`unit: UUID`, `code: str`, `name: str | None = None`, `expires_at: AwareDatetime | None = None`) and `AccessCodeUpdate` (the same fields, all optional; an explicit None for `unit` or `code` is rejected, as the schema doesn't allow null there). `extra="forbid"` (MOD-4). Both enforce the schema's value rules: `code` matches `^[0-9]{3,15}$` and `name` is at most 255 characters (MOD-5). Response models don't, so a stored value that predates a rule still parses.
- **Enums**, as `str` enums whose `str()` and f-string give the value (`str(CallResult.REJECTED) == "rejected"`, MOD-6): `CallResult`, `CallStepKind`, `CodeAttemptResult`, `DialStatus`, `DoorDigit`, `AccessLevel` (`none`/`read`/`write`) and `UnitAccessType`. Response fields are typed `Enum | str` with left-to-right union mode (MOD-3). Members are the values upper-cased, with `-` as `_` (`DialStatus.NO_ANSWER`); `DoorDigit` members are `ZERO` to `NINE`. Compare with `==` (`call.result == CallResult.REJECTED`), which works for both forms without type narrowing.

## Errors

```
YamaError                       # base; also raised for misconfiguration (CFG-2); .idempotency_key (CODE-4)
├── APIConnectionError          # network failure, after retries; nothing may have been sent
│   └── APITimeoutError         # a request attempt timed out, after retries; it may have been processed
└── APIStatusError              # any other non-2xx: status_code, detail, body, api_version, method, path
    ├── BadRequestError         # 400; .errors: dict[str, list[str]]
    ├── AuthenticationError     # 401
    ├── PermissionDeniedError   # 403
    ├── NotFoundError           # 404
    ├── ConflictError           # 409: an Idempotency-Key still being processed (retried, RTY-6)
    ├── GoneError               # 410: a replayed create whose code has since been deleted; it was created
    ├── UnprocessableEntityError  # 422: an Idempotency-Key reused with a different request
    ├── RateLimitError          # 429; .retry_after: int | None (seconds)
    └── ServerError             # 5xx
```

A 405 or 415 (a method an endpoint doesn't offer, or a body that isn't JSON) raises plain `APIStatusError`: the client never sends either, so they get no class of their own.

An `APIStatusError`'s message is `"<status> <detail> (<method> <path>)"`, such as `"404 Not found. (GET /api/v2/buildings/<uuid>/)"`, where `detail` is the body's `detail`, or else its field errors joined (`"code: Access code already exists for this unit."`), or else the HTTP reason phrase, and `path` is the URL path without its query string. A connection error's message names the method and path too. Errors hold plain fields only, never the `httpx.Response` or a chained httpx error, which would hold the key (ERR-5, SEC-1). Every `YamaError` has `idempotency_key`, None except on an error from `codes.create`, where it's the key that was sent (CODE-4); it's a plain attribute, so it pickles. The `codes.create` docstring says to pass a stable `idempotency_key`, always with the same data, when the caller's own code may repeat a create (a job that re-runs, or a web form that carries it in a hidden field), and what each error means for a create.

## Implementation Defaults

Choices that aren't requirements, recorded so they're consistent: every list requests the API's maximum page size (`limit=500`), for the fewest requests under the rate limit. An open `start` is sent as `2000-01-01` (CALL-2); the live tests confirm the API accepts it. The call log's de-duplication remembers the last 1,000 UUIDs it yielded, two pages (CALL-1). Backoff starts at 0.5 s, doubles, is capped at 8 s, with full jitter. Retries depend on the method (RTY-7): a 429, or a failure to connect (`httpx.ConnectError`, `ConnectTimeout`, `PoolTimeout`), means the API never ran the request, so every method retries it; any other failure is retried for every method except a POST without an `Idempotency-Key`, which the client never sends. A retried DELETE that gets a 404 returns as done, unless every earlier attempt got a 429 or failed to connect (RTY-8).

Async isn't in v0.1, but the core is shaped so an `AsyncYama` is a small, non-breaking addition later: only sending and sleeping touch I/O.

- Plain functions, free of I/O, build each request (method, URL, headers, query, body), decide whether and how long to wait before a retry, and turn a response into a model or an error.
- `Yama` is a thin layer over them that sends with `httpx.Client` and waits with `time.sleep`. An `AsyncYama` would be the same layer over `httpx.AsyncClient` and `asyncio.sleep`, reusing every rule.
- Most tests exercise those functions directly, so they would cover both clients.
