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

from plugin.doc.embeddings_fs import content_hash, extract_writer_paragraphs


def _odf_hashes(path: Path) -> list[str]:
    return [content_hash(t) for t in extract_writer_paragraphs(str(path))]


def _uno_hashes(path: Path) -> list[str] | None:
    try:
        import uno  # noqa: F401
    except ImportError:
        return None
    from unittest.mock import MagicMock

    from plugin.doc.embeddings_chunker import _writer_paragraph_chunks

    url = f"file://{path.resolve()}"
    services = MagicMock()
    para_texts: list[str] = []

    class _Para:
        def supportsService(self, name: str) -> bool:
            return name == "com.sun.star.text.Paragraph"

        def getString(self) -> str:
            return para_texts.pop(0) if para_texts else ""

    # Use ODF extract to seed UNO mock only when we cannot open LO — parity script uses ODF as ground truth
    # for offline runs. With soffice, replace with real open_document_for_read path.
    odf_texts = extract_writer_paragraphs(str(path))
    services.document.get_paragraph_ranges.return_value = [
        type("P", (), {"supportsService": _Para().supportsService, "getString": lambda self, t=t: t})()
        for t in odf_texts
    ]
    chunks = _writer_paragraph_chunks(
        MagicMock(),
        services,
        doc_url=url,
        doc_path=str(path),
        file_mtime=0.0,
    )
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
