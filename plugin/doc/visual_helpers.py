# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared helpers for visual UNO objects across Writer, Calc, Draw, and Impress."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

WRITER_DOCUMENT_SERVICE = "com.sun.star.text.TextDocument"
WEB_DOCUMENT_SERVICE = "com.sun.star.text.WebDocument"
CALC_DOCUMENT_SERVICE = "com.sun.star.sheet.SpreadsheetDocument"
DRAW_DOCUMENT_SERVICE = "com.sun.star.drawing.DrawingDocument"
IMPRESS_DOCUMENT_SERVICE = "com.sun.star.presentation.PresentationDocument"

WRITER_GRAPHIC_SERVICE = "com.sun.star.text.TextGraphicObject"
TEXT_GRAPHIC_SERVICE = "com.sun.star.text.GraphicObject"
DRAW_GRAPHIC_SERVICE = "com.sun.star.drawing.GraphicObjectShape"

SHAPE_TOOL_UNO_SERVICES = [
    WRITER_DOCUMENT_SERVICE,
    CALC_DOCUMENT_SERVICE,
    DRAW_DOCUMENT_SERVICE,
    IMPRESS_DOCUMENT_SERVICE,
]


def get_visual_doc_type(doc: Any) -> str:
    """Return the visual-tool document label used by image and shape helpers.

    Delegates to :func:`plugin.doc.document_helpers.get_document_type` for the
    shared Writer/Calc/Draw/Impress map. Web documents are checked first because
    they also support TextDocument and would otherwise look like Writer.
    Unknown models keep the legacy ``\"writer\"`` default (not ``\"unknown\"``).
    """
    try:
        if doc.supportsService(WEB_DOCUMENT_SERVICE):
            return "web"
    except Exception:
        pass
    from plugin.doc.document_helpers import DocumentType, doc_type_label_for_enum, get_document_type

    doc_type = get_document_type(doc)
    if doc_type == DocumentType.UNKNOWN:
        return "writer"
    return doc_type_label_for_enum(doc_type)


def mm_to_units(width_mm: int | float, height_mm: int | float) -> tuple[int, int]:
    """Convert millimetres to LibreOffice 1/100 mm units, preserving legacy truncation."""
    return int(width_mm) * 100, int(height_mm) * 100


def px_to_units(width_px: int | float, height_px: int | float) -> tuple[int, int]:
    """Convert 96-DPI pixels to LibreOffice 1/100 mm units."""
    return int(width_px * 26.46), int(height_px * 26.46)


def units_to_px(width_units: int | float, height_units: int | float, *, minimum: int = 1) -> tuple[int, int]:
    """Convert LibreOffice 1/100 mm units to 96-DPI pixels."""
    width_px = int(width_units * 96 / 2540)
    height_px = int(height_units * 96 / 2540)
    return max(minimum, width_px), max(minimum, height_px)


def mm_to_px(width_mm: int | float, height_mm: int | float, *, minimum: int = 1) -> tuple[int, int]:
    width_units, height_units = mm_to_units(width_mm, height_mm)
    return units_to_px(width_units, height_units, minimum=minimum)


def has_uno_property(obj: Any, name: str) -> bool:
    """True when *name* exists on the UNO PropertySet.

    PyUNO can raise while probing missing properties, so visual tools should use
    PropertySetInfo rather than Python attribute checks for UNO properties.
    """
    try:
        psi = obj.getPropertySetInfo()
        if psi is not None and hasattr(psi, "hasPropertyByName"):
            return bool(psi.hasPropertyByName(name))
    except Exception:
        pass
    return False


def safe_set_property(obj: Any, name: str, value: Any) -> bool:
    if not has_uno_property(obj, name):
        return False
    try:
        obj.setPropertyValue(name, value)
        return True
    except Exception as ex:
        log.debug("safe_set_property %s failed: %s", name, ex)
        return False


def safe_try_method(obj: Any, method_name: str, *args: Any) -> bool:
    try:
        method = getattr(obj, method_name, None)
        if callable(method):
            method(*args)
            return True
    except Exception as ex:
        log.debug("safe_try_method %s failed: %s", method_name, ex)
    return False


