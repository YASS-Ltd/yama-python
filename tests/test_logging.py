import logging

import httpx
import pytest

import yama
from tests.mock import KEY, make_client, recorder, respond
from yama import YamaError


@pytest.fixture
def log(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG, logger="yama")
    return caplog


def test_log_1_logs_one_debug_record_per_attempt(log: pytest.LogCaptureFixture) -> None:
    handler, _ = recorder(respond(503), respond())
    client, _ = make_client(handler)
    client._request("GET", "codes/", params={"unit": "x"})
    debug = [r for r in log.records if r.levelno == logging.DEBUG]
    assert [r.name for r in debug] == ["yama", "yama"]
    for record, status, attempt in zip(debug, [503, 200], [1, 2], strict=True):
        message = record.getMessage()
        for fact in ("GET", "/api/v2/codes/", str(status), f"attempt {attempt}"):
            assert fact in message
        assert record.yama_method == "GET"  # type: ignore[attr-defined]
        assert record.yama_path == "/api/v2/codes/"  # type: ignore[attr-defined]
        assert record.yama_status == status  # type: ignore[attr-defined]
        assert record.yama_attempt == attempt  # type: ignore[attr-defined]
        assert record.yama_elapsed >= 0  # type: ignore[attr-defined]
        assert f"{record.yama_elapsed:.3f}s" in message  # type: ignore[attr-defined]


def test_log_1_logs_an_attempt_that_failed_at_the_network_level(
    log: pytest.LogCaptureFixture,
) -> None:
    handler, _ = recorder(httpx.ConnectError("refused"), respond())
    client, _ = make_client(handler)
    client._request("GET", "codes/")
    first = next(r for r in log.records if r.levelno == logging.DEBUG)
    assert first.yama_status is None  # type: ignore[attr-defined]
    assert "ConnectError" in first.getMessage()


def test_log_2_logs_one_info_record_per_retry(log: pytest.LogCaptureFixture) -> None:
    handler, _ = recorder(respond(429, headers={"Retry-After": "3"}), respond())
    client, _ = make_client(handler)
    client._request("GET", "codes/")
    info = [r for r in log.records if r.levelno == logging.INFO]
    assert len(info) == 1
    record = info[0]
    assert record.yama_reason == "429"  # type: ignore[attr-defined]
    assert record.yama_wait == 3  # type: ignore[attr-defined]
    assert record.yama_attempt == 2  # type: ignore[attr-defined]
    message = record.getMessage()
    for fact in ("429", "3.00s", "attempt 2", "GET", "/api/v2/codes/"):
        assert fact in message


def test_log_3_keeps_secrets_and_payloads_out_and_logs_nothing_above_info(
    log: pytest.LogCaptureFixture,
) -> None:
    secrets = [
        KEY,
        "Bearer",
        "Authorization",
        "4321",
        "Cleaner",
        "?",
        "code=",
        f"yama-python/{yama.__version__}",
    ]
    handler, _ = recorder(
        httpx.ReadTimeout("slow"),
        respond(503, {"detail": "Down: 4321 Cleaner"}),
        respond(400, {"code": ["4321 already exists."]}),
    )
    client, _ = make_client(handler)
    with pytest.raises(YamaError):
        client._request(
            "POST",
            "codes/",
            params={"code": "4321"},
            json={"code": "4321", "name": "Cleaner"},
            headers={"Idempotency-Key": "4321"},
        )
    assert len(log.records) == 5  # three attempts, two retries
    assert all(r.levelno < logging.WARNING for r in log.records)
    for record in log.records:
        text = record.getMessage() + repr(vars(record))
        assert not [s for s in secrets if s in text], text
