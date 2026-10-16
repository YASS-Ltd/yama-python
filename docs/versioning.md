# Versioning

## The client

The client follows [Semantic Versioning](https://semver.org/). Before 1.0, a minor release (0.1 to 0.2) may change the interface, and the [changelog](https://github.com/YASS-Ltd/yama-python/releases) says what changed and how to update your code; patch releases never break it. Pin to a minor version until then:

```console
uv add "yama>=0.1,<0.2"
```

From 1.0, a breaking change needs a major release, and anything to be removed first raises a `DeprecationWarning` for at least one minor release.

## The API

Each release targets one version of the Yama API, currently version 2 (`/api/v2/`). Version 2 grows by adding fields, filters and enum values, and the client is built to take them in its stride: unknown fields stay readable on the model, and unknown enum values come back as strings (see [Models](models.md)). An error's `api_version` is the version the API answered with.

## Python

The client supports Python 3.10 and newer, and is tested on every supported version. An old version is dropped only in a minor release, announced in the changelog, some time after it reaches its end of life.
