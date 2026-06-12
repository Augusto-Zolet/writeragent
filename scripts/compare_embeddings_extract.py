#!/usr/bin/env python3
# WriterAgent - compare UNO vs ODF paragraph extract for embeddings parity research.
"""Compare paragraph extraction: UNO (hidden open) vs stdlib ODF zip/XML.

Run with LibreOffice available for UNO path:
  make fix-uno
  .venv/bin/python scripts/compare_embeddings_extract.py scripts/longdocsample.odt

ODF-only (no UNO):
  .venv/bin/python scripts/compare_embeddings_extract.py scripts/longdocsample.odt --odf-only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from plugin.embeddings.embeddings_fs import content_hash, extract_writer_paragraphs, paragraph_chunks_from_path


def _odf_hashes(path: Path) -> list[str]:
    return [content_hash(t) for t in extract_writer_paragraphs(str(path))]


def _uno_hashes(path: Path) -> list[str] | None:
    try:
        import uno  # noqa: F401
    except ImportError:
        return None
    url = f"file://{path.resolve()}"
    chunks = paragraph_chunks_from_path(str(path), doc_url=url, file_mtime=0.0)
    return [c.content_hash for c in chunks]


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare ODF vs UNO paragraph extract hashes")
    parser.add_argument("odt", type=Path, help="Writer .odt/.fodt path")
    parser.add_argument("--odf-only", action="store_true", help="Skip UNO comparison")
    args = parser.parse_args()
    path = args.odt.resolve()
    if not path.is_file():
        print(f"Not found: {path}", file=sys.stderr)
        return 1

    odf = _odf_hashes(path)
    print(f"ODF paragraphs: {len(odf)}")
    if args.odf_only:
        return 0

    uno = _uno_hashes(path)
    if uno is None:
        print("UNO unavailable — ODF-only run")
        return 0

    print(f"UNO paragraphs: {len(uno)}")
    matched = sum(1 for a, b in zip(odf, uno, strict=False) if a == b)
    total = max(len(odf), len(uno))
    pct = (100.0 * matched / total) if total else 100.0
    print(f"Hash match: {matched}/{total} ({pct:.1f}%)")
    if len(odf) != len(uno):
        print(f"Count mismatch: ODF={len(odf)} UNO={len(uno)}")
    return 0 if pct >= 95.0 and len(odf) == len(uno) else 1


if __name__ == "__main__":
    raise SystemExit(main())
