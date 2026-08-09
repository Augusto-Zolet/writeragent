"""LibrePy bundle includes writeragent namespace stub, not full tool API."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.librepy_bundle_paths import collect_librepy_plugin_paths  # noqa: E402


def test_librepy_bundle_includes_writeragent_namespace():
    paths = collect_librepy_plugin_paths(str(_REPO_ROOT))
    assert "plugin/scripting/writeragent_namespace.py" in paths


def test_librepy_bundle_excludes_writeragent_api():
    paths = collect_librepy_plugin_paths(str(_REPO_ROOT))
    assert "plugin/scripting/writeragent_api.py" not in paths


def test_librepy_bundle_includes_settings_fields():
    paths = collect_librepy_plugin_paths(str(_REPO_ROOT))
    assert "plugin/chatbot/settings_fields.py" in paths
    assert "plugin/scripting/venv_probe_ui.py" in paths


def test_librepy_bundle_includes_ast_stmt_edit():
    """excel_py_convert/to_dag imports this; must ship in LibrePy.oxt allowlist."""
    paths = collect_librepy_plugin_paths(str(_REPO_ROOT))
    assert "plugin/framework/ast_stmt_edit.py" in paths


def test_librepy_bundle_includes_deal_shim():
    """constants and other framework modules import deal via deal_shim; must ship in LibrePy.oxt."""
    paths = collect_librepy_plugin_paths(str(_REPO_ROOT))
    assert "plugin/framework/deal_shim.py" in paths
