# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Unit tests for plugin.chatbot.panel_resize."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from plugin.tests.testing_utils import setup_uno_mocks

setup_uno_mocks()

from plugin.chatbot.panel_resize import _PanelResizeListener
from plugin.chatbot.rich_text_control import sidebar_content_right_edge


def _mock_control(x, y, width, height):
    ctrl = MagicMock()
    pos = SimpleNamespace(X=x, Y=y, Width=width, Height=height)

    def set_pos_size(nx, ny, nw, nh, _flags):
        pos.X, pos.Y, pos.Width, pos.Height = nx, ny, nw, nh

    ctrl.getPosSize.return_value = pos
    ctrl.setPosSize.side_effect = set_pos_size
    return ctrl


def _xdl_like_controls():
    """Positions from extension/WriterAgentDialogs/ChatPanelDialog.xdl."""
    return {
        "response": _mock_control(4, 16, 142, 110),
        "status": _mock_control(4, 128, 142, 10),
        "query": _mock_control(4, 152, 142, 30),
        "send": _mock_control(4, 186, 50, 15),
        "stop": _mock_control(56, 186, 50, 15),
        "clear": _mock_control(108, 186, 50, 15),
        "direct_image_check": _mock_control(4, 203, 78, 10),
        "web_research_check": _mock_control(84, 203, 78, 10),
        "model_label": _mock_control(4, 217, 142, 10),
        "model_selector": _mock_control(4, 229, 142, 14),
        "image_model_selector": _mock_control(4, 215, 142, 14),
        "base_size_label": _mock_control(4, 235, 20, 10),
        "base_size_input": _mock_control(25, 233, 40, 14),
        "aspect_ratio_selector": _mock_control(70, 233, 102, 14),
    }


class TestPanelResizeContentEdgeClamp:
    def test_comboboxes_clamp_to_sidebar_content_right_edge(self):
        controls = _xdl_like_controls()
        root = MagicMock()
        root.getPosSize.return_value = SimpleNamespace(Width=900, Height=500)
        root.getControl.side_effect = lambda name: controls.get(name)

        listener = _PanelResizeListener(controls)
        listener._width_negotiated = True
        listener.relayout_now(root)

        edge = sidebar_content_right_edge(root, controls["response"])
        clamped = ("query", "model_selector", "image_model_selector", "aspect_ratio_selector")
        for name in clamped:
            ps = controls[name].getPosSize()
            assert ps.X + ps.Width == edge, f"{name} right edge should match content edge"
            assert ps.Width < 200, f"{name} should not stretch to full panel width"
