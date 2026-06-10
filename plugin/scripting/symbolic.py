# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Trusted venv symbolic math helpers — SymPy only (Sage deferred).

Includes execution templates, egress formatting, runner, and dispatch logic.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from plugin.doc.document_helpers import is_calc, is_writer
from plugin.scripting.client import run_symbolic as client_run_symbolic
from plugin.framework.errors import ToolExecutionError
from plugin.framework.i18n import _

# --- Constants & Common ---

HELPER_NAMES = frozenset(
    {
        "solve_equation",
        "symbolic_simplify",
        "integrate",
        "differentiate",
        "latex_to_math_object",
    }
)

SYMBOLIC_VENV_PIP_INSTALL = "pip install sympy"

MATH_HEADER_PREFIX = "# writeragent:math"
_MATH_HEADER_RE = re.compile(
    r"^\s*#\s*writeragent:math\s+helper=(\w+)\s+params=(\{.*\})\s*$",
    re.MULTILINE,
)

_SHIPPED_TEMPLATES = frozenset({"solve_equation", "symbolic_simplify", "integrate"})

_DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    "solve_equation": {"equation": "x**2 - 4", "variable": "x"},
    "symbolic_simplify": {"expression": "(x + 1)**2 - x**2 - 2*x"},
    "integrate": {"expression": "sin(x)", "variable": "x"},
}

_HELPER_DESCRIPTIONS: dict[str, str] = {
    "solve_equation": "Solve an equation for a variable (use = or expression equal to zero).",
    "symbolic_simplify": "Simplify a symbolic expression.",
    "integrate": "Integrate an expression (add lower/upper for definite integrals).",
}


# --- Templates ---

@dataclass(frozen=True)
class MathScriptMeta:
    helper: str
    params: dict[str, Any]


def _template_body(helper: str, params: dict[str, Any]) -> str:
    params_json = json.dumps(params, separators=(",", ":"))
    desc = _HELPER_DESCRIPTIONS.get(helper, helper)
    return (
        f"{MATH_HEADER_PREFIX} helper={helper} params={params_json}\n"  # nosec
        f"# {desc}\n"
        f"# Edit params above, then Run.\n"
        f"from plugin.scripting.symbolic import run_symbolic\n\n"
        f"result = run_symbolic(\n"
        f'    {{"helper": "{helper}", "params": {params_json}}},\n'
        f"    None,\n"
        f"    {{}},\n"
        f")\n"
    )


def get_math_script_templates() -> dict[str, str]:
    """Return built-in math helper scripts keyed by helper name."""
    return {
        helper: _template_body(helper, dict(_DEFAULT_PARAMS.get(helper, {})))
        for helper in sorted(_SHIPPED_TEMPLATES)
        if helper in HELPER_NAMES
    }


def parse_math_script_header(code: str) -> MathScriptMeta | None:
    """Parse the machine-readable header from a built-in or copied math script."""
    if not code or MATH_HEADER_PREFIX not in code:
        return None
    match = _MATH_HEADER_RE.search(code)
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
    return MathScriptMeta(helper=helper, params=params)


# --- Runner ---

def supports_symbolic_manual(doc: Any) -> bool:
    """True when Run Python Script should expose Math Helpers for *doc*."""
    if doc is None:
        return False
    try:
        return is_writer(doc) or is_calc(doc)
    except Exception:
        return False


def run_trusted_symbolic(
    uno_ctx: Any,
    doc: Any,
    *,
    helper: str,
    params: dict[str, Any] | None = None,
    task_hint: str | None = None,
) -> dict[str, Any]:
    """Run a trusted symbolic helper in the user venv."""
    name = str(helper or "").strip()
    if not name:
        raise ToolExecutionError("helper is required", code="SYMBOLIC_ERROR")
    if name not in HELPER_NAMES:
        raise ToolExecutionError(f"Unknown helper {name!r}", code="SYMBOLIC_ERROR")
    if not is_calc(doc) and not is_writer(doc):
        raise ToolExecutionError("Symbolic helpers require a Writer or Calc document.", code="SYMBOLIC_ERROR")

    spec: dict[str, Any] = {"helper": name}
    if isinstance(params, dict) and params:
        spec["params"] = params

    context: dict[str, Any] = {}
    if task_hint:
        context["task_hint"] = str(task_hint)

    return client_run_symbolic(uno_ctx, spec, None, context=context or None)


