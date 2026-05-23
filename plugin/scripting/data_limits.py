# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Calc/Python data cell cap from scripting module.yaml (single source of truth)."""

from __future__ import annotations

from typing import Any

_CONFIG_KEY = "scripting.python_max_data_cells"


def _schema_field() -> dict[str, Any]:
    from plugin._manifest import MODULES

    for m in MODULES:
        if not isinstance(m, dict):
            continue
        if m.get("name") != "scripting":
            continue
        config = m.get("config", {})
        if isinstance(config, dict):
            field = config.get("python_max_data_cells")
            if isinstance(field, dict):
                return field
    raise RuntimeError(
        "python_max_data_cells missing from manifest; run make manifest "
        "(plugin/scripting/module.yaml must define the field)."
    )


def _schema_int(name: str) -> int:
    field = _schema_field()
    val = field.get(name)
    if not isinstance(val, int):
        raise RuntimeError(f"python_max_data_cells.{name} must be int in module.yaml/manifest")
    return val


def python_max_data_cells_default() -> int:
    return _schema_int("default")


def python_max_data_cells_min() -> int:
    return _schema_int("min")


def python_max_data_cells_max() -> int:
    return _schema_int("max")


def _clamp_max_data_cells(value: int) -> int:
    lo = python_max_data_cells_min()
    hi = python_max_data_cells_max()
    return max(lo, min(hi, value))


def configured_python_max_data_cells(ctx: Any) -> int:
    """Read Settings value for scripting.python_max_data_cells and clamp to schema bounds."""
    from plugin.framework.config import get_config_int

    return _clamp_max_data_cells(get_config_int(ctx, _CONFIG_KEY))
