# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""MCP menu icon wiring: yaml declarations, manifest action_icons, asset URLs."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_mcp_module_yaml_declares_status_icons():
    text = (_REPO_ROOT / "plugin" / "mcp" / "module.yaml").read_text(encoding="utf-8")
    assert "server_status:" in text
    assert "icon: stopped" in text
    # Toggle is text-only; only Status shows a running/stopped icon.
    toggle_block, status_block = text.split("server_status:", 1)
    assert "icon:" not in toggle_block.split("toggle_server:", 1)[-1]


def test_manifest_mcp_action_icons():
    from plugin._manifest import MODULES

    mcp = next(m for m in MODULES if m["name"] == "mcp")
    assert mcp["action_icons"] == {"server_status": "stopped"}


def test_menu_icon_asset_url():
    from plugin.framework.uno_context import menu_icon_asset_url

    assert menu_icon_asset_url("file:///tmp/oxt", "stopped_16.png") == (
        "file:///tmp/oxt/assets/stopped_16.png"
    )
    assert menu_icon_asset_url("file:///tmp/oxt/", "running_16.png") == (
        "file:///tmp/oxt/assets/running_16.png"
    )


def test_status_icon_pngs_exist():
    assets = _REPO_ROOT / "extension" / "assets"
    for name in ("stopped_16.png", "running_16.png", "starting_16.png"):
        assert (assets / name).is_file(), name
