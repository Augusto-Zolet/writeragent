# Writer

Root invariants still apply (tool `uno_services` first, `guard_uno` at
document boundaries, LibrePy-safe helpers in `plugin/doc/text_helpers.py`).

## Entry points

- HTML import / apply-content (callers `import format as format_support`): `format.py`
- Charts / shapes (shared **names** with Calc/Draw): `specialized/charts.py`, `specialized/shapes.py`
- Light reads (tracked deletions, heading tree, selection range): `plugin/doc/text_helpers.py`

Topic docs: [docs/writer-math-tex.md](../../docs/writer-math-tex.md),
[docs/writer-grammar-checker-plan.md](../../docs/writer-grammar-checker-plan.md),
[docs/writer-specialized-toolsets.md](../../docs/writer-specialized-toolsets.md),
[docs/writer-llm-styles.md](../../docs/writer-llm-styles.md),
[docs/writer-reviewable-agent-edits.md](../../docs/writer-reviewable-agent-edits.md),
[docs/writer-lo-dom-semantic-tree.md](../../docs/writer-lo-dom-semantic-tree.md).

## Sharp edges

- Writer `charts` / `shapes` share tool **names** with Calc/Draw — the Writer class must declare the **union** of those UNO services or execution rejects the document.
- Extend / Edit selection prompts must use `get_string_without_tracked_deletions()` in `text_helpers`, not a raw text dump that includes tracked deletions.
- Do not import `document_helpers` from LibrePy paths (it pulls Calc analyzer / chat context). Light helpers stay in `text_helpers` / `doc_type` / `udprops` and are **not** re-exported from `document_helpers`.
