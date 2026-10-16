import json
import logging
import sys
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
    monkeypatch.delenv("YAMA_API_BASE_URL", raising=False)


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


def test_cfg_5_closes_only_its_own_connection() -> None:
    client = Yama(KEY)
    client.close()
    assert client._http.is_closed


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


# Package


def test_pkg_4_is_safe_to_share_between_threads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return respond(body={"path": request.url.path})

    client, _ = make_client(handler)
    paths = [f"codes/{n}/" for n in range(200)]
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda p: client._request("GET", p), paths))
    assert [r["path"] for r in results] == [f"/api/v2/{p}" for p in paths]
