# Date and Time Lifecycle in LibreOffice Calc

**Current behavior, target wire contract, and implementation plan**

This document separates what WriterAgent ships today from the proposed Calc write behavior. It covers PyUNO cell values, read-path format enrichment, MCP clock context, and the planned conversion of date/time strings into Calc serial values.

> **Status:** MCP clock context and read enrichment are implemented. ISO-shaped write ingestion is not implemented. Sections marked **Target** describe future behavior, not the current API.

---

## 1. Context & Problem Statement

### 1.1 The Calc Date/Time Storage Model
Calc's **PyUNO cell API** operationally represents constant dates, times, and datetimes as numeric values. This does not mean that file formats lack typed date/time values: ODF has `office:value-type="date"` / `"time"` with `office:date-value` / `office:time-value`, and SpreadsheetML also supports typed ISO dates. This plan concerns Calc's runtime cell API, not the on-disk representation.

1. **Cell content type**: A constant date/time cell is `com.sun.star.table.CellContentType.VALUE`; a formula that evaluates to a date/time remains `FORMULA`. Text that resembles a date remains `TEXT`.
2. **Epoch serial representation**: Runtime values are floating-point day counts relative to the document's `NullDate` (the common Calc default is `1899-12-30`).
   - `46239.0` represents `2026-08-05`.
   - `0.3333333333333333` represents `08:00:00` (8 hours / 24 hours).
   - `46240.5` represents `2026-08-06 12:00:00`.
3. **Display formatting**: Presentation (`2026-08-05`, `08/05/2026`, or `46239`) comes from the cell's `NumberFormat` key in the document's `XNumberFormats` registry.

`format_category` therefore describes the **number format**, not an intrinsic cell data type. An arbitrary number can be date-formatted. `NumberFormat.DURATION` is deliberately excluded from the current enrichment contract: elapsed values such as 30 hours cannot round-trip through a clock-time serializer that drops whole days.

### 1.2 The LLM Friction Points
- **Read Path Friction**: When an LLM reads a spreadsheet via raw `read_cell_range`, receiving `value: 46239.0` without context leaves the model unable to determine if the cell represents currency, a raw quantity, or a date.
- **Write Path Friction**: When an LLM generates data to write (e.g. `["2026-08-08", "08:00"]`), standard string assignment puts literal text (`com.sun.star.table.CellContentType.TEXT`) into the cell. This breaks spreadsheet formulas (e.g. `=A26+1`), numeric sorting, and native Calc filtering.

---

## 2. Lifecycle Architecture

