# Logging

The client logs through the standard `logging` module, to the `yama` logger only. It sets no handlers, levels or formats, so your logging setup, structlog, OpenTelemetry or Sentry decides where its records go.

| Level | Record | `extra` fields |
|---|---|---|
| DEBUG | One per HTTP attempt: method, path, status, elapsed time and attempt number. | `yama_method`, `yama_path`, `yama_attempt`, `yama_status` (None after a network failure), `yama_outcome` (the status or the error's name), `yama_elapsed` (seconds), `yama_request_id` (the response's `Request-Id`; None when there's none) |
| INFO | One per retry: the reason, the wait and the number of the attempt about to start. | `yama_method`, `yama_path`, `yama_attempt` (the attempt about to start), `yama_reason`, `yama_wait` (seconds) |

Nothing is logged at WARNING or above: a failure raises instead. Each fact is in the message and also in the record's `extra` fields, for structured logging. Records never hold the API key, headers, request or response bodies, or query strings, which can hold access-code digits and phone numbers.

To see every request while debugging:

```python
import logging

logging.getLogger("yama").setLevel(logging.DEBUG)
```

## httpx logs full URLs

!!! warning "Raise the `httpx` logger to WARNING"

    httpx, which the client sends requests with, logs every request at INFO through its own shared `httpx` logger, with the full URL, query string included. Query strings can hold access codes and phone numbers, such as `codes.list(code="1234")` or `contacts.list(number=...)`. If your application logs at INFO and its logs leave the machine, turn those records off:

    ```python
    import logging

    logging.getLogger("httpx").setLevel(logging.WARNING)
    ```

    The `httpx` logger is shared by every library that uses httpx, so the client leaves this choice to you.
