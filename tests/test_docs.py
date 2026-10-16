"""The README and docs: their code examples run, and the reference documents the client."""

import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import griffe
import httpx
import pytest

import yama
from yama import testing
from yama.testing import fake_transport

ROOT = Path(__file__).parent.parent
PAGES = sorted((ROOT / "docs").glob("*.md"))
NOT_RUN = "<!-- not run -->"  # put on the line before a block that needs other packages
BLOCK = re.compile(r"^(?P<before>[^\n]*)\n+```python\n(?P<code>.*?)^```", re.MULTILINE | re.DOTALL)


def python_blocks(path: Path) -> list[str]:
    """The ```python blocks of a Markdown file, except those marked as not run."""
    return [
        match["code"]
        for match in BLOCK.finditer(path.read_text())
        if match["before"].strip() != NOT_RUN
    ]


class FakeYama(yama.Yama):
    """`Yama`, on a fresh fake API unless given an `http_client`."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("http_client", httpx.Client(transport=fake_transport()))
        super().__init__(*args, **kwargs)


@pytest.fixture
def on_fake_api(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """`from yama import Yama` gives a client on the fake API, with a key from the env."""
    monkeypatch.setenv("YAMA_API_KEY", "test")
    monkeypatch.setattr(yama, "Yama", FakeYama)
    levels = {name: logging.getLogger(name).level for name in ("httpx", "yama")}
    yield
    for name, level in levels.items():
        logging.getLogger(name).setLevel(level)


def run(blocks: list[str], name: str) -> dict[str, Any]:
    """Run `blocks` in turn in one namespace, as a reader following the page would."""
    namespace: dict[str, Any] = {"__name__": name}
    for code in blocks:
        exec(compile(code, name, "exec"), namespace)
    return namespace


def test_del_3_readme_quick_start_runs_against_the_fake_api(
    on_fake_api: None, capsys: pytest.CaptureFixture[str]
) -> None:
    blocks = python_blocks(ROOT / "README.md")
    assert blocks, "the README has no Python examples"
    run(blocks, "README.md")
    output = capsys.readouterr().out
    assert "Primary" in output  # a code
    assert "code_accepted" in output  # a call in October 2026


@pytest.mark.parametrize("page", PAGES, ids=[page.name for page in PAGES])
def test_del_2_docs_examples_run_against_the_fake_api(page: Path, on_fake_api: None) -> None:
    run(python_blocks(page), page.name)


def test_del_2_reference_documents_the_resource_attributes() -> None:
    client = griffe.load("yama", search_paths=[ROOT / "src"])["Yama"]
    for name in ("api_key", "buildings", "units", "contacts", "codes", "calls"):
        attribute = client.members.get(name)
        assert attribute is not None, f"Yama.{name} is missing"
        assert attribute.docstring, f"Yama.{name} has no docstring"


def test_del_2_testing_docs_list_the_fake_apis_seed_data() -> None:
    page = (ROOT / "docs" / "testing.md").read_text()
    for name, items in testing._DATA.items():
        for item in items:
            suffix = item["uuid"].rsplit("-", 1)[1]
            assert f"`{suffix}`" in page, f"{name} {item['uuid']} is missing"
