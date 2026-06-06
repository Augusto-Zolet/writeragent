# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Background per-folder embeddings index maintenance (Phase B)."""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from typing import Any

from plugin.doc.embeddings_cache import (
    chunk_count,
    ensure_host_schema,
    index_db_path,
    index_is_empty,
    model_matches_index,
    open_host_connection,
    resolve_index_context,
)
from plugin.doc.embeddings_chunker import (
    chunk_to_index_row,
    extract_paragraph_chunks_from_file,
    list_indexable_sibling_files,
)
from plugin.framework.client.embedding_client import get_embedding_model
from plugin.framework.client.embeddings_service import delete_paragraphs, index_paragraphs
from plugin.framework.constants import document_research_uses_embeddings
from plugin.framework.worker_pool import run_in_background

log = logging.getLogger(__name__)

_inflight: set[str] = set()
_inflight_lock = threading.Lock()


def _try_enqueue(folder_key: str) -> bool:
    with _inflight_lock:
        if folder_key in _inflight:
            return False
        _inflight.add(folder_key)
        return True


def _clear_enqueue(folder_key: str) -> None:
    with _inflight_lock:
        _inflight.discard(folder_key)


def get_file_index_state(conn: sqlite3.Connection, doc_url: str) -> dict[str, float | int]:
    """Return stored file_mtime, last_indexed_at, and chunk_count for *doc_url*."""
    try:
        row = conn.execute(
            "SELECT MAX(file_mtime) AS file_mtime, MAX(last_indexed_at) AS last_indexed_at, COUNT(*) AS chunk_count "
            "FROM chunks WHERE doc_url=?",
            (doc_url,),
        ).fetchone()
    except sqlite3.OperationalError:
        return {"file_mtime": 0.0, "last_indexed_at": 0.0, "chunk_count": 0}
    if row is None or int(row["chunk_count"] or 0) == 0:
        return {"file_mtime": 0.0, "last_indexed_at": 0.0, "chunk_count": 0}
    return {
        "file_mtime": float(row["file_mtime"] or 0.0),
        "last_indexed_at": float(row["last_indexed_at"] or 0.0),
        "chunk_count": int(row["chunk_count"]),
    }


def file_is_stale(conn: sqlite3.Connection, doc_url: str, file_mtime: float) -> bool:
    """True when filesystem mtime is newer than last indexed timestamp for *doc_url*."""
    state = get_file_index_state(conn, doc_url)
    if state["chunk_count"] == 0:
        return True
    return float(file_mtime) > float(state["last_indexed_at"])


def mark_file_indexed(
    conn: sqlite3.Connection,
    doc_url: str,
    file_mtime: float,
    *,
    indexed_at: float | None = None,
) -> int:
    """Advance last_indexed_at/file_mtime for *doc_url* when content was checked but unchanged."""
    ts = float(indexed_at if indexed_at is not None else time.time())
    cur = conn.execute(
        "UPDATE chunks SET last_indexed_at=?, file_mtime=? WHERE doc_url=?",
        (ts, float(file_mtime), doc_url),
    )
    conn.commit()
    return int(cur.rowcount)


