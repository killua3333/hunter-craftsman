"""Root pytest bootstrap: fix craftsman.prompts namespace shadow and tests/ import order."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CRAFTSMAN_ROOT = ROOT / "craftsman"
HUNTER_SRC = ROOT / "hunter" / "src"
HUNTER_TESTS = ROOT / "hunter" / "tests"
CRAFTSMAN_TESTS = ROOT / "craftsman" / "tests"


def _prepend(path: Path) -> None:
    entry = str(path)
    if entry in sys.path:
        sys.path.remove(entry)
    sys.path.insert(0, entry)


def _purge_craftsman_modules() -> None:
    for name in list(sys.modules):
        if name == "craftsman" or name.startswith("craftsman."):
            del sys.modules[name]


def _register_hunter_tests_namespace() -> None:
    """Ensure Hunter's `tests.conftest` wins over craftsman/tests/conftest.py."""
    conftest_path = HUNTER_TESTS / "conftest.py"
    spec = importlib.util.spec_from_file_location("tests.conftest", conftest_path)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if "tests" not in sys.modules:
        tests_pkg = importlib.util.module_from_spec(
            importlib.util.spec_from_loader("tests", loader=None)
        )
        tests_pkg.__path__ = [str(HUNTER_TESTS)]  # type: ignore[attr-defined]
        sys.modules["tests"] = tests_pkg
    sys.modules["tests.conftest"] = module


def _configure_import_paths() -> None:
    _prepend(HUNTER_TESTS)
    _prepend(HUNTER_SRC)
    _prepend(CRAFTSMAN_ROOT)
    _purge_craftsman_modules()
    _register_hunter_tests_namespace()


_configure_import_paths()


def pytest_configure(config) -> None:
    _prepend(HUNTER_TESTS)
    _prepend(HUNTER_SRC)
    _prepend(CRAFTSMAN_ROOT)
    craftsman_tests = str(CRAFTSMAN_TESTS)
    if craftsman_tests in sys.path:
        sys.path.remove(craftsman_tests)
        sys.path.append(craftsman_tests)
    _purge_craftsman_modules()
    _register_hunter_tests_namespace()
