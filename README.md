<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/yama-logo-dark.svg">
    <img src=".github/assets/yama-logo-light.svg" alt="Yama" width="280">
  </picture>
</p>

<p align="center">
  <em>The official Python client for the Yama access-control API.</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/yama/"><img src="https://img.shields.io/pypi/v/yama?style=flat-square" alt="PyPI"></a>
  <a href="https://pypi.org/project/yama/"><img src="https://img.shields.io/pypi/pyversions/yama?style=flat-square" alt="Python versions"></a>
  <a href="https://github.com/YASS-Ltd/yama-python/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/YASS-Ltd/yama-python/ci.yml?branch=main&style=flat-square&label=CI" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-MIT-21212B?style=flat-square" alt="MIT licence"></a>
</p>

---

**Docs:** <https://yass-ltd.github.io/yama-python/> · **REST API:** <https://app.yamasystems.com/api/v2/docs/> · **Source:** <https://github.com/YASS-Ltd/yama-python>

---

Manage a building's access codes and read its call log from Python. The client handles auth, pagination, retries and errors, and gives you typed objects back.

> [!NOTE]
> **In development.** Nothing is on PyPI yet. Until then, use the [REST API](https://app.yamasystems.com/api/v2/docs/) directly.

## Install

```console
uv add yama        # or: pip install yama
```

<!-- --8<-- [start:quick-start] -->
## Quick start

```python
from datetime import datetime, timezone

from yama import Yama

client = Yama()  # reads YAMA_API_KEY

for code in client.codes.list():
    print(code.name, code.expires_at)

start = datetime(2026, 10, 1, tzinfo=timezone.utc)
end = datetime(2026, 11, 1, tzinfo=timezone.utc)  # exclusive: all of October
for call in client.calls.list(start=start, end=end):
    print(call.started_at, call.result)
```

Create a key in the Yama portal under **Settings › API keys**. Keep it in an environment variable or a secret manager, never in source control.
<!-- --8<-- [end:quick-start] -->

## What you get

- **Typed:** Pydantic models with UTC-aware datetimes, so your editor autocompletes.
- **Every page:** iterating a list follows `next` to the end, and the call log is de-duplicated.
- **Safe retries:** on 429 (honouring `Retry-After`) and failures to connect for every call, and on 5xx and other network errors for every call that's safe to repeat: reads, replaces, updates, deletes, and creates, which carry an `Idempotency-Key` so a code is never created twice.
- **Clear errors:** one exception class per kind of failure, listed in the [docs](https://yass-ltd.github.io/yama-python/).
- **Forward-compatible:** new fields and enum values from the API don't break your code.
- **Small:** two dependencies, httpx and Pydantic. Python 3.10 and newer.

## Versioning

SemVer, targeting version 2 of the Yama API (`/api/v2/`). See the [changelog](CHANGELOG.md).

## Contributing

Bug reports and ideas are welcome in [issues](https://github.com/YASS-Ltd/yama-python/issues). Development uses [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/): `just check` runs everything CI does. Report security issues privately; see [SECURITY.md](SECURITY.md).

## Licence

[MIT](LICENSE) © Yama Access Software Systems Ltd.
