# LibrePythonista Features Analysis for WriterAgent

This document provides a detailed architectural review of the **LibrePythonista** extension (`python_libre_pythonista_ext`) and identifies valuable features, design patterns, and components that can be adapted to enhance **WriterAgent**.

**Related:** [Enabling NumPy & Python](../enabling_numpy_in_libreoffice.md#comparison-with-librepythonista-pyc-and-lp) (`PY.C` / `lp()` vs `=PY`), [Geometric Recalc Order](../calc/geometric-recalc-order.md) (row-major predecessor chain), [Microsoft `=PY` interchange](../scripting/ms-py-compatibility.md#58-ooxml--xlfnpy-import) (Excel rewriter — the pattern, not the parser).

---

## Executive Summary

WriterAgent's **external subprocess venv design** is structurally superior to LibrePythonista's in-process approach because it completely sidesteps critical **ABI compatibility issues** (which frequently crash LibreOffice when users attempt to import compiled C extensions like NumPy/Pandas built for different minor Python versions than the embedded interpreter).

In line with WriterAgent's design philosophy, **we actively reject any bundled package manager or in-LO PIP tracking features**. By letting the user simply point `scripting.python_venv_path` to any standard, externally-managed virtual environment (which they can populate and maintain themselves with standard terminal tools), we keep the extension extremely simple, reliable, and decoupled from environmental overhead.

---

## Core Architectural Alignment: Package Management

### 1. Bundled PIP Installer & Surgical Package Tracker (`___lo_pip___`)
* **Status: REJECTED**
* **The LibrePythonista Feature:** Takes a filesystem snapshot before and after installation to log changes in a tracker JSON file so that it can surgically uninstall packages from LibreOffice's `site-packages`.
* **Why it is rejected for WriterAgent:** This feature adds immense complexity, footprint size, and potential points of failure to the extension. WriterAgent's architecture is built on **user-provided environments**; the user manages their own environment, packages, and paths externally. Leaving package management entirely to the user's standard terminal tools keeps WriterAgent simple, robust, and clean.

---

## Key Features Worth Adopting or Adapting

### 2. WebView Monaco Code Editor Dialog
* **The Feature:** When editing python code inside a cell, LibrePythonista can spawn a subprocess (`cell_edit.py`) that opens a native desktop window containing a WebView. The WebView runs a modern Monaco (VS Code-based) code editor (`librepythonista-python-editor`). 
* **The Socket Bridge:** The editor subprocess communicates in real-time with LibreOffice via a local socket server:
  - **Syntax Validation:** Sends code to LibreOffice for on-the-fly syntax compilation (`test_compile_python`).
  - **Auto-completion & Context:** Syncs module variables and headers.
  - **Theme Matching:** Automatically detects LibreOffice's active theme (dark/light mode) to render Monaco beautifully in matching colors.
* **Application to WriterAgent:** Currently, `=PYTHON()` code must be edited inline inside the formula bar, which is cramped and painful. We could adopt this WebView/Monaco pattern to spawn a gorgeous, full-featured Python editing dialog for `=PYTHON()` formulas and custom scripting blocks!

### 3. Real-Time Calc Sheet Range Selector Integration
* **The Feature:** While editing code inside the Monaco WebView, users can click a "Select Range" menu. The editor calls back to LibreOffice to dispatch a native `GlobalCalcRangeSelector` tool. The user selects a cell range in Calc's grid, and the selected range is returned to the editor, formatted automatically as a Python range call (e.g. `lp("A1:B10")`), and inserted directly at the editor's cursor!
* **Application to WriterAgent:** This bridge is incredibly elegant. In WriterAgent, we could use a similar range-selection dispatcher to let users visually click ranges when prompting the chatbot or building `=PYTHON()` functions.

### 4. Bulletproof Cell Position & Merged Cells Geometry Collapsing (`QryCtlCellSizePos`)
* **The Feature:** Standard PyUNO cell geometry functions (`XCell.Position` and `Size`) fail or return incorrect coordinates when cells are merged. LibrePythonista resolves this beautifully:
  ```python
  if self._cell.component.IsMerged:
      cursor = self._cell.calc_sheet.create_cursor_by_range(cell_obj=self._cell.cell_obj)
      cursor.component.collapseToMergedArea()
      rng = cursor.get_calc_cell_range()
      ps = rng.component.Position
      size = rng.component.Size
  ```
* **Application to WriterAgent:** Any UI features or image overlay tools we build for Calc must handle merged cells correctly. Adopting this cursor-collapsing geometry formula ensures our overlay coordinate calculations are 100% reliable.
* **WriterAgent invariant:** Calc placement code must use `plugin.calc.calc_utils.get_cell_geometry(...)` (merged-aware collapse behavior) instead of reading `cell.Position` / `cell.Size` directly.

### 5. Matplotlib SVG Embedding & Anchoring (`CmdAddImageLinked`)
* **The Feature:** Converts a Matplotlib plot to SVG in the temp directory and inserts it into Calc's `SpreadsheetDrawPage` with robust grid-locked properties:
  - `Anchor`: Set to the specific cell component so it moves/resizes with the cell.
  - `ResizeWithCell`: `True` so the plot stretches/shrinks natively when rows/columns are resized.
  - `MoveProtect` & `SizeProtect`: Set appropriately so users don't accidentally drag the chart out of alignment.
* **Application to WriterAgent:** WriterAgent has tools to generate charts, but placing them as unanchored drawing objects makes the sheet messy. We should port this exact `CmdAddImageLinked` layout model so matplotlib plots and images are perfectly locked to their target cells.

### 6. Flatpak and Snap Environment Sandboxing Support
* **The Feature:** LibrePythonista has robust environment checks to detect if LibreOffice is running under a Flatpak or Snap sandbox. It knows how to shell out to the host system using:
  - `flatpak-spawn --host` for Flatpak environments.
  - `snapctl run` for Snap.
* **Application to WriterAgent:** Many Linux users install LibreOffice via Flatpak or Snap. In these sandboxed environments, standard `subprocess.Popen` is jailed and cannot access the user's host Python venv. Adapting LibrePythonista's Flatpak/Snap detection and spawning parameters will make WriterAgent's venv runner incredibly resilient across all package managers.

---

## Architectural Comparison Summary

| Design Dimension | WriterAgent | LibrePythonista | Recommendation for WriterAgent |
| --- | --- | --- | --- |
| **Execution Sandbox** | Warm external subprocess (venv Python binary) | In-process LibreOffice embedded Python | **Keep WriterAgent's design.** Subprocess isolation is highly secure and immune to ABI conflicts. |
| **IPC Mechanism** | Stdin / Stdout JSON & Pickle5 pipes | Localhost TCP sockets | **Keep Stdin/Stdout.** Pipes have zero setup overhead, zero port conflicts, and no firewall blocks. |
| **Formula Storage** | Embedded directly as `code` in the formula | Key in formula pointing to document-side store | **Keep WriterAgent's design.** Formula-embedded code is a pure function and makes files highly portable. |
| **PIP Management** | N/A (User maintains their own venv) | Custom installer with surgical tracking | **Keep WriterAgent's design.** Standard terminal tools externally manage the venv. |
| **UI & Editor** | Sidebar Chat + inline formula editing | Custom Sidebar + Monaco WebView Dialog | **Adopt Monaco WebView** for rich, multi-line Python editing windows. |
| **Plot Rendering** | Text/JSON results returned | SVG generated and cell-anchored in sheet | **Adopt SVG Cell-Anchored Embedding** for gorgeous, grid-locked charts. |
| **File interchange** | Bidirectional Excel PY rewriter ([`excel_py_convert/`](../../plugin/calc/excel_py_convert/)); LP ODS import **not shipped** | Private ODS sidecar (`librepythonista/` + `PY.C`) | Import-only, reuse `xl()` rewrite + geometric attach — [below](#file-import-librepythonista-ods--py--research) |

---

## File import (LibrePythonista ODS → `=PY`) — research

**Status: research only. Not implemented.** This is a one-way *file conversion* problem, same class as Excel Python-in-Excel → DAG `=PY` ([ms-py §5.8](../scripting/ms-py-compatibility.md#58-ooxml--xlfnpy-import)). It is **not** “run LibrePythonista inside LibrePy.” Do **not** start from [`parse_excel_ooxml.py`](../../plugin/calc/excel_py_convert/parse_excel_ooxml.py) — that is OOXML. Do **not** add a LibrePythonista exporter.

Upstream: [Amourspirit/python_libre_pythonista_ext](https://github.com/Amourspirit/python_libre_pythonista_ext) (Apache 2.0). Layout below is from that tree (`py_source.py`, `py_impl.py`, `lp_mod.py`, `pyproject.toml` `lp_code_dir`).

### What their files actually store

The cell formula is a **locator**, not the script. Typical shapes:

```text
=PY.C(SHEET(); CELL("ADDRESS"))
=PY.C(SHEET(); CELL("ADDRESS"); A1:B10)
=COM.GITHUB.AMOURSPIRIT.EXTENSIONS.LIBREPYTHONISTA.PYIMPL.PYC(SHEET(); CELL("ADDRESS"); C1)
```

`SHEET()` / `CELL("ADDRESS")` identify the cell. Extra arguments are Calc precedents only:

- The **previous Python cell** on the sheet (auto-inserted so later cells dirty when earlier ones change — same *intent* as [Geometric Recalc Order](../calc/geometric-recalc-order.md)).
- And/or the **data range** `lp()` reads, so edits to that range recalc the formula.

Source lives in the document filesystem (SFA), not in the formula:

```text
vnd.sun.star.tdoc:/<runtime_uid>/librepythonista/<sheet_unique_id>/<code_name>.py
```

`lp_code_dir` defaults to `librepythonista`. `code_name` is the cell custom property `libre_pythonista_codename`. On save those streams persist as extra ODS zip members under `librepythonista/`, plus a document JSON (`LibrePythonista_calc_props.json` or similar). Copy/paste of `PY.C` cells is still an upstream gap (formula copies; the sidecar often does not).

User code talks to the sheet with **`lp()`**, not formula `data`:

```python
df = lp("A1:B10", headers=True, collapse=True)
s = lp("MyRange")
x = lp("Sheet1.A1")
```

Ranges come back as **pandas DataFrames** by default (`headers`, `collapse`, `column_types`, named ranges, sheet-qualified addresses). The cell module is in-process LibreOffice Python: `lp`, `ooodev` (`CalcDoc`, `Lo`), matplotlib SVG backend, pandas, and numpy are injected. Later cells use names defined in earlier cells because **all cells share one concatenated module**, run row-major.

LP documents are **ODS-native**. Save-As `.xlsx` typically drops the SFA sidecar; an importer should not chase that path.

### Mapping onto LibrePy

| LibrePythonista | LibrePy `=PY` | Import action |
| --- | --- | --- |
| `=PY.C(SHEET(); CELL("ADDRESS"); extras…)` | `=PY(code; ranges…)` | Replace locator with inlined (or `py_code_*` bank) source |
| Sidecar `.py` + `libre_pythonista_codename` | Code in the formula / bank sheet | Extract via live UNO (custom props + SFA) or unzip `librepythonista/**/*.py` |
| `lp("A1:B10", headers=True)` | `data` / `data.to_pandas()` as a formula arg | AST-rewrite like static `xl()` ([`xl_static_rewrite.py`](../../plugin/calc/python/xl_static_rewrite.py)) |
| Extra `PY.C` arg = data range | Real `data` precedent | Lift onto `=PY` args |
| Extra `PY.C` arg = previous PY cell | Geometric predecessor (Calc-only) | **Drop as worker data.** Attach via [`geometric_recalc.py`](../../plugin/calc/python/geometric_recalc.py) / flag-on reconcile. Copying it as `data` is the [§4 arity footgun](../calc/geometric-recalc-order.md#4-data-binding--do-not-shadow-data) |
| Shared in-process module | Shared kernel (`scripting.python_session_mode`) | Required for LP-style pipelines; Isolated is a no-op for Python globals |
| Row-major previous-cell chain | Geometric Recalc Order (experimental, default **off**) | Same list `cell_discovery` already uses. Do **not** invent a third ordering scheme |
| `collapse=True` / `column_types` | No equivalent | Fail closed; report |
| `from ooodev.calc import CalcDoc` | Forbidden on `=PY` (venv; `python_tool_domain=""`) | Fail closed |
| Cell form-control chrome, anchored SVG plots | Our spill / image egress | Strip controls; plots are a separate egress, not LP-compatible |

### What we reuse (already in the tree)

The Excel converter is the **pipeline**, not the parser (~4,200 lines under [`excel_py_convert/`](../../plugin/calc/excel_py_convert/)): detect → extract → rewrite call sites → write `=PY` through [`apply_calc.py`](../../plugin/calc/excel_py_convert/apply_calc.py). Auto-on-open is [`auto_open.py`](../../plugin/calc/excel_py_convert/auto_open.py).

| Piece | Reuse |
| --- | --- |
| Detect LP workbook | `PY.C` / `…PYIMPL.PYC` formulas; zip member `librepythonista/`; cell prop `libre_pythonista_codename` |
| Extract source | Live UNO on open (custom properties + SFA). Zip parse is a test/CLI helper — sheet/cell ids are user-defined attributes, not `Sheet1/A1.py` |
| Rewrite `lp("A1:B10", headers=True)` | Same AST walk as `xl()` → `data` / `data.to_pandas()`. Refuse dynamic `lp(var)` / f-strings (fail closed, like Excel `xl(variable)`) |
| Write formulas | `apply_calc.py` + `py_code_<Sheet>` bank for long scripts |
| PY↔PY order | [Geometric Recalc Order](../calc/geometric-recalc-order.md) — already landed. **Do not** copy previous-PY extras as `data` |

Excel import policy applies here too: the rewriter **must not invent geometric edges**. After cells are `=PY`, turning Geometric Recalc Order on lets the deferred pass attach `;previous`. LP files are authored *with* that assumption, so the conversion report should say **Shared kernel + Geometric Recalc Order**. Attaching once at import and recording the UDProp map is allowed so strip works; insert/delete repair still needs the flag.

Geometric order is the cheap 80% of LP’s shared module, not a complete substitute:

- **Per sheet**, not workbook. `Sheet2` using a name from `Sheet1` still needs an explicit `data` ref.
- **Chain, not barrier.** Edit a later cell and the prefix namespace stays; “replay everything top to bottom” does not.
- **Flag is global and off.** Shared kernel and geometric recalc are Settings keys, not per-file. Leaving previous-cell refs on the formula *without* the strip map breaks `data`.
- **100-cell cap.** Larger LP sheets skip chaining entirely.

### What stays hard (not a zip rewrite)

1. **`lp()` is not `data`.** Mechanical `lp("A1:B10")` → `data` type-breaks `.iloc` / `.groupby`. `headers=True` we already emit as `data.to_pandas()`. `collapse` we do not have.
2. **In-process UNO in user scripts.** `ooodev` / `uno` / `Lo.` are legal in LP cells and illegal in venv `=PY`. Fail closed; do not stub them.
3. **Chrome.** Form controls on the Python cell and cell-anchored matplotlib SVGs remain as drawing objects unless stripped. Our plot egress is not their `CmdAddImageLinked` card.
4. **No interchange spec.** Sidecar folder + cell properties + Add-In formula is an extension-private store. It can change; it is not ODF.

### Recommended shape (if built)

- **Import only**, ODS, one-way. Live UNO on open (same hook class as Excel auto-convert), not a new zip rewriter as the product path.
- Classify `PY.C` extras: range `lp()` reads → `data`; previous PY cell → drop / geometric attach. Never a second predecessor field.
- Fail closed on `ooodev`/`uno`, dynamic `lp()`, and `collapse=True`, with a conversion report (same policy as Excel `xl(variable)`).
- Do **not** keep `PY.C` working beside `=PY`.

### Effort (order of magnitude)

| Scope | Effort | Notes |
| --- | --- | --- |
| MVP: static `lp("A1:B10")` + pandas, no UNO, no plots | ~1–2 weeks | Detect, extract, AST-rewrite, write `=PY`, tests on sample ODS |
| Production auto-on-open | ~3–6 weeks | Extra-arg classification, named ranges, sheet-qualified refs, shared-kernel + geometric advisory, fail-closed, strip cell controls, UNO + zip tests |
| Faithful LP runtime | Months / don’t | Collapse, default DataFrames, plot cards, in-process UNO, workbook-wide concatenated module. Same class as “run Excel co-volatility inside Calc” — already rejected |

**Bottom line:** for workbooks that are “pandas over sheet ranges,” this is a moderate feature that leans on `xl_static_rewrite.py`, `apply_calc.py`, and geometric recalc. For real LibrePythonista documents that use the shared module across sheets, plots, or `ooodev`, it is a migration tool with a report of what we dropped, not a compatibility layer. Ordering is already paid for; extraction + `lp()` semantics are the remaining weeks.