The end-to-end date/time architecture consists of three synchronized phases:

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                         A. MCP & PROMPT CONTEXT                                │
│  Injects the local clock into initialization instructions and tool guidance    │
└───────────────────────┬────────────────────────────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                         B. READ PATH ENRICHMENT                                │
│  detects NumberFormat category ──► converts serial double ──► outputs iso8601   │
└───────────────────────┬────────────────────────────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                         C. WRITE PATH INGESTION                                │
│  parses ISO string ──► computes serial double ──► sets NumberFormat if needed  │
└────────────────────────────────────────────────────────────────────────────────┘
```

**Implementation status:**
- Area A: MCP clock context is **implemented**; write-tool ISO guidance is not.
- Area B: read enrichment with `iso8601` + `format_category` is **implemented**.
- Area C: ISO-shaped string → serial + `NumberFormat` is **planned, not yet in code**.
- Symmetric LLM read (`value` = ISO string) is a **future follow-up** (§3.2); ship write against today's read shape first.

---

## 3. Read Path (Implemented)

*Status: Implemented in commit [`2650d3b`](https://github.com/KeithCu/writeragent/commit/2650d3bbc39f2c3ab29102d8d50208ea1e817656)*

### 3.1 Mechanism
When `read_cell_range` is invoked with `include_format_info=True` (enabled by default for LLM tool invocations):

1. **Pre-flight Check**: To prevent performance degradation on large datasets, `CellInspector._range_format_rows()` scans the range for cell formats. If no date/time formats or formulas exist in the target block, format inspection returns early.
2. **Format grouping**: Queries `cell_range.getUniqueCellFormatRanges()` to group cells sharing a format. The response still requires an $O(N \times M)$ serialization walk, but format-related UNO round-trips scale with format groups rather than cells.
3. **Format classification**: Reads `getByKey(format_id).getPropertyValue("Type")`, masks `NumberFormat.DEFINED`, and classifies:
   - `NUMBER_FORMAT_DATE` $\rightarrow$ `"date"`
   - `NUMBER_FORMAT_TIME` $\rightarrow$ `"time"`
   - `NUMBER_FORMAT_DATE | NUMBER_FORMAT_TIME` $\rightarrow$ `"datetime"`
   `NumberFormat.DURATION` is not treated as `"time"`.
4. **Serial-to-ISO translation**:
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

After Area C ships, **write will accept the subset in §5.2** while **read still exposes serial + `iso8601`**. Today those strings remain text. Do not flip the read shape in the same change as the write path.

> **Invariant**: Internal PyUNO / analysis callers (`include_format_info=False`) remain un-enriched for NumPy and computational pipelines.

---

## 4. Prompting and Context (Partly Implemented)

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
`Current local date and time: Friday, 2026-08-07T11:04:25-04:00 (EDT).`

Calc serials are timezone-less. The first write implementation should accept **naive values only**. An offset-bearing timestamp such as `2026-08-08T08:00:00-04:00` should remain literal text rather than silently losing its represented instant. The write-tool description must tell the model not to copy the MCP clock's offset into a cell value.

> **Unresolved policy:** A future version may deliberately preserve wall-clock fields and discard the offset. If implemented, the code must explain that this is lossy, why it was chosen, and why converting to a local timezone is not reliable without a document timezone and DST rules.

### 4.2 Tool Schema Definitions
- **`ReadCellRange`** (`read_cell_range` in `plugin/calc/cells.py`): already documents `iso8601` / `format_category`.
- **`WriteCellRange`** (`write_formula_range`): **does not yet** mention date/time strings. When implementing Area C, update its description so LLMs emit the strict subset in §5.2 (formulas still use `=`).

Do not broaden write parsing to locale display forms (`08/05/2026`, `5.8.2026`).

---

## 5. Write Path (Target)

*Implementation plan — not yet in code*

### 5.1 Architecture & Design Requirements

The first implementation applies only to the public `write_formula_range` path. `CellManipulator.write_formula` has no repository call sites and is not part of the initial scope.

When writing via `CellManipulator.write_formula_range`:
1. **String parsing**: For a non-formula string, attempt the strict grammar in §5.2 before falling back to `float()` or literal text.
2. **Serial Calculation**: Compute double float value relative to `NullDate` from `doc.getNumberFormatSettings()` (same source as the read path).
3. **Format Application**:
   - Preserve an existing temporal format only when its category matches the parsed value.
   - On a category mismatch, apply the matching default. Preserving a time format for a date can display only midnight; preserving a date format for a time can display `NullDate`.
   - A recognized date/time string is explicit semantic intent, so Text, General, currency, and other non-temporal formats are replaced with the matching default.
   - Resolve all needed default keys before mutating cells.
4. **Batch Execution**: Prefer `cell_range.setDataArray()` for values. See §5.3 for the mixed formula hole.

> **Required implementation comment:** The format-mismatch branch must explain the display-loss problem, the same-category preservation decision, and the alternative “preserve any temporal format” policy so experts can revisit it.

### 5.2 Shared Helper Module (`plugin/calc/datetime_serial.py`)

Put parse and format-inverse next to each other so NullDate epoch math and second-rounding stay shared. Today `_iso8601_from_serial` lives in `plugin/calc/inspector.py`; move (or re-export) it with `_parse_datetime_string` into `plugin/calc/datetime_serial.py`. `manipulator.py` and `inspector.py` both import from there.

#### Accepted first-version grammar

The wire contract deliberately supports a small, unambiguous subset:

- Date: `YYYY-MM-DD`
- Time: `HH:MM` or `HH:MM:SS`
- Datetime: `YYYY-MM-DDTHH:MM[:SS]`
- Compatibility datetime: one space may replace `T`
- Leading/trailing whitespace may be stripped

Hours, minutes, and seconds are zero-padded. Calendar validity is checked after the shape match. Date slashes, timezone suffixes, fractional seconds, `24:00`, leap seconds, durations, and locale display strings are not accepted as dates in the first version; they fall back to text. Fractional seconds are deferred because the current read path and default formats expose whole seconds.

Fast prefilter before regex:

```python
if not any(c in val for c in ("-", ":")):
    return None  # Skip regexes for plain text, numbers, and prose
