# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Trusted venv module: batch text embedding via sentence-transformers (Phase A/B).

Invoked from the LO host through a fixed RPC stub — not from LLM-submitted code.
See docs/embeddings.md and docs/enabling_numpy_in_libreoffice.md.
"""
from __future__ import annotations

import importlib
import logging
import sqlite3
import struct
import time
from typing import Any

log = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, Any] = {}


def _probe_sqlite_vec() -> bool:
    try:
        sqlite_vec = importlib.import_module("sqlite_vec")
        db = sqlite3.connect(":memory:")
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)
        return True
    except Exception:
        log.debug("sqlite-vec unavailable; using NumPy BLOB fallback for embeddings index", exc_info=True)
        return False


_SQLITE_VEC_AVAILABLE = _probe_sqlite_vec()


def _get_embedder(model_name: str) -> Any:
    cached = _MODEL_CACHE.get(model_name)
    if cached is not None:
        return cached
    try:
        st_mod = importlib.import_module("sentence_transformers")
    except ImportError as exc:
        raise ImportError(
            "sentence-transformers is not installed in the configured Python venv. "
            "Install it with: pip install sentence-transformers numpy"
        ) from exc
    embedder = st_mod.SentenceTransformer(model_name)
    _MODEL_CACHE[model_name] = embedder
    return embedder


def _l2_normalize_rows(matrix: Any) -> Any:
    import numpy as np

    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return matrix / norms


def _vector_to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _open_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if _SQLITE_VEC_AVAILABLE:
        sqlite_vec = importlib.import_module("sqlite_vec")

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    return conn


def _ensure_vec0_table(conn: sqlite3.Connection, dim: int) -> None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vec_chunks'"
    ).fetchone()
    if exists:
        return
    conn.execute(
        f"CREATE VIRTUAL TABLE vec_chunks USING vec0("
        f"chunk_id INTEGER PRIMARY KEY, "
        f"embedding float[{int(dim)}]"
        f")"
    )


def _upsert_corpus_meta(conn: sqlite3.Connection, **pairs: str) -> None:
    conn.executemany(
        "INSERT INTO corpus_meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        list(pairs.items()),
    )


def _find_chunk_id(conn: sqlite3.Connection, doc_url: str, para_index: int) -> int | None:
    row = conn.execute(
        "SELECT chunk_id FROM chunks WHERE doc_url=? AND para_index=?",
        (doc_url, para_index),
    ).fetchone()
    if row is None:
        return None
    return int(row["chunk_id"])


def _delete_chunk(conn: sqlite3.Connection, chunk_id: int, *, use_vec0: bool) -> None:
    if use_vec0:
        conn.execute("DELETE FROM vec_chunks WHERE chunk_id=?", (chunk_id,))
    conn.execute("DELETE FROM chunks WHERE chunk_id=?", (chunk_id,))


def _write_vector(
    conn: sqlite3.Connection,
    chunk_id: int,
    vec: list[float],
    *,
    use_vec0: bool,
) -> None:
    import numpy as np

    arr = np.asarray(vec, dtype=np.float32)
    if use_vec0:
        conn.execute(
            "INSERT INTO vec_chunks(chunk_id, embedding) VALUES (?, ?) "
            "ON CONFLICT(chunk_id) DO UPDATE SET embedding=excluded.embedding",
            (chunk_id, arr),
        )
    blob = _vector_to_blob(vec)
    conn.execute("UPDATE chunks SET embedding=? WHERE chunk_id=?", (blob, chunk_id))


def embed_texts(model_name: str, texts: list[str], *, normalize: bool = True) -> dict[str, Any]:
    """Batch-encode *texts* with a lazily loaded SentenceTransformer.

    Empty strings are skipped; ``indices`` maps each returned vector back to the
    original position in *texts*. Vectors are float32 values as nested lists
    (host-safe over Pickle5 IPC).
    """
    import numpy as np

    model = (model_name or "").strip()
    if not model:
        raise ValueError("embedding model name is required")

    if not texts:
        return {"model": model, "dim": 0, "vectors": [], "indices": []}

    indices: list[int] = []
    valid_texts: list[str] = []
    for i, text in enumerate(texts):
        if text is None:
            continue
        stripped = str(text).strip()
        if not stripped:
            continue
        indices.append(i)
        valid_texts.append(stripped)

    if not valid_texts:
        return {"model": model, "dim": 0, "vectors": [], "indices": []}

    embedder = _get_embedder(model)
    batch = embedder.encode(valid_texts, convert_to_tensor=False, show_progress_bar=False)
    matrix = np.stack(batch).astype(np.float32)
    if normalize:
        matrix = _l2_normalize_rows(matrix)

    dim = int(matrix.shape[1])
    vectors = matrix.tolist()
    return {"model": model, "dim": dim, "vectors": vectors, "indices": indices}


def index_paragraphs(db_path: str, model_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Batch-embed *rows* and persist locators + vectors into shared index.db."""
    model = (model_name or "").strip()
    if not model:
        raise ValueError("embedding model name is required")
    if not rows:
        return {"indexed": 0, "dim": 0, "storage_backend": "vec0" if _SQLITE_VEC_AVAILABLE else "blob_numpy"}

    texts = [str(r.get("text") or "").strip() for r in rows]
    if not any(texts):
        return {"indexed": 0, "dim": 0, "storage_backend": "vec0" if _SQLITE_VEC_AVAILABLE else "blob_numpy"}

    encoded = embed_texts(model, texts)
    vectors = encoded["vectors"]
    dim = int(encoded["dim"])
    use_vec0 = _SQLITE_VEC_AVAILABLE and dim > 0
    storage_backend = "vec0" if use_vec0 else "blob_numpy"
    now = time.time()

    conn = _open_db(db_path)
    try:
        if use_vec0:
            _ensure_vec0_table(conn, dim)

        indexed = 0
        for row, vec in zip(rows, vectors):
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            doc_url = str(row.get("doc_url") or "")
            para_index = int(row.get("para_index", 0))
            content_hash = str(row.get("content_hash") or "")
            file_mtime = float(row.get("file_mtime") or 0.0)
            char_start = int(row.get("char_start") or 0)
            char_end = int(row.get("char_end") or len(text))

            chunk_id = row.get("chunk_id")
            if chunk_id is not None:
                chunk_id = int(chunk_id)
            else:
                chunk_id = _find_chunk_id(conn, doc_url, para_index)

            if chunk_id is None:
                cur = conn.execute(
                    "INSERT INTO chunks("
                    "doc_url, para_index, char_start, char_end, content_hash, "
                    "file_mtime, last_indexed_at, embedding_model, embedding"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        doc_url,
                        para_index,
                        char_start,
                        char_end,
                        content_hash,
                        file_mtime,
                        now,
                        model,
                        _vector_to_blob(vec) if not use_vec0 else None,
                    ),
                )
                if cur.lastrowid is None:
                    raise RuntimeError("INSERT INTO chunks did not return chunk_id")
                chunk_id = int(cur.lastrowid)
            else:
                conn.execute(
                    "UPDATE chunks SET char_start=?, char_end=?, content_hash=?, "
                    "file_mtime=?, last_indexed_at=?, embedding_model=?, embedding=? "
                    "WHERE chunk_id=?",
                    (
                        char_start,
                        char_end,
                        content_hash,
                        file_mtime,
                        now,
                        model,
                        _vector_to_blob(vec) if not use_vec0 else None,
                        chunk_id,
                    ),
                )

            _write_vector(conn, chunk_id, vec, use_vec0=use_vec0)
            indexed += 1

        _upsert_corpus_meta(
            conn,
            embedding_model=model,
            dim=str(dim),
            storage_backend=storage_backend,
            updated_at=str(now),
        )
        conn.commit()
    finally:
        conn.close()

    return {"indexed": indexed, "dim": dim, "storage_backend": storage_backend}


