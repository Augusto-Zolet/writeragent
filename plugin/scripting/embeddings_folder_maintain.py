# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Trusted venv folder index maintenance: ODF extract + Chroma ingest (no UNO)."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Literal

from plugin.doc.embeddings_cache import (
    chroma_persist_dir,
    clear_folder_cache,
    corpus_meta_path,
    diff_paragraph_rows,
    ensure_corpus_meta,
    file_index_state_path,
    file_is_stale,
    folder_corpus_key,
    index_is_empty,
    mark_file_indexed,
    maybe_upgrade_legacy_index,
    needs_cold_rebuild,
    sync_file_paragraph_state,
)
from plugin.doc.embeddings_fs import (
    ParagraphChunk,
    WriterFileEntry,
    guess_indexable_paths,
    paragraph_chunks_from_path,
)
from plugin.framework.constants import EMBEDDINGS_HEARTBEAT_INTERVAL_S
from plugin.scripting.embeddings_ingest_graph import ingest_paragraphs

log = logging.getLogger(__name__)

MaintainMode = Literal["auto", "cold", "incremental"]

__all__ = ["MaintainMode", "maintain_folder_index"]


class _HeartbeatThrottle:
    def __init__(self, heartbeat_fn: Callable[[dict[str, Any]], None] | None) -> None:
        self._fn = heartbeat_fn
        self._last = 0.0

    def ping(self, payload: dict[str, Any]) -> None:
        if self._fn is None:
            return
        now = time.monotonic()
        if now - self._last < EMBEDDINGS_HEARTBEAT_INTERVAL_S:
            return
        self._last = now
        self._fn(payload)

    def force(self, payload: dict[str, Any]) -> None:
        if self._fn is None:
            return
        self._last = time.monotonic()
        self._fn(payload)


def _resolve_mode(
    listing_root: str,
    embedding_model: str,
    mode: MaintainMode,
) -> MaintainMode:
    if mode != "auto":
        return mode
    meta_path = corpus_meta_path(listing_root, create_parent=False)
    persist_dir = chroma_persist_dir(listing_root, create_parent=False)
    if index_is_empty(meta_path, persist_dir) or needs_cold_rebuild(meta_path, embedding_model):
        return "cold"
    return "incremental"


def _ingest_rows(
    listing_root: str,
    folder_key: str,
    embedding_model: str,
    rows: list[dict[str, Any]],
    *,
    delete_keys: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    persist_dir = str(chroma_persist_dir(listing_root))
    meta_path = str(corpus_meta_path(listing_root))
    return ingest_paragraphs(
        persist_dir,
        folder_key,
        meta_path,
        embedding_model,
        rows,
        delete_keys=list(delete_keys or []),
    )


def _cold_build(
    listing_root: str,
    folder_key: str,
    embedding_model: str,
    files: list[WriterFileEntry],
    hb: _HeartbeatThrottle,
) -> dict[str, Any]:
    clear_folder_cache(listing_root)
    ensure_corpus_meta(corpus_meta_path(listing_root), embedding_model=embedding_model)
    all_rows: list[dict[str, Any]] = []
    file_chunks: dict[str, list[ParagraphChunk]] = {}
    total = len(files)

    for index, entry in enumerate(files):
        hb.force({"phase": "extract", "file": entry.name, "index": index, "total": total, "mode": "cold"})
        chunks = paragraph_chunks_from_path(entry.path, doc_url=entry.url, file_mtime=entry.modified)
        file_chunks[entry.url] = chunks
        from plugin.doc.embeddings_fs import chunk_to_index_row

        for chunk in chunks:
            all_rows.append(chunk_to_index_row(chunk))
        hb.ping({"phase": "extract", "file": entry.name, "paragraphs": len(chunks)})

    if not all_rows:
        log.debug("No indexable passages in %s", listing_root)
        return {"mode": "cold", "indexed_paragraphs": 0, "files": total}

    hb.force({"phase": "embed", "paragraphs": len(all_rows), "mode": "cold"})
    result = _ingest_rows(listing_root, folder_key, embedding_model, all_rows)
    state_path = file_index_state_path(listing_root)
    for entry in files:
        sync_file_paragraph_state(state_path, entry.url, file_chunks.get(entry.url, []), entry.modified)

    return {
        "mode": "cold",
        "indexed_paragraphs": len(all_rows),
        "files": total,
        "upserted": int(result.get("upserted") or 0),
    }


def _incremental_refresh(
    listing_root: str,
    folder_key: str,
    embedding_model: str,
    files: list[WriterFileEntry],
    hb: _HeartbeatThrottle,
) -> dict[str, Any]:
    state_path = file_index_state_path(listing_root)
    indexed = 0
    deleted = 0
    files_touched = 0
    total = len(files)

    for index, entry in enumerate(files):
        hb.ping({"phase": "scan", "file": entry.name, "index": index, "total": total})
        if not file_is_stale(state_path, entry.url, entry.modified):
            continue
        hb.force({"phase": "extract", "file": entry.name, "index": index, "total": total, "mode": "incremental"})
        chunks = paragraph_chunks_from_path(entry.path, doc_url=entry.url, file_mtime=entry.modified)
        to_index, to_delete = diff_paragraph_rows(state_path, chunks)
        if to_delete:
            hb.force({"phase": "delete", "file": entry.name, "keys": len(to_delete)})
            _ingest_rows(listing_root, folder_key, embedding_model, [], delete_keys=to_delete)
            deleted += len(to_delete)
        if to_index:
            hb.force({"phase": "embed", "file": entry.name, "paragraphs": len(to_index)})
            _ingest_rows(listing_root, folder_key, embedding_model, to_index)
            sync_file_paragraph_state(state_path, entry.url, chunks, entry.modified)
            indexed += len(to_index)
            files_touched += 1
        elif not to_delete:
            mark_file_indexed(state_path, entry.url, entry.modified)
            files_touched += 1

    return {
        "mode": "incremental",
        "indexed_paragraphs": indexed,
        "deleted_paragraphs": deleted,
        "files_touched": files_touched,
        "files": total,
    }


def maintain_folder_index(
    listing_root: str,
    *,
    embedding_model: str,
    mode: MaintainMode = "auto",
    heartbeat_fn: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Full folder index maintenance in the venv (ODF extract + Chroma)."""
    model = (embedding_model or "").strip()
    if not model:
        raise ValueError("embedding model name is required")
    root = str(listing_root or "").strip()
    if not root:
        raise ValueError("listing_root is required")

    maybe_upgrade_legacy_index(root)
    folder_key = folder_corpus_key(root)
    resolved_mode = _resolve_mode(root, model, mode)
    hb = _HeartbeatThrottle(heartbeat_fn)
    hb.force({"phase": "start", "mode": resolved_mode, "listing_root": root})

    files = guess_indexable_paths(root)
    if resolved_mode == "cold":
        out = _cold_build(root, folder_key, model, files, hb)
    else:
        out = _incremental_refresh(root, folder_key, model, files, hb)

    hb.force({"phase": "done", **out})
    log.info("Embeddings maintain %s for %s: %s", resolved_mode, root, out)
    return out
