# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Trusted venv units compute — runs in user venv worker."""

from __future__ import annotations

import logging
from typing import Any

from plugin.scripting.calc_functions_common import UNITS_HELPER_NAMES as HELPER_NAMES
from plugin.scripting.calc_range import ensure_rectangular_2d
from plugin.scripting.venv.coerce import error_result as _error_result
from plugin.scripting.venv.map_range import inspect_input, map_over_range

log = logging.getLogger(__name__)

_UREG: Any | None = None


def _ok_result(
    helper: str,
    *,
    magnitude: float | None = None,
    units: str = "",
    formatted: str = "",
    text: str = "",
    **extra: Any,
) -> dict[str, Any]:
    display = formatted or text
    out: dict[str, Any] = {
        "status": "ok",
        "helper": helper,
        "formatted": display,
        "text": display,
        "writer_cleanup_hints": [],
        **extra,
    }
    if magnitude is not None:
        out["magnitude"] = magnitude
    if units:
        out["units"] = units
    return out


def _require_pint(helper: str) -> Any | None:
    try:
        import pint
        return pint
    except ImportError:
        return None


def _missing_package(helper: str) -> dict[str, Any]:
    return _error_result(
        "MISSING_PACKAGE",
        f"pint is required for {helper}.",
        helper=helper,
    )


def _get_ureg() -> Any:
    global _UREG
    if _UREG is None:
        pint = _require_pint("units")
        if pint is None:
            raise ValueError("MISSING_PACKAGE")
        _UREG = pint.UnitRegistry()
    return _UREG


def _quantity_payload(qty: Any, *, helper: str, display_unit: str | None = None) -> dict[str, Any]:
    magnitude = float(qty.magnitude)
    units = str(qty.units)
    if display_unit:
        formatted = f"{qty.magnitude:g} {display_unit}"
    else:
        formatted = f"{qty.magnitude:g} {qty.units:~}"
    return _ok_result(helper, magnitude=magnitude, units=units, formatted=formatted)


def _parse_quantity_value(ureg: Any, text: str, *, helper: str) -> Any:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("empty quantity")
    try:
        return ureg.Quantity(raw)
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def _parse_unit_or_quantity(ureg: Any, text: str, *, helper: str, param: str) -> Any:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError(f"empty {param}")
    try:
        return ureg.Quantity(raw) if any(ch.isdigit() for ch in raw) else ureg.Quantity(f"1 {raw}")
    except Exception:
        return _parse_quantity_value(ureg, raw, helper=helper)


def _scalar_convert(val: Any, from_u: Any, to_u: Any) -> float:
    """Convert a single scalar value between units."""
    if val is None or val == "":
        raise ValueError("empty value")
    from_text = str(from_u or "").strip()
    to_text = str(to_u or "").strip()
    if not from_text or not to_text:
        raise ValueError("missing units")
    ureg = _get_ureg()
    num = float(str(val).strip())
    qty = ureg.Quantity(f"{num} {from_text}")
    converted = qty.to(to_text)
    return float(converted.magnitude)


def convert_quantity(
    value: Any,
    from_unit: Any = "",
    to_unit: Any = "",
    *,
    from_unit_kw: Any = "",
    to_unit_kw: Any = "",
    **kwargs: Any,
) -> Any:
    """Convert a numeric value or range between units.

    Direct/``=PY()`` returns numeric magnitude float or 1D/2D list of floats.
    """
    helper = "convert_quantity"
    if _require_pint(helper) is None:
        return _missing_package(helper)

    from_text = (
        from_unit
        if from_unit != ""
        else (
            from_unit_kw
            if from_unit_kw != ""
            else kwargs.get("from", kwargs.get("from_unit", ""))
        )
    )
    to_text = (
        to_unit
        if to_unit != ""
        else (
            to_unit_kw
            if to_unit_kw != ""
            else kwargs.get("to", kwargs.get("to_unit", ""))
        )
    )

    if from_text == "" or to_text == "":
        return _error_result("MISSING_PARAM", "from and to units are required", helper=helper)

    return map_over_range(
        _scalar_convert,
        value,
        from_text,
        to_text,
        handle_blanks=True,
    )


