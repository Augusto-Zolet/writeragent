# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Guard the unit-pytest / live-LibreOffice split used by ``make pytest``."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = REPO_ROOT / "Makefile"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Exact command documented in the Makefile comment and ``make pytest``.
PYTEST_UNIT_CMD = (
    '$(PYTHON) -m pytest tests -m "not slow and not integration" '
    "--ignore-glob='*_uno.py'"
)


def _makefile_text() -> str:
    if not MAKEFILE.is_file():
        pytest.skip("Makefile is not copied into the stripped make release tree")
    return MAKEFILE.read_text(encoding="utf-8")


def test_makefile_documents_exact_pytest_unit_command() -> None:
    text = _makefile_text()
    assert f"Exact command: {PYTEST_UNIT_CMD}" in text
    assert "PYTEST_UNIT =" in text
    assert '-m "not slow and not integration"' in text
    assert '--ignore-glob="*_uno.py"' in text


def test_makefile_pytest_unit_uses_xdist_by_default() -> None:
    text = _makefile_text()
    assert "PYTEST_WORKERS ?= auto" in text
    assert "--dist=loadgroup" in text
    assert "WRITERAGENT_PYTEST_PROGRESS=1" in text
    assert "PYTHONUNBUFFERED=1" in text
    pytest_block = re.search(
        r"^pytest:\n(?:\t.*\n)+",
        text,
        re.MULTILINE,
    )
    assert pytest_block is not None, "missing Makefile pytest: target"
    body = pytest_block.group(0)
    assert "$(PYTEST_UNIT)" in body
    assert "testing_runner" not in body
    assert "$(PYTEST_XDIST)" in text


def test_pyproject_lists_pytest_xdist() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    assert "pytest-xdist" in text


def test_makefile_typecheck_runs_checkers_in_parallel() -> None:
    text = _makefile_text()
    block = re.search(
        r"^typecheck:.*\n(?:\t.*\n)+",
        text,
        re.MULTILINE,
    )
    assert block is not None, "missing Makefile typecheck: target"
    body = block.group(0)
    assert "-j4" in body
    assert "ty-run" in body
    assert "mypy-run" in body
    assert "basedpyright-run" in body
    assert "pyspector" in body


def test_makefile_register_built_oxt_removes_librepy() -> None:
    """Both OXTs register PythonFunction; dual install fails unopkg on addin.py."""
    text = _makefile_text()
    block = re.search(
        r"^register-built-oxt:\n(?:\t.*\n)+",
        text,
        re.MULTILINE,
    )
    assert block is not None, "missing Makefile register-built-oxt: target"
    body = block.group(0)
    assert "remove $(LIBREPY_EXTENSION_ID)" in body
    assert "remove org.extension.writeragent" in body
    librepy_at = body.index("remove $(LIBREPY_EXTENSION_ID)")
    writeragent_at = body.index("remove org.extension.writeragent")
    add_at = body.index("unopkg add") if "unopkg add" in body else body.index("$(UNOPKG) add")
    assert librepy_at < writeragent_at < add_at


def test_makefile_test_run_is_pytest_then_serial_testing_runner() -> None:
    text = _makefile_text()
    test_run = re.search(
        r"^test-run:\n(?:\t.*\n)+",
        text,
        re.MULTILINE,
    )
    assert test_run is not None, "missing Makefile test-run: target"
    body = test_run.group(0)
    assert "$(MAKE) pytest" in body
    assert "plugin.testing_runner" in body
    # UNO stays serial: the testing_runner line must not grow pytest -n / xdist.
    runner_line = [ln for ln in body.splitlines() if "plugin.testing_runner" in ln][0]
    assert re.search(r"(^|\s)-n(\s|$)", runner_line) is None
    assert "xdist" not in runner_line
    pytest_at = body.index("$(MAKE) pytest")
    runner_at = body.index("plugin.testing_runner")
    assert pytest_at < runner_at


def test_pyproject_addopts_ignore_uno_glob() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    assert "--ignore-glob=*_uno.py" in text
    assert "--ignore=tests/uno" in text


def test_conftest_magicmock_cleanup_is_controller_only() -> None:
    import importlib.util
    import types

    # Do not ``import conftest``: under xdist that name can be a nested conftest.
    spec = importlib.util.spec_from_file_location(
        "_writeragent_root_conftest",
        REPO_ROOT / "tests" / "conftest.py",
    )
    assert spec is not None and spec.loader is not None
    root_conftest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(root_conftest)

    worker = types.SimpleNamespace(config=types.SimpleNamespace(workerinput={"workerid": "gw0"}))
    controller = types.SimpleNamespace(config=types.SimpleNamespace())
    assert root_conftest._is_xdist_worker(worker) is True
    assert root_conftest._is_xdist_worker(controller) is False
    assert callable(root_conftest.pytest_sessionfinish)


def test_make_pytest_progress_heartbeat_on_stderr(monkeypatch, capsys) -> None:
    import importlib.util
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "_writeragent_root_conftest_progress",
        REPO_ROOT / "tests" / "conftest.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setenv("WRITERAGENT_PYTEST_PROGRESS", "1")
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    mod._pytest_progress_done = 0
    report = SimpleNamespace(when="call", failed=False)
    for _idx in range(100):
        mod.pytest_runtest_logreport(report)
    err = capsys.readouterr().err
    assert "pytest: 100" in err


def test_uno_suffix_files_exist_for_native_runner() -> None:
    uno_files = list((REPO_ROOT / "tests").rglob("*_uno.py"))
    assert uno_files, "expected native *_uno.py suites under tests/"
    names = {path.name for path in uno_files}
    assert "test_document_uno.py" not in names
    assert "test_linebreak_uno.py" not in names
