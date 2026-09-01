# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Good fixtures pass result oracles; mutated fixtures fail. No API, no soffice."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PO = Path(__file__).resolve().parents[2] / "scripts" / "prompt_optimization"
if str(_PO) not in sys.path:
    sys.path.insert(0, str(_PO))

from oracles import (  # noqa: E402
    check_oracle,
    haystack_has,
    uses_llm_judge,
)
from scripted_student import (  # noqa: E402
    _BULK_CLEANUP,
    _BULLET_CONSISTENCY,
    _COMMENT_MANAGEMENT,
    _FORMAT_PRESERVATION,
    _LOGICAL_REWRITING,
    _REFORMAT_RESUME,
    _SECTION_REFACTOR,
    _SMART_SUMMARIZATION,
    _STYLE_APPLICATION,
    _STYLE_CONSISTENCY,
    _TABLE_ENGINEERING,
    _TABLE_FROM_MESS,
)

_SORT_GOOD = json.dumps(
    {
        "status": "ok",
        "snapshot": True,
        "headers": ["Product", "Revenue"],
        "grid": [
            ["Product", "Revenue"],
            ["Tool", 2100],
            ["Device", 1200],
            ["Widget", 1200],
            ["Gadget", 850],
            ["Aardvark", "n/a"],
        ],
    }
)
_SORT_BAD = json.dumps(
    {
        "status": "ok",
        "snapshot": True,
        "headers": ["Product", "Revenue"],
        "grid": [
            ["Product", "Revenue"],
            ["Widget", 1200],
            ["Tool", 2100],
            ["Device", 950],
            ["Gadget", 850],
        ],
    }
)
_TAX_GOOD = json.dumps(
    {
        "status": "ok",
        "snapshot": True,
        "headers": ["Item", "Price", "Tax"],
        "grid": [
            ["Item", "Price", "Tax"],
            ["Apple", 10, 0.8],
            ["Banana", 5, 0.4],
            ["Orange", 8, 0.64],
            ["Pear", 12.5, 1.0],
            ["Note", "n/a", ""],
            ["Total", "?", ""],
        ],
    }
)
_TAX_BAD = json.dumps(
    {
        "status": "ok",
        "snapshot": True,
        "headers": ["Item", "Price", "Tax"],
        "grid": [
            ["Item", "Price", "Tax"],
            ["Apple", 10, 1.0],
            ["Banana", 5, 0.5],
            ["Orange", 8, 0.8],
            ["Pear", 12.5, 1.25],
        ],
    }
)
_FLOW_GOOD = json.dumps(
    {
        "status": "ok",
        "tree": [
            {"type": "ellipse", "text": "Start", "connected_end": {"name": "shape_1", "text": "Process: user login"}},
            {"type": "flowchart-process", "text": "Process: user login"},
            {"type": "flowchart-decision", "text": "Decision: credentials valid?"},
            {"type": "flowchart-terminator", "text": "End"},
        ],
        "connections": [
            {"from_index": 0, "to_index": 1},
            {"from_index": 1, "to_index": 2},
            {"from_index": 2, "to_index": 3, "label": "Yes"},
            {"from_index": 2, "to_index": 1, "label": "No"},
        ],
    }
)
_PY_GOOD = json.dumps(
    {
        "status": "ok",
        "snapshot": True,
        "formulas": {"J1": '=PY("result = 1"; A1:H500)'},
        "writes": [{"range": ["J1"], "dests": ["J1"], "formula": '=PY("result = 1"; A1:H500)'}],
        "grid": [["Name"]],
    }
)
_PY_BAD = json.dumps(
    {
        "status": "ok",
        "snapshot": True,
        "formulas": {"H1": '=PY("result = 1"; A1:H500)'},
        "writes": [{"range": ["H1"], "dests": ["H1"], "formula": '=PY("result = 1"; A1:H500)'}],
        "grid": [["Name"]],
    }
)


@pytest.mark.parametrize(
    ("task_id", "doc"),
    [
        ("table_from_mess", _TABLE_FROM_MESS),
        ("table_engineering", _TABLE_ENGINEERING),
        ("bulk_cleanup", _BULK_CLEANUP),
        ("format_preservation", _FORMAT_PRESERVATION),
        ("style_application", _STYLE_APPLICATION),
        ("bullet_consistency", _BULLET_CONSISTENCY),
        ("style_consistency", _STYLE_CONSISTENCY),
        ("section_refactor", _SECTION_REFACTOR),
        ("comment_management", _COMMENT_MANAGEMENT),
        ("reformat_resume", _REFORMAT_RESUME),
        ("logical_rewriting", _LOGICAL_REWRITING),
        ("smart_summarization", _SMART_SUMMARIZATION),
        ("data_sorting", _SORT_GOOD),
        ("tax_column", _TAX_GOOD),
        ("flowchart_gen", _FLOW_GOOD),
        ("py_refuse_overlap", _PY_GOOD),
    ],
)
def test_good_fixtures_pass(task_id: str, doc: str) -> None:
    assert check_oracle(task_id, doc) == []


