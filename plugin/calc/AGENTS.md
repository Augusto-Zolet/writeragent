# Calc

Root invariants still apply (one OXT at a time, `get_calc_context_for_chat`
needs `ctx` from the panel / MainJob, specialized tiers omitted from
default tool lists).

## Entry points

- `=PROMPT()`: `prompt_addin.py`, `prompt_function.py`
- `=PYTHON()` / LibrePy: `python/addin.py`, `python/addin_librepy.py`, `python/function.py`
- Do **not** drop `analyzer.py` from the LibrePy bundle (reserved).

Topic docs: [docs/calc-specialized-toolsets.md](../../docs/calc-specialized-toolsets.md),
[docs/calc-conditional-formatting.md](../../docs/calc-conditional-formatting.md),
[docs/calc-sheet-filter.md](../../docs/calc-sheet-filter.md),
[docs/calc-date-time-handling.md](../../docs/calc-date-time-handling.md),
[docs/calc-py-data-shapes.md](../../docs/calc-py-data-shapes.md),
[docs/enabling_numpy_in_libreoffice.md](../../docs/enabling_numpy_in_libreoffice.md).

## Sharp edges

- LibrePy uses `addin_librepy.py` instead of `addin.py`.
- Nested specialized sets use `specialized` / `specialized_control` and are omitted from default main-chat lists. Callers use `delegate_to_specialized_calc_toolset`.
- `plugin/scripting/venv/calc_functions_*.py` alphabet splits are intentional; do not merge them.
- `float(...)` inside `=PYTHON("...")` formula strings → Calc lexer `#NAME?`. Use code-in-cell or bare `np.sum` (see enabling-numpy doc).
- In tests, resolve tools with `plugin.main.get_tools().get("tool_name")`.
