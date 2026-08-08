# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2024 John Balis
# Copyright (c) 2026 KeithCu (modifications and relicensing)
# Copyright (c) 2026 LibreCalc AI Assistant (Calc integration features, originally MIT)
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
def test_calc_pivot_table(ctx, doc):
    sn = doc.getSheets().getByIndex(0).getName()
    res_write = _execute_calc_tool(doc, ctx, "write_formula_range", {
        "range_name": "A1:B6",
        "formula_or_values": [
            ["Month", "Sales"],
            ["Jan", "100"],
            ["Feb", "150"],
            ["Mar", "200"],
            ["Apr", "250"],
            ["May", "300"],
        ],
    })
    assert res_write.get("status") == "ok", f"write_formula_range failed: {res_write}"

    res = _execute_calc_tool(doc, ctx, "create_pivot_table", {
        "pivot_table_name": "WA_PivotTest",
        "source_range": "A1:B6",
        "source_sheet_name": sn,
        "destination_sheet_name": sn,
        "destination_cell": "D1",
        "row_fields": ["Month"],
        "column_fields": [],
        "data_fields": ["Sales"],
        "page_fields": [],
    })
    assert res.get("status") == "ok", f"create_pivot_table failed: {res}"

    res_list = _execute_calc_tool(doc, ctx, "list_pivot_tables", {"sheet_name": sn})
    assert res_list.get("status") == "ok", f"list_pivot_tables failed: {res_list}"
    names = [p.get("name") for p in res_list.get("pivot_tables", [])]
    assert "WA_PivotTest" in names, f"Expected WA_PivotTest in {names}"

    res_ref = _execute_calc_tool(doc, ctx, "refresh_pivot_table", {
        "pivot_table_name": "WA_PivotTest",
        "sheet_name": sn,
    })
    assert res_ref.get("status") == "ok", f"refresh_pivot_table failed: {res_ref}"
