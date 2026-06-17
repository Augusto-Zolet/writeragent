<!-- DRAFT for discussion #315 (item 4). Trim to taste before posting. -->

Hi Keith! Coming back to the idea of making the full tool set easier to reach over MCP — I went deep on it and worked out the following approach:

### The problem (recap)
Over MCP we advertise ~12 core tools; the ~138 specialized ones are only reachable through the `delegate_to_specialized_*` gateway, which spins up a sub-agent and therefore needs an LLM backend configured. I'd like to reach them **directly** — without that indirection, and without dumping 138 schemas into the model's context (~17k tokens, past the ~30–50-tool point where selection accuracy starts dropping).

### Modes, selectable by a config flag
By default we keep today's behavior; the flag is `mcp.tool_exposure_mode`:

| Mode | What it does | Who it's for |
|---|---|---|
| `delegate` *(default)* | today's behavior, unchanged | anyone with a sub-agent backend running |
| `direct_flat` | advertise **all** specialized tools | clients with native tool-search (Claude API; OpenAI gpt-5.4+) |
| `direct_discovery` | small list **+ a `find_tools` search tool** | everyone, engine-agnostic |

### 1. `direct_flat` — why keep it (and the honest part)
I checked whether native tool-search "performs better" enough to justify this mode. Honestly: **not on retrieval quality** — Anthropic's Tool Search Tool is BM25/regex-based, and independent reports suggest a good server-side **semantic+BM25** search can match or beat it (treat the magnitudes as directional). So I'm *not* selling `direct_flat` as the high-performance mode. Its real value is **native integration**: capable clients already have an in-context, prompt-cache-friendly search built in, but it only kicks in if the server advertises the full catalog. `direct_flat` is the server half they need, it's a ~1-line change, and it skips the extra `find_tools` round-trip for those clients. (Foot-gun: for clients *without* native search it's the bloat case, so it's explicitly a "capable-client" mode.)

### 2. `direct_discovery` (`find_tools`) — the client-agnostic SOTA, a **server-side discovery meta-tool** is where the ecosystem has converged: Docker MCP Gateway (`mcp-find`/`mcp-exec`), Cloudflare (`search_and_execute`), IBM ContextForge (`search_tools`), FastMCP's Tool Search transform. The MCP spec is heading the same way (SEP-1821, SEP-1888) but **nothing's adopted yet**. Concretely:

- **one tool, `find_tools(query, domain?)`**: `domain` → a precise pre-filter via the existing domain registry; `query` → ranking over tool name/description/args; returns the **top ~5–8 full schemas**, plus the available domains and per-domain usage hints. The agent then calls the real tool **by name** — which already works (the server routes `tools/call` by registry lookup, not by the advertised list).
- keep the ~12 core tools always listed (hot tools); `find_tools` is hidden from the chat agent and only advertised in this mode.

**On the ranker — a deliberate divergence from my own research.** The decision brief recommends a **semantic+BM25** backend, and the evidence for that is solid (see `mode3-discovery-decision-brief.md`). But `find_tools` has to run **inline in `tools/call` on the host process**, where the embeddings stack (venv, separate process / main-thread hop) isn't readily available. Making discovery depend on the venv would add a dependency, latency, and a failure mode to the one call that needs to be **instant and always-available**. So v1 is a **host-side lexical ranker (BM25-lite + substring bonus)**: zero deps, runs in <1 ms, can't break when the venv isn't ready — and live it already returns the right tools for real queries (`"insert a footnote"` → `footnotes_insert`, `"make a chart from a range"` → the chart tools). **Semantic is the clean next step, not abandoned**: the `_rank` seam is stable, so swapping in embeddings later is a drop-in, and the research stands as the justification for that upgrade.

This is **our** server-side mechanism — *not* Anthropic's Tool Search Tool (which is client-side); they compose (we can also flag tools `defer_loading` so capable clients get native search on top).

### 3. A related fix that fell out: addressing documents by id
Validating the direct modes with several docs open surfaced a real gap. Tools default to **the active document**, and you can pin a specific one only by its file URL (`document_url`). That has two holes: **unsaved/untitled docs have no URL**, so they're unaddressable; and the UNO "current component" is flaky right after a window opens (I saw `list_open_documents` report one doc active while the very next call resolved another).

Small fix, built on what's already there: every open component exposes a stable `RuntimeUID` (we already read it for the mutation-gate key). Expose it as `uid` in `list_open_documents`, and let the resolver match `document_url` against the URL **or** the uid. Then **every open doc is addressable — saved or not, active or not.** Validated live: inserted text into an unsaved "Untitled" Writer doc by uid while a Calc doc was the active one.

It's separable (its own small PR), but it composes directly with the direct modes: when the agent drives multiple docs itself, it should pin them by id instead of trusting "active".

### Should the agent pick the mode?
I'd keep it a **config flag**, not a model decision. The right mode depends on the *client's* capability (does it have native tool-search?), which the model can't reliably self-determine, and a model-chosen mode adds nondeterminism. Note the agent *already* "chooses what it needs" within `direct_discovery` by calling `find_tools`. A nicer future option is for the server to auto-select from the client's declared capabilities at `initialize` — but that isn't standardized for tool-search yet, so config is the right v1.

### One caveat worth flagging (the scaffolding thing)
The delegate doesn't only route — it injects per-domain hints/examples and **live context** (e.g. the spreadsheet snapshot) that a few domains (charts/analysis/calc/shapes) lean on. In the direct modes that's lost, so those domains may need the hints folded into their descriptions / the `find_tools` result, or stay on `delegate`. So `delegate` keeps a permanent niche — this isn't "kill the gateway."

### Status / phasing (each behind the flag, default `delegate`)
1. ✅ `direct_flat` — ~1 line; done + live (Calc 74 / Writer 102).
2. ✅ `direct_discovery` / `find_tools` — done; lexical ranker, 19 unit tests + live on Calc & Writer.
3. ⬜ Fold the load-bearing hints into tool descriptions (good hygiene regardless) — the main remaining piece.
4. ⬜ (separable) the `uid` doc-targeting fix above.
5. ⬜ (later) semantic ranker behind the embeddings venv — the `_rank` seam is ready for it.

What do you think? It's all behind the flag with `delegate` unchanged, so it's safe to land incrementally — happy to open the tiny `direct_flat` slice first so we can try it end-to-end.
