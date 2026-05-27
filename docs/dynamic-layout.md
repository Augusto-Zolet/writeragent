# Dynamic Sidebar Panel Layout (WriterAgent Chat)

## Overview

The chat sidebar uses a **hybrid XDL + runtime relayout** approach. Control definitions (types, labels, initial positions) live in `extension/WriterAgentDialogs/ChatPanelDialog.xdl`. At runtime, `_PanelResizeListener` (an `XWindowListener` in `plugin/chatbot/panel_resize.py`) repositions and resizes controls when the panel size changes: the **response** area grows vertically to fill space above a bottom-anchored cluster; **fluid** controls stretch horizontally to a fixed right margin; other controls stay fixed width and left-anchored.

Wiring happens in `plugin/chatbot/panel_wiring.py`. `ChatToolPanel.getHeightForWidth()` in `plugin/chatbot/panel_factory.py` negotiates width/height with LibreOffice’s sidebar deck layouter and must stay consistent with `_relayout()`’s width logic.

---

## How LibreOffice Uses `LayoutSize`

`XSidebarPanel.getHeightForWidth(width)` returns `LayoutSize(Minimum, Maximum, Preferred)`. The sidebar’s `DeckLayouter` (`sfx2/source/sidebar/DeckLayouter.cxx`) uses this to distribute height:

- Panels with **Maximum = -1** (unbounded) receive **remaining height** after fixed panels are satisfied.
- Field order for `uno.createUnoStruct("com.sun.star.ui.LayoutSize", ...)` is **Minimum, Maximum, Preferred** (IDL order matters).

WriterAgent returns `LayoutSize(100, -1, 400)`: minimum width hint 100, unbounded max height, preferred height 400.

---

## XDL as Baseline

`ChatPanelDialog.xdl` defines Map AppFont positions/sizes. After `ContainerWindowProvider.createContainerWindow()` loads the dialog, pixel geometry is the baseline for `_capture_initial()`. The root dialog width (e.g. 180 Map AppFont units) is aligned with `getMinimalWidth()` so the first paint matches the declared minimum sidebar width.

---

## Runtime layout: `_PanelResizeListener`

### Snapshot (`_capture_initial`)

On first `_relayout`, the listener records each control’s `(x, y, width, height)`, the window size, the response field’s bottom edge, and the vertical span of the “bottom cluster” (everything below the response). Control widths in the snapshot are **clamped up** to `_MIN_WIDTHS` when GTK/VCL briefly reports ultra-narrow widths (~10px), so later math does not lock in a broken baseline.

### Two-pass layout (`_relayout`)

