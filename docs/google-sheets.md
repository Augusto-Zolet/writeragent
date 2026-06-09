# Calc spreadsheet backlog — ideas from competitive landscape

Distilled from a broader survey of Google Sheets, Excel, Quadratic, Mito, Neptyne, and LibrePythonista. This doc lists **what WriterAgent might still build**. Shipped behavior and architecture live in the linked docs below — not repeated here.

---

## What we already have

| Capability | Status | Doc / code |
|------------|--------|------------|
| `=PY()` / `=PYTHON()` + venv worker | Shipped | [enabling_numpy_in_libreoffice.md §6](enabling_numpy_in_libreoffice.md#6-the-python-calc-function) |
| Pickle5 IPC + `split_grid` wire format | Shipped | [numpy-serialization.md](numpy-serialization.md) |
| AST sandbox (import whitelist, no `os`/`sys`/`subprocess`) | Shipped | [plugin/scripting/venv_sandbox.py](../plugin/scripting/venv_sandbox.py) |
| Shared kernel per workbook | Shipped | [python-in-excel-dev-plan.md](python-in-excel-dev-plan.md) Phase 1 |
| Workbook init scripts | Shipped | [document_scripts.py](../plugin/scripting/document_scripts.py) |
| Multi-range varargs (`data = [range1, range2, …]`) | Shipped | [enabling_numpy_in_libreoffice.md §9](enabling_numpy_in_libreoffice.md#9-multi-range-support-varargs) |
| Agent / chat grid writes (`write_formula_range`, egress helpers) | Shipped | [plugin/calc/manipulator.py](../plugin/calc/manipulator.py) |
| Trusted Analysis / Viz / Symbolic / Vision helpers | Shipped | [Scientific domain roadmap](enabling_numpy_in_libreoffice.md#scientific-domain-roadmap-trusted-helpers) |
| Monaco Run Python Script + document-attached scripts | Shipped | [python-monaco-editor-dev-plan.md](python-monaco-editor-dev-plan.md) |
| Background worker + UI drain (no main-thread block) | Shipped | [async_stream.py](../plugin/framework/async_stream.py), [worker_pool.py](../plugin/framework/worker_pool.py) |

---

## Design principles (from the survey)

- **Local-first / data sovereignty** — Compute stays on the user's machine (user venv subprocess), not in a cloud `=AI()` or `=PY()` container. This is already WriterAgent's architecture; cloud spreadsheet AI is a positioning contrast, not a feature target.
- **Auditable code over black-box cell AI** — Prefer generated Python plus existing tools over non-deterministic LLM text written directly into cells. Aligns with the two-phase LLM workflow in [enabling_numpy §3](enabling_numpy_in_libreoffice.md#3-user-guide).
- **Explicit `data` wiring for recalc order** — Shared kernel does **not** give Excel-style co-volatility (all Python cells re-run together in row-major order). Pass upstream cells/ranges as `data` arguments to declare Calc's DAG order. Author idempotent side effects. Detail: [python-in-excel-dev-plan § Shared kernel lifecycle](python-in-excel-dev-plan.md#shared-kernel-lifecycle--recalc-semantics).

---

## Backlog — consider doing

### Tier A — Calc / Python UX (high leverage)

#### Range alignment for multi-range NumPy

**Problem:** Varargs deliver separate arrays per range. Mismatched shapes (e.g. `A1:A10` and `C1:C15`) still require manual padding or masking before vector ops like `np.corrcoef`, regression, or element-wise math across ranges.

**Consider:** A small alignment helper that projects mismatched grids into a common shape using masked arrays (`np.ma`), with empty/unaligned slots masked out.

**Touch:** [`plugin/scripting/`](../plugin/scripting/) or [`plugin/calc/calc_addin_data.py`](../plugin/calc/calc_addin_data.py) — optional auto-align when `len(data_list) > 1` and shapes differ.

**Tests:** `tests/scripting/` — shape transforms on mismatched 1D/2D inputs.

**Not the same as:** Multi-range wire format (already shipped).

---

#### Venv ↔ Calc write-back (Neptyne-style)

**Problem:** `=PYTHON()` scripts assign to `result` only. They cannot write arbitrary ranges back to the grid from inside the venv without the chat agent calling `write_formula_range` in a second phase.

**Consider:** Same work as [venv ↔ LibreOffice tool RPC](enabling_numpy_in_libreoffice.md#venv--libreoffice-tool-rpc) in enabling_numpy §7. Implement RPC first (`writeragent_api.py` stubs today); optional sugar API (e.g. `calc.write_range("A1:B2", matrix)`) afterward.

**Risks:** Recalc loops if script writes trigger upstream recalc; needs main-thread UNO dispatch and mutex (see [`manipulator.py`](../plugin/calc/manipulator.py) patterns).

**Tests:** `tests/uno/` with `@native_test` for thread-safe batch `setValues`.

---

#### Shared-kernel dependency / invalidation (optional)

**Problem:** With shared globals, Calc's DAG tracks `data` cell references, not Python global mutations. A downstream cell may read stale namespace state if an upstream cell changed a global without passing it through `data`.

**Consider:** AST read/write analysis per cell formula to build an internal dependency graph and invalidate dependents when globals change.

**Touch:** [`session_manager.py`](../plugin/scripting/session_manager.py), recalc semantics in [python-in-excel-dev-plan.md](python-in-excel-dev-plan.md).

**Priority:** Defer until users report stale downstream cells in shared-kernel workbooks.

---

#### Blank vs NaN semantics on ingress

**Problem:** Empty Calc cells become `np.nan` in numeric `split_grid` paths; naive `np.mean(data)` returns NaN and egress can silently blank cells.

**Status:** Already planned — [calc-blanks-vs-nans.md](calc-blanks-vs-nans.md). Do not duplicate that design here.

---

### Tier B — Analyst workflow (larger scope)

#### Mito-style action recorder

**Problem:** Analysts repeat sort, filter, pivot, and chart steps manually; no reproducible pandas script is emitted.

**Consider:** Calc modify listeners that append GUI operations to a stack and compile equivalent pandas code into the Monaco buffer.

**Touch:** New module under [`plugin/calc/`](../plugin/calc/); stream output via [`editor_host.py`](../plugin/scripting/editor_host.py).

**Risks:** Generated code must pass AST sandbox validation before run.

**Priority:** Exploratory — large UX + listener surface.

---

#### Dynamic sidebar controls from sheet context

**Problem:** Cloud add-ons (e.g. A2UI + Gemini) generate interactive forms from spreadsheet context and log responses back to the grid.

**Consider:** LLM-generated sidebar control layouts bound to active sheet ranges.

**Priority:** Low — overlaps chat tool loop and future Calc UI unless product requests it.

---

### Tier C — Performance / scale (tracked elsewhere)

| Item | Where tracked |
|------|----------------|
| Serialization performance (payload cache, Cython pack, profiling) | [numpy-serialization.md — Future work](numpy-serialization.md#future-work--serialization-performance) |
| LRU eviction of large DataFrames in shared kernel | **New consideration:** bounded memory for long-lived workbook sessions — distinct from payload decode cache. Low priority until OOM reports. |
| Dynamic array spill, DataFrame → rich table, JSON `result` envelope | [enabling_numpy §7 Calc UX](enabling_numpy_in_libreoffice.md#calc-ux-and-output-enhancements) |
| Python Object cards, diagnostics pane, formula-bar Jedi, AI code synthesis | [python-in-excel-dev-plan.md](python-in-excel-dev-plan.md) Phases 5–7 |
| Remaining scientific domains (Forecast, Text, Optimization, Geo, Audio) | [enabling_numpy scientific roadmap](enabling_numpy_in_libreoffice.md#scientific-domain-roadmap-trusted-helpers) |

---

## Non-goals

- Google Sheets / gspread / cloud sync integration — local-first product.
- Cloud `=AI()` cell function parity — non-deterministic text in cells conflicts with reproducible spreadsheets.
- Re-documenting AST sandbox, FSM, sidebar streaming, or pickle IPC — see [enabling_numpy_in_libreoffice.md](enabling_numpy_in_libreoffice.md) and [AGENTS.md](../AGENTS.md).

---

## Related docs

- [enabling_numpy_in_libreoffice.md](enabling_numpy_in_libreoffice.md) — venv bridge, `=PYTHON()`, deferred roadmap
- [python-in-excel-dev-plan.md](python-in-excel-dev-plan.md) — phased Calc parity plan
- [python-in-excel-ideas.md](python-in-excel-ideas.md) — Excel feature mapping and enhancement backlog
- [calc-blanks-vs-nans.md](calc-blanks-vs-nans.md) — blank vs NaN wire semantics
- [calc-specialized-toolsets.md](calc-specialized-toolsets.md) — pivot, filters, charts via chat tools
- [numpy-serialization.md](numpy-serialization.md) — IPC protocol and serialization benchmarks

**Inspiration (external):** [Quadratic — auditable Python cells](https://www.quadratichq.com/python) · [Mito — spreadsheet ops to pandas code](https://www.trymito.io/) · [Neptyne — bidirectional cell binding](https://www.ycombinator.com/companies/neptyne)
