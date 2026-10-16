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

The site stays small: a home page (install and quick start, shared with the README), one guide (configuration, pagination, errors, retries and idempotency, versioning), a reference generated from docstrings, and the changelog. It documents the Python client only. The REST API's own docs stay in Scalar at `/api/v2/docs/`, and the site links to them rather than repeating them. The README stays the front door: short, with the quick start and a link to the site.

httpx is chosen over requests because it offers sync and async clients with one interface, so async can be added later without a rewrite. It also has timeouts on by default and is well typed.

The `justfile` is the single entry point for repeated commands: `just test`, `just lint`, `just check` (everything CI runs), `just schema-pull` and `just release`. CI calls the same recipes, so a green `just check` locally means a green CI run. Recipes wrap uv; they never replace it.

## Supported Python Versions

- `requires-python = ">=3.10"`, never with an upper bound. CI tests every supported version, including the newest CPython release.
- A version is dropped only after it is out of upstream support **and** either the default Python on the oldest supported Ubuntu LTS has moved past it or a runtime dependency (httpx, Pydantic) has dropped it.
- Drops happen in a minor release and are announced in the changelog. pip honours `requires-python`, so integrators on a dropped version keep getting the last release that supports it.
- Review this at each Ubuntu LTS end-of-standard-support date and each new CPython release. 3.10 is expected to go around April 2027.

## Library Principles

The rules for what the client exposes and what it hides. They follow the conventions of well-liked Python API clients (httpx, Stripe, OpenAI) rather than inventing new ones; an integrator who has used one of those should feel at home. Each rule earns its place by preventing a known mistake. Add a rule only when a real decision needs it, and give its reason.

### What to abstract

1. **Hide the mechanics, mirror the domain.** The client takes over everything an integrator would otherwise hand-write: auth, URLs, JSON, pagination, retries, timeouts and error parsing. It invents nothing on top of the API: resources, fields and filters keep the API's names and meanings, so the API docs map one-to-one onto the client. No caching, sync helpers or convenience workflows.
2. **Correct by default.** Iterating a list follows `next` to the end and de-duplicates the call log. Retries happen only where they can't do harm. Calls time out. The integrator shouldn't need to read the docs to avoid a known trap.
3. **One way to do each thing.** One method per API operation, one input style (Pydantic request models), no aliases. A second way to do something is a second thing to document, test and keep compatible.
4. **Escape hatches, not options.** Instead of a setting for every case, offer a few general outlets: pass your own `httpx.Client`, read unknown response fields from the model, drop to `pages()` when you need `count`. Each new constructor argument has to be one most integrators need.

### The public surface

5. **Small and explicit.** The public interface is what `yama/__init__.py` and `yama.models` export, as listed in `design/interface.md`. Everything else is underscore-private. Adding to the surface is easy; removing from it is a breaking change, so add reluctantly.
6. **Typed and documented.** Every public name has type hints and a docstring, mypy runs in strict mode, and the package ships `py.typed`. Editor autocompletion should be enough to use the client.
7. **Our errors, not our dependencies'.** Every failure the client raises is a `YamaError`; httpx and Pydantic exceptions never leak out of a call. The exception is programmer error, such as a wrong argument type or `start` without `end`, which raises the usual `TypeError` or `ValueError`.

### Compatibility

8. **Tolerant reader, strict writer.** Responses accept unknown fields and pass unknown enum values through as strings, since v2 grows additively. Requests reject unknown fields locally. The client checks types and required fields, but leaves value rules (lengths, formats, uniqueness) to the API, so a rule the API relaxes doesn't need a client release.
9. **Deprecate before removing.** Before 1.0, a minor release may break the interface, and the changelog says how to migrate. From 1.0, a removal or rename first warns with `DeprecationWarning` for at least one minor release.
10. **Wide dependency ranges.** Runtime dependencies are httpx and Pydantic only, each with the lowest floor the code allows and no upper bound. Every extra or pinned dependency is a version conflict waiting in someone else's project.

### Behaviour

11. **No surprises.** Importing `yama` does nothing but define things: no network, no logging configuration, no printing, no warnings. There is no global client and no hidden state. Configuration comes from arguments, with only `YAMA_API_KEY` and `YAMA_API_BASE_URL` as environment fallbacks. A `Yama` instance is safe to share between threads.
12. **Keys stay secret.** The key appears in no `repr`, log line, exception message or URL.
13. **Identify the client.** Requests send `User-Agent: yama-python/<version> python/<version>`, so the server's logs show which client versions are in use.

### The schema is the contract

The published OpenAPI schema is vendored as `tests/fixtures/openapi.yaml`. The client and its models are hand-written, and contract tests check them against the vendored copy. A daily CI job flags when the published schema drifts from it; updating the copy, and the client to match, is a deliberate change.

## Yama's Domain

Yama is moving from `getyama.ca` to `yamasystems.com` now, while no integration depends on the old host. The client targets the new host from its first release and never the old one:

- `DEFAULT_BASE_URL` is `https://app.yamasystems.com` (host to be confirmed) and is the only place in the code that names the domain. `YAMA_API_BASE_URL` and the `base_url` argument override it.
- 0.1.0 isn't released until the API answers on the new host. Until then, development and live tests point `YAMA_API_BASE_URL` at the current host, and the vendored schema comes from it.
- `pyproject.toml` already points at the new domain, since its URLs only show on PyPI. When the new host is live, one change switches the `justfile`'s schema URL, re-vendors the schema, and updates the links people can follow today: the README, the issue template config and `AGENTS.md`.
- The old host can redirect or be retired on the API's own schedule; no released client calls it.

## Requirements

Requirements live in the PRD, written in [EARS](https://alistairmavin.com/ears/) form with an ID each (`RTY-2`). The PRD says what the client must do, and `design/interface.md` names the pieces; neither says how the work is split, which is up to the issues.

- A requirement describes behaviour an integrator can observe. Implementation choices, such as backoff timings or module layout, aren't requirements; they live in the interface spec's defaults, the code and its docstrings.
- Use the five EARS patterns: *The client shall…*, *When <trigger>, the client shall…*, *While <state>, the client shall…*, *If <condition>, then the client shall…*, *Where <feature>, the client shall…*. One sentence, one behaviour.
- Behaviour is written down once. If a requirement and another doc disagree, the requirement wins; fix the other doc.
- IDs are never reused. A dropped requirement is struck through, not renumbered.

## Testing Strategy

- **Tests first:** write a failing test, then the minimum code to pass, then refactor.
- **Tests trace requirements.** Each requirement has at least one test whose name starts with its ID, such as `test_rty_2_waits_for_retry_after`, so `grep -ri rty_2` finds the requirement's tests.
- **Unit tests** mock single HTTP exchanges with respx. They cover each operation's request (method, path, query, body), response parsing, pagination edge cases (empty list, one page, many pages, a `next` that repeats a call), the error mapping for each status, and retry behaviour, using a fake clock so tests don't sleep.
- **Contract tests** check the client against the vendored schema: every operation in the schema has a client method, and every request the client builds validates against the schema.
- **An in-memory fake API** built on `httpx.MockTransport`, with no server or process. It holds a few made-up buildings, units, contacts, codes and calls in dicts and implements the real behaviours: `limit`/`offset` with `next` links, code create (honouring `Idempotency-Key`), update and delete, a 400 for a code that already exists on its unit, a 400 naming an unknown field, a 404, and a 429 with `Retry-After` on demand. Every response it returns is validated against the vendored schema, so the fake can't drift from the contract unnoticed. One scenario test drives the client through every operation an integrator uses, end to end, in milliseconds.
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
