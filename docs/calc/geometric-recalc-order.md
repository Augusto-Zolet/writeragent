# Geometric Recalc Order — PM / Senior Dev Review

**Status:** Proposal under review. Not implemented. Product calls in [§9](#9-open-questions) are **open** — each lists alternatives and a current opinion.

**Related:** [Enabling NumPy & Python](../enabling_numpy_in_libreoffice.md) (session modes, auto-spill), [Microsoft `=PY` design stance](../scripting/ms-py-compatibility.md) (why we refuse Excel co-volatility), [Calc `=PY()` data shapes](py-data-shapes.md) (`data` / `ranges` arity).

---

## Executive summary

Shared-kernel `=PY()` already persists one Python namespace per workbook, but Calc may evaluate those cells in **any order**. Authors today must pass the upstream cell as a `data` argument so the DAG runs precedents first. That is correct and cheap — and easy to forget.

**Geometric Recalc Order** is an opt-in Settings → Python flag. When on, LibrePy treats the sheet’s `=PY()` cells as a **list in sheet order** (row then column — the same order the Python sidebar already uses) and **auto-attaches only the previous list entry** as an extra formula field. Calc then runs A before B because B’s formula literally names A. Partial recalc stays intact: edit A, only A and the chain after it dirty.

This is **not** Excel co-volatility (re-run every Python cell when any one is dirty). It is the existing `data`-as-dependency-edge idea, applied automatically to one predecessor.

**Hard part:** inserting a new `=PY()` cell in the middle of the list. The successor’s predecessor field must be rewritten to the new cell. Those writes **must happen outside recalc**, using the same deferred, undo-isolated pattern as auto-spill (`perform_deferred_spill` + short timer). Writing other cells from inside the add-in re-enters the formula engine.

**Difficulty:** medium for someone who already knows the spill / formula-edit path — on the order of **one careful week**, not a core-Calc project. The risk is semantic (`data` arity, insert/delete, undo), not “can we write cells after recalc.”

**Current opinion:** accept the flag as an **opt-in Shared-kernel companion**, default **off**. The two product calls that most affect implementation are still open in [§9](#9-open-questions): whether the geometric arg is **precedent-only** (stripped before packing worker `data`), and whether the list is **all PY cells on the sheet, row-major**. The rest of this doc describes the design under those current opinions.

---

## 1. Why this exists

### The gap users hit

| Mode | Persistence | Order |
|------|-------------|--------|
| Isolated (default) | Fresh namespace per cell | Irrelevant for Python globals |
| Shared kernel today | One workbook namespace | **Only** via explicit `data` refs (or luck) |
| Excel `=PY` | One workbook namespace | Row-major + **re-run all PY cells** (co-volatility) |

A typical Shared-kernel pipeline is a **vertical list**:

```text
A1  =PY("df = load()")
A2  =PY("df = clean(df)")
A3  =PY("result = df.describe()")
```

Without `data` edges, Calc may run A3 before A1. The current docs tell authors to write `=PY("…"; A1)` on A2. Geometric Recalc Order does that attach automatically.

### What we will not do

Do **not** implement Excel co-volatility. That needs a workbook-global PY barrier in `sc/`, flip-flop with non-PY formulas, and N Python executions per keystroke. [ms-py-compatibility §5.2](../scripting/ms-py-compatibility.md#52-co-volatility-a-second-calculation-mode) already rejected it. Geometric order reuses Calc’s DAG: one extra precedent per cell, dirty subgraph only.

---

## 2. Product definition

**Flag name (UI):** Geometric Recalc Order  
**Config key (proposed):** `scripting.python_geometric_recalc_order`  
**Type:** bool, default **false**  
**Surface:** Settings → Python, next to session mode / auto-spill (`plugin/scripting/module.yaml`). Same checkbox path as `python_auto_spill`. LibrePy **and** WriterAgent.

**When on:**

1. Discover `=PY()` / `=PYTHON()` cells (reuse [`cell_discovery.py`](../../plugin/calc/python/cell_discovery.py) — already sorted **row then column**).
2. For each cell after the first in that list, ensure the formula’s trailing fields include **exactly one geometric predecessor**: the previous list entry’s address.
3. Leave user-authored ranges alone (see [§4 Data binding](#4-data-binding--do-not-shadow-data)).
4. On insert / delete / move that changes who “previous” is, **rewrite** the affected successor formulas — **deferred**, not during add-in evaluation.

**When off:** no attach, no rewrite. Existing user-written `data` args stay. Geometric refs already attached **stay** (they are valid DAG edges). No strip-on-disable under the current opinion ([§9.4](#94-flag-turned-off)).

**Most valuable with Shared kernel.** Isolated cells do not share names, so order-only precedents do nothing useful for Python globals. Isolated + this flag is a **no-op** for Python semantics (the checkbox stays visible; helper text says it is used with Shared kernel). Do not hide the checkbox when Isolated is selected — current opinion; see [§9.3](#93-isolated-mode--checkbox).

---

## 3. Mechanism (senior-dev view)

### 3.1 The list

`list_python_cells_on_sheet` already returns `PythonCellInfo` sorted by `(row, column)`. That **is** the geometric list.

**Proposed list (current opinion, [§9.2](#92-what-is-the-list) / [§9.6](#96-flag-on--document-open-scope)):** all PY cells on **each sheet**, row-major, each sheet chained **independently**. Flag-on / document-open reconcile every sheet (`list_python_cells_in_doc(..., active_sheet_only=False)`). Insert/delete repair only the **modified** sheet. Cross-sheet predecessors are out of scope (sheet-qualified refs + sheet insert/rename). Workbook-global order (Sheet1 then Sheet2) is a later option, not required to prove the idea.

**Cross-cluster chaining (current opinion, [§9.2](#92-what-is-the-list)):** two independent PY clusters on one sheet (A1:A5 and D1:D5) become one chain — D1 waits on A5. That slightly over-dirties the D column when A3 changes. Correctness is fine; users who care can turn the flag off and write explicit `data` refs. Spatial clustering is an alternative, not the current lean.

**Cap:** discovery stops at 100 PY cells / 50k scanned (`_MAX_PYTHON_CELLS_FOUND`). Geometric order must honor the same cap or raise it deliberately — do not silently chain a truncated list. A 100-cell chain is serial (venv IPC per dirty cell); that is the price of order, not a new cliff. Document the cap; do not raise it in this feature.

### 3.2 Auto-attach is a formula field, not a Python parse

Calc only orders cells that **name** each other in the formula. We do **not** parse Python for `df = …`. We rewrite:

```text
A2:  =PY("df = clean(df)")          →  =PY("df = clean(df)"; A1)
A3:  =PY("result = df.describe()")   →  =PY("result = df.describe()"; A2)
```

Reuse [`parse_python_formula`](../../plugin/calc/python/formula_edit.py) / `rebuild_python_formula_with_data` / `build_data_suffix`. Do not invent a second formula serializer.

The first cell in the list gets **no** predecessor. Cycles cannot appear if we only ever attach the previous entry in a total order.

### 3.3 Why “just the previous” is enough

A chain A1→A2→A3→A4 is enough for Calc: dirty A2 recalculates A2, then A3, then A4. We do **not** attach A1 onto every later cell. One field, one rewrite on insert.

### 3.4 Insert / delete / move — the only reason this is not a one-liner

Calc will shift A1-style refs when rows move, but it will **not** retarget “previous PY cell” when a **new PY formula** appears between two existing ones.

Example: list is A1, A3. A3 has `;A1`. User inserts a PY cell at A2.

| Cell | Before | After repair |
|------|--------|----------------|
| A1 | `=PY("…")` | unchanged |
| A2 | `=PY("…")` (new) | `=PY("…"; A1)` |
| A3 | `=PY("…"; A1)` | `=PY("…"; A2)` |

Delete A2: A3’s predecessor must become A1 again (or empty if A3 is now first).

Row insert that only **moves** existing PY cells: Calc’s own reference adjust may already be correct. The deferred pass should be **idempotent**: recompute desired predecessor per cell, rewrite only when the geometric field differs.

### 3.5 Writes must be outside recalc (same as auto-spill)

`=PY()` evaluation is a **synchronous add-in** in Calc’s recalc. Invariants already in the tree:

- Do not mutate other cells from `execute_python_addin` / `finalize_python_return`.
- Do not `processEventsToIdle` during recalc (re-enters the engine → `#VALUE!`).
- Auto-spill already defers neighbor writes: collision check sync, then `threading.Timer(0.1)` → `perform_deferred_spill` on the **UI thread**, inside `_undo_lock` (`enterHiddenUndoContext` / `lock`).

Geometric rewrites use that same shape:

1. **Detect** (modify listener, Monaco/formula save, flag toggle) that the geometric list changed.
2. **Compute** a small patch: cells whose predecessor field is wrong.
3. **Schedule** a deferred UI-thread job (reuse the 0.1s timer / drain pattern; do not start a raw thread — `run_in_background` + main-thread apply, or the existing Timer-on-main pattern in `function.py`).
4. **Apply** `setFormula` under `_undo_lock` so Ctrl+Z still undoes the user’s edit, not a stray “rewrite A3” undo step.
5. **Guard** like spill: same doc URL / lifecycle key; skip if the origin formula is no longer what we expected.

`setFormula` on a successor will dirty that cell and start another recalc. That is intended. The deferred job must be **re-entrant-safe**: a rewrite pass that finds nothing to do is a no-op; do not loop “rewrite → recalc → rewrite.”

Yellow recalc / off-main formula groups: same contract as spill and session lookup — **no UNO desktop/document queries from a recalc worker**. Discovery + rewrite only on the UI thread after the pass.

### 3.6 When to run the repair pass

| Trigger | Why |
|---------|-----|
| Flag turned **on** | One-shot attach for **all sheets**, each chained independently |
| Flag turned **off** | Stop maintaining refs; **leave** existing geometric fields |
| Monaco / native **Save** of a PY cell | New or edited formula may need a predecessor; neighbors may need retarget |
| `XModifyListener` on sheets that already have PY cells | Insert/delete/clear. Prefer a **sibling** `CalcGeometricModifyListener` (spill listener is tightly coupled to `SPILL_REGISTRY`). If a third `addModifyListener` is undesirable, factor a one-sheet dispatcher that fans out to spill cleanup and geometric repair — do not merge the two jobs into one class. |
| Document open | Cheap: if flag on, reconcile once so files authored with the flag stay consistent |

Do **not** rewrite from inside the add-in just because this cell is evaluating.

---

## 4. Data binding — do not shadow `data`

**This is the highest-risk product call.** Current opinion is **precedent-only** ([§9.1](#91-does-the-geometric-arg-change-python-data)).

Today ([data shapes](py-data-shapes.md)):

- One trailing arg → Python `data` is that `CalcRange`.
- Two or more → `data` is the **list** (same as `ranges`).

`calc_addin_args_from_split` in [`calc_addin_data.py`](../../plugin/calc/calc_addin_data.py) is the flip: `len(args) == 1` returns one 2D grid; `len(args) >= 2` returns a **list** of grids. If A2 is `=PY("np.mean(data)"; B1:B10)` and we append `;A1`, then `data` suddenly becomes a list and `np.mean(data)` breaks. That is the common case, not a corner.

**Proposed contract under opinion A:**

The geometric predecessor is a **Calc-only ordering token**. The add-in **strips it** before packing worker `data` / `ranges`. User-authored args keep today’s arity. Isolated and Shared both see the same `data` they wrote.

**Where to strip:** after `split_python_addin_data_args` and **before** `calc_addin_args_from_split` / `pack_calc_data_for_wire` in `_execute_python_addin_impl` ([`function.py`](../../plugin/calc/python/function.py)). The geometric token is the last trailing arg when it is a **single cell** that matches the computed previous PY address (or, at eval time, a 1×1 last arg that is itself a PY cell — see [§9.5](#95-how-do-we-recognize-our-field)). Do not invent a reserved formula suffix or a third IDL argument unless review picks those alternatives.

**Alternatives (not the current lean):** injecting the previous cell’s *value* into `data` / `data[-1]` (changes Python semantics and fights existing scripts), or a third IDL parameter (rebuilds `.rdb`s for both OXTs; Collabora/Excel import get another arity case). A trailing A1 field is enough if we strip it.

Code-in-cell form (`=PY($A$1; B1:B10)`) must keep `$A$1` as the code arg and still accept a geometric trailing field.

---

## 5. User-visible behavior

**What the user sees:** formulas gain a trailing cell ref they did not type. That is the feature (Calc must see it). Document it in Settings helper text and the hub session-modes page when this ships.

**What they should not see:** extra undo steps, `#REF!` storms after insert, `data` breaking on cells that already pass ranges, or a full-sheet PY re-run after one edit.

**LibrePy sidebar:** the existing cell list is already geometric. A later UX nicety (not MVP) is a small “depends on A1” hint. Do not block the flag on sidebar chrome.

**Excel import:** the OOXML rewriter must **not** invent geometric edges ([ms-py already says this](../scripting/ms-py-compatibility.md)). If the user turns the flag on after import, the deferred pass attaches them. Export **leaves** geometric-only args as extra `_xlws.PY` deps (they are valid precedents). Do not special-case strip on export for MVP.

---

## 6. Difficulty and reuse

| Piece | New? | Reuse |
|-------|------|--------|
| Settings checkbox | Small | `module.yaml` + existing Settings dialog |
| Discover PY cells in order | None | `cell_discovery.list_python_cells_on_sheet` / `list_python_cells_in_doc` |
| Parse / rebuild `=PY(code; args)` | Small helper to splice one address | `formula_edit.py` |
| Deferred UI-thread writes + undo hide | Small | `perform_deferred_spill`, `_undo_lock`, Timer 0.1s |
| Sheet modify | Small | Sibling `CalcGeometricModifyListener`; optional one-sheet dispatcher shared with spill |
| Strip geometric arg from worker `data` | Medium | `function.py` / `calc_addin_data.py` — strip **before** `calc_addin_args_from_split` |
| Insert-in-middle repair | Medium | Pure list-diff + `setFormula` |
| Tests | Required | pytest on list-diff + formula splice; UNO for insert-row + deferred rewrite |

**Not required:** LibreOffice core patches, co-volatility, IDL change, venv protocol change, chat tools.

**Rough effort:** 3–5 days for the happy path (flag + attach + deferred repair on one sheet) once [§9.1](#91-does-the-geometric-arg-change-python-data) is settled; another 2–3 days for insert/delete/undo/flag-toggle edges and tests.

Compare to **full Excel co-volatility:** multiple engineer-months in `sc/`, high regression risk. This flag is the cheap 80%.

---

## 7. Risks

| Risk | Mitigation |
|------|------------|
| Shadowing `data` (arity flip) | Precedent-only strip ([§4](#4-data-binding--do-not-shadow-data); [§9.1](#91-does-the-geometric-arg-change-python-data)) |
| Rewrite during recalc | Same ban as spill; deferred only |
| Undo fragmentation | `_undo_lock` / hidden undo, same as spill (`test_calc_spill_undo_lock`) |
| Infinite rewrite loop | Idempotent desired-vs-actual; skip if already correct |
| Calc already adjusted refs on row insert | Repair pass compares desired predecessor, does not blindly rewrite |
| User already passed the previous cell | No duplicate field ([§9.5](#95-how-do-we-recognize-our-field)) |
| User passed a **different** single-cell last arg (real data) | Append, do not replace, unless that last arg is a **stale** geometric predecessor |
| Two independent PY clusters on one sheet | Current opinion: one row-major chain; slightly over-dirties the later cluster ([§9.2](#92-what-is-the-list)) |
| Circular refs from user forward-refs | Calc reports circular; we never attach a later cell |
| 100-cell discovery cap | Honor it; never chain a partial list as if complete |
| Shared + Isolated confusion | Checkbox always visible; helper: “Used with Shared kernel”; Isolated is a no-op ([§9.3](#93-isolated-mode--checkbox)) |
| Collabora Online | Desktop LibrePy first. Online has no deferred UNO spill-style writes in the same way; do not promise this flag in jail-safe compute until desktop is boring |

---

## 8. Suggested phases (when scheduled)

**Phase 0 — Review (this doc).** Product calls in [§9](#9-open-questions) are open. No code until review picks (or confirms) the current opinions.

**Phase 1 — Pure list + formula splice.** Unit tests only: given a list of addresses + current formulas, compute the patch. No UNO. This is the whole algorithm. Encode the [§9.5](#95-how-do-we-recognize-our-field) table.

**Phase 2 — Flag + attach on save / flag-on.** Monaco and native cell save call the splicer; apply on the UI thread after save (save is already outside recalc). Settings default off. Flag-on walks **all sheets**.

**Phase 3 — Deferred repair on insert/delete.** Sibling modify listener + spill-like timer. UNO tests: three-cell column, insert PY in the middle, successor’s field updates; delete; undo.

**Phase 4 — Strip geometric arg from worker ingress.** Tests that `=PY("np.mean(data)"; B1:B10)` still sees a single `CalcRange` after attach.

**Non-goals until someone asks:** cross-sheet chains, workbook-global order, Isolated value-piping, sidebar annotations, Excel export special-case, raising the 100-cell cap, strip-on-disable, spatial clustering of independent PY groups.

---

## 9. Open questions

Please mark these up. Each item is a question, the real alternatives, and a current opinion — not a closed contract.

### 9.1 Does the geometric arg change Python `data`?

**Question:** After we append a predecessor cell so Calc orders the DAG, what does the worker see in `data` / `ranges`?

**Alternatives:**

- **A — Precedent-only.** The geometric arg is a Calc DAG token. Strip it before packing worker `data` / `ranges`. Do not inject the previous cell’s value.
- **B — Value-in-`data`.** Inject the previous cell’s value into `data` / `data[-1]`.
- **C — Third IDL parameter.** A dedicated ordering argument, not a trailing A1 field. Rebuilds `.rdb`s for both OXTs; Collabora/Excel import get another arity case.

**Current opinion: A.** `calc_addin_args_from_split` flips arity at two args. Value-in-`data` would break `np.mean(data)` on every cell that already passes one range — the common case. A trailing A1 field is enough if we strip it.

### 9.2 What is “the list”?

**Question:** Which `=PY()` cells are chained, and in what order?

**Alternatives:**

- **A — All PY cells on the sheet, row-major.** One chain per sheet. Independent clusters (A1:A5 and D1:D5) become one chain — D1 waits on A5.
- **B — Contiguous column only.** Only cells stacked in the same column (or a contiguous block) are chained.
- **C — Spatial clustering.** Detect independent PY groups by proximity and chain within each group.
- **D — Workbook-global.** Sheet1 then Sheet2 (and so on), one chain for the whole file.

**Current opinion: A.** Matches `list_python_cells_on_sheet` and the sidebar. Contiguous-column-only would surprise authors who put the next step in C1. Spatial clustering and workbook-global order can wait; they are not required to prove the idea. Over-dirtying the later cluster is acceptable; users who care can turn the flag off and write explicit `data` refs.

### 9.3 Isolated mode + checkbox?

**Question:** What should Settings do when session mode is Isolated?

**Alternatives:**

- **A — Always visible; Isolated is a no-op.** Helper text says the flag is used with Shared kernel.
- **B — Hide the checkbox** when Isolated is selected.

**Current opinion: A.** Hiding the box when Isolated is selected couples two settings and looks like a bug when the box disappears. Isolated cells have independent namespaces, so order-only precedents do nothing useful for Python globals. Precedent-only strip ([§9.1](#91-does-the-geometric-arg-change-python-data) A) means Isolated `data` is unchanged.

Helper: “Ensures PY cells evaluate in sheet order. Most useful with Shared kernel.”

### 9.4 Flag turned off?

**Question:** What happens to geometric refs already attached when the user turns the flag off?

**Alternatives:**

- **A — Leave attached refs.** Stop attaching and stop repairing. The refs stay as valid DAG edges.
- **B — Strip-on-disable.** Rewrite formulas to remove the geometric field.

**Current opinion: A.** After a precedent-only strip they do not change Python behavior. Strip-on-disable needs a reliable “ours vs user-typed” marker; do not build that unless review wants B.

### 9.5 How do we recognize “our” field?

**Question:** When rewriting or stripping, how do we tell a geometric predecessor from a user-typed last arg?

**Alternatives:**

- **A — Match the computed predecessor.** No reserved suffix and no document UDProp. Desired predecessor is the previous entry in the sheet’s row-major PY list (or none if first). Compare the last trailing arg using the table below.
- **B — Reserved formula suffix.** A marker that is unambiguously ours (and visible in the formula bar).
- **C — Workbook UDProp** listing cells we attached. Useful later if someone wants strip-on-disable ([§9.4](#94-flag-turned-off) B).
- **D — Third IDL argument.** Same as [§9.1](#91-does-the-geometric-arg-change-python-data) C — the field is not a trailing `data` arg at all.

**Current opinion: A** for a first version. C only if someone later wants strip-on-disable.

**Proposed heuristic under A.** Compare the last trailing arg:

| Scenario | Last arg | Desired predecessor | Action |
|----------|----------|---------------------|--------|
| No args | — | A1 | Append `;A1` |
| User range `B1:B10` | range | A1 | Append (`;B1:B10;A1`) |
| Already correct | single cell = desired | A1 | No-op |
| Stale predecessor after insert | single cell ≠ desired, and last arg **was** the old geometric predecessor | A2 | Replace `;A1` → `;A2` |
| User single-cell data `C5` (not a PY cell, not the old predecessor) | single cell ≠ desired | A1 | Append (`;C5;A1`) — do not overwrite user data |
| User already passed the previous PY cell as real data | single cell = desired | A1 | No-op (satisfied either way) |

**Eval-time strip** can be slightly looser than the rewrite heuristic: if the last split arg is a 1×1 cell that is itself a PY cell, drop it before packing. False positive (user passed a PY cell as real `data`) is the same case as the last row above — accepted under A.

Phase 1 tests would encode this table if A is confirmed.

### 9.6 Flag-on / document-open scope?

**Question:** When the flag is turned on, or a flagged workbook is opened, which sheets get a chain?

**Alternatives:**

- **A — All sheets, each chained independently.** Opening a workbook with the flag on orders every tab, not whichever sheet happens to be active. `list_python_cells_in_doc(..., active_sheet_only=False)` already walks `doc.getSheets()`. Modify-listener repair stays per-sheet.
- **B — Active sheet only.** Cheaper first pass; other tabs wait until the user visits them or toggles the flag again.

**Current opinion: A.** A flagged file should stay consistent on every tab.

---

## 10. Test plan (when implemented)

**Unit (`tests/calc/python/`, match the new module name):**

- List-diff: empty, one cell, two cells, insert in middle, delete middle, delete first, reorder.
- Formula splice: no args; existing range args preserved; code-in-cell `$A$1`; already-correct predecessor; stale predecessor replaced; user extra cell-ref appended not overwritten when it is not the old predecessor. Encode the [§9.5](#95-how-do-we-recognize-our-field) table.
- `data` strip: host payload arity unchanged when a geometric token is present.

**UNO (`test_*_uno.py`):**

- Shared kernel, flag on: A3 reads a name assigned in A1 without a user-typed `data` ref; result is stable across F9.
- Insert a PY row between two chained cells; after the deferred pass, successor formula names the new cell; values update on next recalc.
- Flag off: no new attaches; existing refs stay.
- Isolated + flag on: no-op for Python semantics; no `data` breakage.
- Undo: user types a new PY cell, geometric rewrite does not add a second undo step (hidden context).
- `#SPILL!` / auto-spill still works on a chained origin cell.

Do not run the full suite until this is implemented. Phase 1 is mockable without soffice.

---

## 11. Docs to update when this ships (not now)

- Hub [session modes](../enabling_numpy_in_libreoffice.md#session-modes-and-recalc-semantics): one short subsection + Settings table row.
- [ms-py-compatibility](../scripting/ms-py-compatibility.md): pointer — “opt-in geometric *chain*, still not co-volatility.”
- Settings helper in `module.yaml`.
- This file: flip Status to shipped.

Do not touch `AGENTS.md` unless the rewrite-outside-recalc rule needs to become a global invariant (it is already implied by the spill / `=PY()` contract).
