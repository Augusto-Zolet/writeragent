# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Trusted venv folder FTS5 index: ODF extract + SQLite search (no UNO)."""
from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable, Literal

log = logging.getLogger(__name__)

MaintainMode = Literal["auto", "cold", "incremental"]

__all__ = [
    "MaintainMode",
    "build_match_query",
    "fts_stats",
    "maintain_folder_fts",
    "search_folder_fts",
    "strip_fts_snippet_markers",
]

_NEAR_SLASH_RE = re.compile(r"(.+?)\s+NEAR\s*/\s*(\d+)\s+(.+)", re.IGNORECASE)
_FTS5_NEAR_CALL_RE = re.compile(r"\bNEAR\s*\(", re.IGNORECASE)
_BOOL_RE = re.compile(r"\b(AND|OR|NOT)\b", re.IGNORECASE)


def _escape_fts_token(token: str) -> str:
    cleaned = str(token or "").strip()
    if not cleaned:
        return '""'
    escaped = cleaned.replace('"', '""')
    return f'"{escaped}"'


def build_match_query(query: str, *, near_slop: int = 10) -> str:
    """Build an FTS5 MATCH expression (multi-word defaults to NEAR with slop)."""
    raw = str(query or "").strip()
    if not raw:
        raise ValueError("query is required")
    slop = max(0, int(near_slop))

    if _FTS5_NEAR_CALL_RE.search(raw):
        return raw
    if _BOOL_RE.search(raw):
        return raw

    near_match = _NEAR_SLASH_RE.search(raw)
    if near_match:
        left_tokens = [t for t in near_match.group(1).split() if t.strip()]
        right_tokens = [t for t in near_match.group(3).split() if t.strip()]
        dist = int(near_match.group(2))
        tokens = left_tokens + right_tokens
        if not tokens:
            raise ValueError("NEAR query has no terms")
        quoted = " ".join(_escape_fts_token(t) for t in tokens)
        return f"NEAR({quoted}, {dist})"

    tokens = [t for t in raw.split() if t.strip()]
    if len(tokens) == 1:
        return _escape_fts_token(tokens[0])
    quoted = " ".join(_escape_fts_token(t) for t in tokens)
    return f"NEAR({quoted}, {slop})"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _count_rows(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS c FROM passages").fetchone()
    return int(row["c"] if row else 0)


def maintain_folder_fts(
    listing_root: str,
    mode: MaintainMode = "auto",
    *,
    heartbeat_fn: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Full folder FTS maintenance — delegates to unified corpus maintain (FTS leg only)."""
    from plugin.embeddings.venv.embeddings_folder_maintain import maintain_folder_corpus

    return maintain_folder_corpus(
        listing_root,
        embedding_model="",
        search_mode="fts",
        mode=mode,
        heartbeat_fn=heartbeat_fn,
    )


def strip_fts_snippet_markers(snippet: str) -> str:
    """Remove FTS5 snippet() highlight brackets; readable plain text for agents and UI."""
    return str(snippet or "").replace("[", "").replace("]", "")


def search_folder_fts(
    fts_db_path_str: str,
    query: str,
    *,
    k: int = 10,
    near_slop: int = 10,
) -> dict[str, Any]:
    """BM25 search over a folder FTS5 index (unified corpus.db or legacy fts5.db)."""
    db_path = Path(str(fts_db_path_str or ""))
    if not db_path.is_file():
        return {"hits": [], "query": query, "match": ""}

    limit = max(1, min(int(k or 10), 30))
    match_expr = build_match_query(str(query or ""), near_slop=near_slop)

    from plugin.embeddings.venv.embeddings_sqlite import connect_corpus_db, fts_corpus_search

    conn = connect_corpus_db(db_path)
    try:
        hits = fts_corpus_search(conn, str(query or ""), k=limit, near_slop=near_slop)
    finally:
        conn.close()

    return {"hits": hits, "query": query, "match": match_expr}


def fts_stats(fts_db_path_str: str, meta_path_str: str) -> dict[str, Any]:
    """Lightweight FTS corpus stats for host empty/stale checks."""
    db_path = Path(str(fts_db_path_str or ""))
    meta_path = Path(str(meta_path_str or ""))
    row_count = 0
    if db_path.is_file():
        with _connect(db_path) as conn:
            row_count = _count_rows(conn)
    from plugin.embeddings.folder_fts_cache import read_fts_meta

    meta = read_fts_meta(meta_path)
    return {
        "row_count": row_count,
        "schema_version": meta.get("schema_version", ""),
        "updated_at": meta.get("updated_at", ""),
    }
