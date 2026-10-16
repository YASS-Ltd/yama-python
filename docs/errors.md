# Errors and retries

## What a call raises

A failed call raises a [`YamaError`][yama.YamaError] subclass, never an httpx or Pydantic error. Invalid arguments, such as a naive datetime or a malformed UUID, raise `TypeError` or `ValueError` before anything is sent. Building a request model with an unknown field, a datetime without a time zone, or None for a field that can't be cleared raises `pydantic.ValidationError`, which is a `ValueError`.

| Error | When | Try again later? |
|---|---|---|
| `YamaError` | The base class. Raised itself for misconfiguration, or a response the client can't read. | No |
| `APIConnectionError` | The network failed, after retries. | Yes |
| ↳ `APITimeoutError` | The last attempt timed out, after retries. The API may still have run it. | Yes |
| `APIStatusError` | The base class for HTTP errors; raised itself for a status not listed below. | No |
| ↳ `BadRequestError` | 400: a field or filter is invalid. `errors` maps each to its messages. | No |
| ↳ `AuthenticationError` | 401: the API key is malformed, unknown, deleted or expired. | No |
| ↳ `PermissionDeniedError` | 403: the API key lacks the permission this call needs. | No |
| ↳ `NotFoundError` | 404: no such object within the API key's reach. | No |
| ↳ `ConflictError` | 409: a create with the same idempotency key was still running, after retries. | Yes |
| ↳ `GoneError` | 410: a repeated create did happen, but its code has since been deleted or is out of the API key's reach. | No |
| ↳ `UnprocessableEntityError` | 422: the idempotency key was already used with different data. | No |
| ↳ `RateLimitError` | 429: too many requests, after retries, or at once when the wait is over 60 seconds. `retry_after` is the wait in seconds, or None. | Yes |
| ↳ `ServerError` | 5xx: the API failed, after retries. | Yes |

"No" means fix the request or your setup first.

An `APIStatusError` carries `status_code`, `detail`, the parsed `body`, `api_version`, `method`, `path` and `request_id`, the response's `Request-Id` (None when it has none). Quote the `request_id` to Yama support when asking about a failed call. Its message reads like `404 Not found. (GET /api/v2/codes/<uuid>/, Request-Id req_3f9c...)`. Every error pickles with its fields intact.

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

`codes.create()` sends an idempotency key in the `Idempotency-Key` header, so the API runs the create at most once however many times it's sent with that idempotency key. Each call uses a new idempotency key, kept across its retries, unless you pass `idempotency_key`. When a create still fails, the error's `idempotency_key` is the idempotency key that was sent.

After an `APIConnectionError`, a `ConflictError` or a `ServerError`, you don't know whether the create happened, and the client has already retried it. Keep `error.idempotency_key`, and send the create again later with that idempotency key and the same data:

```python
from yama import APIConnectionError, ConflictError, ServerError

data = AccessCodeCreate(unit=unit.uuid, code="8642", name="Dog walker")
try:
    code = client.codes.create(data)
except (APIConnectionError, ConflictError, ServerError) as error:
    retry_key = error.idempotency_key  # send `data` again later with this idempotency key
```

**Idempotency keys:**

- **Same idempotency key, same data.** An idempotency key reused with different data raises `UnprocessableEntityError`. A time sent with a different UTC offset counts as different data, so work out times such as `expires_at` once.
- **The API remembers an idempotency key for 24 hours**, along with the answer it gave. A repeat within that time gets the same answer: the code, or the same 400. To send corrected data after a `BadRequestError`, use a new idempotency key.
- **`GoneError`** means the create with that idempotency key happened, but the code has since been deleted. Don't create it again with that idempotency key.
- **Your own idempotency key.** When your own code may repeat a create, such as a job that re-runs or a form submitted twice, pass a stable `idempotency_key` of your own: one derived from your own record, or one generated when you render the form and carried in a hidden field.
