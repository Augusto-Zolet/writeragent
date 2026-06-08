# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest.mock import MagicMock

from plugin.calc.navigation import (
    WRITERAGENT_CELL_URL_PREFIX,
    cell_link_registry,
    cell_ref_at_index,
    extract_cell_links_from_html,
    lookup_cell_ref_at_index,
    normalize_cell_address,
    render_calc_cell_refs,
)


def test_normalize_cell_address_simple():
    assert normalize_cell_address("b2") == "B2"
    assert normalize_cell_address("Sheet1.B2") == "Sheet1.B2"
    assert normalize_cell_address("cell://C10") == "C10"
    assert normalize_cell_address(f"{WRITERAGENT_CELL_URL_PREFIX}D4") == "D4"
    assert normalize_cell_address("not-a-cell") is None


def test_render_calc_cell_refs_html():
    text = '<p>See <a href="cell://B2">B2</a> and <a href=\'cell://Sheet1.C3\'>C3</a>.</p>'
    out = render_calc_cell_refs(text)
    assert f'href="{WRITERAGENT_CELL_URL_PREFIX}B2"' in out
    assert f"href='{WRITERAGENT_CELL_URL_PREFIX}Sheet1.C3'" in out
    assert 'href="cell://' not in out.lower()
    assert "href='cell://" not in out.lower()


def test_extract_cell_links_from_html():
    html = '<p>See <a href="cell://B2">B2</a> and <a href="writeragent-cell://C3">cell C3</a>.</p>'
    assert extract_cell_links_from_html(html) == [("B2", "B2"), ("cell C3", "C3")]


def test_render_calc_cell_refs_passthrough():
    assert render_calc_cell_refs("no links here") == "no links here"
    assert render_calc_cell_refs("") == ""


def test_cell_link_registry_lookup():
    control = MagicMock()
    cell_link_registry.clear(control)
    cell_link_registry.add(control, 10, 12, "B2")
    assert lookup_cell_ref_at_index(control, 10) == "B2"
    assert lookup_cell_ref_at_index(control, 11) == "B2"
    assert lookup_cell_ref_at_index(control, 12) is None


def test_cell_ref_at_index_html():
    text = '<p>See <a href="writeragent-cell://B2">B2</a> here.</p>'
    idx = text.index("writeragent-cell")
    assert cell_ref_at_index(text, idx) == "B2"
    assert cell_ref_at_index(text, 0) is None
