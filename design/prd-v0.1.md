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

- Async support. Design for it (see engineering foundations) but don't ship it.
- A CLI. The TUI demo comes after v0.1, in its own repo.
- Portal-only features that the API doesn't expose: unit, contact and building writes, API key management, user management.
- Webhooks or event streaming; the API doesn't offer them.

## API Prerequisites

0.1.0 waits on one API change, handed off to django-poc: `POST /api/v2/codes/` honouring an `Idempotency-Key` header, so the client retries creates safely and an integrator never has to work out whether a failed create happened. Work on the client doesn't wait for it; it's built and tested against the in-memory fake.

## Requirements

Written in [EARS](https://alistairmavin.com/ears/) form: each is one testable sentence about behaviour an integrator can observe. Names and signatures are in `design/interface.md`; fields, filters and statuses are in the vendored schema. Each requirement has a test named after its ID (for example `test_rty_2_...`), and issues list the IDs they deliver.

### Configuration (CFG)

- **CFG-1** The client shall use the `api_key` argument, or else the `YAMA_API_KEY` environment variable, as its API key.
- **CFG-2** If no API key is available, then the client shall raise `YamaError` when constructed, without sending a request.
- **CFG-3** The client shall send requests to the `base_url` argument, or else `YAMA_API_BASE_URL`, or else `https://app.yamasystems.com`.
- **CFG-4** The client shall give up on a request attempt after `timeout` seconds (default 30).
- **CFG-5** Where the caller provides an `httpx.Client`, the client shall send every request through it and shall leave closing it to the caller.

### Requests (HTTP)

- **HTTP-1** The client shall send the API key as `Authorization: Bearer <key>` on every request.
- **HTTP-2** The client shall send `User-Agent: yama-python/<version> python/<major.minor>` on every request.
- **HTTP-3** The client shall send a filter as a query parameter only when the caller sets it.
- **HTTP-4** The client shall send request bodies as JSON.

### Errors (ERR)

- **ERR-1** When the API returns a non-2xx status, the client shall raise the `APIStatusError` subclass for that status, carrying the status code, the body's `detail`, the parsed body and the `API-Version` header.
- **ERR-2** When the API returns 400, the client shall expose its field-to-messages map on the error.
- **ERR-3** If a request still fails at the network level after its retries, then the client shall raise `APIConnectionError`.
- **ERR-4** The client shall raise only `YamaError` subclasses for failed calls, and `TypeError` or `ValueError` for invalid arguments.

### Security (SEC)

- **SEC-1** The client shall keep the API key out of every `repr`, exception message, log record and URL.

### Retries (RTY)

- **RTY-1** When a request gets a 429, a 5xx or a network error, the client shall retry it, up to `max_retries` times (default 2).
- **RTY-2** When a 429 carries `Retry-After`, the client shall wait that many seconds before retrying.
- **RTY-3** If `Retry-After` exceeds 60 seconds, then the client shall raise `RateLimitError` without waiting.
- **RTY-4** When the API gives no `Retry-After`, the client shall wait an increasing, jittered delay between attempts.
- **RTY-5** If a request gets a 4xx other than 429, then the client shall not retry it, except as RTY-6 allows.
- **RTY-6** When creating an access code gets a 409 (its idempotency key still in flight), the client shall retry it.

### Pagination (PAG)

- **PAG-1** When the caller iterates a list, the client shall yield every item on every page, following each `next` URL as given until it is null.
- **PAG-2** The client shall send no request for a list until the caller starts iterating it.
- **PAG-3** Where the caller sets `page_size`, the client shall send it as `limit`.
- **PAG-4** The client shall let the caller iterate a list page by page, with each page's `count`, `next`, `previous` and `results`.

### Call log (CALL)

- **CALL-1** While iterating the call log, the client shall skip any call whose `uuid` it has already yielded in that iteration.
- **CALL-2** If the caller passes only one of `start` and `end`, then the client shall raise `ValueError` without sending a request.
- **CALL-3** The client shall send `start` and `end` as ISO 8601 dates.

### Access codes (CODE)

- **CODE-1** When creating an access code, the client shall send an `Idempotency-Key` header: the caller's `idempotency_key` where given, or else a new random UUID.
- **CODE-2** The client shall send the same `Idempotency-Key` on every retry of a create.
- **CODE-3** When updating an access code, the client shall send only the fields the caller set, including fields set to `None`.

### Models (MOD)

- **MOD-1** The client shall return responses as Pydantic models, with UUIDs as `UUID` and datetimes timezone-aware.
- **MOD-2** When a response contains a field the client doesn't define, the client shall keep it readable on the model.
- **MOD-3** When a response contains an enum value the client doesn't know, the client shall return it as a plain string.
- **MOD-4** If a request model is given a field it doesn't define, or a datetime without a timezone, then the client shall raise before sending anything.
- **MOD-5** The client shall check only types and required fields in request models, leaving value rules such as lengths to the API.

### Coverage (OPS)

- **OPS-1** The client shall provide a method for every operation in the vendored schema, with every query filter the schema defines for it.

### Package (PKG)

- **PKG-1** The package shall install on Python 3.10 and newer, with httpx and Pydantic as its only runtime dependencies.
- **PKG-2** The package shall ship type information and pass mypy in strict mode.
- **PKG-3** Importing `yama` shall send no requests and produce no output, warnings or logging configuration.
- **PKG-4** The client shall be safe to use from several threads at once.

### Delivery (DEL)

- **DEL-1** The package shall be published to PyPI as `yama` through trusted publishing.
- **DEL-2** The documentation site shall cover install, configuration, pagination, errors, retries and versioning, with a reference generated from docstrings.
- **DEL-3** The README quick start shall run as written against the in-memory fake API.

## Settled Choices

- PyPI name `yama`, import name `yama`.
- MIT licence.
- Hand-written client whose interface takes and returns Pydantic v2 models.
- Enum values the client doesn't know pass through as strings.
- Default base URL `https://app.yamasystems.com`, overridden by the `base_url` argument or `YAMA_API_BASE_URL`.
- Python 3.10 and newer, with a policy for dropping old versions (see engineering foundations).

## Open Questions

None. Raise new ones here as implementation surfaces them.
