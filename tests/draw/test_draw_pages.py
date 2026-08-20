# WriterAgent — unit tests for core slide lifecycle tools
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest.mock import MagicMock, patch

from plugin.draw.pages import DuplicateSlide, MoveSlide, RenameSlide


def _ctx():
    return MagicMock()


def test_duplicate_slide_ok():
    ctx = _ctx()
    with patch("plugin.draw.bridge.DrawBridge") as bridge_cls:
        bridge = bridge_cls.return_value
        bridge.get_pages.return_value.getCount.return_value = 2
        bridge.get_active_page_index.return_value = 1
        out = DuplicateSlide().execute(ctx, page=0)
    assert out["status"] == "ok"
    bridge.duplicate_slide.assert_called_once_with(0, switch=True)
    assert out["active_page_index"] == 1


def test_duplicate_slide_out_of_range():
    ctx = _ctx()
    with patch("plugin.draw.bridge.DrawBridge") as bridge_cls:
        bridge_cls.return_value.get_pages.return_value.getCount.return_value = 1
        out = DuplicateSlide().execute(ctx, page=5)
    assert out["status"] == "error"


def test_move_slide_failure():
    ctx = _ctx()
    with patch("plugin.draw.bridge.DrawBridge") as bridge_cls:
        bridge_cls.return_value.move_slide.return_value = False
        out = MoveSlide().execute(ctx, from_page=0, to_page=2)
    assert out["status"] == "error"


def test_move_slide_ok():
    ctx = _ctx()
    with patch("plugin.draw.bridge.DrawBridge") as bridge_cls:
        bridge = bridge_cls.return_value
        bridge.move_slide.return_value = True
        bridge.get_active_page_index.return_value = 1
        out = MoveSlide().execute(ctx, from_page=0, to_page=1)
    assert out["status"] == "ok"
    bridge.move_slide.assert_called_once_with(0, 1)


def test_rename_slide_ok():
    ctx = _ctx()
    with patch("plugin.draw.bridge.DrawBridge") as bridge_cls:
        bridge = bridge_cls.return_value
        bridge.get_pages.return_value.getCount.return_value = 3
        bridge.rename_slide.return_value = True
        bridge.get_active_page_index.return_value = 0
        out = RenameSlide().execute(ctx, page=2, name="Agenda")
    assert out["status"] == "ok"
    assert out["name"] == "Agenda"
    bridge.rename_slide.assert_called_once_with(2, "Agenda")


def test_rename_slide_missing_name():
    out = RenameSlide().execute(_ctx(), page=0, name="")
    assert out["status"] == "error"
