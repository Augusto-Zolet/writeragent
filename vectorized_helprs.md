# Dev Plan: Vectorized / Range Inputs for Lightweight Helpers

## Overview & Goals

Currently, lightweight helper functions such as `convert_quantity(10, "m/s", "km/h")` in the **Units** domain or `solve_equation("x**2 - 4", "x")` in the **Math / Symbolic** domain are primarily scalar/single-expression functions.

When users work in Calc spreadsheets with `=PY()` or `=PYTHON()`, their data is naturally organized in cell ranges (e.g. `A1:A100`). Without vectorization support, users must write Python list comprehensions like `[convert_quantity(x, "m/s", "km/h") for x in A1:A100]`.

### Primary Objectives
1. **Polymorphic Scalar & Vector Inputs**: Allow helper functions to accept either a **scalar** (number, string) or a **vector/range** (`CalcRange`, 1D `list`/`tuple`, 2D column vector `[[v], ...]`, `numpy.ndarray`, or `pandas.Series`).
2. **Orientation & Shape Preservation**:
   - Scalar input $\to$ scalar output.
   - 1D list input `[x, y, z]` $\to$ 1D list output `[r1, r2, r3]`.
   - Column vector / vertical range $N \times 1$ $\to$ column vector $N \times 1$ `[[r1], [r2], [r3]]` (so it spills vertically down the spreadsheet column in Calc).
   - Row vector / horizontal range $1 \times N$ $\to$ row vector $1 \times N$ `[[r1, r2, r3]]`.
   - 2D grid $M \times N$ $\to$ 2D grid $M \times N$.
3. **Parameter Broadcasting**:
   - When values are a vector and configuration parameters (e.g. `from_unit`, `to_unit`, `variable`) are scalars, automatically broadcast the scalars across all items.
   - When parameters are also vectors of matching length (e.g. converting a column of values using a paired column of units), pair them elementwise.
4. **Resilient Cell Handling**:
   - Handle empty/missing cells (`None`, `""`, `NaN`) gracefully without crashing the whole range computation.
   - Provide per-element error reporting if individual cells fail to parse.
5. **Domain Audit**:
   - Evaluate all domains and helpers across the codebase to determine which functions should be vectorized.

---

## Domain-by-Domain Audit Table

Below is the comprehensive analysis of all domains and helper functions in the codebase:

| Domain | Helper Function | Worth Extending? | Rationale & Behavioral Specification |
| :--- | :--- | :---: | :--- |
| **Units** | `convert_quantity(value, from, to)` | **YES** *(High Priority)* | **Primary use case.** Users want to convert entire columns of measurements (e.g. `convert_quantity(A1:A50, "m/s", "km/h")`). Broadcasts units if scalar, or pairs elementwise if unit columns are passed. |
| **Units** | `parse_quantity(quantity)` | **YES** *(High Priority)* | Users have columns of raw measurement strings (e.g. `["10 m/s", "25 km/h", "3.5 psi"]`). Vectorized version parses each row into magnitude and unit. |
| **Units** | `format_quantity(magnitude, units, format_spec)` | **YES** *(Medium Priority)* | Formatting a column of numerical magnitudes with a unit label and format specifier (e.g. `format_quantity(A1:A50, "m/s", ".2f")`). |
| **Units** | `check_dimensionality(quantity_a, quantity_b)` | **YES** *(Medium Priority)* | Batch verification of physical unit compatibility across two columns of data. |
| **Math (SymPy)** | `solve_equation(equation, variable)` | **YES** *(High Priority)* | Solving a column of equations (e.g. `solve_equation(A1:A10, "x")`). Returns solution(s) per row. |
| **Math (SymPy)** | `symbolic_simplify(expression)` | **YES** *(High Priority)* | Simplifying a column of mathematical expressions row-by-row. |
| **Math (SymPy)** | `differentiate(expression, variable)` | **YES** *(High Priority)* | Computing derivatives for a column of expressions with respect to a variable. |
| **Math (SymPy)** | `integrate(expression, variable, lower, upper)` | **YES** *(High Priority)* | Computing indefinite or definite integrals for a column of expressions. Broadcasts bounds if scalar. |
| **Math (SymPy)** | `latex_to_math_object(latex)` | **YES** *(Medium Priority)* | Batch validating and normalizing a column of LaTeX formulas. |
| **Text Analytics** | `sentiment(text, ...)` | **YES** *(High Priority)* | Analyzing sentiment on a column of survey comments, reviews, or feedback cells (e.g. `sentiment(A2:A100)`). Returns score/label column. |
| **Text Analytics** | `readability(text, ...)` | **YES** *(High Priority)* | Scoring readability (Flesch-Kincaid, etc.) across a column of text snippets or paragraphs. |
| **Text Analytics** | `entities(text, ...)` | **YES** *(Medium Priority)* | Extracting NER entities for each text cell in a column. |
| **Text Analytics** | `key_phrases(text, ...)` | **YES** *(Medium Priority)* | Extracting keywords/noun phrases for each text cell in a column. |
| **Text Analytics** | `topics(text, ...)` | **No (Keep Tabular/Corpus)** | Topic modeling (TF-IDF + NMF) requires the entire collection of documents/rows as a corpus to extract global topics, rather than operating independently per row. (Already accepts range as corpus). |
| **Analysis** | `format_currency(values, symbol, decimals)` | **YES (Fix/Refine)** | Currently only handles lists; fails on `CalcRange`/NumPy/Pandas and always returns 1D list even for scalar. Refactor to preserve scalar vs 2D column orientation. |
| **Analysis** | `format_percent(values, decimals)` | **YES (Fix/Refine)** | Same as `format_currency`. Needs clean scalar and 2D column orientation support. |
| **Analysis** | `describe_data`, `kpi_summary`, `detect_outliers`, `quick_stats`, `clean_and_prepare`, `pivot_aggregate`, `group_summary`, `compare_periods`, `correlation_matrix`, `run_regression`, `cluster_numeric`, `monte_carlo` | **No (Already Range-Native)** | These are whole-dataset/EDA operations designed for 2D tabular grids. They already accept `CalcRange` / 2D tables and return summary tables/metrics. |
| **Viz** | `quick_plot`, `plot_data`, `correlation_heatmap`, `time_series_plot` | **No (Already Range-Native)** | Statistical plotting generates chart images from multi-column dataset grids. Not a per-element scalar function. |
| **Forecasting** | `forecast_time_series`, `decompose_time_series`, `anomaly_detection_time_series` | **No (Already Range-Native)** | Time-series algorithms require temporal sequences (date + value series), not elementwise mapping. |
| **Optimization** | `optimize_portfolio`, `linear_programming`, `solve_scheduling_problem` | **No (Already Range-Native)** | Matrix-level optimization solvers (mean-variance covariance, simplex LP, Hungarian assignment). |
| **Quant** | `fetch_historical_data(tickers, ...)` | **YES (Ticker Input)** | Accepts a single ticker string `"AAPL"` or list `["AAPL", "MSFT"]`. Should seamlessly accept a Calc column range `A1:A5` of ticker symbols. |
| **Quant** | `technical_analysis`, `portfolio_tearsheet`, `efficient_frontier` | **No (Already Range-Native)** | Full-grid financial operations on OHLCV and asset return matrices. |
| **DuckDB / SQL** | `run_sql(query, ...)` | **No (Query-Native)** | Executes SQL statements over registered table ranges. |

---

## Technical Design & Architecture

### 1. Shared Vectorization Engine (`plugin/scripting/venv/vectorize.py`)

To avoid duplicating shape inspection, unwrapping, broadcasting, and re-wrapping across every domain helper, we will introduce a shared, zero-dependency (stdlib-only, numpy/pandas optional) vectorization utility in the venv:

```python
class VectorShape(Enum):
    SCALAR = "scalar"
    LIST_1D = "list_1d"
    COLUMN_2D = "column_2d"     # N x 1 (e.g. CalcRange vertical column)
    ROW_2D = "row_2d"           # 1 x N (e.g. CalcRange horizontal row)
    GRID_2D = "grid_2d"         # M x N

@dataclass
class UnwrappedVector:
    flat_items: list[Any]
    shape: VectorShape
    orig_shape: tuple[int, ...]
    is_vector: bool

def inspect_vector_input(val: Any) -> UnwrappedVector:
    """Inspect input and flatten to 1D items while remembering the original orientation."""
    ...

def rewrap_vector_output(results: list[Any], shape: VectorShape, orig_shape: tuple[int, ...]) -> Any:
    """Reconstruct output matching the exact input orientation."""
    ...

def broadcast_arguments(*args: Any) -> tuple[bool, int, list[list[Any]]]:
    """Inspect multiple positional arguments, determine if any is a vector, 
    and broadcast scalar arguments to match the vector length."""
    ...
```

#### Shape Mapping Matrix:
| Input Type & Shape | Output Shape | Notes |
| :--- | :--- | :--- |
| Scalar (`10`, `"x**2"`) | Scalar (`36.0`, `[-2, 2]`) | Returns raw scalar value for direct python / `=PY()` |
| 1D list/tuple (`[10, 20]`) | 1D list (`[36.0, 72.0]`) | Python list semantics |
| Vertical `CalcRange` ($N \times 1$) | 2D Column `[[36.0], [72.0]]` | Calc `=PY()` matrix formulas spill vertically down the column |
| Horizontal `CalcRange` ($1 \times N$) | 2D Row `[[36.0, 72.0]]` | Calc `=PY()` matrix formulas spill horizontally |
| 2D `CalcRange` ($M \times N$) | 2D Grid ($M \times N$) | Elementwise grid transformation |
| Pandas Series ($N$) | 1D list / Pandas Series | Preserves index if requested |
| NumPy 1D ndarray ($N$) | NumPy array or list | Seamless array protocol |

### 2. Handling Blanks, None, and Errors in Ranges

In Calc spreadsheets, ranges often contain empty cells (represented as `None` or `""`), headers, or bad inputs.
- **Missing / Blank Cells**:
  - When an element is `None` or `""`, the vectorized helper returns `""` or `None` (empty cell in Calc) rather than throwing an exception.
- **Per-Element Failures**:
  - If a specific cell has an invalid equation or unit (e.g. row 4 has `"invalid_expr"` while rows 1–3 are valid), the helper can return `#VALUE!` or `#ERR: <msg>` for row 4 while successfully computing rows 1–3, preventing the entire column calculation from breaking.

---

## Detailed Component Changes

### Component 1: Core Vectorization Utility
#### [NEW] `plugin/scripting/venv/vectorize.py`
- Implements `inspect_vector_input`, `rewrap_vector_output`, `broadcast_arguments`, and `@vectorize` decorator or wrapper helper.
- Handles `CalcRange`, `list`, `tuple`, `np.ndarray`, `pd.Series`, and scalars.

#### [NEW] `tests/scripting/test_vectorize.py`
- Comprehensive unit tests verifying shape preservation, broadcasting, empty cell skipping, and error resilience.

---

### Component 2: Units Domain Vectorization
#### [MODIFY] `plugin/scripting/venv/units.py`
- Update `convert_quantity`:
  - Support scalar `value` or range/vector `value`.
  - Support scalar or vector `from_unit` and `to_unit` with broadcasting.
  - Return numeric float/int or formatted strings based on `return_formatted: bool = False` or payload mode.
  - If called via `run_units` RPC spec, returns a unified result payload containing `magnitudes: list[float]`, `formatted: list[str]`, and `values: list[list[Any]]`.
- Update `parse_quantity`:
  - Accept list of quantity strings $\to$ return list of parsed results (or 2-column grid of `[magnitude, unit]`).
- Update `format_quantity`:
  - Accept list of magnitudes and format with given unit.
- Update `check_dimensionality`:
  - Accept paired lists of units/quantities and return list/column of boolean results.

#### [MODIFY] `plugin/scripting/units.py`
- Update host facade and `format_units_for_calc`:
  - Support formatting multi-row / column results for Calc sheet insertion when Run Python Script is executed on a range.