@pytest.mark.parametrize(
    ("task_id", "doc", "needle"),
    [
        ("table_from_mess", _TABLE_FROM_MESS.replace("Total", "Subtotal").replace("$1458.46", "$1.00"), "Total"),
        ("table_engineering", _TABLE_ENGINEERING.replace("51.40", "0.00"), "51.4"),
        ("bulk_cleanup", _BULK_CLEANUP.replace("extra spaces", "extra  spaces"), "double space"),
        (
            "format_preservation",
            _FORMAT_PRESERVATION.replace("John Doe (legacy", "Jane Smith (legacy"),
            "legal",
        ),
        (
            "style_application",
            _STYLE_APPLICATION.replace("<p>Background</p>", "<h1>Background</h1>"),
            "Background",
        ),
        (
            "bullet_consistency",
            _BULLET_CONSISTENCY.replace("- First thing.", "* First thing"),
            "hyphen+period or <li>",
        ),
        (
            "section_refactor",
            _SECTION_REFACTOR.replace("<h1>Goal</h1>", "<h1>Conclusion</h1>"),
            "Conclusion",
        ),
        ("data_sorting", _SORT_BAD, "sort order"),
        ("tax_column", _TAX_BAD, "8%"),
        ("logical_rewriting", _LOGICAL_REWRITING.replace("WriterAgent", "LocalWriter"), "LocalWriter"),
        ("flowchart_gen", json.dumps({"status": "ok", "tree": [{"text": "Start"}]}), "login"),
        (
            "flowchart_gen",
            json.dumps(
                {
                    "status": "ok",
                    "tree": [
                        {"text": "Start"},
                        {"text": "Process: user login"},
                        {"text": "Decision: credentials valid?"},
                        {"text": "End"},
                    ],
                }
            ),
            "edge",
        ),
        (
            "flowchart_gen",
            json.dumps(
                {
                    "status": "ok",
                    "tree": [
                        {"type": "ellipse", "text": "Start"},
                        {"type": "flowchart-process", "text": "Process: user login"},
                        {"type": "flowchart-decision", "text": "Decision: credentials valid?"},
                        {"type": "flowchart-terminator", "text": "End"},
                    ],
                    "connections": [
                        {"from_index": 0, "to_index": 1},
                        {"from_index": 1, "to_index": 2},
                        {"from_index": 2, "to_index": 3, "label": "Yes"},
                    ],
                }
            ),
            "loop",
        ),
        (
            "table_engineering",
            _TABLE_ENGINEERING.replace(
                '<td align="right">6</td>', '<td align="right">[note]</td>', 1
            ),
            "[note]",
        ),
        ("py_refuse_overlap", _PY_BAD, "inside"),
        (
            "style_consistency",
            _STYLE_CONSISTENCY.replace("data-lo-style=\"Quotations\"", ""),
            "style/class",
        ),
        (
            "smart_summarization",
            _SMART_SUMMARIZATION.replace("40% cost reduction", "9001ms intern joke"),
            "distractor",
        ),
        (
            "comment_management",
            "<p>uncertain</p><p>[Review this before finalizing]</p>",
            "uncertain",
        ),
        (
            "tax_column",
            json.dumps(
                {
                    "status": "ok",
                    "snapshot": True,
                    "headers": ["Item", "Price", "Tax"],
                    "grid": [
                        ["Item", "Price", "Tax"],
                        ["Apple", 10, 0.8],
                        ["Banana", 5, 0.4],
                        ["Orange", 8, 0.64],
                        ["Pear", 12.5, 1.0],
                        ["Note", "n/a", 0.08],
                    ],
                }
            ),
            "not be taxed",
        ),
    ],
)
def test_mutated_fixtures_fail(task_id: str, doc: str, needle: str) -> None:
    fails = check_oracle(task_id, doc)
    assert fails, f"{task_id} should fail on mutated fixture"
    assert any(needle.lower() in f.lower() for f in fails), (needle, fails)


def test_unsorted_input_fails_data_sorting() -> None:
    raw = "Product\tRevenue\nWidget\t1200\nGadget\t850\nTool\t2100\nDevice\t1200\nAardvark\tn/a"
    fails = check_oracle("data_sorting", raw)
    assert fails


def test_empty_doc_fails_structural() -> None:
    assert check_oracle("table_from_mess", "")
    assert check_oracle("bulk_cleanup", "hello")


def test_py_dest_i1_document_oracle() -> None:
    assert check_oracle("py_refuse_overlap", _PY_GOOD.replace("J1", "I1")) == []


def test_resume_nnbsp_matches_100k_oracle() -> None:
    doc = (
        "<h1>John Doe</h1><p>WORK HISTORY</p><p>EDUCATION</p><p>SKILLS</p>"
        "<p>Acme Corp</p><p>TechStart</p>"
        "<p>Scaled to 100\u202fK users and 100\u202fM requests per month.</p>"
    )
    assert check_oracle("reformat_resume", doc) == []
    assert haystack_has(doc, "100K")
    assert haystack_has(doc, "100M")