def safe_get_property(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return obj.getPropertyValue(name)
    except Exception:
        return default


def is_graphic_object(obj: Any) -> bool:
    if obj is None:
        return False

    graphic = safe_get_property(obj, "Graphic")
    if graphic is not None:
        return True

    try:
        if obj.supportsService(WRITER_GRAPHIC_SERVICE) or obj.supportsService(TEXT_GRAPHIC_SERVICE) or obj.supportsService(DRAW_GRAPHIC_SERVICE):
            return True
    except Exception:
        pass

    # Some TextGraphicObject instances expose GraphicURL even when Graphic cannot
    # be read directly. The property read is guarded to avoid PyUNO probe errors.
    return safe_get_property(obj, "GraphicURL") is not None


def _controller_selection(model: Any) -> Any | None:
    try:
        controller = None
        try:
            controller = model.getCurrentController()
        except Exception:
            controller = getattr(model, "CurrentController", None)
        if controller is None:
            return None
        selection = None
        try:
            selection = controller.getSelection()
        except Exception:
            selection = None
        if selection is None:
            selection = getattr(controller, "Selection", None)
        return selection if selection else None
    except Exception as ex:
        log.debug("_controller_selection failed: %s", ex)
        return None


def _graphic_object_name(obj: Any) -> str:
    try:
        return str(obj.getName() or "").strip()
    except Exception:
        return ""


def selected_graphic_object(model: Any) -> Any | None:
    try:
        selection = _controller_selection(model)
        if not selection:
            return None
        if hasattr(selection, "getCount"):
            if selection.getCount() != 1:
                return None
            obj = selection.getByIndex(0)
        else:
            obj = selection
        return obj if is_graphic_object(obj) else None
    except Exception as ex:
        log.debug("selected_graphic_object failed: %s", ex)
        return None


def _anchor_start(graphic: Any) -> Any | None:
    try:
        anchor = graphic.getAnchor()
        if anchor is None:
            return None
        if hasattr(anchor, "getStart"):
            return anchor.getStart()
        return anchor
    except Exception:
        return None


def _sort_graphics_by_anchor(text: Any, pairs: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    """Stable document-order sort using ``compareRegionStarts`` on graphic anchors."""
    if len(pairs) <= 1 or text is None:
        return pairs

    def _cmp(a: tuple[str, Any], b: tuple[str, Any]) -> int:
        a_start = _anchor_start(a[1])
        b_start = _anchor_start(b[1])
        if a_start is None or b_start is None:
            return 0
        try:
            # compareRegionStarts(A,B): 1 if A before B → A should sort first → negative cmp.
            return -int(text.compareRegionStarts(a_start, b_start))
        except Exception:
            return 0

    from functools import cmp_to_key

    return sorted(pairs, key=cmp_to_key(_cmp))


def _graphics_in_text_range(doc: Any, range_obj: Any) -> list[tuple[str, Any]]:
    """Named graphics whose anchors fall inside *range_obj* (intervening text ignored)."""
    try:
        text = range_obj.getText()
        sel_start = range_obj.getStart()
        sel_end = range_obj.getEnd()
    except Exception:
        return []
    if text is None or sel_start is None or sel_end is None:
        return []

    found: list[tuple[str, Any]] = []
    for name, graphic in list_graphic_objects(doc):
        if not name:
            continue
        anchor_start = _anchor_start(graphic)
        if anchor_start is None:
            continue
        try:
            # sel_start <= anchor_start <= sel_end
            if text.compareRegionStarts(sel_start, anchor_start) < 0:
                continue
            if text.compareRegionStarts(anchor_start, sel_end) < 0:
                continue
            found.append((name, graphic))
        except Exception:
            continue
    return _sort_graphics_by_anchor(text, found)


def graphic_objects_in_selection(doc: Any) -> list[tuple[str, Any]]:
    """Return named ``(name, graphic)`` pairs covered by the current selection.

    Writer supports: a single selected graphic, multi-selected graphics, or a text
    range that contains embedded images (text in the range is ignored). Non-Writer
    documents return at most the single selected graphic (Calc multi stays out of scope).
    """
    try:
        selection = _controller_selection(doc)
        if not selection:
            return []

        if get_visual_doc_type(doc) != "writer":
            graphic = selected_graphic_object(doc)
            if graphic is None:
                return []
            name = _graphic_object_name(graphic)
            return [(name, graphic)] if name else []

        if hasattr(selection, "getCount"):
            graphics_from_sel: list[tuple[str, Any]] = []
            for i in range(selection.getCount()):
                obj = selection.getByIndex(i)
                if not is_graphic_object(obj):
                    continue
                name = _graphic_object_name(obj)
                if name:
                    graphics_from_sel.append((name, obj))
            if graphics_from_sel:
                text = None
                try:
                    anchor = graphics_from_sel[0][1].getAnchor()
                    text = anchor.getText() if anchor is not None else None
                except Exception:
                    text = None
                return _sort_graphics_by_anchor(text, graphics_from_sel)

            if selection.getCount() > 0:
                range_obj = selection.getByIndex(0)
                if hasattr(range_obj, "getStart") and hasattr(range_obj, "getEnd"):
                    return _graphics_in_text_range(doc, range_obj)
            return []

        if is_graphic_object(selection):
            name = _graphic_object_name(selection)
            return [(name, selection)] if name else []

        if hasattr(selection, "getStart") and hasattr(selection, "getEnd"):
            return _graphics_in_text_range(doc, selection)
        return []
    except Exception as ex:
        log.debug("graphic_objects_in_selection failed: %s", ex)
        return []


def get_active_draw_page(doc: Any, doc_type: str | None = None) -> Any | None:
    """Return the active draw page for Calc, Draw, or Impress visual objects."""
    inside = doc_type or get_visual_doc_type(doc)
    try:
        controller = doc.CurrentController
    except Exception:
        try:
            controller = doc.getCurrentController()
        except Exception:
            controller = None
    if controller is None:
        return None

    if inside == "calc":
        sheet = None
        try:
            sheet = controller.ActiveSheet
        except Exception:
            pass
        if sheet is None:
            try:
                sheet = controller.getActiveSheet()
            except Exception:
                sheet = None
        if sheet is None:
            return None
        try:
            return sheet.getDrawPage()
        except Exception:
            try:
                return sheet.DrawPage
            except Exception:
                return None

    try:
        page = controller.CurrentPage
    except Exception:
        page = None
    if page is not None:
        return page
    try:
        return controller.getCurrentPage()
    except Exception:
        pass
    try:
        pages = doc.getDrawPages()
        if pages.getCount() > 0:
            return pages.getByIndex(0)
    except Exception:
        pass
    return None


def list_graphic_objects(doc: Any, doc_type: str | None = None) -> list[tuple[str, Any]]:
    """Return ``(name, object)`` pairs for document-level graphic objects."""
    inside = doc_type or get_visual_doc_type(doc)
    graphics: list[tuple[str, Any]] = []

    if inside == "calc":
        draw_page = get_active_draw_page(doc, inside)
        if draw_page is None:
            return graphics
        try:
            for i in range(draw_page.getCount()):
                shape = draw_page.getByIndex(i)
                if is_graphic_object(shape):
                    graphics.append((shape.getName(), shape))
        except Exception as ex:
            log.debug("list_graphic_objects calc failed: %s", ex)
        return graphics

    if inside in ("draw", "impress"):
        draw_page = get_active_draw_page(doc, inside)
        if draw_page is None:
            return graphics
        try:
            for i in range(draw_page.getCount()):
                shape = draw_page.getByIndex(i)
                if is_graphic_object(shape):
                    graphics.append((shape.getName(), shape))
        except Exception as ex:
            log.debug("list_graphic_objects draw/impress failed: %s", ex)
        return graphics

    try:
        get_graphics = getattr(doc, "getGraphicObjects", None)
        if not callable(get_graphics):
            return graphics
        graphic_objects: Any = get_graphics()
        for name in graphic_objects.getElementNames():
            graphics.append((name, graphic_objects.getByName(name)))
    except Exception as ex:
        log.debug("list_graphic_objects writer failed: %s", ex)
    return graphics


def get_graphic_object_by_name(doc: Any, image_name: str, doc_type: str | None = None) -> Any | None:
    if not image_name:
        return None
    for name, graphic in list_graphic_objects(doc, doc_type=doc_type):
        if name == image_name:
            return graphic
    return None


def graphic_from_object(obj: Any) -> Any | None:
    """Return the UNO Graphic for a text graphic or draw GraphicObjectShape."""
    if obj is None:
        return None
    graphic = safe_get_property(obj, "Graphic")
    if graphic is not None:
        return graphic
    try:
        graphic = obj.Graphic
        return graphic if graphic is not None else None
    except Exception as ex:
        log.debug("graphic_from_object missing Graphic: %s", ex)
    return None
