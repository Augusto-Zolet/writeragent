# LibrePy-surface live QA plan (real user scenarios)

**Audience:** Cloud / checkout agents (and humans) exercising the **LibrePy feature set** in a real LibreOffice Calc/Writer/Draw session.

**Which OXT:** **Does not matter.** `=PY()`, the warm venv, Run Python Script, domain helpers, Monaco, Vision, and TeX are the **same code** in WriterAgent.oxt and LibrePy.oxt. Install whichever is already on the machine (`make deploy` or `make deploy-core`). Do **not** spend time swapping extensions or asserting which id is registered.

**What to test:** Only surfaces LibrePy ships — formulas, Python menus, Settings → Python, sidebar diagnostics, trusted domain helpers via **Run Python Script** (and `=PY()`). That is the product slice, not “must boot LibrePy.oxt”.

**Goal:** Prove that slice works the way a data-science spreadsheet user would use it — not formula-lexer trivia. Start with `=PY("1 + 1")` and walk the shipped layers.

**Out of scope for this pass (do later):**

- Syntax/runtime junk (`=PY("1 + E")`, empty code, nested quotes).
- WriterAgent-only features even if the WriterAgent OXT is installed: chat, `=PROMPT()`, `analyze_data` / `run_venv_python_script` / MCP, embeddings, DuckDB, Jupyter import, spreadsheet → Python converter.
- `calc.*` parity helpers (not in the LibrePy *feature* set; ignore if they happen to work under WriterAgent).
- Collabora Online / jail-safe C++ path ([numpy-jailsafe.md](numpy-jailsafe.md)).
- Geospatial, Audio analysis, SageMath, Prophet.

Related docs: [extension split](libreoffice-core-python-extension-split.md), [user guide](enabling_numpy_in_libreoffice.md), [data shapes](calc-py-data-shapes.md), [domains](numpy-domains.md), [showcase](python-in-calc-showcase.md).

---

## How to farm this to agents

Each **work packet** below is independent after **P0** (venv + smoke). Assign one packet per agent. Agents must:

1. Run on a machine with **LibreOffice + either OXT + configured venv** (not pytest-only).
2. Fill the **result table** at the bottom of their packet: `id | pass/fail | actual | notes`.
3. Prefer **recalc in Calc** (`Ctrl+Shift+F9`) over inventing new formulas when a fixture already exists.
4. Not expand into edge cases unless a happy path is already broken.
5. Leave chat / `=PROMPT()` / `chat_prompt` cells in fixtures **untested** — those are WriterAgent-only even when the full OXT is installed.

**Pass rule:** Cell/script result matches the expected column (or visual: plot is on the sheet, not `#VALUE!`). Numeric tolerance: relative 1e-4 unless a formatted string is specified.

**Fail rule:** `#VALUE!`, `#NUM!` from a successful computation we expected to be a number, empty when a value is expected, LO crash, hang past timeout, or missing menu.

Slow open of `numpy_domains_demo.ods`: set `PYTHON_TIMINGS_LOG = True` in `plugin/calc/python/function.py`, deploy, then grep `py_timing` in `writeragent_debug.log` (DEBUG). Use `ipc_ms` / last line `pass_*`, not `asctime` deltas — [enabling_numpy.md §5](enabling_numpy_in_libreoffice.md).

---

## P0 — Environment (every agent, once)

Do this before any packet.

| Step | Action | Pass |
|------|--------|------|
| P0.1 | LibreOffice with **WriterAgent or LibrePy** already installed. Restart if you just deployed. | `=PY` is in the function wizard; Python menus exist. Do not uninstall/swap OXTs |
| P0.2 | **Settings → Python**: set `scripting.python_venv_path` to a real venv | Path accepted |
| P0.3 | **Test** button | Scientific + Data Analysis groups **Present** for analysis packets; Viz / Computer Algebra / Units as needed |
| P0.4 | Session mode **Isolated** unless a packet says Shared | Default |
| P0.5 | Auto-spill **on** (default) | — |

Suggested venv (from the user guide):

```bash
uv pip install numpy pandas scipy scikit-learn statsmodels matplotlib seaborn sympy pint
# optional per packet: yfinance pandas_ta quantstats pyportfolioopt ydata-profiling pandas-montecarlo
# optional Vision: docling rapidocr css_inline
# optional Text: spacy textdescriptives; python -m spacy download xx_sent_ud_sm
# optional Monaco: pywebview  (+ PyQt6 PyQt6-WebEngine qtpy on Linux)
```

