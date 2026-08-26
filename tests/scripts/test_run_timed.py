# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for scripts/run_timed.py (make typecheck wall-time wrapper)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "run_timed.py"


def test_run_timed_prints_label_and_seconds() -> None:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "demo", sys.executable, "-c", "print('hello')"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout.startswith("=== demo ===\n")
    assert "hello\n" in proc.stdout
    hello_at = proc.stdout.index("hello\n")
    header_at = proc.stdout.index("=== demo ===\n")
    timer_at = proc.stdout.index("=== demo:")
    assert header_at < hello_at < timer_at
    assert "s ===" in proc.stdout


def test_run_timed_merges_stderr_into_block() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "demo",
            sys.executable,
            "-c",
            "import sys; print('out'); print('err', file=sys.stderr)",
        ],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "out\n" in proc.stdout
    assert "err\n" in proc.stdout
    assert proc.stderr == ""


def test_run_timed_preserves_command_exit_code() -> None:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "fail", sys.executable, "-c", "raise SystemExit(7)"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 7
    assert "=== fail:" in proc.stdout
