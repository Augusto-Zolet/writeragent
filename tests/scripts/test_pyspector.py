"""Smoke tests for PySpector config (make pyspector; part of make typecheck / make test)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

try:
    import tomllib
except ImportError:  # pragma: no cover — Python < 3.11
    tomllib = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parents[2]
PYSPECTOR_TOML = REPO_ROOT / "pyspector.toml"


@pytest.mark.skipif(tomllib is None, reason="tomllib requires Python 3.11+")
def test_pyspector_toml_exists_and_excludes_vendored() -> None:
    assert PYSPECTOR_TOML.is_file()
    data = tomllib.loads(PYSPECTOR_TOML.read_text(encoding="utf-8"))
    tool = data["tool"]["pyspector"]
    excludes = set(tool["exclude"])
    # Bare component names: scan root is plugin/, so contrib/lib match via path parts.
    assert "contrib" in excludes
    assert "lib" in excludes
    assert tool["severity"] == "MEDIUM"


def test_pyspector_cli_help_if_installed() -> None:
    """Skip cleanly when pyspector is not on PATH / in .venv (optional tool)."""
    exe = shutil.which("pyspector")
    if exe is None:
        venv_bin = REPO_ROOT / ".venv" / "bin" / "pyspector"
        venv_win = REPO_ROOT / ".venv" / "Scripts" / "pyspector.exe"
        if venv_bin.is_file():
            exe = str(venv_bin)
        elif venv_win.is_file():
            exe = str(venv_win)
        else:
            pytest.skip("pyspector not installed (uv sync)")
    result = subprocess.run([exe, "--help"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    assert "scan" in (result.stdout + result.stderr).lower() or "pyspector" in (result.stdout + result.stderr).lower()