def _scalar_parse(quantity: Any) -> float:
    """Parse a single quantity string into its numeric magnitude."""
    ureg = _get_ureg()
    qty = _parse_quantity_value(ureg, str(quantity or ""), helper="parse_quantity")
    return float(qty.magnitude)


def _is_blank_param(value: Any) -> bool:
    """True for omitted helper args. Ranges/lists must not use ``!= ""`` (numpy truthiness)."""
    return value is None or (isinstance(value, str) and value == "")


def parse_quantity(*, quantity: Any = "", **kwargs: Any) -> Any:
    """Parse a quantity string or range of quantity strings into magnitudes."""
    helper = "parse_quantity"
    if _require_pint(helper) is None:
        return _missing_package(helper)

    raw_quantity = kwargs.get("quantity", "") if _is_blank_param(quantity) else quantity
    if _is_blank_param(raw_quantity):
        return _error_result("MISSING_PARAM", "quantity is required", helper=helper)

    return map_over_range(
        _scalar_parse,
        quantity=raw_quantity,
        handle_blanks=True,
    )


def _scalar_format(magnitude: Any, units: Any, format_spec: Any = "") -> str:
    """Format a single magnitude and unit string."""
    ureg = _get_ureg()
    mag = float(str(magnitude or "0").strip())
    units_text = str(units or "").strip()
    qty = ureg.Quantity(f"{mag} {units_text}")
    spec = str(format_spec or "").strip()
    return f"{qty.magnitude:{spec}} {qty.units}" if spec else f"{qty.magnitude:g} {qty.units}"


def format_quantity(
    *,
    magnitude: Any = "",
    units: Any = "",
    format_spec: Any = "",
    **kwargs: Any,
) -> Any:
    """Format magnitude and units for a scalar or range."""
    helper = "format_quantity"
    if _require_pint(helper) is None:
        return _missing_package(helper)

    raw_mag = kwargs.get("magnitude", "") if _is_blank_param(magnitude) else magnitude
    raw_units = kwargs.get("units", "") if _is_blank_param(units) else units
    raw_spec = kwargs.get("format_spec", "") if _is_blank_param(format_spec) else format_spec

    if _is_blank_param(raw_units):
        return _error_result("MISSING_PARAM", "units is required", helper=helper)

    return map_over_range(
        _scalar_format,
        magnitude=raw_mag,
        units=raw_units,
        format_spec=raw_spec,
        handle_blanks=True,
    )


def check_dimensionality(
    *,
    quantity_a: str = "",
    quantity_b: str = "",
    unit_a: str = "",
    unit_b: str = "",
) -> dict[str, Any]:
    helper = "check_dimensionality"
    if _require_pint(helper) is None:
        return _missing_package(helper)
    left = str(quantity_a or unit_a or "").strip()
    right = str(quantity_b or unit_b or "").strip()
    if not left or not right:
        return _error_result("MISSING_PARAM", "quantity_a/quantity_b or unit_a/unit_b are required", helper=helper)
    try:
        ureg = _get_ureg()
        qty_a = _parse_unit_or_quantity(ureg, left, helper=helper, param="quantity_a")
        qty_b = _parse_unit_or_quantity(ureg, right, helper=helper, param="quantity_b")
        compatible = qty_a.dimensionality == qty_b.dimensionality
        dim_a = str(qty_a.dimensionality)
        dim_b = str(qty_b.dimensionality)
        text = "compatible" if compatible else "incompatible"
        return _ok_result(
            helper,
            formatted=text,
            compatible=compatible,
            dimensionality_a=dim_a,
            dimensionality_b=dim_b,
        )
    except ValueError as exc:
        if str(exc) == "MISSING_PACKAGE":
            return _missing_package(helper)
        return _error_result("PARSE_ERROR", str(exc), helper=helper)
    except Exception as exc:
        return _error_result("UNITS_ERROR", str(exc), helper=helper)


