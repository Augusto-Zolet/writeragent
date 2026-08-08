# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for OXT build path exclusions."""

from __future__ import annotations

import os

from scripts.build_oxt import GENERATED_INCLUDES, remap_path, should_exclude, sync_vendor_into_lib

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


def test_sync_vendor_into_lib_copies_isodate(tmp_path):
    """Hot-deploy needs isodate under plugin/lib or datetime_wire fails to import."""
    vendor = tmp_path / "vendor"
    (vendor / "isodate").mkdir(parents=True)
    (vendor / "isodate" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (vendor / "isodate-0.7.2.dist-info").mkdir()
    (vendor / ".cache").mkdir()
    lib = tmp_path / "plugin" / "lib"
    n = sync_vendor_into_lib(str(vendor), str(lib), prune_websockets=False)
    assert n == 1
    assert (lib / "isodate" / "__init__.py").is_file()
    assert not (lib / "isodate-0.7.2.dist-info").exists()
    assert not (lib / ".cache").exists()
    # Replace existing tree on re-sync
    (lib / "isodate" / "stale.py").write_text("stale\n", encoding="utf-8")
    sync_vendor_into_lib(str(vendor), str(lib), prune_websockets=False)
    assert not (lib / "isodate" / "stale.py").exists()
