#!/usr/bin/env python3
"""Write cost–correctness Pareto SVGs from a run_eval_multi summary JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_eval_multi import (  # noqa: E402
    PARETO_DOMINATED,
    PARETO_FRONTIER,
    annotate_pareto_status,
    pareto_f1_distances,
)

# Snapshot exclusions: full 429s and MiniMax harness crash (re-run later).
DEFAULT_EXCLUDE = frozenset(
    {
        "nvidia/nemotron-3.5-lightning",
        "qwen/qwen3.8-flash",
        "minimax/minimax-m3",
    }
)

# Okabe–Ito (color-blind friendly) for successive fronts.
OKABE_ITO = (
    "#E69F00",
    "#56B4E9",
    "#009E73",
    "#F0E442",
    "#0072B2",
    "#D55E00",
    "#CC79A7",
    "#000000",
)

LABEL_OFFSETS = (
    (7, 7),
    (7, -10),
    (-7, 8),
    (-7, -11),
    (10, 0),
    (-12, 2),
    (8, 12),
    (8, -14),
)

FOOTNOTE = (
    "Source: OpenRouter string-harness run, 2026-09-01. "
    "Each point is labeled with model slug and average correctness. "
    "Excluded: two full 429 runs and minimax/minimax-m3 (harness crash)."
)


def load_eligible_summaries(
    path: Path,
    *,
    exclude: frozenset[str] = DEFAULT_EXCLUDE,
) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"{path} is not a JSON array of model summaries")
    kept: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        model_id = str(row.get("openrouter_id") or "")
        if model_id in exclude:
            continue
        if "n_examples" not in row:
            row["n_examples"] = 17
        kept.append(row)
    annotate_pareto_status(kept)
    return kept


def _short_label(row: dict[str, Any]) -> str:
    model_id = str(row.get("openrouter_id") or "")
    name = model_id.rsplit("/", 1)[-1]
    return f"{name} {float(row['avg_correctness']):.3f}"


def _plotable_rows(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in summaries
        if row.get("pareto_status") in (PARETO_FRONTIER, PARETO_DOMINATED)
        and row.get("pareto_front") is not None
    ]


def _annotate_all_labels(ax: Any, rows: list[dict[str, Any]]) -> None:
    labeled = sorted(
        rows,
        key=lambda row: (float(row["avg_cost_per_example"]), float(row["avg_correctness"])),
    )
    for idx, row in enumerate(labeled):
        dx, dy = LABEL_OFFSETS[idx % len(LABEL_OFFSETS)]
        ax.annotate(
            _short_label(row),
            (float(row["avg_cost_per_example"]), float(row["avg_correctness"])),
            textcoords="offset points",
            xytext=(dx, dy),
            fontsize=7.5,
            fontweight="bold",
            color="#3c4043",
        )


def _style_cost_quality_axes(ax: Any, *, title: str) -> None:
    ax.set_xscale("log")
    ax.set_xlabel("Average cost per task (USD, log scale)")
    ax.set_ylabel("Average correctness (0–1)")
    ax.set_title(title)
    ax.set_ylim(0.52, 1.05)
    ax.grid(True, which="both", linestyle=":", linewidth=0.6, color="#dadce0")


def write_pareto_fronts_svg(summaries: list[dict[str, Any]], out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = _plotable_rows(summaries)
    fronts = sorted({int(row["pareto_front"]) for row in rows})

    fig, ax = plt.subplots(figsize=(11.2, 7.2), dpi=120)
    for front_num in fronts:
        front_rows = [row for row in rows if int(row["pareto_front"]) == front_num]
        front_rows.sort(key=lambda row: float(row["avg_cost_per_example"]))
        color = OKABE_ITO[(front_num - 1) % len(OKABE_ITO)]
        costs = [float(row["avg_cost_per_example"]) for row in front_rows]
        correctness = [float(row["avg_correctness"]) for row in front_rows]
        if len(front_rows) > 1:
            ax.plot(costs, correctness, color=color, linewidth=1.2, zorder=2 + front_num)
        ax.scatter(
            costs,
            correctness,
            s=56 if front_num == 1 else 44,
            c=color,
            zorder=3 + front_num,
            label=f"F{front_num}",
        )

    _annotate_all_labels(ax, rows)
    _style_cost_quality_axes(
        ax,
        title="WriterAgent 17-task cost–quality Pareto fronts (nondominated sorting)",
    )
    ax.legend(frameon=False, loc="lower right", title="Front")
    fig.text(0.01, 0.01, FOOTNOTE, fontsize=7, color="#5f6368")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="svg")
    plt.close(fig)


def write_pareto_distance_svg(summaries: list[dict[str, Any]], out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = _plotable_rows(summaries)
    distances = pareto_f1_distances(summaries)
    if not rows or not distances:
        raise ValueError("No eligible models for distance chart")

    f1_rows = sorted(
        (row for row in rows if int(row.get("pareto_front") or 0) == 1),
        key=lambda row: float(row["avg_cost_per_example"]),
    )
    dist_values = [distances[id(row)] for row in rows]

    fig, ax = plt.subplots(figsize=(11.2, 7.2), dpi=120)
    scatter = ax.scatter(
        [float(row["avg_cost_per_example"]) for row in rows],
        [float(row["avg_correctness"]) for row in rows],
        s=52,
        c=dist_values,
        cmap="cividis",
        zorder=3,
    )
    if len(f1_rows) > 1:
        ax.plot(
            [float(row["avg_cost_per_example"]) for row in f1_rows],
            [float(row["avg_correctness"]) for row in f1_rows],
            color="#1a73e8",
            linewidth=1.4,
            zorder=4,
            label="F1 frontier",
        )
    elif f1_rows:
        ax.scatter(
            [float(f1_rows[0]["avg_cost_per_example"])],
            [float(f1_rows[0]["avg_correctness"])],
            s=70,
            facecolors="none",
            edgecolors="#1a73e8",
            linewidths=1.4,
            zorder=4,
            label="F1 frontier",
        )

    _annotate_all_labels(ax, rows)
    _style_cost_quality_axes(
        ax,
        title="WriterAgent 17-task distance to F1 frontier",
    )
    cbar = fig.colorbar(scatter, ax=ax, pad=0.02)
    cbar.set_label("Distance to F1 (normalized log-cost × correctness)")
    if f1_rows:
        ax.legend(frameon=False, loc="lower right")
    fig.text(
        0.01,
        0.01,
        FOOTNOTE + " Color = min point-to-segment distance to the F1 polyline.",
        fontsize=7,
        color="#5f6368",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="svg")
    plt.close(fig)


def write_all_pareto_svgs(
    summaries: list[dict[str, Any]],
    *,
    docs_eval_dir: Path,
) -> list[Path]:
    """Write fronts and distance SVGs."""
    fronts_path = docs_eval_dir / "pareto-fronts.svg"
    distance_path = docs_eval_dir / "pareto-distance.svg"
    write_pareto_fronts_svg(summaries, fronts_path)
    write_pareto_distance_svg(summaries, distance_path)
    return [fronts_path, distance_path]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--in",
        dest="in_path",
        type=Path,
        default=SCRIPT_DIR / "benchmark_results.json",
    )
    parser.add_argument(
        "--out-dir",
        dest="out_dir",
        type=Path,
        default=SCRIPT_DIR.parent.parent / "docs" / "eval",
    )
    args = parser.parse_args(argv)
    summaries = load_eligible_summaries(args.in_path)
    written = write_all_pareto_svgs(summaries, docs_eval_dir=args.out_dir)
    for path in written:
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
