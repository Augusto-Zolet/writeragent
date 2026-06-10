# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Trusted venv optimization helpers — Operations Research capabilities.

Includes execution templates, egress formatting, runner, and dispatch logic.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

# LO host imports (only imported/used if running on LO host)
from plugin.calc.address_utils import index_to_column
from plugin.calc.bridge import CalcBridge
from plugin.calc.manipulator import CellManipulator
from plugin.calc.python_function import to_calc_compatible
from plugin.calc.venv_python import _resolve_python_data
from plugin.doc.document_helpers import is_calc
from plugin.framework.errors import ToolExecutionError
from plugin.scripting.analysis import CoerceResult, coerce_to_dataframe
from plugin.scripting.client import run_optimize as client_run_optimize

if TYPE_CHECKING:
    from plugin.framework.tool import ToolContext

log = logging.getLogger(__name__)

# --- Common & Constants ---

HELPER_NAMES = {
    "optimize_portfolio",
    "linear_programming",
    "solve_scheduling_problem",
}

MAX_TABLE_ROWS = 50

OPTIMIZE_HEADER_PREFIX = "# writeragent:optimize"
_OPTIMIZE_HEADER_RE = re.compile(
    r"^\s*#\s*writeragent:optimize\s+helper=(\w+)\s+params=(\{.*\})\s*$",
    re.MULTILINE,
)

_DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    "optimize_portfolio": {"returns_col": None, "target_return": None, "risk_free_rate": 0.0},
    "linear_programming": {"c_col": "c", "a_cols": ["a1"], "b_col": "b", "maximize": False},
    "solve_scheduling_problem": {"cost_cols": ["cost1"]},
}

_HELPER_DESCRIPTIONS: dict[str, str] = {
    "optimize_portfolio": "Mean-variance portfolio optimization",
    "linear_programming": "Linear programming solver",
    "solve_scheduling_problem": "Assignment problem solver (e.g., workers to tasks)",
}


# --- Templates ---

@dataclass
class OptimizeScriptHeader:
    helper: str
    params: dict[str, Any]


def parse_optimize_script_header(code: str) -> OptimizeScriptHeader | None:
    match = _OPTIMIZE_HEADER_RE.search(code)
    if not match:
        return None
    try:
        params = json.loads(match.group(2))
        return OptimizeScriptHeader(helper=match.group(1), params=params)
    except Exception:
        return None


def get_optimize_template(helper: str) -> str | None:
    if helper not in HELPER_NAMES:
        return None
    params = _DEFAULT_PARAMS.get(helper, {})
    params_str = json.dumps(params)
    
    desc = _HELPER_DESCRIPTIONS.get(helper, helper.replace("_", " ").title())
    
    lines = [
        f"{OPTIMIZE_HEADER_PREFIX} helper={helper} params={params_str}",
        "#",
        f"# {desc}",
        "# This script delegates to the trusted optimize venv module.",
        "# Edit the JSON params above if needed. No other code runs.",
    ]
    
    return "\n".join(lines) + "\n"


# --- Runner ---

def calc_tool_context(uno_ctx: Any, doc: Any) -> ToolContext:
    """Minimal ToolContext-like object for range reads on the main thread."""
    from types import SimpleNamespace

    return cast(
        "ToolContext",
        SimpleNamespace(ctx=uno_ctx, doc=doc, doc_type="calc" if is_calc(doc) else None, active_domain=None),
    )


