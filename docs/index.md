# yama-python

The official Python client for the [Yama](https://yamasystems.com) access-control API. Manage a building's access codes and read its call log from Python. The client handles auth, pagination, retries and errors, and gives you typed objects back.

This site covers the Python client. The REST API itself is documented at <https://app.yamasystems.com/api/v2/docs/>, and the client's resources, fields and filters use the same names.

## Install

```console
uv add yama        # or: pip install yama
```

It needs Python 3.10 or newer, and depends only on httpx and Pydantic.

--8<-- "README.md:quick-start"

## Next steps

- [Configuration](configuration.md): keys, timeouts, retries and your own `httpx.Client`.
- [Reading and writing](reading-and-writing.md): lists, filters, the call log, and changing access codes.
- [Errors and retries](errors.md): what to catch, and how creates stay safe to repeat.
- [Logging](logging.md), [Testing](testing.md), and [web apps and background jobs](web-apps-and-jobs.md).
- [Reference](reference.md): every class and method.
