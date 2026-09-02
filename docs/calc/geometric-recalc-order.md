# Geometric Recalc Order — PM / Senior Dev Review

**Status:** Proposal only. Not implemented. Review before scheduling.

**Audience:** Product, senior engineers, and a future implementer. This is the design to accept, reject, or narrow — not a coding checklist.

**Related:** [Enabling NumPy & Python](../enabling_numpy_in_libreoffice.md) (session modes, auto-spill), [Microsoft `=PY` design stance](../scripting/ms-py-compatibility.md) (why we refuse Excel co-volatility), [Calc `=PY()` data shapes](py-data-shapes.md) (`data` / `ranges` arity).

---

## Executive summary

Shared-kernel `=PY()` already persists one Python namespace per workbook, but Calc may evaluate those cells in **any order**. Authors today must pass the upstream cell as a `data` argument so the DAG runs precedents first. That is correct and cheap — and easy to forget.

**Geometric Recalc Order** is an opt-in Settings → Python flag. When on, LibrePy treats the sheet’s `=PY()` cells as a **list in sheet order** (row then column — the same order the Python sidebar already uses) and **auto-attaches only the previous list entry** as an extra formula field. Calc then runs A before B because B’s formula literally names A. Partial recalc stays intact: edit A, only A and the chain after it dirty.

This is **not** Excel co-volatility (re-run every Python cell when any one is dirty). It is the existing `data`-as-dependency-edge idea, applied automatically to one predecessor.

**Hard part:** inserting a new `=PY()` cell in the middle of the list. The successor’s predecessor field must be rewritten to the new cell. Those writes **must happen outside recalc**, using the same deferred, undo-isolated pattern as auto-spill (`perform_deferred_spill` + short timer). Writing other cells from inside the add-in re-enters the formula engine.

**Difficulty:** medium for someone who already knows the spill / formula-edit path — on the order of **one careful week**, not a core-Calc project. The risk is semantic (`data` arity, insert/delete, undo), not “can we write cells after recalc.”

