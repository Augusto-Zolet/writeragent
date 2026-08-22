# Dev Plan: Vectorized / Range Inputs for Lightweight Helpers (Revised)

## Overview & Goals

This plan refines the implementation for **vectorized and range inputs** across lightweight helper functions in WriterAgent / LibrePy.

When users work in Calc spreadsheets with `=PY()` or `=PYTHON()`, range arguments are passed as trailing arguments (e.g. `=PY("convert_quantity(data, 'm/s', 'km/h')"; A1:A100)`), binding the cell range to `data` in the Python execution scope (see [`docs/calc-py-data-shapes.md`](docs/calc-py-data-shapes.md)).

Without vectorization, helper functions require manual Python list comprehensions (`[convert_quantity(x, "m/s", "km/h") for x in data]`). This plan adds seamless, polymorphic scalar/vector execution to lightweight helpers.

---

## Key Design Principles & Clarifications

### 1. Correct `=PY()` Formula Syntax
Trailing range arguments are bound to `data` by the Calc add-in:
```text
# Correct Calc formula:
=PY("convert_quantity(data, 'm/s', 'km/h')"; A1:A10)
=PY("format_currency(data)"; C1:C10)
```

### 2. Three Distinct Range Operations
Range inputs are handled differently depending on the nature of the helper:
1. **Elementwise Map:** One scalar computation per cell, rewrapped to the input shape and orientation (`convert_quantity`, `symbolic_simplify`, `format_currency`, `readability`).
2. **Flatten-then-One-Call:** Unwrap a range/column of cells into a clean 1D list of strings for a single batch API call (`fetch_historical_data(tickers)` in Quant).
3. **Corpus / Whole-Document:** The range represents a document collection or corpus for whole-dataset modeling (`topics` in Text Analytics).

### 3. Dual Call Surfaces & Return Contracts
- **Direct Python / `=PY()`:** Returns raw Python numbers or 1D/2D lists (`[[36.0], [72.0]]`) so Calc matrix formulas spill numbers cleanly into spreadsheet columns.
- **RPC Dispatcher (`run_units`, `run_symbolic`):**
  - **Scalar input:** Returns the existing compact `_ok_result` dictionary (no breaking changes to existing RPS templates/tests).
  - **Vector input:** Returns **one single compact payload** containing `values` (2D grid), `magnitudes`, `formatted`, and per-cell error summaries (never an array of $N$ dict blobs).

### 4. Reuse Existing Shape & Coercion Primitives
Do not create a parallel type system or duplicate grid classes:
- Reuse [`CalcRange`](plugin/scripting/calc_range.py), `ensure_rectangular_2d`, and `column_vector_as_2d`.
- Reuse `is_missing_value` and standard error tokens (`_LO_ERROR_TOKENS`) from [`coerce.py`](plugin/scripting/venv/coerce.py).
- New helper module is named `plugin/scripting/venv/map_range.py` (avoiding name collision with `plugin/calc/spreadsheet_import/vectorize.py`).

### 5. Error & Blank Handling
- **Blanks / Empty Cells:** `None`, `""`, NaN, or existing `#N/A` are skipped and emitted as empty cells (`""` / `None`).
- **Per-Element Failures:** If a single cell fails (e.g. invalid unit syntax in row 3), emit `"#VALUE!"` for that cell while remaining cells compute successfully.
- **Call-Level Failures:** Missing packages (`pint`, `sympy`), invalid helper names, or vector length mismatches fail the entire call immediately via `_error_result`.

---

## Domain-by-Domain Audit & Phasing Table