def _dispatch_helper(name: str, params: dict[str, Any]) -> dict[str, Any]:
    if name == "convert_quantity":
        raw_val = params.get("value")
        raw_from = params.get("from") or params.get("from_unit") or ""
        raw_to = params.get("to") or params.get("to_unit") or ""

        # Check if all inputs are scalar
        insp_val = inspect_input(raw_val)
        insp_from = inspect_input(raw_from)
        insp_to = inspect_input(raw_to)

        if insp_val.is_scalar and insp_from.is_scalar and insp_to.is_scalar:
            # Traditional scalar RPC return shape
            if _require_pint("convert_quantity") is None:
                return _missing_package("convert_quantity")
            from_text = str(raw_from or "").strip()
            to_text = str(raw_to or "").strip()
            if not from_text or not to_text:
                return _error_result("MISSING_PARAM", "from and to units are required", helper=name)
            try:
                ureg = _get_ureg()
                val_str = str(insp_val.flat_items[0] if insp_val.flat_items else "0")
                qty = ureg.Quantity(f"{float(val_str.strip() or '0')} {from_text}")
                converted = qty.to(to_text)
                return _quantity_payload(converted, helper=name, display_unit=to_text)
            except ValueError as exc:
                if str(exc) == "MISSING_PACKAGE":
                    return _missing_package(name)
                return _error_result("PARSE_ERROR", str(exc), helper=name)
            except Exception as exc:
                return _error_result("UNITS_ERROR", str(exc), helper=name)

        # Vector RPC return shape
        try:
            res = convert_quantity(raw_val, from_unit=raw_from, to_unit=raw_to)
            if isinstance(res, dict) and res.get("status") == "error":
                return res
            # Wrap into one compact vector payload
            grid = ensure_rectangular_2d(res)
            flat_magnitudes = [cell for row in grid for cell in row]
            to_text = str(raw_to or "")
            formatted_list = [
                f"{c:g} {to_text}" if isinstance(c, (int, float)) else str(c)
                for c in flat_magnitudes
            ]
            return {
                "status": "ok",
                "helper": name,
                "values": grid,
                "magnitudes": flat_magnitudes,
                "formatted": formatted_list,
                "units": to_text,
                "text": f"{len(flat_magnitudes)} quantities converted",
                "writer_cleanup_hints": [],
            }
        except ValueError as exc:
            return _error_result("UNITS_ERROR", str(exc), helper=name)
        except Exception as exc:
            return _error_result("UNITS_ERROR", str(exc), helper=name)

    if name == "parse_quantity":
        raw_qty = params.get("quantity")
        insp = inspect_input(raw_qty)
        if insp.is_scalar:
            if _require_pint("parse_quantity") is None:
                return _missing_package("parse_quantity")
            try:
                ureg = _get_ureg()
                qty_str = str(insp.flat_items[0] if insp.flat_items else "")
                qty = _parse_quantity_value(ureg, qty_str, helper=name)
                return _quantity_payload(qty, helper=name)
            except ValueError as exc:
                if str(exc) == "MISSING_PACKAGE":
                    return _missing_package(name)
                return _error_result("PARSE_ERROR", str(exc), helper=name)
            except Exception as exc:
                return _error_result("UNITS_ERROR", str(exc), helper=name)

        # Vector parse_quantity
        try:
            res = parse_quantity(quantity=raw_qty)
            if isinstance(res, dict) and res.get("status") == "error":
                return res
            grid = ensure_rectangular_2d(res)
            flat = [cell for row in grid for cell in row]
            return {
                "status": "ok",
                "helper": name,
                "values": grid,
                "magnitudes": flat,
                "text": f"{len(flat)} quantities parsed",
                "writer_cleanup_hints": [],
            }
        except Exception as exc:
            return _error_result("UNITS_ERROR", str(exc), helper=name)

    if name == "format_quantity":
        raw_mag = params.get("magnitude")
        raw_units = params.get("units")
        raw_spec = str(params.get("format_spec") or "")
        insp_mag = inspect_input(raw_mag)
        insp_u = inspect_input(raw_units)
        if insp_mag.is_scalar and insp_u.is_scalar:
            if _require_pint("format_quantity") is None:
                return _missing_package("format_quantity")
            units_text = str(insp_u.flat_items[0] if insp_u.flat_items else "").strip()
            if not units_text:
                return _error_result("MISSING_PARAM", "units is required", helper=name)
            try:
                ureg = _get_ureg()
                mag_str = str(insp_mag.flat_items[0] if insp_mag.flat_items else "0").strip()
                mag = float(mag_str or "0")
                qty = ureg.Quantity(f"{mag} {units_text}")
                spec = raw_spec.strip()
                formatted = f"{qty.magnitude:{spec}} {qty.units}" if spec else f"{qty.magnitude:g} {qty.units}"
                return _ok_result(name, magnitude=mag, units=units_text, formatted=formatted)
            except ValueError as exc:
                if str(exc) == "MISSING_PACKAGE":
                    return _missing_package(name)
                return _error_result("PARSE_ERROR", str(exc), helper=name)
            except Exception as exc:
                return _error_result("UNITS_ERROR", str(exc), helper=name)

        # Vector format_quantity
        try:
            res = format_quantity(magnitude=raw_mag, units=raw_units, format_spec=raw_spec)
            if isinstance(res, dict) and res.get("status") == "error":
                return res
            grid = ensure_rectangular_2d(res)
            flat = [cell for row in grid for cell in row]
            return {
                "status": "ok",
                "helper": name,
                "values": grid,
                "formatted": flat,
                "text": f"{len(flat)} quantities formatted",
                "writer_cleanup_hints": [],
            }
        except Exception as exc:
            return _error_result("UNITS_ERROR", str(exc), helper=name)

    if name == "check_dimensionality":
        return check_dimensionality(
            quantity_a=str(params.get("quantity_a") or ""),
            quantity_b=str(params.get("quantity_b") or ""),
            unit_a=str(params.get("unit_a") or ""),
            unit_b=str(params.get("unit_b") or ""),
        )
    return _error_result("UNKNOWN_HELPER", f"Unknown helper {name!r}", helper=name)


