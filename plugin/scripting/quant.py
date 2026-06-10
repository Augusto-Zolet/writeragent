# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Trusted venv quantitative finance helpers.

Includes execution templates, runner, and dispatch logic.
"""

from __future__ import annotations

import importlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from plugin.calc.analysis_runner import calc_tool_context
from plugin.calc.venv_python import _resolve_python_data
from plugin.doc.document_helpers import is_calc, is_writer
from plugin.scripting.analysis import CoerceResult, coerce_to_dataframe
from plugin.scripting.client import run_quant as client_run_quant
from plugin.framework.errors import ToolExecutionError

log = logging.getLogger(__name__)

# --- Constants & Common ---

HELPER_NAMES = (
    "fetch_historical_data",
    "technical_analysis",
    "portfolio_tearsheet",
    "efficient_frontier",
)

QUANT_VENV_PIP_INSTALL = "pip install yfinance pandas-ta quantstats pyportfolioopt"

QUANT_HEADER_PREFIX = "# writeragent:quant"
_QUANT_HEADER_RE = re.compile(
    r"^\s*#\s*writeragent:quant\s+helper=(\w+)\s+params=(\{.*\})\s*$",
    re.MULTILINE,
)

_DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    "fetch_historical_data": {"tickers": ["AAPL", "MSFT"], "start_date": "2023-01-01", "end_date": "2024-01-01", "interval": "1d"},
    "technical_analysis": {"indicators": ["macd", "rsi", "bbands"]},
    "portfolio_tearsheet": {},
    "efficient_frontier": {},
}

_HELPER_DESCRIPTIONS: dict[str, str] = {
    "fetch_historical_data": "Fetch historical prices via yfinance",
    "technical_analysis": "Calculate MACD, RSI, and Bollinger Bands",
    "portfolio_tearsheet": "Generate portfolio performance metrics via quantstats",
    "efficient_frontier": "Optimize portfolio weights via PyPortfolioOpt",
}


# --- Templates ---

@dataclass
class QuantScriptHeader:
    helper: str
    params: dict[str, Any]


def parse_quant_script_header(code: str) -> QuantScriptHeader | None:
    match = _QUANT_HEADER_RE.search(code)
    if not match:
        return None
    try:
        params = json.loads(match.group(2))
        return QuantScriptHeader(helper=match.group(1), params=params)
    except Exception:
        return None


def get_quant_template(helper: str) -> str | None:
    if helper not in HELPER_NAMES:
        return None
    params = _DEFAULT_PARAMS.get(helper, {})
    params_str = json.dumps(params)
    
    desc = _HELPER_DESCRIPTIONS.get(helper, helper.replace("_", " ").title())
    
    lines = [
        f"{QUANT_HEADER_PREFIX} helper={helper} params={params_str}",
        "#",
        f"# {desc}",
        "# This script delegates to the trusted quant venv module.",
        "# Edit the JSON params above if needed. No other code runs.",
    ]
    
    return "\n".join(lines) + "\n"


# --- Runner ---

def supports_quant_manual(doc: Any) -> bool:
    """True when Run Python Script should expose Quant Helpers for *doc*."""
    if doc is None:
        return False
    try:
        return is_writer(doc) or is_calc(doc)
    except Exception:
        return False


def run_trusted_quant(
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
    """Fetch Calc data and run a trusted quant helper in the user venv."""
    name = str(helper or "").strip()
    if not name:
        raise ToolExecutionError("helper is required", code="QUANT_ERROR")
    if name not in HELPER_NAMES:
        raise ToolExecutionError(f"Unknown helper {name!r}", code="QUANT_ERROR")

    if not is_calc(doc) and not is_writer(doc):
        raise ToolExecutionError("Quant helpers require a Writer or Calc document.", code="QUANT_ERROR")

    dr = str(data_range).strip() if data_range else None
    
    py_data = None
    if dr or data is not None:
        tool_ctx = calc_tool_context(uno_ctx, doc)
        py_data, err = _resolve_python_data(tool_ctx, data_range=dr, data=data)
        if err:
            raise ToolExecutionError(err, code="QUANT_ERROR")
            
    # Some helpers like fetch_historical_data do not need py_data
    if name != "fetch_historical_data" and py_data is None:
        raise ToolExecutionError("Provide data_range or data for this quant helper", code="QUANT_ERROR")

    spec_params = params or {}

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

    return client_run_quant(uno_ctx, name, spec_params, py_data, context=context or None)


# --- Core Helper Implementations (Venv Execution Path) ---

def _error_result(code: str, message: str, *, helper: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "error", "code": code, "message": message}
    if helper:
        out["helper"] = helper
    return out


def _missing_package_error(helper: str, package: str) -> dict[str, Any]:
    return _error_result(
        "MISSING_PACKAGE",
        f"{package} is required for {helper}. Install: {QUANT_VENV_PIP_INSTALL}",
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


def fetch_historical_data(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        return _missing_package_error("fetch_historical_data", "yfinance")
    
    tickers = params.get("tickers", [])
    if isinstance(tickers, str):
        tickers = [tickers]
    start_date = params.get("start_date")
    end_date = params.get("end_date")
    interval = params.get("interval", "1d")
    
    if not tickers:
        return _error_result("INVALID_PARAMS", "tickers parameter is required.")
        
    try:
        data = yf.download(tickers, start=start_date, end=end_date, interval=interval)
        data = data.reset_index()
        # Convert datetime to string for JSON serialization
        if 'Date' in data.columns:
            data['Date'] = data['Date'].astype(str)
        if 'Datetime' in data.columns:
            data['Datetime'] = data['Datetime'].astype(str)
            
        columns = list(data.columns)
        records = data.values.tolist()
        
        return {
            "status": "success",
            "helper": "fetch_historical_data",
            "table": {
                "columns": columns,
                "rows": records
            }
        }
    except Exception as e:
        log.exception("Error in fetch_historical_data")
        return _error_result("EXECUTION_ERROR", str(e), helper="fetch_historical_data")


def technical_analysis(params: dict[str, Any], data: Any, context: dict[str, Any]) -> dict[str, Any]:
    try:
        importlib.import_module("pandas_ta")
    except ImportError:
        return _missing_package_error("technical_analysis", "pandas-ta")
        
    res = _resolve_df(data)
    df = res.df
    indicators = params.get("indicators", ["macd", "rsi", "bbands"])
    
    try:
        # Assuming df has typical columns like Close, High, Low
        close_col = next((c for c in df.columns if c.lower() == 'close'), None)
        if close_col:
            for ind in indicators:
                if ind.lower() == 'macd':
                    df.ta.macd(close=close_col, append=True)
                elif ind.lower() == 'rsi':
                    df.ta.rsi(close=close_col, append=True)
                elif ind.lower() == 'bbands':
                    df.ta.bbands(close=close_col, append=True)
        else:
            return _error_result("MISSING_COLUMN", "Could not find 'Close' column for technical analysis.")
            
        # Convert datetime again if needed
        for col in df.select_dtypes(include=['datetime64']).columns:
            df[col] = df[col].astype(str)
            
        return {
            "status": "success",
            "helper": "technical_analysis",
            "table": {
                "columns": list(df.columns),
                "rows": df.values.tolist()
            }
        }
    except Exception as e:
        log.exception("Error in technical_analysis")
        return _error_result("EXECUTION_ERROR", str(e), helper="technical_analysis")


def portfolio_tearsheet(params: dict[str, Any], data: Any, context: dict[str, Any]) -> dict[str, Any]:
    try:
        import quantstats as qs  # type: ignore
    except ImportError:
        return _missing_package_error("portfolio_tearsheet", "quantstats")
        
    res = _resolve_df(data)
    df = res.df
    
    try:
        if df.shape[1] > 1:
            prices = df.iloc[:, 1]
            returns = prices.pct_change().dropna()
        else:
            returns = df.iloc[:, 0].dropna()
            
        metrics = qs.reports.metrics(returns, display=False)
        metrics_dict = metrics.to_dict()
        
        return {
            "status": "success",
            "helper": "portfolio_tearsheet",
            "metrics": metrics_dict
        }
    except Exception as e:
        log.exception("Error in portfolio_tearsheet")
        return _error_result("EXECUTION_ERROR", str(e), helper="portfolio_tearsheet")


def efficient_frontier(params: dict[str, Any], data: Any, context: dict[str, Any]) -> dict[str, Any]:
    try:
        from pypfopt.expected_returns import mean_historical_return  # type: ignore
        from pypfopt.risk_models import CovarianceShrinkage  # type: ignore
        from pypfopt.efficient_frontier import EfficientFrontier  # type: ignore
    except ImportError:
        return _missing_package_error("efficient_frontier", "PyPortfolioOpt")
        
    res = _resolve_df(data)
    df = res.df
    
    try:
        if 'Date' in df.columns or 'date' in df.columns:
            date_col = 'Date' if 'Date' in df.columns else 'date'
            df = df.set_index(date_col)
            
        import pandas as pd
        df = df.apply(pd.to_numeric, errors='coerce').dropna()
        
        mu = mean_historical_return(df)
        S = CovarianceShrinkage(df).ledoit_wolf()
        
        ef = EfficientFrontier(mu, S)
        ef.max_sharpe()
        cleaned_weights = ef.clean_weights()
        
        return {
            "status": "success",
            "helper": "efficient_frontier",
            "weights": cleaned_weights
        }
    except Exception as e:
        log.exception("Error in efficient_frontier")
        return _error_result("EXECUTION_ERROR", str(e), helper="efficient_frontier")


def run_quant(
    helper: str,
    params: dict[str, Any],
    data: Any = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = context or {}
    
    if helper not in HELPER_NAMES:
        return _error_result("UNKNOWN_HELPER", f"Unknown quant helper '{helper}'.", helper=helper)
        
    if helper == "fetch_historical_data":
        return fetch_historical_data(params, context)
    elif helper == "technical_analysis":
        return technical_analysis(params, data, context)
    elif helper == "portfolio_tearsheet":
        return portfolio_tearsheet(params, data, context)
    elif helper == "efficient_frontier":
        return efficient_frontier(params, data, context)
        
    return _error_result("UNIMPLEMENTED", f"Helper {helper} not fully implemented.", helper=helper)
