# Date and Time Lifecycle in LibreOffice Calc

**Architecture, Storage Model, Serialization & Tool Integration Specification**

This document describes how WriterAgent handles date, time, and datetime values across their lifecycle in LibreOffice Calc: PyUNO storage, read-path format enrichment, MCP/system prompt context injection, and write-path string-to-serial conversion with number-format preservation.

---

## 1. Context & Problem Statement

### 1.1 The Calc Date/Time Storage Model
In LibreOffice Calc (and the ISO/IEC 29500 / OpenDocument Spreadsheet standards), **dates, times, and datetimes do not exist as distinct primitive cell data types**.

Instead:
1. **Cell Content Type**: All date and time cells have `com.sun.star.table.CellContentType.VALUE` (numeric double).
2. **Epoch Serial Representation**: Dates are stored as floating-point day counts relative to a document epoch (`NullDate`, standard LibreOffice default: `1899-12-30 00:00:00`).
   - `46239.0` represents `2026-08-05`.
   - `0.3333333333333333` represents `08:00:00` (8 hours / 24 hours).
   - `46240.5` represents `2026-08-06 12:00:00`.
3. **Display Formatting**: The visual presentation (e.g. `2026-08-05` vs `08/05/2026` vs `46239`) is controlled entirely by the cell's `NumberFormat` property key referencing the document's `XNumberFormats` registry.

### 1.2 The LLM Friction Points
- **Read Path Friction**: When an LLM reads a spreadsheet via raw `read_cell_range`, receiving `value: 46239.0` without context leaves the model unable to determine if the cell represents currency, a raw quantity, or a date.
- **Write Path Friction**: When an LLM generates data to write (e.g. `["2026-08-08", "08:00"]`), standard string assignment puts literal text (`com.sun.star.table.CellContentType.TEXT`) into the cell. This breaks spreadsheet formulas (e.g. `=A26+1`), numeric sorting, and native Calc filtering.

---

## 2. Complete 3-Phase Lifecycle Architecture