1. **Width sync (root window)**  
   The panel’s **root** window width is synchronized with a **target** derived from the sidebar **parent** window and the last **deck** width hint (see [Parent vs deck width](#parent-vs-deck-width-divergence) below). This avoids the root staying wider than the visible column (or vice versa) when UNO reports inconsistent sizes.

2. **Non-response controls**  
   - **Fluid** (`response` is handled in pass 2): `query`, `status`, `model_selector`, `image_model_selector`, `aspect_ratio_selector`. Each gets `new_w = max(10, w - ox - fixed_margin)` (fill to a small right margin), then minimum widths from `_MIN_WIDTHS` are applied **without exceeding** available horizontal space (`avail`), so combos never force a width larger than the panel.  
   - **Fixed**: buttons, labels, checkboxes keep snapshot width (with minimum floors for non-fluid controls).

3. **Bottom anchoring**  
   Controls at or below the response’s original bottom edge are shifted vertically so the cluster sits near the window bottom while preserving intra-cluster spacing and not overlapping the response (see `bottom_top_new` / `gap_below_response`).

4. **Response area**  
   Second pass sets height from the top of the response to just above the bottom cluster, and width using the same right-margin rule as other fluid controls.

**Note:** Early design docs described **proportional horizontal scaling** (`new_w = ow * width_ratio`). The implementation intentionally switched to **fill-to-margin + minimum floors** to avoid feedback loops between intrinsic control sizing and panel width (especially on GTK).

---

## `ChatToolPanel.getHeightForWidth(width)`

Called by the deck layouter with a **width hint** (`deck_w`). The implementation:

1. Reads **parent** window size (`parent_w`, `parent_h`) from `ChatToolPanel.parent_window`.
2. Stores **`_last_deck_w = deck_w`** for `_relayout` to use on the next pass.
3. Computes **`eff_w`** using the same rule as `_relayout`’s parent sync ([divergence](#parent-vs-deck-width-divergence)).
4. **`setPosSize(0, 0, eff_w, h)`** on `PanelWindow` so the panel root matches the chosen column width.
5. Calls **`resize_listener.relayout_now(PanelWindow)`** because **`windowResized` does not always fire** when the layouter changes size programmatically.
6. Returns `LayoutSize(100, -1, 400)`.

---

## Parent vs deck width (“divergence”)

On GTK/VCL (notably LibreOffice 24), **two different width numbers** show up in logs:

- **`deck_w`**: width passed into `getHeightForWidth` (deck’s idea of the column).
- **`parent_w`**: width of the sidebar content parent (`xParentWindow`).

Often they track together when the user drags the sidebar splitter. Sometimes **`parent_w` grows with “intrinsic” layout** (e.g. long text, combo preferred size) even when **`deck_w` stays modest** — logs showed huge `parent_w` vs ~deck width. If the panel was sized to `parent_w`, it would overflow the allocated visible area of the sidebar column (`deck_w`), causing a horizontal scrollbar.

**Sizing Strategy**:
To completely break this feedback loop and prevent horizontal scrollbars, we always size the panel directly to the allocated deck width (`deck_w` / `deck`) whenever it is available and valid (`> 0`). This ensures the panel fits perfectly within the visible columns across all VCL/GTK themes. If the deck width is not available, we fall back to the parent window width (`parent_w`).

---

## Evolution: what we tried

| Approach | Intent | Outcome |
|----------|--------|---------|
| **Simple `setPosSize(width, h)` in `getHeightForWidth`** | Match deck width | Worked for basic cases; **combo dropdown** still clipped; typing could **widen** the panel on GTK. |
| **`_MIN_WIDTHS` + fill-to-margin for fluid controls** | Stop ~10px-wide controls; keep dropdown affordance visible | **Helped**; model comboboxes use ≥120px floor where space allows. |
| **`relayout_now` from `getHeightForWidth`** | Relayout when `windowResized` misses | **Necessary**; without it, sizes lag after layouter updates. |
| **Fixed Send button width** (`_measure_send_button_max_width` + `QueryTextListener.set_fixed_send_width`) | **Record / Send / Stop Rec** label changes resized the button and caused **~22px width steps** and feedback loops | **Worked**; measure max label width once after wiring, re-apply after each label change. |
| **`_column_width_cap`** (`min(parent, deck)`, grow only when parent≈deck) | Stop runaway width | **Stopped creep** but **blocked stretching** when the user widened the sidebar — fluid fields no longer filled the column. **Replaced** by divergence rule. |
| **Relayout after toggling “Use Image model”** | Visibility swap changes vertical stack | **Needed** so the visible model row gets correct widths. |
| **Wiring split: `panel_wiring.py`** | Smaller `panel_factory.py` | Organizational; behavior unchanged. |

Debugging relies on `writeragent_debug.log` lines: `getHeightForWidth deck_hint=...`, the `layout_sanity: root_w=... max_child_right=...` line (emitted once after wiring), and the remaining `_relayout` / `_capture_initial` messages (now much quieter). The old `sync root` and `fluid widths` messages were removed in the 2026-05 simplification.

---

## Key files (WriterAgent)

| File | Role |
|------|------|
| `extension/WriterAgentDialogs/ChatPanelDialog.xdl` | Control definitions; baseline Map AppFont layout |
| `plugin/chatbot/panel_resize.py` | `_PanelResizeListener` (now only vertical anchoring + simple stretch + right-edge safety clamps). The old root width sync, `min_client_w`, and complex fluid math were deleted in the 2026-05 simplification. |
| `plugin/chatbot/panel_factory.py` | `ChatToolPanel`, `getHeightForWidth`, `getMinimalWidth`, image-mode relayout hook |
| `plugin/chatbot/panel_wiring.py` | `_wireControls`, resize listener construction, Send width measurement |
| `plugin/chatbot/panel.py` | `QueryTextListener` (Send label + fixed width) |
| `registry/.../Sidebar.xcu` | Deck / panel registration |

---

## Comparison: fully programmatic layout (e.g. writeragent2-style)

Some projects drop XDL and place every control with raw pixel math. That can work for a **minimal** toolbar, but it tends to drop controls (model selectors, checkboxes, image rows) or duplicate a lot of boilerplate. WriterAgent keeps **XDL as the declarative source** and a **single resize listener** for dynamic height and horizontal fill.

---

## 2026-05 Major Simplification (H Scrollbar Fix)

The previous approach (heavy bidirectional width sync between `getHeightForWidth`, `_relayout` root sync, peer walking, `is_docked` heuristics in two places, `min_client_w` forcing from the Clear button position, and per-control fluid math derived from an XDL snapshot) was the primary source of the persistent horizontal scrollbar.

**What was removed / heavily simplified:**
- The entire root-window width sync block inside `_relayout` (parent/deck/visible_pw/`_SAFETY_MARGIN`/ `is_docked` / `target_w` / `setPosSize` for the root, plus the `min_w` forcing that only applied in the non-docked path).
- Most of the complex horizontal fluid logic (the `fluid_controls` tuple, `avail`/`fixed_margin` calculations, special `backend_indicator` right-alignment, multiple overflow guards, and the "clamp snapshot widths up" dance in `_capture_initial`).
- The `min_client_w` reconstruction and its use to widen the panel beyond what the deck allocated.
- Duplicated "docked detection" heuristics between `getHeightForWidth` and the listener.
- Heavy reliance on the initial XDL snapshot for deciding horizontal widths (the snapshot is now used almost only for vertical bottom-cluster anchoring + safe Y/height baselines).

**New simpler model (single source of truth):**
- `ChatToolPanel.getHeightForWidth` owns panel width. It receives the authoritative `deck_w` from the DeckLayouter. It now has a targeted guard: if the hint is huge (>500, the classic startup frame-width query) **but the current actual PanelWindow is modest (<450)**, clamp instead of widening. This directly kills the "set to ~1160 px → permanent scrollbar" feedback loop.
- The resize listener (`_PanelResizeListener`) now does only three things:
  1. Vertical bottom-cluster anchoring + response height fill (the useful UX).
  2. Simple stretch of a short list of main fields to `w - ox - 4`.
  3. A single final right-edge clamp on every control (`<= w-4`) as a safety net.
- XDL baseline widths for the stretchy controls (response, query, model selectors, labels, status) were reduced from 172 to 142 on the 180-wide root. This lowers the dialog's intrinsic "natural" size without hurting the runtime fill behavior.
- A lightweight `layout_sanity` debug line is emitted once after wiring (root_w vs max child right edge) so future regressions are obvious even without the verbose resize flag.
- Two additional high-signal markers were added for the "restored wide on restart" case:
  - `[FIRST LAYOUT]` (INFO) — fires immediately after the first `relayout_now` after the panel is created.
  - `[FIRST RELAYOUT SIZES]` (INFO) — fires on the very first response sizing pass and reports `root_w`, `response_w`, `clear_right`, and `model_sel_right`. These are extremely useful for diagnosing the initial layout at a restored wide width.

The button fixed-width measurement (Send/Record/Stop/Accept + Stop/Clear/Reject) was kept because it is still the only reliable way to stop the ~22 px stepwise widening when the label changes.

Result: far less code, far fewer feedback surfaces. The H scrollbar is now mostly gone in normal docked use (confirmed working well enough in practice).

If the scrollbar still appears when the sidebar is *wider* than the Clear button row + a few pixels, the scrollbar is on an sfx2 ancestor container (Deck / TabControl / splitter), not our PanelWindow. In that case the practical options are (a) raise `getMinimalWidth()` or (b) redesign the bottom button/checkbox row for narrower sidebars.

---

## Manual verification checklist

1. Open Writer (or Calc) → WriterAgent sidebar deck.  
2. **Resize sidebar width**: response, query, model combo should **stretch**; dropdown glyph should stay visible.  
3. **Resize window height**: response grows/shrinks; bottom cluster stays at bottom.  
4. **Type in query** (with recording enabled): **Send ↔ Record** should not widen the panel stepwise.  
5. **Toggle “Use Image model”**: no permanent overlap; relayout correct.  
6. **Narrow sidebar**: fluid widths should **not** exceed panel (no clipped-off combo button).  
7. Compare debug log `parent` vs `deck_hint` when anomalies appear.
8. **Restart test (restored width)**: Close and reopen LibreOffice with the sidebar at a previously widened size. The H scrollbar should not appear on the initial layout (or should disappear cleanly when the user widens further). Check `layout_sanity` and the new `[FIRST LAYOUT]` / `[FIRST RELAYOUT SIZES]` markers on startup.

---

## LibreOffice references

- `sfx2/source/sidebar/DeckLayouter.cxx` — height distribution, `getHeightForWidth` usage  
- `com.sun.star.ui.LayoutSize` — struct field order  
- XDL / Map AppFont: DevGuide graphical UIs, `xmlscript` DTD

---

## Residual / Future Work (post-2026-05 simplification)

The aggressive removal of the bidirectional width sync and snapshot-derived fluid math eliminated the main causes of the H scrollbar (confirmed working well enough in practice).

What remains:
- If a scrollbar still appears when the sidebar is *wider* than the Clear button row + a few pixels, the scrollbar is on an sfx2 ancestor container (Deck / TabControl / splitter), not our PanelWindow. In that case the only reliable fixes are raising `getMinimalWidth()` or redesigning the bottom button/checkbox row for narrower sidebars.
- The parent/deck/`_last_deck_w` plumbing is still wired through (low risk, used only for logging and the deck getter). It can be cleaned up in a later pass if the simplified model proves stable.
- A declarative "stretch list + min widths" table (instead of the hardcoded `stretch` tuple + `_MIN_WIDTHS`) would be a small polish item.
- UNO layout still has no good unit tests; the manual checklist below + the `layout_sanity` debug line are the practical verification tools.

### "Restored wide on restart" variant (observed 2026-05)

Even after the 2026-05 simplifications, the H scrollbar can still appear **immediately on app restart** when LibreOffice restores the sidebar to a previously saved wider width.

- The scrollbar does **not** appear (or disappears cleanly) when the user starts with a narrow sidebar and manually widens it during the same session.
- Root cause: The very first `_capture_initial` + `_relayout` after the panel is created locks in dimensions based on the restored wide root. The bottom row (especially `model_selector` + the Clear button area) ends up with its right edge too close to the right edge of the reported root window relative to the actual column width the deck allocated for that restored size.
- `layout_sanity` on such startups consistently shows a small gap (typically 4–6 px, e.g. `root_w=1238 max_child_right=1232`).
- The manual widening path works better because it never performs a full layout from a "restored wide" snapshot — it only sees gradual increases in `deck_hint`.
- Various first-relayout conservatism experiments were tried (extra right margin on the response area on first layout, then the same for the model row). These helped incrementally (`model_sel_right` moved from 1234 → 1232) but did not fully eliminate the case.
- The behavior was noticeably better in commit `af649476`. Later changes made the "always on restart at previous width" variant more prominent.
- Diagnostic markers `[FIRST LAYOUT]` (in `panel_wiring.py`) and `[FIRST RELAYOUT SIZES]` (in `panel_resize.py`, emitted at INFO level on the very first response sizing) were added to help debug this specific path.

This remains an open residual issue for future work. When revisiting, focus on the interaction between LibreOffice's sidebar width restoration and our initial snapshot + bottom-row sizing on the very first layout.
