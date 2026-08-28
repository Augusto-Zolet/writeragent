# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Makefile invariants for `make release` stripped-tree UNO tests."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = PROJECT_ROOT / "Makefile"


@pytest.mark.skipif(shutil.which("make") is None, reason="make not on PATH")
def test_lo_kill_when_cwd_has_no_makefile(tmp_path: Path) -> None:
    """`make release` runs `make -f $checkout/Makefile test-uno` from a
    stripped /tmp tree (no Makefile). lo-kill must resolve via PROJECT_ROOT
    (the Makefile's directory), not CURDIR.

    Dry-run lo-kill only: `make -n test-uno` still executes recipe lines that
    contain $(MAKE) (GNU make recursive-make exception).
    """
    proc = subprocess.run(
        [
            "make",
            "-n",
            "-C",
            str(tmp_path),
            "-f",
            str(MAKEFILE),
            "lo-kill",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "No rule to make target" not in combined
    assert "kill-libreoffice" in combined

    text = MAKEFILE.read_text(encoding="utf-8")
    assert '$(MAKE) -C "$(PROJECT_ROOT)" lo-kill' in text
