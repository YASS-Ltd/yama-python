import email
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import yama

IMPORT_CHECK = """
import logging, socket

def refuse(*args, **kwargs):
    raise AssertionError("network used on import")

socket.socket.connect = refuse
socket.create_connection = refuse

import yama, yama.testing

assert logging.root.handlers == []
logger = logging.getLogger("yama")
assert [type(h).__name__ for h in logger.handlers] == ["NullHandler"]
assert logger.level == logging.NOTSET and logger.propagate
"""


def test_version_is_set() -> None:
    assert yama.__version__


def test_pkg_3_import_is_silent_and_configures_nothing() -> None:
    result = subprocess.run(
        [sys.executable, "-W", "error", "-c", IMPORT_CHECK],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


CONSUMER = """
from yama import AccessCodeCreate, Yama
from yama.testing import fake_transport
import httpx

with Yama("test", http_client=httpx.Client(transport=fake_transport())) as client:
    names: list[str] = [b.name for b in client.buildings.list()]
    unit = next(client.units.list())
    code = client.codes.create(AccessCodeCreate(unit=unit.uuid, code="482915"))
    digits: str = code.code
"""


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The wheel `uv build` makes from this checkout."""
    out = tmp_path_factory.mktemp("dist")
    root = Path(__file__).parent.parent
    subprocess.run(["uv", "build", "--wheel", "-q", "-o", str(out), str(root)], check=True)
    return next(out.glob("yama_client-*.whl"))


def in_clean_env(wheel: Path, cwd: Path, *command: str) -> subprocess.CompletedProcess[str]:
    """Run `command` with only the wheel, its dependencies and mypy installed, as a consumer."""
    return subprocess.run(
        ["uv", "run", "--isolated", "--no-project", "--python", sys.executable,
         "--with", str(wheel), "--with", "mypy", *command],
        cwd=cwd, capture_output=True, text=True, check=False,
    )  # fmt: skip


def test_pkg_1_wheel_needs_python_3_10_and_only_httpx_and_pydantic(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".dist-info/METADATA"))
        metadata = email.message_from_bytes(zf.read(name))
    assert metadata["Name"] == "yama-client"
    assert metadata["Requires-Python"] == ">=3.10"
    requires = [re.split(r"[^\w.-]", r)[0] for r in metadata.get_all("Requires-Dist", [])]
    assert sorted(requires) == ["httpx", "pydantic"]


def test_pkg_1_wheel_installs_and_imports(wheel: Path, tmp_path: Path) -> None:
    result = in_clean_env(wheel, tmp_path, "python", "-c", "import yama; print(yama.__version__)")
    assert result.returncode == 0, result.stderr


def test_pkg_2_wheel_ships_py_typed_and_passes_mypy_strict(wheel: Path, tmp_path: Path) -> None:
    with zipfile.ZipFile(wheel) as zf:
        assert "yama/py.typed" in zf.namelist()
    (tmp_path / "consumer.py").write_text(CONSUMER)
    result = in_clean_env(wheel, tmp_path, "mypy", "--strict", "consumer.py")
    assert result.returncode == 0, result.stdout + result.stderr
