# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest.mock import MagicMock, patch

from plugin.calc.formula_dep_chain import _resolve_sheet_and_cell, fetch_formula_dep_chain
from plugin.tests.testing_utils import CalcDocStub


def test_resolve_sheet_and_cell_with_sheet_prefix():
    doc = CalcDocStub()
    sheet = doc.getSheets().getByName("Sheet1")
    # No active controller path for prefixed addresses — still resolves via getSheets.
    doc.CurrentController = None
    doc._controller = None

    resolved = _resolve_sheet_and_cell(doc, "Sheet1.B2")
    assert resolved is not None
    got_sheet, col, row = resolved
    assert got_sheet is sheet
    assert col == 1
    assert row == 1


def test_fetch_formula_dep_chain_uses_command_values_when_available():
    doc = CalcDocStub(command_values='{"commandValues": {"root": {"address": "B2"}}}')

    with patch("plugin.calc.navigation.navigate_to_cell"):
        chain = fetch_formula_dep_chain(doc, MagicMock(), "B2")

    assert chain is not None
    assert chain.get("source") == "uno_formula_dep_chain"
    assert chain.get("cell") == "B2"


def test_fetch_formula_dep_chain_falls_back_to_formula_query():
    doc = CalcDocStub()

    fallback = {"source": "formula_query", "precedents": [{"address": "A1", "type": "value"}]}
    with patch("plugin.calc.navigation.navigate_to_cell"), patch(
        "plugin.calc.formula_dep_chain._precedents_via_formula_query",
        return_value=fallback,
    ):
        chain = fetch_formula_dep_chain(doc, MagicMock(), "A1")

    assert chain is not None
    assert chain.get("source") == "formula_query"
    assert chain.get("precedents")