```

```python
_DATE_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$")
_DATETIME_RE = re.compile(
    r"^(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])[T ]"
    r"([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$"
)
```

The regexes are a shape filter, not the calendar validator. The implementation may instead use a smaller standard-library parser if it enforces exactly the same contract on LibreOffice's supported Python runtimes.

#### Parsing & Serial Conversion Logic
```python
def _parse_datetime_string(val_str: str, null_date=None) -> tuple[float, str] | None:
    """Parse WriterAgent's date/time wire subset.

    Returns:
        tuple of (serial_float, format_category) or None if unparseable.
        format_category is \"date\", \"time\", or \"datetime\".
    """
    # 1. strip + fast char guard
    # 2. match DATETIME, DATE, then TIME
    # 3. validate calendar fields and compute against the document NullDate
    # 4. invalid or unsupported input → None, allowing literal-text fallback
    ...
```

For dates and datetimes, serials are the day/second difference from `NullDate`. Time-only values are seconds since midnight divided by 86,400 and do not depend on the epoch. Default format keys are resolved separately (§6).

The initial contract targets modern civil dates. Pre-1582 dates, Excel's fictitious `1900-02-29` (serial 60), and direct interchange of raw Excel 1900/1904 serials are explicitly out of scope. Reading the Calc document's `NullDate` is still mandatory and covers Calc's supported `1899-12-30`, `1900-01-01`, and `1904-01-01` settings.

### 5.3 Execution Workflow in `CellManipulator.write_formula_range`

**Critical:** today's code, when any cell in the range is a formula, commits the **entire** range via `setFormulaArray` of stringified inputs and **ignores** `data_array`. Parsing ISO into serials is useless for mixed ranges unless the commit path is fixed.

1. **Retrieve Document Settings**:
   Read `null_date = doc.getNumberFormatSettings().getPropertyValue("NullDate")` once per invocation. Resolve the destination number-format locales and the documented fallback described in §6.3 before mutation.
2. **Build Data Array + Formula Overlay List**:
   For each input:
   - `startswith("=")` → leave data cell empty; record formula for overlay.
   - else `_parse_datetime_string(...)` → put `serial_float` in `data_array`; mark cell for format pass if needed.
   - else `float()` → number; else TEXT string.
3. **Commit Values First**:
   `cell_range.setDataArray(tuple(data_array))` always (serials / numbers / text; formula cells empty).
4. **Overlay Formulas**:
   For each recorded formula cell, `setFormula` (or a formula-only pass). Do **not** send ISO date strings through `setFormulaArray`.
5. **Apply format adjustments**:
   - Prefer one `getUniqueCellFormatRanges()` (or a category mask built while parsing) to skip cells already in date/time/datetime.
   - Coalesce remaining cells that need a default into contiguous blocks; apply `NumberFormat` per block — never per-cell `setPropertyValue` inside a tight loop.
   - Resolve default keys once per category via §6 and cache in a Python `dict` for the invocation.

### 5.4 Write-Path Performance & Optimization Rules

1. **Fast String Pre-filtering**: $O(1)$ char guard before regex (§5.2).
2. **Range / Block `NumberFormat`**: Never set NumberFormat per cell in a loop. Homogeneous ranges → one range set. Sparse mixed grids → coalesce contiguous same-category blocks ($O(\text{blocks})$ IPC, not a hard $\le 6$ for every sparse layout).
3. **Format Key Caching**: Cache resolved keys per category (`date` / `time` / `datetime`) for the write invocation (and optionally per document session).

Typical homogeneous writes should stay near a handful of UNO calls (`NullDate`, locale resolution, format resolution, `setDataArray`, and a format block). Sparse mixed grids scale with block count.

### 5.5 Merge-Safe Implementation Sequence

1. **Behavior-preserving extraction**: Add `plugin/calc/datetime_serial.py`, move shared serial conversion/classification there, and retain compatibility imports where useful. Add `tests/calc/test_datetime_serial.py`, matching the source module as required by `AGENTS.md`.
2. **Mixed-formula correction**: Independently change `write_formula_range` to commit `data_array` first and overlay formulas. Add regression coverage proving ordinary numbers/text keep their native types in mixed ranges.
3. **Complete user-visible feature**: Add parsing, locale-safe format resolution, required design comments, tool-schema guidance, and UNO write/readback tests together. Do not merge a state that writes serials without usable number formats.

### 5.6 Follow-ups (out of scope)

- Symmetric LLM read (`value` = ISO) — §3.2 future.
- Locale-display write parsing.
- Fractional seconds, offsets/timezones, `24:00`, leap seconds, and durations.
- Fixing existing `set_style` / `_set_number_format` ASCII `queryKey("YYYY-MM-DD", …)` (same locale-letter bug; prefer `getFormatIndex` / FormatString there too).
- Changing NumPy / `include_format_info=False` raw serial behavior.
- `=PY` spill coercion, NumPy `datetime64` epoch conversion, and spreadsheet-import epoch cleanup.

---

## 6. Locale-Safe Number Formats

### 6.1 Localized Format Codes
LibreOffice supports many locales, and the exact set evolves. Format code letters can be localized:

In non-English locales, passing raw ASCII format codes like `"YYYY-MM-DD"` directly to `XNumberFormats.queryKey()` can fail because date format letters are localized:
- **German (`de-DE`)**: Year = `J` (Jahr), Day = `T` (Tag) $\rightarrow$ `"JJJJ-MM-TT"`
- **French (`fr-FR`)**: Year = `A` (Année), Day = `J` (Jour) $\rightarrow$ `"AAAA-MM-JJ"`
- **Finnish (`fi-FI`)**: Year = `V` (Vuosi), Day = `P` (Päivä) $\rightarrow$ `"VVVV-KK-PP"`

Hardcoding `"YYYY-MM-DD"` inside `queryKey()` may fail or create an unintended format on installations whose format letters are localized.

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
locale = resolved_destination_or_document_fallback_locale

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

Never pass ASCII `"YYYY-MM-DD"` into `queryKey` / `addNew` for defaults. Built-in `getFormatIndex` keys carry localized format letters. Composing datetime from their `FormatString` values is the proposed approach, but UNO tests must verify it on the project's supported LibreOffice versions and representative locales.

### 6.3 Locale Selection

`CharLocale` is text-language metadata and is not universally the correct number-format locale.

1. If a destination already has a number format, prefer the `Locale` property of that format.
2. Group mixed destinations by the locale needed for default-format resolution.
3. For General/unformatted cells, use an explicitly documented document-level fallback; verify the exact UNO property used on supported LibreOffice versions.

Do not silently treat `CharLocale` as authoritative for every cell.

### 6.4 Locale-Independent Wire Contract
1. **Read Path**: `_iso8601_from_serial()` translates serial doubles to ISO 8601 strings (`YYYY-MM-DD`, `HH:MM:SS`, `YYYY-MM-DDTHH:MM:SS`), locale-independent.
2. **Write Path**: `_parse_datetime_string()` parses the strict locale-independent subset in §5.2 into day serials.
3. **Display Formatting**: `DATE_DIN_YYYYMMDD` / `TIME_HHMMSS` / composed datetime FormatString for defaults when the cell has no date/time format yet.

### 6.5 Expected UNO Call Shape

During a typical homogeneous `write_formula_range` invocation:

| UNO API Method | Frequency | Optimization Strategy |
| :--- | :--- | :--- |
| `NullDate` via `getNumberFormatSettings()` | Once per write | Retrieved once per batch |
| Destination/fallback locale resolution | Once per relevant locale group | Reuse locale and format keys across equal-format destinations |
| `getFormatIndex` / composed datetime `queryKey` | Once per category used ($\le 3$) | Cached in `format_key_cache[category]` |
| `cell_range.setDataArray(...)` | Once | Bulk 2D grid write |
| Formula overlay | Per formula cell (or batched) | Only when the range mixes formulas |
| `setPropertyValue("NumberFormat", key)` | Once per contiguous block needing a default | Skip cells that already have date/time/datetime formats |

Homogeneous ranges should require only a small number of UNO calls. Sparse mixed grids scale with formula overlays, locale groups, and contiguous format blocks. These are design targets, not hard constant-call guarantees.

---

## 7. Testing Strategy & Verification Plan

### 7.1 Unit Tests (`tests/calc/test_datetime_serial.py`)
- Test `_parse_datetime_string` with varied ISO inputs:
  - Valid dates (`2026-08-08`)
  - Valid times (`08:00`, `08:00:00`)
  - Valid datetimes (`2026-08-08T08:00:00`, `2026-08-08 08:00:00`)
  - Unsupported slash, fractional-second, `Z`, and offset forms → `None`
  - Invalid calendar dates (`2026-02-30`, `2026-13-45`) $\rightarrow$ returns `None`
  - Non-date strings (`"Hello World"`, `"=SUM(A1:A10)"`) $\rightarrow$ returns `None`
  - All three Calc `NullDate` settings and epoch boundary values
  - Time-only conversion is independent of `NullDate`
  - Duration-format classification remains excluded

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
- Preserve a same-category existing `NumberFormat`.
- Apply the matching default for temporal subtype mismatches and Text/non-temporal formats.
- Non-default `NullDate` round-trip.
- Built-in date/time and composed datetime formats under representative locales.
- Formula results equal to zero and conversion overflow should be recorded as read-path edge cases; enrichment must eventually fail per cell rather than fail an entire range.

---

## 8. Related Documents

- [Calc Specialized Toolsets](calc-specialized-toolsets.md) — Tool delegation, tiers, and Calc domain status.
- [MCP Protocol & Invariants](mcp-protocol.md) — Model Context Protocol instructions and clock context formatting.
- [NumPy & Python Venv Bridge](enabling_numpy_in_libreoffice.md) — Raw numeric serialization for analytical pipelines.
- [Calc `=PY` Data Shapes](calc-py-data-shapes.md) — Intentional non-coercion at the Python bridge.
- [NumPy Serialization](numpy-serialization.md) — Separate datetime/string wire semantics that must not be conflated with Calc serials.

## 9. Authoritative References

- [LibreOffice Date & Time Functions](https://help.libreoffice.org/latest/en-US/text/scalc/01/04060102.html) — serial model, supported date bases, and timezone limitations.
- [LibreOffice `NumberFormatSettings`](https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1util_1_1NumberFormatSettings.html) — `NullDate`.
- [LibreOffice `NumberFormat` constants](https://api.libreoffice.org/docs/idl/ref/namespacecom_1_1sun_1_1star_1_1util_1_1NumberFormat.html) — DATE, TIME, DATETIME, and DURATION categories.
- [LibreOffice `NumberFormatIndex`](https://api.libreoffice.org/docs/idl/ref/namespacecom_1_1sun_1_1star_1_1i18n_1_1NumberFormatIndex.html) and [`XNumberFormatTypes`](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1util_1_1XNumberFormatTypes.html) — locale-specific built-in keys.
- [ODF 1.3 schema](https://docs.oasis-open.org/office/OpenDocument/v1.3/os/part3-schema/OpenDocument-v1.3-os-part3-schema.html) — persisted date/time value types.
- [SpreadsheetML cell types](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.cellvalues?view=openxml-3.0.1) — typed ISO date support in XLSX.
- [Microsoft Excel 1900 leap-year behavior](https://learn.microsoft.com/en-us/troubleshoot/office/excel/wrongly-assumes-1900-is-leap-year) — raw-serial interoperability boundary.
