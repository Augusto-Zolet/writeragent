# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Range inspection, broadcasting, and mapping for trusted venv helpers.

Provides polymorphic execution over scalars, Calc ranges, 1D/2D lists, and
NumPy/pandas sequences while preserving orientation ($N \\times 1$ column in $\\to$
$N \\times 1$ column out) and handling blanks and LibreOffice error tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from plugin.scripting.calc_range import CalcRange, ensure_rectangular_2d
from plugin.scripting.venv.coerce import is_missing_value


@dataclass(frozen=True)
class InspectedInput:
    """Structural metadata of an inspected argument for rewrapping."""

    flat_items: list[Any]
    is_scalar: bool
    is_python_1d: bool
    nrows: int
    ncols: int

    @property
    def length(self) -> int:
        return len(self.flat_items)


def _to_plain_sequence(val: Any) -> Any:
    """Unwrap NumPy ndarray, pandas Series/DataFrame to nested lists."""
    if hasattr(val, "tolist") and callable(val.tolist):
        try:
            return val.tolist()
        except Exception:
            pass
    if hasattr(val, "to_list") and callable(val.to_list):
        try:
            return val.to_list()
        except Exception:
            pass
    return val


def inspect_input(val: Any) -> InspectedInput:
    """Inspect input shape and flatten to 1D items while tracking orientation.

    Rules:
    - Scalar (number, str, bool, None) $\\to$ scalar (nrows=1, ncols=1).
    - 1×1 CalcRange or 2D list ``[[v]]`` $\\to$ scalar (nrows=1, ncols=1).
    - 1D Python list/tuple $\\to$ python_1d (nrows=1, ncols=len).
    - $N \\times 1$ CalcRange / 2D list ($N \\ge 2$) $\\to$ column (nrows=N, ncols=1).
    - $1 \\times N$ CalcRange / 2D list ($N \\ge 2$) $\\to$ row (nrows=1, ncols=N).
    - $M \\times N$ 2D grid ($M, N \\ge 2$) $\\to$ grid (nrows=M, ncols=N).
    """
    val = _to_plain_sequence(val)

    if val is None or isinstance(val, (str, bytes, int, float, bool)):
        return InspectedInput(flat_items=[val], is_scalar=True, is_python_1d=False, nrows=1, ncols=1)

    grid: Any
    if isinstance(val, CalcRange):
        grid = val.values
    elif isinstance(val, (list, tuple)):
        grid = val
    else:
        # Unknown non-sequence object
        return InspectedInput(flat_items=[val], is_scalar=True, is_python_1d=False, nrows=1, ncols=1)

    if not grid:
        return InspectedInput(flat_items=[], is_scalar=False, is_python_1d=True, nrows=0, ncols=0)

    # Distinguish 1D list from 2D list
    if not isinstance(grid[0], (list, tuple)):
        # Plain 1D Python sequence: [10, 20] or [10]
        items = list(grid)
        return InspectedInput(flat_items=items, is_scalar=False, is_python_1d=True, nrows=1, ncols=len(items))

    # 2D sequence or CalcRange
    rect_grid = ensure_rectangular_2d(grid)
    nrows = len(rect_grid)
    ncols = len(rect_grid[0]) if rect_grid else 0

    if nrows == 1 and ncols == 1:
        # 1x1 CalcRange / [[v]] is treated as scalar for single-cell formulas
        return InspectedInput(flat_items=[rect_grid[0][0]], is_scalar=True, is_python_1d=False, nrows=1, ncols=1)

    flat = [cell for row in rect_grid for cell in row]
    return InspectedInput(flat_items=flat, is_scalar=False, is_python_1d=False, nrows=nrows, ncols=ncols)


def rewrap_output(results: list[Any], inspected: InspectedInput) -> Any:
    """Reconstruct output matching the input shape and orientation.

    - Scalar $\\to$ single value.
    - 1D list $\\to$ 1D list.
    - $N \\times 1$ column $\\to$ ``[[r1], [r2], ...]``.
    - $1 \\times N$ row $\\to$ ``[[r1, r2, ...]]``.
    - $M \\times N$ grid $\\to$ ``[[...], [...]]``.
    """
    if inspected.is_scalar:
        return results[0] if results else None
    if inspected.is_python_1d:
        return list(results)
    if inspected.ncols == 1:
        return [[r] for r in results]
    if inspected.nrows == 1:
        return [list(results)]

    # M x N grid
    nrows = inspected.nrows
    ncols = inspected.ncols
    out: list[list[Any]] = []
    for i in range(nrows):
        out.append(list(results[i * ncols : (i + 1) * ncols]))
    return out


