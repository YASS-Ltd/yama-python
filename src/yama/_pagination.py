"""Paging through lists, and parsing responses into models."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from yama._errors import YamaError

T = TypeVar("T", bound=BaseModel)
PAGE_SIZE = 500  # the API's maximum, for the fewest requests under the rate limit


class _Page(BaseModel):
    next: str | None = None
    results: list[Any]


def parse(model: type[T], data: object) -> T:
    """Validate `data` as `model`, raising `YamaError` if the response doesn't fit."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        # Name the fields and what's wrong, never their values (SEC-2): no `from exc`, whose
        # errors hold the input, and the raise is outside the `except` so it isn't chained.
        problems = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'response'}: {e['type']}" for e in exc.errors()
        )
    raise YamaError(f"Unexpected response: not a valid {model.__name__} ({problems}).")


def paginate(
    request: Callable[..., Any],
    path: str,
    model: type[T],
    params: Mapping[str, object] | None = None,
) -> Iterator[T]:
    """Yield every item of a list, requesting each page as iteration reaches it and following
    `next` as given until it is null."""
    url: str | None = path
    query: dict[str, object] | None = {**(params or {}), "limit": PAGE_SIZE}
    while url:
        page = parse(_Page, request("GET", url, params=query))
        for item in page.results:
            yield parse(model, item)
        url, query = page.next, None
