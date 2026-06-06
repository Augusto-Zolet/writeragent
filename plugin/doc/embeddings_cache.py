# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Per-folder embeddings index paths and host-side SQLite locator schema (Phase B)."""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from plugin.doc.document_research import resolve_listing_directory
from plugin.framework.config import user_config_dir

log = logging.getLogger(__name__)

EMBEDDINGS_CACHE_DIRNAME = "writeragent_embeddings"
SCHEMA_VERSION = "1"
CHUNKS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id INTEGER PRIMARY KEY,
  doc_url TEXT NOT NULL,
  para_index INTEGER NOT NULL,
  char_start INTEGER,
  char_end INTEGER,
  content_hash TEXT NOT NULL,
  file_mtime REAL,
  last_indexed_at REAL,
  embedding_model TEXT NOT NULL,
  embedding BLOB
);
"""
CORPUS_META_DDL = """
CREATE TABLE IF NOT EXISTS corpus_meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
"""


def folder_corpus_key(directory_path: str) -> str:
    """Stable cache key for a normalized directory path."""
    norm = os.path.normpath(os.path.abspath(directory_path))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def resolve_folder_for_active_doc(ctx: Any, model: Any) -> str | None:
    """Directory whose siblings are indexed — same scope as list_nearby_files."""
    return resolve_listing_directory(ctx, model)


def embeddings_cache_root(ctx: Any) -> Path:
    """Profile-local root for all per-folder index.db files."""
    root = user_config_dir(ctx)
    if not root:
        raise OSError("Could not resolve WriterAgent user config directory")
    return Path(root) / EMBEDDINGS_CACHE_DIRNAME


def index_db_path(ctx: Any, folder_key: str, *, create_parent: bool = True) -> Path:
    """Path to index.db for *folder_key* under the profile embeddings cache."""
    path = embeddings_cache_root(ctx) / folder_key / "index.db"
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def open_host_connection(db_path: Path) -> sqlite3.Connection:
    """Open index.db with stdlib sqlite3 (host — no vec extension)."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_host_schema(
    conn: sqlite3.Connection,
    *,
    embedding_model: str,
    dim: int | None = None,
    storage_backend: str = "pending",
) -> None:
    """Create locator tables if missing; refresh corpus_meta keys."""
    conn.executescript(CHUNKS_TABLE_DDL + CORPUS_META_DDL)
    now = str(time.time())
    meta_rows = {
        "schema_version": SCHEMA_VERSION,
        "embedding_model": embedding_model,
        "storage_backend": storage_backend,
        "updated_at": now,
    }
    if dim is not None:
        meta_rows["dim"] = str(dim)
    conn.executemany(
        "INSERT INTO corpus_meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        list(meta_rows.items()),
    )
    conn.commit()


def read_corpus_meta(conn: sqlite3.Connection) -> dict[str, str]:
    """Return corpus_meta as a plain dict."""
    rows = conn.execute("SELECT key, value FROM corpus_meta").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def chunk_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
    return int(row["n"]) if row else 0


def index_is_empty(db_path: Path) -> bool:
    """True when index.db is missing or has no chunk rows."""
    if not db_path.is_file():
        return True
    try:
        with open_host_connection(db_path) as conn:
            return chunk_count(conn) == 0
    except sqlite3.Error:
        log.debug("index_is_empty failed for %s", db_path, exc_info=True)
        return True


def model_matches_index(conn: sqlite3.Connection, embedding_model: str) -> bool:
    """False when stored embedding_model differs (requires cold rebuild)."""
    meta = read_corpus_meta(conn)
    stored = meta.get("embedding_model", "").strip()
    if not stored:
        return True
    return stored == embedding_model.strip()


def resolve_index_context(ctx: Any, model: Any) -> tuple[str, Path, str] | tuple[None, None, str]:
    """Return (folder_key, db_path, listing_root) or (None, None, error_message)."""
    listing_root = resolve_folder_for_active_doc(ctx, model)
    if not listing_root:
        return None, None, "No nearby files found. Save the document or open sibling files in LibreOffice."
    folder_key = folder_corpus_key(listing_root)
    db_path = index_db_path(ctx, folder_key)
    return folder_key, db_path, listing_root