**Existing automated coverage (do not re-implement in pytest):** `tests/calc/python/test_function.py`, `test_calc_addin_data.py`, `tests/scripting/test_*.py` for trusted helpers, `tests/calc/numpy_domains_demo_cases.py` (case catalog). **This plan is live LO**, which those mocks do not replace.

**Existing live fixtures (reuse):**

| File | Use |
|------|-----|
| New blank Calc | Packets A–C (formula authoring) |
| [`tests/fixtures/python_showcase_demo.xlsx`](../tests/fixtures/python_showcase_demo.xlsx) | Packet D (business dashboard). **Do not use** `python_showcase_demo.ods` — ODS generator is currently wrong |
| [`tests/fixtures/numpy_domains_demo.ods`](../tests/fixtures/numpy_domains_demo.ods) | Packet E (trusted helpers via `=PYTHON()`) |
| [numpy_domains_demo.README.md](../tests/fixtures/numpy_domains_demo.README.md) | How to recalc that ODS |

---

## Packet A — `=PY()` smoke (Layer 0)

**Why first:** If this fails, nothing else is worth debugging.

Open a **new** Calc spreadsheet. Semicolon vs comma: use your locale’s argument separator (`;` in many EU locales).

| id | Scenario | Formula / action | Expected |
|----|----------|------------------|----------|
| A1 | Hello world | `=PY("1 + 1")` | `2` |
| A2 | Alias | `=PYTHON("1 + 1")` | `2` |
| A3 | `result` assignment | `=PY("result = 3 ** 8")` | `6561` |
| A4 | Last-expression fallback | `=PY("3 ** 8")` | `6561` |
| A5 | Auto-imported NumPy | `=PY("float(np.mean([1, 2, 3, 4]))")` | `2.5` |
| A6 | Auto-imported math | `=PY("round(math.sqrt(2), 4)")` | `1.4142` |
| A7 | String return | `=PY("result = 'hello'")` | `hello` |
| A8 | List as text | `=PY("str([1, 2, 3])")` | `[1, 2, 3]` (single cell) |
| A9 | Recalc persists | Edit an unrelated cell, then **F9** | A1 still `2` |
| A10 | Hard recalc | **Ctrl+Shift+F9** | All PY cells still correct |

---

## Packet B — Ranges, pandas, spill (Layer 0 + data shapes)

Put sample data on **Sheet1**:

```
A1: Region    B1: Sales    C1: Units
A2: North     B2: 1200.5   C2: 10
A3: South     B3: 800      C3: 8
A4: North     B4: 1500     C4: 12
A5: East      B5: 400      C5: 5
```

| id | Scenario | Formula | Expected |
|----|----------|---------|----------|
| B1 | Column mean | `=PY("float(np.mean(data))"; B2:B5)` | `975.125` |
| B2 | Header table → pandas | `=PY("df = data.to_pandas(); float(df['Sales'].sum())"; A1:C5)` | `3900.5` |
| B3 | Filter in Python | `=PY("sum(r[1] for r in data[1:] if r[0]=='North')"; A1:C5)` | `2700.5` |
| B4 | Weighted idea (units × sales not needed) | `=PY("float(np.sum(np.asarray(data)))"; C2:C5)` | `35` |
| B5 | Multi-range | `=PY("float(np.mean(data[0])+np.mean(data[1]))"; B2:B5; C2:C5)` | mean(sales)+mean(units) ≈ `983.875` |
| B6 | Auto-spill list | Single cell `=PY("result = [10, 20, 30]")` | Origin + two cells below fill `10,20,30` |
| B7 | Auto-spill DataFrame | `=PY("data.to_pandas()"; A1:C5)` from a **free** cell (e.g. E1) | Header + 4 data rows spill |
| B8 | Spill blocked | Put text in the spill target, re-enter B6 | Origin shows `#SPILL!` |
| B9 | Date parse (opt-in) | Dates in `A1:B4` as ISO strings + `=PY("df=data.to_pandas(date_cols=True); str(df.dtypes.iloc[0])"; A1:B4)` | datetime-like dtype, not object crash |
| B10 | Dependents | `=PY("float(np.mean(data))"; B2:B5)` then change B2 | Mean updates on recalc |

**Do not** combine a data range **and** `ROW()-1` as a third argument (IDL is `(code, data)`; that is a known limitation, not this pass).

---

## Packet C — Shared kernel, init script, Reset (Layer 0 session)