#### [MODIFY] `tests/scripting/test_units.py`
- Add unit tests for `convert_quantity([10, 20, 30], "m/s", "km/h")`.
- Add test for `convert_quantity(CalcRange([[10], [20], [30]]), "m/s", "km/h")` asserting vertical $3 \times 1$ return `[[36.0], [72.0], [108.0]]`.
- Add test for pairwise unit conversion: `convert_quantity([10, 100], ["m/s", "cm"], ["km/h", "m"])`.
- Add test for blank/None cell handling.

---

### Component 3: Math / Symbolic Domain Vectorization
#### [MODIFY] `plugin/scripting/venv/symbolic.py`
- Update `solve_equation`:
  - Accept scalar equation or range/list of equations.
  - Returns list/column of solutions.
- Update `symbolic_simplify`:
  - Accept scalar expression or range/list of expressions $\to$ return column of simplified strings/LaTeX.
- Update `differentiate`:
  - Accept range/list of expressions with broadcasted variable.
- Update `integrate_helper`:
  - Accept range/list of expressions with broadcasted bounds.
- Update `latex_to_math_object`:
  - Accept range/list of LaTeX strings.

#### [MODIFY] `plugin/scripting/symbolic.py`
- Update host egress to handle vector results in Calc and Writer.

#### [MODIFY] `tests/scripting/test_symbolic.py`
- Add unit tests for `solve_equation(["x**2 - 4", "x + 5 = 10"], "x")`.
- Add unit tests for `symbolic_simplify(["(x+1)**2 - x**2 - 2*x", "sin(x)**2 + cos(x)**2"])` with `CalcRange`.

---

### Component 4: Analysis Domain Formatting Refinement
#### [MODIFY] `plugin/scripting/venv/analysis.py`
- Refactor `format_currency` and `format_percent`:
  - Ensure single scalar input returns a single scalar string (e.g. `format_currency(1234.5)` $\to$ `"$1,234.50"`).
  - Ensure `CalcRange` column input returns a 2D column list `[["$1,234.50"], ["$500.00"]]` for Calc matrix compatibility.

---

### Component 5: Text Analytics Vectorization
#### [MODIFY] `plugin/scripting/venv/text_analytics.py`
- Update `sentiment`, `readability`, `entities`, `key_phrases` to accept a `CalcRange` / list of strings and run batch inference via spaCy/transformers `nlp.pipe(texts)` or list mapping.
- Maintain existing single-text whole-document analysis behavior when given a single string.

---

### Component 6: Quant Domain Ticker Range Support
#### [MODIFY] `plugin/scripting/venv/quant.py`
- In `fetch_historical_data`, unpack `tickers` if passed as a `CalcRange` or 2D column grid into a flat list of clean ticker strings.

---

### Component 7: Documentation & Showcase Updates
#### [MODIFY] `docs/numpy-domains.md`
- Document the vectorized / range input support for Units, Math, Text Analytics, and Analysis helpers.
- Provide examples of `=PY("convert_quantity(A1:A10, 'm/s', 'km/h')")` and `=PY("solve_equation(A1:A5, 'x')")`.

#### [MODIFY] `tests/calc/numpy_domains_demo_cases.py`
- Add test cases demonstrating range-in / column-out execution for `=PY()`.

---

## Verification Plan

### Automated Tests
1. **Vectorization Core Tests**:
   - `pytest tests/scripting/test_vectorize.py`
2. **Units Domain Tests**:
   - `pytest tests/scripting/test_units.py`
   - `pytest tests/scripting/test_python_runner_units.py`
3. **Math / Symbolic Domain Tests**:
   - `pytest tests/scripting/test_symbolic.py`
   - `pytest tests/scripting/test_python_runner_symbolic.py`
4. **Analysis & Text Analytics Tests**:
   - `pytest tests/scripting/test_analysis.py`
   - `pytest tests/scripting/test_text_analytics.py`
5. **Static Typecheck & Lint**:
   - `make typecheck`

### Integration / Demo Verification
- Test Calc spreadsheet formula evaluation:
  - `=PY("convert_quantity(A1:A10, 'm/s', 'km/h')")`
  - `=PY("solve_equation(B1:B5, 'x')")`
  - `=PY("format_currency(C1:C10)")`
- Confirm column spilling matches expectations without manual list comprehensions.
