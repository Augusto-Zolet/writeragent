# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Comment helper tests (list/read paths). No LibreOffice required."""
from unittest.mock import MagicMock, patch

from plugin.tests.testing_utils import setup_uno_mocks
setup_uno_mocks()


def test_read_annotation_falls_back_to_paragraph_context():
    from plugin.writer.specialized.comments import _read_annotation

    anchor = MagicMock()
    anchor.getString.return_value = ""
    field = MagicMock()
    field.getAnchor.return_value = anchor
    field.getPropertyValue.side_effect = lambda p: {"Author": "Rev", "Content": "note"}.get(p, "")
    doc_svc = MagicMock()
    doc_svc.find_paragraph_for_range.return_value = 7
    with patch("plugin.writer.search._enclosing_paragraph_text", return_value="  the clause the comment covers  "):
        entry = _read_annotation(field, [], MagicMock(), doc_svc)
    assert entry["anchor_preview"] == "the clause the comment covers"
    assert entry["anchor_is_paragraph_context"] is True


def test_comment_workflow_split_tool_names():
    from plugin.writer.specialized import comments

    assert comments.CommentScanTasks.name == "comment_scan_tasks"
    assert comments.CommentWorkflowGet.name == "comment_workflow_get"
    assert comments.CommentWorkflowSet.name == "comment_workflow_set"
    assert comments.CommentCheckStop.name == "comment_check_stop"
    assert comments.CommentWorkflowSet.is_mutation is True
    assert not getattr(comments.CommentScanTasks, "is_mutation", False)
    assert not hasattr(comments, "CommentWorkflow")


def test_workflow_task_prefixes_shared():
    from plugin.framework.constants import WORKFLOW_TASK_PREFIXES
    from plugin.writer.specialized.comments import CommentScanTasks, _WORKFLOW_TASK_PREFIXES
    from plugin.scripting import writeragent_api

    expected = ("TODO-AI", "FIX", "QUESTION", "VALIDATION", "NOTE")
    assert WORKFLOW_TASK_PREFIXES == expected
    assert _WORKFLOW_TASK_PREFIXES == WORKFLOW_TASK_PREFIXES
    assert writeragent_api.WORKFLOW_TASK_PREFIXES == WORKFLOW_TASK_PREFIXES

    # Schema consistency
    enum_values = CommentScanTasks.parameters["properties"]["prefix_filter"]["enum"]
    assert enum_values == list(WORKFLOW_TASK_PREFIXES)
    for prefix in WORKFLOW_TASK_PREFIXES:
        assert prefix in CommentScanTasks.description


def test_comment_scan_tasks_with_prefixes():
    from plugin.writer.specialized.comments import _comment_scan_tasks

    def make_field(content: str, resolved: bool = False):
        f = MagicMock()
        f.supportsService.return_value = True
        f.getPropertyValue.side_effect = lambda prop: {
            "Content": content,
            "Resolved": resolved,
            "Author": "Reviewer",
        }.get(prop, "")
        anchor = MagicMock()
        anchor.getString.return_value = "Selected text"
        f.getAnchor.return_value = anchor
        return f

    f1 = make_field("TODO-AI: refactor this method", resolved=False)
    f2 = make_field("FIX: bug here", resolved=True)
    f3 = make_field("NOTE: general comment", resolved=False)
    f4 = make_field("Arbitrary comment", resolved=False)

    class FakeEnum:
        def __init__(self, items):
            self._items = list(items)
        def hasMoreElements(self):
            return bool(self._items)
        def nextElement(self):
            return self._items.pop(0)

    doc = MagicMock()
    fields = MagicMock()
    fields.createEnumeration.side_effect = lambda: FakeEnum([f1, f2, f3, f4])
    doc.getTextFields.return_value = fields
    doc.getText.return_value = MagicMock()

    ctx = MagicMock()
    ctx.doc = doc
    ctx.services.document.get_paragraph_ranges.return_value = []
    ctx.services.document.find_paragraph_for_range.return_value = None

    # Unresolved only (default)
    res = _comment_scan_tasks(ctx, {})
    assert res["status"] == "ok"
    assert res["count"] == 2
    assert [t["prefix"] for t in res["tasks"]] == ["TODO-AI", "NOTE"]

    # Filter by specific prefix
    fields.createEnumeration.side_effect = lambda: FakeEnum([f1, f2, f3, f4])
    res_filtered = _comment_scan_tasks(ctx, {"prefix_filter": "NOTE"})
    assert res_filtered["status"] == "ok"
    assert res_filtered["count"] == 1
    assert res_filtered["tasks"][0]["prefix"] == "NOTE"