# --- Egress ---

def is_symbolic_result(value: Any) -> bool:
    """True when *value* matches the compact symbolic helper result contract."""
    if not isinstance(value, dict):
        return False
    if "status" not in value:
        return False
    helper = value.get("helper")
    if isinstance(helper, str) and helper in HELPER_NAMES:
        return True
    return bool(value.get("latex"))


def format_symbolic_for_calc(result: dict[str, Any]) -> list[list[Any]]:
    """Turn a symbolic helper result into a row-major grid for sheet egress."""
    if result.get("status") == "error":
        code = str(result.get("code") or "ERROR")
        message = str(result.get("message") or "Symbolic helper failed.")
        return [[f"Symbolic error ({code})"], [message]]

    helper = str(result.get("helper") or "symbolic")
    rows: list[list[Any]] = [[helper]]
    latex = str(result.get("latex") or "").strip()
    text = str(result.get("text") or latex).strip()
    if latex:
        rows.append(["LaTeX", latex])
    if text and text != latex:
        rows.append(["Text", text])
    solutions = result.get("solutions")
    if isinstance(solutions, list) and solutions:
        rows.append(["Solutions"])
        for sol in solutions:
            rows.append([str(sol)])
    return rows


def insert_symbolic_result_into_writer(ctx: Any, doc: Any, result: dict[str, Any], *, display_block: bool = False) -> None:
    """Insert symbolic LaTeX as a Writer Math OLE object at the selection."""
    if result.get("status") == "error":
        code = str(result.get("code") or "SYMBOLIC_ERROR")
        message = str(result.get("message") or _("Symbolic helper failed."))
        raise ToolExecutionError(message, code=code, details={"symbolic_result": result})

    latex = str(result.get("latex") or "").strip()
    if not latex:
        raise ToolExecutionError(
            _("Symbolic helper returned no LaTeX."),
            code="SYMBOLIC_ERROR",
            details={"symbolic_result": result},
        )

    from plugin.writer.math.math_mml_convert import convert_latex_to_starmath, insert_writer_math_formula

    conv = convert_latex_to_starmath(ctx, latex, display_block=display_block)
    if not conv.ok or not conv.starmath:
        err = conv.error_message or "conversion_failed"
        raise ToolExecutionError(
            _("Failed to convert LaTeX to Writer Math: {error}").format(error=err),
            code="SYMBOLIC_ERROR",
            details={"latex": latex},
        )

    controller = doc.getCurrentController()
    if controller is None:
        raise ToolExecutionError(_("No active document view."), code="SYMBOLIC_ERROR")
    view_cursor = controller.getViewCursor()
    insert_writer_math_formula(doc, view_cursor, conv.starmath, display_block=display_block)


def insert_symbolic_result_into_calc(doc: Any, ctx: Any, result: dict[str, Any]) -> int:
    """Write symbolic result rows on the active Calc sheet."""
    from plugin.calc.analysis_egress import calc_anchor_from_selection
    from plugin.calc.address_utils import index_to_column
    from plugin.calc.bridge import CalcBridge
    from plugin.calc.manipulator import CellManipulator

    grid = format_symbolic_for_calc(result)
    col, row = calc_anchor_from_selection(doc)
    bridge = CalcBridge(doc)
    manipulator = CellManipulator(bridge)
    addr = f"{index_to_column(col)}{row + 1}"
    manipulator.write_formula_range(addr, grid)
    return len(grid)


def insert_symbolic_result_into_doc(ctx: Any, doc: Any, result: dict[str, Any], *, display_block: bool = False) -> None:
    """Insert a symbolic helper result into Writer or Calc."""
    if is_writer(doc):
        insert_symbolic_result_into_writer(ctx, doc, result, display_block=display_block)
        return
    if is_calc(doc):
        insert_symbolic_result_into_calc(doc, ctx, result)
        return
    raise ToolExecutionError(_("Unsupported document type for symbolic insertion."), code="SYMBOLIC_ERROR")


