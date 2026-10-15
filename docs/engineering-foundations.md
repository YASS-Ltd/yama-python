# Engineering Foundations

The tech stack, design principles, testing, CI and release process for yama-python. `AGENTS.md` holds the day-to-day workflow. This doc holds the reasoning that workflow rests on.

Items marked **Proposed** are working defaults, not yet confirmed. Confirm or change each one when the work reaches it, and update this doc.

## Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.10 and newer (see Supported Python Versions) |
| HTTP | [httpx](https://www.python-httpx.org/) |
| Models | Pydantic v2, hand-written |
| Package manager and build | uv, with the `uv_build` backend |
| Linting and formatting | ruff |
| Type checking | mypy in strict mode, and the package ships `py.typed` |
| Testing | pytest, [respx](https://lundberg.github.io/respx/) for mocked HTTP |
| Docs | **Proposed:** MkDocs with mkdocstrings, published to GitHub Pages |

httpx is chosen over requests because it offers sync and async clients with one interface, so async can be added later without a rewrite. It also has timeouts on by default and is well typed.

## Supported Python Versions

- `requires-python = ">=3.10"`, never with an upper bound. CI tests every supported version, including the newest CPython release.
- A version is dropped only after it is out of upstream support **and** either the default Python on the oldest supported Ubuntu LTS has moved past it or a runtime dependency (httpx, Pydantic) has dropped it.
- Drops happen in a minor release and are announced in the changelog. pip honours `requires-python`, so integrators on a dropped version keep getting the last release that supports it.
- Review this at each Ubuntu LTS end-of-standard-support date and each new CPython release. 3.10 is expected to go around April 2027.

## Design Principles

1. **The schema is the contract.** The published OpenAPI schema from `https://app.getyama.ca/api/v2/schema/` is vendored in the repo as a test fixture. The client and its models are hand-written, and contract tests check them against the vendored schema. CI flags when the vendored copy drifts from the published one; updating it, and the client to match, is a deliberate change.
2. **Correct by default.** Iterating a list follows `next` to the end, and retries happen only where the API says they're safe (5xx, 429 with `Retry-After`, network errors). Calls time out by default. The integrator shouldn't have to read the docs to avoid a known trap.
3. **Resource-oriented interface that speaks Pydantic:** `client.codes.list(unit=...)`, `client.codes.create(AccessCodeCreate(...))`, `client.calls.list(start=..., end=...)`. It mirrors the API's URLs, so the API docs map directly onto the client. Methods take and return Pydantic models.
4. **Typed errors.** One base `YamaError`, with subclasses by HTTP status: `AuthenticationError` and `PermissionDeniedError` for 403s, `NotFoundError`, `ValidationError` (carrying the field-to-messages map), `RateLimitError` (carrying `retry_after`), `ServerError`, and `ConnectionError` for network failures. Every error keeps the status, the parsed body and the `API-Version` header.
5. **Additive tolerance.** Models accept unknown response fields, since the API may add fields within v2, and unknown enum values pass through as strings, so a new call `result` doesn't break existing integrations.
6. **Keys stay secret.** The key appears in no `repr`, log line, exception message or URL. The client reads `YAMA_API_KEY` if no key is passed, as in the integrator guide, and the base URL defaults to production unless overridden.
7. **Small dependency footprint.** Runtime dependencies are httpx and Pydantic, nothing else, each with the lowest version floor the code allows. Every extra dependency is a version conflict waiting in someone else's project.
8. **Identify the client.** Requests send `User-Agent: yama-python/<version> python/<version>`, so the server's logs show which client versions are in use.

## Testing Strategy

- **Tests first:** write a failing test, then the minimum code to pass, then refactor.
- **Unit tests** mock HTTP with respx. They cover each operation's request (method, path, query, body), response parsing, pagination edge cases (empty list, one page, many pages, a `next` that repeats a call), the error mapping for each status, and retry behaviour, using a fake clock so tests don't sleep.
- **Contract tests** check the client against the vendored schema: every operation in the schema has a client method, and every request the client builds validates against the schema.
- **No production calls** in tests or CI. An optional live-test suite runs against a non-production Yama instance with a dedicated key, outside CI, and is skipped when the environment variables are absent.
- **Fixtures** use made-up data shaped like the integrator guide's examples. Never commit real API responses: they hold customer phone numbers and names.
- **Coverage** is reported in CI. **Proposed:** a 90% floor on the `yama` package, enforced once v0.1's core is in.

## CI and Branch Policy

GitHub Actions on every pull request and every push to `main`:

1. ruff (lint and format check) and mypy.
2. pytest across the supported Python versions on Linux, plus the newest version on macOS and Windows.
3. A schema drift check: fetch the published schema and compare it with the vendored copy. A drift fails a scheduled daily run and opens an issue; on PRs it only warns, so an API release doesn't block unrelated work.
4. A build check: build the sdist and wheel, then install the wheel into a clean environment and import it.

Branches: feature branches off `main`, squash-merged through PRs with `Closes #<n>`. `main` is always releasable.

## Release Process

- **Versioning:** SemVer, independent of the app's CalVer releases. Before 1.0, minor versions may break the interface, and every break is called out in the changelog. From 1.0, breaks need a major version.
- **Mapping to the API:** each release targets one API version (`v2`). A future `/api/v3/` gets new client code side by side or a major release, decided when v3 exists.
- **Changelog:** each user-facing PR carries a `## Changelog` section, collected into `CHANGELOG.md` at release, the same convention as django-poc.
- **Publishing:** tagging `vX.Y.Z` on `main` runs a workflow that builds and publishes to PyPI through trusted publishing (no stored PyPI token) and creates the GitHub Release.

## Security

- The repo is public: no keys, customer data, internal hostnames or django-poc internals in code, tests, issues or docs.
- Dependabot keeps dependencies and the GitHub Actions in use up to date, and `SECURITY.md` explains how to report a vulnerability privately.
- Release artifacts get PyPI's attestations through trusted publishing.