**Recommendation:** accept the flag as an **opt-in Shared-kernel companion**, default **off**. Gate implementation on the two decisions in [Open questions](#open-questions): whether the geometric arg is precedent-only, and whether the list is per-sheet row-major or per-column runs.

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

**When off:** no attach, no rewrite. Existing user-written `data` args stay. Optional one-shot strip of *our* geometric args on disable — [open question](#open-questions).

**Most valuable with Shared kernel.** Isolated cells do not share names, so order-only precedents do nothing useful unless we also pass the previous *value* into `data` (usually the wrong default). Treat Isolated + this flag as a no-op or a settings warning, not a second product.

---

## 3. Mechanism (senior-dev view)

### 3.1 The list

`list_python_cells_on_sheet` already returns `PythonCellInfo` sorted by `(row, column)`. That **is** the geometric list.

**MVP list (recommended):** all PY cells on the **active sheet**, row-major. Cross-sheet predecessors are out of scope (sheet-qualified refs + sheet insert/rename). Workbook-global order (Sheet1 then Sheet2) is a later option, not required to prove the idea.

**Cap:** discovery stops at 100 PY cells / 50k scanned (`_MAX_PYTHON_CELLS_FOUND`). Geometric order must honor the same cap or raise it deliberately — do not silently chain a truncated list.

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
| Flag turned **on** | One-shot attach for the current sheet (or all sheets — [open question](#open-questions)) |
| Flag turned **off** | Optional strip of geometric fields only |
| Monaco / native **Save** of a PY cell | New or edited formula may need a predecessor; neighbors may need retarget |
| `XModifyListener` on sheets that already have PY cells | Insert/delete/clear; **reuse** the spill listener pattern (`CalcSpillModifyListener`) or a sibling listener — do not register a third sheet-wide listener if one can dispatch both jobs |
| Document open | Cheap: if flag on, reconcile once so files authored with the flag stay consistent |

Do **not** rewrite from inside the add-in just because this cell is evaluating.

---

## 4. Data binding — do not shadow `data`

**This is the highest-risk product decision.**

Today ([data shapes](py-data-shapes.md)):

- One trailing arg → Python `data` is that `CalcRange`.
- Two or more → `data` is the **list** (same as `ranges`).

If A2 is `=PY("np.mean(data)"; B1:B10)` and we append `;A1`, then `data` suddenly becomes a list and `np.mean(data)` breaks.

**Recommended contract (for review):**

The geometric predecessor is a **Calc-only ordering token**. The add-in **strips it** before packing worker `data` / `ranges`. User-authored args keep today’s arity.

Implementation sketch (not for this review to implement):

- Mark the last trailing arg as geometric when it is a **single cell** that is the previous PY address in the current list (or store a reserved suffix — avoid a new IDL argument).
- `function.py` drops that arg from the payload sent to the venv.
- Isolated/Shared both see the same `data` they wrote.

**Rejected for MVP:** injecting the previous cell’s *value* into `data` / `data[-1]`. That changes Python semantics and fights existing scripts.

**Also rejected for MVP:** a third IDL parameter. Rebuilds `.rdb`s for both OXTs; Collabora/Excel import get another arity case. A trailing A1 field is enough.

Code-in-cell form (`=PY($A$1; B1:B10)`) must keep `$A$1` as the code arg and still accept a geometric trailing field.

---

## 5. User-visible behavior

**What the user sees:** formulas gain a trailing cell ref they did not type. That is the feature (Calc must see it). Document it in Settings helper text and the hub session-modes page when this ships.

**What they should not see:** extra undo steps, `#REF!` storms after insert, `data` breaking on cells that already pass ranges, or a full-sheet PY re-run after one edit.

**LibrePy sidebar:** the existing cell list is already geometric. A later UX nicety (not MVP) is a small “depends on A1” hint. Do not block the flag on sidebar chrome.

**Excel import:** the OOXML rewriter must **not** invent geometric edges ([ms-py already says this](../scripting/ms-py-compatibility.md)). If the user turns the flag on after import, the deferred pass attaches them. Export should strip geometric-only args or leave them as extra `_xlws.PY` deps — decide at implement time; default to **leave them** (they are valid precedents).

---

## 6. Difficulty and reuse

| Piece | New? | Reuse |
|-------|------|--------|
| Settings checkbox | Small | `module.yaml` + existing Settings dialog |
| Discover PY cells in order | None | `cell_discovery.list_python_cells_on_sheet` |
| Parse / rebuild `=PY(code; args)` | Small helper to splice one address | `formula_edit.py` |
| Deferred UI-thread writes + undo hide | Small | `perform_deferred_spill`, `_undo_lock`, Timer 0.1s |
| Sheet modify | Small | `CalcSpillModifyListener` or sibling |
| Strip geometric arg from worker `data` | Medium | `function.py` / `calc_addin_data.py` |
| Insert-in-middle repair | Medium | Pure list-diff + `setFormula` |
| Tests | Required | pytest on list-diff + formula splice; UNO for insert-row + deferred rewrite |

**Not required:** LibreOffice core patches, co-volatility, IDL change, venv protocol change, chat tools.

**Rough effort:** 3–5 days for the happy path (flag + attach + deferred repair on one sheet) if the `data`-strip rule is agreed first; another 2–3 days for insert/delete/undo/flag-toggle edges and tests. Slips if we argue `data` arity in code instead of in this review.

Compare to **full Excel co-volatility:** multiple engineer-months in `sc/`, high regression risk. This flag is the cheap 80%.

---

## 7. Risks

| Risk | Mitigation |
|------|------------|
| Shadowing `data` (arity flip) | Precedent-only strip ([§4](#4-data-binding--do-not-shadow-data)) |
| Rewrite during recalc | Same ban as spill; deferred only |
| Undo fragmentation | `_undo_lock` / hidden undo, same as spill |
| Infinite rewrite loop | Idempotent desired-vs-actual; skip if already correct |
| Calc already adjusted refs on row insert | Repair pass compares desired predecessor, does not blindly rewrite |
| User already passed the previous cell | No duplicate field |
| User passed a **different** single-cell last arg (real data) | Must not treat every last cell-ref as geometric — only when it matches the computed previous PY address, or when we wrote a marker we can recognize |
| Circular refs from user forward-refs | Calc reports circular; we never attach a later cell |
| 100-cell discovery cap | Document or raise; never chain a partial list as if complete |
| Shared + Isolated confusion | Flag helper: “Used with Shared kernel”; Isolated no-op |
| Collabora Online | Desktop LibrePy first. Online has no deferred UNO spill-style writes in the same way; do not promise this flag in jail-safe compute until desktop is boring |

---

## 8. Suggested phases (when scheduled)

**Phase 0 — Review (this doc).** Lock [open questions](#open-questions). No code.

**Phase 1 — Pure list + formula splice.** Unit tests only: given a list of addresses + current formulas, compute the patch. No UNO. This is the whole algorithm.

**Phase 2 — Flag + attach on save / flag-on.** Monaco and native cell save call the splicer; apply on the UI thread after save (save is already outside recalc). Settings default off.

**Phase 3 — Deferred repair on insert/delete.** Modify listener + spill-like timer. UNO tests: three-cell column, insert PY in the middle, successor’s field updates; delete; undo.

**Phase 4 — Strip geometric arg from worker ingress.** Tests that `=PY("np.mean(data)"; B1:B10)` still sees a single `CalcRange` after attach.

**Non-goals until someone asks:** cross-sheet chains, workbook-global order, Isolated value-piping, sidebar annotations, Excel export special-case, raising the 100-cell cap.

---

## 9. Open questions

Reviewers should answer these explicitly. Implementation should not guess.

1. **Precedent-only vs value-in-`data`?** Recommendation: precedent-only. Confirm.
2. **List scope:** all PY cells on the sheet (row-major), or only **contiguous runs** in one column? Recommendation: all PY cells on the sheet — matches “the list” and the sidebar. Contiguous-column-only is smaller but surprises users who put the next step in C1.
3. **Isolated mode:** no-op + helper text, or hide the checkbox unless Shared is selected?
4. **Flag off:** leave attached refs (they are harmless DAG edges) or strip the ones we added? Recommendation: **leave them** (simplest; file stays valid). Strip only if we have a reliable marker.
5. **How we recognize “our” field** vs a user-typed last cell-ref that happens to be the previous PY cell. Recommendation: if it already *is* the correct predecessor, treat as satisfied (no rewrite). If the last arg is some other single cell, **append** the predecessor rather than replacing — unless that last arg *is* an *old* predecessor after insert, in which case **replace**. Phase 1 tests should encode this table.
6. **All sheets vs active sheet** on flag-on. Recommendation: all sheets in the workbook, each chained independently.

---

## 10. Test plan (when implemented)

**Unit (`tests/calc/python/`, match the new module name):**

- List-diff: empty, one cell, two cells, insert in middle, delete middle, delete first, reorder.
- Formula splice: no args; existing range args preserved; code-in-cell `$A$1`; already-correct predecessor; stale predecessor replaced; user extra cell-ref appended not overwritten when it is not the old predecessor.
- `data` strip: host payload arity unchanged when a geometric token is present.

**UNO (`test_*_uno.py`):**

- Shared kernel, flag on: A3 reads a name assigned in A1 without a user-typed `data` ref; result is stable across F9.
- Insert a PY row between two chained cells; after the deferred pass, successor formula names the new cell; values update on next recalc.
- Flag off: no new attaches (existing refs stay if we chose “leave”).
- Isolated + flag on: documented no-op (or warning), no `data` breakage.
- Undo: user types a new PY cell, geometric rewrite does not add a second undo step (hidden context).
- `#SPILL!` / auto-spill still works on a chained origin cell.

Do not run the full suite until this is implemented. Phase 1 is mockable without soffice.

---

## 11. Docs to update when this ships (not now)

- Hub [session modes](../enabling_numpy_in_libreoffice.md#session-modes-and-recalc-semantics): one short subsection + Settings table row.
- [ms-py-compatibility](../scripting/ms-py-compatibility.md): pointer — “opt-in geometric *chain*, still not co-volatility.”
- Settings helper in `module.yaml`.
- This file: flip Status to shipped and drop open questions that were decided.

Do not touch `AGENTS.md` unless the rewrite-outside-recalc rule needs to become a global invariant (it is already implied by the spill / `=PY()` contract).
