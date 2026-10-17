import pickle

import httpx
import pytest

from tests.mock import make_client, recorder, respond
from yama import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    GoneError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    UnprocessableEntityError,
    Yama,
    YamaError,
)


@pytest.mark.parametrize(
    ("status", "error_class"),
    [
        (400, BadRequestError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (405, APIStatusError),
        (409, ConflictError),
        (410, GoneError),
        (415, APIStatusError),
        (422, UnprocessableEntityError),
        (429, RateLimitError),
        (500, ServerError),
        (503, ServerError),
    ],
)
def test_err_1_raises_the_class_for_each_status(
    status: int, error_class: type[APIStatusError]
) -> None:
    body = {"detail": "Something went wrong."}
    client, _ = make_client(recorder(respond(status, body))[0], max_retries=0)
    with pytest.raises(error_class) as caught:
        client._request("GET", "codes/", params={"code": "1234"})
    error = caught.value
    assert type(error) is error_class
    assert error.status_code == status
    assert error.detail == "Something went wrong."
    assert error.body == body
    assert error.api_version == "v2"
    assert error.method == "GET"
    assert error.path == "/api/v2/codes/"
    assert str(error) == f"{status} Something went wrong. (GET /api/v2/codes/)"


def test_err_1_handles_a_body_that_is_not_json() -> None:
    response = httpx.Response(502, text="<html>Bad gateway</html>")
    client, _ = make_client(recorder(response)[0], max_retries=0)
    with pytest.raises(ServerError) as caught:
        client._request("GET", "codes/")
    assert caught.value.body == "<html>Bad gateway</html>"
    assert caught.value.api_version is None
    assert str(caught.value) == "502 Bad Gateway (GET /api/v2/codes/)"


def test_err_2_exposes_the_400_error_map() -> None:
    body = {
        "code": ["Access code already exists for this unit."],
        "non_field_errors": ["Something about the whole request."],
    }
    client, _ = make_client(recorder(respond(400, body))[0])
    with pytest.raises(BadRequestError) as caught:
        client._request("POST", "codes/", json={})
    assert caught.value.errors == body
    assert str(caught.value) == (
        "400 code: Access code already exists for this unit.; "
        "non_field_errors: Something about the whole request. (POST /api/v2/codes/)"
    )


def test_err_3_raises_connection_error_after_retries() -> None:
    handler, requests = recorder(httpx.ConnectError("refused"))
    client, _ = make_client(handler)
    with pytest.raises(APIConnectionError) as caught:
        client._request("GET", "codes/")
    assert type(caught.value) is APIConnectionError
    assert len(requests) == 3


def test_err_3_raises_timeout_error_when_the_last_attempt_timed_out() -> None:
    handler, requests = recorder(httpx.ConnectError("refused"), httpx.ReadTimeout("slow"))
    client, _ = make_client(handler)
    with pytest.raises(APITimeoutError):
        client._request("GET", "codes/")
    assert len(requests) == 3


def test_err_3_raises_connection_error_when_only_an_earlier_attempt_timed_out() -> None:
    handler, _ = recorder(httpx.ReadTimeout("slow"), httpx.ConnectError("refused"))
    client, _ = make_client(handler)
    with pytest.raises(APIConnectionError) as caught:
        client._request("GET", "codes/")
    assert type(caught.value) is APIConnectionError


def test_err_4_raises_yama_errors_for_failed_calls() -> None:
    for error_class in (APIConnectionError, APIStatusError):
        assert issubclass(error_class, YamaError)
    response = httpx.Response(200, text="not json")
    client, _ = make_client(recorder(response)[0])
    with pytest.raises(YamaError, match="JSON"):
        client._request("GET", "codes/")


@pytest.mark.parametrize(
    ("kwargs", "error_class"),
    [
        ({"api_key": 123}, TypeError),
        ({"max_retries": -1}, ValueError),
        ({"max_retries": 1.5}, TypeError),
        ({"timeout": "30"}, TypeError),
        ({"base_url": "app.yamasystems.com"}, ValueError),
    ],
)
def test_err_4_raises_type_or_value_error_for_invalid_arguments(
    kwargs: dict[str, object], error_class: type[Exception]
) -> None:
    with pytest.raises(error_class):
        Yama(**{"api_key": "k", **kwargs})  # type: ignore[arg-type]


def test_err_6_carries_the_request_id() -> None:
    response = respond(404, {"detail": "Not found."}, {"Request-Id": "req_3f9c"})
    client, _ = make_client(recorder(response)[0])
    with pytest.raises(NotFoundError) as caught:
        client._request("GET", "codes/")
    assert caught.value.request_id == "req_3f9c"
    assert str(caught.value) == "404 Not found. (GET /api/v2/codes/, Request-Id req_3f9c)"


def test_err_6_carries_the_last_responses_request_id_after_retries() -> None:
    handler, _ = recorder(
        respond(503, headers={"Request-Id": "req_first"}),
        respond(503, headers={"Request-Id": "req_last"}),
    )
    client, _ = make_client(handler, max_retries=1)
    with pytest.raises(ServerError) as caught:
        client._request("GET", "codes/")
    assert caught.value.request_id == "req_last"


def test_err_6_has_no_request_id_when_the_response_has_none() -> None:
    client, _ = make_client(recorder(respond(404, {"detail": "Not found."}))[0])
    with pytest.raises(NotFoundError) as caught:
        client._request("GET", "codes/")
    assert caught.value.request_id is None
    assert str(caught.value) == "404 Not found. (GET /api/v2/codes/)"


def keyed(error: YamaError) -> YamaError:
    error.idempotency_key = "job-17"
    return error


@pytest.mark.parametrize(
    "error",
    [
        YamaError("No API key."),
        APIConnectionError("Connection failed: ConnectError"),
        APITimeoutError("Request timed out: ReadTimeout"),
        APIStatusError(405, "Not allowed.", {"detail": "Not allowed."}, "v2", "PUT", "/api/v2/x/"),
        NotFoundError(404, "Not found.", {"detail": "Not found."}, "v2", "GET", "/api/v2/x/"),
        BadRequestError(400, "code: Taken.", {"code": ["Taken."]}, "v2", "POST", "/api/v2/x/"),
        RateLimitError(429, "Slow down.", {}, "v2", "GET", "/api/v2/x/", retry_after=12),
        ServerError(502, "Bad Gateway", "<html></html>", None, "GET", "/api/v2/x/"),
        keyed(ConflictError(409, "In progress.", {}, "v2", "POST", "/api/v2/codes/")),
        keyed(APITimeoutError("Request timed out: ReadTimeout")),
        NotFoundError(404, "Not found.", {}, "v2", "GET", "/api/v2/x/", "req_3f9c"),
        RateLimitError(429, "Slow down.", {}, "v2", "GET", "/api/v2/x/", "req_3f9c", 12),
    ],
)
def test_err_5_survives_a_pickle_round_trip(error: YamaError) -> None:
    copy = pickle.loads(pickle.dumps(error))
    assert type(copy) is type(error)
    assert str(copy) == str(error)
    assert vars(copy) == vars(error)


def raise_for_status(response: httpx.Response) -> None:
    response.raise_for_status()


class UnreadTransport(httpx.BaseTransport):
    """Answers 404 with a body that is only read if the client gets that far."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, stream=httpx.ByteStream(b'{"detail": "Not found."}'))


@pytest.mark.parametrize(
    ("transport", "detail"),
    [
        (httpx.MockTransport(lambda _: respond(404, {"detail": "Not found."})), "Not found."),
        (UnreadTransport(), "Not Found"),
    ],
)
def test_err_1_raises_the_status_error_when_the_callers_client_raises_for_status(
    transport: httpx.BaseTransport, detail: str
) -> None:
    hooked = httpx.Client(transport=transport, event_hooks={"response": [raise_for_status]})
    client = Yama("test-key", http_client=hooked)
    with pytest.raises(NotFoundError) as caught:
        client._request("GET", "codes/")
    assert caught.value.detail == detail
