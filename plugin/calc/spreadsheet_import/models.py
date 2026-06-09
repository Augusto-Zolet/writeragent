# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Data models for Calc spreadsheet → Python import (ingest + preserve phases)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

CellType = Literal[
    "empty",
    "constant",
    "formula",
    "py_formula",
    "prompt",
    "array_formula",
    "error",
]

FORMULA_LIKE_TYPES: frozenset[CellType] = frozenset(
    {"formula", "py_formula", "array_formula", "error"},
)


@dataclass
class CellRecord:
    """One cell in an ingested sheet snapshot."""

    address: str
    type: CellType
    value: Any
    formula: str | None
    number_format: int | None  # UNO NumberFormat key; None in bulk ingest path
    precedents: list[str] = field(default_factory=list)
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SheetModel:
    """Ingested sheet: classified cells plus dependency ordering."""

    sheet_name: str
    used_range: str
    cells: dict[str, CellRecord]
    formula_order: list[str] = field(default_factory=list)
    circular_groups: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheet_name": self.sheet_name,
            "used_range": self.used_range,
            "cells": {addr: cell.to_dict() for addr, cell in self.cells.items()},
            "formula_order": list(self.formula_order),
            "circular_groups": [list(group) for group in self.circular_groups],
        }


@dataclass
class PyCellExtract:
    """Parsed and normalized ``=PY()`` / ``=PYTHON()`` cell."""

    address: str
    original_formula: str
    normalized_formula: str
    code: str
    data_args: list[str]
    changed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OutputCell:
    """One cell in a preserve-phase output grid."""

    address: str
    value: Any
    formula: str | None
    number_format: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OutputSheetModel:
    """Output grid after preserve pass (constants + normalized PY + pass-through formulas)."""

    sheet_name: str
    used_range: str
    cells: dict[str, OutputCell]
    py_extracts: list[PyCellExtract] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheet_name": self.sheet_name,
            "used_range": self.used_range,
            "cells": {addr: cell.to_dict() for addr, cell in self.cells.items()},
            "py_extracts": [item.to_dict() for item in self.py_extracts],
        }
