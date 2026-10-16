# Changelog

All notable changes to yama-python. The project follows [Semantic Versioning](https://semver.org/). Sections are collected from each pull request's `## Changelog` section when a release is cut.

## Unreleased

## 0.1.0 - 2026-10-16

### Added

- `Yama` client with API-key configuration, timeouts, automatic retries that honour `Retry-After`, and typed exceptions for every failure.
- Automatic pagination and structured, key-free logging through the `yama` logger.
- `yama.testing.fake_transport()`, an in-memory Yama API for testing integrations without a network or a key.
- Methods for every v2 operation: `api_key`, `buildings`, `units`, `contacts`, `codes` and `calls`, with typed models and enums in `yama.models`.
- `codes.create` is safe to retry: it sends an `Idempotency-Key`, and a failed create's error carries the key as `idempotency_key`.
- `GoneError` (410) and `UnprocessableEntityError` (422) for replays of deleted codes and reused idempotency keys.
- `Yama.with_options()` for a shorter timeout or fewer retries at one call site.
- `calls.list` takes timezone-aware datetimes, so you can ask for a local day in any time zone.
- Documentation site with a guide and an API reference.
- HTTP errors now have `request_id`, the API's `Request-Id` for that call, which is also shown in the error message; quote it to Yama support.

### Changed

- Replaces, updates and deletes are retried after a 5xx or network error; a create without an `Idempotency-Key` still isn't.
- `calls.list(start=...)` stops fetching pages once it reaches calls older than `start`, so polling for recent calls takes one request instead of paging through the whole day.
- `Yama(http_client=...)` raises `TypeError` for anything but an `httpx.Client`, such as an `httpx.AsyncClient`.
- `AccessCodeUpdate(code=None)` and `AccessCodeUpdate(unit=None)` raise `pydantic.ValidationError`; only `name` and `expires_at` can be cleared.
- `AccessCodeCreate` and `AccessCodeUpdate` raise `pydantic.ValidationError` for a `code` that isn't 3 to 15 digits or a `name` over 255 characters, instead of leaving it to the API.