def delete_paragraphs(db_path: str, keys: list[dict[str, Any]]) -> dict[str, Any]:
    """Remove locator + vector rows for (doc_url, para_index) pairs."""
    if not keys:
        return {"deleted": 0}
    use_vec0 = _SQLITE_VEC_AVAILABLE
    conn = _open_db(db_path)
    deleted = 0
    try:
        for key in keys:
            doc_url = str(key.get("doc_url") or "")
            para_index = int(key.get("para_index", 0))
            chunk_id = _find_chunk_id(conn, doc_url, para_index)
            if chunk_id is None:
                continue
            _delete_chunk(conn, chunk_id, use_vec0=use_vec0)
            deleted += 1
        conn.commit()
    finally:
        conn.close()
    return {"deleted": deleted}


def knn_search(db_path: str, query_text: str, k: int, *, model_name: str) -> dict[str, Any]:
    """Return top-k hits with locators and cosine-like scores from index.db."""
    import numpy as np

    model = (model_name or "").strip()
    if not model:
        raise ValueError("embedding model name is required")
    query = str(query_text or "").strip()
    if not query:
        return {"hits": []}
    limit = max(1, min(int(k or 5), 50))

    encoded = embed_texts(model, [query])
    if not encoded["vectors"]:
        return {"hits": []}
    query_vec = np.asarray(encoded["vectors"][0], dtype=np.float32)

    conn = _open_db(db_path)
    try:
        meta_row = conn.execute(
            "SELECT value FROM corpus_meta WHERE key='storage_backend'"
        ).fetchone()
        storage = str(meta_row["value"]) if meta_row else ""
        use_vec0 = storage == "vec0" and _SQLITE_VEC_AVAILABLE

        if use_vec0:
            rows = conn.execute(
                "SELECT chunk_id, distance FROM vec_chunks "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (query_vec, limit),
            ).fetchall()
            hits: list[dict[str, Any]] = []
            for row in rows:
                chunk_id = int(row["chunk_id"])
                loc = conn.execute(
                    "SELECT doc_url, para_index, char_start, char_end FROM chunks WHERE chunk_id=?",
                    (chunk_id,),
                ).fetchone()
                if loc is None:
                    continue
                distance = float(row["distance"])
                score = max(0.0, 1.0 - distance)
                hits.append(
                    {
                        "chunk_id": chunk_id,
                        "doc_url": str(loc["doc_url"]),
                        "para_index": int(loc["para_index"]),
                        "char_start": int(loc["char_start"] or 0),
                        "char_end": int(loc["char_end"] or 0),
                        "score": score,
                    }
                )
            return {"hits": hits}

        blob_rows = conn.execute(
            "SELECT chunk_id, doc_url, para_index, char_start, char_end, embedding "
            "FROM chunks WHERE embedding IS NOT NULL"
        ).fetchall()
        if not blob_rows:
            return {"hits": []}

        ids: list[int] = []
        locators: list[tuple[str, int, int, int]] = []
        matrix_rows: list[Any] = []
        for row in blob_rows:
            blob = row["embedding"]
            if not blob:
                continue
            vec = np.frombuffer(blob, dtype=np.float32)
            ids.append(int(row["chunk_id"]))
            locators.append(
                (
                    str(row["doc_url"]),
                    int(row["para_index"]),
                    int(row["char_start"] or 0),
                    int(row["char_end"] or 0),
                )
            )
            matrix_rows.append(vec)

        if not matrix_rows:
            return {"hits": []}

        corpus = np.stack(matrix_rows)
        similarities = np.clip(np.dot(corpus, query_vec), -1.0, 1.0)
        n = similarities.shape[0]
        if limit >= n:
            top_idx = np.argsort(similarities)[-limit:][::-1]
        else:
            part = np.argpartition(similarities, -limit)[-limit:]
            top_idx = part[np.argsort(similarities[part])][::-1]

        hits = []
        for i in top_idx:
            doc_url, para_index, char_start, char_end = locators[int(i)]
            hits.append(
                {
                    "chunk_id": ids[int(i)],
                    "doc_url": doc_url,
                    "para_index": para_index,
                    "char_start": char_start,
                    "char_end": char_end,
                    "score": float(similarities[int(i)]),
                }
            )
        return {"hits": hits}
    finally:
        conn.close()