Settings → Python → session mode **shared**. New workbook.

| id | Scenario | Action | Expected |
|----|----------|--------|----------|
| C1 | Init helpers | **Edit Initialization Script…**: `def double(x): return x * 2` Save. Cell: `=PY("double(21)")` | `42` |
| C2 | Isolated vs seed | Switch to **isolated**, same init, same formula | Still `42` (init seeds every cell) |
| C3 | Shared leak | Shared mode. A1: `=PY("x = 10")`. B1: `=PY("x + 1"; A1)` (**must pass A1 as data**) | `11` |
| C4 | DAG order | Put C3’s consumer **above** the producer on the sheet; still pass producer as `data` | Still `11` (order via `data`, not row-major) |
| C5 | Reset | **Reset Python Session** (or **Ctrl+Alt+Shift+F9**). Recalc B1 without re-running A1 first | `NameError` / error text for `x`, not stale `11` |
| C6 | Idempotent KPI | `=PY("result = float(np.sum(data))"; B2:B5)` press F9 three times | Same number each time (no growth) |

---

## Packet D — Showcase workbook (real dashboard)

Open [`python_showcase_demo.xlsx`](../tests/fixtures/python_showcase_demo.xlsx). **Ctrl+Shift+F9**. Check live KPI / metric cells, not the static labels.

**Use the `.xlsx` only.** The matching `.ods` from `generate_pretty_demo_spreadsheet.py` is currently buggy; do not report ODS mismatches as product failures. (XLSX import may show `=PYTHON()` / `=py()` casing — that is expected; recalc should still hit the add-in.)

Source of formulas: [python-in-calc-showcase.md](python-in-calc-showcase.md) and `scripts/generate_pretty_demo_spreadsheet.py`.

| id | Sheet | What to check | Expected (from docs / generator) |
|----|-------|---------------|----------------------------------|
| D1 | Overview | Total Revenue KPI | `$119,142.00` (or `119142`) |
| D2 | Overview | Avg Profit Margin | `28.4%` |
| D3 | Overview | Anomalies Flagged | `5 Detected` (or `5`) |
| D4 | Sales_Analytics | Enterprise revenue `=PY` | `81497.5` (matches filter on `Customer Type == Enterprise`) |
| D5 | Sales_Analytics | Top SKU by revenue | `FURN-3388` (non-empty SKU code) |
| D6 | Statistics_ML | Pearson r Ad Spend vs Revenue | ~`0.7978` |
| D7 | Statistics_ML | OLS slope | ~`5.07` |
| D8 | Statistics_ML | Top ROI channel | `Email Marketing` (one of Search Ads / Social Media / Email Marketing) |
| D9 | Forecasting | CAGR string | `46.3%` (percentage like `x.x%`) |
| D10 | Forecasting | Peak historical sales | `303.5` (max of volume column) |
| D11 | Optimization | Lowest-vol asset | `Treasury_Bonds` (one of the four names) |
| D12 | Engineering_Math | kW→hp, PSI→bar, °C→°F, km/h→m/s | `201.15`, `151.68`, `185.0`, `33.33` (sensible converted numbers) |
| D13 | Engineering_Math | derivative / erf cells | `7.5824`, `0.7468` (finite numbers, not errors) |
| D14 | Viz_Gallery | Four `=PY(plt…)` cells | Four GraphicObjectShape plots anchored near those cells |

If KPIs are `#VALUE!` but Packet A passed, suspect locale separators or add-in namespace; LibrePy must still resolve `ORG.EXTENSION.WRITERAGENT.PYTHONFUNCTION` ([`tests/scripts/test_librepy_calc_addin_namespace.py`](../tests/scripts/test_librepy_calc_addin_namespace.py)).

---

## Packet E — Domain demo ODS (trusted helpers via formula)

Open [`numpy_domains_demo.ods`](../tests/fixtures/numpy_domains_demo.ods). Follow [the README](../tests/fixtures/numpy_domains_demo.README.md): **Ctrl+Shift+F9**, compare `python_formula` vs `expected_scalar`.

**Skip** `chat_prompt` cells (WriterAgent). **Skip** `goal_seek_solver` chat block. **Quant** helpers that `requires_network` (`fetch_historical_data`): skip unless the agent has network + `yfinance`.

Cases are defined in [`tests/calc/numpy_domains_demo_cases.py`](../tests/calc/numpy_domains_demo_cases.py). Treat each `DomainDemoCase.id` as a row:

### E-analysis (14)

`describe_data`, `kpi_summary`, `detect_outliers`, `quick_stats`, `format_currency`, `format_percent`, `clean_and_prepare`, `pivot_aggregate`, `group_summary`, `compare_periods`, `correlation_matrix`, `run_regression`, `cluster_numeric`, `monte_carlo`

Needs: numpy pandas scipy sklearn statsmodels; `describe_data` also ydata-profiling; `monte_carlo` also pandas-montecarlo. If a helper returns `MISSING_PACKAGE`, record that as **blocked**, not fail.

### E-forecast (3)

`forecast_time_series`, `decompose_time_series`, `anomaly_detection_time_series` (spike month should be flagged)

### E-viz (formula + visual)

`quick_plot`, `correlation_heatmap`, `time_series_plot` — `check_mode: visual`: image on sheet. Optional `matplotlib_multi_figure` block.

### E-math (4)

`solve_equation`, `symbolic_simplify`, `integrate`, `differentiate` — scalar matches `expected_scalar`.

### E-optimize (3)

`linear_programming`, `optimize_portfolio`, `solve_scheduling_problem`

### E-units (formula if present on sheet)

`convert_quantity`, `parse_quantity` — formatted cell like `36 km/h`.

### E-quant (optional)

`technical_analysis` on OHLCV grid (no network). `portfolio_tearsheet`, `efficient_frontier` if packages present. `fetch_historical_data` only with network.

---

## Packet F — Run Python Script menus (Layers 2–3)

LibrePy surface: **Tools / Python menus → Run Python Script…** (not chat). Use **domain helper picker**, not freeform unless noted.

For each row: select the **input range** on the demo ODS (or Packet B sample), open the named helper, **Run**, confirm table/image/text lands in the document.

| id | Menu section | Helper | Input | Pass |
|----|--------------|--------|-------|------|
| F1 | Analysis Helpers | `[Analysis] kpi_summary` | Sales grid | KPI table inserted |
| F2 | Analysis Helpers | `[Analysis] detect_outliers` | `OUTLIER_GRID` (100 is the outlier) | Flags 100 |
| F3 | Analysis Helpers | `[Analysis] run_regression` | x/y 1→2,2→4,… | Slope ~2 |
| F4 | Viz Helpers | `[Viz] quick_plot` | Sales grid | Chart image on sheet |
| F5 | Viz Helpers | `[Viz] correlation_heatmap` | 3-col numeric | Heatmap image |
| F6 | Forecast Helpers | `[Forecast] forecast_time_series` | 36-month grid | Forecast table (and optional plot) |
| F7 | Forecast Helpers | `[Forecast] anomaly_detection_time_series` | anomaly grid | Spike flagged |
| F8 | Math Helpers | `[Math] solve_equation` | template defaults | Solution text/table |
| F9 | Units Helpers | `[Units] convert_quantity` | `10, "m/s", "km/h"` | `36 km/h` at selection |
| F10 | Optimize Helpers | `[Optimize] linear_programming` | LP grid from demo | Feasible solution table |
| F11 | Calc undo | After F1, **Ctrl+Z** | Inserted table gone in one undo |
| F12 | Writer RPS | Open Writer, Units or Math helper | Formatted string / math-related insert, no crash |
| F13 | Text Analytics (opt) | `[Text] readability` on a Writer paragraph | Scores table if spaCy present |

Quant RPS (optional, same as E-quant).

---

## Packet G — Matplotlib from `=PY()` (Viz Phase A)

New sheet. Auto-import `plt`.

| id | Scenario | Formula | Expected |
|----|----------|---------|----------|
| G1 | Minimal plot | `=PY("plt.plot([1,2,3])")` | Image anchored on/near cell |
| G2 | Plot from range | Packet B sales: `=PY("plt.plot([r[1] for r in data[1:]]); plt.title('Sales')"; A1:C5)` | Line chart |
| G3 | Recalc does not crash | F9 twice | Still one sensible graphic (dupes acceptable to note, crash is fail) |

---

## Packet H — Monaco / Edit Python in Cell (Layer 4)

Needs `pywebview` in the venv. If missing: **Run Python Script** should fall back to the native dialog (H-fallback). **Edit Python in Cell** should **not** silently use LO embedded Python.