def test_summary_nnbsp_matches_45ms_oracle() -> None:
    doc = (
        "<h1>Findings</h1><p>stats</p>"
        "<h1>Executive Summary</h1>"
        "<ul><li>99.9%</li><li>45\u202fms</li><li>0.01%</li>"
        "<li>10k RPS</li><li>40%</li></ul>"
    )
    fails = check_oracle("smart_summarization", doc)
    assert not any("45ms" in f for f in fails), fails


def test_flowchart_login_labels_pass_without_process_decision_words() -> None:
    doc = json.dumps(
        {
            "status": "ok",
            "tree": [
                {
                    "type": "ellipse",
                    "text": "Start",
                    "connected_end": {"name": "shape_1", "text": "User Login"},
                },
                {
                    "type": "rectangle",
                    "text": "User Login",
                    "connected_end": {"name": "shape_2", "text": "Credentials valid?"},
                    "connected_start": {"name": "shape_0", "text": "Start"},
                },
                {
                    "type": "diamond",
                    "text": "Credentials valid?",
                    "connected_end": {"name": "shape_3", "text": "End"},
                    "connected_start": {"name": "shape_1", "text": "User Login"},
                },
                {
                    "type": "ellipse",
                    "text": "End",
                    "connected_start": {"name": "shape_2", "text": "Credentials valid?"},
                },
            ],
            "connections": [
                {"from_index": 0, "to_index": 1},
                {"from_index": 1, "to_index": 2},
                {"from_index": 2, "to_index": 3},
                {"from_index": 2, "to_index": 1},
            ],
        }
    )
    assert check_oracle("flowchart_gen", doc) == []


def test_golds_pass_oracles() -> None:
    golds = json.loads((_PO / "gold_standards.json").read_text(encoding="utf-8"))
    for task_id, doc in golds.items():
        assert check_oracle(task_id, doc) == [], task_id


def test_table_golds_match_scripted_and_align_numerics() -> None:
    golds = json.loads((_PO / "gold_standards.json").read_text(encoding="utf-8"))
    assert golds["table_from_mess"] == _TABLE_FROM_MESS
    assert golds["table_engineering"] == _TABLE_ENGINEERING
    assert 'align="right"' in golds["table_engineering"]
    assert "Ubiquiti" in golds["table_from_mess"]


def test_table_engineering_oracle_does_not_require_align() -> None:
    """Right-align is a judge gold, not a hard-gate requirement."""
    bare = (
        "<table><thead><tr><th>Item</th><th>Price</th><th>Quantity</th></tr></thead>"
        "<tbody>"
        "<tr><td>Apple</td><td>1.20</td><td>12</td></tr>"
        "<tr><td>Banana</td><td>0.50</td><td>24</td></tr>"
        "<tr><td>Orange</td><td>0.80</td><td>0</td></tr>"
        "<tr><td>Grape</td><td>2.00</td><td>8</td></tr>"
        "<tr><td>Mango</td><td>1.50</td><td>6</td></tr>"
        "<tr><td>Kiwi</td><td>1.75</td><td>0</td></tr>"
        "<tr><td>Total</td><td>51.40</td><td>50</td></tr>"
        "</tbody></table>"
    )
    assert check_oracle("table_engineering", bare) == []


def test_nnbsp_100k_counts_as_expected_contains() -> None:
    from eval_core import _correctness_breakdown
    from types import SimpleNamespace

    ex = SimpleNamespace(
        task_id="reformat_resume",
        expected_contains=["100K", "100M"],
        reject_contains=[],
    )
    doc = "Scaled to 100\u202fK users and 100\u202fM requests."
    score, missing, found_reject, oracle_failures = _correctness_breakdown(ex, doc)
    assert "100K" not in missing
    assert "100M" not in missing
    unused = (score, found_reject, oracle_failures)
    del unused


def test_whitespace_needles_are_ignored() -> None:
    from eval_core import _correctness_breakdown
    from types import SimpleNamespace

    ex = SimpleNamespace(
        task_id="format_preservation",
        expected_contains=[" ", "Jane Smith - Project Lead"],
        reject_contains=[" "],
    )
    score, missing, found_reject, oracle_failures = _correctness_breakdown(
        ex, _FORMAT_PRESERVATION
    )
    assert " " not in missing
    assert " " not in found_reject
    assert oracle_failures == []
    assert score == 1.0


def test_judge_only_for_quality_tasks() -> None:
    assert uses_llm_judge("reformat_resume", "creative")
    assert uses_llm_judge("logical_rewriting")
    assert uses_llm_judge("smart_summarization")
    assert uses_llm_judge("table_from_mess", "structural")
    assert uses_llm_judge("table_engineering", "structural")
    assert not uses_llm_judge("tax_column", "structural")
