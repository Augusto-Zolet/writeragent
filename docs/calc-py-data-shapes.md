# Calc `=PY()` data shapes

**Glossary:** `=PY()` and `=PYTHON()` are the same Calc add-in (`XPythonFunction`). Formulas below use `=PY`; either name works.

This doc is the authoritative **behavior** contract for range arguments: what `data` / `ranges` look like in Python, blank vs NaN, dates, logicals, and multi-range varargs.

Related:

| Doc | Owns |
| --- | --- |
| [Enabling NumPy & Python](enabling_numpy_in_libreoffice.md) | User guide, session modes, spill/matrix UX, architecture overview |
| [Venv IPC & serialization](numpy-serialization.md) | Pickle5 wire, `split_grid`, benchmarks, codec invariants |
| [Microsoft `=PY` design stance](ms-py-libreoffice-compatibility.md) | Why Calc keeps explicit `data` args; Excel packages already bind ranges as trailing `_xlws.PY` args that the rewriter maps onto `data` / `ranges` ([§5.8](ms-py-libreoffice-compatibility.md#58-ooxml--xlfnpy-import)) |

Code: [`plugin/scripting/calc_range.py`](../plugin/scripting/calc_range.py), [`plugin/calc/calc_addin_data.py`](../plugin/calc/calc_addin_data.py), [`plugin/calc/python/function.py`](../plugin/calc/python/function.py) (`to_calc_compatible`).

## Table of contents

1. [Data handoff and shaping](#data-handoff-and-shaping)
2. [Multi-range support (varargs)](#multi-range-support-varargs)
3. [Empty cells vs NaN](#empty-cells-vs-nan)
4. [Cell types and logicals](#cell-types-and-logicals)
5. [Dates and datetimes](#dates-and-datetimes)
6. [Rectangular shape rules](#rectangular-shape-rules)
7. [Deferred upgrades](#deferred-upgrades)

---

## Data handoff and shaping {#data-handoff-and-shaping}

**Where does `data` come from?** In an IDE, referencing `data` looks like a `NameError`. In `=PY()`, `data` is **injected at runtime** when you pass a range (or cell) as a trailing formula argument.

When you write `=PY(code; range)`, the add-in:

1. Resolves the range in Calc and reads cell values as a **rectangular 2D grid** (orientation preserved).
2. Packs the grid in a `calc_range` wire envelope (`split_grid` is a private transport optimization — see [serialization](numpy-serialization.md#strategy-3-split-grid-serialization-detail)).
3. Materializes [`CalcRange`](../plugin/scripting/calc_range.py) values and injects **`ranges`** (always a `list`) plus polymorphic **`data`** (one arg → that `CalcRange`; two or more → the same list as `ranges`).
4. Runs your script with `data` / `ranges` already bound.

| Range you pass in Calc | Structure of `data` in Python | Example usage |
| --- | --- | --- |
| **Single cell** (e.g. `B1`) | `CalcRange` shape `(1, 1)` — use `data.values[0][0]` or `float(np.asarray(data))` | `data.values[0][0] * 2` |
| **Row** (e.g. `B1:D1`) | `CalcRange` shape `(1, N)` | `np.mean(data)` (via `__array__`) |
| **Column** (e.g. `B1:B10`) | `CalcRange` shape `(N, 1)` | `np.mean(data)` |
| **2D rectangle** (e.g. `B1:C5`) | `CalcRange` shape `(rows, cols)` | `data.to_pandas()` or `data.to_numpy()` |

**API (explicit conversions)** — when `data` is a single `CalcRange`:

```python
data.values                          # exact list[list] (None for blanks)
data.to_numpy()                      # ndarray (None → nan for numeric dtype)
data.to_pandas()                     # header_row=0 by default
data.to_pandas(header_row=None)      # all rows are data; columns col_0…
data.to_pandas(parse_strings=True)   # opt-in currency/percent/date string parsing
ranges                               # always list[CalcRange]; len 1 when one formula arg
```

Returning a **pandas DataFrame** spills/writes with its **column header row** included. Returning a list/ndarray writes values only.

Payload size cap: `scripting.python_max_data_cells` ([serialization config](numpy-serialization.md#subprocess-module-map-and-config)). Host↔venv pipeline: [Current pipeline](numpy-serialization.md#current-pipeline-and-costs).

**Gaps vs LibrePythonista (workarounds):** chat tool still single `data_range` (use multiple `=PY` cells or formula varargs); no `collapse` (tighter range or strip `None` in Python); DataFrame conversion is explicit via `data.to_pandas()` (not automatic).

---

## Multi-range support (varargs) {#multi-range-support-varargs}

**Status:** Shipped. `ranges` is always a `list[CalcRange]`. `data` is **polymorphic**: one formula arg → that `CalcRange`; two or more → the same list object as `ranges` (`data is ranges`). Wire envelope: [Multi-range wire format](numpy-serialization.md#multi-range-wire-format). Chat-tool multi `data_range` remains future work.

`=PY()` accepts **one or more** optional data arguments after `code`. Calc packs trailing arguments into a single `sequence<any>` (UNO varargs).

**IDL (shipped):**

```idl
// extension/idl/XPythonFunction.idl
interface XPythonFunction : com::sun::star::uno::XInterface
{
    any python( [in] string code, [in] sequence< any > data );
};
```

Rebuild after IDL changes: `scripts/rebuild_xprompt_rdb.sh` → [`extension/XPythonFunction.rdb`](../extension/XPythonFunction.rdb).

| Formula | `data` | `ranges` |
| --- | --- | --- |
| `=PY("…"; A1:A5)` | `CalcRange` for `A1:A5` | `[data]` |
| `=PY("…"; A1:A5; C1:C5)` | same list as `ranges` | `[range0, range1]` |

**Example — weighted average across regions** (multi-arg: index with `data[i]` or loop `ranges`):

```text
=PY("result = (np.mean(data[0]) + np.mean(data[1])*2 + np.mean(data[2])) / 4"; A1:A10; C1:C10; E1:E10)
```

```python
result = float(np.mean([np.mean(r) for r in ranges]))
```

Under multi-arg, prefer `data[i]` / `ranges[i]` for a single binding — do **not** use bare `data.to_pandas()` (that is for the one-arg `CalcRange` case). On a single `CalcRange`, `data[i]` means **row** `i`, not another formula argument.

---

## Empty cells vs NaN {#empty-cells-vs-nan}

### Locked decision (shipped)

- **No wire-format change** for blank vs NaN provenance. Empty Calc cells and Python/NumPy NaN both use NaN slots in the `split_grid` float64 buffer (or `None` in small/mixed list results).
- **Egress:** every computed `nan` becomes a real Calc error that **cascades** (`#NUM!` / `#VALUE!`). Python `None` maps to an empty cell (`""`).
- **Accepted tradeoff:** a Calc blank that flows through a pure-numeric path becomes `np.nan` in the worker; if you return that NaN, the sheet shows an error (not a silent blank). Matches the spreadsheet model where a missing numeric value taints dependents.
- Production transport: length-prefixed **Pickle5** + `split_grid` (or nested lists below threshold). No JSON on the runtime wire.

Microsoft Python in Excel also collapses empty → `NaN` on ingress and renders computed `np.nan` as `#NUM!` ([microsoft/python-in-excel#38](https://github.com/microsoft/python-in-excel/issues/38)). We match that with an egress-only fix (`to_calc_compatible` no longer collapses NaN → `""`).

### Ingress (Calc → Python)

| Grid type in the venv | Empty Calc cell becomes | Notes |
| --- | --- | --- |
| **Mixed** (any text in range) | `None` in `list` / `list[list]` (inside `CalcRange.values`) | Same as small-list path |
| **Pure numeric** (≥100 cells, split_grid) | `np.nan` when using `data.to_numpy()` / `__array__` | Use `np.nansum`, `np.nanmean`, or `np.isnan` |
| **Small range** (<100 cells, nested list) | `None` in `.values` | May promote to ndarray only if reloaded as clean numeric |

Ingress blanks can poison naive `np.sum` / `np.mean` — prefer `nan*` helpers when blanks should be ignored.

### Egress (Python → Calc)

- Python `None` → `""` (empty cell).
- `float('nan')` / `np.nan` → raw NaN → cascading error cell.
- `±inf` passes through (may also error in formulas).
- For a visible non-error marker, return a string:

```python
val = np.mean(data)
result = "NaN" if (isinstance(val, float) and math.isnan(val)) else val
```

```python
# Ingress
result = np.nansum(data)          # ignores blanks/NaNs
result = np.sum(data)             # poisons on blanks/NaN (returns NaN)

# Egress
result = None                     # empty cell
result = float("nan")             # #NUM! / #VALUE! (cascades)
result = [[1.0, np.nan, 3.0]]     # 1, error, 3
```

**We do not round-trip "real NaN" as a special visible sentinel.** `±inf` is never coerced to empty.

### Author / LLM summary

- Blanks on ingress are `np.nan` in numeric arrays — use `np.nansum` / `np.nanmean` when you mean "ignore missing."
- A computed `nan` is a sheet error and poisons dependents. Return a string for a quiet marker.
- `None` is the way to produce a true empty cell on egress.
- Shared helper: `is_missing_value` in [`plugin/scripting/venv/coerce.py`](../plugin/scripting/venv/coerce.py) (None, `""`, LO error tokens, float/NumPy NaN) — used by dataframe coercion and Excel-parity formula helpers.

Codec details: [numpy-serialization — Split-Grid encoding](numpy-serialization.md#strategy-3-split-grid-serialization-detail).

---

## Cell types and logicals {#cell-types-and-logicals}

What Python sees after UNO unwrap / pack ([`calc_addin_data.py`](../plugin/calc/calc_addin_data.py)):

| Calc / UNO | In `CalcRange.values` (before NumPy conversion) |
| --- | --- |
| Empty cell / `""` | `None` |
| Number | `int` or `float` |
| Logical constant (`TRUE`/`FALSE` in sheet) | Usually **`1.0`/`0.0`** from the add-in bridge (VALUE cells) |
| UNO boolean (rare on range args) | `bool` |
| Text | `str` (including literal `"True"` until string-logical coercion) |

**Logical string coercion (shipped):** text that looks like a logical or formula after import/paste (`"TRUE"`, `"=WAHR()"`, `"True"`, plus localized names from `XFormulaOpCodeMapper`) is coerced to Python `bool` in `_unwrap_cell` before packing. Typed Calc logicals that arrive as `1.0`/`0.0` are left numeric.

| What the user sees | Typical Python value |
| --- | --- |
| Logical typed in Calc | `1.0` / `0.0` |
| Formula / plain / Python-style text logicals | `True` / `False` (after coercion) |

**Egress:** Python `True` / `False` map to UNO booleans in `to_calc_compatible`. `=PY("True")` should display a **logical** TRUE, not the text `"True"`.

---

## Dates and datetimes {#dates-and-datetimes}

Calc stores dates as float serials (days since `1899-12-30`). Detecting “is this a date?” requires per-cell `NumberFormat` on the main thread — too slow for range reads — so the bridge **does not** auto-coerce on ingress.

- **Ingress:** serials arrive as floats (or strings if stored as text).
- **User coercion:**
  - Float serials: `pd.to_datetime(df["date_col"], unit="D", origin="1899-12-30")`
  - String dates: `pd.to_datetime(df["date_col"])`
- **Text stays text** by default (`"00123"` remains a string). Opt in with `to_pandas(parse_strings=True)`.

Wire note (large grids): above the `split_grid` threshold, Python `datetime` / `Timestamp` values become ISO strings in the sparse `strings` map — see [Dates on the wire](numpy-serialization.md#dates-on-the-wire).

---

## Rectangular shape rules {#rectangular-shape-rules}

- **2D data must be rectangular:** every row the same length. Calc range args always arrive that way; empty cells are `None` in a full-width row, not missing list elements.
- **Jagged nested lists** (tool/LLM payloads) are **unsupported** at pack time: [`_flatten_grid_to_components`](../plugin/scripting/payload_codec.py) raises `ValueError`. We do not pad short rows on the wire path.
- Orientation is preserved via `ensure_rectangular_2d`: a single row stays `[[a, b, c]]`; a single column stays `[[a], [b], [c]]`; a scalar becomes `[[v]]`. User scripts see this as `CalcRange.shape`, not a flat 1D list.

---

## Deferred upgrades {#deferred-upgrades}

Not planned unless needed:

- Blank side-channel on `split_grid` + masked-array ingress so pass-through blanks stay empty and `np.mean` auto-ignores Calc blanks (upgrade can be atomic; wire already carries NaN slots).
- Formula parameters: 3rd arg `extras` for recalc deps; `collapse` on conversion; host `lp()` bridge; per-formula `timeout_sec`.
- Range alignment helper for mismatched multi-range shapes before `np.corrcoef` / element-wise math — see [Calc UX backlog](enabling_numpy_in_libreoffice.md#calc-ux-backlog).
