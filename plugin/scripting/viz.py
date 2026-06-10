# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Trusted venv visualization helpers — matplotlib/seaborn plots from sheet data.

Includes execution templates, egress formatting, runner, and dispatch logic.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from plugin.calc.analysis_runner import calc_tool_context
from plugin.calc.venv_python import _resolve_python_data
from plugin.doc.document_helpers import is_calc, is_draw, is_writer
from plugin.scripting.analysis import CoerceResult, coerce_to_dataframe
from plugin.scripting.client import run_viz as client_run_viz
from plugin.scripting.image_payload import write_image_payload_to_temp
from plugin.scripting.payload_codec import is_image_payload
from plugin.framework.errors import ToolExecutionError
from plugin.framework.i18n import _

log = logging.getLogger(__name__)

# --- Constants & Common ---

HELPER_NAMES = frozenset(
    {
        "quick_plot",
        "plot_data",
        "correlation_heatmap",
        "time_series_plot",
    }
)

VIZ_VENV_PIP_INSTALL = "pip install matplotlib seaborn"

VIZ_HEADER_PREFIX = "# writeragent:viz"
_VIZ_HEADER_RE = re.compile(
    r"^\s*#\s*writeragent:viz\s+helper=(\w+)\s+params=(\{.*\})\s*$",
    re.MULTILINE,
)

_SHIPPED_TEMPLATES = frozenset({"quick_plot", "correlation_heatmap", "time_series_plot"})

_DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    "quick_plot": {},
    "correlation_heatmap": {"method": "pearson"},
    "time_series_plot": {"date_col": "Date", "value_col": "Amount"},
}

_HELPER_DESCRIPTIONS: dict[str, str] = {
    "quick_plot": "Auto line/bar chart from numeric columns in the data range.",
    "correlation_heatmap": "Heatmap of pairwise correlations (matplotlib/seaborn).",
    "time_series_plot": "Line plot for date_col vs value_col.",
}


# --- Templates ---

@dataclass(frozen=True)
class VizScriptMeta:
    helper: str
    params: dict[str, Any]


def _template_body(helper: str, params: dict[str, Any]) -> str:
    params_json = json.dumps(params, separators=(",", ":"))
    desc = _HELPER_DESCRIPTIONS.get(helper, helper)
    return (
        f"{VIZ_HEADER_PREFIX} helper={helper} params={params_json}\n"  # nosec
        f"# {desc}\n"
        f"# Set the data range in the toolbar (or select cells), then Run.\n"
        f"from plugin.scripting.viz import run_viz\n\n"
        f"result = run_viz(\n"
        f'    {{"helper": "{helper}", "params": {params_json}}},\n'
        f"    data,\n"
        f"    {{}},\n"
        f")\n"
    )


def get_viz_script_templates() -> dict[str, str]:
    """Return built-in viz helper scripts keyed by helper name."""
    return {
        helper: _template_body(helper, dict(_DEFAULT_PARAMS.get(helper, {})))
        for helper in sorted(_SHIPPED_TEMPLATES)
        if helper in HELPER_NAMES
    }


def parse_viz_script_header(code: str) -> VizScriptMeta | None:
    """Parse the machine-readable header from a built-in or copied viz script."""
    if not code or VIZ_HEADER_PREFIX not in code:
        return None
    match = _VIZ_HEADER_RE.search(code)
    if not match:
        return None
    helper = match.group(1)
    if helper not in HELPER_NAMES:
        return None
    try:
        params = json.loads(match.group(2))
    except json.JSONDecodeError:
        params = {}
    if not isinstance(params, dict):
        params = {}
    return VizScriptMeta(helper=helper, params=params)


# --- Runner ---

def supports_viz_manual(doc: Any) -> bool:
    """True when Run Python Script should expose Viz Helpers for *doc*."""
    if doc is None:
        return False
    try:
        return is_writer(doc) or is_calc(doc)
    except Exception:
        return False


