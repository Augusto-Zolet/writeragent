# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for pretty showcase demo spreadsheet generator (scripts/generate_pretty_demo_spreadsheet.py)."""

from __future__ import annotations

import importlib.util
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest
import scipy.stats as st

REPO_ROOT = Path(__file__).resolve().parents[2]
_GEN_PATH = REPO_ROOT / "scripts" / "generate_pretty_demo_spreadsheet.py"


@pytest.fixture(scope="module")
def generator_mod():
    spec = importlib.util.spec_from_file_location("generate_pretty_demo_spreadsheet", _GEN_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_showcase_kpi_math(generator_mod):
    """Verify all KPI calculations on generator datasets match expected QA / showcase values."""
    sales = generator_mod.get_sales_dataset()
    mkt = generator_mod.get_marketing_dataset()
    ts = generator_mod.get_timeseries_dataset()
    port = generator_mod.get_portfolio_dataset()
    eng = generator_mod.get_engineering_dataset()

    # Overview KPIs
    tot_rev = sum(r[7] for r in sales[1:])
    assert tot_rev == 119142.0
    assert f"${tot_rev:,.2f}" == "$119,142.00"

    weighted_margin = (
        sum(r[7] * (0.28 if r[3] == "Electronics" else 0.30 if r[3] == "Furniture" else 0.22) for r in sales[1:])
        / tot_rev
    )
    assert f"{weighted_margin:.1%}" == "28.4%"

    anomalies = sum(1 for r in sales[1:] if r[7] > 8000)
    assert anomalies == 5
    assert f"{anomalies} Detected" == "5 Detected"

    fc_target = ts[-1][4] * 1.15
    assert f"${fc_target:,.2f}" == "$349.02"

    # Sales Analytics
    ent_sales = sum(r[7] for r in sales[1:] if r[4] == "Enterprise")
    assert ent_sales == 81497.5
    top_sku = max(sales[1:], key=lambda r: r[7])[8]
    assert top_sku == "FURN-3388"
    avg_units = round(sum(r[5] for r in sales[1:]) / len(sales[1:]), 1)
    assert avg_units == 25.1

    # Statistics & ML
    pearson_r = round(st.pearsonr([r[2] for r in mkt[1:]], [r[6] for r in mkt[1:]])[0], 4)
    assert pearson_r == 0.7978
    slope = round(st.linregress([r[2] for r in mkt[1:]], [r[6] for r in mkt[1:]]).slope, 2)
    assert slope == 5.07
    top_roi = max(
        ["Search Ads", "Social Media", "Email Marketing"],
        key=lambda ch: sum(r[6] for r in mkt[1:] if r[1] == ch) / max(1, sum(r[2] for r in mkt[1:] if r[1] == ch)),
    )
    assert top_roi == "Email Marketing"
    total_roas = round(sum(r[6] for r in mkt[1:]) / sum(r[2] for r in mkt[1:]), 2)
    assert total_roas == 6.02

    # Forecasting
    cagr = f"{((ts[-1][4] / ts[1][4]) ** (1 / 3) - 1):.1%}"
    assert cagr == "46.3%"
    next_trend = round(ts[-1][2] + 4.5, 1)
    assert next_trend == 282.0
    peak_sales = max(r[4] for r in ts[1:])
    assert peak_sales == 303.5
    spike_month = ts[1:][max(range(len(ts[1:])), key=lambda i: ts[1:][i][4] - ts[1:][i][2] - ts[1:][i][3])][1]
    assert spike_month == "2023-08-01"

    # Optimization
    highest_ret = ["Equities_US", "Tech_Growth", "Treasury_Bonds", "Real_Estate"][
        max(range(4), key=lambda c: sum(r[c + 1] for r in port[1:]))
    ]
    assert highest_ret == "Tech_Growth"
    lowest_vol = ["Equities_US", "Tech_Growth", "Treasury_Bonds", "Real_Estate"][
        min(range(4), key=lambda c: float(np.var([r[c + 1] for r in port[1:]])))
    ]
    assert lowest_vol == "Treasury_Bonds"

    # Engineering Math
    assert round(eng[1][1] * 1.34102, 2) == 201.15
    assert round(eng[2][1] * 0.0689476, 2) == 151.68
    assert round(eng[3][1] * 9 / 5 + 32, 1) == 185.0
    assert round(eng[4][1] / 3.6, 2) == 33.33
    assert round(3 * (2**2) * math.sin(2) + (2**3) * math.cos(2), 4) == 7.5824
    assert round(math.erf(1) * (math.sqrt(math.pi) / 2), 4) == 0.7468


def test_generator_writes_ods_and_xlsx(generator_mod, tmp_path: Path):
    """Test generating both ODS and XLSX formats into a temporary path."""
    ods_path = tmp_path / "python_showcase_demo.ods"
    xlsx_path = tmp_path / "python_showcase_demo.xlsx"

    generator_mod.build_ods_showcase(ods_path)
    assert ods_path.is_file()

    generator_mod.build_xlsx_showcase(xlsx_path)
    assert xlsx_path.is_file()

    # Verify ODS contains sheets and addin functions
    with zipfile.ZipFile(ods_path) as zf:
        content_xml = zf.read("content.xml").decode("utf-8")
        assert "Overview" in content_xml
        assert "Sales_Analytics" in content_xml
        assert "Statistics_ML" in content_xml
        assert "Forecasting" in content_xml
        assert "Optimization" in content_xml
        assert "Engineering_Math" in content_xml
        assert "Viz_Gallery" in content_xml
        assert "ORG.EXTENSION.WRITERAGENT.PYTHONFUNCTION.PY" in content_xml
        assert "$119,142.00" in content_xml
        assert "28.4%" in content_xml
        assert "5 Detected" in content_xml
        assert "$349.02" in content_xml

    # Verify XLSX contains sheet XMLs and fully-qualified addin functions
    with zipfile.ZipFile(xlsx_path) as zf:
        sheet_files = [name for name in zf.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")]
        assert len(sheet_files) == 7
        for sf in sheet_files:
            xml_text = zf.read(sf).decode("utf-8")
            if "ORG.EXTENSION.WRITERAGENT.PYTHONFUNCTION.PY" in xml_text:
                assert "ORG.EXTENSION.WRITERAGENT.PYTHONFUNCTION.PY(" in xml_text
