#!/usr/bin/env python3
# WriterAgent - Merge Benchmark Results Utility
# Copyright (c) 2026 KeithCu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Safely merge selective model evaluation results into the benchmark dataset.

Features:
- Replaces existing rows for updated models with new scores.
- Drops retired/superseded models (e.g. mercury-2 in favor of mercury-2.5-preview).
- Merges per-task detail files (e.g. benchmark_results_details.json).
- Recomputes Pareto frontier annotations on the unified dataset.
- Sorts rows by hard pass -> agent score -> metric score.
- Optionally prints the markdown table for docs/eval/benchmarks.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_eval_multi import (  # noqa: E402
    annotate_pareto_status,
    _write_details,
    _write_results,
)


def sort_by_ranking(summaries: list[dict[str, Any]]) -> None:
    """Sort models by hard_pass_rate desc, then avg_agent_score desc, then avg_metric_score desc."""
    summaries.sort(
        key=lambda r: (
            -float(r.get("hard_pass_rate") or 0.0),
            -float(r.get("avg_agent_score") or 0.0),
            -float(r.get("avg_correctness") or 0.0),
            -float(r.get("avg_metric_score") or 0.0),
            float(r.get("avg_cost_per_example") or 0.0),
        )
    )


def format_markdown_table(summaries: list[dict[str, Any]], *, include_n_err: bool = False) -> str:
    """Format summaries list as a GitHub Markdown ranking table."""
    headers = ["Rank", "Model", "Hard pass", "Agent", "Correctness", "Quality", "Tokens/task", "$/task", "C²/$"]
    if include_n_err:
        headers.append("n_err")

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["----" if h in ("Rank", "Model") else "-------" for h in headers]) + " |",
    ]

    rank = 1
    for row in summaries:
        mid = row.get("openrouter_id") or row.get("model_id") or ""
        hard = float(row.get("hard_pass_rate") or 0.0)
        agent = float(row.get("avg_agent_score") or 0.0)
        corr = float(row.get("avg_correctness") or 0.0)
        qual = row.get("avg_quality")
        qual_s = f"{float(qual):.2f}" if qual is not None and float(qual) > 0 else "—"

        n_ex = int(row.get("n_examples") or 17)
        total_tokens = int(row.get("total_tokens") or 0)
        tokens_per_task = total_tokens // n_ex if n_ex > 0 else 0

        cost = float(row.get("avg_cost_per_example") or 0.0)
        cost_s = f"{cost:.5f}" if cost > 0 else "0.00000"

        c2_d = float(row.get("intelligence_per_dollar_metric") or 0.0)
        c2_d_s = f"{c2_d:.1f}" if c2_d > 0 else "0.0"

        cols = [
            str(rank),
            str(mid),
            f"{hard:.3f}",
            f"{agent:.3f}",
            f"{corr:.3f}",
            qual_s,
            str(tokens_per_task),
            cost_s,
            c2_d_s,
        ]
        if include_n_err:
            cols.append(str(int(row.get("n_error") or 0)))

        lines.append("| " + " | ".join(cols) + " |")
        rank += 1

    return "\n".join(lines)


def format_readme_value_table(summaries: list[dict[str, Any]]) -> str:
    """Format table for root README.md (sorted by Value = Correctness^2 / $/task desc)."""
    headers = ["Model", "Correctness<br>avg task score (0–1)", "Value<br>Correctness² ÷ $/task"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| ----- | ----- | ----- |",
    ]

    scored_rows: list[tuple[int, float, dict[str, Any]]] = []
    for r in summaries:
        corr = float(r.get("avg_correctness") or 0.0)
        cost = float(r.get("avg_cost_per_example") or 0.0)
        if cost > 0 and corr > 0:
            val = round((corr**2) / cost)
        else:
            val = 0
        scored_rows.append((val, corr, r))

    # Sort by Value desc, then Correctness desc
    scored_rows.sort(key=lambda item: (-item[0], -item[1]))

    for val, corr, r in scored_rows:
        mid = r.get("openrouter_id") or r.get("model_id") or ""
        lines.append(f"| {mid} | {corr:.3f} | {val} |")

    return "\n".join(lines)


def replace_markdown_table(content: str, header_prefix: str, new_table: str) -> str:
    """Replace a markdown table starting with header_prefix with new_table."""
    lines = content.splitlines()
    start_idx = -1
    for i, line in enumerate(lines):
        if line.startswith(header_prefix):
            start_idx = i
            break
    if start_idx == -1:
        return content

    end_idx = start_idx
    while end_idx < len(lines) and lines[end_idx].startswith("|"):
        end_idx += 1

    new_lines = lines[:start_idx] + new_table.splitlines() + lines[end_idx:]
    return "\n".join(new_lines) + ("\n" if content.endswith("\n") else "")