def try_insert_symbolic_result(ctx: Any, doc: Any, result_data: Any, *, display_block: bool = False) -> bool:
    """Insert symbolic results when present. Returns True if insertion ran."""
    if not is_symbolic_result(result_data):
        return False
    insert_symbolic_result_into_doc(ctx, doc, result_data, display_block=display_block)
    return True


# --- Core Helper Implementations (Venv Execution Path) ---

_PARSE_TRANSFORMS = None


def _error_result(code: str, message: str, *, helper: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "error", "code": code, "message": message}
    if helper:
        out["helper"] = helper
    return out


def _ok_result(helper: str, *, latex: str, text: str = "", **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": "ok",
        "helper": helper,
        "latex": latex,
        "text": text or latex,
        "writer_cleanup_hints": [],
        **extra,
    }
    return out


def _require_sympy(helper: str) -> Any | None:
    try:
        import sympy as sp
        return sp
    except ImportError:
        return None


def _parse_transformations() -> tuple[Any, ...]:
    global _PARSE_TRANSFORMS
    if _PARSE_TRANSFORMS is None:
        from sympy.parsing.sympy_parser import (
            implicit_multiplication_application,
            standard_transformations,
        )
        _PARSE_TRANSFORMS = standard_transformations + (implicit_multiplication_application,)
    return _PARSE_TRANSFORMS


def _parse_expression(expr: str, *, helper: str) -> Any:
    sp = _require_sympy(helper)
    if sp is None:
        raise ValueError("MISSING_PACKAGE")
    from sympy.parsing.sympy_parser import parse_expr

    text = str(expr or "").strip()
    if not text:
        raise ValueError("empty expression")
    try:
        return parse_expr(text, transformations=_parse_transformations())
    except Exception as exc:
        raise ValueError(f"Could not parse expression: {exc}") from exc


def _parse_variable(name: str, *, helper: str) -> Any:
    sp = _require_sympy(helper)
    if sp is None:
        raise ValueError("MISSING_PACKAGE")
    var = str(name or "x").strip() or "x"
    return sp.Symbol(var)


def _to_latex(sp: Any, value: Any) -> str:
    return str(sp.latex(value))


def _missing_package(helper: str) -> dict[str, Any]:
    return _error_result(
        "MISSING_PACKAGE",
        f"sympy is required for {helper}. Install: {SYMBOLIC_VENV_PIP_INSTALL}",
        helper=helper,
    )


def symbolic_simplify(*, expression: str) -> dict[str, Any]:
    helper = "symbolic_simplify"
    sp = _require_sympy(helper)
    if sp is None:
        return _missing_package(helper)
    try:
        expr = _parse_expression(expression, helper=helper)
        simplified = sp.simplify(expr)
    except ValueError as exc:
        if str(exc) == "MISSING_PACKAGE":
            return _missing_package(helper)
        return _error_result("PARSE_ERROR", str(exc), helper=helper)
    except Exception as exc:
        return _error_result("SYMBOLIC_ERROR", str(exc), helper=helper)
    latex = _to_latex(sp, simplified)
    return _ok_result(helper, latex=latex, text=str(simplified))


def differentiate(*, expression: str, variable: str = "x") -> dict[str, Any]:
    helper = "differentiate"
    sp = _require_sympy(helper)
    if sp is None:
        return _missing_package(helper)
    try:
        expr = _parse_expression(expression, helper=helper)
        sym = _parse_variable(variable, helper=helper)
        result = sp.diff(expr, sym)
    except ValueError as exc:
        if str(exc) == "MISSING_PACKAGE":
            return _missing_package(helper)
        return _error_result("PARSE_ERROR", str(exc), helper=helper)
    except Exception as exc:
        return _error_result("SYMBOLIC_ERROR", str(exc), helper=helper)
    latex = _to_latex(sp, result)
    return _ok_result(helper, latex=latex, text=str(result), variable=variable)


