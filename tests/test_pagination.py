import httpx
import pytest
from pydantic import BaseModel

from tests.mock import make_client, recorder, respond
from yama import YamaError


class Item(BaseModel):
    n: int


def page(numbers: list[int], next_url: str | None) -> httpx.Response:
    results = [{"n": n} for n in numbers]
    return respond(body={"count": 5, "next": next_url, "previous": None, "results": results})


PAGE_2 = "https://app.yamasystems.com/api/v2/codes/?limit=2&offset=2&unit=u1"
PAGE_3 = "https://app.yamasystems.com/api/v2/codes/?limit=2&offset=4&unit=u1"


def test_pag_1_yields_every_item_on_every_page_following_next() -> None:
    handler, requests = recorder(page([1, 2], PAGE_2), page([3, 4], PAGE_3), page([5], None))
    client, _ = make_client(handler)
    items = list(client._list("codes/", Item, {"unit": "u1", "name": None}))
    assert [item.n for item in items] == [1, 2, 3, 4, 5]
    assert str(requests[0].url) == "https://app.yamasystems.com/api/v2/codes/?unit=u1&limit=500"
    assert [str(r.url) for r in requests[1:]] == [PAGE_2, PAGE_3]


@pytest.mark.parametrize(
    "next_url",
    [
        "http://app.yamasystems.com/api/v2/codes/?offset=2",
        "https://elsewhere.example/api/v2/codes/?offset=2",
        "https://app.yamasystems.com:8443/api/v2/codes/?offset=2",
        "https://app.yamasystems.com:port/api/v2/codes/?offset=2",
    ],
)
def test_pag_1_follows_next_only_on_the_configured_base_url(next_url: str) -> None:
    handler, requests = recorder(page([1, 2], next_url), page([3], None))
    client, _ = make_client(handler)
    items = client._list("codes/", Item)
    assert [next(items).n, next(items).n] == [1, 2]
    with pytest.raises(YamaError, match="base URL"):
        next(items)
    assert len(requests) == 1


def test_pag_1_yields_nothing_for_an_empty_list() -> None:
    handler, requests = recorder(page([], None))
    client, _ = make_client(handler)
    assert list(client._list("codes/", Item)) == []
    assert len(requests) == 1


def test_pag_1_raises_yama_error_for_a_malformed_page() -> None:
    handler, _ = recorder(respond(body={"results": [{"n": "not a number"}]}))
    client, _ = make_client(handler)
    with pytest.raises(YamaError):
        list(client._list("codes/", Item))


def test_pag_2_sends_nothing_until_iteration_starts() -> None:
    handler, requests = recorder(page([1], None))
    client, _ = make_client(handler)
    items = client._list("codes/", Item)
    assert requests == []
    assert next(items).n == 1
    assert len(requests) == 1


def test_pag_5_each_call_returns_a_new_iterator_from_the_first_page() -> None:
    handler, requests = recorder(page([1, 2], PAGE_2))
    client, _ = make_client(handler)
    first = client._list("codes/", Item)
    second = client._list("codes/", Item)
    assert first is not second
    assert next(first).n == 1
    assert next(second).n == 1
    assert [str(r.url.path) for r in requests] == ["/api/v2/codes/"] * 2
    assert requests[0].url == requests[1].url


def test_pag_5_an_exhausted_iterator_yields_nothing_more() -> None:
    handler, requests = recorder(page([1], None))
    client, _ = make_client(handler)
    items = client._list("codes/", Item)
    assert [i.n for i in items] == [1]
    assert list(items) == []
    assert len(requests) == 1
