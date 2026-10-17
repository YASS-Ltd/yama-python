import json
import logging
import sys
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
import respx

import yama
from tests.mock import KEY, make_client, recorder, respond
from yama import DEFAULT_BASE_URL, Yama, YamaError


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YAMA_API_KEY", raising=False)


def _transport_client(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


# Configuration


def test_cfg_1_uses_the_api_key_argument_over_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YAMA_API_KEY", "from-env")
    handler, requests = recorder(respond())
    client, _ = make_client(handler, api_key="from-arg")
    client._request("GET", "api-key/")
    assert requests[0].headers["Authorization"] == "Bearer from-arg"


def test_cfg_1_falls_back_to_the_environment_only_when_the_key_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YAMA_API_KEY", "from-env")
    handler, requests = recorder(respond())
    Yama(http_client=_transport_client(handler))._request("GET", "api-key/")
    assert requests[0].headers["Authorization"] == "Bearer from-env"


@pytest.mark.parametrize("key", [None, ""])
def test_cfg_2_rejects_a_missing_key_argument_even_with_the_environment_set(
    monkeypatch: pytest.MonkeyPatch, key: str | None
) -> None:
    monkeypatch.setenv("YAMA_API_KEY", "from-env")
    handler, requests = recorder(respond())
    with pytest.raises(YamaError, match="API key"):
        Yama(key, http_client=_transport_client(handler))
    assert requests == []


@pytest.mark.parametrize("env", [None, ""])
def test_cfg_2_rejects_an_omitted_key_without_the_environment(
    monkeypatch: pytest.MonkeyPatch, env: str | None
) -> None:
    if env is not None:
        monkeypatch.setenv("YAMA_API_KEY", env)
    handler, requests = recorder(respond())
    with pytest.raises(YamaError, match="YAMA_API_KEY"):
        Yama(http_client=_transport_client(handler))
    assert requests == []


def test_cfg_3_sends_to_the_base_url_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YAMA_API_BASE_URL", "https://env.example")
    handler, requests = recorder(respond())
    client, _ = make_client(handler, base_url="https://arg.example/")
    client._request("GET", "api-key/")
    assert str(requests[0].url) == "https://arg.example/api/v2/api-key/"


def test_cfg_3_falls_back_to_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YAMA_API_BASE_URL", "https://env.example")
    handler, requests = recorder(respond())
    client, _ = make_client(handler)
    client._request("GET", "api-key/")
    assert str(requests[0].url) == "https://env.example/api/v2/api-key/"


def test_cfg_3_defaults_to_yamas_api() -> None:
    handler, requests = recorder(respond())
    client, _ = make_client(handler)
    client._request("GET", "api-key/")
    assert DEFAULT_BASE_URL == "https://app.yamasystems.com"
    assert str(requests[0].url) == "https://app.yamasystems.com/api/v2/api-key/"


@pytest.mark.parametrize(
    ("timeout", "expected"),
    [
        (None, {"connect": 30.0, "read": 30.0, "write": 30.0, "pool": 30.0}),
        (5, {"connect": 5, "read": 5, "write": 5, "pool": 5}),
        (
            httpx.Timeout(1, connect=2, pool=3),
            {"connect": 2, "read": 1, "write": 1, "pool": 3},
        ),
    ],
)
def test_cfg_4_applies_the_timeout_to_each_phase(
    timeout: float | httpx.Timeout | None, expected: dict[str, float]
) -> None:
    handler, requests = recorder(respond())
    client, _ = make_client(handler, **({} if timeout is None else {"timeout": timeout}))
    client._request("GET", "api-key/")
    assert requests[0].extensions["timeout"] == expected


def test_cfg_4_rejects_none_pointing_to_httpx_timeout() -> None:
    with pytest.raises(TypeError, match=r"httpx\.Timeout\(None\)"):
        Yama(KEY, timeout=None)  # type: ignore[arg-type]


@respx.mock
def test_cfg_4_applies_the_timeout_on_the_clients_own_connection() -> None:
    route = respx.get(f"{DEFAULT_BASE_URL}/api/v2/api-key/").mock(return_value=respond())
    with Yama(KEY, timeout=7) as client:
        client._request("GET", "api-key/")
    assert route.calls.last.request.extensions["timeout"]["read"] == 7


def test_cfg_5_sends_through_the_callers_client_with_its_own_settings() -> None:
    handler, requests = recorder(respond())
    http = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://elsewhere.example",
        timeout=1,
        headers={"Authorization": "Bearer other", "User-Agent": "other", "X-Trace": "kept"},
    )
    with Yama(KEY, http_client=http) as client:
        client._request("GET", "api-key/")
    request = requests[0]
    assert str(request.url) == f"{DEFAULT_BASE_URL}/api/v2/api-key/"
    assert request.extensions["timeout"]["read"] == 30
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert request.headers["User-Agent"].startswith("yama-python/")
    assert request.headers["X-Trace"] == "kept"
    assert not http.is_closed