The end-to-end date/time architecture consists of three synchronized phases:

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                           1. MCP & PROMPT CONTEXT                              │
│  Injects local clock & timezone into initialization instructions + tool schemas│
└───────────────────────┬────────────────────────────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                           2. READ PATH ENRICHMENT                              │
│  detects NumberFormat category ──► converts serial double ──► outputs iso8601   │
└───────────────────────┬────────────────────────────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                           3. WRITE PATH INGESTION                              │
│  parses ISO string ──► computes serial double ──► sets NumberFormat if needed  │
└────────────────────────────────────────────────────────────────────────────────┘
```

**Implementation status:**
- Phase 1 (MCP clock) and Phase 2 (read enrichment with `iso8601` + `format_category`) are **implemented**.
- Phase 3 (write ISO → serial + NumberFormat) is **planned, not yet in code**.
- Symmetric LLM read (`value` = ISO string) is a **future follow-up** (§3.2); ship write against today's read shape first.

---

## 3. Phase 1: Read Path (Inspection & Serialization)

*Status: Implemented in commit [`2650d3b`](https://github.com/KeithCu/writeragent/commit/2650d3bbc39f2c3ab29102d8d50208ea1e817656)*

### 3.1 Mechanism
When `read_cell_range` is invoked with `include_format_info=True` (enabled by default for LLM tool invocations):

1. **Pre-flight Check**: To prevent performance degradation on large datasets, `CellInspector._range_format_rows()` scans the range for cell formats. If no date/time formats or formulas exist in the target block, format inspection returns early.
2. **Format Grouping**: Queries `cell_range.getUniqueCellFormatRanges()` to group contiguous cells sharing identical number formats. This reduces UNO RPC round-trips from $O(N \times M)$ per-cell queries to $O(K)$ format group queries.
3. **Format Classification**: Evaluates `com.sun.star.util.XNumberFormats.getByKey(format_id).Type`:
   - `NUMBER_FORMAT_DATE` $\rightarrow$ `"date"`
   - `NUMBER_FORMAT_TIME` $\rightarrow$ `"time"`
   - `NUMBER_FORMAT_DATE | NUMBER_FORMAT_TIME` $\rightarrow$ `"datetime"`
4. **Serial to ISO-8601 Translation**:
   Reads `NullDate` from `doc.getNumberFormatSettings().getPropertyValue("NullDate")` and computes:
   $$\text{timestamp} = \text{NullDate} + \text{timedelta}(\text{seconds} = \text{round}(\text{serial\_value} \times 86400))$$
   Outputs formatted ISO string (`iso8601`) and `format_category`. Helpers live in `plugin/calc/inspector.py` today; write work should move the shared serial math into `plugin/calc/datetime_serial.py` (§5.2).

### 3.2 Current Wire Shape vs Future Symmetry

#### Current design (shipped; matches UNO tests)
`read_cell_range` returns the raw Calc serial double as `value` and appends `iso8601` + `format_category`:

```json
{
  "address": "A20",
  "value": 46239.0,
  "formula": null,
  "type": "value",
  "iso8601": "2026-08-05",
  "format_category": "date"
}
```

Internal callers use `CellInspector.read_range(include_format_info=False)` and get un-enriched raw float serials (NumPy, `=PY`, analysis).

#### Future symmetry (not implemented — do after write path)
Returning `value: 46239.0` reflects `CellContentType.VALUE` but creates LLM friction:
1. **Transformation loops**: read → edit → write often reuses `row["value"]`, so serials bounce back into `write_formula_range`.
2. **Model reasoning**: LLMs prefer ISO strings (`"2026-08-05"`) and must reconcile `value` vs `iso8601`.

A later change can put ISO in `value` and set `type` to `"date"` / `"time"` / `"datetime"`, omitting the raw serial from the LLM payload:

```json
[
  {
    "address": "A20",
    "value": "2026-08-05",
    "formula": null,
    "type": "date",
    "format_category": "date"
  },
  {
    "address": "B20",
    "value": "08:00:00",
    "formula": null,
    "type": "time",
    "format_category": "time"
  }
]
```

Until then, **write accepts ISO strings** while **read still exposes serial + `iso8601`**. Do not flip the read shape in the same change as the write path.

> **Invariant**: Internal PyUNO / analysis callers (`include_format_info=False`) remain un-enriched for NumPy and computational pipelines.

---

## 4. Phase 2: Prompting & Context Injection

### 4.1 Connection-Time Clock Context
`plugin/mcp/mcp_protocol.py` injects current local clock context into MCP system instructions:
```python
def _format_mcp_clock_context(now: datetime.datetime | None = None) -> str:
    local_now = now.astimezone() if now is not None else datetime.datetime.now().astimezone()
    timezone_name = local_now.tzname()
    timezone_suffix = f" ({timezone_name})" if timezone_name else ""
    return f"Current local date and time: {local_now.strftime('%A')}, {local_now.isoformat(timespec='seconds')}{timezone_suffix}."
```
Example string prepended to system instructions:
`Current local date and time: Thursday, 2026-08-07T11:04:25-04:00 (EDT).`

Calc serials are timezone-less. When parsing write inputs, accept optional trailing `Z` or `±HH:MM` and **strip to naive wall time** (no zone conversion). Do not reject timezone suffixes — that increases TEXT fallbacks when models copy the MCP clock.

### 4.2 Tool Schema Definitions
- **`ReadCellRange`** (`read_cell_range` in `plugin/calc/cells.py`): already documents `iso8601` / `format_category`.
- **`WriteCellRange`** (`write_formula_range`): **does not yet** mention ISO dates. When implementing Phase 3, update its description so LLMs emit ISO 8601 date/time/datetime strings (formulas still use `=`).

Do not broaden write parsing to locale display forms (`08/05/2026`, `5.8.2026`); the wire contract stays ISO-shaped only.

---

## 5. Phase 3: Write Path (Parsing, Serial Conversion & Formatting)

*Implementation plan — not yet in code*

### 5.1 Architecture & Design Requirements

When writing via `CellManipulator.write_formula_range` or `write_formula`:
1. **String Parsing**: When a written element is a string (and does not start with `"="` for formulas), attempt ISO 8601 parsing (with optional TZ strip) before falling back to `float()` or literal text.
2. **Serial Calculation**: Compute double float value relative to `NullDate` from `doc.getNumberFormatSettings()` (same source as the read path).
3. **Format Application**:
   - If the destination cell already has **any** Date, Time, or Datetime `NumberFormat`, **preserve** that format key (even if the written subtype differs, e.g. date string into a datetime-formatted cell).
   - If the destination cell has General/Text/plain numeric format, apply a locale-safe default via `getFormatIndex` / composed FormatString (§6) — never hardcode ASCII `"YYYY-MM-DD"` into `queryKey()`.
4. **Batch Execution**: Prefer `cell_range.setDataArray()` for values. See §5.3 for the mixed formula hole.
5. **Single-cell path**: Mirror the same parse + `setValue` + format logic in `write_formula`, not only `write_formula_range`.

### 5.2 Shared Helper Module (`plugin/calc/datetime_serial.py`)

Put parse and format-inverse next to each other so NullDate epoch math and second-rounding stay shared. Today `_iso8601_from_serial` lives in `plugin/calc/inspector.py`; move (or re-export) it with `_parse_datetime_string` into `plugin/calc/datetime_serial.py`. `manipulator.py` and `inspector.py` both import from there.

#### ISO Regular Expressions
Keep ISO-shaped patterns only. Fast prefilter before regex:

```python
if not any(c in val for c in ("-", ":", "/")):
    return None  # Skip regexes for plain text, numbers, and prose
