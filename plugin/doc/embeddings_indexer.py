# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Background per-folder embeddings index maintenance (Chroma + LangGraph)."""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

from plugin.doc.embeddings_cache import (
    chroma_persist_dir,
    clear_folder_cache,
    corpus_meta_path,
    diff_paragraph_rows,
    ensure_corpus_meta,
    file_index_state_path,
    file_is_stale,
    index_is_empty,
    mark_file_indexed,
    needs_cold_rebuild,
    resolve_index_context,
    sync_file_paragraph_state,
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

if TYPE_CHECKING:
    from plugin.doc.document_research import FileEntry
    from plugin.doc.embeddings_chunker import ParagraphChunk

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


def _execute_uno_phase(ctx: Any, fn):
    """Run document open/extract/close on the LibreOffice main thread (UNO is not thread-safe)."""
    from plugin.framework.queue_executor import execute_on_main_thread

    return execute_on_main_thread(fn)


def _doc_url_for_entry(entry: FileEntry) -> str:
    from plugin.doc.document_research import _path_to_file_url

    path = entry.get("path") or ""
    url = entry.get("url") or ""
    return url if url else _path_to_file_url(str(path))


def _collect_cold_build_chunks(
    ctx: Any,
    services: Any,
    model: Any,
) -> tuple[list[FileEntry], list[dict[str, Any]], dict[str, list[ParagraphChunk]], str | None]:
    files, err = list_indexable_sibling_files(ctx, model)
    if err:
        return [], [], {}, err
    all_rows: list[dict[str, Any]] = []
    file_chunks: dict[str, list[ParagraphChunk]] = {}
    for entry in files:
        chunks = extract_paragraph_chunks_from_file(ctx, services, entry)
        doc_url = _doc_url_for_entry(entry)
        file_chunks[doc_url] = chunks
        for chunk in chunks:
            all_rows.append(chunk_to_index_row(chunk))
    return files, all_rows, file_chunks, None


def _collect_incremental_uno_work(
    ctx: Any,
    services: Any,
    model: Any,
    state_path: Any,
) -> tuple[list[tuple[FileEntry, str, float, list[ParagraphChunk], list[dict[str, Any]], list[dict[str, Any]]]], str | None]:
    files, err = list_indexable_sibling_files(ctx, model)
    if err:
        return [], err
    work: list[tuple[FileEntry, str, float, list[ParagraphChunk], list[dict[str, Any]], list[dict[str, Any]]]] = []
    for entry in files:
        doc_url = _doc_url_for_entry(entry)
        mtime = float(entry.get("modified") or 0.0)
        if not file_is_stale(state_path, doc_url, mtime):
            continue
        chunks = extract_paragraph_chunks_from_file(ctx, services, entry)
        to_index, to_delete = diff_paragraph_rows(state_path, chunks)
        work.append((entry, doc_url, mtime, chunks, to_index, to_delete))
    return work, None


def rebuild_folder_index(ctx: Any, services: Any, model: Any, *, folder_key: str, listing_root: str) -> None:
    """Cold build: index all Writer siblings in the folder."""
    embedding_model = get_embedding_model(ctx)
    persist_dir = chroma_persist_dir(listing_root)
    meta_path = corpus_meta_path(listing_root)
    state_path = file_index_state_path(listing_root)

    files, all_rows, file_chunks, err = _execute_uno_phase(
        ctx,
        lambda: _collect_cold_build_chunks(ctx, services, model),
    )
    if err:
        log.debug("Folder index skipped: %s", err)
        return

    clear_folder_cache(listing_root)
    ensure_corpus_meta(meta_path, embedding_model=embedding_model)

    if not all_rows:
        log.debug("No indexable Writer paragraphs in %s", listing_root)
        return

    index_paragraphs(
        ctx,
        str(persist_dir),
        folder_key,
        str(meta_path),
        all_rows,
        model=embedding_model,
    )
    for entry in files:
        doc_url = _doc_url_for_entry(entry)
        mtime = float(entry.get("modified") or 0.0)
        sync_file_paragraph_state(state_path, doc_url, file_chunks.get(doc_url, []), mtime)

    log.info("Cold-built Chroma embeddings index for %s (%d paragraphs)", listing_root, len(all_rows))


def refresh_folder_index_incremental(
    ctx: Any,
    services: Any,
    model: Any,
    *,
    folder_key: str,
    listing_root: str,
) -> None:
    """Incremental refresh: mtime skip, hash diff, batch embed changed paragraphs only."""
    embedding_model = get_embedding_model(ctx)
    persist_dir = chroma_persist_dir(listing_root)
    meta_path = corpus_meta_path(listing_root)
    state_path = file_index_state_path(listing_root)

    if needs_cold_rebuild(meta_path, embedding_model):
        from plugin.doc.embeddings_cache import resolve_folder_for_active_doc

        listing_root = resolve_folder_for_active_doc(ctx, model) or ""
        rebuild_folder_index(ctx, services, model, folder_key=folder_key, listing_root=listing_root)
        return

    work, err = _execute_uno_phase(
        ctx,
        lambda: _collect_incremental_uno_work(ctx, services, model, state_path),
    )
    if err:
        log.debug("Incremental index skipped: %s", err)
        return

    for _entry, doc_url, mtime, chunks, to_index, to_delete in work:
        if to_delete:
            delete_paragraphs(
                ctx,
                str(persist_dir),
                folder_key,
                str(meta_path),
                to_delete,
                model=embedding_model,
            )
        if to_index:
            index_paragraphs(
                ctx,
                str(persist_dir),
                folder_key,
                str(meta_path),
                to_index,
                model=embedding_model,
            )
            sync_file_paragraph_state(state_path, doc_url, chunks, mtime)
        elif not to_delete:
            mark_file_indexed(state_path, doc_url, mtime)


def _index_worker(ctx: Any, services: Any, model: Any, folder_key: str, listing_root: str) -> None:
    try:
        meta_path = corpus_meta_path(listing_root, create_parent=False)
        persist_dir = chroma_persist_dir(listing_root, create_parent=False)
        if index_is_empty(meta_path, persist_dir):
            rebuild_folder_index(ctx, services, model, folder_key=folder_key, listing_root=listing_root)
            return
        if needs_cold_rebuild(meta_path, get_embedding_model(ctx)):
            rebuild_folder_index(ctx, services, model, folder_key=folder_key, listing_root=listing_root)
            return
        refresh_folder_index_incremental(ctx, services, model, folder_key=folder_key, listing_root=listing_root)
    except Exception:
        log.exception("Background embeddings index failed for folder %s", folder_key)
    finally:
        _clear_enqueue(folder_key)


def enqueue_folder_index(ctx: Any, services: Any, model: Any) -> None:
    """Schedule background index maintenance for the active document folder."""
    if not document_research_uses_embeddings(ctx):
        return
    resolved = resolve_index_context(ctx, model)
    folder_key, _persist, _meta, listing_root = resolved[0], resolved[1], resolved[2], resolved[3]
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


