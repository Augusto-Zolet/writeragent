# Steal from PPT Master — a host-side deck design system for WriterAgent Impress

**Status:** Plan (Route B is the plan; Route A is documented context only).
**Audience:** Keith / Chief.
**Date:** 2026-09-16 (rev 2 — supersedes the earlier "page-job + checklist" plan).
**Upstream:** [hugohe3/ppt-master](https://github.com/hugohe3/ppt-master) (MIT), skill v6.x.
**Evidence base:** rendered slides from `hugohe3/ppt-master-examples` (glassmorphism, swiss-grid), `plugin/draw/*`, `plugin/framework/prompts.py`, `scripts/eval_2_draw_oracle.py`.

> **Not a product brief:** do **not** paste upstream `references/*.md` into a WriterAgent prompt. This doc steals *patterns*, and the implementation below is WriterAgent-original.

---

## 0. Decision

There are two ways to close the polish gap between main-chat Impress and ppt-master output.

| Route | What it is | Verdict |
|-------|------------|---------|
| **A** | Use the existing **PPT-Master sidebar mode** (`plugin/chatbot/ppt_master.py` + `plugin/ppt_master/` venv worker) with a strong model. Authors SVG → `svg_to_pptx` → native PPTX → clone into Impress. | **Quality today.** Already installed on this machine. Not the subject of this doc — but worth doing alongside. |
| **B** | Build a **host-side deck design system** in the main Draw/Impress tool path: a persisted theme + a closed enum of page carriers the host renders, with the model only choosing content and recipe. | **This plan.** Makes WriterAgent's own product better and is what a small model can actually drive. |

Both can coexist. Route B is the one that improves `DEFAULT_DRAW_CHAT_SYSTEM_PROMPT_TEMPLATE` and the base product.

---

## 1. What we are actually trying to reproduce

Rendered from the public examples repo, two decks show the same five layers on every page:

1. **A composition layer.** A full-bleed background (gradient art / drawn grid), a primary panel or band, deliberate negative space. Not a white slide with shapes on it.
2. **A locked design system.** One palette, one type pairing, one icon style, fixed before page 1 and re-read per page (`spec_lock.md`, `plugin/contrib/ppt_master/skill/SKILL.md:30`).
3. **Typographic hierarchy.** Eyebrow / kicker → display title → subhead → body → microcopy, plus chrome (series name, `01 / 12` folio).
4. **A carrier per page.** A 4×4 card grid, an 8-item principles grid, a KPI row. One device family per page, repeated deck-wide.
5. **Assets.** Icons, AI illustrations, photos, native charts.

Main-chat Impress currently produces "title + bullets + one rectangle" (`docs/draw/impress-ai-mercury-2.5-headed-findings.md:96`). Layers 1–4 are simply absent; layer 5 is barely used.

**Key conclusion:** the gap is a *design-system and assets* gap, not a prompt-wording gap. A model that cannot see the slide cannot be talked into producing a frosted-glass panel and a locked type scale. The host must own layout; the model must own content choice.

---

## 2. What changes from the previous version of this doc

The old plan was prompt-first and is now demoted:

| Old item | Old framing | New framing |
|----------|-------------|-------------|
| #1 page-job/density/one-carrier rules (≤12 lines) | "Try first" | Keep as a **6-line pointer** to `compose_slide` / recipe enum. Prose cannot create backgrounds, gradients, or type scales. |
| #2 closed recipe enum | "Yes, second" | **Promoted to the core of the plan**, but implemented as *host-rendered page templates*, not a prompt list. |
| #3 one polish pass (Hard checklist + `get_draw_tree`/`get_image`) | "Yes, third" | **Promoted to a deterministic lint tool** (`check_deck_layout`), not a model checklist. No vision needed. |
| #4 eval rubric | "maybe" | **Strengthened**: add Hard geometric checks to `scripts/eval_2_draw_oracle.py` so polish is measured, not asserted. |
| #5 Calc transfer | "light" | **Deferred** until Impress lands. Calc has its own active failures. |
| #6 keep sidebar PPT-Master | "keep" | Unchanged. Route A lives there. |

The reusable insight from upstream is its **decomposition** (plan → per-page job → one device → post-check), not its files.

---

## 3. Route B: the design system

### 3.1 Separation of concerns

```
model  →  deck plan (JSON): theme + slides[{recipe, slots}]
host   →  theme resolution + geometry + shapes + chrome + lint
```

The model never emits coordinates, colors, or font sizes. It emits content plus a recipe name from a closed enum. This is the single biggest reliability win for mercury-class models: structured output over free-form layout reasoning.

### 3.2 Deck theme (tokens)

A `DeckTheme` is a small, serializable token set. It is chosen once per deck and persisted in the document so later turns stay consistent.

```python
@dataclass(frozen=True)
class DeckTheme:
    name: str
    bg_top: str; bg_bottom: str          # background gradient stops (or one solid)
    bg_gradient_angle: int
    surface: str; surface_alpha: int     # card/panel fill + transparency 0-100
    border: str; border_alpha: int
    accent: str; accent2: str
    text: str; text_muted: str
    font_display: str; font_body: str
    margin: int; gutter: int; radius: int
    folio: bool = True
    footer: str = ""
```

Ship 3–5 presets in code (steal the *look*, not the files): e.g. `midnight_teal` (dark gradient hero), `swiss_grid` (light, hairline rules, one red accent), `slate_clean` (light cards), `glass_dark` (frosted panels). Presets are constants, **not** a registry — no fourth ad-hoc registry (see `AGENTS.md`).

Persist with `plugin/doc/udprops.py` (`set_document_property` / `get_document_property`) under a namespaced key such as `WriterAgent.DeckTheme` (JSON). Document properties survive re-open and are LibrePy-safe.

### 3.3 Page carriers (recipes)

A recipe is a *template*: slot names → geometry + styling. It is the main-chat analogue of upstream's "device" menu, but rendered by the host.

| Recipe | Slots | Steals (upstream device) | Reuses |
|--------|-------|--------------------------|--------|
| `cover` | eyebrow, title, subtitle, series | hero cover + eyebrow + rule + folio | `carrier_boxes` |
| `section_divider` | number, title, subtitle | section divider | `carrier_boxes` |
| `title_bullets` | title, bullets[] | content page | `align_boxes` |
| `kpi_row` | title, items[{value,label}] (2–4) | KPI tile row | `distribute_boxes` |
| `card_grid` | title, cards[{headline, body, icon}] (2–6) | card band / icon-and-label | `carrier_boxes` |
| `two_column_compare` | title, left{head,points[]}, right{head,points[]} | contrast device | `carrier_boxes` |
| `process_flow` | title, steps[] (2–6) | topology / flow | `diagram_node_boxes` + `CreateDiagram` |
| `quote` | quote, attribution | quote block | `carrier_boxes` |
| `chart` | title, chart spec | native chart page | `plugin/draw/charts.py` |
| `table` | title, header, rows | table page | `plugin/draw/tables.py` |
| `closing` | title, subtitle, contact | ending / CTA | `carrier_boxes` |

Rules:
- One carrier per page; do not mix two devices.
- `card_grid`/`kpi_row` item counts are validated against the enum range; out-of-range returns an error listing valid counts.
- `freeform` is **not** a recipe. If none fits, the model may still use the raw shape tools (specialized domain) — the design system is a default, not a cage.

### 3.4 Composition details (the part that makes it look designed)

`compose_slide` renders in this order so Z-order is correct:

1. **Background** — full-bleed rectangle, gradient `bg_top`→`bg_bottom`. Created first so it sits behind everything (also set `ZOrder` defensively; property is in `_COPY_PROPS` at `plugin/ppt_master/adapter/uno_shape_postprocess.py`).
2. **Accent layer** — one thin rule or band in `accent`; optional large low-alpha shape.
3. **Chrome** — eyebrow (uppercase, letter-spaced feel via short text), folio `NN / NN`, footer series name. Draw these as shapes; do **not** depend on Impress master header/footer text frames (`plugin/draw/headers_footers.py` remains an alternative for real presentation-wide footers).
4. **Surface/cards** — rounded rectangles (`round-rectangle` alias is supported, `plugin/draw/shapes.py:544`) with `surface` + `surface_alpha` and hairline `border`.
5. **Text slots** — role-based sizes from the theme type scale (display/h1/h2/body/micro), each in its own text box with `TextFitToSize = AUTOFIT` so variable-length model output cannot overflow or wrap one character per line.
6. **Assets** — icon or image inside the reserved box.

The visual quality largely comes from steps 1–3 and 5. These are exactly the steps a small model omits.

### 3.5 Assets

- **v1 (deterministic, no network):** icons are Unicode glyphs in a tinted rounded square; hero imagery is optional and off by default. This keeps a small/offline model usable.
- **v2 (opt-in):** wire `plugin/writer/images/images.py` tools (`image_generate`, `image_download`, `image_insert`) so `cover` and one key page can carry a generated hero image (the user already has `google/gemini-3.1-flash-lite-image` configured).
- **v3 (later):** generated illustration *sheet* + slice, as upstream does. Explicitly out of scope for the first cut.

### 3.6 The model contract

One structured call. The model emits a deck plan; the host renders it. This is also the safest interface for weak models because a schema error is a normal, recoverable tool error.

```json
{
  "recipe": "render_deck_plan",
  "plan": {
    "theme": "midnight_teal",
    "slides": [
      {"recipe": "cover", "slots": {"eyebrow": "2026 STRATEGY", "title": "…", "subtitle": "…"}},
      {"recipe": "kpi_row", "slots": {"title": "…", "items": [{"value": "3.2x", "label": "…"}]}},
      {"recipe": "card_grid", "slots": {"title": "…", "cards": [{"icon": "◆", "headline": "…", "body": "…"}]}}
    ]
  }
}
```

Incremental multi-turn use is still available: `set_deck_theme` once, then `compose_slide(recipe=…, slots=…)` per page. `render_deck_plan` is a thin loop over `compose_slide`, so there is one renderer, two entry points.

Validation contract:
- unknown `recipe` → error listing the enum;
- missing slot → that slot is left empty and the reason is returned (do not guess);
- wrong item count → error with the valid range;
- partial success → return `{created: [...], errors: [...]}` and never abort the whole deck.

### 3.7 Deterministic layout lint — `check_deck_layout`

The old plan's "Hard checklist" becomes a tool, because a model that ignores prose will still fail a tool result, and a model with no vision can still read geometry.

Pure geometry in `plugin/draw/layout.py`, so it is unit-testable without UNO:

```python
def layout_issues(boxes: Sequence[tuple[Box, str]], page_w: int, page_h: int) -> list[dict]
```

Rules (each returns `{kind, shapes, hint}`):
- `off_canvas` — any shape box outside the page.
- `overlap` — text boxes overlapping text boxes beyond a small tolerance (the recorded dominant failure: `docs/eval/eval-2/headed-failure-autopsy.md`).
- `empty_text` — text placeholder with no content.
- `one_char_line` — text box too narrow for its character count (heuristic from box width vs `CharHeight`; the recorded vertical-text bug).
- `column_drift` — same-column boxes with differing x (misaligned cards).
- `unbalanced_margins` — left/right margins differ by more than the theme gutter.

`check_deck_layout(page=N)` wraps `get_draw_tree` boxes (reuse `_shape_box` at `plugin/draw/shapes.py:848`) into `layout_issues`. It is report-only by default; `fix=true` may apply the obvious repairs (align to margin, grow box, delete empty) but is capped at one pass.

### 3.8 Prompt delta (small by design)

`DEFAULT_DRAW_CHAT_SYSTEM_PROMPT_TEMPLATE` gets ~10–12 lines, not a skill:

```
DECK MODE (when building more than one slide):
- Plan the deck, then render with render_deck_plan (or compose_slide per page).
- Pick one theme for the whole deck; never set colors/sizes by hand.
- One carrier per page. Never place free coordinates unless no recipe fits.
- Content goes in slots; the host owns geometry, type scale, and chrome.
- Before finishing, call check_deck_layout and fix reported issues once.
```

Everything else (recipes, themes, geometry) is tool schema and host code — respecting the 2× prompt-size rule.

### 3.9 UNO fidelity guardrails

Three concrete gaps to close, verified with `plugin/testing_runner.py` (per `AGENTS.md`, inspect UNO directly rather than guessing):

1. **Gradients/transparency.** `_apply_shape_properties` (`plugin/draw/shapes.py:433`) currently handles only `solid` / `transparent` / `none`. Add optional `fill_gradient` (two stops + angle → `FillStyle.GRADIENT`, `FillGradient`, `FillColor`, `FillColor2`) and `fill_transparence`. Centralize in `shapes.py` so `shape_upsert` benefits too — one styling path, less debt.
2. **Text autofit.** Set `TextFitToSize` to autofit on slot boxes so variable model text cannot overflow; confirm the enum value on the live instance.
3. **Fonts.** Use fonts that exist on typical installs (Liberation family / DejaVu) or explicitly fall back; a missing display font silently flattens the whole design.

---

## 4. Architecture and file map

| File | Change | Why |
|------|--------|-----|
| `plugin/draw/layout.py` | Add `carrier_boxes(...)` and `layout_issues(...)` (pure, 1/100 mm) | Geometry is testable without UNO; `test_draw_layout.py` already exists |
| `plugin/draw/deck.py` (new) | `DeckTheme`, `DECK_THEMES`, `RECIPES`, `compose_slide`, `render_deck_plan`, `check_deck_layout` | One place owns the design system; no new registry |
| `plugin/draw/shapes.py` | Optional `fill_gradient` / `fill_transparence` in `_apply_shape_properties`; reuse `_apply_shape_properties` + `DrawShapes.safe_create_shape` from the renderer | One styling path; renderer does not fork shape creation |
| `plugin/draw/base.py` | `ToolDrawDeckBase` (domain `deck`) | Subclass scan in `plugin/doc/specialized_base.py` lists it in the gateway automatically |
| `plugin/draw/__init__.py` | `from . import deck as deck` | `auto_discover_package` registers the tools |
| `plugin/framework/prompts.py` | ~10-line DECK MODE block in `DEFAULT_DRAW_CHAT_SYSTEM_PROMPT_TEMPLATE` | Small steer, points at tools |
| `plugin/doc/udprops.py` | Used as-is for theme persistence | No change expected |
| `scripts/eval_2_draw_oracle.py` | Add geometry checks + score fields | Makes polish measurable |
| `tests/draw/test_draw_layout.py` | New cases for `carrier_boxes` / `layout_issues` | Required |
| `tests/draw/test_deck.py` (new) | Unit tests for theme defaults, recipe validation, plan validation (mock UNO) | Required |
| `tests/draw/test_deck_uno.py` (new) | `@native_test` compose a cover + a card grid, then `layout_issues` on the result | Required |
| `docs/draw/impress-specialized-toolsets.md` | Add the `deck` domain to the domain table | Keep the toolsets doc current |

**Tier decision:** `compose_slide`, `render_deck_plan`, `check_deck_layout`, and `set_deck_theme` are `tier="core"` for Impress/Draw. They are host-side orchestrators, so the main agent calls them directly — no delegation round-trip for a small model, and no chance of the model "helpfully" placing raw coordinates. The raw `shapes` domain stays specialized as the escape hatch.

**Reuse, not reinvention:** `CreateDiagram` already batches geometry via `diagram_node_boxes` (`plugin/draw/layout.py:118`). The recipe renderer should share that path for `process_flow` rather than adding a second layout engine.

---

## 5. Milestones

Each milestone is independently shippable and has tests. M0–M2 already produce a visible polish jump.

| # | Deliverable | Tests | Notes |
|---|-------------|-------|-------|
| **M0** | `carrier_boxes` + `layout_issues` in `layout.py` | `tests/draw/test_draw_layout.py` | Pure, fast, no UNO. Proves geometry before any rendering. |
| **M1** | `DeckTheme` + presets + `compose_slide` for `cover`, `title_bullets`, `kpi_row`, `card_grid`, `section_divider`, `closing`; core tools registered | `tests/draw/test_deck.py`, `tests/draw/test_deck_uno.py` | The visual payoff: background gradient, surface, type scale, chrome. |
| **M2** | `render_deck_plan` + validation/partial-success contract; prompt DECK MODE block | `test_deck.py` (plan cases) | One-shot path for weak models. |
| **M3** | `check_deck_layout` + wire `layout_issues`; `fix=true` single pass | `test_draw_layout.py`, `test_deck_uno.py` | Directly targets the recorded Draw failure. |
| **M4** | `set_deck_theme` / `get_deck_theme` via `udprops`; remaining recipes (`two_column_compare`, `process_flow`, `quote`, `chart`, `table`) | `test_deck.py` | Consistency across turns. |
| **M5** | Optional hero image via `image_generate` for `cover`/`section_divider`; icon glyph styling | `test_deck_uno.py` | Offline default stays intact. |
| **M6** | Eval: geometry scoring in `eval_2_draw_oracle.py` + rubric additions; run headed space-elevator before/after | oracle unit path + headed run | Answers "did polish move?" |

---

## 6. Measurement

Polish must be falsifiable. Extend `scripts/eval_2_draw_oracle.py` (it already parses the saved `.odg` XML: frames, shapes, text, connectors) with geometry-derived fields:

- `off_canvas_count`, `text_overlap_count`, `empty_text_count`, `one_char_line_count`, `column_drift_count`, `has_folio`.
- Keep the existing semantic anchors (Clearbend, lanes, decision) — add geometry, do not replace content scoring.
- Report a `polish` sub-score separately from the content score so a deck can be content-HAPPY and polish-low, which is exactly today's failure mode.

Run `scripts/eval_2_headed.py --task draw-primary --score …` before M1 and after M3 on the same prompt to quantify the delta. Add the same geometry criteria to `docs/eval/eval-2/draw-primary-deliverable/rubric.eval2.md`.

---

## 7. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Recipes feel rigid / samey | Closed enum is a default, not a cage: `shapes` domain remains for freeform; `theme` variation; future recipes are additive. |
| Card fatigue ("every page is a card grid") | Enforce one carrier per page and a rhythm: alternate `card_grid` with `kpi_row` / `quote` / `chart`; upstream's `page_rhythm` concept, applied as a render-time warning when consecutive pages share a recipe. |
| No real text metrics → overflow | Autofit on every slot; lint reports overflow; keep copy limits per slot in the recipe spec. |
| Fonts missing on user installs | Default to Liberation/DejaVu; theme fonts are advisory with a verified fallback. |
| Z-order / background bugs | Background created first and `ZOrder` set; covered by the `test_deck_uno.py` assertions. |
| Gradient/transparency unsupported | M1 supports solid + layered rects first; gradient is an M1/M2 enhancement in one styling path, with a fallback to two stacked rects. |
| Scope creep into a full SVG engine | Explicit non-goals below; the renderer only uses UNO shape primitives. |

---

## 8. Non-goals

- Re-implementing `svg_to_pptx` or an SVG pipeline in main chat.
- Loading `executor-base.md` / `strategist.md` / `image-generator.md` into any prompt.
- Multi-agent Strategist/Executor role switching in main chat.
- Animations / Morph / narrated video.
- AI illustration-sheet slicing in v1 (upstream does this; we do not need it yet).
- Removing or deprecating the sidebar PPT-Master mode (Route A).

---

## 9. Technical debt this retires

- **One shape-styling path.** Gradient/transparency live in `_apply_shape_properties`, so `shape_upsert` and the deck renderer share behavior instead of drifting.
- **One geometry home.** `layout.py` already holds `align_boxes`, `distribute_boxes`, `diagram_node_boxes`; `carrier_boxes` joins them, and `CreateDiagram` can later share it.
- **Lint instead of prose.** The old plan would have grown the Draw prompt for a class of defects that a pure function can detect exactly.
- **Measured polish.** Geometry fields in the oracle turn "looks generic" into a number, so future changes can be accepted or reverted on evidence.

---

## References (upstream, read selectively)

- Skill entry: `skills/ppt-master/SKILL.md`
- Rubric to compress: `references/visual-review.md`
- Do not load into WA prompts: `references/executor-base.md`, `strategist.md`, `image-generator.md`, `shared-standards-core.md`
- WA integration: `plugin/contrib/ppt_master/README.md`, `plugin/ppt_master/`, `plugin/chatbot/ppt_master.py`
