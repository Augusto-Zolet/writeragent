# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native tests: Writer/Calc documents are wiped and reused between @with_native_doc tests."""

from plugin.testing_runner import native_test
from plugin.tests.testing_utils import with_native_doc

_calc_uids: list = []
_writer_uids: list = []


def _runtime_uid(doc) -> str:
    try:
        return str(doc.RuntimeUID)
    except Exception:
        return str(doc.getURL())


@native_test
@with_native_doc("calc")
def test_calc_reuse_writes_then_leaves_dirt(ctx, doc):
    sheet = doc.getSheets().getByIndex(0)
    sheet.getCellByPosition(0, 0).setString("leftover-calc")
    _calc_uids.append(_runtime_uid(doc))


@native_test
@with_native_doc("calc")
def test_calc_reuse_next_test_sees_empty_sheet(ctx, doc):
    sheet = doc.getSheets().getByIndex(0)
    assert sheet.getCellByPosition(0, 0).getString() == ""
    if _calc_uids:
        assert _runtime_uid(doc) == _calc_uids[0]


@native_test
@with_native_doc("writer")
def test_writer_reuse_writes_then_leaves_dirt(ctx, doc):
    doc.getText().setString("leftover-writer")
    _writer_uids.append(_runtime_uid(doc))


@native_test
@with_native_doc("writer")
def test_writer_reuse_next_test_sees_empty_text(ctx, doc):
    assert doc.getText().getString() == ""
    if _writer_uids:
        assert _runtime_uid(doc) == _writer_uids[0]


@native_test
@with_native_doc("calc", reuse=False)
def test_calc_reuse_false_still_empty(ctx, doc):
    assert doc.getSheets().getByIndex(0).getCellByPosition(0, 0).getString() == ""
