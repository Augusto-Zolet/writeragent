# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Translate P1 Calc formulas to ``=PY()`` Python source via vendored AST."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from plugin.contrib.calc_formula_parser import (
    FunctionNode,
    OperandNode,
    OperatorNode,
    RangeNode,
    parse_formula,
)
from plugin.calc.spreadsheet_import.models import TranslationResult
from plugin.calc.spreadsheet_import.preprocess import normalize_lo_formula_for_parse
from plugin.calc.address_utils import parse_address, parse_range_string

_CROSS_SHEET_RE = re.compile(r"[!']")


@dataclass
class _CodegenState:
    ranges: list[str] = field(default_factory=list)
    _index: dict[str, int] = field(default_factory=dict)

    def add_range(self, addr: str) -> int:
        key = _canonical_range(addr)
        if key not in self._index:
            self._index[key] = len(self.ranges)
            self.ranges.append(key)
        return self._index[key]

    def ref_expr(self, addr: str) -> str:
        idx = self.add_range(addr)
        if len(self.ranges) == 1:
            return "data"
        return f"data[{idx}]"


def _canonical_range(addr: str) -> str:
    return str(addr).replace("$", "").upper()


def _walk_ranges(node, state: _CodegenState) -> None:
    if isinstance(node, RangeNode):
        state.add_range(node.address)
    elif isinstance(node, OperatorNode):
        if node.left is not None:
            _walk_ranges(node.left, state)
        if node.right is not None:
            _walk_ranges(node.right, state)
    elif isinstance(node, FunctionNode):
        for arg in node.args or []:
            _walk_ranges(arg, state)


def _emit_operand(node: OperandNode) -> str:
    if node.tsubtype == "logical":
        return "True" if str(node.tvalue).upper() == "TRUE" else "False"
    if node.tsubtype == "text":
        return repr(str(node.tvalue))
    if node.tsubtype == "error":
        raise ValueError("error literal")
    # number or none
    text = str(node.tvalue)
    if text.upper() in ("TRUE", "FALSE"):
        return "True" if text.upper() == "TRUE" else "False"
    try:
        val = float(text)
        if val.is_integer():
            return str(int(val)) if abs(val) < 1e15 else str(val)
        return str(val)
    except ValueError:
        return repr(text)


def _emit_expr(node, state: _CodegenState, cell_addr: str | None = None) -> str:
    if isinstance(node, RangeNode):
        return state.ref_expr(node.address)
    if isinstance(node, OperandNode):
        return _emit_operand(node)
    if isinstance(node, OperatorNode):
        return _emit_operator(node, state, cell_addr)
    if isinstance(node, FunctionNode):
        return _emit_function(node, state, cell_addr)
    raise ValueError(f"unknown node {type(node)}")


def _emit_operator(node: OperatorNode, state: _CodegenState, cell_addr: str | None = None) -> str:
    if node.ttype == "operator-prefix":
        rhs = _emit_expr(node.right, state, cell_addr)
        if node.tvalue == "-":
            return f"(-{rhs})"
        if node.tvalue == "+":
            return rhs
        raise ValueError("unsupported prefix op")
    if node.ttype != "operator-infix":
        raise ValueError("unsupported operator type")
    left = _emit_expr(node.left, state, cell_addr)
    right = _emit_expr(node.right, state, cell_addr)
    op = node.tvalue
    if op == "^":
        return f"({left} ** {right})"
    if op == "=":
        return f"({left} == {right})"
    if op == "<>":
        return f"({left} != {right})"
    if op == "&":
        return f"(str({left}) + str({right}))"
    return f"({left} {op} {right})"


def _emit_row_func(node: FunctionNode, state: _CodegenState, cell_addr: str | None = None) -> str:
    if not node.args:
        if cell_addr:
            try:
                _, r = parse_address(cell_addr)
                return f"float({r + 1})"
            except ValueError:
                pass
        return "float(1)"
    arg = node.args[0]
    if isinstance(arg, RangeNode):
        try:
            (sc, sr), (ec, er) = parse_range_string(arg.address)
            if sr == er:
                return f"float({sr + 1})"
            rows = [float(r) for r in range(sr + 1, er + 2)]
            return f"np.array({rows}, dtype=float)"
        except ValueError:
            pass
    return "float(1)"


def _emit_col_func(node: FunctionNode, state: _CodegenState, cell_addr: str | None = None) -> str:
    if not node.args:
        if cell_addr:
            try:
                c, _ = parse_address(cell_addr)
                return f"float({c + 1})"
            except ValueError:
                pass
        return "float(1)"
    arg = node.args[0]
    if isinstance(arg, RangeNode):
        try:
            (sc, sr), (ec, er) = parse_range_string(arg.address)
            if sc == ec:
                return f"float({sc + 1})"
            cols = [float(c) for c in range(sc + 1, ec + 2)]
            return f"np.array({cols}, dtype=float)"
        except ValueError:
            pass
    return "float(1)"


def _emit_rows_func(node: FunctionNode, state: _CodegenState) -> str:
    if not node.args:
        raise ValueError("ROWS arity")
    arg = node.args[0]
    if isinstance(arg, RangeNode):
        try:
            (sc, sr), (ec, er) = parse_range_string(arg.address)
            return f"float({abs(er - sr) + 1})"
        except ValueError:
            pass
    expr = _emit_expr(arg, state)
    return f"float(np.asarray({expr}).shape[0])"


def _emit_columns_func(node: FunctionNode, state: _CodegenState) -> str:
    if not node.args:
        raise ValueError("COLUMNS arity")
    arg = node.args[0]
    if isinstance(arg, RangeNode):
        try:
            (sc, sr), (ec, er) = parse_range_string(arg.address)
            return f"float({abs(ec - sc) + 1})"
        except ValueError:
            pass
    expr = _emit_expr(arg, state)
    return f"float(np.asarray({expr}).shape[1])" if "np.asarray" in expr or "data" in expr else "float(1.0)"


def _emit_switch(args: list[str]) -> str:
    if len(args) < 2:
        raise ValueError("SWITCH arity")
    expr = args[0]
    pairs = args[1:]
    if len(pairs) % 2 == 1:
        default = pairs[-1]
        cases = pairs[:-1]
    else:
        default = "None"
        cases = pairs
    res = default
    for i in range(len(cases) - 2, -1, -2):
        val = cases[i]
        ret = cases[i+1]
        res = f"({ret} if {expr} == {val} else {res})"
    return res


def _emit_ifs(args: list[str]) -> str:
    if len(args) < 2 or len(args) % 2 != 0:
        raise ValueError("IFS arity")
    res = "None"
    for i in range(len(args) - 2, -1, -2):
        cond = args[i]
        ret = args[i + 1]
        res = f"({ret} if {cond} else {res})"
    return res


# Functions that return arbitrary types — skip scalar float() wrap in translate_formula.
_NO_SCALAR_WRAP_FUNCTIONS = frozenset(
    {
        "TRUE",
        "FALSE",
        "IF",
        "IFS",
        "SWITCH",
        "AND",
        "OR",
        "NOT",
        "ISBLANK",
        "ISNUMBER",
        "ISNA",
        "ISERROR",
        "ISTEXT",
        "ISLOGICAL",
        "ISERR",
        "ISNONTEXT",
    }
)

