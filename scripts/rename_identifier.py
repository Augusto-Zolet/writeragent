#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rename a Python identifier across ``.py`` files (reusable codemod).

Uses word-boundary substitution so ``openpyxl`` / ``xlrd`` / ``_xlws`` stay intact.
Optional ``--string-attr-prefix`` is implied by the same ``old.`` → ``new.`` rule
(covered by rewriting ``old`` before a following ``.`` via the identifier pattern
plus a dedicated attr pass).

Does **not** rewrite markdown; update docs separately.

Examples::

  python scripts/rename_identifier.py xl calc --dry-run --paths plugin/framework/constants.py

  python scripts/rename_identifier.py xl calc --paths-file /tmp/files.txt

  # Paths file format: one repo-relative path per line; ``#`` comments allowed.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Lines mentioning these stay untouched (third-party / Excel package tokens).
_SKIP_LINE_MARKERS = ("openpyxl", "xlrd", "xlwt", "xlsxwriter", "_xlws", "xlfn")


def _resolve_path(raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p.resolve()


def rewrite_text(original: str, old: str, new: str) -> str | None:
    """Return rewritten text, or None if unchanged.

    Identifier rule: ``old`` not adjacent to other identifier chars.
    Also rewrites ``old.`` attr/string prefixes the same way (``xl.foo`` → ``calc.foo``).
    """
    ident_re = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])")
    out: list[str] = []
    changed = False
    for line in original.splitlines(keepends=True):
        if any(m in line for m in _SKIP_LINE_MARKERS):
            out.append(line)
            continue
        replaced = ident_re.sub(new, line)
        if replaced != line:
            changed = True
        out.append(replaced)
    if not changed:
        return None
    return "".join(out)


def process_file(path: Path, old: str, new: str, *, dry_run: bool) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = rewrite_text(original, old, new)
    if updated is None:
        return False
    rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
    if dry_run:
        print(f"WOULD UPDATE: {rel}")
        return True
    path.write_text(updated, encoding="utf-8")
    print(f"UPDATED: {rel}")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old", help="Old identifier (e.g. xl)")
    ap.add_argument("new", help="New identifier (e.g. calc)")
    ap.add_argument("--paths", nargs="*", default=[], help="Files relative to repo root")
    ap.add_argument("--paths-file", type=Path, help="File with one path per line")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not args.old.isidentifier() or not args.new.isidentifier():
        print("old/new must be valid Python identifiers", file=sys.stderr)
        return 2
    if args.old == args.new:
        print("old and new are identical", file=sys.stderr)
        return 2

    paths: list[Path] = [_resolve_path(p) for p in args.paths]
    if args.paths_file:
        for line in args.paths_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                paths.append(_resolve_path(line))
    if not paths:
        print("No paths given", file=sys.stderr)
        return 2

    n = 0
    for path in paths:
        if not path.is_file():
            print(f"MISSING: {path}", file=sys.stderr)
            continue
        if path.suffix != ".py":
            print(f"SKIP (not .py): {path}", file=sys.stderr)
            continue
        if process_file(path, args.old, args.new, dry_run=args.dry_run):
            n += 1
    print(f"{'Would update' if args.dry_run else 'Updated'} {n} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
