# PRD: yama-python v0.1

Status: draft, 2026-10-15. Structure follows django-poc's PRD template: problem, direction, current-state audit, open questions.

## Problem Statement

Yama's REST API (`/api/v2/`) shipped in October 2026 so integrators can manage a building's access codes and read its call log from their own systems. Today every integrator hand-writes the same plumbing: Bearer-key auth, following `next` links, retrying 429s with `Retry-After`, parsing 400 field errors, and turning UTC timestamps into datetimes. The integrator guide even includes a hand-rolled `requests` helper for this.

That plumbing is where integrations go wrong. A missed `next` link silently truncates a sync, a retry loop that ignores `Retry-After` gets throttled, and a call log paged without de-duplication double-counts calls. Every integrator who gets it wrong becomes a support request for a one-person company.

A small, typed, official Python client removes that work and makes the documented behaviour the default. It's also the foundation for a TUI demo, planned after v0.1, that serves as a design reference for integrators.

**Who it's for:** developers working for or with an Account Holder (property managers, building operators, and the integrators they hire) who hold a Yama API key and write Python.

**If we don't:** each integration keeps reimplementing the plumbing, support load grows with each integrator, and Yama has no reference integration to point people to.

## Goals for v0.1

1. Cover every operation in the published v2 API (see the audit below), with the key's own record as the first call an integrator makes.
2. Make the correct behaviour the default: automatic pagination, retries only where the API says they're safe, typed errors.
3. Return typed objects with UTC-aware datetimes and UUIDs, and let callers use editor autocompletion instead of reading the docs.
4. Be installable from PyPI, documented, and tested without calling the production API.

## Non-goals for v0.1

- Async support. Design for it (see engineering foundations) but don't ship it.
- A CLI. The TUI demo comes after v0.1, in its own repo.
- Portal-only features that the API doesn't expose: unit, contact and building writes, API key management, user management.
- Webhooks or event streaming; the API doesn't offer them.

## Direction

Each item becomes a GitHub issue.

1. **Settle the open questions** below (done, see Settled Choices).
2. **Project skeleton:** packaging, tooling and a `justfile`, CI test matrix, the vendored OpenAPI schema and a drift check against the published one.
3. **Core transport:** client construction (key, base URL, timeout), Bearer auth, the `User-Agent`, error mapping to exception classes, and retries on 5xx/429/network errors with `Retry-After` and backoff.
4. **Pagination:** a lazy iterator that follows `next`, plus access to a single page and its `count` for callers who want it.
5. **Read resources:** API key, buildings, units, contacts, with their filters.
6. **Access codes:** list, get, create (with `expires_at`), update (PUT and PATCH, including clearing `expires_at`), delete.
7. **Call log:** list by date range with `unit`/`building`/`result` filters, get by uuid, and de-duplication by `uuid` while paging.
8. **Docs and examples:** README quick start, a reference generated from docstrings, and runnable examples matching the integrator guide's.
9. **Release tooling:** `just release` (with `--dry-run` and automatic version calculation), changelog collection, and the publish workflow.
10. **Release 0.1.0** to PyPI through trusted publishing, and announce it in the integrator guide.

## Current-State Audit

Checked against django-poc on 2026-10-15 (release 2026.10.6, `docs/api/reference.md` and `docs/api/getting-started.md`):

| Operation | Key permission |
|---|---|
| `GET /api/v2/api-key/` | any valid key |
| `GET /api/v2/buildings/`, `GET /api/v2/buildings/{uuid}/` | buildings: read |
| `GET /api/v2/units/` (`?building=`, `?door_digit=`), `GET /api/v2/units/{uuid}/` | units: read |
| `GET /api/v2/contacts/` (`?unit=`), `GET /api/v2/contacts/{uuid}/` | contacts: read |
| `GET /api/v2/codes/` (`?unit=`), `GET /api/v2/codes/{uuid}/` | codes: read |
| `POST`, `PUT`, `PATCH`, `DELETE /api/v2/codes/…` | codes: write |
| `GET /api/v2/calls/` (`start`, `end`, `?unit=`, `?building=`, `result`), `GET /api/v2/calls/{uuid}/` | call log: read |

Behaviour the client has to handle:

- **Auth:** `Authorization: Bearer <key>`. A missing key or too low a permission is a `403` with a `detail` string. The permission check runs before any lookup, so a 403 never reveals whether an object exists.
- **Pagination:** `limit` 1-500 (default 100) and `offset`; the envelope is `count`, `next`, `previous`, `results`. Follow `next` rather than building URLs.
- **Call log:** inclusive UTC `start`/`end` dates, sent together. Without them the API returns the last 30 days. New calls arrive at the top while you page, so a call can appear on two pages.
- **Strictness:** a read-only or unknown body field, or an undocumented query parameter, is a `400` naming it. Bodies are JSON only. An unknown object is a `404` with `{"detail": "Not found."}`.
- **Rate limits:** 600 requests a minute sustained and 20 a second burst, per key. A `429` carries `Retry-After` in whole seconds. Retry only on 5xx, 429 and network errors.
- **Versioning:** every response carries `API-Version: v2`. Changes within v2 are additive, so the client must tolerate new response fields and new enum values (for example a new call `result`).

Correction to earlier notes: django-poc TASK-243 mentioned a separate `before` + `limit` paging for the call log. The published API pages calls with `limit`/`offset` like every other list, filtered by `start`/`end`.

## Settled Choices

- PyPI name `yama`, import name `yama`.
- MIT licence.
- Hand-written client whose interface takes and returns Pydantic v2 models.
- Enum values the client doesn't know pass through as strings.
- Default base URL `https://app.getyama.ca`, overridden by the `base_url` argument or `YAMA_API_BASE_URL`.
- Python 3.10 and newer, with a policy for dropping old versions (see engineering foundations).

## Open Questions

None. Raise new ones here as implementation surfaces them.
