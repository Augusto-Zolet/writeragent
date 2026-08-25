#!/usr/bin/env python3
# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run a command and print ``=== LABEL: N.Ns ===`` wall time afterward.

Used by ``make typecheck`` so parallel ty/mypy/basedpyright/pyspector each
report how long they took even when their logs interleave.
"""
from __future__ import annotations

import subprocess
import sys
import time


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: run_timed.py LABEL command [args...]", file=sys.stderr)
        return 2
    label, cmd = argv[0], argv[1:]
    t0 = time.monotonic()
    rc = subprocess.call(cmd)
    print(f"=== {label}: {time.monotonic() - t0:.1f}s ===", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