def broadcast_args(
    *args: Any,
    **kwargs: Any,
) -> tuple[InspectedInput, list[list[Any]], dict[str, list[Any]]]:
    """Inspect arguments and broadcast scalars across vector length.

    Returns:
        (primary_inspected, broadcasted_args, broadcasted_kwargs)
    Raises:
        ValueError: If vector lengths mismatch or M×N grid is paired with a vector.
    """
    inspected_args = [inspect_input(a) for a in args]
    inspected_kwargs = {k: inspect_input(v) for k, v in kwargs.items()}

    all_inspected = inspected_args + list(inspected_kwargs.values())

    vector_items = [insp for insp in all_inspected if not insp.is_scalar]

    if not vector_items:
        # All scalar
        primary = inspected_args[0] if inspected_args else (list(inspected_kwargs.values())[0] if inspected_kwargs else inspect_input(None))
        scalar_args = [[insp.flat_items[0]] for insp in inspected_args]
        scalar_kwargs = {k: [insp.flat_items[0]] for k, insp in inspected_kwargs.items()}
        return primary, scalar_args, scalar_kwargs

    # Check for M x N grid + vector conflict (both dimensions > 1)
    has_2d_grid = any(insp.nrows > 1 and insp.ncols > 1 for insp in vector_items)
    if has_2d_grid and len(vector_items) > 1:
        raise ValueError("Cannot pair an M×N grid with a vector parameter; broadcast only with scalars.")

    # Find target length and primary target shape
    target_length = vector_items[0].length
    primary = vector_items[0]

    for insp in vector_items[1:]:
        if insp.length != target_length:
            raise ValueError(f"Vector length mismatch: {insp.length} != {target_length}")

    b_args: list[list[Any]] = []
    for insp in inspected_args:
        if insp.is_scalar:
            scalar_val = insp.flat_items[0] if insp.flat_items else None
            b_args.append([scalar_val] * target_length)
        else:
            b_args.append(list(insp.flat_items))

    b_kwargs: dict[str, list[Any]] = {}
    for k, insp in inspected_kwargs.items():
        if insp.is_scalar:
            scalar_val = insp.flat_items[0] if insp.flat_items else None
            b_kwargs[k] = [scalar_val] * target_length
        else:
            b_kwargs[k] = list(insp.flat_items)

    return primary, b_args, b_kwargs


def map_over_range(
    fn: Callable[..., Any],
    *args: Any,
    handle_blanks: bool = True,
    return_errors: bool = True,
    **kwargs: Any,
) -> Any:
    """Map a scalar function elementwise over scalar/range/vector inputs.

    Args:
        fn: Scalar compute function.
        *args: Positional arguments (may be scalars or ranges).
        handle_blanks: If True, missing cells (None, "", NaN, error tokens)
            produce empty string "" without calling fn.
        return_errors: If True, per-element exceptions return "#VALUE!".
        **kwargs: Keyword arguments (may be scalars or ranges).

    Returns:
        Scalar or list/nested list matching the primary vector shape.
    """
    primary, b_args, b_kwargs = broadcast_args(*args, **kwargs)
    n_items = primary.length

    results: list[Any] = []
    for i in range(n_items):
        row_args = [arg_list[i] for arg_list in b_args]
        row_kwargs = {k: kwarg_list[i] for k, kwarg_list in b_kwargs.items()}

        if handle_blanks:
            # Check if all primary input values for this row are missing
            main_val = row_args[0] if row_args else (next(iter(row_kwargs.values())) if row_kwargs else None)
            if is_missing_value(main_val):
                results.append("")
                continue

        try:
            res = fn(*row_args, **row_kwargs)
            results.append(res)
        except Exception:
            if return_errors:
                results.append("#VALUE!")
            else:
                raise

    return rewrap_output(results, primary)
