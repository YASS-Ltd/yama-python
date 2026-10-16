# PRD: yama-python v0.1

Status: draft, 2026-10-15. Problem, goals and scope, the API changes 0.1.0 depends on, and the requirements, in EARS form. How the work is split into issues lives in the issues, not here.

## Problem Statement

Yama's REST API (`/api/v2/`) shipped in October 2026 so integrators can manage a building's access codes and read its call log from their own systems. Today every integrator hand-writes the same plumbing: Bearer-key auth, following `next` links, retrying 429s with `Retry-After`, parsing 400 field errors, and turning UTC timestamps into datetimes. The integrator guide even includes a hand-rolled `requests` helper for this.

That plumbing is where integrations go wrong. A missed `next` link silently truncates a sync, a retry loop that ignores `Retry-After` gets throttled, and a call log paged without de-duplication double-counts calls. Every integrator who gets it wrong becomes a support request for a one-person company.

A small, typed, official Python client removes that work and makes the documented behaviour the default. It's also the foundation for a TUI demo, planned after v0.1, that serves as a design reference for integrators.

**Who it's for:** developers working for or with an Account Holder (property managers, building operators, and the integrators they hire) who hold a Yama API key and write Python.

**If we don't:** each integration keeps reimplementing the plumbing, support load grows with each integrator, and Yama has no reference integration to point people to.

## Goals for v0.1

1. Cover every operation in the published v2 API, with the key's own record as the first call an integrator makes.
2. Make the correct behaviour the default: automatic pagination, retries only where the API says they're safe, typed errors.
3. Return typed objects with UTC-aware datetimes and UUIDs, and let callers use editor autocompletion instead of reading the docs.
4. Be installable from PyPI, documented, and tested without calling the production API.

## Non-goals for v0.1

- Async support. The core is shaped for it (see `design/interface.md`); it comes in a later minor release, when integrators ask for it.
- A CLI. The TUI demo comes after v0.1, in its own repo.
- Portal-only features that the API doesn't expose: unit, contact and building writes, API key management, user management.
- Webhooks or event streaming; the API doesn't offer them.

## API Prerequisites

0.1.0 waits on one API change, handed off to django-poc: `POST /api/v2/codes/` honouring an `Idempotency-Key` header, so the client retries creates safely and an integrator never has to work out whether a failed create happened. Work on the client doesn't wait for it; it's built and tested against the in-memory fake.

## Requirements