# Helpers and array-returning emitters — skip scalar float() wrap.
_NO_FLOAT_WRAP_PREFIXES = (
    "_iferror(",
    "_ifna(",
    "_sumif(",
    "_sumifs(",
    "_countif(",
    "_countifs(",
    "_averageif(",
    "_averageifs(",
    "_xlookup(",
    "_textjoin(",
    "_eomonth(",
    "_networkdays(",
    "_regex(",
    "_subtotal(",
    "_lookup(",
    "_edate(",
    "_datedif(",
    "_sumproduct(",
    "_averagea(",
    "_text(",
    "_xmatch(",
    "_workday(",
    "_filter(",
    "_sort(",
    "_unique(",
    "_sortby(",
    "_rank(",
    "_large(",
    "_small(",
    "_mode(",
)


def _emit_function(node: FunctionNode, state: _CodegenState, cell_addr: str | None = None) -> str:
    name = str(node.tvalue).upper().replace("_XLFN.", "")
    if name == "ROW":
        return _emit_row_func(node, state, cell_addr)
    if name == "COLUMN":
        return _emit_col_func(node, state, cell_addr)
    if name == "ROWS":
        return _emit_rows_func(node, state)
    if name == "COLUMNS":
        return _emit_columns_func(node, state)
    args = [_emit_expr(arg, state, cell_addr) for arg in (node.args or [])]
    if name == "SWITCH":
        return _emit_switch(args)
    if name == "IFS":
        return _emit_ifs(args)
    emitted = _P1_FUNCTION_EMITTERS.get(name)
    if emitted is None:
        raise ValueError(f"unsupported function {name}")
    return emitted(args)


def _float_wrap(expr: str) -> str:
    return f"float({expr})"


def _emit_if(args: list[str]) -> str:
    if len(args) != 3:
        raise ValueError("IF arity")
    return f"({args[1]} if {args[0]} else {args[2]})"


