# WriterAgent: Evaluation System Development Plan (Internal Edition)

**Current string-harness work** lives in
[`string-harness-upgrade.md`](string-harness-upgrade.md) (core schemas,
inner specialized `LlmClient` loop, document worlds, process/`=PY` score;
no LO ranking). This file is the older hybrid/LO roadmap. Phase F
`=PY` dest rows (`py_refuse_overlap`, `py_no_bulk_read`) and DrawWorld
(flowchart tree + `shape_connect`) are **shipped** in the 17-task pack.

This plan covers the WriterAgent prompt optimization + evaluation system (`scripts/prompt_optimization/`). Ranking is `--backend string` only (17 tasks). Specialized Draw/Calc work uses a bounded inner `LlmClient` loop (`delegate_to_specialized_*` → domain schemas → `specialized_workflow_finished`), not SmolAgents. See `ideas.md` for the original ~50 ideas; the shipped pack is the 17 in `dataset.py`.

## Current Status

The evaluation system lives in `scripts/prompt_optimization/`:
- `run_eval.py` / `run_eval_multi.py`: Main entrypoints (`LlmClient` + tool loop from `llm_chat_eval.py`). Eval does not set sampling temperature (LlmClient / provider default). `run_eval_multi.py` **refuses** a full catalog sweep unless `--models` or `--yes-all-models` is set. `--gold-model` runs only with `--generate-golds`.
- Default: `--backend string` (Writer/Draw/Calc worlds in `eval_worlds.py` via `string_eval_tools.py`). Core schemas from `ToolRegistry.get_schemas`. Flowchart uses `delegate_to_specialized_draw_toolset(domain="shapes")`; sort uses `delegate_to_specialized_calc_toolset(domain="ranges")` then one-column `sort_range` (two stable passes for Product then Revenue).
- `--backend lo`: Headless UNO via `tools_lo.py` (fidelity smoke, not ranking).
- Judging: Hard gate is substring + **result oracles** + **process oracles**. Quality LLM-as-judge runs **after** the hard gate for resume, rewriting, summarization, and the two table tasks. Creative weights are accuracy-first (50/20/30); tables are formatting-heavy after the gate (20/80). Unparseable judge JSON retries once, then keeps the hard pass (`judge_score=None`). Rank by hard pass / agent score / quality; C²/$ is secondary.
- Dataset: 17 tasks in `dataset.py` `ALL_EXAMPLES`. `gold_standards.json` is hand-written from the rubrics.
- `--student scripted` (`scripted_student.py`): no API key; pass is `example_passed` (substring + oracles + process). `-j` is threads. Do not use `tests/eval_runner.py`. Do not set `WRITERAGENT_TESTING=1` for LO eval.
- CI / pytest: `tests/scripts/test_eval_oracles.py` and `test_scripted_eval_pack.py` replay `--backend string --student scripted` (no OpenRouter). Prompt-text pins live in `tests/scripts/test_eval_prompts.py`. Headless `--backend lo --student scripted` is `@pytest.mark.integration`; local: `python scripts/prompt_optimization/run_eval.py --backend lo --student scripted --no-bust-cache -v`.

The 50 test cases live in [`ideas.md`](ideas.md) (20 Writer, 20 Calc, 5 Draw, 5 Multimodal; categorized by level with modes for judging).

---

## Hybrid Evaluation Strategy for Draw, Flowcharts & Images (New)

`DrawWorld` in `eval_worlds.py` shipped the tree/`shape_connect` path (no separate `--backend drawjson`). Remaining gaps: `image_generate`, vision/multimodal, and LO geometry/z-order. **Screenshots are not needed**.

**Recommended path (non-LO first)**:
- **DrawWorld** (shipped; this section used to call it DrawJSONBackend): Maintains a mutable JSON tree. Mock `get_draw_tree`, `shape_upsert` (flowchart-*, connectors), `shape_connect`, `shape_group`, `shape_summary`. `dispatch_string_tool` extended for Draw tools. Final state for judging = serialized tree JSON (structural diff on nodes, connections, text, geometry with tolerances) or LLM-as-Judge on tree.
- `plugin/draw/tree.py:GetDrawTree` is the perfect "DOM" — recursive JSON with `type`, `text`, `geometry`, `connected_start`/`connected_end` (by name/text), `children` for groups. Its description explicitly says "Use this instead of requesting a screenshot to understand the layout, text, connections, and hierarchy of objects (like flowcharts or diagrams)."
- For `image_generate` (`plugin/writer/images.py`, `plugin/writer/image_utils.py`): Mock `ImageService.image_generate` to return fixed temp path; state adds an "image" node to tree or HTML sentinel. Judge on tool result JSON (`status: "ok"`) + presence in final tree.
- Verification: Extend `eval_core.py` for tree-based `expected_contains` (node paths) or JSON-aware judge. No pixel comparison.

**LO transition**: Use `--backend lo` with Draw doc (`private:factory/sdraw`) + real tools for fidelity tests (real insertion, styles, z-order, rendering). See `tests/draw/test_draw_uno.py` for patterns (`_exec_tool`, assertions on JSON + UNO counts/positions). `get_draw_context_for_chat` in `plugin/draw/bridge.py` provides lighter text summary.

