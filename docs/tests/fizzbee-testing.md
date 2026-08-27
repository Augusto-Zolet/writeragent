# FizzBee Formal Modeling and MCP Testing (Writer & Calc)

## Overview

This document describes the formal model checking and Model-Based Testing (MBT) infrastructure for WriterAgent's **MCP (Model Context Protocol)** server across **Writer** and **Calc** full toolset layouts, powered by **FizzBee** (formal specification language and model checker) and Python MBT runners.

---

## 1. Motivation

WriterAgent exposes a large surface area over MCP:
- **Writer**: 108 tools across core functions and 18 specialized domains (`bookmarks`, `footnotes`, `tables`, `tracking`, `page`, `structural`, `styles`, `shapes`, `charts`, `indexes`, `textframes`, etc.).
- **Calc**: 61 tools across core functions and 12 specialized domains (`sheets`, `ranges`, `analysis`, `shapes`, `charts`, `comments`, `conditional_formatting`, `errors`, `pivot_tables`, `python`, `search`, etc.).

Testing such large surfaces requires:
1. **Full layout discovery and validation**: Ensuring all tools produce valid MCP JSON schemas (`inputSchema`, normalized parameter types, `document_url` targeting support).
2. **Formal state machine modeling**: Verifying protocol transitions (`UNINITIALIZED` $\rightarrow$ `INITIALIZED`, exposure mode switches, session handling).
3. **Safety and invariant verification**: Guaranteeing structured error envelopes on invalid tools or parameters, correct tool visibility under different exposure modes (`direct_flat`, `delegate`, `direct_discovery`), and document/spreadsheet state integrity.

---

## 2. FizzBee Installation & Verification

FizzBee is distributed as a standalone binary (Go). We provide an automated installer script and Make targets for easy developer onboarding:

### Installation
```bash
# Automated install into active virtual environment (.venv/bin/fizzbee)
make install-fizzbee
# Or directly via python:
python scripts/install_fizzbee.py --install

# macOS Homebrew alternative:
brew tap fizzbee-io/fizzbee && brew install fizzbee
```

### Checking Formal Models
To run the formal model checker against all `.fizz` specifications:
```bash
make check-fizzbee
```

---

## 3. FizzBee Formal Specifications

Formal specifications live in [`tests/mcp/fizzbee/`](../../tests/mcp/fizzbee/):

### A. Protocol Lifecycle (`tests/mcp/fizzbee/writer_mcp_protocol.fizz`)
- MCP server lifecycle states (`UNINITIALIZED`, `INITIALIZED`).
- Exposure modes (`DELEGATE`, `DIRECT_FLAT`, `DIRECT_DISCOVERY`).
- Document context targeting (`NONE`, `WRITER`, `CALC`, `DRAW`).
- Invariants: `Inv_InitializedBeforeCalls`, `Inv_FindToolsGating`.

### B. Writer Tools Model (`tests/mcp/fizzbee/writer_tools_model.fizz`)
- Document text buffer, bookmarks, footnotes, tables, and track changes state.
- Invariants: `Inv_BookmarksBounded`, `Inv_TablesValidDimensions`, `Inv_PendingChangesOnlyWhenRecorded`.

### C. Calc Tools Model (`tests/mcp/fizzbee/calc_tools_model.fizz`)
- Spreadsheet grid cells, formula ranges, sheet management, named ranges, and filters.
- Invariants: `Inv_SheetCountPositive` (`len(sheets) >= 1`), `Inv_ActiveSheetMustExist`, `Inv_NamedRangesIntegrity`.

---

## 4. Full Layout Extraction & Validation

The layout extraction helpers inspect, categorize, and validate all tools for Writer and Calc:

- **Writer Layout Helper**: [`tests/mcp/writer_full_layout.py`](../../tests/mcp/writer_full_layout.py)
- **Calc Layout Helper**: [`tests/mcp/calc_full_layout.py`](../../tests/mcp/calc_full_layout.py)

```python
from tests.mcp.writer_full_layout import extract_full_writer_layout, validate_mcp_schema
from tests.mcp.calc_full_layout import extract_full_calc_layout

writer_layout = extract_full_writer_layout()
calc_layout = extract_full_calc_layout()

print(f"Writer tools: {writer_layout['total_count']}") # 108
print(f"Calc tools:   {calc_layout['total_count']}")   # 61
```

---

## 5. Exposure Modes

WriterAgent MCP supports three tool exposure modes across both Writer and Calc:

| Mode | `tools/list` Content | Specialized Tools Access |
|------|----------------------|--------------------------|
| **`delegate`** (default) | Core tools only (~12-14 tools) | Via delegate gateway or direct call |
| **`direct_flat`** | Full layout (all core & specialized tools) | Listed directly in `tools/list` |
| **`direct_discovery`** | Core tools + `find_tools` | Via dynamic domain lookup with `find_tools` |

---

## 6. Running the Tests & Fuzzer

### A. Automated Pytest Suite
Run the Writer and Calc Model-Based Test suites:

```bash
# Run Writer MCP tests
pytest tests/mcp/test_fizzbee_writer_mcp.py -v

# Run Calc MCP tests
pytest tests/mcp/test_fizzbee_calc_mcp.py -v

# Run with custom steps or duration via environment variables
FIZZBEE_MCP_STEPS=2000 pytest tests/mcp/test_fizzbee_calc_mcp.py -v
FIZZBEE_MCP_DURATION_SEC=10 pytest tests/mcp/test_fizzbee_calc_mcp.py -v
```

### B. Dedicated CLI Randomized Fuzzer
A standalone runner in [`scripts/fizzbee_mcp_fuzzer.py`](../../scripts/fizzbee_mcp_fuzzer.py) runs randomized fuzzing over either Writer or Calc:

```bash
# Fuzz Writer (default)
python scripts/fizzbee_mcp_fuzzer.py --app writer --duration 5

# Fuzz Calc full toolset
python scripts/fizzbee_mcp_fuzzer.py --app calc --duration 5

# Run for a specific step count with malformed parameter mutations
python scripts/fizzbee_mcp_fuzzer.py --app calc --steps 2000 --mutate-rate 0.15 --verbose
```

### Fuzzer Performance & Metrics
- **Throughput**: ~750–1,000 JSON-RPC requests/second.
- **Coverage**: Exercises **100% of all tools** in ~2 seconds.
- **Invariants Checked**: Validates JSON-RPC 2.0 response format, correct request/response ID matching, error envelope schemas, and absence of server crashes on every request.
