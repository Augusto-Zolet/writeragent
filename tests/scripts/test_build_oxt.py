# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for OXT build path exclusions."""

from __future__ import annotations

import os

from scripts.build_oxt import GENERATED_INCLUDES, remap_path, should_exclude

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_python_logo_dev_sources_excluded_from_oxt():
    assert should_exclude("extension/assets/python_logo.svg") is True
    assert should_exclude("extension/assets/python_logo.NOTICE") is True
    assert should_exclude("extension/assets/python_32.png") is False


def test_generated_includes_single_dialogs_tree():
    """Lowercase dialogs/ must not be packaged — it collides with Dialogs/ on Windows."""
    assert "build/generated/Dialogs/" in GENERATED_INCLUDES
    assert "build/generated/dialogs/" not in GENERATED_INCLUDES
    lower = [p for p in GENERATED_INCLUDES if p.replace("\\", "/").rstrip("/").endswith("dialogs")]
    assert lower == [], "GENERATED_INCLUDES must not list a lowercase dialogs/ path: %s" % lower


def test_remap_path_chat_panel_and_generated_dialogs():
    assert remap_path("extension/Dialogs/ChatPanelDialog.xdl") == "Dialogs/ChatPanelDialog.xdl"
    assert remap_path("build/generated/Dialogs/SettingsDialog.xdl") == "Dialogs/SettingsDialog.xdl"
    assert remap_path("build/generated/Dialogs/chatbot.xdl") == "Dialogs/chatbot.xdl"


def test_extension_chat_panel_xdl_exists():
    path = os.path.join(PROJECT_ROOT, "extension", "Dialogs", "ChatPanelDialog.xdl")
    assert os.path.isfile(path), "sidebar XDL missing at %s" % path
