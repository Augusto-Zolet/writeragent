# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""get_page_objects must not clone the view cursor through the body XText.

jumpToEndOfPage can land inside a table cell. Body createTextCursorByRange then
raises RuntimeException: End of content node doesn't have the proper start node.
"""
from unittest.mock import MagicMock

from plugin.writer.structural import GetPageObjects


def _empty_named_collection():
    coll = MagicMock()
    coll.getElementNames.return_value = ()
    return coll


def test_scan_page_does_not_clone_via_body_text():
    """Shapes use the view-cursor page, not body createTextCursorByRange at page end."""
    tool = GetPageObjects()
    body = MagicMock()
    body.createTextCursorByRange.side_effect = RuntimeError(
        "End of content node doesn't have the proper start node"
    )
    doc = MagicMock()
    doc.getText.return_value = body
    doc.getGraphicObjects.return_value = _empty_named_collection()
    doc.getTextTables.return_value = _empty_named_collection()
    doc.getTextFrames.return_value = _empty_named_collection()
    draw = MagicMock()
    draw.getCount.return_value = 0
    doc.getDrawPage.return_value = draw

    vc = MagicMock()
    vc.getPage.return_value = 1
    vc.jumpToPage.return_value = True

    result = tool._scan_page(MagicMock(), doc, vc, 1)
    assert result == {"images": [], "tables": [], "frames": [], "shapes": []}
    body.createTextCursorByRange.assert_not_called()
    vc.jumpToEndOfPage.assert_not_called()


def test_scan_page_includes_paragraph_anchored_shape_on_page(monkeypatch):
    import com.sun.star.text.TextContentAnchorType as anchor_types

    at_para = object()
    monkeypatch.setattr(anchor_types, "AT_PAGE", object())
    monkeypatch.setattr(anchor_types, "AT_PARAGRAPH", at_para)
    monkeypatch.setattr(anchor_types, "AT_CHARACTER", object())
    monkeypatch.setattr(anchor_types, "AS_CHARACTER", object())

    tool = GetPageObjects()
    doc = MagicMock()
    doc.getGraphicObjects.return_value = _empty_named_collection()
    doc.getTextTables.return_value = _empty_named_collection()
    doc.getTextFrames.return_value = _empty_named_collection()

    shape = MagicMock()
    shape.getPropertyValue.side_effect = lambda name: at_para if name == "AnchorType" else 1
    shape.getShapeType.return_value = "com.sun.star.drawing.RectangleShape"
    shape.Name = "Box"
    shape.getString.return_value = "label"
    pos = MagicMock(X=1, Y=2)
    size = MagicMock(Width=3, Height=4)
    shape.getPosition.return_value = pos
    shape.getSize.return_value = size

    draw = MagicMock()
    draw.getCount.return_value = 1
    draw.getByIndex.return_value = shape
    doc.getDrawPage.return_value = draw

    vc = MagicMock()
    vc.getPage.return_value = 2

    result = tool._scan_page(MagicMock(), doc, vc, 2)
    assert len(result["shapes"]) == 1
    assert result["shapes"][0]["name"] == "Box"
    vc.gotoRange.assert_called_once()
