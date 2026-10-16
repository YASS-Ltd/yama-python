# Changelog

All notable changes to yama-python. The project follows [Semantic Versioning](https://semver.org/). Sections are collected from each pull request's `## Changelog` section when a release is cut.

## Unreleased

## 0.1.0 - 2026-10-16

First release of the official Python client for the Yama v2 API. Install it with `pip install yama-client` (or `uv add yama-client`) and import it as `yama`. It needs Python 3.10 or newer.

### Added

- `Yama` client with methods for every v2 operation: `api_key`, `buildings`, `units`, `contacts`, `codes` and `calls`, returning typed models from `yama.models`.
- Automatic pagination, timeouts, and retries that honour `Retry-After`. Reads, replaces, updates and deletes are retried after a 5xx or network error.
- `codes.create` is safe to retry: it sends an `Idempotency-Key`, and a failed create's error carries the key as `idempotency_key`.
- Request models that check codes (3 to 15 digits) and names (at most 255 characters) before anything is sent.
- `calls.list` takes timezone-aware `start` and `end`, so you can ask for a local day in any time zone, and polling for recent calls takes one request.
- Typed exceptions for every failure, each with the API's `request_id` to quote to Yama support.
- `Yama.with_options()` for a shorter timeout or fewer retries at one call site.
- Structured, key-free logging through the `yama` logger.
- `yama.testing.fake_transport()`, an in-memory Yama API for testing integrations without a network or a key.
- [Documentation](https://yass-ltd.github.io/yama-python/) with a guide and an API reference.
