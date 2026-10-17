import socket
from typing import Any

import pytest

from tests.test_live import is_production


def fake_dns(monkeypatch: pytest.MonkeyPatch, table: dict[str, str]) -> None:
    def getaddrinfo(host: str, *_: Any, **__: Any) -> list[Any]:
        if host not in table:
            raise socket.gaierror(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (table[host], 443))]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


@pytest.mark.parametrize(
    "url",
    [
        "https://app.yamasystems.com",
        "https://APP.yamasystems.com/",
        "https://app.yamasystems.com./",
        "https://192.0.2.10",
        "https://alias.example",
    ],
)
def test_live_guard_refuses_production_by_name_or_address(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    fake_dns(
        monkeypatch,
        {
            "app.yamasystems.com": "192.0.2.10",
            "192.0.2.10": "192.0.2.10",
            "alias.example": "192.0.2.10",
        },
    )
    assert is_production(url)


@pytest.mark.parametrize("url", ["http://localhost:8000", "https://staging.example"])
def test_live_guard_allows_other_servers(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    fake_dns(
        monkeypatch,
        {
            "app.yamasystems.com": "192.0.2.10",
            "localhost": "127.0.0.1",
            "staging.example": "192.0.2.20",
        },
    )
    assert not is_production(url)
