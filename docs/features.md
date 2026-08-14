# WriterAgent — Feature docs index

Product overview lives in the root [README](../README.md). This page maps each area to deeper topic docs.

## Writer

| Topic | Docs |
|-------|------|
| Specialized toolsets | [writer-specialized-toolsets.md](writer-specialized-toolsets.md) |
| Page layout | [page-api-reference.md](page-api-reference.md) |
| Shapes | [shape_support.md](shape_support.md) |
| Bookmarks | [bookmarks-api-reference.md](bookmarks-api-reference.md) |
| Footnotes | [footnotes-api-reference.md](footnotes-api-reference.md) |
| Track changes | [writer-tracking-api-reference.md](writer-tracking-api-reference.md) |
| Grammar pipeline | [realtime-grammar-checker-plan.md](realtime-grammar-checker-plan.md) |
| Math / TeX | [math-tex.md](math-tex.md) |
| Styles / LLM HTML | [llm-styles.md](llm-styles.md) · [LLM_STYLES.md](../LLM_STYLES.md) |
| Reviewable edits | [reviewable-agent-edits.md](reviewable-agent-edits.md) |
| Rich-text sidebar | [rich-text-control-sidebar.md](rich-text-control-sidebar.md) |
| Chat sidebar | [chat-sidebar-implementation.md](chat-sidebar-implementation.md) |

## Calc

| Topic | Docs |
|-------|------|
| NumPy / `=PY()` | [enabling_numpy_in_libreoffice.md](enabling_numpy_in_libreoffice.md) |
| LibrePy (Python-only OXT) | [libreoffice-core-python-extension-split.md](libreoffice-core-python-extension-split.md) · [enabling_numpy_in_libreoffice.md](enabling_numpy_in_libreoffice.md) |
| Data shapes | [calc-py-data-shapes.md](calc-py-data-shapes.md) |
| Domain helpers (Viz, Math, Quant, …) | [numpy-domains.md](numpy-domains.md) |
| Analysis tools | [calc-analysis-tools.md](calc-analysis-tools.md) · [analysis-sub-agent.md](analysis-sub-agent.md) |
| Specialized toolsets | [calc-specialized-toolsets.md](calc-specialized-toolsets.md) |
| Sheet → Python | [calc-spreadsheet-to-python-import.md](calc-spreadsheet-to-python-import.md) |
| Conditional formatting | [calc-conditional-formatting.md](calc-conditional-formatting.md) |
| Sheet filters | [calc-sheet-filter.md](calc-sheet-filter.md) |
| Serialization | [numpy-serialization.md](numpy-serialization.md) |

### Analysis helpers

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

Contracts and RPC: [calc-analysis-tools.md](calc-analysis-tools.md).

## Multi-modal

| Topic | Docs |
|-------|------|
| Web research | [agent-search.md](agent-search.md) · [search-engine-integration.md](search-engine-integration.md) |
| Image generation | [image-generation.md](image-generation.md) |
| Vision / OCR | [image-recognition.md](image-recognition.md) |
| Audio | [audio-architecture.md](audio-architecture.md) |

## Cross-document & intelligence

| Topic | Docs |
|-------|------|
| LO-DOM | [lo-dom-semantic-tree.md](lo-dom-semantic-tree.md) |
| Embeddings / FTS | [embeddings.md](embeddings.md) |
| Multi-document | [multi-document-dev-plan.md](multi-document-dev-plan.md) |
| Memory | [hermes-agent-patterns.md](hermes-agent-patterns.md) |
| Librarian | [librarian-agentic-onboarding.md](librarian-agentic-onboarding.md) |
| Localization | [localization.md](localization.md) |

## Draw / Impress

| Topic | Docs |
|-------|------|
| Specialized toolsets | [draw-impress-specialized-toolsets.md](draw-impress-specialized-toolsets.md) |
| Shapes | [shape_support.md](shape_support.md) |
| PPT-Master | [ppt-master-integration-plan.md](ppt-master-integration-plan.md) |

## MCP & integrations

| Topic | Docs |
|-------|------|
| MCP protocol | [mcp-protocol.md](mcp-protocol.md) |
| Cursor plugin | [cursor-libreoffice](https://github.com/KeithCu/cursor-libreoffice) |
| LibreOffice skill | [libreoffice-skill](https://github.com/KeithCu/libreoffice-skill) |
| Config examples | [CONFIG_EXAMPLES.md](../CONFIG_EXAMPLES.md) |

## Engineering

| Topic | Docs |
|-------|------|
| Architecture | [writeragent-architecture.md](writeragent-architecture.md) |
| Streaming / threading | [streaming-and-threading.md](streaming-and-threading.md) |
| Formal verification | [formal_verification.md](formal_verification.md) |
| Test architecture | [test_architecture_analysis.md](test_architecture_analysis.md) |
| LLM hacks | [llm-hacks.md](llm-hacks.md) |
| Benchmarks | [benchmarks.md](benchmarks.md) · [scripts/prompt_optimization/](../scripts/prompt_optimization/README.md) |
| Type checking | [type-checking.md](type-checking.md) |