| Domain | Helper Function | Phasing & Status | Operation Kind | Rationale & Behavioral Contract |
| :--- | :--- | :---: | :---: | :--- |
| **Units** | `convert_quantity(value, from, to)` | **v1 (High)** | Elementwise Map | **Primary showcase.** Accepts scalar or `CalcRange`/1D list. Broadcasts scalar units or pairs equal-length 1D unit vectors. Direct `=PY()` returns numeric magnitudes; RPC returns single vector payload. |
| **Units** | `parse_quantity(quantity)` | **v1 (High)** | Elementwise Map | Parses column of quantity strings. Default: one cell per row (magnitude or formatted string). Optional 2-column grid in RPC. |
| **Units** | `format_quantity(magnitude, units, format_spec)` | **v1** | Elementwise Map | Formats column of magnitudes with scalar (or paired) units. |
| **Units** | `check_dimensionality(quantity_a, quantity_b)` | **Later** | Elementwise Map | Boolean compatibility column. Useful but deprioritized for v1. |
| **Analysis** | `format_currency(values, symbol, decimals)` | **v1 (Fix)** | Elementwise Map | Fix existing implementation: scalar returns scalar string; `CalcRange` column returns $N \times 1$ list; handles missing cells. |
| **Analysis** | `format_percent(values, decimals)` | **v1 (Fix)** | Elementwise Map | Same fix as `format_currency`. |
| **Quant** | `fetch_historical_data(tickers, ...)` | **v1 (Optional)** | Flatten | Unwraps `CalcRange` / $N \times 1$ column into `["AAPL", "MSFT"]` for single batch fetch. |
| **Math (SymPy)** | `symbolic_simplify(expression)` | **v2** | Elementwise Map | Simplifies column of expressions 1:1. |
| **Math (SymPy)** | `differentiate(expression, variable)` | **v2** | Elementwise Map | Computes derivative column; broadcasts scalar variable. |
| **Math (SymPy)** | `integrate(expression, variable, lower, upper)` | **v2** | Elementwise Map | Computes integral column; broadcasts bounds. |
| **Math (SymPy)** | `solve_equation(equation, variable)` | **v2** | Elementwise Map | Solves column of equations. **Policy:** joins multiple roots per equation into a single text cell (`"-2, 2"`) to maintain clean $N \times 1$ column spilling. |
| **Math (SymPy)** | `latex_to_math_object(latex)` | **Later** | Elementwise Map | Batch LaTeX validation. |
| **Text Analytics** | `readability(text, ...)` | **v3** | Batch Map | Evaluates readability on column of snippets via `nlp.pipe` batching. Single `str` preserves Writer whole-document mode. |
| **Text Analytics** | `sentiment(text, ...)` | **v3** | Batch Map | Batched transformer/spaCy inference on text column. Single `str` preserves Writer whole-document mode. |
| **Text Analytics** | `entities(text, ...)` / `key_phrases(text, ...)` | **v3** | Batch Map | Extracts entities/phrases per cell; default joins into single text cell. |
| **Text Analytics** | `topics(text, ...)` | **No Change** | Corpus | TF-IDF + NMF uses entire range as document collection (already range-native). |
| **Analysis** | `describe_data`, `kpi_summary`, `detect_outliers`, `run_regression`, etc. | **No Change** | Range-Native | 2D tabular dataset operations. |
| **Viz** | `quick_plot`, `plot_data`, `correlation_heatmap`, `time_series_plot` | **No Change** | Range-Native | Statistical chart generators from 2D grids. |
| **Forecasting** | `forecast_time_series`, `decompose_time_series`, `anomaly_detection_time_series` | **No Change** | Range-Native | Time series temporal algorithms on sequence grids. |
| **Optimization** | `optimize_portfolio`, `linear_programming`, `solve_scheduling_problem` | **No Change** | Range-Native | Matrix-level optimization solvers. |
| **DuckDB / SQL** | `run_sql(query, ...)` | **No Change** | Query-Native | SQL execution over registered range tables. |

---

## Detailed Implementation: Phase v1 Scope

### 1. Core Range Mapper: `plugin/scripting/venv/map_range.py`
- Implements:
  - `inspect_input(val)` $\to$ extracts 1D items, detects if input is scalar vs 1D list vs $N \times 1$ column vs $1 \times N$ row vs $M \times N$ grid.
  - `rewrap_output(results, inspected)` $\to$ converts 1D output back into the exact matching shape (scalar, 1D list, $N \times 1$ list, $1 \times N$ list, $M \times N$ grid).
  - `broadcast_args(*args)` $\to$ checks if any argument is a vector; broadcasts scalars across vector length; asserts equal length for multiple 1D vectors (mismatch raises `ValueError("Length mismatch")`).
  - `map_over_range(fn, *args, handle_blanks=True)` $\to$ helper that handles blank/missing cells via `is_missing_value`, catches per-element exceptions as `"#VALUE!"`, and rewraps output.
