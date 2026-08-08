# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from plugin.testing_runner import native_test
from plugin.tests.testing_utils import TestingFactory, with_native_doc


def _execute_calc_tool(doc, ctx, name, args):
    return TestingFactory.execute_tool(doc, ctx, name, args, doc_type="calc")


@native_test
@with_native_doc("calc")
def test_add_and_list_named_ranges(ctx, doc):
    # Make sure we clean up any old named ranges if existing
    named_ranges = doc.NamedRanges
    if named_ranges.hasByName("MyTestRange"):
        named_ranges.removeByName("MyTestRange")
    if named_ranges.hasByName("OtherRange"):
        named_ranges.removeByName("OtherRange")

    # 1. Add Named Range
    res = _execute_calc_tool(doc, ctx, "add_named_range", {"name": "MyTestRange", "content": "$Sheet1.$A$1:$B$2"})
    assert res.get("status") == "ok", f"add_named_range failed: {res}"
    assert named_ranges.hasByName("MyTestRange"), "Named range was not created"

    # Add another
    res2 = _execute_calc_tool(doc, ctx, "add_named_range", {"name": "OtherRange", "content": "$Sheet1.$C$1"})
    assert res2.get("status") == "ok", f"add_named_range failed: {res2}"

    # 2. List Named Ranges
    res_list = _execute_calc_tool(doc, ctx, "list_named_ranges", {})
    assert res_list.get("status") == "ok"
    ranges = res_list.get("result", [])
    names = [r["name"] for r in ranges]
    assert "MyTestRange" in names
    assert "OtherRange" in names

    my_range_content = next(r["content"] for r in ranges if r["name"] == "MyTestRange")
    assert "$Sheet1.$A$1:$B$2" in my_range_content


@native_test
@with_native_doc("calc")
def test_delete_named_range(ctx, doc):
    named_ranges = doc.NamedRanges
    if not named_ranges.hasByName("MyTestRange"):
        from com.sun.star.table import CellAddress
        named_ranges.addNewByName("MyTestRange", "$Sheet1.$A$1:$B$2", CellAddress(Sheet=0, Column=0, Row=0), 0)

    res = _execute_calc_tool(doc, ctx, "delete_named_range", {"name": "MyTestRange"})
    assert res.get("status") == "ok", f"delete_named_range failed: {res}"
    assert not named_ranges.hasByName("MyTestRange"), "Named range was not deleted"


@native_test
@with_native_doc("calc")
def test_transparent_resolution_read_write(ctx, doc):
    named_ranges = doc.NamedRanges
    if named_ranges.hasByName("TransparentRange"):
        named_ranges.removeByName("TransparentRange")

    # Create a named range pointing to a 1x2 area (A10:B10)
    from com.sun.star.table import CellAddress
    named_ranges.addNewByName("TransparentRange", "$Sheet1.$A$10:$B$10", CellAddress(Sheet=0, Column=0, Row=0), 0)

    sheet = doc.getSheets().getByIndex(0)
    sheet.getCellByPosition(0, 9).setString("Apple")
    sheet.getCellByPosition(1, 9).setString("Banana")

    # 1. Read using the named range
    res_read = _execute_calc_tool(doc, ctx, "read_cell_range", {"range_name": ["TransparentRange"]})
    assert res_read.get("status") == "ok", f"read_cell_range failed: {res_read}"
    
    # Structure from read_cell_range with multiple ranges is {"status": "ok", "result": [[[{"value": "Apple", ...}, ...]]]}
    result_data = res_read["result"][0]
    assert result_data[0][0]["value"] == "Apple"
    assert result_data[0][1]["value"] == "Banana"

    # 2. Write using the named range
    res_write = _execute_calc_tool(doc, ctx, "write_formula_range", {
        "range_name": ["TransparentRange"],
        "formula_or_values": '["Cherry", "Date"]'
    })
    assert res_write.get("status") == "ok", f"write_formula_range failed: {res_write}"
    assert sheet.getCellByPosition(0, 9).getString() == "Cherry"
    assert sheet.getCellByPosition(1, 9).getString() == "Date"

    # Clean up
    named_ranges.removeByName("TransparentRange")