def update_doc_tables(summaries: list[dict[str, Any]], repo_root: Path) -> list[Path]:
    """Update ranking and value tables in docs/eval/benchmarks.md, README.md, and scripts/prompt_optimization/README.md."""
    updated: list[Path] = []

    # 1. docs/eval/benchmarks.md
    bench_p = repo_root / "docs" / "eval" / "benchmarks.md"
    if bench_p.exists():
        text = bench_p.read_text(encoding="utf-8")
        new_tbl = format_markdown_table(summaries, include_n_err=False)
        text = replace_markdown_table(text, "| Rank | Model | Hard pass |", new_tbl)
        bench_p.write_text(text, encoding="utf-8")
        updated.append(bench_p)

    # 2. scripts/prompt_optimization/README.md
    po_readme = repo_root / "scripts" / "prompt_optimization" / "README.md"
    if po_readme.exists():
        text = po_readme.read_text(encoding="utf-8")
        new_tbl = format_markdown_table(summaries, include_n_err=True)
        text = replace_markdown_table(text, "| Rank | Model | Hard pass |", new_tbl)
        po_readme.write_text(text, encoding="utf-8")
        updated.append(po_readme)

    # 3. root README.md
    root_readme = repo_root / "README.md"
    if root_readme.exists():
        text = root_readme.read_text(encoding="utf-8")
        new_tbl = format_readme_value_table(summaries)
        text = replace_markdown_table(text, "| Model | Correctness<br>", new_tbl)
        root_readme.write_text(text, encoding="utf-8")
        updated.append(root_readme)

    return updated


def merge_summaries(
    base_rows: list[dict[str, Any]],
    update_rows: list[dict[str, Any]],
    drop_ids: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """
    Merge update_rows into base_rows.

    - Removes models in drop_ids.
    - Replaces base entries if present in update_rows.
    - Appends new models from update_rows.
    - Recomputes Pareto status.
    - Sorts by ranking order.
    """
    drop_set = set(drop_ids)
    merged_map: dict[str, dict[str, Any]] = {}

    for row in base_rows:
        mid = row.get("openrouter_id") or row.get("model_id")
        if mid and mid not in drop_set:
            merged_map[mid] = dict(row)

    for row in update_rows:
        mid = row.get("openrouter_id") or row.get("model_id")
        if mid and mid not in drop_set:
            merged_map[mid] = dict(row)

    merged = list(merged_map.values())
    annotate_pareto_status(merged)
    sort_by_ranking(merged)
    return merged


def merge_details(
    base_details: list[dict[str, Any]],
    update_details: list[dict[str, Any]],
    replaced_or_dropped_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """Remove prior records for updated or dropped models, then append new detail records."""
    purge_set = set(replaced_or_dropped_ids)
    filtered = [d for d in base_details if d.get("model_id") not in purge_set]
    return filtered + list(update_details)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge selective benchmark results into master dataset.")
    parser.add_argument(
        "--base",
        "-b",
        default="scripts/prompt_optimization/benchmark_results.json",
        help="Base results JSON path",
    )
    parser.add_argument(
        "--update",
        "-u",
        required=True,
        help="Selective/update results JSON path",
    )
    parser.add_argument(
        "--drop",
        "-d",
        default="",
        help="Comma-separated model IDs to drop/supersede (e.g. inception/mercury-2,meta/muse-spark-1.2-contributor)",
    )
    parser.add_argument(
        "--out",
        "-o",
        default=None,
        help="Output merged results JSON path (default: overwrite --base)",
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Skip merging _details.json files",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Print markdown ranking table to stdout",
    )
    parser.add_argument(
        "--update-docs",
        action="store_true",
        help="Update ranking tables directly in docs/eval/benchmarks.md, README.md, and scripts/prompt_optimization/README.md",
    )
    args = parser.parse_args(argv)

    base_path = Path(args.base).resolve()
    update_path = Path(args.update).resolve()
    out_path = Path(args.out).resolve() if args.out else base_path

    if not base_path.exists():
        print(f"Base file not found: {base_path}", file=sys.stderr)
        return 1
    if not update_path.exists():
        print(f"Update file not found: {update_path}", file=sys.stderr)
        return 1

    base_rows: list[dict[str, Any]] = json.loads(base_path.read_text(encoding="utf-8"))
    update_rows: list[dict[str, Any]] = json.loads(update_path.read_text(encoding="utf-8"))
    drop_ids = [s.strip() for s in args.drop.split(",") if s.strip()]

    merged_rows = merge_summaries(base_rows, update_rows, drop_ids=drop_ids)
    _write_results(out_path, merged_rows)
    print(f"Wrote {len(merged_rows)} merged model summaries to {out_path}")

    if not args.no_details:
        base_details_path = base_path.parent / (base_path.stem + "_details" + base_path.suffix)
        update_details_path = update_path.parent / (update_path.stem + "_details" + update_path.suffix)
        out_details_path = out_path.parent / (out_path.stem + "_details" + out_path.suffix)

        if base_details_path.exists() and update_details_path.exists():
            base_details = json.loads(base_details_path.read_text(encoding="utf-8"))
            update_details = json.loads(update_details_path.read_text(encoding="utf-8"))

            update_ids = {r.get("openrouter_id") or r.get("model_id") for r in update_rows}
            purge_ids = set(drop_ids) | {uid for uid in update_ids if uid}

            merged_details = merge_details(base_details, update_details, list(purge_ids))
            _write_details(out_path, merged_details)
            print(f"Wrote {len(merged_details)} merged details to {out_details_path}")
        else:
            print("Notice: Details files not found for one or both inputs; skipped details merge.")

    if args.markdown:
        print("\n" + "=" * 40 + " MARKDOWN TABLE " + "=" * 40)
        print(format_markdown_table(merged_rows))

    if args.update_docs:
        updated_files = update_doc_tables(merged_rows, REPO_ROOT)
        for uf in updated_files:
            print(f"Updated benchmark table in {uf}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