```

```python
_DATE_RE = re.compile(r"^(\d{4})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d)(?:\.(\d+))?)?$")
_DATETIME_RE = re.compile(
    r"^(\d{4})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])[T ]"
    r"([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d)(?:\.(\d+))?)?"
    r"(?:Z|[+-]\d{2}:?\d{2})?$"
)
```

Optional `Z` / offset on datetime (and similarly on bare dates if needed) is stripped; treat the remaining wall clock as naive.

#### Parsing & Serial Conversion Logic
```python
def _parse_datetime_string(val_str: str, null_date=None) -> tuple[float, str] | None:
    """Parse an ISO 8601 date, time, or datetime string.

    Returns:
        tuple of (serial_float, format_category) or None if unparseable.
        format_category is \"date\", \"time\", or \"datetime\".
    """
    # 1. strip + fast char guard
    # 2. strip optional trailing Z / ±HH:MM (no zone conversion)
    # 3. match DATE, then DATETIME, then TIME (same NullDate epoch as _iso8601_from_serial)
    # 4. invalid calendar dates (e.g. 2026-02-30) → None
    ...
```

Default NumberFormat keys are resolved separately via `NumberFormatIndex` (§6), not by returning ASCII format pattern strings from the parser.

### 5.3 Execution Workflow in `CellManipulator.write_formula_range`

**Critical:** today's code, when any cell in the range is a formula, commits the **entire** range via `setFormulaArray` of stringified inputs and **ignores** `data_array`. Parsing ISO into serials is useless for mixed ranges unless the commit path is fixed.

1. **Retrieve Document Settings**:
   `null_date = doc.getNumberFormatSettings().getPropertyValue("NullDate")` once per invocation. Also fetch `CharLocale` once for format resolution.
2. **Build Data Array + Formula Overlay List**:
   For each input:
   - `startswith("=")` → leave data cell empty; record formula for overlay.
   - else `_parse_datetime_string(...)` → put `serial_float` in `data_array`; mark cell for format pass if needed.
   - else `float()` → number; else TEXT string.
3. **Commit Values First**:
   `cell_range.setDataArray(tuple(data_array))` always (serials / numbers / text; formula cells empty).
4. **Overlay Formulas**:
   For each recorded formula cell, `setFormula` (or a formula-only pass). Do **not** send ISO date strings through `setFormulaArray`.
5. **Apply Format Adjustments (blocked)**:
   - Prefer one `getUniqueCellFormatRanges()` (or a category mask built while parsing) to skip cells already in date/time/datetime.
   - Coalesce remaining cells that need a default into contiguous blocks; apply `NumberFormat` per block — never per-cell `setPropertyValue` inside a tight loop.
   - Resolve default keys once per category via §6 and cache in a Python `dict` for the invocation.

### 5.4 Write-Path Performance & Optimization Rules

1. **Fast String Pre-filtering**: $O(1)$ char guard before regex (§5.2).
2. **Range / Block `NumberFormat`**: Never set NumberFormat per cell in a loop. Homogeneous ranges → one range set. Sparse mixed grids → coalesce contiguous same-category blocks ($O(\text{blocks})$ IPC, not a hard $\le 6$ for every sparse layout).
3. **Format Key Caching**: Cache resolved keys per category (`date` / `time` / `datetime`) for the write invocation (and optionally per document session).

Typical homogeneous write stays at a handful of UNO calls (`NullDate`, `CharLocale`, $\le 3$ format resolutions, `setDataArray`, one format set). Sparse mixed grids scale with block count.

### 5.5 Follow-ups (out of scope for the first write PR)

- Symmetric LLM read (`value` = ISO) — §3.2 future.
- Locale-display write parsing.
- Fixing existing `set_style` / `_set_number_format` ASCII `queryKey("YYYY-MM-DD", …)` (same locale-letter bug; prefer `getFormatIndex` / FormatString there too).
- Changing NumPy / `include_format_info=False` raw serial behavior.

---

## 6. Multi-Locale Generalization (34+ System Locales)

### 6.1 The 34-Locale Format String Challenge
LibreOffice is localized across **34+ language locales** (e.g. English `en-US`, German `de-DE`, French `fr-FR`, Spanish `es-ES`, Japanese `ja-JP`, Finnish `fi-FI`, Dutch `nl-NL`).

In non-English locales, passing raw ASCII format codes like `"YYYY-MM-DD"` directly to `XNumberFormats.queryKey()` can fail because date format letters are localized:
- **German (`de-DE`)**: Year = `J` (Jahr), Day = `T` (Tag) $\rightarrow$ `"JJJJ-MM-TT"`
- **French (`fr-FR`)**: Year = `A` (Année), Day = `J` (Jour) $\rightarrow$ `"AAAA-MM-JJ"`
- **Finnish (`fi-FI`)**: Year = `V` (Vuosi), Day = `P` (Päivä) $\rightarrow$ `"VVVV-KK-PP"`

Hardcoding `"YYYY-MM-DD"` inside `queryKey()` on a German or French LibreOffice installation returns `-1` or registers a corrupt custom format string.

### 6.2 Correct `NumberFormatIndex` Constants

LibreOffice UNO does **not** define `DATE_ISO` or `DATETIME_SYSTEM_SHORT_HHMMSS`. Use the real [`NumberFormatIndex`](https://api.libreoffice.org/docs/idl/ref/namespacecom_1_1sun_1_1star_1_1i18n_1_1NumberFormatIndex.html) values:

| Category | Constant | Notes |
| :--- | :--- | :--- |
| date | `DATE_DIN_YYYYMMDD` | DIN/EN/ISO `1997-10-08` (formatindex 33) — closest built-in ISO date |
| time | `TIME_HHMMSS` | `HH:MM:SS` |
| datetime | *(composed)* | No ISO datetime index exists. `DATETIME_SYSTEM_SHORT_HHMM` / `DATETIME_SYS_DDMMYYYY_HHMMSS` are **locale short** forms, not ISO — do not use them for the ISO wire display default |

```python
from com.sun.star.i18n.NumberFormatIndex import (
    DATE_DIN_YYYYMMDD,
    TIME_HHMMSS,
)