def run_trusted_viz(
    uno_ctx: Any,
    doc: Any,
    *,
    helper: str,
    params: dict[str, Any] | None = None,
    data_range: str | None = None,
    data: Any = None,
    headers: bool = True,
    task_hint: str | None = None,
) -> dict[str, Any]:
    """Fetch Calc data and run a trusted viz helper in the user venv."""
    name = str(helper or "").strip()
    if not name:
        raise ToolExecutionError("helper is required", code="VIZ_ERROR")
    if name not in HELPER_NAMES:
        raise ToolExecutionError(f"Unknown helper {name!r}", code="VIZ_ERROR")

    if not is_calc(doc) and not is_writer(doc):
        raise ToolExecutionError("Viz helpers require a Writer or Calc document.", code="VIZ_ERROR")

    dr = str(data_range).strip() if data_range else None
    if not dr and data is None:
        raise ToolExecutionError("Provide data_range or data", code="VIZ_ERROR")

    tool_ctx = calc_tool_context(uno_ctx, doc)
    py_data, err = _resolve_python_data(tool_ctx, data_range=dr, data=data)
    if err:
        raise ToolExecutionError(err, code="VIZ_ERROR")
    if py_data is None:
        raise ToolExecutionError("No data to plot", code="VIZ_ERROR")

    spec: dict[str, Any] = {"helper": name, "headers": bool(headers)}
    if isinstance(params, dict) and params:
        spec["params"] = params

    context: dict[str, Any] = {}
    if is_calc(doc):
        try:
            from plugin.calc.bridge import CalcBridge

            context["sheet_name"] = CalcBridge(doc).get_active_sheet().getName()
        except Exception:
            pass
    if task_hint:
        context["task_hint"] = str(task_hint)
    if dr:
        context["range_a1"] = dr

    return client_run_viz(uno_ctx, spec, py_data, context=context or None)


# --- Egress ---

def is_viz_result(value: Any) -> bool:
    """True when *value* matches the compact viz helper result contract."""
    if not isinstance(value, dict):
        return False
    if "status" not in value:
        return False
    helper = value.get("helper")
    if isinstance(helper, str) and helper in HELPER_NAMES:
        return True
    image = value.get("image")
    return is_image_payload(image)


def extract_image_payload(value: Any) -> dict[str, Any] | None:
    """Return the ``__wa_payload__: image`` envelope from raw or viz-wrapped results."""
    if is_image_payload(value):
        return value
    if isinstance(value, dict):
        image = value.get("image")
        if is_image_payload(image):
            return image
    return None


def insert_image_payload_for_doc(
    ctx: Any,
    doc: Any,
    payload: dict[str, Any],
    *,
    title: str = "Plot",
) -> None:
    """Insert an image envelope into Calc, Writer, or Draw/Impress."""
    if is_calc(doc):
        from plugin.calc.python_image_egress import insert_image_result_on_sheet

        insert_image_result_on_sheet(ctx, payload)
        return
    if is_writer(doc):
        from plugin.writer.images.image_tools import insert_image_at_locator

        path = write_image_payload_to_temp(payload)
        insert_image_at_locator(ctx, doc, path, title=title, description="WriterAgent plot")
        return
    if is_draw(doc):
        from plugin.writer.images.image_tools import insert_image

        path = write_image_payload_to_temp(payload)
        insert_image(ctx, doc, path, 400, 300, title=title, description="WriterAgent plot", add_to_gallery=False)
        return
    raise ToolExecutionError(_("Unsupported document type for plot insertion."), code="VIZ_ERROR")


def insert_viz_result_into_doc(ctx: Any, doc: Any, result: dict[str, Any]) -> None:
    """Insert a viz helper result (image nested under ``image`` key)."""
    if result.get("status") == "error":
        code = str(result.get("code") or "VIZ_ERROR")
        message = str(result.get("message") or _("Viz helper failed."))
        raise ToolExecutionError(message, code=code, details={"viz_result": result})
    payload = extract_image_payload(result)
    if payload is None:
        raise ToolExecutionError(
            _("Viz helper returned no image payload."),
            code="VIZ_ERROR",
            details={"viz_result": result},
        )
    title = str(result.get("title") or result.get("helper") or "Plot")
    insert_image_payload_for_doc(ctx, doc, payload, title=title)