def diff_paragraph_rows(
    conn: sqlite3.Connection,
    chunks: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (rows_to_index, keys_to_delete) comparing extracted chunks to DB."""
    from plugin.doc.embeddings_chunker import ParagraphChunk

    to_index: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for chunk in chunks:
        if not isinstance(chunk, ParagraphChunk):
            continue
        key = (chunk.doc_url, chunk.para_index)
        seen.add(key)
        row = conn.execute(
            "SELECT chunk_id, content_hash FROM chunks WHERE doc_url=? AND para_index=?",
            key,
        ).fetchone()
        if row is not None and str(row["content_hash"]) == chunk.content_hash:
            continue
        chunk_id = int(row["chunk_id"]) if row is not None else None
        to_index.append(chunk_to_index_row(chunk, chunk_id=chunk_id))

    if not chunks:
        return to_index, []

    doc_url = chunks[0].doc_url
    db_rows = conn.execute(
        "SELECT para_index FROM chunks WHERE doc_url=?",
        (doc_url,),
    ).fetchall()
    to_delete: list[dict[str, Any]] = []
    for db_row in db_rows:
        para_index = int(db_row["para_index"])
        if (doc_url, para_index) not in seen:
            to_delete.append({"doc_url": doc_url, "para_index": para_index})
    return to_index, to_delete


def needs_cold_rebuild(conn: sqlite3.Connection, embedding_model: str) -> bool:
    if chunk_count(conn) == 0:
        return True
    return not model_matches_index(conn, embedding_model)


def rebuild_folder_index(ctx: Any, services: Any, model: Any, *, folder_key: str, listing_root: str) -> None:
    """Cold build: index all Writer siblings in the folder."""
    embedding_model = get_embedding_model(ctx)
    db_path = index_db_path(ctx, folder_key)
    files, err = list_indexable_sibling_files(ctx, model)
    if err:
        log.debug("Folder index skipped: %s", err)
        return

    if db_path.is_file():
        db_path.unlink()

    with open_host_connection(db_path) as conn:
        ensure_host_schema(conn, embedding_model=embedding_model)

    all_rows: list[dict[str, Any]] = []
    for entry in files:
        for chunk in extract_paragraph_chunks_from_file(ctx, services, entry):
            all_rows.append(chunk_to_index_row(chunk))

    if not all_rows:
        log.debug("No indexable Writer paragraphs in %s", listing_root)
        return

    index_paragraphs(ctx, str(db_path), all_rows, model=embedding_model)
    log.info("Cold-built embeddings index for %s (%d paragraphs)", listing_root, len(all_rows))


def refresh_folder_index_incremental(ctx: Any, services: Any, model: Any, *, folder_key: str) -> None:
    """Incremental refresh: mtime skip, hash diff, batch embed changed paragraphs only."""
    embedding_model = get_embedding_model(ctx)
    db_path = index_db_path(ctx, folder_key)

    with open_host_connection(db_path) as conn:
        if needs_cold_rebuild(conn, embedding_model):
            from plugin.doc.embeddings_cache import resolve_folder_for_active_doc

            listing_root = resolve_folder_for_active_doc(ctx, model) or ""
            rebuild_folder_index(ctx, services, model, folder_key=folder_key, listing_root=listing_root)
            return

    files, err = list_indexable_sibling_files(ctx, model)
    if err:
        log.debug("Incremental index skipped: %s", err)
        return

    for entry in files:
        doc_url = entry.get("url") or f"file://{entry.get('path')}"
        mtime = float(entry.get("modified") or 0.0)
        with open_host_connection(db_path) as conn:
            if not file_is_stale(conn, doc_url, mtime):
                continue

        chunks = extract_paragraph_chunks_from_file(ctx, services, entry)
        with open_host_connection(db_path) as conn:
            to_index, to_delete = diff_paragraph_rows(conn, chunks)

        if to_delete:
            delete_paragraphs(ctx, str(db_path), to_delete, model=embedding_model)
        if to_index:
            index_paragraphs(ctx, str(db_path), to_index, model=embedding_model)
        elif not to_delete:
            # Save bumped mtime but paragraph hashes match — avoid re-scanning every periodic tick.
            with open_host_connection(db_path) as conn:
                mark_file_indexed(conn, doc_url, mtime)


def _index_worker(ctx: Any, services: Any, model: Any, folder_key: str, listing_root: str) -> None:
    try:
        db_path = index_db_path(ctx, folder_key, create_parent=False)
        if not db_path.is_file() or index_is_empty(db_path):
            rebuild_folder_index(ctx, services, model, folder_key=folder_key, listing_root=listing_root)
            return
        with open_host_connection(db_path) as conn:
            if needs_cold_rebuild(conn, get_embedding_model(ctx)):
                rebuild_folder_index(ctx, services, model, folder_key=folder_key, listing_root=listing_root)
                return
        refresh_folder_index_incremental(ctx, services, model, folder_key=folder_key)
    except Exception:
        log.exception("Background embeddings index failed for folder %s", folder_key)
    finally:
        _clear_enqueue(folder_key)


def enqueue_folder_index(ctx: Any, services: Any, model: Any) -> None:
    """Schedule background index maintenance for the active document folder."""
    if not document_research_uses_embeddings():
        return
    resolved = resolve_index_context(ctx, model)
    folder_key, db_path, listing_root = resolved[0], resolved[1], resolved[2]
    if folder_key is None or listing_root is None:
        return
    if not _try_enqueue(folder_key):
        return

    def _run() -> None:
        _index_worker(ctx, services, model, folder_key, listing_root)

    run_in_background(_run, name=f"embeddings-index-{folder_key[:8]}")


def ensure_index_wakeup(ctx: Any, services: Any, model: Any) -> None:
    """Non-blocking wakeup when search runs against a missing or stale cache."""
    enqueue_folder_index(ctx, services, model)
