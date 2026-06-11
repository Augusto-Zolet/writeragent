# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Trusted venv ODS row extract for folder embeddings / FTS (pandas + odfpy)."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

__all__ = ["extract_calc_rows"]


def extract_calc_rows(path: str) -> list[str]:
    """Read indexable row text from a Calc .ods/.ots/.fods (one passage per non-empty row)."""
    try:
        import pandas as pd
    except ImportError:
        log.debug("pandas not installed — ODS extract skipped for %s", path, exc_info=True)
        return []
    try:
        sheets = pd.read_excel(path, engine="odf", sheet_name=None, header=None)
    except ImportError:
        log.debug("odfpy not installed — ODS extract skipped for %s", path, exc_info=True)
        return []
    except Exception:
        log.debug("extract_calc_rows failed for %s", path, exc_info=True)
        return []

    rows: list[str] = []
    for sheet_name, frame in sheets.items():
        for _, row in frame.iterrows():
            cells = [str(value).strip() for value in row if pd.notna(value) and str(value).strip()]
            if cells:
                rows.append(f"[Sheet: {sheet_name}]\t" + "\t".join(cells))
    return rows