def try_insert_plot_result(ctx: Any, doc: Any, result_data: Any) -> bool:
    """Insert plot/image results when present. Returns True if insertion ran."""
    payload = extract_image_payload(result_data)
    if payload is None:
        return False
    title = "Plot"
    if isinstance(result_data, dict):
        title = str(result_data.get("title") or result_data.get("helper") or "Plot")
    insert_image_payload_for_doc(ctx, doc, payload, title=title)
    return True


# --- Core Helper Implementations (Venv Execution Path) ---

def _error_result(code: str, message: str, *, helper: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "error", "code": code, "message": message}
    if helper:
        out["helper"] = helper
    return out


def _missing_package_error(helper: str, package: str) -> dict[str, Any]:
    return _error_result(
        "MISSING_PACKAGE",
        f"{package} is required for {helper}. Install: {VIZ_VENV_PIP_INSTALL}",
        helper=helper,
    )


def _resolve_df(data: Any, *, headers: bool = True, header_row: int = 0, sheet_hint: str | None = None) -> CoerceResult:
    if isinstance(data, CoerceResult):
        return data
    if hasattr(data, "columns") and hasattr(data, "index"):
        df = data.copy()
        meta: dict[str, Any] = {
            "n_rows": int(len(df)),
            "n_cols": int(len(df.columns)),
            "numeric_cols": [str(c) for c in df.select_dtypes(include="number").columns],
        }
        if sheet_hint:
            meta["sheet_hint"] = sheet_hint
        return CoerceResult(df=df, metadata=meta)
    return coerce_to_dataframe(data, headers=headers, header_row=header_row, sheet_hint=sheet_hint)


def _numeric_columns(df: Any, columns: list[str] | None = None) -> list[str]:
    if columns:
        missing = [c for c in columns if c not in df.columns]
        if missing:
            raise ValueError(f"Unknown columns: {', '.join(missing)}")
        return list(columns)
    return [str(c) for c in df.select_dtypes(include="number").columns]


def _figure_payload(fig: Any) -> dict[str, Any]:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        raise ImportError("matplotlib") from None
    from plugin.scripting.venv_sandbox import _figure_to_image_payload

    payload = _figure_to_image_payload(fig)
    plt.close(fig)
    return payload


def _ok_viz(helper: str, fig: Any, *, chart_type: str, title: str = "", legend: bool = False) -> dict[str, Any]:
    return {
        "status": "ok",
        "helper": helper,
        "image": _figure_payload(fig),
        "title": title or helper,
        "chart_type": chart_type,
        "legend": legend,
        "writer_cleanup_hints": [],
    }


def _require_matplotlib(helper: str) -> Any | None:
    try:
        import matplotlib.pyplot as plt

        plt.switch_backend("Agg")
        return plt
    except ImportError:
        return None


def quick_plot(
    data: Any,
    *,
    x_col: str | None = None,
    y_cols: list[str] | None = None,
    headers: bool = True,
    header_row: int = 0,
    sheet_hint: str | None = None,
) -> dict[str, Any]:
    """Default line or bar chart from numeric columns."""
    plt = _require_matplotlib("quick_plot")
    if plt is None:
        return _missing_package_error("quick_plot", "matplotlib")

    coerced = _resolve_df(data, headers=headers, header_row=header_row, sheet_hint=sheet_hint)
    df = coerced.df
    try:
        numeric = _numeric_columns(df, y_cols)
    except ValueError as exc:
        return _error_result("UNKNOWN_COLUMN", str(exc), helper="quick_plot")
    if not numeric:
        return _error_result("NO_NUMERIC_COLUMNS", "No numeric columns to plot.", helper="quick_plot")

    y_name = numeric[0]
    x_values = df[x_col] if x_col and x_col in df.columns else range(len(df))
    y_values = df[y_name]

    fig, ax = plt.subplots(figsize=(8, 4))
    chart_type = "bar" if len(df) <= 12 else "line"
    if chart_type == "bar":
        ax.bar(range(len(y_values)), y_values.astype(float))
        ax.set_xticks(range(len(y_values)))
        if x_col and x_col in df.columns:
            ax.set_xticklabels([str(v) for v in x_values], rotation=45, ha="right")
    else:
        ax.plot(y_values.astype(float))
    ax.set_ylabel(y_name)
    ax.set_title(f"Quick plot: {y_name}")
    fig.tight_layout()
    return _ok_viz("quick_plot", fig, chart_type=chart_type, title=ax.get_title())


