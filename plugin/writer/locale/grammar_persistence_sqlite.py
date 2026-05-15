# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""SQLite implementation of persistent grammar cache."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

try:
    import sqlite3
    HAS_SQLITE = True
except ImportError:
    sqlite3 = None  # type: ignore
    HAS_SQLITE = False

from .grammar_persistence import (
    CACHE_LIMIT,
    GRAMMAR_CACHE_VERSION,
    PRUNE_TARGET,
    GrammarPersistence,
    _compress_error,
    _decompress_error,
)

log = logging.getLogger("writeragent.grammar")

class SQLitePersistence(GrammarPersistence):
    """SQLite implementation of persistent grammar cache."""

    def __init__(self, ctx: Any, db_path: str):
        super().__init__(ctx, db_path)
        self._init_db()

    def _migrate_version(self, conn: Any) -> None:
        try:
            cols = [str(row[1]) for row in conn.execute("PRAGMA table_info(sentence_cache)").fetchall()]
            if "version" not in cols:
                conn.execute("ALTER TABLE sentence_cache ADD COLUMN version INTEGER DEFAULT 1")
            
            # If any rows have an older version, clear them as fingerprints and formats have changed.
            cursor = conn.execute("SELECT count(*) FROM sentence_cache WHERE version < ?", (GRAMMAR_CACHE_VERSION,))
            old_count = cursor.fetchone()[0]
            if old_count > 0:
                log.info("[grammar] SQLitePersistence: clearing %s old-version cache entries (v < %s)", old_count, GRAMMAR_CACHE_VERSION)
                conn.execute("DELETE FROM sentence_cache WHERE version < ?", (GRAMMAR_CACHE_VERSION,))
        except Exception as e:
            log.warning("[grammar] SQLitePersistence version migration failed: %s", e)

    def _init_db(self) -> None:
        if not HAS_SQLITE or sqlite3 is None:
            return
        try:
            os.makedirs(os.path.dirname(self.base_path), exist_ok=True)
            with sqlite3.connect(self.base_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sentence_cache (
                        fingerprint TEXT PRIMARY KEY,
                        locale TEXT,
                        errors_json TEXT,
                        last_used INTEGER,
                        version INTEGER DEFAULT 1
                    )
                """)
                self._migrate_version(conn)
                self._migrate_drop_text_column(conn)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_last_used ON sentence_cache(last_used)")
                conn.commit()
        except Exception as e:
            log.error("[grammar] SQLitePersistence _init_db failed: %s", e)

    def _migrate_drop_text_column(self, conn: Any) -> None:
        try:
            cols = [str(row[1]) for row in conn.execute("PRAGMA table_info(sentence_cache)").fetchall()]
            if "text" not in cols:
                return
            # The sentence text was never read after writes; keep only the stable
            # fingerprint and errors to reduce cache size and plaintext footprint.
            conn.executescript("""
                DROP INDEX IF EXISTS idx_last_used;
                CREATE TABLE sentence_cache_new (
                    fingerprint TEXT PRIMARY KEY,
                    locale TEXT,
                    errors_json TEXT,
                    last_used INTEGER,
                    version INTEGER DEFAULT 1
                );
                INSERT INTO sentence_cache_new (fingerprint, locale, errors_json, last_used, version)
                    SELECT fingerprint, locale, errors_json, last_used, version FROM sentence_cache;
                DROP TABLE sentence_cache;
                ALTER TABLE sentence_cache_new RENAME TO sentence_cache;
            """)
            log.info("[grammar] SQLitePersistence: migrated sentence_cache schema without text column")
        except Exception as e:
            log.warning("[grammar] SQLitePersistence text-column migration failed: %s", e)

    def get(self, fp: str) -> list[dict[str, Any]] | None:
        if not HAS_SQLITE or sqlite3 is None:
            return None
        try:
            with sqlite3.connect(self.base_path) as conn:
                cursor = conn.execute("SELECT errors_json FROM sentence_cache WHERE fingerprint = ? AND version = ?", (fp, GRAMMAR_CACHE_VERSION))
                row = cursor.fetchone()
                if row:
                    conn.execute("UPDATE sentence_cache SET last_used = ? WHERE fingerprint = ?", (int(time.time()), fp))
                    conn.commit()
                    if row[0] is None:
                        return []
                    raw_errors = json.loads(row[0])
                    if isinstance(raw_errors, list):
                        return [_decompress_error(e) for e in raw_errors]
                    return []
        except Exception as e:
            log.debug("[grammar] SQLitePersistence get failed: %s", e)
        return None

    def put(self, fp: str, locale: str, errors: list[dict[str, Any]]) -> None:
        if not HAS_SQLITE or sqlite3 is None:
            return
        try:
            if not errors:
                errors_json = None
            else:
                compressed = [_compress_error(e) for e in errors]
                errors_json = json.dumps(compressed)
            with sqlite3.connect(self.base_path) as conn:
                conn.execute("""
                    INSERT INTO sentence_cache (fingerprint, locale, errors_json, last_used, version)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(fingerprint) DO UPDATE SET
                        errors_json = excluded.errors_json,
                        last_used = excluded.last_used,
                        version = excluded.version
                """, (fp, locale, errors_json, int(time.time()), GRAMMAR_CACHE_VERSION))
                conn.commit()
        except Exception as e:
            log.warning("[grammar] SQLitePersistence put failed: %s", e)

    def prune(self) -> None:
        if not HAS_SQLITE or sqlite3 is None:
            return
        try:
            with sqlite3.connect(self.base_path) as conn:
                cursor = conn.execute("SELECT count(*) FROM sentence_cache")
                count = cursor.fetchone()[0]
                if count > CACHE_LIMIT:
                    to_remove = count - PRUNE_TARGET
                    log.info("[grammar] persistence: pruning %s entries from SQLite cache", to_remove)
                    conn.execute("""
                        DELETE FROM sentence_cache WHERE fingerprint IN (
                            SELECT fingerprint FROM sentence_cache ORDER BY last_used ASC LIMIT ?
                        )
                    """, (to_remove,))
                    conn.commit()
        except Exception as e:
            log.warning("[grammar] SQLitePersistence prune failed: %s", e)

    def clear(self) -> None:
        if not HAS_SQLITE or sqlite3 is None:
            return
        try:
            with sqlite3.connect(self.base_path) as conn:
                conn.execute("DELETE FROM sentence_cache")
                conn.commit()
        except Exception as e:
            log.warning("[grammar] SQLitePersistence clear failed: %s", e)


class JSONPersistence(GrammarPersistence):
    """JSON-sharded implementation of persistent grammar cache (fallback)."""

    def __init__(self, ctx: Any, dir_path: str):
        super().__init__(ctx, dir_path)
        try:
            os.makedirs(self.base_path, exist_ok=True)
        except Exception as e:
            log.error("[grammar] JSONPersistence init failed to create dir: %s", e)

    def _file_path(self, fp: str) -> str:
        return os.path.join(self.base_path, f"{fp}.json")

    def get(self, fp: str) -> list[dict[str, Any]] | None:
        path = self._file_path(fp)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                os.utime(path, None)
                
                version = data.get("version", 1)
                if version < GRAMMAR_CACHE_VERSION:
                    log.debug("[grammar] JSONPersistence: ignoring old version %s for %s", version, fp)
                    return None
                
                errors = data.get("errors")
                if isinstance(errors, list):
                    return [_decompress_error(e) for e in errors]
                return []
        except Exception as e:
            log.debug("[grammar] JSONPersistence get failed: %s", e)
        return None

    def put(self, fp: str, locale: str, errors: list[dict[str, Any]]) -> None:
        path = self._file_path(fp)
        try:
            data = {
                "version": GRAMMAR_CACHE_VERSION,
                "locale": locale,
                "errors": [_compress_error(e) for e in errors],
                "timestamp": int(time.time()),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            log.warning("[grammar] JSONPersistence put failed: %s", e)

    def prune(self) -> None:
        try:
            files = [os.path.join(self.base_path, f) for f in os.listdir(self.base_path) if f.endswith(".json")]
            if len(files) > CACHE_LIMIT:
                files.sort(key=os.path.getmtime)
                to_remove = len(files) - PRUNE_TARGET
                log.info("[grammar] persistence: pruning %s files from JSON cache", to_remove)
                for i in range(to_remove):
                    try:
                        os.remove(files[i])
                    except OSError:
                        pass
        except Exception as e:
            log.warning("[grammar] JSONPersistence prune failed: %s", e)

    def clear(self) -> None:
        try:
            for f in os.listdir(self.base_path):
                if f.endswith(".json"):
                    try:
                        os.remove(os.path.join(self.base_path, f))
                    except OSError:
                        pass
        except Exception as e:
            log.warning("[grammar] JSONPersistence clear failed: %s", e)