def integrate_helper(*, expression: str, variable: str = "x", lower: str | None = None, upper: str | None = None) -> dict[str, Any]:
    helper = "integrate"
    sp = _require_sympy(helper)
    if sp is None:
        return _missing_package(helper)
    try:
        expr = _parse_expression(expression, helper=helper)
        sym = _parse_variable(variable, helper=helper)
        if lower is not None and upper is not None:
            a = _parse_expression(lower, helper=helper)
            b = _parse_expression(upper, helper=helper)
            result = sp.integrate(expr, (sym, a, b))
        else:
            result = sp.integrate(expr, sym)
    except ValueError as exc:
        if str(exc) == "MISSING_PACKAGE":
            return _missing_package(helper)
        return _error_result("PARSE_ERROR", str(exc), helper=helper)
    except Exception as exc:
        return _error_result("SYMBOLIC_ERROR", str(exc), helper=helper)
    latex = _to_latex(sp, result)
    return _ok_result(helper, latex=latex, text=str(result), variable=variable)


def solve_equation(*, equation: str, variable: str = "x") -> dict[str, Any]:
    helper = "solve_equation"
    sp = _require_sympy(helper)
    if sp is None:
        return _missing_package(helper)
    try:
        sym = _parse_variable(variable, helper=helper)
        text = str(equation or "").strip()
        if not text:
            return _error_result("MISSING_PARAM", "equation is required", helper=helper)
        if "=" in text:
            lhs_s, rhs_s = text.split("=", 1)
            lhs = _parse_expression(lhs_s, helper=helper)
            rhs = _parse_expression(rhs_s, helper=helper)
            eq = sp.Eq(lhs, rhs)
            solutions = sp.solve(eq, sym)
        else:
            expr = _parse_expression(text, helper=helper)
            solutions = sp.solve(expr, sym)
    except ValueError as exc:
        if str(exc) == "MISSING_PACKAGE":
            return _missing_package(helper)
        return _error_result("PARSE_ERROR", str(exc), helper=helper)
    except Exception as exc:
        return _error_result("SYMBOLIC_ERROR", str(exc), helper=helper)

    if not isinstance(solutions, list):
        solutions = [solutions]
    latex_parts = [_to_latex(sp, sol) for sol in solutions]
    latex = ", ".join(latex_parts) if latex_parts else ""
    text = ", ".join(str(s) for s in solutions)
    return _ok_result(
        helper,
        latex=latex,
        text=text,
        solutions=[str(s) for s in solutions],
        variable=variable,
    )


def latex_to_math_object(*, latex: str) -> dict[str, Any]:
    helper = "latex_to_math_object"
    sp = _require_sympy(helper)
    if sp is None:
        return _missing_package(helper)
    trimmed = str(latex or "").strip()
    if not trimmed:
        return _error_result("MISSING_PARAM", "latex is required", helper=helper)
    # Validate by attempting a lightweight parse when the input looks like plain SymPy syntax.
    if "=" not in trimmed and "\\" not in trimmed:
        try:
            expr = _parse_expression(trimmed, helper=helper)
            trimmed = _to_latex(sp, expr)
        except ValueError:
            pass
    return _ok_result(helper, latex=trimmed, text=trimmed)


def _dispatch_helper(name: str, params: dict[str, Any]) -> dict[str, Any]:
    if name == "symbolic_simplify":
        return symbolic_simplify(expression=str(params.get("expression") or ""))
    if name == "differentiate":
        return differentiate(
            expression=str(params.get("expression") or ""),
            variable=str(params.get("variable") or "x"),
        )
    if name == "integrate":
        return integrate_helper(
            expression=str(params.get("expression") or ""),
            variable=str(params.get("variable") or "x"),
            lower=params.get("lower"),
            upper=params.get("upper"),
        )
    if name == "solve_equation":
        return solve_equation(
            equation=str(params.get("equation") or ""),
            variable=str(params.get("variable") or "x"),
        )
    if name == "latex_to_math_object":
        return latex_to_math_object(latex=str(params.get("latex") or params.get("expression") or ""))
    return _error_result("UNKNOWN_HELPER", f"Unknown helper {name!r}", helper=name)


def run_symbolic(
    spec: dict[str, Any] | str,
    data: Any = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Spec-driven dispatcher for trusted symbolic helpers."""
    del data, context  # reserved for future numeric substitution from sheet data
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
        params = {k: v for k, v in spec_dict.items() if k != "helper"}
    if not isinstance(params, dict):
        params = {}
    return _dispatch_helper(helper, params)