def plot_data(
    data: Any,
    *,
    spec: dict[str, Any] | None = None,
    headers: bool = True,
    header_row: int = 0,
    sheet_hint: str | None = None,
) -> dict[str, Any]:
    """Plot from numeric grid using a small chart spec dict."""
    plt = _require_matplotlib("plot_data")
    if plt is None:
        return _missing_package_error("plot_data", "matplotlib")

    spec = dict(spec or {})
    coerced = _resolve_df(data, headers=headers, header_row=header_row, sheet_hint=sheet_hint)
    df = coerced.df
    chart_type = str(spec.get("chart_type") or "line").lower()
    x_col = spec.get("x")
    y_col = spec.get("y")
    hue = spec.get("hue")
    title = str(spec.get("title") or "Plot")

    try:
        numeric = _numeric_columns(df)
    except ValueError as exc:
        return _error_result("UNKNOWN_COLUMN", str(exc), helper="plot_data")
    if not numeric:
        return _error_result("NO_NUMERIC_COLUMNS", "No numeric columns to plot.", helper="plot_data")

    y_name = str(y_col) if y_col in df.columns else numeric[0]
    fig, ax = plt.subplots(figsize=(8, 4))

    if chart_type == "scatter":
        x_name = str(x_col) if x_col in df.columns else (numeric[1] if len(numeric) > 1 else numeric[0])
        sample = df[[x_name, y_name]].dropna()
        ax.scatter(sample[x_name].astype(float), sample[y_name].astype(float))
        ax.set_xlabel(x_name)
        ax.set_ylabel(y_name)
    elif chart_type == "histogram":
        ax.hist(df[y_name].dropna().astype(float), bins=min(30, max(5, len(df) // 5)))
        ax.set_xlabel(y_name)
    elif chart_type == "bar":
        if x_col and x_col in df.columns:
            ax.bar(df[x_col].astype(str), df[y_name].astype(float))
            ax.set_xlabel(str(x_col))
        else:
            ax.bar(range(len(df)), df[y_name].astype(float))
        ax.set_ylabel(y_name)
    else:
        if x_col and x_col in df.columns:
            ax.plot(df[x_col], df[y_name].astype(float), label=str(y_name))
            ax.set_xlabel(str(x_col))
        else:
            ax.plot(df[y_name].astype(float), label=str(y_name))
        ax.set_ylabel(y_name)
        chart_type = "line"

    if hue and hue in df.columns:
        ax.legend(title=str(hue))
    ax.set_title(title)
    fig.tight_layout()
    return _ok_viz("plot_data", fig, chart_type=chart_type, title=title, legend=bool(hue))


def correlation_heatmap(
    data: Any,
    *,
    method: str = "pearson",
    headers: bool = True,
    header_row: int = 0,
    sheet_hint: str | None = None,
) -> dict[str, Any]:
    """Heatmap of pairwise numeric correlations."""
    plt = _require_matplotlib("correlation_heatmap")
    if plt is None:
        return _missing_package_error("correlation_heatmap", "matplotlib")

    coerced = _resolve_df(data, headers=headers, header_row=header_row, sheet_hint=sheet_hint)
    df = coerced.df
    numeric = df.select_dtypes(include="number")
    if numeric.shape[1] < 2:
        return _error_result("NOT_ENOUGH_NUMERIC", "Need at least two numeric columns.", helper="correlation_heatmap")

    corr = numeric.corr(method=method)
    fig, ax = plt.subplots(figsize=(max(6, numeric.shape[1]), max(5, numeric.shape[1] - 1)))

    try:
        import seaborn as sns

        sns.heatmap(corr, annot=numeric.shape[1] <= 8, fmt=".2f", cmap="coolwarm", ax=ax)
    except ImportError:
        im = ax.imshow(corr.values, cmap="coolwarm", aspect="auto")
        ax.set_xticks(range(len(corr.columns)))
        ax.set_yticks(range(len(corr.index)))
        ax.set_xticklabels([str(c) for c in corr.columns], rotation=45, ha="right")
        ax.set_yticklabels([str(c) for c in corr.index])
        fig.colorbar(im, ax=ax)

    ax.set_title(f"Correlation ({method})")
    fig.tight_layout()
    return _ok_viz("correlation_heatmap", fig, chart_type="heatmap", title=ax.get_title())


def time_series_plot(
    data: Any,
    *,
    date_col: str,
    value_col: str,
    headers: bool = True,
    header_row: int = 0,
    sheet_hint: str | None = None,
) -> dict[str, Any]:
    """Line plot for a date-indexed series."""
    plt = _require_matplotlib("time_series_plot")
    if plt is None:
        return _missing_package_error("time_series_plot", "matplotlib")

    coerced = _resolve_df(data, headers=headers, header_row=header_row, sheet_hint=sheet_hint)
    df = coerced.df
    if date_col not in df.columns:
        return _error_result("UNKNOWN_COLUMN", f"Unknown date column {date_col!r}", helper="time_series_plot")
    if value_col not in df.columns:
        return _error_result("UNKNOWN_COLUMN", f"Unknown value column {value_col!r}", helper="time_series_plot")

    series = df[[date_col, value_col]].dropna()
    if series.empty:
        return _error_result("INSUFFICIENT_DATA", "No rows to plot.", helper="time_series_plot")

    import pandas as pd
    dates = pd.to_datetime(series[date_col], errors="coerce")
    values = series[value_col].astype(float)
    mask = dates.notna()
    dates = dates[mask]
    values = values[mask]
    if dates.empty:
        return _error_result("INVALID_DATES", "Could not parse date column.", helper="time_series_plot")

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(dates, values)
    ax.set_xlabel(date_col)
    ax.set_ylabel(value_col)
    ax.set_title(f"{value_col} over time")
    fig.autofmt_xdate()
    fig.tight_layout()
    return _ok_viz("time_series_plot", fig, chart_type="line", title=ax.get_title())


def _dispatch_helper(name: str, data: Any, params: dict[str, Any], *, headers: bool, header_row: int, context: dict[str, Any]) -> dict[str, Any]:
    sheet_hint = context.get("sheet_name") if isinstance(context.get("sheet_name"), str) else None
    common: dict[str, Any] = {"headers": headers, "header_row": header_row, "sheet_hint": sheet_hint}

    if name == "quick_plot":
        return quick_plot(data, x_col=params.get("x_col"), y_cols=params.get("y_cols"), **common)
    if name == "plot_data":
        return plot_data(data, spec=params.get("spec") if isinstance(params.get("spec"), dict) else params, **common)
    if name == "correlation_heatmap":
        return correlation_heatmap(data, method=params.get("method", "pearson"), **common)
    if name == "time_series_plot":
        if not params.get("date_col") or not params.get("value_col"):
            return _error_result(
                "MISSING_PARAM",
                "time_series_plot requires params.date_col and params.value_col",
                helper=name,
            )
        return time_series_plot(
            data,
            date_col=str(params["date_col"]),
            value_col=str(params["value_col"]),
            **common,
        )
    return _error_result("UNKNOWN_HELPER", f"Unknown helper {name!r}", helper=name)


def run_viz(
    spec: dict[str, Any] | str,
    data: Any,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Spec-driven dispatcher for trusted viz helpers."""
    if isinstance(spec, str):
        spec_dict: dict[str, Any] = {"helper": spec}
    elif isinstance(spec, dict):
        spec_dict = spec
    else:
        return _error_result("INVALID_SPEC", "spec must be a dict or helper name")

    helper = str(spec_dict.get("helper") or "").strip()
    if not helper:
        return _error_result("MISSING_HELPER", "helper is required")
    if helper not in HELPER_NAMES:
        return _error_result("UNKNOWN_HELPER", f"Unknown helper {helper!r}", helper=helper)

    params = spec_dict.get("params")
    if params is None:
        params = {k: v for k, v in spec_dict.items() if k not in ("helper", "headers", "header_row")}
    if not isinstance(params, dict):
        params = {}

    headers = bool(spec_dict.get("headers", True))
    header_row = int(spec_dict.get("header_row", 0))
    ctx = context if isinstance(context, dict) else {}
    return _dispatch_helper(helper, data, params, headers=headers, header_row=header_row, context=ctx)
