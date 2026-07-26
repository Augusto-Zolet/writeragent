# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for binding-only Excel ``xl()`` shim."""

from __future__ import annotations

import unittest

from plugin.scripting.calc_range import CalcRange
from plugin.scripting.excel_xl import make_xl


class TestExcelXlShim(unittest.TestCase):
    def test_p2_omit_returns_calcrange(self):
        r0 = CalcRange([[1, 2], [3, 4]])
        xl = make_xl((r0,))
        out = xl("%P2%")
        self.assertIs(out, r0)

    def test_headers_true_dataframe(self):
        r0 = CalcRange([["a", "b"], [1, 2]])
        xl = make_xl((r0,))
        df = xl("%P2%", headers=True)
        self.assertEqual(list(df.columns), ["a", "b"])
        self.assertEqual(df.iloc[0].tolist(), [1, 2])

    def test_headers_false_no_header_row(self):
        r0 = CalcRange([["a", "b"], [1, 2]])
        xl = make_xl((r0,))
        df = xl("%P2%", headers=False)
        # First row stays data; synthetic column names.
        self.assertEqual(df.iloc[0].tolist(), ["a", "b"])

    def test_p3_second_input(self):
        r0 = CalcRange([[1]])
        r1 = CalcRange([[9]])
        xl = make_xl((r0, r1))
        self.assertIs(xl("%P3%"), r1)

    def test_case_insensitive_token(self):
        r0 = CalcRange([[1]])
        xl = make_xl((r0,))
        self.assertIs(xl("%p2%"), r0)

    def test_unbound_index_raises(self):
        xl = make_xl((CalcRange([[1]]),))
        with self.assertRaises(ValueError) as ctx:
            xl("%P9%")
        self.assertIn("no matching data binding", str(ctx.exception))

    def test_a1_literal_raises(self):
        xl = make_xl((CalcRange([[1]]),))
        with self.assertRaises(ValueError) as ctx:
            xl("A1")
        self.assertIn("no live sheet reads", str(ctx.exception))

    def test_non_string_ref_raises(self):
        xl = make_xl(())
        with self.assertRaises(ValueError):
            xl(None)  # type: ignore[arg-type]

    def test_empty_inputs_raises(self):
        xl = make_xl(None)
        with self.assertRaises(ValueError):
            xl("%P2%")


if __name__ == "__main__":
    unittest.main()
