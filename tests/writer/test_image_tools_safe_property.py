# WriterAgent - safe UNO property helpers for image_tools

from __future__ import annotations

from unittest.mock import MagicMock

from plugin.writer.images import image_tools


def test_has_uno_property_uses_property_set_info():
    psi = MagicMock()
    psi.hasPropertyByName.return_value = True
    obj = MagicMock()
    obj.getPropertySetInfo.return_value = psi
    assert image_tools._has_uno_property(obj, "GraphicURL") is True
    psi.hasPropertyByName.assert_called_once_with("GraphicURL")


def test_create_embedded_graphic_uses_safe_set_not_hasattr(monkeypatch):
    graphic = MagicMock()
    graphic.getPropertySetInfo.return_value = MagicMock()
    graphic.getPropertySetInfo.return_value.hasPropertyByName.return_value = True

    doc = MagicMock()
    doc.createInstance.return_value = graphic

    monkeypatch.setattr(image_tools, "_safe_set_property", lambda obj, name, value: name == "GraphicURL")
    monkeypatch.setattr(image_tools, "_graphic_from_provider", lambda ctx, url: None)

    result = image_tools._create_embedded_graphic(doc, "writer", "file:///tmp/x.png", ctx=MagicMock())
    assert result is graphic
