# WriterAgent — unit tests for Draw TableShape fill helper and insert_table
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest.mock import MagicMock, patch

from plugin.draw.tables import InsertTable, fill_table_cells


class _Cell:
    def __init__(self):
        self._s = ""

    def getText(self):
        return self

    def setString(self, val):
        self._s = val


class _Table:
    def __init__(self):
        self.cells = {}

    def getCellByPosition(self, col, row):
        key = (col, row)
        if key not in self.cells:
            self.cells[key] = _Cell()
        return self.cells[key]


def test_fill_table_cells():
    table = _Table()
    n = fill_table_cells(table, [["a", "b"], ["c", "d"]])
    assert n == 4
    assert table.cells[(0, 0)]._s == "a"
    assert table.cells[(1, 1)]._s == "d"


def test_insert_table_ok():
    ctx = MagicMock()
    shape = MagicMock()
    page = MagicMock()
    page.getCount.return_value = 1
    ctx.doc.createInstance.return_value = shape
    with patch("plugin.draw.bridge.DrawBridge") as bridge_cls:
        bridge = bridge_cls.return_value
        bridge.get_active_page_index.return_value = 0
        bridge.get_pages.return_value.getByIndex.return_value = page
        with patch("plugin.draw.tables._table_model", return_value=_Table()):
            with patch("com.sun.star.awt.Point", MagicMock(), create=True), patch(
                "com.sun.star.awt.Size", MagicMock(), create=True
            ):
                out = InsertTable().execute(ctx, rows=2, columns=2, data=[["h1", "h2"], ["v1", "v2"]])
    assert out["status"] == "ok"
    assert out["cells_written"] == 4
    page.add.assert_called_once_with(shape)


def test_insert_table_rejects_zero_rows():
    out = InsertTable().execute(MagicMock(), rows=0, columns=2)
    assert out["status"] == "error"
