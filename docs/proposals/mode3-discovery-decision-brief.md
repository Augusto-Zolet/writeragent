<!-- Branch: explore/mcp-direct-tools · Decision brief for MODE 3 (multi-agent web research, verified) -->
<!-- Companion to mcp-direct-tool-exposure.md. Raw research in mode3-research-appendix.md -->

# Mode 3: Client-Agnostic Tool Exposure for a Large MCP Catalog — Decision Brief

**Date of brief:** 2026-06-15 · **Scope:** self-hosted LibreOffice MCP server (localhost Streamable-HTTP), ~138 specialized tools across ~30 domains + ~12 core tools · **Constraint:** must serve clients that lack provider-native tool search (Codex CLI, Cursor, ChatGPT, generic MCP clients).

---

## 1. The landscape of viable approaches

**A. Server-side discovery / search meta-tool** (`find_tools(query, domain?)` → schemas → agent calls the real tool by name).
*What it is:* one (or two) always-loaded meta-tool(s) that search the catalog and return matching tool schemas on demand; the model then invokes the real tool. *Maturity:* mature and battle-tested — it is what every leading gateway actually ships: Docker Dynamic MCP's `mcp-find`/`mcp-exec` (https://docs.docker.com/ai/mcp-catalog-and-toolkit/dynamic-mcp/, blog 2026... see https://www.docker.com/blog/dynamic-mcps-stop-hardcoding-your-agents-world/), Cloudflare's non-code `search_and_execute` (https://blog.cloudflare.com/code-mode-mcp/, 2026-02-20), IBM ContextForge `search_tools` (https://github.com/IBM/mcp-context-forge), and FastMCP's v3.1.0 "Tool Search" transform which ships exactly `search_tools` + `call_tool` over standard `list_tools()`/`call_tool()` (https://gofastmcp.com/servers/transforms/tool-search). AWS Prescriptive Guidance lists a "search function" as one of three discovery strategies and recommends "tool filtering or semantic search" by name pattern, description, or domain/category tags (https://docs.aws.amazon.com/prescriptive-guidance/latest/mcp-strategies/mcp-tool-strategy-discovery.html). *Client-agnostic?* **Yes — fully.** It relies only on the universally-supported `tools/list` + `tools/call` primitives. *Fit for us:* **excellent** — maps 1:1 onto our existing domain registry; our server already permits direct call-by-name after discovery, so we need no `execute_tool` proxy.

**B. Tool-RAG / semantic retrieval** (the *ranking backend* for approach A, not a separate architecture).
*What it is:* back the discovery tool's `query` with embeddings (and/or BM25) over tool name+description+arg-names instead of pure substring match. *Maturity:* strong academic + industry support. RAG-MCP (arXiv:2505.03275, 2025-05-06, https://arxiv.org/abs/2505.03275) reports >50% token reduction and triples selection accuracy (43.1% vs 13.6%); a vector-retrieval study reports 99.6% token reduction, 97.1% hit-rate@3 over 121 tools (arXiv:2603.20313 — **pre-print, treat as directional**). Hybrid semantic+BM25 outperforms pure regex/BM25 in two independent vendor reports (Stacklok 94%/98% vs Anthropic Tool Search 34%/48%, https://stacklok.com/blog/...; Arcade 56%/64%, https://blog.arcade.dev/anthropic-tool-search-claude-mcp-runtime — **vendor magnitudes unconfirmed; direction corroborated**). *Client-agnostic?* **Yes** (it lives inside approach A). *Fit for us:* **excellent and low marginal cost** — we already ship an embeddings stack; indexing ~138 tool docs is trivial (brute-force cosine over 138 vectors is instant; no FAISS needed). Note context: 138 tools is *past* the danger threshold — Anthropic observes selection accuracy degrades beyond 30–50 tools (https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool); "How Many Tools Should an LLM Agent See?" (arXiv:2605.24660, 2026-06-07) recommends a query-dependent top-K (~1.4–7.4), not a fixed number.

**C. Code execution with MCP / tools-as-code.**
*What it is:* present the catalog as a code/filesystem API; the agent writes code that imports and chains only the tools it needs. Two flavors: Anthropic's "Code execution with MCP" (2025-11-04, https://www.anthropic.com/engineering/code-execution-with-mcp; ~150k→2k tokens) which runs in the **client harness** — a proposal with **no reference implementation** (Simon Willison, 2025-11-04, https://simonwillison.net/2025/Nov/4/code-execution-with-mcp/); and Cloudflare "Code Mode" (https://blog.cloudflare.com/code-mode-mcp/, 2026-02-20; ~99.9% reduction) which runs `search()`/`execute()` **server-side** in a V8 isolate. *Maturity:* Anthropic flavor proposal-stage; Cloudflare flavor shipped but tied to Workers/isolate infra. *Client-agnostic?* The client-harness flavor is **NO** (needs a sandbox in Codex/Cursor/ChatGPT, which they don't provide); the server-side flavor is **yes**. *Fit for us:* **poor as Mode 3.** It is strictly heavier — it means embedding a secure code interpreter inside a LibreOffice extension process (sandboxing, resource limits, escaping the document model) for only ~150 tools. **Critically, it does NOT replace discovery:** Anthropic's own article keeps a `search_tools` tool, Cloudflare ships `search()`, StackOne confirms agents call `search_tools` before writing code (verdict CODE-EXEC-DISPLACES = NUANCED/REFUTED on that inference). Code execution's unique extra win is keeping large *intermediate results* out of context — a marginal benefit for doc-manipulation tools. Treat as a *future optimization*, not Mode 3.