| id | Scenario | Pass |
|----|----------|------|
| H1 | Select a `=PY` cell → **Edit Python in Cell…** (or **Ctrl+Alt+Shift+P**) | Monaco (or documented failure) with the code |
| H2 | Change `1 + 1` → `1 + 2`, Save | Cell formula updates and value is `3` |
| H3 | **Run Python Script…** with `result = 2 + 2` | Inserts `4` / table |
| H4 | Document-attached script: Save under **This Document**, close/reopen file | Script still in picker |
| H5 | LibrePy Python **sidebar** (Calc deck) | Lists PY cells; diagnostics show stdout if you `print()` in a cell (cell value still from `result`) |

---

## Packet I — Vision / OCR (Layer 5, optional)

Skip if Vision packages missing (record **blocked**).

| id | Scenario | Pass |
|----|----------|------|
| I1 | Insert a PNG of a simple table into Writer or Calc | Graphic selected |
| I2 | Run Python Script → **Vision Helpers** OCR | Text/table extracted into doc |
| I3 | Settings → Python **Vision Libraries** Test | OCR group Present |

---

## Packet J — TeX / Math (Layer 6)

| id | Scenario | Pass |
|----|----------|------|
| J1 | Writer: **Insert LaTeX Math…** with `E = mc^2` | Native Math object, not raw LaTeX dump |
| J2 | RPS Math `latex_to_math_object` if exposed | Valid Math insert |

---

## Packet K — Settings / worker health

| id | Scenario | Pass |
|----|----------|------|
| K1 | Empty venv path: `=PY("1+1")` | Works on embedded Python (stdlib) |
| K2 | Empty path: `=PY("float(np.mean([1,2]))")` | Clear missing-numpy / import error, **not** LO crash |
| K3 | Point at a good venv again | NumPy formula works without restart if documented; otherwise after restart |
| K4 | Timeout: set timeout to `1`, `=PY("import time; time.sleep(5)")` | Timeout message in cell, UI not frozen forever |
| K5 | LibrePy weekly update check does not throw at startup | Log clean enough |

---

## Packet L — Stay on the LibrePy *surface* (sandbox)

Not a packaging checklist. If WriterAgent is installed, chat / `=PROMPT()` / converter menus may exist — **do not open them** for this plan.

| id | Check | Pass |
|----|-------|------|
| L1 | `=PY("import os; os.getcwd()")` | Sandbox **blocks** `os` (error in cell, not a path) |

---

## Suggested farm-out batches

| Agent | Packets | Time-ish | Venv extras |
|-------|---------|----------|-------------|
| 1 | P0 + A + B | 20–40 min | numpy pandas |
| 2 | P0 + C | 15–25 min | numpy |
| 3 | P0 + D | 20–40 min | numpy pandas scipy matplotlib |
| 4 | P0 + E-analysis + E-forecast | 30–45 min | analysis + statsmodels stack |
| 5 | P0 + E-viz + G | 20 min | matplotlib seaborn |
| 6 | P0 + E-math + E-units + J | 20 min | sympy pint |
| 7 | P0 + E-optimize + F (subset) | 30 min | scipy |
| 8 | P0 + H + K + L | 25 min | pywebview |
| 9 | P0 + E-quant + F quant | optional | yfinance stack + network |
| 10 | P0 + I | optional | docling/paddle |

Agents 4–7 can share one running LO if they use **separate workbooks** and do not Reset Session on each other.

---

## Mapping to layers (split doc)

| Layer | Packets |
|-------|---------|
| 0 `=PY()` | A, B, C, D, G, K |
| 1 Trusted RPC | E (formula path), F |
| 2 Run Python Script | F, H3, H4 |
| 3 Domain helpers | E, F |
| 4 Monaco / sidebar | H |
| 5 Vision | I |
| 6 TeX | J |
| Sandbox (LibrePy surface, not packaging) | L |

---

## After this pass (not now)

- Lexer/quoting, `#SPILL!` geometry, jagged ranges, NaN vs blank tables ([calc-py-data-shapes.md](calc-py-data-shapes.md)).
- Matrix `ROW()-1` fast path UNO tests (`test_prompt_function_matrix_uno.py`).
- Excel `.xlsx` round-trip (`PythonExcelSamples/`) — WriterAgent converter, not LibrePy.
- Jail-safe Online (`compute_service/`, [numpy-jailsafe.md](numpy-jailsafe.md)).
- Turn passing live cases into UNO `@native_test` only where mocks already lie.

---

## Result template (copy per agent)

```
packet: A
librepy_version:
lo_version:
venv:
id	result	actual	notes
A1	pass	2
A2	...
```
