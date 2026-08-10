# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Tests for the Gemini CLI ACP backend adapter."""

import unittest
from unittest.mock import patch

from plugin.chatbot.send_handlers import _agent_backend_label
from plugin.agent_backend.gemini_simple import GeminiBackend


class TestGeminiBinaryDiscovery(unittest.TestCase):
    """Test binary / identity hooks used by ACPBackend._find_binary()."""

    def test_binary_name_is_gemini(self):
        backend = GeminiBackend()
        self.assertEqual(backend.get_binary_name(), "gemini")

    def test_display_name(self):
        backend = GeminiBackend()
        self.assertEqual(backend.get_display_name(), "Gemini CLI (ACP)")

    def test_agent_name(self):
        backend = GeminiBackend()
        self.assertEqual(backend.get_agent_name(), "gemini")


class TestGeminiBackendInit(unittest.TestCase):
    """Test backend initialization."""

    def test_backend_id(self):
        backend = GeminiBackend()
        self.assertEqual(backend.backend_id, "gemini")
        self.assertEqual(backend.get_display_name(), "Gemini CLI (ACP)")


class TestIsAvailable(unittest.TestCase):
    """Test availability check."""

    @patch("os.path.isfile", return_value=True)
    @patch("shutil.which", return_value="/usr/bin/gemini")
    def test_available_when_gemini_in_path(self, mock_which, mock_isfile):
        backend = GeminiBackend()
        self.assertTrue(backend.is_available(None))
        self.assertEqual(backend._extra_args, ["--acp"])

    @patch("shutil.which", return_value=None)
    @patch("os.path.isfile", return_value=False)
    def test_unavailable_when_no_binary(self, mock_isfile, mock_which):
        backend = GeminiBackend()
        self.assertFalse(backend.is_available(None))

    @patch("os.path.isfile", side_effect=lambda p: p == "/usr/bin/gemini")
    @patch(
        "shutil.which",
        side_effect=lambda name: "/usr/bin/gemini" if name == "gemini" else None,
    )
    def test_available_when_gemini_cli_in_path(self, mock_which, mock_isfile):
        """Official install uses `gemini --acp`."""
        backend = GeminiBackend()
        self.assertTrue(backend.is_available(None))
        self.assertEqual(backend._binary_path, "/usr/bin/gemini")
        self.assertEqual(backend._extra_args, ["--acp"])


class TestGeminiEnvVars(unittest.TestCase):
    """Forward WriterAgent endpoint key as GEMINI_API_KEY for headless ACP."""

    @patch("plugin.agent_backend.gemini_simple.get_api_key_for_endpoint", return_value="test-key")
    @patch("plugin.agent_backend.gemini_simple.get_current_endpoint", return_value="https://generativelanguage.googleapis.com")
    def test_get_env_vars_forwards_key(self, mock_endpoint, mock_key):
        backend = GeminiBackend()
        self.assertEqual(backend.get_env_vars(), {"GEMINI_API_KEY": "test-key"})

    @patch("plugin.agent_backend.gemini_simple.get_api_key_for_endpoint", return_value=None)
    @patch("plugin.agent_backend.gemini_simple.get_current_endpoint", return_value="")
    def test_get_env_vars_empty_without_key(self, mock_endpoint, mock_key):
        backend = GeminiBackend()
        self.assertEqual(backend.get_env_vars(), {})


class TestAgentBackendDisplayLabel(unittest.TestCase):
    """Error messages must use get_display_name(), not inherited display_name."""

    def test_label_gemini(self):
        self.assertEqual(_agent_backend_label(GeminiBackend(), "gemini"), "Gemini CLI (ACP)")


if __name__ == "__main__":
    unittest.main()
