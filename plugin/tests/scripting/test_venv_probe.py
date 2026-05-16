# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from __future__ import annotations

import stat
import subprocess
import sys
from unittest.mock import patch

from plugin.scripting.venv_probe import probe_venv_path, resolve_venv_python, run_venv_self_check


def _fake_completed(returncode: int, stdout: str = "", stderr: str = ""):
    class R:
        pass

    r = R()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def test_resolve_venv_python_finds_posix_python(tmp_path):
    venv = tmp_path / "venv"
    bindir = venv / "bin"
    bindir.mkdir(parents=True)
    py = bindir / "python"
    py.write_text("#!/bin/sh\necho ok\n")
    py.chmod(py.stat().st_mode | stat.S_IEXEC)
    got = resolve_venv_python(str(venv))
    assert got == str(py)


def test_resolve_venv_python_none_when_missing(tmp_path):
    assert resolve_venv_python(str(tmp_path / "nope")) is None


def test_probe_venv_path_not_directory():
    ok, msg = probe_venv_path(__file__)
    assert ok is False
    assert "Not a directory" in msg or "directory" in msg.lower()


def test_probe_venv_path_empty():
    ok, msg = probe_venv_path("  ")
    assert ok is False


def test_run_venv_self_check_success():
    ok, msg = run_venv_self_check(sys.executable, timeout=10.0)
    assert ok is True
    assert "OK" in msg or "ok" in msg.lower()


def test_run_venv_self_check_subprocess_error():
    with patch("plugin.scripting.venv_probe.subprocess.run", side_effect=OSError("boom")):
        ok, msg = run_venv_self_check("/fake/python", timeout=1.0)
    assert ok is False
    assert "boom" in msg


def test_run_venv_self_check_bad_exit():
    fake = _fake_completed(1, stdout="", stderr="nope")
    with patch("plugin.scripting.venv_probe.subprocess.run", return_value=fake):
        ok, msg = run_venv_self_check("/x/python", timeout=1.0)
    assert ok is False
    assert "1" in msg
    assert "nope" in msg


def test_run_venv_self_check_timeout():
    with patch(
        "plugin.scripting.venv_probe.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1.0),
    ):
        ok, msg = run_venv_self_check("/x/python", timeout=1.0)
    assert ok is False
    assert "Timed out" in msg
