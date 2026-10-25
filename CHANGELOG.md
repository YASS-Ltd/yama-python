# Changelog

All notable changes to yama-python. The project follows [Semantic Versioning](https://semver.org/). Sections are collected from each pull request's `## Changelog` section when a release is cut.

## Unreleased

## 0.2.1 - 2026-10-25

### Changed

- `yama.testing`'s fake API answers 404s, 410s and call labels with the same wording as the live API.

### Fixed

- `yama.testing`'s fake API answers 405 for a method an endpoint doesn't offer and 415 for a body that isn't JSON, as the live API does, instead of 404 and 400.

## 0.2.0 - 2026-10-18

### Changed

- Breaking: `Yama()` raises `ValueError` for a plain `http://` base URL (argument or `YAMA_API_BASE_URL`) unless the host is `localhost`, `127.0.0.1` or `[::1]`, and then ignores proxies set in the environment, so your API key isn't sent unencrypted over a network. Use `https://` for any other host. If you pass your own `http_client`, its proxy settings still apply.
- The `ValueError` for a bad API key or base URL now says where the value came from: the argument (`api_key`, `base_url`) or the environment variable (`YAMA_API_KEY`, `YAMA_API_BASE_URL`).

### Fixed

- A 429 with a malformed `Retry-After` header raises `RateLimitError` or retries as usual, instead of a bare `ValueError`.
- With your own `httpx.Client` whose response hook calls `raise_for_status()`, an error status raises the matching error, such as `NotFoundError`, instead of `APIConnectionError`.
- The fake API in `yama.testing` answers 400, instead of crashing, when a code's `unit` isn't a string.
- Passing your own `httpx.Client` that has `auth` set no longer replaces your API key, so requests no longer fail with 401.
- A base URL with whitespace around it, such as a trailing space or newline from a `.env` file, now works instead of failing every request.
- A base URL with a query or fragment raises `ValueError` instead of sending requests to the wrong path.
- A `base_url` that isn't a string raises `TypeError`.
- A pagination `next` link or base URL with a malformed internationalised host name (such as `xn--a-`) raises `YamaError` or `ValueError` as other bad URLs do, instead of an error from the `idna` package.

### Security

- An error for a response the client can't read no longer carries the response's values, so they can't reach logs or error trackers; it names the fields that failed instead.
- A base URL with a username or password (`https://user:pw@host`) raises `ValueError`. Before, they were sent as Basic auth in place of your API key, and `repr()` of the client showed them.

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
