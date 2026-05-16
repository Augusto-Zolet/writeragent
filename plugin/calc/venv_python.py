# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""LLM tool: run Python in the user-configured venv (see plugin/scripting/run_venv_code.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from plugin.calc.base import ToolCalcPythonBase
from plugin.scripting.run_venv_code import run_code_in_user_venv

if TYPE_CHECKING:
    from plugin.framework.tool import ToolContext

_ALL_VENV_DOCS = [
    "com.sun.star.sheet.SpreadsheetDocument",
    "com.sun.star.text.TextDocument",
    "com.sun.star.drawing.DrawingDocument",
    "com.sun.star.presentation.PresentationDocument",
]


class RunVenvPythonScript(ToolCalcPythonBase):
    """Registered once; visible in Writer/Calc/Draw specialized ``domain=python`` via ``specialized_cross_cutting``."""

    name = "run_venv_python_script"
    specialized_cross_cutting: ClassVar[bool] = True
    description = (
        "Run Python code in the external venv configured under Settings → Python (scripting.python_venv_path). "
        "Uses a subprocess (not LibreOffice's embedded Python). Assign your output to variable `result` "
        "(JSON-serializable); it is returned in the tool response. Optional timeout seconds (default 120, max 600)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python source to execute in the venv. Set `result` to a JSON-serializable value.",
            },
            "timeout_sec": {
                "type": "integer",
                "description": "Wall-clock timeout in seconds (1–600). Default 120.",
            },
        },
        "required": ["code"],
    }
    uno_services = list(_ALL_VENV_DOCS)
    long_running = True

    def is_async(self) -> bool:
        return True

    def execute(self, ctx: ToolContext, **kwargs: Any) -> dict[str, Any]:
        code = str(kwargs.get("code", ""))
        timeout_sec = kwargs.get("timeout_sec", 120)
        try:
            t = int(float(timeout_sec))
        except (TypeError, ValueError):
            t = 120
        return run_code_in_user_venv(ctx.ctx, code, timeout_sec=t)
