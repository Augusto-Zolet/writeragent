# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native UNO coverage for nested Writer text-table relationships."""
import uno  # noqa: F401

from plugin.testing_runner import native_test
from plugin.tests.testing_utils import TestingFactory, with_native_doc
from plugin.writer.specialized.tables import (
    ManageTableStructure,
    TableDelete,
    TableGetCells,
    TableInsert,
    TableList,
    TableSetCell,
)


@native_test
@with_native_doc("writer")
def test_table_get_cells_reports_nested_parent_relation_uno(ctx, doc):
    """A nested table reports its direct parent table/cell; a top-level table does not."""
    text = doc.getText()

    outer = doc.createInstance("com.sun.star.text.TextTable")
    outer.initialize(2, 2)
    text.insertTextContent(text.getEnd(), outer, False)
    outer.setName("FixtureOuter")
    outer.getCellByName("A1").setString("OUTER_ALPHA")

    nested = doc.createInstance("com.sun.star.text.TextTable")
    nested.initialize(2, 2)
    host = outer.getCellByName("B2")
    host.insertTextContent(host.getStart(), nested, False)
    nested.setName("FixtureNested")
    nested.getCellByName("A1").setString("NESTED_ALPHA")
    nested.getCellByName("B2").setString("NESTED_OMEGA")

    standalone = doc.createInstance("com.sun.star.text.TextTable")
    standalone.initialize(1, 2)
    text.insertTextContent(text.getEnd(), standalone, False)
    standalone.setName("FixtureStandalone")
    standalone.getCellByName("A1").setString("STANDALONE_ALPHA")

    tool_ctx = TestingFactory.create_context(doc=doc, ctx=ctx, env="native")

    nested_res = TableGetCells().execute(tool_ctx, name="FixtureNested")
    assert nested_res.get("status") == "ok", nested_res
    assert nested_res["matrix"][0][0] == "NESTED_ALPHA"
    assert nested_res["matrix"][1][1] == "NESTED_OMEGA"
    assert nested_res["nesting"] == {
        "is_nested": True,
        "parent_table": "FixtureOuter",
        "parent_cell": "B2",
    }
    assert nested_res["nested_in_cells"] == {}

    standalone_res = TableGetCells().execute(tool_ctx, name="FixtureStandalone")
    assert standalone_res.get("status") == "ok", standalone_res
    assert standalone_res["matrix"][0][0] == "STANDALONE_ALPHA"
    assert standalone_res["nesting"] == {
        "is_nested": False,
        "parent_table": None,
        "parent_cell": None,
    }

    outer_res = TableGetCells().execute(tool_ctx, name="FixtureOuter")
    assert outer_res.get("status") == "ok", outer_res
    assert outer_res["nesting"] == {
        "is_nested": False,
        "parent_table": None,
        "parent_cell": None,
    }
    assert outer_res["nested_in_cells"] == {"B2": ["FixtureNested"]}

    listed = TableList().execute(tool_ctx)
    assert listed.get("status") == "ok", listed
    by = {t["name"]: t for t in listed["tables"]}
    assert by["FixtureNested"]["nesting"] == nested_res["nesting"]
    assert by["FixtureOuter"]["nested_in_cells"] == outer_res["nested_in_cells"]
    assert by["FixtureStandalone"]["nesting"]["is_nested"] is False

    wipe = TableSetCell().execute(tool_ctx, name="FixtureOuter", cell="B2", text="wipe")
    assert wipe.get("status") == "error" and "FixtureNested" in wipe.get("message", ""), wipe
    assert nested.getName() == "FixtureNested"

    del_row = ManageTableStructure().execute(
        tool_ctx, action="delete", axis="row", name="FixtureOuter", index=1
    )
    assert del_row.get("status") == "error" and "FixtureNested" in del_row.get("message", ""), del_row
    assert outer.getRows().getCount() == 2


@native_test
@with_native_doc("writer")
def test_table_insert_parent_cell_nests_and_table_delete_removes_uno(ctx, doc):
    """table_insert(parent, cell) nests; table_delete removes nested and top-level tables."""
    text = doc.getText()
    outer = doc.createInstance("com.sun.star.text.TextTable")
    outer.initialize(2, 2)
    text.insertTextContent(text.getEnd(), outer, False)
    outer.setName("InsertOuter")
    outer.getCellByName("A1").setString("KEEP_HOST")

    tool_ctx = TestingFactory.create_context(doc=doc, ctx=ctx, env="native")
    nested = TableInsert().execute(
        tool_ctx, rows=2, columns=2, parent="InsertOuter", cell="B2",
        data=[["N1", "N2"], ["N3", "N4"]],
    )
    assert nested.get("status") == "ok", nested
    nested_name = nested["table_name"]
    assert nested_name
    assert nested["nesting"] == {
        "is_nested": True,
        "parent_table": "InsertOuter",
        "parent_cell": "B2",
    }
    assert doc.getTextTables().hasByName(nested_name)
    listed = TableList().execute(tool_ctx)
    by = {t["name"]: t for t in listed["tables"]}
    assert by[nested_name]["nesting"] == nested["nesting"]
    assert by["InsertOuter"]["nested_in_cells"] == {"B2": [nested_name]}
    cells = TableGetCells().execute(tool_ctx, name=nested_name)
    assert cells["matrix"][0][0] == "N1" and cells["matrix"][1][1] == "N4"

    deleted = TableDelete().execute(tool_ctx, name=nested_name)
    assert deleted.get("status") == "ok", deleted
    assert not doc.getTextTables().hasByName(nested_name)
    assert doc.getTextTables().hasByName("InsertOuter")
    after = TableList().execute(tool_ctx)
    after_by = {t["name"]: t for t in after["tables"]}
    assert after_by["InsertOuter"]["nested_in_cells"] == {}
    # Host cell is writable again once the nested table is gone.
    set_host = TableSetCell().execute(tool_ctx, name="InsertOuter", cell="B2", text="host-again")
    assert set_host.get("status") == "ok", set_host

    top = TableInsert().execute(tool_ctx, rows=1, columns=2)
    assert top.get("status") == "ok", top
    top_name = top["table_name"]
    assert top["nesting"]["is_nested"] is False
    assert doc.getTextTables().hasByName(top_name)
    gone = TableDelete().execute(tool_ctx, name=top_name)
    assert gone.get("status") == "ok", gone
    assert not doc.getTextTables().hasByName(top_name)
    assert doc.getTextTables().hasByName("InsertOuter")
