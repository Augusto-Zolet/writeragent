"""Import-graph ownership tests for the sidebar factory (no UNO import)."""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FACTORY = _REPO_ROOT / "plugin" / "chatbot" / "panel_factory.py"
_DIALOG_VIEWS = _REPO_ROOT / "plugin" / "chatbot" / "dialog_views.py"
_SEND_HANDLERS = _REPO_ROOT / "plugin" / "chatbot" / "send_handlers.py"
_TOOL_LOOP = _REPO_ROOT / "plugin" / "chatbot" / "tool_loop.py"
_TOOL_LOOP_ACTIONS = _REPO_ROOT / "plugin" / "chatbot" / "tool_loop_actions.py"


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names.add(module)
            for alias in node.names:
                names.add(alias.name)
                if module:
                    names.add("%s.%s" % (module, alias.name))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


def _calls_name(path: Path, func_name: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == func_name:
            return True
        if isinstance(func, ast.Attribute) and func.attr == func_name:
            return True
    return False


def test_panel_factory_does_not_import_or_call_chat_context_builder():
    """Factory wires XDL/controls. Document context is ChatSession / send / tool_loop."""
    imported = _imported_names(_FACTORY)
    assert "get_document_context_for_chat" not in imported
    assert "plugin.doc.document_helpers.get_document_context_for_chat" not in imported
    assert not _calls_name(_FACTORY, "get_document_context_for_chat")


def test_panel_factory_mode_switch_delegates_context_refresh_to_session():
    src = _FACTORY.read_text(encoding="utf-8")
    assert "session.refresh_document_context(model, self.ctx)" in src
    assert "_refresh_doc_session_context" not in src


def test_dialog_views_does_not_import_tool_loop():
    imported = _imported_names(_DIALOG_VIEWS)
    assert "plugin.chatbot.tool_loop" not in imported
    assert "tool_loop" not in imported


def test_send_and_tool_loop_do_not_import_panel_factory():
    for path in (_SEND_HANDLERS, _TOOL_LOOP, _TOOL_LOOP_ACTIONS):
        imported = _imported_names(path)
        assert "plugin.chatbot.panel_factory" not in imported
        assert "panel_factory" not in imported


def test_send_and_tool_loop_refresh_via_session_not_builder():
    """Send / mid-loop refresh go through ChatSession.refresh_document_context."""
    for path in (_SEND_HANDLERS, _TOOL_LOOP, _TOOL_LOOP_ACTIONS):
        imported = _imported_names(path)
        assert "get_document_context_for_chat" not in imported
        assert "plugin.doc.document_helpers.get_document_context_for_chat" not in imported
        src = path.read_text(encoding="utf-8")
        assert "refresh_document_context" in src


class _MockDisposedException(Exception):
    """Name must include DisposedException so is_disposed_exception matches."""


def _thin_panel_element():
    from plugin.chatbot.panel_factory import ChatPanelElement

    el = object.__new__(ChatPanelElement)
    el.send_listener = None
    el.toolpanel = None
    el.m_panelRootWindow = None
    el.rich_text_widget = None
    return el


def test_disposing_swallows_disposed_focus_restore():
    from unittest.mock import patch

    el = _thin_panel_element()
    with patch(
        "plugin.framework.uno_context.set_default_focus_restore",
        side_effect=_MockDisposedException("bridge gone"),
    ):
        el.disposing(None)
    assert el.rich_text_widget is None


def test_disposing_swallows_disposed_remove_window_listener():
    from unittest.mock import MagicMock, patch

    el = _thin_panel_element()
    root = MagicMock()
    root.removeWindowListener.side_effect = _MockDisposedException("window gone")
    tp = MagicMock()
    tp.resize_listener = MagicMock()
    el.toolpanel = tp
    el.m_panelRootWindow = root
    with patch("plugin.framework.uno_context.set_default_focus_restore"):
        el.disposing(None)
    root.removeWindowListener.assert_called_once()


def test_refresh_mode_selector_disposed_still_updates_backend_indicator():
    from unittest.mock import MagicMock, patch

    el = _thin_panel_element()
    el.ctx = MagicMock()
    el._in_refresh_controls = False
    root = MagicMock()

    def get_control(name):
        if name == "chat_mode_selector":
            return MagicMock()
        return None

    root.getControl.side_effect = get_control
    el.m_panelRootWindow = root
    el._update_backend_indicator = MagicMock()
    with patch("plugin.chatbot.config_ui_helpers.populate_combobox_with_lru"), patch(
        "plugin.chatbot.config_ui_helpers.populate_image_model_selector"
    ), patch("plugin.chatbot.panel_factory.get_text_model", return_value="m"), patch(
        "plugin.chatbot.panel_factory.get_config", return_value=""
    ), patch(
        "plugin.chatbot.panel_factory.get_current_endpoint", return_value=""
    ), patch(
        "plugin.chatbot.panel_factory.get_optional_control",
        side_effect=lambda _root, name: MagicMock() if name == "chat_mode_selector" else None,
    ), patch.object(
        el, "_get_document_model", side_effect=_MockDisposedException("model disposed")
    ):
        el._refresh_controls_from_config()
    el._update_backend_indicator.assert_called_once_with(root)