def run_trusted_optimize(
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
    """Fetch Calc data and run a trusted optimization helper in the user venv."""
    name = str(helper or "").strip()
    if not name:
        raise ToolExecutionError("helper is required", code="OPTIMIZE_ERROR")
    if name not in HELPER_NAMES:
        raise ToolExecutionError(f"Unknown helper {name!r}", code="OPTIMIZE_ERROR")

    dr = str(data_range).strip() if data_range else None
    if not dr and data is None:
        raise ToolExecutionError("Provide data_range or data", code="OPTIMIZE_ERROR")

    tool_ctx = calc_tool_context(uno_ctx, doc)
    py_data, err = _resolve_python_data(tool_ctx, data_range=dr, data=data)
    if err:
        raise ToolExecutionError(err, code="OPTIMIZE_ERROR")
    if py_data is None:
        raise ToolExecutionError("No data to optimize", code="OPTIMIZE_ERROR")

    spec: dict[str, Any] = {"helper": name, "headers": bool(headers)}
    if isinstance(params, dict) and params:
        spec["params"] = params

    context: dict[str, Any] = {}
    try:
        bridge = CalcBridge(doc)
        context["sheet_name"] = bridge.get_active_sheet().getName()
    except Exception:
        pass
    if task_hint:
        context["task_hint"] = str(task_hint)
    if dr:
        context["range_a1"] = dr

    return client_run_optimize(uno_ctx, spec, py_data, context=context or None)


# --- Egress ---

def is_optimize_result(value: Any) -> bool:
    """True when *value* matches the compact optimize helper result contract."""
    if not isinstance(value, dict):
        return False
    if "status" not in value:
        return False
    helper = value.get("helper")
    if isinstance(helper, str) and helper in HELPER_NAMES:
        return True
    if value.get("status") == "error":
        code = str(value.get("code") or "")
        return code == "OPTIMIZE_ERROR" or "OPTIMIZ" in code
    return False


def _cell(value: Any) -> Any:
    return to_calc_compatible(value)


def _append_blank(rows: list[list[Any]]) -> None:
    if rows and rows[-1]:
        rows.append([])


def _append_key_value_block(rows: list[list[Any]], title: str, mapping: dict[str, Any]) -> None:
    if not mapping:
        return
    _append_blank(rows)
    rows.append([title])
    rows.append(["Key", "Value"])
    for key, val in mapping.items():
        if isinstance(val, (dict, list)):
            rows.append([str(key), str(val)])
        else:
            rows.append([str(key), _cell(val)])


def format_optimize_for_calc(result: dict[str, Any]) -> list[list[Any]]:
    """Turn an optimize helper result dict into a row-major grid for ``write_formula_range``."""
    rows: list[list[Any]] = []

    if result.get("status") == "error":
        code = str(result.get("code") or "ERROR")
        message = str(result.get("message") or "Optimization failed.")
        return [[f"Optimization error ({code})"], [message]]

    helper = str(result.get("helper") or "optimization")
    raw_ctx = result.get("context")
    ctx: dict[str, Any] = raw_ctx if isinstance(raw_ctx, dict) else {}
    range_a1 = str(ctx.get("range_a1") or "").strip()
    title = f"{helper} — {range_a1}" if range_a1 else helper
    rows.append([title])

    metrics = result.get("metrics")
    if isinstance(metrics, dict) and metrics:
        _append_key_value_block(rows, "Metrics", metrics)

    flags = result.get("flags")
    if isinstance(flags, list) and flags:
        _append_blank(rows)
        rows.append(["Flags"])
        for item in flags:
            rows.append([str(item)])

    tables = result.get("tables")
    if isinstance(tables, list):
        for table in tables:
            if not isinstance(table, dict):
                continue
            _append_blank(rows)
            rows.append([str(table.get("name") or "table")])
            columns = table.get("columns")
            table_rows = table.get("rows")
            if isinstance(columns, list) and columns:
                rows.append([str(c) for c in columns])
            if isinstance(table_rows, list):
                for row in table_rows:
                    if isinstance(row, list):
                        rows.append([_cell(cell) for cell in row])
                    else:
                        rows.append([_cell(row)])
            if table.get("truncated"):
                total = table.get("total_rows")
                note = f"(showing first rows; {total} total)" if total is not None else "(truncated)"
                rows.append([note])

    metadata = result.get("metadata")
    if isinstance(metadata, dict) and metadata:
        subset = {k: metadata[k] for k in ("n_rows", "n_cols", "numeric_cols") if k in metadata}
        if subset:
            _append_key_value_block(rows, "Metadata", subset)

    if len(rows) == 1:
        rows.append(["(no tabular output)"])
    return rows


def calc_anchor_from_selection(doc: Any) -> tuple[int, int]:
    """Return (start_col, start_row) from the current Calc selection."""
    controller = doc.getCurrentController()
    selection = controller.getSelection()
    if selection is not None and hasattr(selection, "getRangeAddress"):
        addr = selection.getRangeAddress()
        return int(addr.StartColumn), int(addr.StartRow)
    return 0, 0


def insert_optimize_result_into_calc(
    doc: Any,
    uno_ctx: Any,
    result: dict[str, Any],
    *,
    start_col: int | None = None,
    start_row: int | None = None,
) -> int:
    """Write formatted optimization output starting at *start_col*/*start_row* (or selection). Returns row count."""
    if start_col is None or start_row is None:
        col, row = calc_anchor_from_selection(doc)
        start_col = col if start_col is None else start_col
        start_row = row if start_row is None else start_row

    grid = format_optimize_for_calc(result)
    bridge = CalcBridge(doc)
    manipulator = CellManipulator(bridge)
    addr = f"{index_to_column(start_col)}{start_row + 1}"
    manipulator.write_formula_range(addr, grid)
    return len(grid)


# --- Core Helper Implementations (Venv Execution Path) ---

def _missing_package_error(helper: str, package: str) -> dict[str, Any]:
    return _error_result(
        "MISSING_PACKAGE",
        f"{package} is required for {helper}.",
        helper=helper,
    )


def _table_from_df(df: Any, *, name: str, max_rows: int = MAX_TABLE_ROWS) -> dict[str, Any]:
    limited = df.head(max_rows)
    return {
        "name": name,
        "columns": [str(c) for c in limited.columns],
        "rows": limited.where(limited.notna(), None).values.tolist(),
        "truncated": len(df) > max_rows,
        "total_rows": int(len(df)),
    }


def _ok_result(helper: str, **payload: Any) -> dict[str, Any]:
    return {"status": "ok", "helper": helper, **payload}


def _error_result(code: str, message: str, *, helper: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "error", "code": code, "message": message}
    if helper:
        out["helper"] = helper
    if details:
        out["details"] = details
    return out


def _resolve_df(data: Any, *, headers: bool = True, header_row: int = 0, sheet_hint: str | None = None) -> CoerceResult:
    if isinstance(data, CoerceResult):
        return data
    if hasattr(data, "columns") and hasattr(data, "index"):
        df = data.copy()
        meta: dict[str, Any] = {
            "n_rows": int(len(df)),
            "n_cols": int(len(df.columns)),
            "numeric_cols": [str(c) for c in df.select_dtypes(include="number").columns],
            "dropped_rows": 0,
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


def linear_programming(
    data: Any,
    *,
    c_col: str,
    a_cols: list[str],
    b_col: str,
    bounds: tuple[float | None, float | None] | None = (0, None),
    maximize: bool = False,
    headers: bool = True,
    header_row: int = 0,
    sheet_hint: str | None = None,
) -> dict[str, Any]:
    """Solve a linear programming problem using scipy.optimize.linprog.
    
    Future: Consider pulp for more complex formulations.
    """
    import numpy as np
    import pandas as pd
    from scipy import optimize as scipy_optimize

    coerced = _resolve_df(data, headers=headers, header_row=header_row, sheet_hint=sheet_hint)
    df = coerced.df.dropna(subset=[c_col, b_col] + a_cols)
    
    if df.empty:
        return _error_result("INSUFFICIENT_DATA", "No data for linear programming", helper="linear_programming")

    # Objective function coefficients
    c = df[c_col].values.astype(float)
    if maximize:
        c = -c

    # Inequality constraints matrix (A_ub * x <= b_ub)
    A_ub = df[a_cols].values.astype(float).T
    b_ub = df[b_col].values.astype(float)
    
    # Needs to match dimensions
    if len(b_ub) != A_ub.shape[0]:
        # Assume A is provided such that each column is a variable, each row a constraint
        A_ub = df[a_cols].values.astype(float)
        b_ub = np.zeros(A_ub.shape[0]) # if b isn't correctly dimensioned

    try:
        res = scipy_optimize.linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=(bounds,) * len(c) if bounds else None)
    except Exception as e:
        return _error_result("OPTIMIZATION_FAILED", str(e), helper="linear_programming")

    if not res.success:
        return _error_result("OPTIMIZATION_FAILED", res.message, helper="linear_programming")

    solution_df = pd.DataFrame({
        "variable_index": range(len(res.x)),
        "optimal_value": np.round(res.x, 4)
    })
    table = _table_from_df(solution_df, name="lp_solution")

    metrics = {
        "objective_value": float(-res.fun) if maximize else float(res.fun),
        "status": res.message,
        "iterations": int(res.nit)
    }

    return _ok_result("linear_programming", metrics=metrics, tables=[table], metadata=coerced.metadata)


def optimize_portfolio(
    data: Any,
    *,
    returns_col: list[str] | None = None,
    target_return: float | None = None,
    risk_free_rate: float = 0.0,
    headers: bool = True,
    header_row: int = 0,
    sheet_hint: str | None = None,
) -> dict[str, Any]:
    """Mean-variance portfolio optimization."""
    import numpy as np
    import pandas as pd
    from scipy import optimize as scipy_optimize

    coerced = _resolve_df(data, headers=headers, header_row=header_row, sheet_hint=sheet_hint)
    df = coerced.df
    
    try:
        numeric_cols = _numeric_columns(df, returns_col)
    except ValueError as exc:
        return _error_result("UNKNOWN_COLUMN", str(exc), helper="optimize_portfolio")

    if not numeric_cols or len(numeric_cols) < 2:
        return _error_result("INSUFFICIENT_DATA", "Need at least two numeric columns (assets).", helper="optimize_portfolio")

    returns = df[numeric_cols].astype(float)
    mean_returns = returns.mean().values
    cov_matrix = returns.cov().values
    num_assets = len(mean_returns)

    # Objective: Minimize portfolio variance
    def portfolio_variance(weights):
        return weights.T @ cov_matrix @ weights

    # Constraints: sum of weights = 1
    constraints: list[dict[str, Any]] = [
        {"type": "eq", "fun": lambda x: np.sum(x) - 1}
    ]

    # If target_return is specified, add it to constraints
    if target_return is not None:
        constraints.append({
            "type": "eq",
            "fun": lambda x: np.sum(mean_returns * x) - target_return
        })

    # Bounds: weights between 0 and 1 (no short selling)
    bounds = tuple((0.0, 1.0) for _ in range(num_assets))
    
    # Initial guess: equal weighting
    init_guess = np.array(num_assets * [1.0 / num_assets])

    try:
        result = scipy_optimize.minimize(
            portfolio_variance,
            init_guess,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints
        )
    except Exception as e:
        return _error_result("OPTIMIZATION_FAILED", str(e), helper="optimize_portfolio")

    if not result.success:
        return _error_result("OPTIMIZATION_FAILED", result.message, helper="optimize_portfolio")

    weights = np.round(result.x, 4)
    expected_return = np.sum(mean_returns * weights)
    expected_volatility = np.sqrt(result.fun)
    sharpe_ratio = (expected_return - risk_free_rate) / expected_volatility if expected_volatility > 0 else 0

    weights_df = pd.DataFrame({
        "asset": numeric_cols,
        "weight": weights
    })
    # Filter out near-zero weights
    weights_df = weights_df[weights_df["weight"] > 1e-4]
    
    table = _table_from_df(weights_df, name="portfolio_weights")

    metrics = {
        "expected_return": float(expected_return),
        "expected_volatility": float(expected_volatility),
        "sharpe_ratio": float(sharpe_ratio)
    }

    return _ok_result("optimize_portfolio", metrics=metrics, tables=[table], metadata=coerced.metadata)


def solve_scheduling_problem(
    data: Any,
    *,
    cost_cols: list[str] | None = None,
    headers: bool = True,
    header_row: int = 0,
    sheet_hint: str | None = None,
) -> dict[str, Any]:
    """Solve an assignment problem (e.g. workers to tasks) using linear_sum_assignment."""
    import pandas as pd
    from scipy import optimize as scipy_optimize

    coerced = _resolve_df(data, headers=headers, header_row=header_row, sheet_hint=sheet_hint)
    df = coerced.df
    
    try:
        numeric_cols = _numeric_columns(df, cost_cols)
    except ValueError as exc:
        return _error_result("UNKNOWN_COLUMN", str(exc), helper="solve_scheduling_problem")

    if not numeric_cols:
        return _error_result("INSUFFICIENT_DATA", "Need numeric columns for cost matrix.", helper="solve_scheduling_problem")

    cost_matrix = df[numeric_cols].values.astype(float)
    
    try:
        row_ind, col_ind = scipy_optimize.linear_sum_assignment(cost_matrix)
    except Exception as e:
        return _error_result("OPTIMIZATION_FAILED", str(e), helper="solve_scheduling_problem")

    total_cost = cost_matrix[row_ind, col_ind].sum()
    
    assignment_df = pd.DataFrame({
        "row_index": row_ind,
        "assigned_column": [numeric_cols[i] for i in col_ind],
        "cost": cost_matrix[row_ind, col_ind]
    })
    
    table = _table_from_df(assignment_df, name="optimal_assignment")

    metrics = {
        "total_cost": float(total_cost),
        "assignments": len(row_ind)
    }

    return _ok_result("solve_scheduling_problem", metrics=metrics, tables=[table], metadata=coerced.metadata)


def _dispatch_helper(name: str, data: Any, params: dict[str, Any], *, headers: bool, header_row: int, context: dict[str, Any]) -> dict[str, Any]:
    sheet_hint = context.get("sheet_name") if isinstance(context.get("sheet_name"), str) else None
    common: dict[str, Any] = {"headers": headers, "header_row": header_row, "sheet_hint": sheet_hint}

    if name == "optimize_portfolio":
        return optimize_portfolio(data, returns_col=params.get("returns_col"), target_return=params.get("target_return"), risk_free_rate=params.get("risk_free_rate", 0.0), **common)
    if name == "linear_programming":
        if "c_col" not in params or "a_cols" not in params or "b_col" not in params:
            return _error_result("MISSING_PARAM", "linear_programming requires c_col, a_cols, and b_col", helper=name)
        return linear_programming(data, c_col=params["c_col"], a_cols=params["a_cols"], b_col=params["b_col"], bounds=params.get("bounds", (0, None)), maximize=params.get("maximize", False), **common)
    if name == "solve_scheduling_problem":
        return solve_scheduling_problem(data, cost_cols=params.get("cost_cols"), **common)

    return _error_result("UNKNOWN_HELPER", f"Optimization helper {name!r} not found", helper=name)


def run_optimize(
    spec: dict[str, Any] | str,
    data: Any,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Spec-driven dispatcher — single trusted entry for host RPC."""
    if isinstance(spec, str):
        spec_dict: dict[str, Any] = {"helper": spec}
    elif isinstance(spec, dict):
        spec_dict = spec
    else:
        return _error_result("INVALID_SPEC", "spec must be a dict or helper name string")

    helper = str(spec_dict.get("helper") or "").strip()
    if not helper:
        return _error_result("MISSING_HELPER", "spec.helper is required")
    if helper not in HELPER_NAMES:
        return _error_result("UNKNOWN_HELPER", f"Unknown helper {helper!r}", helper=helper)

    params: dict[str, Any] = spec_dict["params"] if isinstance(spec_dict.get("params"), dict) else {}
    headers = bool(spec_dict.get("headers", True))
    header_row = int(spec_dict.get("header_row", 0))
    ctx = context if isinstance(context, dict) else {}

    try:
        result = _dispatch_helper(helper, data, params, headers=headers, header_row=header_row, context=ctx)
    except Exception as exc:
        log.exception("Optimization helper %s failed", helper)
        return _error_result("OPTIMIZATION_FAILED", str(exc), helper=helper)

    if isinstance(result, dict) and result.get("status") == "ok" and ctx:
        result["context"] = {k: v for k, v in ctx.items() if k in ("sheet_name", "range_a1", "task_hint")}

    return result