**D. MCP-native `searchTools` / progressive-disclosure (spec primitives).**
*What it is:* native filtering in the protocol itself — SEP-1821 "Dynamic Tool Discovery" (optional `query` on `tools/list` + a `tools.filtering` capability flag; draft 2025-11-17, https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1821), SEP-1888 progressive-disclosure `searchTools` meta-tool (draft 2025-11-24, .../issues/1888), SEP-1881 scope-filtered discovery (draft 2025-11-24). *Maturity:* **all drafts, none adopted.** Verified against the normative spec: the adopted **2025-11-25** `tools/list` supports only `cursor` pagination + `listChanged` — **no `query`/filter parameter** (https://modelcontextprotocol.io/specification/2025-11-25/server/tools); the **2026-07-28 release candidate** adds Tasks, stateless core, and `tools/list` *caching* (`ttlMs`) but still **no search/filter** (https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/). *Client-agnostic?* Would be ideal once adopted, but no client understands it today. *Fit for us:* not yet buildable; design our meta-tool so its logic re-exposes cleanly through filtered `tools/list` later (near-zero rework). **Do not rely on `tools/list_changed` as a discovery mechanism** — needs persistent transport and client support is inconsistent (VS Code does not surface mid-conversation tools until the next turn, https://github.com/microsoft/vscode/issues/303012).

**E. Provider-side deferral (Anthropic / OpenAI tool search).**
*What it is:* the *model platform* searches deferred tools — Anthropic Tool Search Tool (`defer_loading:true` + `tool_search_tool_bm25_20251119`, beta header `advanced-tool-use-2025-11-20`; ~85% token cut, https://www.anthropic.com/engineering/advanced-tool-use, https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool); OpenAI `tool_search`+`defer_loading` in the Responses API, gpt-5.4+ only, with a *client-executed* mode that calls back to your own search (https://developers.openai.com/api/docs/guides/tools-tool-search). *Maturity:* shipped but **model-gated** (Sonnet/Opus 4.x+, Haiku 4.5+; GPT-5.4+; **no Gemini** — open parity request googleapis/python-genai#2185). *Client-agnostic?* **No** — Claude-only / OpenAI-API-only; absent on generic clients. Confirmed: the **Codex CLI specifically still injects MCP tools upfront** (open issue, opened ~Mar 2026, https://github.com/openai/codex/issues/14507), so our premise holds for Codex *today*. *Fit for us:* a **bonus accelerator** that composes on top of Mode 3, not a substitute. Mark deferred tools so Claude/OpenAI-API clients get native search too.

---

## 2. Comparison table

| Approach | Client-agnostic? | Maturity (early 2026) | Impl. cost for us | Context savings |
|---|---|---|---|---|
| **A. Server-side discovery meta-tool** | ✅ Full (works on every MCP client) | High — shipped by Docker, Cloudflare, IBM, FastMCP | **Low** — reuses domain registry; no execute proxy needed | ~85–99% (Speakeasy: 405k→~5k on 400 tools) |
| **B. Tool-RAG backend (semantic+BM25)** | ✅ (lives inside A) | High academic + vendor; magnitudes pre-print/vendor | **Low** — embeddings stack already shipped | Best retrieval accuracy (97%+ hit@3) |
| **C. Code execution / tools-as-code** | ⚠️ Only server-side flavor; client-harness flavor NO | Mixed — Anthropic proposal-only; Cloudflare shipped (Workers-tied) | **High** — sandboxed interpreter inside LibreOffice ext | ~98–99% (vendor, favorable cases) |
| **D. MCP-native `searchTools` (SEP-1821/1888)** | ✅ once adopted; ❌ today | **Draft only — not adopted** | N/A (not buildable) | N/A |
| **E. Provider-side deferral (Anthropic/OpenAI)** | ❌ Model-gated; no Gemini; Codex CLI not wired | Shipped but gated | Low (flag tools) | ~85% (Claude only) |

---

## 3. Recommendation for Mode 3

**Build a single server-side discovery meta-tool, `find_tools(query, domain?)`, backed by hybrid semantic+BM25 retrieval over your existing domain registry. This is the SOTA client-agnostic answer — and it IS a `find_tools`, just a smarter one than pure substring.**

Why this beats the alternatives against our constraints:
- It is the **only** approach that works uniformly across Codex CLI, Cursor, ChatGPT, and generic clients today (relies solely on `tools/list`+`tools/call`). Provider-side deferral (E) is model-gated and Codex CLI doesn't even wire it up; native `searchTools` (D) is unadopted draft; code execution (C) is a heavier architecture that *still contains* a discovery layer.
- We already have the two hard prerequisites: a **domain-narrowing registry** (= the deterministic pre-filter) and an **embeddings stack** (= the semantic ranker). Marginal cost is indexing ~138 short docs.

Concrete shape in our server:
1. **Keep the ~12 core tools always-listed** (FastMCP `always_visible` / Anthropic "keep hot tools loaded" principle). Defer the ~138 specialized tools — list them only via discovery.
2. **One tool, `find_tools(query, domain?)`**: `domain` → deterministic high-precision pre-filter via the existing registry; `query` → **hybrid** rank (BM25 + cosine over name/description/arg-names) within/across domains. Return **top ~5 full schemas** (matches Anthropic 3–5 and the chance-corrected adaptive-K finding). Use the one-tool variant — return schemas, let the agent call the real tool **by name** (our server already allows this). Add an `execute_tool` wrapper later **only** if we want to hide names or centralize logging/governance.
3. **Invest in error messages + tagging**: on a misnamed call, return "tool not found; available domains: […]; call find_tools" ("errors are prompts," Synaptic Labs production patterns, https://blog.synapticlabs.ai/bounded-context-packs-production-patterns). All search variants match on name/description/keyword fields, so curate those.
4. **Forward-compat / belt-and-suspenders**: also set `defer_loading:true` for Anthropic/OpenAI-API clients so they get native search on top of our already-small surface; design `find_tools`' logic so it can be re-exposed through SEP-1821 filtered `tools/list` with near-zero rework if/when it lands.

**Net:** Mode 3 = `find_tools` — but specifically the **semantic-hybrid, domain-filterable, single-tool, return-schemas-and-call-by-name** shape. A bare substring `find_tools` would underperform on retrieval and waste the embeddings stack you already own.

---

## 4. Confidence and open uncertainties

**Confidence: HIGH** that a server-side discovery layer is the correct client-agnostic choice today (corroborated across Anthropic, AWS, Cloudflare, IBM, FastMCP, Speakeasy, and the normative spec). **MEDIUM** on the long-run winner between "meta-tool" vs "native `tools/list` filtering" — but both are server-side, so building the meta-tool now is **low-regret**.

What's still uncertain / date-sensitive:
- **The "client-agnostic" premise is a shrinking set, not a durable truth** (verdict DISCOVERY-IS-SOTA = SUPPORTED *with this nuance*). OpenAI's API now has `tool_search`/`defer_loading` (gpt-5.4+) and a *client-executed* mode; the Codex CLI specifically hasn't wired it to general MCP tools (open issue, ~Mar 2026), so the recommendation holds *now* but re-validate per release.
- **Code execution does NOT make discovery unnecessary** (verdict CODE-EXEC-DISPLACES = NUANCED/REFUTED on that inference): the sources promoting it retain `search_tools`/`search()`. Code execution changes *how* discovery is hosted, not *whether* it's needed.
- **SEP-1821/1888/1881 are drafts** (2025-11-17 / -24) with no sponsor; re-check before committing — if `tools/list?query=` is adopted, prefer migrating to it.
- **Provider-native variant IDs/headers are dated and beta** (`*_20251119`, `advanced-tool-use-2025-11-20`); model gating shifts (no Gemini parity as of early 2026).
- **Quantitative magnitudes are mostly vendor-reported or pre-print** (Speakeasy 100x, Stacklok 94% vs 34%, arXiv:2603.20313, arXiv:2605.24660). Treat the *direction* (semantic/hybrid > pure keyword; retrieval accuracy is the whole ballgame) as solid; treat exact percentages as directional, and benchmark on our own 138-tool catalog before publishing any numbers.
