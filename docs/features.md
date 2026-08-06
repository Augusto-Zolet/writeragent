# WriterAgent — Feature Index

User-facing catalog of what ships today. The root [README](../README.md) is the landing page; this file is the deeper map with links into topic docs.

---

## Writer

- **Core + specialized tools**: Everyday chat keeps a small default tool list; [domain-scoped sub-agents](writer-specialized-toolsets.md) unlock page layout, [shapes](shape_support.md), charts, [bookmarks](bookmarks-api-reference.md), fields, [footnotes](footnotes-api-reference.md), [track changes](writer-tracking-api-reference.md), indexes, forms, and more ([page API](page-api-reference.md)).
- **Format preservation**: Surgical replacements keep bold, italics, highlights, and font sizes. See [reviewable agent edits](reviewable-agent-edits.md) and [styles](llm-styles.md) / [LLM_STYLES.md](../LLM_STYLES.md).
- **Grammar & style**: Async proofreader with sentence cache and Unicode-aware splitting. Backends: AI (LLM), [LanguageTool](https://languagetool.org), or [Harper](https://github.com/Automattic/harper). Optional sentence language detection in Settings → Doc. [Grammar plan](realtime-grammar-checker-plan.md).
- **Math & LaTeX**: MathML / TeX → editable LibreOffice Math OLE objects. [math-tex.md](math-tex.md).
- **Symbolic math & charts**: SymPy helpers and Matplotlib figures from Viz Helpers insert into the document.
- **Text analytics (spaCy)**: Readability, NER, key phrases via **WriterAgent → Text Analytics…** (venv packages required).
- **Rich-text sidebar**: Optional rich text control in the sidebar (off by default). [Rich text control](rich-text-control-sidebar.md).

## Calc

- **`=PROMPT()`**: AI prompts inside spreadsheet cells.
- **`=PY()` / `=PYTHON()`**: NumPy/pandas in cells with multi-range `data` / `data_list`, auto spill, shared kernel, init scripts. [NumPy in LibreOffice](enabling_numpy_in_libreoffice.md) · [data shapes](calc-py-data-shapes.md).
- **Python sidebar**: Diagnostics deck for `=PY()` cells (**View → Sidebar → Python**).
- **Trusted helpers**: Analysis, Viz, Math, Quant, Optimize, Units via chat or **Tools → Run Python Script**. [Analysis tools](calc-analysis-tools.md) · [numpy domains](numpy-domains.md) · [analysis sub-agent](analysis-sub-agent.md).
- **Sheet → Python**: Convert formulas to `=PY()` while keeping constants and formats. [Spreadsheet → Python](calc-spreadsheet-to-python-import.md).
- **Agent toolsets**: Batch edits, [conditional formatting](calc-conditional-formatting.md), [sheet filters](calc-sheet-filter.md). [Calc specialized toolsets](calc-specialized-toolsets.md).

### Analysis helpers (quick list)

| Helper | Purpose |
|--------|---------|
| `describe_data` | Extended EDA + column quality |
| `kpi_summary` | Aggregate mean/min/max/sum |
| `detect_outliers` | IQR, z-score, or isolation forest |
| `quick_stats` | Compact metric card |
| `format_currency` / `format_percent` | Display formatters |
| `clean_and_prepare` | Dedupe, simple imputation |
| `pivot_aggregate` | Pivot table wrapper |
| `group_summary` | Group-by aggregates |
| `compare_periods` | YoY/QoQ/MoM |
| `correlation_matrix` | Top correlated pairs |
| `run_regression` | OLS via statsmodels |
| `cluster_numeric` | KMeans centroids |
| `monte_carlo` | Monte Carlo resampling |
| `calc_goal_seek` | Single-variable what-if (native Calc) |
| `calc_solver` | Constrained optimization on formulas (native Calc) |

Full contracts and RPC details: [calc-analysis-tools.md](calc-analysis-tools.md).

## Multi-modal & research

- **Web research**: Local [smolagents](https://github.com/huggingface/smolagents) loop + DuckDuckGo. [agent-search.md](agent-search.md) · [search-engine-integration.md](search-engine-integration.md).
- **Audio / voice**: [audio-architecture.md](audio-architecture.md).
- **Image generation**: [image-generation.md](image-generation.md).
- **Local OCR**: Docling / RapidOCR via Vision Helpers. [image-recognition.md](image-recognition.md).

## Cross-document & intelligence

- **LO-DOM**: Structural document model. [lo-dom-semantic-tree.md](lo-dom-semantic-tree.md).
- **Memory / librarian**: [hermes-agent-patterns.md](hermes-agent-patterns.md) · [librarian-agentic-onboarding.md](librarian-agentic-onboarding.md).
- **Locales**: [localization.md](localization.md).
- **Sibling-folder reads**: Say *my* / *our* in chat to read other files beside the saved document. [multi-document plan](multi-document-dev-plan.md).
- **Embeddings + FTS** (optional): `writeragent_embeddings/` corpus beside documents. [embeddings.md](embeddings.md).

## Local Python execution

- **Run Python Script**: Analysis, Viz, Math, Units, Quant, Optimize, Vision, SQL (DuckDB). Configure venv in **Settings → Python**.
- **Shared kernel / init scripts / document-attached scripts**: Jupyter-like state, workbook startup, scripts stored in the document.
- **Sandbox**: Out-of-process venv + AST executor. [enabling_numpy_in_libreoffice.md](enabling_numpy_in_libreoffice.md) · [numpy-serialization.md](numpy-serialization.md).

## Editing & formatting

- Surgical text replacement; HTML import for tables/lists; tracked deletions; single-undo streamed rewrites. [llm-styles.md](llm-styles.md) · [reviewable-agent-edits.md](reviewable-agent-edits.md).

## MCP & external agents

- **MCP server**: Enable in Settings; default `http://localhost:8765/mcp`. Full protocol, document targeting, and integrator notes: [mcp-protocol.md](mcp-protocol.md).
- **Cursor / Hermes helpers**: [cursor-libreoffice](https://github.com/KeithCu/cursor-libreoffice) · [libreoffice-skill](https://github.com/KeithCu/libreoffice-skill).
- **Agent backends**: Local (Ollama, LM Studio) or cloud (OpenRouter, Together.AI, …). Optional external ACP agents ([Hermes](https://github.com/NousResearch/hermes-agent), Grok Build) with HITL approve/reject.

## Architecture, evals, roadmap

| Topic | Doc |
|-------|-----|
| Architecture overview | [writeragent-architecture.md](writeragent-architecture.md) |
| Sidebar / chat FSM | [chat-sidebar-implementation.md](chat-sidebar-implementation.md) |
| Streaming / threading | [streaming-and-threading.md](streaming-and-threading.md) |
| Formal verification | [formal_verification.md](formal_verification.md) |
| LLM evals & benchmarks | [benchmarks.md](benchmarks.md) · [scripts/prompt_optimization/](../scripts/prompt_optimization/README.md) |
| Product / engineering roadmap | [ROADMAP.md](ROADMAP.md) |

## Showcase

Screenshots and sample docs live under [`Showcase/`](../Showcase/).

## Build chronicle (blog)

See [The Evolution of WriterAgent](../README.md#the-evolution-of-writeragent) in the root README for the weekly writeups.
