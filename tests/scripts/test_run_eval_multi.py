# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI guards for run_eval_multi (no paid API)."""
from __future__ import annotations

import sys
from pathlib import Path

_PO = Path(__file__).resolve().parents[2] / "scripts" / "prompt_optimization"
if str(_PO) not in sys.path:
    sys.path.insert(0, str(_PO))

import run_eval_multi  # noqa: E402


def test_out_path_relative_is_cwd(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    args = type("A", (), {"out": "scripts/prompt_optimization/eval_results_17task.csv"})()
    got = run_eval_multi._out_path(args)
    assert got == tmp_path / "scripts/prompt_optimization/eval_results_17task.csv"
    abs_args = type("A", (), {"out": "/tmp/eval.csv"})()
    assert run_eval_multi._out_path(abs_args) == Path("/tmp/eval.csv")


def test_nitro_student_reuses_base_catalog_pricing() -> None:
    cfg = run_eval_multi._model_config_for_id(
        "openai/gpt-oss-120b:nitro", allow_unknown=False
    )
    base = run_eval_multi._model_config_for_id(
        "openai/gpt-oss-120b", allow_unknown=False
    )
    assert cfg.openrouter_id == "openai/gpt-oss-120b:nitro"
    assert cfg.input_cost_per_million == base.input_cost_per_million
    assert cfg.output_cost_per_million == base.output_cost_per_million


def test_refuse_catalog_sweep_without_models(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys, "argv", ["run_eval_multi.py", "--student", "scripted"]
    )
    assert run_eval_multi.main() == 1
    err = capsys.readouterr().err
    assert "--models" in err
    assert "--yes-all-models" in err


def test_generate_golds_passes_task_id_and_kind_prompt(monkeypatch, tmp_path) -> None:
    """Draw/Calc golds used to run as Writer (no task_id, writer system prompt)."""
    import llm_chat_eval
    from eval_prompts import get_eval_system_prompt

    captured: list[dict] = []

    def fake_run(**kwargs):
        captured.append(kwargs)
        return '{"status": "ok"}', {"total_tokens": 1}, None, []

    monkeypatch.setattr(llm_chat_eval, "run_llm_chat_eval", fake_run)
    monkeypatch.setattr(run_eval_multi, "SCRIPT_DIR", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_eval_multi.py",
            "--generate-golds",
            "-e",
            "flowchart_gen",
            "--student",
            "scripted",
        ],
    )
    assert run_eval_multi.main() == 0
    assert captured
    assert captured[0]["task_id"] == "flowchart_gen"
    assert captured[0]["system_prompt"] == get_eval_system_prompt("flowchart_gen")
    assert captured[0]["system_prompt"] != get_eval_system_prompt("table_from_mess")
    golds = (tmp_path / "gold_standards.json").read_text(encoding="utf-8")
    assert "flowchart_gen" in golds
