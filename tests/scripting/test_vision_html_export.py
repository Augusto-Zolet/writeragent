# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for vision HTML export helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from plugin.scripting.vision_html_export import (
    export_docling_to_html,
    html_from_paddle_regions,
    html_from_paddle_structure,
)


def test_html_from_paddle_regions_escapes_and_wraps():
    html = html_from_paddle_regions([{"text": "Line & one"}, {"text": "Line two"}])
    assert "<p>Line &amp; one</p>" in html
    assert "<p>Line two</p>" in html


def test_html_from_paddle_structure_table_and_heading():
    html = html_from_paddle_structure(
        [{"type": "section_header", "text": "Title", "box": [0, 0, 0, 0]}],
        [{"columns": ["A", "B"], "rows": [["1", "2"]]}],
    )
    assert "<h2>Title</h2>" in html
    assert "<table" in html
    assert "<th>A</th>" in html
    assert "<td>1</td>" in html


def test_export_docling_to_html_default():
    doc = MagicMock()
    doc.export_to_html.return_value = "<p><strong>Hi</strong></p>"
    fake = MagicMock()
    fake.ImageRefMode.EMBEDDED = "embedded"
    with patch("plugin.scripting.vision_html_export.importlib.import_module", return_value=fake):
        out = export_docling_to_html(doc, {})
    assert "strong" in out
    doc.export_to_html.assert_called_once()
