# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Built-in Run Python Script templates for trusted optimization helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from plugin.scripting.optimize_common import HELPER_NAMES

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
