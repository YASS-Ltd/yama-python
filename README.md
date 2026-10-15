# yama-python

The official Python client for the [Yama](https://getyama.ca) API.

Yama manages access control for condos and apartment buildings: intercom call routing, access codes and call logs. This library lets your integration manage a building's access codes and read its call log, with no hand-written HTTP, authentication, pagination or error handling.

> **Status: in development.** Nothing is published on PyPI yet. Until then, use the REST API directly: see the [API docs](https://app.getyama.ca/api/v2/docs/).

## What it will cover

| Resource | Operations |
|---|---|
| Access codes | List, create, read, update, delete, including expiry |
| Call log | Read calls by date range, across your units or for one unit or building |
| Buildings, units, contacts | Read only |
| Your API key | Read its own permissions and unit access |

## Authentication

The client authenticates with a Yama API key. The Account Holder creates keys in the Yama portal under **Settings › API keys**. Keep a key in a secret manager or an environment variable, never in source control.

## Versioning

The client follows [Semantic Versioning](https://semver.org/) and targets version 2 of the Yama API (`/api/v2/`). Each release states which API version it supports.

## Contributing

Found a bug or want a feature? [Open an issue](https://github.com/YASS-Ltd/yama-python/issues). Development uses [uv](https://docs.astral.sh/uv/).

## Licence

[MIT](LICENSE), © Yama Access Software Systems Ltd.
