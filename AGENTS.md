# yama-python Repository Guidelines

This repo is the official Python client for the Yama REST API. It is **public**: everything committed here, including this file, issues and pull requests, is visible to anyone.

Yama is a cloud-based SaaS platform for managing access control (intercom/dialer call routing, access codes) in condos and apartment buildings.

**Status:** pre-release. No client code yet. Scope and design are in `docs/prd-v0.1.md` and `docs/engineering-foundations.md`.

## Product Terminology

- **Account Holder**: the customer entity (building owner, condominium corporation, or property manager) that contracts with Yama and creates API keys.
- **Authorised Users**: staff acting on behalf of an Account Holder in the web portal/API.
- **Residents**: people living in a building configured by an Account Holder.
- **Visitors**: guests/contractors/delivery people using a building intercom that places calls through the Service.

## Relationship to the API (django-poc)

The API is served by the private sister repo `../django-poc`, which is the source of truth for the API contract.

- **The schema is the contract.** The public OpenAPI schema is at `https://app.getyama.ca/api/v2/schema/`, and the docs are at `/api/v2/docs/`. Build against the schema, not against django-poc's internals.
- Read-only references in `../django-poc` when it is checked out: `docs/api/getting-started.md` (integrator guide), `docs/api/reference.md`, `docs/api-versioning.md`, `docs/api-keys.md`.
- **Never edit files in `../django-poc` from a session in this repo.** If the client needs an API change, write it up and hand it off as a django-poc task.
- **Never copy private material into this repo**: no django-poc code, internal hostnames, deploy or ops details, customer names or customer data.

API conventions the client must handle:

- Base path `/api/v2/`. Auth is an API key sent as `Authorization: Bearer <key>`; never put a key in a URL.
- JSON only. Request bodies are strict: a read-only or unknown field is a `400` naming it. An undocumented query parameter is also a `400`.
- Lists use `limit`/`offset` pagination (`count`, `next`, `previous`, `results`); follow `next` until it is `null`. The call log is filtered by inclusive UTC `start`/`end` dates (default: the last 30 days), and new calls can shift pages, so de-duplicate by `uuid`.
- Datetimes are UTC ISO 8601.
- Retry only on 5xx, 429 (honour `Retry-After`) and network errors, with backoff. Every response carries an `API-Version` header.
- Within v2, changes are additive. The client must tolerate new fields in responses.

## Settled choices

- Its own public repo (`YASS-Ltd/yama-python`), with work tracked in GitHub Issues and Projects. Versioned with SemVer and published to PyPI as `yama` (import name `yama`), independently of the app's CalVer releases.
- MIT licence.
- A hand-written client whose interface takes and returns Pydantic v2 models.
- Enum values the client doesn't know pass through as strings.
- Default base URL `https://app.getyama.ca`, overridden by the `base_url` argument or `YAMA_API_BASE_URL`.
- Python 3.10 and newer (policy in `docs/engineering-foundations.md`).
- A copy of the OpenAPI schema lives in this repo as a test fixture, and CI flags drift from the published schema.

## Development Workflow

- Use [uv](https://docs.astral.sh/uv/) for every Python command, as in django-poc.
- Use the [just](https://just.systems/man/en/) recipes when one exists (`just --list`); `just check` runs what CI runs. Releases go through `just release` (try `just release --dry-run` first) and publish from CI, never from a local machine. The process is in `docs/engineering-foundations.md`.
- **Tests first**: write a failing test, implement the minimum change, refactor while green.
- Tests must not call the production API. Use recorded or mocked HTTP responses, plus contract checks against the schema.
- Never commit API keys, even expired ones, or real responses containing customer data.

## Git

- `main` is the default branch. Work happens on `feature/...` branches and is squash-merged through PRs.
- Every user-facing PR includes a `## Changelog` section with 1-3 bullets tagged `[Added]`/`[Changed]`/`[Fixed]`/`[Security]`/`[Removed]` (untagged counts as `[Changed]`). Start a `[Changed]` bullet with `Breaking:` when it breaks existing callers, because the bullets set the next version number. Leave the section out of housekeeping PRs (CI, refactors, docs). Leave out AI-tool attribution in Changelog bullets.

## Issues and Projects

Work is tracked in GitHub Issues on `YASS-Ltd/yama-python` and planned on a GitHub Project board. Issues are public, so write them for outside readers. Use the `gh` CLI:

- Find work: `gh issue list`, `gh issue view <n> --comments`.
- New work: `gh issue create` using the templates in `.github/ISSUE_TEMPLATE/`. A task issue has **Why**, **Acceptance criteria** (a checkbox list) and, once planned, **Implementation plan** sections.
- Planning: write the plan into the issue body (`gh issue edit <n> --body-file ...`) and add a `model:haiku-ok`, `model:sonnet-recommended` or `model:opus-recommended` label saying which model tier should implement it, with a sentence on why.
- Progress: tick acceptance criteria in the issue as they're met, and put `Closes #<n>` in the PR so merging closes the issue.
- Triage: label new outside issues (`bug`, `enhancement`, `question`) and add them to the Project, or reply and close them.
- Leave out AI-tool attribution in issue bodies and comments.

API work stays in django-poc's backlog (`TASK-n`). Refer to it as "django-poc TASK-n" and don't duplicate the detail.

## Decisions and personal information

This repo keeps no decision records. Decisions about the client, with who made them and why, are recorded privately in django-poc's backlog. Here, state only the resulting rule: in `docs/engineering-foundations.md` for ongoing rules, or in the PRD for scope.

Never put personal information in this repo, its issues or its PRs: no names of Yama staff or customers, no emails or phone numbers, nothing about who decided what. Credit outside contributors only through their own commits and PRs.