Written in [EARS](https://alistairmavin.com/ears/) form: each is one testable sentence about behaviour an integrator can observe. Names and signatures are in `design/interface.md`; fields, filters and statuses are in the vendored schema. Each requirement has a test named after its ID (for example `test_rty_2_...`), and issues list the IDs they deliver.

### Configuration (CFG)

- **CFG-1** The client shall use the `api_key` argument as its API key, and only where the caller omits the argument, the `YAMA_API_KEY` environment variable.
- **CFG-2** If the caller passes `api_key` as `None` or an empty string, or omits it while `YAMA_API_KEY` is unset or empty, then the client shall raise `YamaError` when constructed, without sending a request.
- **CFG-3** The client shall send requests to the `base_url` argument, or else `YAMA_API_BASE_URL`, or else `https://app.yamasystems.com`.
- **CFG-4** The client shall apply `timeout` as httpx does: a number of seconds (default 30) limits each phase of a request attempt (connecting, writing, reading, waiting for a pooled connection), and an `httpx.Timeout` sets the phases individually. `None` is rejected with `TypeError`; `httpx.Timeout(None)` turns timeouts off.
- **CFG-5** Where the caller provides an `httpx.Client`, the client shall send every request through it with its own base URL, timeout and headers applied per request, and shall leave closing it to the caller. If it is not an `httpx.Client`, such as an `httpx.AsyncClient`, then the client shall raise `TypeError` when constructed.
- **CFG-6** When the caller calls `with_options()` with a `timeout` or `max_retries`, the client shall return a copy that uses them and shares the original's connections, API key and base URL, leaving the original unchanged and open when the copy is closed.

### Requests (HTTP)

- **HTTP-1** The client shall send the API key as `Authorization: Bearer <key>` on every request.
- **HTTP-2** The client shall send `User-Agent: yama-python/<version> python/<major.minor>` on every request.
- **HTTP-3** The client shall send a filter as a query parameter only when the caller sets it.
- **HTTP-4** The client shall send request bodies as JSON.

### Errors (ERR)

- **ERR-1** When the API returns a non-2xx status, the client shall raise the `APIStatusError` subclass for that status (or `APIStatusError` itself for a status without one), carrying the status code, the body's `detail`, the parsed body, the `API-Version` header, and the request's method and path (never its query string).
- **ERR-2** When the API returns 400, the client shall expose its map of keys to messages on the error. Keys name body fields or query parameters, and may include keys that aren't fields at all, such as `non_field_errors`.
- **ERR-3** If a request still fails at the network level after its retries, then the client shall raise `APIConnectionError`, or its subclass `APITimeoutError` when the last attempt timed out.
- **ERR-4** The client shall raise only `YamaError` subclasses for failed calls, and `TypeError` or `ValueError` for invalid arguments. Using a closed client is a programming error, and raises `ValueError`.
- **ERR-5** The client's exceptions shall survive a pickle round trip with their fields intact.

### Security (SEC)

- **SEC-1** The client shall keep the API key out of every `repr`, exception message, log record and URL.

### Logging (LOG)

- **LOG-1** The client shall log one DEBUG record to the `yama` logger per HTTP attempt, with its method, path, status, elapsed time and attempt number in the message and as `yama_`-prefixed `extra` fields.
- **LOG-2** When the client retries a request, it shall log one INFO record with the reason, the wait and the attempt number, in the same two forms.
- **LOG-3** The client shall keep API keys, headers, request and response bodies and query strings out of every log record, and shall log nothing at WARNING or above.

### Retries (RTY)

- **RTY-1** When a request gets a 429, a 5xx or a network error (a connection that fails or breaks, or an attempt that times out), the client shall retry it, up to `max_retries` times (default 2), except as RTY-7 says.
- **RTY-2** When a 429, or a 409 that RTY-6 retries, carries `Retry-After`, the client shall wait that many seconds before retrying.
- **RTY-3** If `Retry-After` exceeds 60 seconds, then the client shall raise the error (`RateLimitError` or `ConflictError`) without waiting.
- **RTY-4** When the API gives no `Retry-After`, the client shall wait an increasing, jittered delay between attempts.
- **RTY-5** If a request gets a 4xx other than 429, then the client shall not retry it, except as RTY-6 allows.
- **RTY-6** When a request carrying an `Idempotency-Key` gets a 409 (that key still in flight), the client shall retry it like any other retry, counting it against `max_retries` and waiting as RTY-2 and RTY-4 say.
- **RTY-7** If a POST that carries no `Idempotency-Key` gets a 5xx or a network error after connecting (so the API may have run it), then the client shall raise the error without retrying.
- **RTY-8** If a retry of a DELETE gets a 404 after an earlier attempt got a 5xx or failed after connecting (so it may have run), then the client shall treat the delete as done.

### Pagination (PAG)

- **PAG-1** When the caller iterates a list, the client shall yield every item on every page, following each `next` URL until it is null, and only while it is on the configured base URL (same scheme, host and port); otherwise it shall raise `YamaError` without sending the request.
- **PAG-2** The client shall send no request for a list until the caller starts iterating it.
- **PAG-5** Each call to a list method shall return a new, single-use iterator that starts from the first page; once it's exhausted, it yields nothing more and sends no further requests.

### Call log (CALL)

- **CALL-1** While iterating the call log, the client shall skip any call whose `uuid` it has already yielded within the last two pages.
- **CALL-2** When the caller omits `start` or `end`, the client shall treat that side of the range as open, sending the earliest date the API accepts for a missing `start` and tomorrow's UTC date for a missing `end` (in case the caller's clock is a little behind the API's), so a call with neither covers all history.
- **CALL-3** The client shall send `start` and `end` as the ISO 8601 UTC dates that cover the range: the UTC date of `start`, and of the last instant before `end`.
- **CALL-4** While iterating the call log, the client shall yield only calls whose `started_at` is at or after `start` and before `end`.
- **CALL-5** If `start` or `end` is not a timezone-aware `datetime`, then the client shall raise without sending a request: `TypeError` for a `date` or other type, `ValueError` for a naive `datetime`.
- **CALL-6** If `end` is before `start`, then the client shall raise `ValueError` without sending a request; an `end` equal to `start` is an empty range.
- **CALL-7** When `start` is given, the client shall stop requesting pages once it reaches a call that started before `start`, since the API returns calls newest first by `started_at`.

### Access codes (CODE)

- **CODE-1** When creating an access code, the client shall send an `Idempotency-Key` header: the caller's `idempotency_key` where given, or else a new random UUID.
- **CODE-2** The client shall send the same `Idempotency-Key` on every retry of a create.
- **CODE-3** When updating an access code, the client shall send only the fields the caller set, including fields set to `None`.
- **CODE-4** If a create fails with a `YamaError`, then the client shall set the error's `idempotency_key` to the key it sent, so the caller can retry with it.

### Models (MOD)

- **MOD-1** The client shall return responses as Pydantic models, with UUIDs as `UUID` and datetimes timezone-aware.
- **MOD-2** When a response contains a field the client doesn't define, the client shall keep it readable on the model.
- **MOD-3** When a response contains an enum value the client doesn't know, the client shall return it as a plain string.
- **MOD-4** If a request model is given a field it doesn't define, a datetime without a timezone, or null for a field the schema doesn't allow null, then building the model shall raise `pydantic.ValidationError`.
- **MOD-5** The client shall check only types and required fields in request models, leaving value rules such as lengths to the API.
- **MOD-6** The client's enum members shall give their value from `str()` and in f-strings, as the plain strings of MOD-3 do.

### Coverage (OPS)

- **OPS-1** The client shall provide a method for every operation in the vendored schema, with every query filter the schema defines for it.

### Testing support (TEST)

- **TEST-1** The package shall provide `yama.testing.fake_transport()`, returning an `httpx.MockTransport` that serves an in-memory Yama API with made-up data, so integrators can test their own code without a network or a key.

### Package (PKG)

- **PKG-1** The package shall install on Python 3.10 and newer, with httpx and Pydantic as its only runtime dependencies.
- **PKG-2** The package shall ship type information and pass mypy in strict mode.
- **PKG-3** Importing `yama` shall send no requests and produce no output, warnings or logging configuration.
- **PKG-4** The client shall be safe to use from several threads at once.

### Delivery (DEL)

- **DEL-1** The package shall be published to PyPI as `yama` through trusted publishing.
- **DEL-2** The documentation site shall cover install, configuration, pagination, errors, retries, logging, testing with the fake API, using the client in web apps and background jobs (one client per process, short timeouts in requests, a stable `idempotency_key` where a job may re-run a create), and versioning, with a reference generated from docstrings.
- **DEL-3** The README quick start shall run as written against the in-memory fake API.

## Settled Choices

- PyPI name `yama`, import name `yama`.
- MIT licence.
- Hand-written client whose interface takes and returns Pydantic v2 models.
- Python 3.10 and newer, with a policy for dropping old versions (see engineering foundations).

## Open Questions

None. Raise new ones here as implementation surfaces them.