**When to require LO** (analysis of [`ideas.md`](ideas.md)):
- **String/DrawJSON sufficient** (~40%): Pure text cleanup, logical rewriting, basic table engineering (HTML), bullet consistency, format preservation, simple shape creation (via tree mutation). Flowchart Gen (#3 in Draw) is ideal for tree-based eval (check connections, node types/text).
- **Requires LO or advanced mock for fidelity** (most Calc, many Writer structural, all Draw/Multimodal):
  - Writer: Styles, comments, track changes, TOC, headers/footers, section breaks, style mapping, bibliography (UNO-specific).
  - Calc: Formulas, conditional formatting, pivot tables, charts, multi-sheet ops (20/20 tests).
  - Draw (5/5): Z-order, grouping, precise layout/alignment, scaling — tree JSON handles most; full LO for geometry/rendering edge cases.
  - Multimodal (5/5): Vision (OCR, captioning, spatial audit on images/diagrams) — needs `image_generate` + insertion or real image fixtures (`multimodal_vision.odt`).
- **Recommendation**: DrawWorld covers Draw/flowchart ranking without screenshots. Use `--backend lo` for Calc/Writer fidelity smoke and as a gold standard for UNO-only features. This avoids making all evals "harder" while enabling image/tool-calling evals via metadata/tree. Aligns with AGENTS.md testing policy (unit tests for mocks, UNO tests for real document interaction).

See previous analysis for architecture diagram (StringBackend → DrawJSONBackend → LOBackend; judge on final tree/HTML).

---

## Updated Phase 2: Roadmap & Next Steps

### A. Expand Test Suite (Completed hardening)
- Hardened key tests in [`scripts/prompt_optimization/dataset.py`](scripts/prompt_optimization/dataset.py) (BULK_CLEANUP, REFORMAT_RESUME, LOGICAL_REWRITING, TABLE_ENGINEERING, BULLET_CONSISTENCY, TAX_COLUMN, STYLE_CONSISTENCY, COMMENT_MANAGEMENT) with stricter instructions, edge cases, precise rubrics referencing judge weights/gold, expanded contains/rejects, tool hints (per plan). TABLE_FROM_MESS and structural Draw/Calc kept as baseline. No new full tests added ("don't go crazy").
- Ported/updated from [`ideas.md`](ideas.md).
- Categorize by LO requirement (see above). Update `AGENTS.md` after changes.

### B. Multimodal & Image Evaluation
- Mock `image_generate` + tree/image node in state.
- Fixtures: `tests/fixtures/multimodal_vision.odt`, image assets.
- Judge on inserted image metadata + caption accuracy.

### C. Test Fixtures
- Expand with Draw-specific tree golds in `gold_standards.json`.
- `long_summarization.odt`, `complex_calc.ods`.

### D. Advanced Reporting & CI
- Integrate with `run_eval_multi.py` (already supports multi-model IpD).
- ~~Add `--backend drawjson` flag.~~ DrawWorld is the string-backend Draw tree; no extra flag.
- UNO tests for Draw eval path (`tests/draw/`).

### E. LO Transition Strategy
- Keep `--backend string` (WriterWorld / DrawWorld / CalcWorld) as primary for speed/CI.
- LO for validation of specialized tools (`ToolWriterSpecialBase`, `ToolDrawSpecialBase`, `get_draw_tree`).
- Update `AGENTS.md` prompt optimization section with hybrid guidance.

### F. Calc `=PY()` placement (shipped in the 17-task pack)

**Hypothesis:** a few limitation words on main chat beat a second specialized domain. Dest / spill / peek live on `write_formula_range` (`plugin/calc/cells.py`); MIPROv2 can later rewrite that description plus the remaining `CALC_FORMULA_SYNTAX` / pointer in `CALC_CORE_DIRECTIVES` (`plugin/framework/prompts.py`).

Calc chat no longer delegates `domain="python"`; models must `write_formula_range` of `=PY("result = …"; DataRange)` into an **empty cell outside DataRange**. Rows in `dataset.py`:

| id | Ask | Pass | Fail | Status |
|----|-----|------|------|--------|
| refuse overlap | put the formula in **H1**, data A1:H500 | dest J1/I1 and says H1 is inside the range | writes H1 | **shipped** (`py_refuse_overlap`) |
| no bulk read | unique-rows via `=PY` | no `read_cell_range` of A1:H500 / the spill | dumping the block into chat | **shipped** (`py_no_bulk_read`) |
| unique beside | drop dupes on A1:H500 onto the sheet | `=PY` dest **J1** (or first empty col / other sheet) | dest inside A1:H500; `domain=python`; chat-only | dropped (pack stays even) |
| in-place reframe | write unique rows **back onto** A1:H500 | same as unique beside + short circular explanation | `=PY` in A1 | dropped |

Scoring: dest vs parsed data range on `--backend string` (`CalcWorld` records dest + formula). LO later for spill. Next ranking run is live `--backend string` (do not regenerate golds first). Optimize output if needed: `optimized_calc_py_prompt.json`.

---
*Updated Dev Plan v2.2 — Phase F shipped (Aug 2026)*
