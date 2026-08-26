#!/usr/bin/env python3
# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run a command, then print its output as one labeled block plus wall time.

Used by ``make typecheck`` so parallel ty/mypy/basedpyright/pyspector keep
running concurrently without interleaving progress bars and banners.
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
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    body = proc.stdout or ""
    if body and not body.endswith("\n"):
        body += "\n"
    elapsed = time.monotonic() - t0
    # One write so a finishing sibling cannot splice into this block.
    sys.stdout.write(f"=== {label} ===\n{body}=== {label}: {elapsed:.1f}s ===\n")
    sys.stdout.flush()
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