doc = self.bridge.get_active_document()
formats = doc.getNumberFormats()
locale = doc.getPropertyValue("CharLocale")

date_key = formats.getFormatIndex(DATE_DIN_YYYYMMDD, locale)
time_key = formats.getFormatIndex(TIME_HHMMSS, locale)

# Datetime: locale-letter-safe compose from the two built-ins' FormatString,
# then queryKey / addNew once and cache.
date_fmt = formats.getByKey(date_key).FormatString
time_fmt = formats.getByKey(time_key).FormatString
datetime_pattern = f"{date_fmt} {time_fmt}"
datetime_key = formats.queryKey(datetime_pattern, locale, False)
if datetime_key == -1:
    datetime_key = formats.addNew(datetime_pattern, locale)
```

Never pass ASCII `"YYYY-MM-DD"` into `queryKey` / `addNew` for defaults. Built-in `getFormatIndex` keys already carry the correct localized format letters; composing datetime from those FormatStrings stays safe across locales.

### 6.3 Universal ISO 8601 Wire Contract Across Locales
1. **Read Path**: `_iso8601_from_serial()` translates serial doubles to ISO 8601 strings (`YYYY-MM-DD`, `HH:MM:SS`, `YYYY-MM-DDTHH:MM:SS`), locale-independent.
2. **Write Path**: `_parse_datetime_string()` parses ISO 8601 (optional TZ stripped) into day serials in Python.
3. **Display Formatting**: `DATE_DIN_YYYYMMDD` / `TIME_HHMMSS` / composed datetime FormatString for defaults when the cell has no date/time format yet.

### 6.4 Performance & Call Frequency Analysis for Locale APIs

During a typical homogeneous `write_formula_range` invocation:

| UNO API Method | Frequency | Optimization Strategy |
| :--- | :--- | :--- |
| `NullDate` via `getNumberFormatSettings()` | Once per write | Retrieved once per batch |
| `CharLocale` | Once per write | Retrieved once per batch |
| `getFormatIndex` / composed datetime `queryKey` | Once per category used ($\le 3$) | Cached in `format_key_cache[category]` |
| `cell_range.setDataArray(...)` | Once | Bulk 2D grid write |
| Formula overlay | Per formula cell (or batched) | Only when the range mixes formulas |
| `setPropertyValue("NumberFormat", key)` | Once per contiguous block needing a default | Skip cells that already have date/time/datetime formats |

Homogeneous ranges stay near a small constant IPC count. Sparse mixed grids are $O(\text{blocks})$ for format sets — still independent of total cell count for `setDataArray`.

---

## 7. Testing Strategy & Verification Plan

### 7.1 Unit Tests (`tests/calc/test_cells.py`)
- Test `_parse_datetime_string` with varied ISO inputs:
  - Valid dates (`2026-08-08`, `2026/08/08`)
  - Valid times (`08:00`, `08:00:00`, `14:30:45.500`)
  - Valid datetimes (`2026-08-08T08:00:00`, `2026-08-08 08:00:00`)
  - Timezone / `Z` stripped to naive (`2026-08-08T08:00:00-04:00`, `…Z`)
  - Invalid calendar dates (`2026-02-30`, `2026-13-45`) $\rightarrow$ returns `None`
  - Non-date strings (`"Hello World"`, `"=SUM(A1:A10)"`) $\rightarrow$ returns `None`
  - NullDate ≠ default epoch (serial math matches `_iso8601_from_serial`)

### 7.2 Native UNO Integration Tests (`tests/calc/test_cells_uno.py`)
End-to-end write and readback against the **current** read shape (serial `value` + `iso8601`), not the future symmetric shape:

```python
@native_test
def test_write_and_read_date_time_cells():
    res = _execute_calc_tool("write_formula_range", {
        "range_name": ["A26:B26"],
        "formula_or_values": "[\"2026-08-08\", \"08:00\"]",
    })
    assert res.get("status") == "ok"

    read_res = _execute_calc_tool("read_cell_range", {"range_name": ["A26:B26"]})
    row = read_res["result"][0][0]

    assert row[0]["iso8601"] == "2026-08-08"
    assert row[0]["format_category"] == "date"
    assert isinstance(row[0]["value"], (int, float))

    assert row[1]["iso8601"] == "08:00:00"
    assert row[1]["format_category"] == "time"
```

Also cover:
- Mixed range: ISO date + formula in one `write_formula_range` (proves two-step commit).
- Preserve existing NumberFormat when overwriting a date-formatted cell.
- `write_formula` single-cell date.
- Non-default `NullDate` round-trip when practical in UNO tests.

---

## 8. Related Documents

- [Calc Specialized Toolsets](calc-specialized-toolsets.md) — Tool delegation, tiers, and Calc domain status.
- [MCP Protocol & Invariants](mcp-protocol.md) — Model Context Protocol instructions and clock context formatting.
- [NumPy & Python Venv Bridge](enabling_numpy_in_libreoffice.md) — Raw numeric serialization for analytical pipelines.
