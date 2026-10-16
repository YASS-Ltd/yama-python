import pytest


@pytest.fixture(autouse=True)
def _no_base_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a developer's `YAMA_API_BASE_URL` from redirecting the tests' requests."""
    monkeypatch.delenv("YAMA_API_BASE_URL", raising=False)