class _HeaderAuth(httpx.Auth):
    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = "Custom other"
        request.headers["X-Auth-Flow"] = "ran"
        yield request


@pytest.mark.parametrize("auth", [httpx.BasicAuth("u", "p"), _HeaderAuth()])
def test_cfg_5_sends_its_own_authorization_whatever_auth_the_callers_client_has(
    auth: httpx.Auth,
) -> None:
    handler, requests = recorder(respond())
    http = httpx.Client(transport=httpx.MockTransport(handler), auth=auth)
    with Yama(KEY, http_client=http) as client:
        client._request("GET", "api-key/")
    assert requests[0].headers["Authorization"] == f"Bearer {KEY}"
    assert "X-Auth-Flow" not in requests[0].headers  # the custom flow didn't run at all


def test_cfg_5_sends_the_key_when_the_base_url_has_credentials() -> None:
    handler, requests = recorder(respond())
    client, _ = make_client(handler, base_url="https://user:secret@api.example")
    client._request("GET", "api-key/")
    assert requests[0].headers["Authorization"] == f"Bearer {KEY}"


def test_cfg_5_closes_only_its_own_connection() -> None:
    client = Yama(KEY)
    client.close()
    assert client._http.is_closed


def test_cfg_5_rejects_an_async_client_when_constructed() -> None:
    with pytest.raises(TypeError, match="async"):
        Yama(KEY, http_client=httpx.AsyncClient())  # type: ignore[arg-type]


def test_cfg_6_with_options_returns_a_copy_sharing_the_connections() -> None:
    handler, requests = recorder(respond(503), respond(body={"ok": True}))
    client, _ = make_client(handler, base_url="https://yama.example")
    fast = client.with_options(timeout=2, max_retries=0)
    assert fast is not client
    assert fast._http is client._http
    with pytest.raises(yama.ServerError):
        fast.api_key.get()
    assert requests[0].extensions["timeout"]["read"] == 2
    assert requests[0].headers["Authorization"] == f"Bearer {KEY}"
    assert str(requests[0].url) == "https://yama.example/api/v2/api-key/"
    assert client._request("GET", "api-key/") == {"ok": True}
    assert requests[1].extensions["timeout"]["read"] == 30
    assert repr(fast) == repr(client)


