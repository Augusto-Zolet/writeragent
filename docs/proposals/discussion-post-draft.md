<!-- DRAFT for discussion #315 (item 4). Trim to taste before posting. -->

Hi Keith! Following up on **item 4** (reaching the full tool set over MCP). I went deep on this — sharing a concrete proposal before I touch any code.

### The problem (recap)
Over MCP we advertise ~12 core tools; the ~138 specialized ones are only reachable through the `delegate_to_specialized_*` gateway, which spins up a sub-agent and therefore needs an LLM backend configured. I'd like to reach them **directly** — without that indirection, and without dumping 138 schemas into the model's context (~17k tokens, past the ~30–50-tool point where selection accuracy starts dropping).

### Shape: one config flag, three modes
Exactly your "feature behind a config flag, default off" idea — `mcp.tool_exposure_mode`:

| Mode | What it does | Who it's for |
|---|---|---|
| `delegate` *(default)* | today's behavior, unchanged | everyone / domains that need the sub-agent's scaffolding |
| `direct_flat` | advertise **all** specialized tools | clients with native tool-search (Claude API; OpenAI Responses API gpt-5.4+ `defer_loading`) |
| `direct_discovery` | small list **+ a `find_tools` search tool** | **any** client, including Codex CLI / generic ones |

### Why keep `direct_flat` (and the honest part)
I checked whether native tool-search "performs better" enough to justify this mode. Honestly: **not on retrieval quality** — Anthropic's Tool Search Tool is BM25/regex-based, and independent reports suggest a good server-side **semantic+BM25** search can match or beat it (I'd treat the magnitudes as directional). So I'm *not* selling `direct_flat` as the high-performance mode. Its real value is **native integration**: capable clients already have an in-context, prompt-cache-friendly search built in — but it only kicks in if the server advertises the full catalog. `direct_flat` is the server half they need, it's a ~1-line change, and it skips the extra `find_tools` round-trip for those clients. (Foot-gun: for clients *without* native search it's the bloat case, so it's explicitly a "capable-client" mode.)

### Why `direct_discovery` is the state of the art + how I'd build it
For client-agnostic large catalogs, a **server-side discovery meta-tool** is where the ecosystem has converged — Docker MCP Gateway (`mcp-find`/`mcp-exec`), Cloudflare (`search_and_execute`), IBM ContextForge (`search_tools`), FastMCP's Tool Search transform. The MCP spec is heading the same way (SEP-1821, SEP-1888) but **nothing's adopted yet**, so we build it now and it migrates cleanly to native `tools/list` filtering later. Concretely:

- **one tool, `find_tools(query, domain?)`**: `domain` → a precise pre-filter via the existing domain registry; `query` → **hybrid semantic + BM25** ranking over tool name/description/args; return the **top ~5 full schemas**.
- the agent then calls the real tool **by name** — which already works (the server routes `tools/call` by registry lookup, not by the advertised list).
- keep the ~12 core tools always listed (hot tools). We already ship an embeddings stack, so the semantic ranker is basically free (index ~138 short docs).
- this is **our** server-side mechanism — *not* Anthropic's Tool Search Tool (which is client-side); they compose (we can also flag tools `defer_loading` so capable clients get native search on top).

### Should the agent pick the mode?
I'd keep it a **config flag**, not a model decision. The right mode depends on the *client's* capability (does it have native tool-search?), which the model can't reliably self-determine, and a model-chosen mode adds nondeterminism. Note the agent *already* "chooses what it needs" within `direct_discovery` by calling `find_tools`. A nicer future option is for the server to auto-select from the client's declared capabilities at `initialize` — but that isn't standardized for tool-search yet, so config is the right v1.

### One caveat worth flagging (the scaffolding thing)
The delegate doesn't only route — it injects per-domain hints/examples and **live context** (e.g. the spreadsheet snapshot) that a few domains (charts/analysis/calc/shapes) lean on. In the direct modes that's lost, so those domains may need the hints folded into their descriptions / the `find_tools` result, or stay on `delegate`. So `delegate` keeps a permanent niche — this isn't "kill the gateway."

### Phasing (each behind the flag, default `delegate`)
1. `direct_flat` — ~1 line.
2. Fold the load-bearing hints into tool descriptions (good hygiene regardless).
3. `find_tools` — the recommended steady-state.

What do you think? Happy to start with the tiny `direct_flat` slice so we can try it end-to-end behind the flag.