def run_units(
    spec: dict[str, Any] | str,
    data: Any = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Spec-driven dispatcher for trusted units helpers."""
    del data
    if isinstance(spec, str):
        spec_dict: dict[str, Any] = {"helper": spec}
    elif isinstance(spec, dict):
        spec_dict = spec
    else:
        return _error_result("INVALID_SPEC", "spec must be a dict or helper name")

    helper = str(spec_dict.get("helper") or "").strip()
    if not helper:
        return _error_result("MISSING_PARAM", "helper is required")
    if helper not in HELPER_NAMES:
        return _error_result("UNKNOWN_HELPER", f"Unknown helper {helper!r}", helper=helper)

    params = spec_dict.get("params")
    if params is None:
        params = {k: v for k, v in spec_dict.items() if k != "helper"}
    if not isinstance(params, dict):
        params = {}

    # Inlined from host split_helper_params: strip the egress-only "output_style" key
    clean = dict(params)
    raw_style = clean.pop("output_style", None)
    output_style = str(raw_style).strip() if raw_style is not None else None
    if output_style == "":
        output_style = None
    clean_params, _output_style = clean, output_style
    result = _dispatch_helper(helper, clean_params)
    if result.get("status") == "ok" and context:
        for key in ("task_hint",):
            if key in context:
                result[key] = context[key]
    return result