- Zero dependencies on host UNO / `document_helpers` / LLM client (safe for LibrePy and standard venv).

### 2. Units Domain Vectorization: `plugin/scripting/venv/units.py` & `plugin/scripting/units.py`
- Update `convert_quantity`:
  - Directly called from `=PY()`: returns numeric floats / integers in matching shape (e.g. `[[36.0], [72.0]]`).
  - Called via `run_units` RPC: returns single compact vector payload (`status="ok"`, `helper="convert_quantity"`, `values=[[36.0], ...]`, `magnitudes=[36.0, ...]`, `formatted=["36 km/h", ...]`). Scalar RPC return shape remains completely unchanged.
- Update `parse_quantity`:
  - Vector input returns 1D/2D output of parsed magnitudes (or formatted text).
- Update `format_quantity`:
  - Vector input returns formatted strings in matching shape.
- Host egress (`plugin/scripting/units.py`):
  - In `format_units_for_calc`, handle vector payload with `values` grid for sheet insertion.

### 3. Analysis Domain Formatting: `plugin/scripting/venv/analysis.py`
- Refactor `format_currency` and `format_percent`:
  - Scalar input $\to$ scalar formatted string (`"$1,234.50"`).
  - `CalcRange` / 2D column input $\to$ $N \times 1$ list of strings (`[["$1,234.50"], ["$500.00"]]`).
  - Empty cells return `""`.

### 4. Quant Domain Ticker Unwrap: `plugin/scripting/venv/quant.py` (v1 optional)
- In `fetch_historical_data(tickers, ...)`:
  - If `tickers` is a `CalcRange` or $N \times 1$ / $1 \times N$ column, unwrap to a clean list of non-empty ticker strings and pass to existing batch download.

---

## Verification Plan

### Automated Tests
1. **Core Mapper Tests** (`tests/scripting/test_map_range.py`):
   - Scalar input $\to$ scalar output.
   - 1D list input $\to$ 1D list output.
   - $N \times 1$ `CalcRange` / 2D list $\to$ $N \times 1$ 2D list output.
   - $1 \times N$ `CalcRange` $\to$ $1 \times N$ 2D list output.
   - $M \times N$ 2D grid with scalar parameter $\to$ $M \times N$ 2D grid output.
   - Broadcasting scalar parameters across a vector.
   - Pairwise 1D vector matching.
   - Vector length mismatch $\to$ raises error.
   - Blank / `None` / `""` / NaN / `_LO_ERROR_TOKENS` $\to$ empty cell.
   - Per-element error $\to$ `"#VALUE!"` in that slot, other rows succeed.
2. **Units Domain Tests** (`tests/scripting/test_units.py`):
   - Regression: scalar RPC dictionary shape is 100% unchanged.
   - `=PY()` direct call with 1D list $\to$ list of floats.
   - `=PY()` direct call with $N \times 1$ `CalcRange` $\to$ $N \times 1$ column of floats.
   - Pairwise conversion (`convert_quantity([10, 100], ["m/s", "cm"], ["km/h", "m"])`).
   - RPC vector execution returns single payload with `values` grid.
3. **Analysis Formatting Tests** (`tests/scripting/test_analysis.py`):
   - `format_currency` scalar $\to$ scalar string; `CalcRange` $\to$ $N \times 1$ 2D list.
   - `format_percent` scalar $\to$ scalar string; `CalcRange` $\to$ $N \times 1$ 2D list.
4. **Static Typecheck**:
   - `make typecheck`

### Spreadsheet Formula Verification
- `=PY("convert_quantity(data, 'm/s', 'km/h')"; A1:A10)`
- `=PY("format_currency(data)"; B1:B10)`
