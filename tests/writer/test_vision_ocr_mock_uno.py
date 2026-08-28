# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""UNO tests: mock OCR through run_and_insert_vision_for_selection + Writer insert placement."""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
import zlib
from typing import Any
from unittest.mock import patch

from plugin.doc.visual_helpers import list_graphic_objects
from plugin.testing_runner import native_test
from plugin.tests.testing_utils import with_native_doc
from plugin.vision.vision_runner import run_and_insert_vision_for_selection
from plugin.writer.images.image_tools import insert_image_at_locator

_PNG_COLORS = ((255, 0, 0), (0, 255, 0), (0, 0, 255))


def _make_unique_png_bytes(r: int, g: int, b: int) -> bytes:
    """Minimal 1x1 RGB PNG so each embedded graphic exports distinct bytes."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00" + bytes([r, g, b])
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


def _write_temp_png(r: int, g: int, b: int) -> str:
    fd, path = tempfile.mkstemp(suffix=".png", prefix="wa_vision_test_")
    os.close(fd)
    with open(path, "wb") as handle:
        handle.write(_make_unique_png_bytes(r, g, b))
    return path


def _assert_strict_order(body: str, *needles: str) -> None:
    indices: list[int] = []
    for needle in needles:
        idx = body.find(needle)
        assert idx >= 0, f"{needle!r} not found in {body!r}"
        assert body.count(needle) == 1, f"{needle!r} appears {body.count(needle)} times in {body!r}"
        indices.append(idx)
    for left, right in zip(indices, indices[1:]):
        assert left < right, f"expected strict order {needles!r}, got {body!r}"


def _assert_graphics_named(doc: Any, names: list[str]) -> None:
    found = {name for name, _unused in list_graphic_objects(doc)}
    for name in names:
        assert name in found, f"graphic {name!r} missing; have {found!r}"


def _make_fake_run_vision(captured: list[tuple[str, str]]):
    def fake_run_vision(_ctx: Any, spec: dict[str, Any], png_bytes: bytes, context: dict[str, Any] | None = None):
        params = spec.get("params") if isinstance(spec, dict) else {}
        image_name = str((params or {}).get("image_name") or "")
        if not image_name and context:
            image_name = str(context.get("image_name") or "")
        digest = hashlib.sha256(png_bytes).hexdigest()[:8]
        token = f"OCR_{image_name}_{digest}"
        captured.append((image_name, token))
        return {
            "status": "ok",
            "helper": "extract_text",
            "full_text": token,
            "html": f"<p>{token}</p>",
            "regions": [{"box": [0, 0, 1, 1], "text": token, "confidence": 1.0}],
            "metrics": {"line_count": 1, "mean_confidence": 1.0},
            "warnings": [],
        }

    return fake_run_vision


def _run_mock_ocr(ctx: Any, doc: Any) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    captured: list[tuple[str, str]] = []
    with patch("plugin.vision.vision_runner.run_vision", side_effect=_make_fake_run_vision(captured)):
        result = run_and_insert_vision_for_selection(ctx, doc, helper="extract_text", params={})
    return result, captured


def _select_whole_document(doc: Any) -> None:
    view = doc.getCurrentController().getViewCursor()
    view.gotoStart(False)
    view.gotoEnd(True)


def _select_range_to_label_start(doc: Any, label: str) -> None:
    sd = doc.createSearchDescriptor()
    sd.SearchString = label
    found = doc.findFirst(sd)
    assert found is not None, f"label {label!r} not found"
    view = doc.getCurrentController().getViewCursor()
    view.gotoStart(False)
    view.gotoRange(found.getStart(), True)


def _build_labeled_fixture(ctx: Any, doc: Any, image_count: int) -> dict[str, Any]:
    assert 1 <= image_count <= 3
    text = doc.getText()
    text.setString("")
    cursor = text.createTextCursor()
    graphics: list[Any] = []
    temp_paths: list[str] = []

    text.insertString(cursor, "T0", False)
    cursor.gotoEnd(False)

    for idx in range(image_count):
        path = _write_temp_png(*_PNG_COLORS[idx])
        temp_paths.append(path)
        graphic = insert_image_at_locator(ctx, doc, path, width_mm=12, height_mm=12)
        assert graphic is not None, f"failed to insert image {idx}"
        graphics.append(graphic)
        cursor.gotoEnd(False)
        if idx < image_count - 1:
            text.insertString(cursor, f"T{idx + 1}", False)
            cursor.gotoEnd(False)

    text.insertString(cursor, "T3", False)

    return {
        "graphics": graphics,
        "names": [graphic.getName() for graphic in graphics],
        "temp_paths": temp_paths,
    }


def _build_images_only_fixture(ctx: Any, doc: Any, image_count: int = 2) -> dict[str, Any]:
    text = doc.getText()
    text.setString("")
    cursor = text.createTextCursor()
    graphics: list[Any] = []
    temp_paths: list[str] = []

    for idx in range(image_count):
        path = _write_temp_png(*_PNG_COLORS[idx])
        temp_paths.append(path)
        graphic = insert_image_at_locator(ctx, doc, path, width_mm=12, height_mm=12)
        assert graphic is not None, f"failed to insert image {idx}"
        graphics.append(graphic)
        cursor.gotoEnd(False)

    return {
        "graphics": graphics,
        "names": [graphic.getName() for graphic in graphics],
        "temp_paths": temp_paths,
    }


def _cleanup_temp_paths(temp_paths: list[str]) -> None:
    for path in temp_paths:
        try:
            os.unlink(path)
        except OSError:
            pass


def _ocr_token_for_name(captured: list[tuple[str, str]], name: str) -> str:
    for image_name, token in captured:
        if image_name == name:
            return token
    raise AssertionError(f"no OCR token captured for {name!r}; got {captured!r}")


@native_test
@with_native_doc("writer")
def test_mock_ocr_single_graphic_click(ctx, doc):
    fixture = _build_labeled_fixture(ctx, doc, image_count=1)
    try:
        doc.getCurrentController().select(fixture["graphics"][0])
        result, captured = _run_mock_ocr(ctx, doc)
        assert result["images_processed"] == 1
        body = doc.getText().getString()
        token = _ocr_token_for_name(captured, fixture["names"][0])
        _assert_strict_order(body, "T0", token, "T3")
        _assert_graphics_named(doc, fixture["names"])
    finally:
        _cleanup_temp_paths(fixture["temp_paths"])


@native_test
@with_native_doc("writer")
def test_mock_ocr_range_with_one_image(ctx, doc):
    fixture = _build_labeled_fixture(ctx, doc, image_count=1)
    try:
        _select_whole_document(doc)
        result, captured = _run_mock_ocr(ctx, doc)
        assert result["images_processed"] == 1
        body = doc.getText().getString()
        token = _ocr_token_for_name(captured, fixture["names"][0])
        _assert_strict_order(body, "T0", token, "T3")
        _assert_graphics_named(doc, fixture["names"])
    finally:
        _cleanup_temp_paths(fixture["temp_paths"])


@native_test
@with_native_doc("writer")
def test_mock_ocr_two_images_preserves_intervening_text(ctx, doc):
    fixture = _build_labeled_fixture(ctx, doc, image_count=2)
    try:
        _select_whole_document(doc)
        result, captured = _run_mock_ocr(ctx, doc)
        assert result["images_processed"] == 2
        body = doc.getText().getString()
        token_a = _ocr_token_for_name(captured, fixture["names"][0])
        token_b = _ocr_token_for_name(captured, fixture["names"][1])
        _assert_strict_order(body, "T0", token_a, "T1", token_b, "T3")
        _assert_graphics_named(doc, fixture["names"])
    finally:
        _cleanup_temp_paths(fixture["temp_paths"])


@native_test
@with_native_doc("writer")
def test_mock_ocr_three_images_with_text_between(ctx, doc):
    fixture = _build_labeled_fixture(ctx, doc, image_count=3)
    try:
        _select_whole_document(doc)
        result, captured = _run_mock_ocr(ctx, doc)
        assert result["images_processed"] == 3
        body = doc.getText().getString()
        token_a = _ocr_token_for_name(captured, fixture["names"][0])
        token_b = _ocr_token_for_name(captured, fixture["names"][1])
        token_c = _ocr_token_for_name(captured, fixture["names"][2])
        _assert_strict_order(body, "T0", token_a, "T1", token_b, "T2", token_c, "T3")
        _assert_graphics_named(doc, fixture["names"])
    finally:
        _cleanup_temp_paths(fixture["temp_paths"])


@native_test
@with_native_doc("writer")
def test_mock_ocr_partial_range_excludes_third_image(ctx, doc):
    fixture = _build_labeled_fixture(ctx, doc, image_count=3)
    try:
        _select_range_to_label_start(doc, "T2")
        result, captured = _run_mock_ocr(ctx, doc)
        assert result["images_processed"] == 2
        body = doc.getText().getString()
        token_a = _ocr_token_for_name(captured, fixture["names"][0])
        token_b = _ocr_token_for_name(captured, fixture["names"][1])
        _assert_strict_order(body, "T0", token_a, "T1", token_b, "T2", "T3")
        excluded = [token for image_name, token in captured if image_name == fixture["names"][2]]
        assert not excluded, f"unexpected OCR for excluded image: {excluded!r}"
        _assert_graphics_named(doc, fixture["names"])
    finally:
        _cleanup_temp_paths(fixture["temp_paths"])


@native_test
@with_native_doc("writer")
def test_mock_ocr_images_only(ctx, doc):
    fixture = _build_images_only_fixture(ctx, doc, image_count=2)
    try:
        _select_whole_document(doc)
        result, captured = _run_mock_ocr(ctx, doc)
        assert result["images_processed"] == 2
        body = doc.getText().getString()
        token_a = _ocr_token_for_name(captured, fixture["names"][0])
        token_b = _ocr_token_for_name(captured, fixture["names"][1])
        _assert_strict_order(body, token_a, token_b)
        _assert_graphics_named(doc, fixture["names"])
    finally:
        _cleanup_temp_paths(fixture["temp_paths"])
