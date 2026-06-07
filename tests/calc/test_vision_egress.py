# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for Calc vision HTML egress."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from plugin.calc.vision_egress import calc_output_anchor_from_graphic, insert_vision_html_into_calc
from plugin.framework.errors import ToolExecutionError


def test_calc_output_anchor_from_graphic_no_selection():
    with patch("plugin.calc.vision_egress._get_selected_graphic_object", return_value=(None, None)):
        with pytest.raises(ToolExecutionError) as exc:
            calc_output_anchor_from_graphic(MagicMock())
        assert exc.value.code == "NO_IMAGE_SELECTED"


def test_calc_output_anchor_from_graphic_returns_row_below():
    shape = MagicMock()
    anchor = MagicMock()
    anchor.getCellAddress.return_value = MagicMock(Column=2, Row=4)
    shape.getPropertyValue.return_value = anchor

    with patch("plugin.calc.vision_egress._get_selected_graphic_object", return_value=(shape, "calc")):
        col, row = calc_output_anchor_from_graphic(MagicMock())
    assert col == 2
    assert row == 5


@patch("plugin.calc.vision_egress.insert_cell_html_rich")
@patch("plugin.calc.vision_egress.calc_output_anchor_from_graphic", return_value=(1, 3))
def test_insert_vision_html_into_calc(mock_anchor, mock_rich):
    doc = MagicMock()
    ctx = MagicMock()
    insert_vision_html_into_calc(doc, ctx, "<p>hello</p>")
    mock_rich.assert_called_once_with(doc, ctx, "B4", "<p>hello</p>")
