# Errors and retries

## What a call raises

A failed call raises a [`YamaError`][yama.YamaError] subclass, never an httpx or Pydantic error. Invalid arguments, such as a naive datetime or a malformed UUID, raise `TypeError` or `ValueError` before anything is sent.

| Error | When |
|---|---|
| `YamaError` | The base class. Raised itself for misconfiguration, such as no API key. |
| `APIConnectionError` | The network failed, after retries. |
| ↳ `APITimeoutError` | The last attempt timed out, after retries. The API may still have run it. |
| `APIStatusError` | Any other non-2xx answer. |
| ↳ `BadRequestError` | 400: a field or filter is invalid. `errors` maps each to its messages. |
| ↳ `AuthenticationError` | 401: the key is malformed, unknown, deleted or expired. |
| ↳ `PermissionDeniedError` | 403: the key lacks the permission this call needs. |
| ↳ `NotFoundError` | 404: no such object within the key's reach. |
| ↳ `ConflictError` | 409: a create with the same idempotency key was still running, after retries. |
| ↳ `GoneError` | 410: a repeated create did happen, but its code has since been deleted. |
| ↳ `UnprocessableEntityError` | 422: the idempotency key was already used with different data. |
| ↳ `RateLimitError` | 429: too many requests, after retries. `retry_after` is the wait in seconds. |
| ↳ `ServerError` | 5xx: the API failed, after retries. |

An `APIStatusError` carries `status_code`, `detail`, the parsed `body`, `api_version`, `method` and `path`. Its message reads like `404 Not found. (GET /api/v2/codes/<uuid>/)`. Every error pickles with its fields intact.

```python
from yama import AccessCodeCreate, BadRequestError, NotFoundError, Yama

client = Yama()
unit = next(client.units.list())

try:
    client.codes.create(AccessCodeCreate(unit=unit.uuid, code="1234"))
except BadRequestError as error:
    print(error.errors)  # {'code': ['Access code already exists for this unit.']}

try:
    client.codes.get("00000000-0000-4000-8000-ffffffffffff")
except NotFoundError as error:
    print(error.status_code, error.detail)
```

## Retries

The client retries a request, up to `max_retries` times (2 by default), only where repeating it can't do harm:

- **A 429, or a failure to connect**, for every call: the API never ran the request.
- **A 5xx, a timeout or a broken connection**, for every call, creates included (see [Creates that are safe to repeat](#creates-that-are-safe-to-repeat)).
- **Never** a 4xx other than 429, which would fail again. A 409 on a create is retried, since it means the first attempt is still running.

It waits as long as `Retry-After` says, or else a random, increasing delay of up to 8 seconds. When `Retry-After` asks for more than 60 seconds, it raises `RateLimitError` at once instead of blocking, and you choose when to try again. A retried delete that gets a 404 counts as done, since an earlier attempt may have deleted it. Each retry is logged at INFO (see [Logging](logging.md)).

## Creates that are safe to repeat

`codes.create()` sends an `Idempotency-Key`, so the API runs the create at most once however many times it's sent with that key. Each call uses a new key, kept across its retries, unless you pass `idempotency_key`. When a create still fails, the error's `idempotency_key` is the key that was sent. If you don't know whether the create happened, after an `APIConnectionError`, a `ConflictError` or a `ServerError`, send it again with that key and the same data:

```python
from yama import APIConnectionError, ConflictError, ServerError

data = AccessCodeCreate(unit=unit.uuid, code="8642", name="Dog walker")
try:
    code = client.codes.create(data)
except (APIConnectionError, ConflictError, ServerError) as error:
    code = client.codes.create(data, idempotency_key=error.idempotency_key)
```

Things to know about keys:

- **Same key, same data.** A key reused with different data raises `UnprocessableEntityError`. A time sent with a different UTC offset counts as different data, so work out times such as `expires_at` once.
- **The API remembers a key for 24 hours**, along with the answer it gave. A repeat within that time gets the same answer: the code, or the same 400. To send corrected data after a `BadRequestError`, use a new key.
- **`GoneError`** means the create with that key happened, but the code has since been deleted. Don't create it again with that key.
- When your own code may repeat a create, such as a job that re-runs or a form submitted twice, pass a stable `idempotency_key` of your own: one derived from your own record, or one generated when you render the form and carried in a hidden field.
