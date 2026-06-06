# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Paragraph-level chunk extraction for embeddings indexing (Phase B)."""
from __future__ import annotations

import dataclasses
import hashlib
import logging
import os
from typing import Any

from plugin.doc.document_research import (
    FileEntry,
    close_document_research_document,
    list_nearby_files,
    open_document_for_read,
)

log = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class ParagraphChunk:
    doc_url: str
    para_index: int
    char_start: int
    char_end: int
    text: str
    content_hash: str
    file_mtime: float
    doc_path: str = ""


def content_hash(text: str) -> str:
    """SHA-256 of normalized paragraph text (stable for incremental invalidation)."""
    normalized = str(text or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _writer_paragraph_chunks(
    model: Any,
    services: Any,
    *,
    doc_url: str,
    doc_path: str,
    file_mtime: float,
) -> list[ParagraphChunk]:
    doc_svc = services.document
    para_ranges = doc_svc.get_paragraph_ranges(model)
    chunks: list[ParagraphChunk] = []
    for para_index, para in enumerate(para_ranges):
        try:
            if para.supportsService("com.sun.star.text.Paragraph"):
                raw = str(para.getString() or "")
            else:
                raw = ""
        except Exception:
            raw = ""
        text = raw.strip()
        if not text:
            continue
        chunks.append(
            ParagraphChunk(
                doc_url=doc_url,
                para_index=para_index,
                char_start=0,
                char_end=len(text),
                text=text,
                content_hash=content_hash(text),
                file_mtime=file_mtime,
                doc_path=doc_path,
            )
        )
    return chunks


def extract_paragraph_chunks_from_file(
    ctx: Any,
    services: Any,
    entry: FileEntry,
) -> list[ParagraphChunk]:
    """Read-only extract of indexable Writer paragraphs from one sibling file."""
    path = entry.get("path") or ""
    url = entry.get("url") or ""
    if not path:
        return []
    doc_type = entry.get("doc_type_guess") or ""
    if doc_type != "writer":
        log.debug("Skipping non-writer file for embeddings chunker: %s (%s)", path, doc_type)
        return []

    target = url if url else path
    model, opened_type, err, opened_for_dr = open_document_for_read(ctx, target)
    if model is None or err:
        log.debug("Could not open %s for chunk extract: %s", path, err)
        return []
    try:
        if opened_type != "writer":
            return []
        mtime = float(entry.get("modified") or 0.0)
        if not mtime:
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = 0.0
        doc_url = url or f"file://{path}"
        return _writer_paragraph_chunks(
            model,
            services,
            doc_url=doc_url,
            doc_path=path,
            file_mtime=mtime,
        )
    finally:
        close_document_research_document(model, opened_for_document_research=opened_for_dr)


def list_indexable_sibling_files(ctx: Any, model: Any) -> tuple[list[FileEntry], str | None]:
    """Return office siblings in the active folder (same scope as list_nearby_files)."""
    listing = list_nearby_files(ctx, model, file_kind="documents")
    if listing.get("status") != "ok":
        return [], listing.get("message", "Could not list nearby files")
    files: list[FileEntry] = list(listing.get("files") or [])
    return files, None


def chunk_to_index_row(chunk: ParagraphChunk, *, chunk_id: int | None = None) -> dict[str, Any]:
    """Dict shape for venv index_paragraphs RPC."""
    row: dict[str, Any] = {
        "doc_url": chunk.doc_url,
        "para_index": chunk.para_index,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "content_hash": chunk.content_hash,
        "text": chunk.text,
        "file_mtime": chunk.file_mtime,
    }
    if chunk_id is not None:
        row["chunk_id"] = chunk_id
    return row
