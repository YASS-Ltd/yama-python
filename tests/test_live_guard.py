import pytest

from tests.test_live import is_local


@pytest.mark.parametrize(
    "url",
    ["http://localhost:8000", "http://127.0.0.1:8000", "http://[::1]:8000", "http://LOCALHOST"],
)
def test_live_guard_allows_a_server_on_this_machine(url: str) -> None:
    assert is_local(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://app.yamasystems.com",
        "https://app.yamasystems.com.",
        "http://localhost.",
        "http://localhost.example",
        "https://192.0.2.10",
        "http://[::ffff:127.0.0.1]",
        "http://web:8000",
        "http://localhost@app.yamasystems.com",
        "http://localhost:abc",
        "",
    ],
)
def test_live_guard_refuses_any_other_host(url: str) -> None:
    assert not is_local(url)
