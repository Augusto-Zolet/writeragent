# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from plugin.writer.locale.grammar_persistence import JSONPersistence, SQLitePersistence, get_persistence, HAS_SQLITE
from plugin.writer.locale.grammar_proofread_locale import fingerprint_for_text

class TestGrammarPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.ctx = MagicMock()
        
    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    @unittest.skipUnless(HAS_SQLITE, "SQLite not available")
    def test_sqlite_persistence(self):
        db_path = os.path.join(self.tmp_dir, "test_grammar.db")
        p = SQLitePersistence(self.ctx, db_path)
        
        text = "This is a test."
        fp = fingerprint_for_text(text)
        errors = [{"wrong": "test", "correct": "TEST", "type": "grammar", "reason": "why not"}]
        
        p.put(fp, "en-US", text, errors)
        
        # New instance to verify persistence
        p2 = SQLitePersistence(self.ctx, db_path)
        hit = p2.get(fp)
        self.assertEqual(hit, errors)
        
        p2.clear()
        self.assertIsNone(p2.get(fp))

    def test_json_persistence(self):
        dir_path = os.path.join(self.tmp_dir, "test_grammar_cache.d")
        p = JSONPersistence(self.ctx, dir_path)
        
        text = "This is a JSON test."
        fp = fingerprint_for_text(text)
        errors = [{"wrong": "test", "correct": "JSON_TEST", "type": "grammar", "reason": "fallback"}]
        
        p.put(fp, "en-US", text, errors)
        
        # Verify file exists
        self.assertTrue(os.path.exists(os.path.join(dir_path, f"{fp}.json")))
        
        # New instance
        p2 = JSONPersistence(self.ctx, dir_path)
        hit = p2.get(fp)
        self.assertEqual(hit, errors)
        
        p2.clear()
        self.assertIsNone(p2.get(fp))
        self.assertEqual(len(os.listdir(dir_path)), 0)

    @unittest.skipUnless(HAS_SQLITE, "SQLite not available")
    def test_sqlite_pruning(self):
        db_path = os.path.join(self.tmp_dir, "test_pruning.db")
        # Patch limits for testing
        with patch("plugin.writer.locale.grammar_persistence.CACHE_LIMIT", 5), \
             patch("plugin.writer.locale.grammar_persistence.PRUNE_TARGET", 2):
            p = SQLitePersistence(self.ctx, db_path)
            for i in range(10):
                txt = f"Sentence {i}"
                p.put(fingerprint_for_text(txt), "en-US", txt, [])
            
            p.prune()
            
            # Verify count is PRUNE_TARGET (2)
            import sqlite3
            with sqlite3.connect(db_path) as conn:
                count = conn.execute("SELECT count(*) FROM sentence_cache").fetchone()[0]
                self.assertEqual(count, 2)

    def test_json_pruning(self):
        dir_path = os.path.join(self.tmp_dir, "test_json_pruning.d")
        with patch("plugin.writer.locale.grammar_persistence.CACHE_LIMIT", 5), \
             patch("plugin.writer.locale.grammar_persistence.PRUNE_TARGET", 2):
            p = JSONPersistence(self.ctx, dir_path)
            for i in range(10):
                txt = f"Sentence {i}"
                p.put(fingerprint_for_text(txt), "en-US", txt, [])
            
            p.prune()
            
            self.assertEqual(len(os.listdir(dir_path)), 2)

    def test_factory_and_singleton(self):
        # Reset singleton for testing
        with patch("plugin.writer.locale.grammar_persistence._persistence_instance", None):
            with patch("plugin.framework.config.user_config_dir", return_value=self.tmp_dir):
                p = get_persistence(self.ctx)
                self.assertIsNotNone(p)
                p2 = get_persistence(self.ctx)
                self.assertIs(p, p2)
                
                if HAS_SQLITE:
                    self.assertIsInstance(p, SQLitePersistence)
                else:
                    self.assertIsInstance(p, JSONPersistence)

if __name__ == "__main__":
    unittest.main()
