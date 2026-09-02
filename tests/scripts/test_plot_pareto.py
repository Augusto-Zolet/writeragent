# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
# SPDX-License-Identifier: GPL-3.0-or-later
"""Frontier selection for the README Pareto SVG (no pixel checks)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PO = Path(__file__).resolve().parents[2] / "scripts" / "prompt_optimization"
if str(_PO) not in sys.path:
    sys.path.insert(0, str(_PO))

import plot_pareto  # noqa: E402
from run_eval_multi import PARETO_FRONTIER  # noqa: E402


def test_plot_selection_keeps_quality_cost_tradeoff(tmp_path: Path) -> None:
    payload = [
        {
            "openrouter_id": "openai/gpt-oss-120b",
            "pricing_known": True,
            "n_examples": 17,
            "n_error": 0,
            "avg_correctness": 0.971,
            "avg_cost_per_example": 0.00054,
        },
        {
            "openrouter_id": "x-ai/grok-4.6",
            "pricing_known": True,
            "n_examples": 17,
            "n_error": 0,
            "avg_correctness": 0.982,
            "avg_cost_per_example": 0.04653,
        },
        {
            "openrouter_id": "upstage/solar-pro4",
            "pricing_known": True,
            "n_examples": 17,
            "n_error": 0,
            "avg_correctness": 0.682,
            "avg_cost_per_example": 0.00065,
        },
        {
            "openrouter_id": "minimax/minimax-m3",
            "pricing_known": True,
            "n_examples": 17,
            "n_error": 1,
            "avg_correctness": 0.70,
            "avg_cost_per_example": 0.008,
        },
    ]
    src = tmp_path / "in.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    kept = plot_pareto.load_eligible_summaries(src)
    ids = {row["openrouter_id"] for row in kept}
    assert "minimax/minimax-m3" not in ids
    frontier = {
        row["openrouter_id"]
        for row in kept
        if row.get("pareto_status") == PARETO_FRONTIER
    }
    assert frontier == {"openai/gpt-oss-120b", "x-ai/grok-4.6"}


def test_plot_writes_fronts_and_distance_svgs(tmp_path: Path) -> None:
    payload = [
        {
            "openrouter_id": "openai/gpt-oss-120b",
            "pricing_known": True,
            "n_examples": 17,
            "n_error": 0,
            "avg_correctness": 0.971,
            "avg_cost_per_example": 0.00054,
        },
        {
            "openrouter_id": "x-ai/grok-4.6",
            "pricing_known": True,
            "n_examples": 17,
            "n_error": 0,
            "avg_correctness": 0.982,
            "avg_cost_per_example": 0.04653,
        },
        {
            "openrouter_id": "upstage/solar-pro4",
            "pricing_known": True,
            "n_examples": 17,
            "n_error": 0,
            "avg_correctness": 0.682,
            "avg_cost_per_example": 0.00065,
        },
    ]
    src = tmp_path / "in.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    summaries = plot_pareto.load_eligible_summaries(src)
    out_dir = tmp_path / "eval"
    written = plot_pareto.write_all_pareto_svgs(summaries, docs_eval_dir=out_dir)
    assert len(written) == 2
    for path in written:
        assert path.exists()
        assert path.read_text(encoding="utf-8").startswith("<?xml")
