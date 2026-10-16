# Engineering Foundations

The tech stack, design principles, testing, CI and release process for yama-python. `AGENTS.md` holds the day-to-day workflow. This doc holds the reasoning that workflow rests on.

Items marked **Proposed** are working defaults, not yet confirmed. Confirm or change each one when the work reaches it, and update this doc.

## Guiding Star: Lightweight

Lightweight code and lightweight process. Few dependencies, little code, and as few files, steps, tools and rules as the job needs. When two approaches both work, pick the one with less to read, run and maintain. Every addition to this doc, the `justfile`, CI or the issue process has to earn its place, and removing something that no longer does is a welcome change.

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
| Docs | [Zensical](https://zensical.org/) with mkdocstrings, published to GitHub Pages |
| Task runner | [just](https://just.systems/man/en/) |

Zensical is the successor to Material for MkDocs, from the same team; Material went into maintenance mode in November 2025. The site is branded with Yama's colours, Dark Forest `#21212B` and Clay Rose `#E3C8BD`, and the logo and icon in `.github/assets/` (the logo has a Dark Forest variant for light backgrounds and a Clay Rose one for dark). Zensical is young; if it falls short, Material for MkDocs reads the same configuration.

httpx is chosen over requests because it offers sync and async clients with one interface, so async can be added later without a rewrite. It also has timeouts on by default and is well typed.

The `justfile` is the single entry point for repeated commands: `just test`, `just lint`, `just check` (everything CI runs), `just schema-pull` and `just release`. CI calls the same recipes, so a green `just check` locally means a green CI run. Recipes wrap uv; they never replace it.

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
- **Unit tests** mock single HTTP exchanges with respx. They cover each operation's request (method, path, query, body), response parsing, pagination edge cases (empty list, one page, many pages, a `next` that repeats a call), the error mapping for each status, and retry behaviour, using a fake clock so tests don't sleep.
- **Contract tests** check the client against the vendored schema: every operation in the schema has a client method, and every request the client builds validates against the schema.
- **An in-memory fake API** built on `httpx.MockTransport`, with no server or process. It holds a few made-up buildings, units, contacts, codes and calls in dicts and implements the real behaviours: `limit`/`offset` with `next` links, code create, update and delete, a 400 naming an unknown field, a 404, and a 429 with `Retry-After` on demand. Every response it returns is validated against the vendored schema, so the fake can't drift from the contract unnoticed. One scenario test drives the client through every operation an integrator uses, end to end, in milliseconds.
- **Live tests** (`just test-live <base-url>`) run the same scenario against a real Yama API, normally a local django-poc checkout with seed data, and are skipped when no base URL and key are given. They never run in CI. They're a step in every release, as the last check that the client works against the real server. The client talks to it only over HTTP, as an integrator would; nothing from django-poc is copied here.
- **No production calls** in tests, CI or live tests.
- **Fixtures** use made-up data shaped like the integrator guide's examples. Never commit real API responses: they hold customer phone numbers and names.
- **Coverage** is there to find untested code (`just cov`), not a gate. There is no floor.

## CI and Branch Policy

On every pull request and every push to `main`, GitHub Actions runs `just check` (ruff, mypy, pytest, and a build whose wheel is imported in a clean environment) on every supported Python version, on Linux only. The package and its dependencies are pure Python, so other operating systems add minutes but catch little.

A separate daily job runs `just schema-diff` and fails when the published schema no longer matches the vendored copy. It doesn't run on PRs, so an API release never blocks unrelated work.

Branches: feature branches off `main`, squash-merged through PRs with `Closes #<n>`. `main` is always releasable.

## Release Process

- **Versioning:** SemVer, independent of the app's CalVer releases. Before 1.0, minor versions may break the interface, and every break is called out in the changelog. From 1.0, breaks need a major version.
- **Mapping to the API:** each release targets one API version (`v2`). A future `/api/v3/` gets new client code side by side or a major release, decided when v3 exists.
- **Changelog:** each user-facing PR carries a `## Changelog` section of 1-3 bullets, each tagged `[Added]`, `[Changed]`, `[Fixed]`, `[Security]` or `[Removed]`. An untagged bullet counts as `[Changed]`, and a bullet reading "No user-facing change" is skipped. Leave the section out of housekeeping PRs (CI, refactors, docs) entirely. A `[Changed]` bullet that breaks existing callers starts with `Breaking:`. At release, the bullets from PRs merged since the last tag are de-duplicated, grouped by tag and written into `CHANGELOG.md` under a `## X.Y.Z - YYYY-MM-DD` heading below `## Unreleased`; the same section becomes the GitHub Release notes. If the section for a version already exists, collecting again leaves the file alone, so a re-run is safe.
- **Next version:** `just release` works out the bump from the changelog bullets waiting to ship. Any `[Removed]` or `Breaking:` bullet is a major bump, any `[Added]` a minor bump, and anything else a patch. Before 1.0, a major bump becomes a minor one. `just release X.Y.Z` overrides the calculation, for example to cut 1.0.0.
- **Cutting a release:** `just release [X.Y.Z]` runs from a clean, up-to-date `main`. It refuses when there are no changelog bullets to ship or the tag or branch already exists, runs `just check` and `uv build`, then creates `release/vX.Y.Z` with the version bumped in `pyproject.toml`, pushes it and opens a PR whose body previews the release notes. The PR body has no `## Changelog` heading of its own, so its bullets aren't collected twice.
- **Dry run:** `just release --dry-run [X.Y.Z]` runs every check, the tests and the build, prints the version it would choose, the reason for the bump and the release notes, and stops. It creates no branch, commit, tag or PR.
- **Publishing:** merging a `release/vX.Y.Z` PR runs a workflow that tags `vX.Y.Z` on the merge commit, writes the section into `CHANGELOG.md`, builds the sdist and wheel, publishes them to PyPI through trusted publishing (no stored PyPI token) and creates the GitHub Release. Nothing publishes from a developer's machine.

## Security

- The repo is public: no keys, customer data, internal hostnames or django-poc internals in code, tests, issues or docs.
- Dependabot keeps dependencies and GitHub Actions up to date with one grouped PR each a month, and `SECURITY.md` explains how to report a vulnerability privately.
- Release artifacts get PyPI's attestations through trusted publishing.
