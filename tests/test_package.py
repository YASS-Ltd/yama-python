import subprocess
import sys

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
