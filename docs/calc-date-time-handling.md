# Date and Time Lifecycle in LibreOffice Calc

**Architecture, Storage Model, Serialization & Tool Integration Specification**

This document provides a comprehensive technical plan for senior developers on how WriterAgent handles date, time, and datetime values across their entire lifecycle in LibreOffice Calc. It details the underlying PyUNO storage mechanics, read-path format enrichment, MCP/system prompt context injection, and write-path string-to-serial conversion with number-format preservation.

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
   Reads `NullDate` struct (`Year`, `Month`, `Day`) from document settings and computes:
   $$\text{timestamp} = \text{NullDate} + \text{timedelta}(\text{seconds} = \text{round}(\text{serial\_value} \times 86400))$$
   Outputs formatted ISO string (`iso8601`) and `format_category`.

### 3.2 Read/Write Symmetry Evolution

#### Initial Design (Commit `2650d3b`)
In commit [`2650d3b`](https://github.com/KeithCu/writeragent/commit/2650d3bbc39f2c3ab29102d8d50208ea1e817656), the read path returned the raw Calc serial double as `value` and appended an extra `iso8601` field:
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

#### Why We Changed to Symmetric Read/Write
While returning `value: 46239.0` reflected the underlying PyUNO `CellContentType.VALUE`, it introduced **asymmetric friction for LLMs**:
1. **Transformation Loops**: In common tool workflows (e.g. read table $\rightarrow$ filter/edit $\rightarrow$ write back), an LLM would naturally extract `row["value"]` and pass `46239.0` back into `write_formula_range`.
2. **Model Reasoning**: LLMs operate natively on ISO 8601 strings (`"2026-08-05"`). Having `value` be a serial double forced the model to reconcile `value` vs `iso8601`.

#### Symmetric Design Specification
To achieve **100% read/write symmetry**, `read_cell_range` returns the ISO 8601 string directly as `value` and updates `type` to `"date"`, `"time"`, or `"datetime"`.

The raw float serial (e.g. `46239.0`) is **omitted from the LLM payload** to reduce token overhead, prevent context clutter, and eliminate model confusion between serial numbers and price/quantity metrics.

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

With this design:
- **Read Path**: `read_cell_range` returns `"value": "2026-08-05"`.
- **Write Path**: `write_formula_range` accepts `"value": "2026-08-05"`.
- **Token Efficiency**: Omitting `raw_value` keeps JSON responses lean and clutter-free.
- **Internal Python Tools**: NumPy, `=PY`, and analytical pipelines call `CellInspector.read_range(include_format_info=False)` which returns un-enriched raw float serials directly.

> **Invariant**: Internal PyUNO / analysis callers (`CellInspector.read_range(include_format_info=False)`) remain un-enriched to preserve raw numerical performance for NumPy and internal computational pipelines.

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

### 4.2 Tool Schema Definitions
`WriteCellRange` (`write_formula_range` in `plugin/calc/cells.py`) and `ReadCellRange` (`read_cell_range`) explicitly detail date/time support in their parameter descriptions so LLMs reliably output ISO 8601 strings when writing cell data.

---

## 5. Phase 3: Write Path (Parsing, Serial Conversion & Formatting)

*Implementation Plan for Senior Developers*

### 5.1 Architecture & Design Requirements

When writing via `CellManipulator.write_formula_range` or `write_formula`:
1. **String Parsing**: When a written element is a string (and does not start with `"="` for formulas), attempt ISO 8601 parsing before falling back to `float()` or literal text.
2. **Serial Calculation**: Compute double float value relative to `NullDate`.
3. **Format Application**:
   - If the destination cell already has a Date, Time, or Datetime `NumberFormat`, preserve its format key.
   - If the destination cell has General/Text format, apply the corresponding default format string:
     - Date: `"YYYY-MM-DD"`
     - Time: `"HH:MM:SS"`
     - Datetime: `"YYYY-MM-DD HH:MM:SS"`
4. **Batch Execution**: Maintain fast $O(1)$ batch write performance using `cell_range.setDataArray()`.

### 5.2 Helper Module Specification (`plugin/calc/manipulator.py`)

#### ISO Regular Expressions
```python
_DATE_RE = re.compile(r"^(\d{4})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d)(?:\.(\d+))?)?$")
_DATETIME_RE = re.compile(r"^(\d{4})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])[T ]([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d)(?:\.(\d+))?)?$")
```

#### Parsing & Serial Conversion Logic
```python
def _parse_datetime_string(val_str: str, null_date=None) -> tuple[float, str, str] | None:
    """Parse an ISO 8601 date, time, or datetime string.

    Returns:
        tuple of (serial_float, format_category, format_pattern) or None if unparseable.
    """
    if not isinstance(val_str, str) or not val_str.strip():
        return None
    
    val = val_str.strip()
    
    # NullDate default: 1899-12-30
    null_y = int(null_date.Year) if null_date else 1899
    null_m = int(null_date.Month) if null_date else 12
    null_d = int(null_date.Day) if null_date else 30
    epoch_base = datetime.datetime(null_y, null_m, null_d)

    # 1. Date check
    m_date = _DATE_RE.match(val)
    if m_date:
        try:
            dt = datetime.datetime(int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3)))
            serial = float((dt - epoch_base).days)
            return (serial, "date", "YYYY-MM-DD")
        except ValueError:
            return None

    # 2. Datetime check
    m_dt = _DATETIME_RE.match(val)
    if m_dt:
        try:
            sec = int(m_dt.group(6)) if m_dt.group(6) else 0
            usec = int(m_dt.group(7).ljust(6, "0")[:6]) if m_dt.group(7) else 0
            dt = datetime.datetime(
                int(m_dt.group(1)), int(m_dt.group(2)), int(m_dt.group(3)),
                int(m_dt.group(4)), int(m_dt.group(5)), sec, usec
            )
            delta = dt - epoch_base
            serial = delta.total_seconds() / 86400.0
            return (serial, "datetime", "YYYY-MM-DD HH:MM:SS")
        except ValueError:
            return None

    # 3. Time check
    m_time = _TIME_RE.match(val)
    if m_time:
        try:
            hr, mn = int(m_time.group(1)), int(m_time.group(2))
            sec = int(m_time.group(3)) if m_time.group(3) else 0
            usec = int(m_time.group(4).ljust(6, "0")[:6]) if m_time.group(4) else 0
            total_sec = hr * 3600 + mn * 60 + sec + usec / 1e6
            serial = total_sec / 86400.0
            return (serial, "time", "HH:MM:SS")
        except ValueError:
            return None

    return None
```

### 5.3 Execution Workflow in `CellManipulator.write_formula_range`

1. **Retrieve Document Settings**:
   Fetch `NullDate` from active document settings via PyUNO bridge.
2. **Build Data Array**:
   Iterate over input values. For string inputs:
   - Check if formula (`value.startswith("=")`).
   - Attempt `_parse_datetime_string(value, null_date)`.
   - If matched: record `serial_float` into `data_row`, and track formatting requirement for cell `(col, row)`.
   - If not matched: attempt `float()`, fallback to string text.
3. **Commit Bulk Data**:
   Call `cell_range.setDataArray(tuple(data_array))`.
4. **Apply Format Adjustments**:
   For cells identified as date/time/datetime:
   - Query existing `NumberFormat` property.
   - If existing format category is not date/time, query/add format string (`YYYY-MM-DD`, `HH:MM:SS`, `YYYY-MM-DD HH:MM:SS`) using `doc.getNumberFormats()` and set `cell.setPropertyValue("NumberFormat", format_id)`.

### 5.4 Write-Path Performance & Optimization Rules

To guarantee high throughput on bulk dataset writes (e.g. 10,000 cells written in < 15 ms), senior developers MUST enforce the following three performance invariants:

1. **Fast String Pre-filtering**:
   Before running full regex matches in `_parse_datetime_string()`, execute a fast $O(1)$ character guard check:
   ```python
   if not any(c in val for c in ("-", ":", "/")):
       return None  # Skip regexes instantly for plain text, numbers, and prose
   ```
2. **Range-Level `NumberFormat` Ingestion (Zero Per-Cell UNO RPCs)**:
   - **NEVER** call `cell.setPropertyValue("NumberFormat", format_id)` inside a per-cell loop.
   - If an entire range or column contains dates, apply `cell_range.setPropertyValue("NumberFormat", format_id)` **once to the range** ($O(1)$ IPC calls).
   - For mixed ranges, group contiguous date cells into range blocks (e.g. `A2:A50`) and apply `NumberFormat` per block.
3. **Format Key Session Caching**:
   - Cache resolved `NumberFormat` IDs in a Python dictionary (`{"YYYY-MM-DD": format_id, "HH:MM:SS": format_id}`) per document session to eliminate redundant `formats.queryKey()` / `formats.addNew()` bridge calls.

---

## 6. Multi-Locale Generalization (34+ System Locales)

### 6.1 The 34-Locale Format String Challenge
LibreOffice is localized across **34+ language locales** (e.g. English `en-US`, German `de-DE`, French `fr-FR`, Spanish `es-ES`, Japanese `ja-JP`, Finnish `fi-FI`, Dutch `nl-NL`).

In non-English locales, passing raw ASCII format codes like `"YYYY-MM-DD"` directly to `XNumberFormats.queryKey()` can fail because date format letters are localized:
- **German (`de-DE`)**: Year = `J` (Jahr), Day = `T` (Tag) $\rightarrow$ `"JJJJ-MM-TT"`
- **French (`fr-FR`)**: Year = `A` (Année), Day = `J` (Jour) $\rightarrow$ `"AAAA-MM-JJ"`
- **Finnish (`fi-FI`)**: Year = `V` (Vuosi), Day = `P` (Päivä) $\rightarrow$ `"VVVV-KK-PP"`

Hardcoding `"YYYY-MM-DD"` inside `queryKey()` on a German or French LibreOffice installation returns `-1` or registers a corrupt custom format string.

### 6.2 The Native PyUNO Solution: `XNumberFormatTypes.getFormatIndex()`
LibreOffice UNO provides a built-in, locale-independent abstraction via the `com.sun.star.util.XNumberFormatTypes` interface (implemented directly on `doc.getNumberFormats()`) and `com.sun.star.i18n.NumberFormatIndex` constants.

Instead of translating format letters manually for 34 locales, PyUNO resolves the exact localized format key for **any locale** automatically:

```python
from com.sun.star.i18n.NumberFormatIndex import (
    DATE_ISO,                          # Standard ISO 8601 date (YYYY-MM-DD)
    TIME_HHMMSS,                       # Standard time (HH:MM:SS)
    DATETIME_SYSTEM_SHORT_HHMMSS,      # Standard datetime (YYYY-MM-DD HH:MM:SS)
    DATE_SYS_DDMMYYYY,                 # System short date for active locale
)

doc = self.bridge.get_active_document()
formats = doc.getNumberFormats()
locale = doc.getPropertyValue("CharLocale")

# Query localized format key natively across ANY of LibreOffice's 34+ locales:
iso_date_key = formats.getFormatIndex(DATE_ISO, locale)
time_key = formats.getFormatIndex(TIME_HHMMSS, locale)
datetime_key = formats.getFormatIndex(DATETIME_SYSTEM_SHORT_HHMMSS, locale)
```

### 6.3 Universal ISO 8601 Wire Contract Across Locales
1. **Read Path**: `_iso8601_from_serial()` translates serial doubles to ISO 8601 strings (`YYYY-MM-DD`, `HH:MM:SS`, `YYYY-MM-DDTHH:MM:SS`), which are 100% locale-independent.
2. **Write Path**: `_parse_datetime_string()` parses ISO 8601 strings into floating-point day serials in Python. ISO 8601 is language-agnostic across all 34 locales.
3. **Display Formatting**: `formats.getFormatIndex(DATE_ISO, locale)` resolves the correct native number format key for the document's active locale (whether `en-US`, `de-DE`, `fr-FR`, `ja-JP`, `zh-CN`, `es-ES`, etc.).

### 6.4 Performance & Call Frequency Analysis for Locale APIs

A core requirement for multi-locale support across WriterAgent's 34 locales is keeping PyUNO IPC round-trips to a minimum.

#### Call Frequency & Caching Accounting
During a `write_formula_range` invocation:

| UNO API Method | Frequency | Total Calls | Optimization Strategy |
| :--- | :--- | :--- | :--- |
| `NullDate` (`getPropertyValue("NullDate")`) | Once per write invocation | **1 call** | Retrieved once per batch invocation |
| `CharLocale` (`getPropertyValue("CharLocale")`) | Once per write invocation | **1 call** | Retrieved once per batch invocation |
| `getFormatIndex(NumberFormatIndex, locale)` | Once per format category used (`"date"`, `"time"`, `"datetime"`) | **$\le 3$ calls** | Cached in Python `dict` (`format_key_cache[category]`) |
| `cell_range.setDataArray(...)` | Once per cell range write | **1 call** | Bulk 2D grid write ($O(1)$ IPC calls) |
| `cell_range.setPropertyValue("NumberFormat", key)` | Once per cell range / block | **1 call** | Applied at range/column level ($O(1)$ IPC calls) |

#### Performance Guarantee Across All 34 Locales
- **Total PyUNO IPC Calls**: **$\le 6$ calls total**, regardless of whether writing 1 cell or 10,000 cells.
- **Bridge Overhead**: **$\sim 2-5\text{ ms}$** total UNO bridge execution time.
- **Scalability**: Completely $O(1)$ with respect to range cell count, guaranteeing high performance across all 34 supported LibreOffice locales.

---

## 7. Testing Strategy & Verification Plan

### 7.1 Unit Tests (`tests/calc/test_cells.py`)
- Test `_parse_datetime_string` with varied ISO inputs:
  - Valid dates (`2026-08-08`, `2026/08/08`)
  - Valid times (`08:00`, `08:00:00`, `14:30:45.500`)
  - Valid datetimes (`2026-08-08T08:00:00`, `2026-08-08 08:00:00`)
  - Invalid calendar dates (`2026-02-30`, `2026-13-45`) $\rightarrow$ returns `None`.
  - Non-date strings (`"Hello World"`, `"=SUM(A1:A10)"`) $\rightarrow$ returns `None`.

### 7.2 Native UNO Integration Tests (`tests/calc/test_cells_uno.py`)
- Test end-to-end write and readback in live LibreOffice Calc instance using `@native_test`:
  ```python
  @native_test
  def test_write_and_read_date_time_cells():
      # Write ISO date and time strings
      res = _execute_calc_tool("write_formula_range", {
          "range_name": ["A26:B26"],
          "formula_or_values": "[\"2026-08-08\", \"08:00\"]"
      })
      assert res.get("status") == "ok"

      # Read back values
      read_res = _execute_calc_tool("read_cell_range", {"range_name": ["A26:B26"]})
      row = read_res["result"][0][0]

      # Assert A26 (date)
      assert row[0]["type"] == "date"
      assert row[0]["value"] == "2026-08-08"
      assert row[0]["format_category"] == "date"

      # Assert B26 (time)
      assert row[1]["type"] == "time"
      assert row[1]["value"] == "08:00:00"
      assert row[1]["format_category"] == "time"
  ```

---

## 8. Related Documents

- [Calc Specialized Toolsets](calc-specialized-toolsets.md) — Tool delegation, tiers, and Calc domain status.
- [MCP Protocol & Invariants](mcp-protocol.md) — Model Context Protocol instructions and clock context formatting.
- [NumPy & Python Venv Bridge](enabling_numpy_in_libreoffice.md) — Raw numeric serialization for analytical pipelines.