def test_cfg_6_with_options_keeps_settings_not_given() -> None:
    client, _ = make_client(recorder(respond())[0], timeout=4, max_retries=5)
    assert client.with_options()._timeout == client._timeout
    assert client.with_options(timeout=1)._max_retries == 5
    assert client.with_options(max_retries=0)._timeout == httpx.Timeout(4)
    with pytest.raises(TypeError):
        client.with_options(timeout=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        client.with_options(max_retries=-1)


def test_cfg_6_closing_the_copy_leaves_the_original_open() -> None:
    handler, _ = recorder(respond())
    with Yama(KEY) as client:
        client._http = httpx.Client(transport=httpx.MockTransport(handler))
        with client.with_options(max_retries=0) as fast:
            fast._request("GET", "api-key/")
        assert not client._http.is_closed
        client._request("GET", "api-key/")
        fast_after_close = client.with_options(timeout=1)
    with pytest.raises(ValueError, match="client is closed"):
        fast_after_close._request("GET", "api-key/")


def test_err_4_raises_value_error_when_the_client_is_closed() -> None:
    handler, requests = recorder(respond())
    own = Yama(KEY)
    own.close()
    callers_http = httpx.Client(transport=httpx.MockTransport(handler))
    callers = Yama(KEY, http_client=callers_http)
    callers.close()
    closed_by_caller = Yama(KEY, http_client=httpx.Client())
    closed_by_caller._http.close()
    for client in (own, callers, closed_by_caller):
        with pytest.raises(ValueError, match="client is closed"):
            client._request("GET", "api-key/")
    assert requests == []


# Requests


def test_http_1_sends_the_key_as_a_bearer_token_on_every_request() -> None:
    handler, requests = recorder(respond(503), respond())
    client, _ = make_client(handler)
    client._request("GET", "api-key/")
    client._request("POST", "codes/", json={"code": "1234"})
    assert [r.headers["Authorization"] for r in requests] == [f"Bearer {KEY}"] * 3


def test_http_2_identifies_the_client_and_python_version() -> None:
    handler, requests = recorder(respond())
    client, _ = make_client(handler)
    client._request("GET", "api-key/")
    python = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert requests[0].headers["User-Agent"] == f"yama-python/{yama.__version__} python/{python}"


def test_http_4_sends_bodies_as_json() -> None:
    handler, requests = recorder(respond(201))
    client, _ = make_client(handler)
    body = {"unit": "dd1053d5-0a4b-4c0d-a619-6a1457d97de6", "code": "4321", "name": None}
    client._request("POST", "codes/", json=body)
    assert requests[0].headers["Content-Type"] == "application/json"
    assert json.loads(requests[0].content) == body


# Security


def test_sec_1_keeps_the_key_out_of_reprs_errors_logs_and_urls(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="yama")
    handler, requests = recorder(
        respond(401, {"detail": "Invalid API key."}), httpx.ConnectError("refused")
    )
    client, _ = make_client(handler)
    errors: list[Exception] = []
    for _ in range(2):
        try:
            client._request("GET", "codes/", params={"code": "1234"})
        except YamaError as exc:
            errors.append(exc)
    assert len(errors) == 2
    texts = [repr(client), str(client)]
    texts += [text for e in errors for text in (str(e), repr(e), repr(vars(e)))]
    texts += [repr(vars(r)) for r in caplog.records]
    texts += [str(r.url) for r in requests]
    assert not [text for text in texts if KEY in text]


def test_sec_1_strips_whitespace_around_the_key() -> None:
    handler, requests = recorder(respond())
    client, _ = make_client(handler, api_key=f" {KEY}\n")
    client._request("GET", "api-key/")
    assert requests[0].headers["Authorization"] == f"Bearer {KEY}"


@pytest.mark.parametrize("key", [f"{KEY} x", f"{KEY}\tx", f"{KEY}\u00e9", f"{KEY}\x00"])
def test_sec_1_rejects_a_key_that_is_not_printable_ascii_without_the_key_in_the_error(
    key: str,
) -> None:
    with pytest.raises(ValueError) as caught:
        Yama(key)
    assert KEY not in str(caught.value)
    assert KEY not in repr(caught.value)


@pytest.mark.parametrize(
    "failure", [httpx.ConnectError("refused"), httpx.LocalProtocolError("bad header")]
)
def test_sec_1_chains_no_httpx_error_holding_the_request(failure: Exception) -> None:
    handler, _ = recorder(failure)
    client, _ = make_client(handler, max_retries=0)
    with pytest.raises(YamaError) as caught:
        client._request("GET", "codes/")
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_sec_2_keeps_response_values_out_of_an_unreadable_response_error() -> None:
    uuid = "dd1053d5-0a4b-4c0d-a619-6a1457d97de6"
    body = {"uuid": uuid, "unit": uuid, "code": 98765, "expires_at": "soon-31337"}
    client, _ = make_client(recorder(respond(body=body))[0])
    with pytest.raises(YamaError) as caught:
        client.codes.get(uuid)
    error = caught.value
    assert error.__cause__ is None
    assert error.__context__ is None
    assert "code" in str(error)
    assert "expires_at" in str(error)
    texts = [str(error), repr(error), repr(vars(error)), repr(error.args)]
    assert not [text for text in texts if "98765" in text or "31337" in text]


# Package


def test_pkg_4_is_safe_to_share_between_threads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return respond(body={"path": request.url.path})

    client, _ = make_client(handler)
    paths = [f"codes/{n}/" for n in range(200)]
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda p: client._request("GET", p), paths))
    assert [r["path"] for r in results] == [f"/api/v2/{p}" for p in paths]