# P1 function emitters: args are already Python sub-expressions using data[i].
_P1_FUNCTION_EMITTERS: dict[str, Callable[[list[str]], str]] = {
    "SUM": lambda a: _float_wrap(f"np.sum({a[0]})"),
    "AVERAGE": lambda a: _float_wrap(f"np.mean({a[0]})"),
    "PRODUCT": lambda a: _float_wrap(f"np.prod({a[0]})"),
    "MAX": lambda a: _float_wrap(f"np.nanmax({a[0]})"),
    "MIN": lambda a: _float_wrap(f"np.nanmin({a[0]})"),
    "COUNT": lambda a: _float_wrap(f"np.sum(np.isfinite(np.asarray({a[0]}, dtype=float).ravel()))"),
    "COUNTA": lambda a: _float_wrap(
        f"sum(1 for x in np.asarray({a[0]}).ravel() if x is not None and str(x) != '')"
    ),
    "ABS": lambda a: _float_wrap(f"np.abs({a[0]})"),
    "SQRT": lambda a: _float_wrap(f"np.sqrt({a[0]})"),
    "SIGN": lambda a: _float_wrap(f"np.sign({a[0]})"),
    "INT": lambda a: _float_wrap(f"np.floor({a[0]})"),
    "TRUNC": lambda a: _float_wrap(f"np.trunc({a[0]})"),
    "EXP": lambda a: _float_wrap(f"np.exp({a[0]})"),
    "LN": lambda a: _float_wrap(f"np.log({a[0]})"),
    "LOG10": lambda a: _float_wrap(f"np.log10({a[0]})"),
    "MOD": lambda a: _float_wrap(f"{a[0]} % {a[1]}"),
    "POWER": lambda a: _float_wrap(f"{a[0]} ** {a[1]}"),
    "ROUND": lambda a: _float_wrap(f"np.round({a[0]}, {a[1]})") if len(a) > 1 else _float_wrap(f"np.round({a[0]})"),
    "SIN": lambda a: _float_wrap(f"np.sin({a[0]})"),
    "COS": lambda a: _float_wrap(f"np.cos({a[0]})"),
    "TAN": lambda a: _float_wrap(f"np.tan({a[0]})"),
    "NOT": lambda a: f"(not {a[0]})",
    "TRUE": lambda _a: "True",
    "FALSE": lambda _a: "False",
    "PI": lambda _a: "math.pi",
    "IF": _emit_if,
    "AND": lambda a: f"all([{', '.join(a)}])",
    "OR": lambda a: f"any([{', '.join(a)}])",
    # Text (P2)
    "CONCATENATE": lambda a: f'"".join(str(x) for x in [{", ".join(a)}])',
    "CONCAT": lambda a: f'"".join(str(x) for x in np.asarray([{", ".join(a)}]).ravel())',
    "LEFT": lambda a: f'str({a[0]})[:int({a[1]})]' if len(a) > 1 else f'str({a[0]})[:1]',
    "RIGHT": lambda a: f'str({a[0]})[-int({a[1]}):]' if len(a) > 1 else f'str({a[0]})[-1:]',
    "MID": lambda a: f'str({a[0]})[max(0, int({a[1]})-1) : max(0, int({a[1]})-1) + int({a[2]})]',
    "LEN": lambda a: f'float(len(str({a[0]})))',
    "LOWER": lambda a: f'str({a[0]}).lower()',
    "UPPER": lambda a: f'str({a[0]}).upper()',
    "PROPER": lambda a: f'str({a[0]}).title()',
    "TRIM": lambda a: f'str({a[0]}).strip()',
    "SUBSTITUTE": lambda a: f'str({a[0]}).replace(str({a[1]}), str({a[2]}))' if len(a) > 2 else f'str({a[0]}).replace(str({a[1]}), "")',
    "REPLACE": lambda a: f'str({a[0]})[:max(0, int({a[1]})-1)] + str({a[3]}) + str({a[0]})[max(0, int({a[1]})-1) + int({a[2]}):]',
    "FIND": lambda a: f'float(str({a[1]}).find(str({a[0]})) + 1)',
    "SEARCH": lambda a: f'float(str({a[1]}).lower().find(str({a[0]}).lower()) + 1)',
    "VALUE": lambda a: f'float({a[0]})',
    # Date & Time (P2)
    "TODAY": lambda _a: 'float(datetime.date.today().toordinal() - 693594)',
    "NOW": lambda _a: 'float(datetime.datetime.now().toordinal() - 693594)',
    "YEAR": lambda a: f'float(datetime.date.fromordinal(int({a[0]}) + 693594).year)',
    "MONTH": lambda a: f'float(datetime.date.fromordinal(int({a[0]}) + 693594).month)',
    "DAY": lambda a: f'float(datetime.date.fromordinal(int({a[0]}) + 693594).day)',
    # Statistical (P2)
    "STDEV": lambda a: _float_wrap(f"np.std({a[0]}, ddof=1)"),
    "STDEVP": lambda a: _float_wrap(f"np.std({a[0]}, ddof=0)"),
    "VAR": lambda a: _float_wrap(f"np.var({a[0]}, ddof=1)"),
    "VARP": lambda a: _float_wrap(f"np.var({a[0]}, ddof=0)"),
    "TRANSPOSE": lambda a: f"np.asarray({a[0]}).T.tolist()",
    # Lookup & Reference (P2)
    "VLOOKUP": lambda a: f'next((r[int({a[2]})-1] for r in np.asarray({a[1]}) if r[0] == {a[0]}), None)',
    "HLOOKUP": lambda a: f'next((np.asarray({a[1]})[int({a[2]})-1, i] for i, val in enumerate(np.asarray({a[1]})[0]) if val == {a[0]}), None)',
    "INDEX": lambda a: f'np.asarray({a[0]})[int({a[1]})-1, int({a[2]})-1]' if len(a) > 2 else f'np.asarray({a[0]})[int({a[1]})-1]',
    "MATCH": lambda a: f'float(next((i+1 for i, val in enumerate(np.asarray({a[1]}).ravel()) if val == {a[0]}), -1))',
    # Logical (P2)
    "IFERROR": lambda a: f"_iferror(lambda: {a[0]}, {a[1]})",
    "IFNA": lambda a: f"_ifna(lambda: {a[0]}, {a[1]})",
    # Math & Trig (P2)
    "ASIN": lambda a: _float_wrap(f"np.arcsin({a[0]})"),
    "ACOS": lambda a: _float_wrap(f"np.arccos({a[0]})"),
    "ATAN": lambda a: _float_wrap(f"np.arctan({a[0]})"),
    "ATAN2": lambda a: _float_wrap(f"np.arctan2({a[1]}, {a[0]})"),
    "DEGREES": lambda a: _float_wrap(f"np.degrees({a[0]})"),
    "RADIANS": lambda a: _float_wrap(f"np.radians({a[0]})"),
    "GCD": lambda a: _float_wrap(f"math.gcd({', '.join(a)})") if len(a) > 1 else _float_wrap(f"math.gcd({a[0]}, 0)"),
    "LCM": lambda a: _float_wrap(f"math.lcm({', '.join(a)})") if len(a) > 1 else _float_wrap(f"int({a[0]})"),
    # Date & Time (P2)
    "DATE": lambda a: f"float(datetime.date(int({a[0]}), int({a[1]}), int({a[2]})).toordinal() - 693594)",
    "HOUR": lambda a: f"float((datetime.datetime.fromordinal(693594) + datetime.timedelta(days=float({a[0]}))).hour)",
    "MINUTE": lambda a: f"float((datetime.datetime.fromordinal(693594) + datetime.timedelta(days=float({a[0]}))).minute)",
    "SECOND": lambda a: f"float((datetime.datetime.fromordinal(693594) + datetime.timedelta(days=float({a[0]}))).second)",
    # Conditional Aggregates
    "SUMIF": lambda a: f"_sumif({a[0]}, {a[1]}, {a[2]})" if len(a) > 2 else f"_sumif({a[0]}, {a[1]})",
    "SUMIFS": lambda a: f"_sumifs({a[0]}, {', '.join(a[1:])})",
    "COUNTIF": lambda a: f"_countif({a[0]}, {a[1]})",
    "COUNTIFS": lambda a: f"_countifs({', '.join(a)})",
    "AVERAGEIF": lambda a: f"_averageif({a[0]}, {a[1]}, {a[2]})" if len(a) > 2 else f"_averageif({a[0]}, {a[1]})",
    "AVERAGEIFS": lambda a: f"_averageifs({a[0]}, {', '.join(a[1:])})",
    # Lookup & Reference (XLOOKUP)
    "XLOOKUP": lambda a: f"_xlookup({', '.join(a)})",
    # Text (TEXTJOIN, REGEX)
    "TEXTJOIN": lambda a: f"_textjoin({', '.join(a)})",
    "REGEX": lambda a: f"_regex({', '.join(a)})",
    # Date & Time (EOMONTH, NETWORKDAYS)
    "EOMONTH": lambda a: f"_eomonth({a[0]}, {a[1]})",
    "NETWORKDAYS": lambda a: f"_networkdays({', '.join(a)})",
    # Tier A — high-frequency gaps
    "SUBTOTAL": lambda a: f"_subtotal({a[0]}, {a[1]})" if len(a) > 1 else f"_subtotal(9, {a[0]})",
    "ISBLANK": lambda a: f"_isblank({a[0]})",
    "ISNUMBER": lambda a: f"_isnumber({a[0]})",
    "ISNA": lambda a: f"_isna_check({a[0]})",
    "ISERROR": lambda a: f"_iserror_check({a[0]})",
    "LOOKUP": lambda a: f"_lookup({', '.join(a)})",
    "MEDIAN": lambda a: _float_wrap(f"np.median({a[0]})"),
    "COUNTBLANK": lambda a: _float_wrap(
        f"sum(1 for x in np.asarray({a[0]}).ravel() if x is None or x == '')"
    ),
    "ROUNDUP": lambda a: _float_wrap(f"np.ceil({a[0]} * 10**int({a[1]})) / 10**int({a[1]})")
    if len(a) > 1
    else _float_wrap(f"np.ceil({a[0]})"),
    "ROUNDDOWN": lambda a: _float_wrap(f"np.floor({a[0]} * 10**int({a[1]})) / 10**int({a[1]})")
    if len(a) > 1
    else _float_wrap(f"np.floor({a[0]})"),
    "CEILING": lambda a: _float_wrap(f"np.ceil({a[0]})")
    if len(a) == 1
    else _float_wrap(f"np.ceil({a[0]} / {a[1]}) * {a[1]}"),
    "FLOOR": lambda a: _float_wrap(f"np.floor({a[0]})")
    if len(a) == 1
    else _float_wrap(f"np.floor({a[0]} / {a[1]}) * {a[1]}"),
    "LOG": lambda a: _float_wrap(f"np.log({a[0]}) / np.log({a[1]})")
    if len(a) > 1
    else _float_wrap(f"np.log10({a[0]})"),
    "QUOTIENT": lambda a: _float_wrap(f"{a[0]} // {a[1]}"),
    "EDATE": lambda a: f"_edate({a[0]}, {a[1]})",
    "DATEDIF": lambda a: f"_datedif({', '.join(a)})",
    "SUMPRODUCT": lambda a: f"_sumproduct({', '.join(a)})",
    # Tier B — info, stats, text, misc
    "ISTEXT": lambda a: f"_istext({a[0]})",
    "ISLOGICAL": lambda a: f"_islogical({a[0]})",
    "ISERR": lambda a: f"_iserr({a[0]})",
    "ISNONTEXT": lambda a: f"_isnontext({a[0]})",
    "PERCENTILE": lambda a: _float_wrap(f"np.percentile(np.asarray({a[0]}, dtype=float).ravel(), float({a[1]}) * 100)"),
    "QUARTILE": lambda a: f"_quartile({a[0]}, {a[1]})",
    "RANK": lambda a: f"_rank({', '.join(a)})",
    "LARGE": lambda a: f"_large({a[0]}, {a[1]})",
    "SMALL": lambda a: f"_small({a[0]}, {a[1]})",
    "CORREL": lambda a: _float_wrap(f"np.corrcoef(np.asarray({a[0]}).ravel(), np.asarray({a[1]}).ravel())[0, 1]"),
    "COVAR": lambda a: _float_wrap(f"np.cov(np.asarray({a[0]}).ravel(), np.asarray({a[1]}).ravel())[0, 1]"),
    "MODE": lambda a: f"_mode({a[0]})",
    "AVERAGEA": lambda a: f"_averagea({a[0]})",
    "TEXT": lambda a: f"_text({a[0]}, {a[1]})" if len(a) > 1 else f"str({a[0]})",
    "EVEN": lambda a: _float_wrap(f"_even({a[0]})"),
    "ODD": lambda a: _float_wrap(f"_odd({a[0]})"),
    "RAND": lambda _a: "float(np.random.random())",
    "RANDBETWEEN": lambda a: f"float(np.random.randint(int({a[0]}), int({a[1]}) + 1))",
    "XMATCH": lambda a: f"_xmatch({', '.join(a)})",
    "WEEKDAY": lambda a: f"_weekday({a[0]})" if len(a) == 1 else f"_weekday({a[0]}, {a[1]})",
    "WEEKNUM": lambda a: f"_weeknum({', '.join(a)})",
    "WORKDAY": lambda a: f"_workday({', '.join(a)})",
    # Tier C — dynamic array helpers (LO 24.8+)
    "FILTER": lambda a: f"_filter({', '.join(a)})",
    "SORT": lambda a: f"_sort({', '.join(a)})",
    "UNIQUE": lambda a: f"_unique({', '.join(a)})",
    "SORTBY": lambda a: f"_sortby({', '.join(a)})",
}


