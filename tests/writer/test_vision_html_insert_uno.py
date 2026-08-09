# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""UNO tests: vision OCR HTML insert preserves heading weight/size in Writer."""

from __future__ import annotations

from plugin.testing_runner import native_test
from plugin.writer.format import insert_content_at_position
from plugin.tests.testing_utils import with_native_doc

# Frozen post-process fixture (same shape as prepare_html_for_lo_import output).
_VISION_HTML_FIXTURE = (
    '<h2 style="font-size: 14pt; font-weight: bold;color: #333;">SECTION HEADING</h2>'
    '<p style="font-family: Arial, sans-serif; line-height: 1.6;">Body paragraph text.</p>'
)


def _is_bold_char_weight(wv) -> bool:
    if wv is None:
        return False
    try:
        from com.sun.star.awt import FontWeight

        if wv == FontWeight.BOLD:
            return True
    except Exception:
        pass
    try:
        return float(wv) >= 135.0
    except (TypeError, ValueError):
        return False


def _first_char_props_at_search(doc, needle: str) -> tuple[float | None, float | None]:
    sd = doc.createSearchDescriptor()
    sd.SearchString = needle
    found = doc.findFirst(sd)
    if found is None:
        return None, None
    text_obj = found.getText()
    cursor = text_obj.createTextCursorByRange(found.getStart())
    try:
        cursor.goRight(1, True)
        weight = cursor.getPropertyValue("CharWeight")
        height = cursor.getPropertyValue("CharHeight")
        return float(weight), float(height)
    except Exception:
        return None, None


@native_test
@with_native_doc("writer")
def test_vision_html_insert_heading_bolder_and_larger_than_body(ctx, doc):
    insert_content_at_position(doc, ctx, _VISION_HTML_FIXTURE, "end")
    full_text = doc.getText().getString()
    assert "SECTION HEADING" in full_text, f"heading text missing: {full_text!r}"
    assert "Body paragraph" in full_text, f"body text missing: {full_text!r}"

    heading_weight, heading_height = _first_char_props_at_search(doc, "SECTION HEADING")
    body_weight, body_height = _first_char_props_at_search(doc, "Body paragraph")

    assert heading_weight is not None, "heading paragraph not found after HTML import"
    assert body_weight is not None, "body paragraph not found after HTML import"
    assert _is_bold_char_weight(heading_weight), f"expected bold heading, CharWeight={heading_weight!r}"
    assert not _is_bold_char_weight(body_weight), f"expected normal body weight, CharWeight={body_weight!r}"
    assert heading_height > body_height, (
        f"expected heading CharHeight ({heading_height}) > body ({body_height})"
    )