def translate_formula(formula: str, cell_addr: str | None = None) -> TranslationResult:
    """Parse and codegen one Calc formula to ``result = …`` Python."""
    if not formula or not str(formula).strip().startswith("="):
        return TranslationResult(ok=False, reason="PARSE_ERROR")

    normalized = normalize_lo_formula_for_parse(formula)
    try:
        ast = parse_formula(normalized)
    except (SyntaxError, ValueError, IndexError):
        return TranslationResult(ok=False, reason="PARSE_ERROR")

    state = _CodegenState()
    try:
        _walk_ranges(ast, state)
        body = _emit_expr(ast, state, cell_addr)
    except ValueError as exc:
        msg = str(exc)
        if "cross-sheet" in msg:
            return TranslationResult(ok=False, reason="CROSS_SHEET_REF")
        if msg.startswith("unsupported function"):
            return TranslationResult(ok=False, reason="UNSUPPORTED_FUNCTION")
        return TranslationResult(ok=False, reason="PARSE_ERROR")

    if not state.ranges:
        # Literal-only (e.g. =PI() still has no ranges; =1+2 has none)
        pass
    else:
        # Scalar-wrap bare arithmetic for Calc double semantics.
        if isinstance(ast, OperatorNode) or (
            isinstance(ast, FunctionNode)
            and str(ast.tvalue).upper().replace("_XLFN.", "") not in _NO_SCALAR_WRAP_FUNCTIONS
        ):
            if (
                not body.startswith("float(")
                and body not in ("True", "False")
                and not any(prefix in body for prefix in _NO_FLOAT_WRAP_PREFIXES)
            ):
                body = _float_wrap(body)

    helpers = []
    if "_iferror(" in body:
        helpers.append(
            "def _iferror(f, alt):\n"
            "    try:\n"
            "        val = f()\n"
            "        import numpy as np\n"
            "        if isinstance(val, float) and np.isnan(val):\n"
            "            return alt\n"
            "        return val\n"
            "    except Exception:\n"
            "        return alt"
        )
    if "_ifna(" in body:
        helpers.append(
            "def _ifna(f, alt):\n"
            "    try:\n"
            "        val = f()\n"
            "        import numpy as np\n"
            "        if val is None or (isinstance(val, float) and np.isnan(val)):\n"
            "            return alt\n"
            "        return val\n"
            "    except Exception:\n"
            "        return alt"
        )
    if (
        "_match_criteria(" in body
        or "_sumif(" in body
        or "_sumifs(" in body
        or "_countif(" in body
        or "_countifs(" in body
        or "_averageif(" in body
        or "_averageifs(" in body
    ):
        helpers.append(
            "def _match_criteria(val, crit):\n"
            "    if crit is None or crit == '':\n"
            "        return val is None or val == ''\n"
            "    import re\n"
            "    if isinstance(crit, str):\n"
            "        m = re.match(r'^([<>=]+)(.*)$', crit)\n"
            "        if m:\n"
            "            op, val_str = m.groups()\n"
            "            try:\n"
            "                c_val = float(val_str)\n"
            "                v_val = float(val)\n"
            "            except (ValueError, TypeError):\n"
            "                c_val = val_str\n"
            "                v_val = val\n"
            "            if op == '=' or op == '==': return v_val == c_val\n"
            "            elif op == '<>': return v_val != c_val\n"
            "            elif op == '<': return v_val < c_val\n"
            "            elif op == '<=': return v_val <= c_val\n"
            "            elif op == '>': return v_val > c_val\n"
            "            elif op == '>=': return v_val >= c_val\n"
            "    try:\n"
            "        if float(val) == float(crit): return True\n"
            "    except (ValueError, TypeError):\n"
            "        pass\n"
            "    return str(val) == str(crit)"
        )
    if "_sumif(" in body:
        helpers.append(
            "def _sumif(r, crit, sr=None):\n"
            "    import numpy as np\n"
            "    r_flat = np.asarray(r).ravel()\n"
            "    sr_flat = np.asarray(sr).ravel() if sr is not None else r_flat\n"
            "    total = 0.0\n"
            "    for i in range(min(len(r_flat), len(sr_flat))):\n"
            "        if _match_criteria(r_flat[i], crit):\n"
            "            try:\n"
            "                val = float(sr_flat[i])\n"
            "                if not np.isnan(val):\n"
            "                    total += val\n"
            "            except (ValueError, TypeError):\n"
            "                pass\n"
            "    return float(total)"
        )
    if "_sumifs(" in body:
        helpers.append(
            "def _sumifs(sr, *args):\n"
            "    import numpy as np\n"
            "    sr_flat = np.asarray(sr).ravel()\n"
            "    cond_ranges = []\n"
            "    criteria = []\n"
            "    for i in range(0, len(args), 2):\n"
            "        cond_ranges.append(np.asarray(args[i]).ravel())\n"
            "        criteria.append(args[i+1])\n"
            "    total = 0.0\n"
            "    for idx in range(len(sr_flat)):\n"
            "        match = True\n"
            "        for cr, crit in zip(cond_ranges, criteria):\n"
            "            if idx >= len(cr) or not _match_criteria(cr[idx], crit):\n"
            "                match = False\n"
            "                break\n"
            "        if match:\n"
            "            try:\n"
            "                val = float(sr_flat[idx])\n"
            "                if not np.isnan(val):\n"
            "                    total += val\n"
            "            except (ValueError, TypeError):\n"
            "                pass\n"
            "    return float(total)"
        )
    if "_countif(" in body:
        helpers.append(
            "def _countif(r, crit):\n"
            "    import numpy as np\n"
            "    r_flat = np.asarray(r).ravel()\n"
            "    cnt = 0\n"
            "    for val in r_flat:\n"
            "        if _match_criteria(val, crit):\n"
            "            cnt += 1\n"
            "    return float(cnt)"
        )
    if "_countifs(" in body:
        helpers.append(
            "def _countifs(*args):\n"
            "    import numpy as np\n"
            "    cond_ranges = []\n"
            "    criteria = []\n"
            "    for i in range(0, len(args), 2):\n"
            "        cond_ranges.append(np.asarray(args[i]).ravel())\n"
            "        criteria.append(args[i+1])\n"
            "    if not cond_ranges:\n"
            "        return 0.0\n"
            "    min_len = min(len(cr) for cr in cond_ranges)\n"
            "    cnt = 0\n"
            "    for idx in range(min_len):\n"
            "        match = True\n"
            "        for cr, crit in zip(cond_ranges, criteria):\n"
            "            if not _match_criteria(cr[idx], crit):\n"
            "                match = False\n"
            "                break\n"
            "        if match:\n"
            "            cnt += 1\n"
            "    return float(cnt)"
        )
    if "_averageif(" in body:
        helpers.append(
            "def _averageif(r, crit, ar=None):\n"
            "    import numpy as np\n"
            "    r_flat = np.asarray(r).ravel()\n"
            "    ar_flat = np.asarray(ar).ravel() if ar is not None else r_flat\n"
            "    vals = []\n"
            "    for i in range(min(len(r_flat), len(ar_flat))):\n"
            "        if _match_criteria(r_flat[i], crit):\n"
            "            try:\n"
            "                val = float(ar_flat[i])\n"
            "                if not np.isnan(val):\n"
            "                    vals.append(val)\n"
            "            except (ValueError, TypeError):\n"
            "                pass\n"
            "    if not vals:\n"
            "        return float('nan')\n"
            "    return float(np.mean(vals))"
        )
    if "_averageifs(" in body:
        helpers.append(
            "def _averageifs(ar, *args):\n"
            "    import numpy as np\n"
            "    ar_flat = np.asarray(ar).ravel()\n"
            "    cond_ranges = []\n"
            "    criteria = []\n"
            "    for i in range(0, len(args), 2):\n"
            "        cond_ranges.append(np.asarray(args[i]).ravel())\n"
            "        criteria.append(args[i+1])\n"
            "    vals = []\n"
            "    for idx in range(len(ar_flat)):\n"
            "        match = True\n"
            "        for cr, crit in zip(cond_ranges, criteria):\n"
            "            if idx >= len(cr) or not _match_criteria(cr[idx], crit):\n"
            "                match = False\n"
            "                break\n"
            "        if match:\n"
            "            try:\n"
            "                val = float(ar_flat[idx])\n"
            "                if not np.isnan(val):\n"
            "                    vals.append(val)\n"
            "            except (ValueError, TypeError):\n"
            "                pass\n"
            "    if not vals:\n"
            "        return float('nan')\n"
            "    return float(np.mean(vals))"
        )
    if "_xlookup(" in body:
        helpers.append(
            "def _xlookup(lookup_val, lookup_arr, return_arr, if_not_found=None, match_mode=0, search_mode=1):\n"
            "    import numpy as np\n"
            "    l_flat = np.asarray(lookup_arr).ravel()\n"
            "    r_flat = np.asarray(return_arr)\n"
            "    indices = list(range(len(l_flat)))\n"
            "    if search_mode == -1:\n"
            "        indices.reverse()\n"
            "    best_idx = None\n"
            "    if match_mode == 0:\n"
            "        for idx in indices:\n"
            "            if l_flat[idx] == lookup_val:\n"
            "                best_idx = idx\n"
            "                break\n"
            "    elif match_mode in (-1, 1):\n"
            "        for idx in indices:\n"
            "            if l_flat[idx] == lookup_val:\n"
            "                best_idx = idx\n"
            "                break\n"
            "        if best_idx is None:\n"
            "            best_diff = None\n"
            "            for idx in indices:\n"
            "                try:\n"
            "                    diff = float(l_flat[idx]) - float(lookup_val)\n"
            "                    if match_mode == -1 and diff < 0:\n"
            "                        if best_diff is None or diff > best_diff:\n"
            "                            best_diff = diff\n"
            "                            best_idx = idx\n"
            "                    elif match_mode == 1 and diff > 0:\n"
            "                        if best_diff is None or diff < best_diff:\n"
            "                            best_diff = diff\n"
            "                            best_idx = idx\n"
            "                except (ValueError, TypeError):\n"
            "                    pass\n"
            "    elif match_mode == 2:\n"
            "        import re\n"
            "        if isinstance(lookup_val, str):\n"
            "            pattern = re.escape(lookup_val).replace(r'\\*', '.*').replace(r'\\?', '.')\n"
            "            regex = re.compile(f'^{pattern}$')\n"
            "            for idx in indices:\n"
            "                if isinstance(l_flat[idx], str) and regex.match(l_flat[idx]):\n"
            "                    best_idx = idx\n"
            "                    break\n"
            "        else:\n"
            "            for idx in indices:\n"
            "                if l_flat[idx] == lookup_val:\n"
            "                    best_idx = idx\n"
            "                    break\n"
            "    if best_idx is None:\n"
            "        return if_not_found\n"
            "    if r_flat.ndim == 1:\n"
            "        return r_flat[best_idx]\n"
            "    elif r_flat.ndim == 2:\n"
            "        l_shape = np.asarray(lookup_arr).shape\n"
            "        if len(l_shape) == 2 and l_shape[0] > 1 and l_shape[1] == 1:\n"
            "            return r_flat[best_idx].tolist()\n"
            "        else:\n"
            "            if best_idx < r_flat.shape[1]:\n"
            "                return r_flat[:, best_idx].tolist()\n"
            "            return r_flat.ravel()[best_idx]\n"
            "    return r_flat.ravel()[best_idx]"
        )
    if "_textjoin(" in body:
        helpers.append(
            "def _textjoin(delim, ignore_empty, *args):\n"
            "    import numpy as np\n"
            "    parts = []\n"
            "    for arg in args:\n"
            "        for val in np.asarray(arg).ravel():\n"
            "            if val is None or val == '':\n"
            "                if not ignore_empty:\n"
            "                    parts.append('')\n"
            "            else:\n"
            "                parts.append(str(val))\n"
            "    return str(delim).join(parts)"
        )
    if "_eomonth(" in body:
        helpers.append(
            "def _eomonth(start_date, months):\n"
            "    import datetime\n"
            "    try:\n"
            "        date_val = datetime.date.fromordinal(int(float(start_date)) + 693594)\n"
            "    except Exception:\n"
            "        return float('nan')\n"
            "    y, m = date_val.year, date_val.month\n"
            "    m += int(float(months))\n"
            "    y += (m - 1) // 12\n"
            "    m = (m - 1) % 12 + 1\n"
            "    if m == 12:\n"
            "        next_month = datetime.date(y + 1, 1, 1)\n"
            "    else:\n"
            "        next_month = datetime.date(y, m + 1, 1)\n"
            "    last_day = next_month - datetime.timedelta(days=1)\n"
            "    return float(last_day.toordinal() - 693594)"
        )
    if "_networkdays(" in body:
        helpers.append(
            "def _networkdays(start_date, end_date, holidays=None):\n"
            "    import datetime\n"
            "    import numpy as np\n"
            "    try:\n"
            "        sd = datetime.date.fromordinal(int(float(start_date)) + 693594)\n"
            "        ed = datetime.date.fromordinal(int(float(end_date)) + 693594)\n"
            "    except Exception:\n"
            "        return float('nan')\n"
            "    if sd > ed:\n"
            "        sign = -1\n"
            "        sd, ed = ed, sd\n"
            "    else:\n"
            "        sign = 1\n"
            "    h_dates = set()\n"
            "    if holidays is not None:\n"
            "        for h in np.asarray(holidays).ravel():\n"
            "            if h is not None and h != '':\n"
            "                try:\n"
            "                    h_dates.add(datetime.date.fromordinal(int(float(h)) + 693594))\n"
            "                except Exception:\n"
            "                    pass\n"
            "    curr = sd\n"
            "    days = 0\n"
            "    while curr <= ed:\n"
            "        if curr.weekday() < 5 and curr not in h_dates:\n"
            "            days += 1\n"
            "        curr += datetime.timedelta(days=1)\n"
            "    return float(sign * days)"
        )
    if "_regex(" in body:
        helpers.append(
            "def _regex(text, expr, replacement=None, flags=''):\n"
            "    import re\n"
            "    if text is None:\n"
            "        text = ''\n"
            "    text_str = str(text)\n"
            "    expr_str = str(expr)\n"
            "    re_flags = 0\n"
            "    if 'i' in str(flags).lower():\n"
            "        re_flags |= re.IGNORECASE\n"
            "    if replacement is None:\n"
            "        if 'g' in str(flags).lower():\n"
            "            matches = re.findall(expr_str, text_str, flags=re_flags)\n"
            "            if not matches:\n"
            "                return ''\n"
            "            if isinstance(matches[0], tuple):\n"
            "                return ', '.join(''.join(m) for m in matches)\n"
            "            return ', '.join(matches)\n"
            "        else:\n"
            "            m = re.search(expr_str, text_str, flags=re_flags)\n"
            "            if m:\n"
            "                return m.group(1) if m.groups() else m.group(0)\n"
            "            return ''\n"
            "    else:\n"
            "        rep_str = str(replacement)\n"
            "        if 'g' in str(flags).lower():\n"
            "            return re.sub(expr_str, rep_str, text_str, flags=re_flags)\n"
            "        else:\n"
            "            return re.sub(expr_str, rep_str, text_str, count=1, flags=re_flags)"
        )
    if "_isblank(" in body:
        helpers.append(
            "def _isblank(val):\n"
            "    return val is None or val == ''"
        )
    if "_isnumber(" in body:
        helpers.append(
            "def _isnumber(val):\n"
            "    return isinstance(val, (int, float)) and not isinstance(val, bool)"
        )
    if "_isna_check(" in body:
        helpers.append(
            "def _isna_check(val):\n"
            "    import numpy as np\n"
            "    if isinstance(val, str) and val.upper().startswith('#N/A'):\n"
            "        return True\n"
            "    return val is None or (isinstance(val, float) and np.isnan(val))"
        )
    if "_iserror_check(" in body:
        helpers.append(
            "def _iserror_check(val):\n"
            "    return isinstance(val, str) and val.startswith('#')"
        )
    if "_istext(" in body:
        helpers.append(
            "def _istext(val):\n"
            "    return isinstance(val, str) and not (isinstance(val, str) and val.startswith('#'))"
        )
    if "_islogical(" in body:
        helpers.append("def _islogical(val):\n    return isinstance(val, bool)")
    if "_iserr(" in body:
        helpers.append(
            "def _iserr(val):\n"
            "    if isinstance(val, str) and val.startswith('#'):\n"
            "        return not val.upper().startswith('#N/A')\n"
            "    return False"
        )
    if "_isnontext(" in body:
        helpers.append(
            "def _isnontext(val):\n"
            "    return not isinstance(val, str) or val == '' or val.startswith('#')"
        )
    if "_subtotal(" in body:
        helpers.append(
            "def _subtotal(fn_num, r):\n"
            "    import numpy as np\n"
            "    fn = int(float(fn_num)) % 100\n"
            "    flat = np.asarray(r).ravel()\n"
            "    nums = []\n"
            "    for x in flat:\n"
            "        if x is None or x == '':\n"
            "            continue\n"
            "        try:\n"
            "            v = float(x)\n"
            "            if not np.isnan(v):\n"
            "                nums.append(v)\n"
            "        except (ValueError, TypeError):\n"
            "            pass\n"
            "    arr = np.asarray(nums, dtype=float)\n"
            "    if fn == 1:\n"
            "        return float(np.mean(arr)) if len(arr) else 0.0\n"
            "    if fn == 2:\n"
            "        return float(len(arr))\n"
            "    if fn == 3:\n"
            "        return float(sum(1 for x in flat if x is not None and x != ''))\n"
            "    if fn == 4:\n"
            "        return float(np.max(arr)) if len(arr) else 0.0\n"
            "    if fn == 5:\n"
            "        return float(np.min(arr)) if len(arr) else 0.0\n"
            "    if fn == 6:\n"
            "        return float(np.prod(arr)) if len(arr) else 0.0\n"
            "    if fn == 7:\n"
            "        return float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0\n"
            "    if fn == 8:\n"
            "        return float(np.std(arr, ddof=0)) if len(arr) else 0.0\n"
            "    if fn == 9:\n"
            "        return float(np.sum(arr))\n"
            "    if fn == 10:\n"
            "        return float(np.var(arr, ddof=1)) if len(arr) > 1 else 0.0\n"
            "    if fn == 11:\n"
            "        return float(np.var(arr, ddof=0)) if len(arr) else 0.0\n"
            "    return float(np.sum(arr))"
        )
    if "_lookup(" in body:
        helpers.append(
            "def _lookup(lookup_val, *args):\n"
            "    import numpy as np\n"
            "    if len(args) == 1:\n"
            "        vec = np.asarray(args[0]).ravel()\n"
            "        result = vec\n"
            "    else:\n"
            "        lookup_vec = np.asarray(args[0]).ravel()\n"
            "        result = np.asarray(args[1]).ravel()\n"
            "        vec = lookup_vec\n"
            "    best_idx = None\n"
            "    for i, v in enumerate(vec):\n"
            "        try:\n"
            "            if float(v) <= float(lookup_val):\n"
            "                best_idx = i\n"
            "        except (ValueError, TypeError):\n"
            "            if str(v) <= str(lookup_val):\n"
            "                best_idx = i\n"
            "    if best_idx is None:\n"
            "        return None\n"
            "    if len(args) == 1:\n"
            "        return result[best_idx]\n"
            "    return result[best_idx]"
        )
    if "_edate(" in body:
        helpers.append(
            "def _edate(start_date, months):\n"
            "    import datetime\n"
            "    try:\n"
            "        date_val = datetime.date.fromordinal(int(float(start_date)) + 693594)\n"
            "    except Exception:\n"
            "        return float('nan')\n"
            "    y, m = date_val.year, date_val.month\n"
            "    m += int(float(months))\n"
            "    y += (m - 1) // 12\n"
            "    m = (m - 1) % 12 + 1\n"
            "    d = min(date_val.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])\n"
            "    return float(datetime.date(y, m, d).toordinal() - 693594)"
        )
    if "_datedif(" in body:
        helpers.append(
            "def _datedif(start_date, end_date, unit='D'):\n"
            "    import datetime\n"
            "    try:\n"
            "        sd = datetime.date.fromordinal(int(float(start_date)) + 693594)\n"
            "        ed = datetime.date.fromordinal(int(float(end_date)) + 693594)\n"
            "    except Exception:\n"
            "        return float('nan')\n"
            "    if sd > ed:\n"
            "        return float('nan')\n"
            "    u = str(unit).strip('\"').upper()\n"
            "    if u == 'D':\n"
            "        return float((ed - sd).days)\n"
            "    if u == 'M':\n"
            "        return float((ed.year - sd.year) * 12 + ed.month - sd.month)\n"
            "    if u == 'Y':\n"
            "        return float(ed.year - sd.year - ((ed.month, ed.day) < (sd.month, sd.day)))\n"
            "    if u == 'MD':\n"
            "        return float(ed.day - sd.day)\n"
            "    if u == 'YM':\n"
            "        return float(ed.month - sd.month - (ed.day < sd.day))\n"
            "    if u == 'YD':\n"
            "        return float((ed - datetime.date(ed.year, sd.month, sd.day)).days)\n"
            "    return float((ed - sd).days)"
        )
    if "_sumproduct(" in body:
        helpers.append(
            "def _sumproduct(*args):\n"
            "    import numpy as np\n"
            "    arrays = [np.asarray(a).ravel() for a in args]\n"
            "    if not arrays:\n"
            "        return 0.0\n"
            "    min_len = min(len(a) for a in arrays)\n"
            "    total = 0.0\n"
            "    for i in range(min_len):\n"
            "        prod = 1.0\n"
            "        for arr in arrays:\n"
            "            try:\n"
            "                prod *= float(arr[i])\n"
            "            except (ValueError, TypeError):\n"
            "                prod = 0.0\n"
            "                break\n"
            "        total += prod\n"
            "    return float(total)"
        )
    if "_averagea(" in body:
        helpers.append(
            "def _averagea(r):\n"
            "    import numpy as np\n"
            "    vals = []\n"
            "    for x in np.asarray(r).ravel():\n"
            "        if x is None or x == '':\n"
            "            vals.append(0.0)\n"
            "        else:\n"
            "            try:\n"
            "                vals.append(float(x))\n"
            "            except (ValueError, TypeError):\n"
            "                vals.append(0.0)\n"
            "    if not vals:\n"
            "        return float('nan')\n"
            "    return float(np.mean(vals))"
        )
    if "_quartile(" in body:
        helpers.append(
            "def _quartile(r, q):\n"
            "    import numpy as np\n"
            "    arr = np.asarray(r, dtype=float).ravel()\n"
            "    arr = arr[~np.isnan(arr)]\n"
            "    qi = int(float(q))\n"
            "    pct = {0: 0.0, 1: 25.0, 2: 50.0, 3: 75.0, 4: 100.0}.get(qi, float(qi) * 25.0)\n"
            "    return float(np.percentile(arr, pct)) if len(arr) else float('nan')"
        )
    if "_rank(" in body:
        helpers.append(
            "def _rank(val, r, order=0):\n"
            "    import numpy as np\n"
            "    arr = [float(x) for x in np.asarray(r).ravel() if x is not None and x != '']\n"
            "    try:\n"
            "        target = float(val)\n"
            "    except (ValueError, TypeError):\n"
            "        return float('nan')\n"
            "    if int(float(order)) == 0:\n"
            "        arr.sort(reverse=True)\n"
            "    else:\n"
            "        arr.sort()\n"
            "    try:\n"
            "        return float(arr.index(target) + 1)\n"
            "    except ValueError:\n"
            "        return float('nan')"
        )
    if "_large(" in body:
        helpers.append(
            "def _large(r, k):\n"
            "    import numpy as np\n"
            "    arr = sorted([float(x) for x in np.asarray(r).ravel() if x is not None and x != ''], reverse=True)\n"
            "    ki = int(float(k))\n"
            "    return float(arr[ki - 1]) if 0 < ki <= len(arr) else float('nan')"
        )
    if "_small(" in body:
        helpers.append(
            "def _small(r, k):\n"
            "    import numpy as np\n"
            "    arr = sorted([float(x) for x in np.asarray(r).ravel() if x is not None and x != ''])\n"
            "    ki = int(float(k))\n"
            "    return float(arr[ki - 1]) if 0 < ki <= len(arr) else float('nan')"
        )
    if "_mode(" in body:
        helpers.append(
            "def _mode(r):\n"
            "    import numpy as np\n"
            "    from collections import Counter\n"
            "    vals = [x for x in np.asarray(r).ravel() if x is not None and x != '']\n"
            "    if not vals:\n"
            "        return float('nan')\n"
            "    counts = Counter(vals)\n"
            "    return counts.most_common(1)[0][0]"
        )
    if "_text(" in body:
        helpers.append(
            "def _text(val, fmt):\n"
            "    fmt_str = str(fmt).strip('\"')\n"
            "    if fmt_str in ('0', '0.00', '#,##0'):\n"
            "        try:\n"
            "            return format(float(val), fmt_str.replace('#', '').replace(',', '') or '.0f')\n"
            "        except (ValueError, TypeError):\n"
            "            return str(val)\n"
            "    return str(val)"
        )
    if "_even(" in body or "_odd(" in body:
        helpers.append(
            "def _even(n):\n"
            "    import numpy as np\n"
            "    v = float(n)\n"
            "    i = int(np.trunc(v))\n"
            "    if i % 2 == 0:\n"
            "        return float(i)\n"
            "    return float(i + (1 if v >= 0 else -1))\n"
            "def _odd(n):\n"
            "    import numpy as np\n"
            "    v = float(n)\n"
            "    i = int(np.trunc(v))\n"
            "    if i % 2 != 0:\n"
            "        return float(i)\n"
            "    return float(i + (1 if v >= 0 else -1))"
        )
    if "_xmatch(" in body:
        helpers.append(
            "def _xmatch(lookup_val, lookup_arr, match_mode=0, search_mode=1):\n"
            "    import numpy as np\n"
            "    l_flat = np.asarray(lookup_arr).ravel()\n"
            "    indices = list(range(len(l_flat)))\n"
            "    if int(float(search_mode)) == -1:\n"
            "        indices.reverse()\n"
            "    mm = int(float(match_mode))\n"
            "    if mm == 0:\n"
            "        for idx in indices:\n"
            "            if l_flat[idx] == lookup_val:\n"
            "                return float(idx + 1)\n"
            "    elif mm in (-1, 1):\n"
            "        for idx in indices:\n"
            "            if l_flat[idx] == lookup_val:\n"
            "                return float(idx + 1)\n"
            "        best_idx = None\n"
            "        for idx in indices:\n"
            "            try:\n"
            "                diff = float(l_flat[idx]) - float(lookup_val)\n"
            "                if mm == -1 and diff < 0:\n"
            "                    if best_idx is None or diff > float(l_flat[best_idx]) - float(lookup_val):\n"
            "                        best_idx = idx\n"
            "                elif mm == 1 and diff > 0:\n"
            "                    if best_idx is None or diff < float(l_flat[best_idx]) - float(lookup_val):\n"
            "                        best_idx = idx\n"
            "            except (ValueError, TypeError):\n"
            "                pass\n"
            "        return float(best_idx + 1) if best_idx is not None else float('nan')\n"
            "    return float('nan')"
        )
    if "_weekday(" in body:
        helpers.append(
            "def _weekday(serial, return_type=1):\n"
            "    import datetime\n"
            "    try:\n"
            "        d = datetime.date.fromordinal(int(float(serial)) + 693594)\n"
            "    except Exception:\n"
            "        return float('nan')\n"
            "    rt = int(float(return_type))\n"
            "    wd = d.weekday()\n"
            "    if rt == 1:\n"
            "        return float(wd + 2 if wd < 6 else 1)\n"
            "    if rt == 2:\n"
            "        return float(wd + 1)\n"
            "    if rt == 3:\n"
            "        return float((wd + 6) % 7)\n"
            "    return float(wd + 1)"
        )
    if "_weeknum(" in body:
        helpers.append(
            "def _weeknum(serial, return_type=1):\n"
            "    import datetime\n"
            "    try:\n"
            "        d = datetime.date.fromordinal(int(float(serial)) + 693594)\n"
            "    except Exception:\n"
            "        return float('nan')\n"
            "    iso = d.isocalendar()\n"
            "    return float(iso[1])"
        )
    if "_workday(" in body:
        helpers.append(
            "def _workday(start_date, days, holidays=None):\n"
            "    import datetime\n"
            "    import numpy as np\n"
            "    try:\n"
            "        curr = datetime.date.fromordinal(int(float(start_date)) + 693594)\n"
            "    except Exception:\n"
            "        return float('nan')\n"
            "    h_dates = set()\n"
            "    if holidays is not None:\n"
            "        for h in np.asarray(holidays).ravel():\n"
            "            if h is not None and h != '':\n"
            "                try:\n"
            "                    h_dates.add(datetime.date.fromordinal(int(float(h)) + 693594))\n"
            "                except Exception:\n"
            "                    pass\n"
            "    remaining = int(float(days))\n"
            "    step = 1 if remaining >= 0 else -1\n"
            "    while remaining != 0:\n"
            "        curr += datetime.timedelta(days=step)\n"
            "        if curr.weekday() < 5 and curr not in h_dates:\n"
            "            remaining -= step\n"
            "    return float(curr.toordinal() - 693594)"
        )
    if "_filter(" in body:
        helpers.append(
            "def _filter(range_arr, criteria, if_empty=None):\n"
            "    import numpy as np\n"
            "    arr = np.asarray(range_arr)\n"
            "    crit = np.asarray(criteria)\n"
            "    if arr.ndim == 1:\n"
            "        mask = np.asarray([bool(x) for x in crit.ravel()[: len(arr)]])\n"
            "        out = arr.ravel()[mask]\n"
            "    else:\n"
            "        if crit.ndim == 1:\n"
            "            mask = np.asarray([bool(x) for x in crit.ravel()[: arr.shape[0]]])\n"
            "            out = arr[mask]\n"
            "        else:\n"
            "            mask = crit.astype(bool)\n"
            "            out = arr[mask]\n"
            "    if out.size == 0:\n"
            "        return if_empty\n"
            "    return out.tolist() if out.ndim > 1 else out.ravel().tolist()"
        )
    if "_sort(" in body:
        helpers.append(
            "def _sort(range_arr, sort_index=1, sort_order=1, by_col=False):\n"
            "    import numpy as np\n"
            "    arr = np.asarray(range_arr)\n"
            "    if arr.size == 0:\n"
            "        return []\n"
            "    si = max(1, int(float(sort_index))) - 1\n"
            "    asc = int(float(sort_order)) >= 0\n"
            "    if arr.ndim == 1:\n"
            "        out = np.sort(arr) if asc else np.sort(arr)[::-1]\n"
            "        return out.tolist()\n"
            "    if bool(by_col):\n"
            "        order = np.argsort(arr[:, si] if si < arr.shape[1] else arr[:, 0])\n"
            "        if not asc:\n"
            "            order = order[::-1]\n"
            "        return arr[:, order].T.tolist()\n"
            "    order = np.argsort(arr[:, si] if si < arr.shape[1] else arr[:, 0])\n"
            "    if not asc:\n"
            "        order = order[::-1]\n"
            "    return arr[order].tolist()"
        )
    if "_unique(" in body:
        helpers.append(
            "def _unique(arr, by_col=False, unique_only=False):\n"
            "    import numpy as np\n"
            "    data = np.asarray(arr)\n"
            "    if data.size == 0:\n"
            "        return []\n"
            "    if data.ndim == 1 or not bool(by_col):\n"
            "        flat = data.ravel().tolist()\n"
            "        seen = []\n"
            "        counts = {}\n"
            "        for x in flat:\n"
            "            counts[x] = counts.get(x, 0) + 1\n"
            "            if x not in seen:\n"
            "                seen.append(x)\n"
            "        if bool(unique_only):\n"
            "            return [x for x in seen if counts[x] == 1]\n"
            "        return seen\n"
            "    rows = [tuple(r) for r in data]\n"
            "    seen_rows = []\n"
            "    for row in rows:\n"
            "        if row not in seen_rows:\n"
            "            seen_rows.append(row)\n"
            "    return [list(r) for r in seen_rows]"
        )
    if "_sortby(" in body:
        helpers.append(
            "def _sortby(range_arr, by_array, sort_order=1, *extra):\n"
            "    import numpy as np\n"
            "    arr = np.asarray(range_arr)\n"
            "    by = np.asarray(by_array).ravel()\n"
            "    asc = int(float(sort_order)) >= 0\n"
            "    if arr.ndim == 1:\n"
            "        order = np.argsort(by[: len(arr)])\n"
            "        if not asc:\n"
            "            order = order[::-1]\n"
            "        return arr.ravel()[order].tolist()\n"
            "    order = np.argsort(by[: arr.shape[0]])\n"
            "    if not asc:\n"
            "        order = order[::-1]\n"
            "    return arr[order].tolist()"
        )
    if helpers:
        body = "\n".join(helpers) + "\nresult = " + body

    return TranslationResult(ok=True, code=body, data_ranges=list(state.ranges))

