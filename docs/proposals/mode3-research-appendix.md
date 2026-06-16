# Mode 3 — research appendix (raw)

Raw output of the SOTA web-research workflow (branch `explore/mcp-direct-tools`). Verdict + recommendation in `mode3-discovery-decision-brief.md`.


## Adversarial verdicts


### [discovery-is-sota]

I now have enough to render a precise, adversarially-tested verdict. The key findings crystallize the nuance:

1. **Codex CLI specifically still injects MCP tools upfront** (issue #14507, open, opened March 2026) — so for the Codex CLI *today*, there is no client-side tool search, which supports the claim's premise for that client.
2. **BUT** the OpenAI *API platform* now has `tool_search` with `defer_loading: true` for MCP servers (gpt-5.4+), which is a client-side mechanism analogous to Anthropic's — so the broad "Codex e.g." framing is becoming time-sensitive, and "clients without client-side tool search" is a shrinking set.
3. The **adopted MCP spec (2025-11-25, and the 2026-07-28 RC)** still has **no native `tools/list` search parameter** — confirmed by reading the normative spec directly. Native client-understood search is not available.
4. A **server-side discovery/search meta-tool is genuinely client-agnostic and is what the leading gateways ship** (Docker `mcp-find`/`mcp-exec`, Cloudflare `search_and_execute`, ContextForge `search_tools`), and AWS blesses the "search function" / semantic filtering as best practice.

The one genuine weakness vs. an unqualified "SOTA" claim: server-side meta-tools are not the *only* client-agnostic approach (server-side **static filtering / virtual servers / domain-scoped sub-servers** is a widely-shipped, simpler client-agnostic alternative), and the "code execution / Code Mode" variant arguably posts better numbers. So the meta-tool is *a* leading client-agnostic SOTA pattern, not the uniquely correct one.

VERDICT: **SUPPORTED (with one material nuance)**

The claim holds on its load-bearing parts, verified against dated authoritative sources:

DECISIVE CITED EVIDENCE

- **No native client-understood tool-search exists in the adopted MCP spec** — so you cannot rely on a built-in mechanism, and any cross-client solution must be server-side. I read the normative spec page directly: MCP **2025-11-25** `tools/list` supports only `cursor` pagination and `listChanged`, with **no `query`/search/filter parameter and no filtering capability** (https://modelcontextprotocol.io/specification/2025-11-25/server/tools). The **2026-07-28 release candidate** (latest as of mid-2026) adds stateless core, Tasks, and `tools/list` *caching* (`ttlMs`) but still **no search/filter/dynamic discovery** (https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/). The cited native-search ideas (SEP-1821/1888) remain unadopted drafts. (Note: one secondary search snippet wrongly attributed "tool search schema support" to the 2025-11-25 spec — the primary spec text refutes that; it was conflating the SEP draft.)

- **Anthropic's Tool Search Tool is Claude-only / client-side**, confirming it cannot serve generic clients. Arcade.dev (Dec 2, 2025): "this tool is exclusively available for Claude … this feature won't work across both" vendors (https://www.arcade.dev/blog/anthropic-tool-search-claude-mcp-runtime/).

- **The server-side discovery/search meta-tool is the pattern the leading client-agnostic gateways actually ship.** Cloudflare Code Mode (Feb 20, 2026) exposes a server-side `search_and_execute` mode — "the server exports just two: `search()` and `execute()`," "No modifications needed on the agent side," "works with the latest MCP specifications," i.e. any MCP-compliant client (https://blog.cloudflare.com/code-mode-mcp/). Docker Dynamic MCP ships `mcp-find` + `mcp-exec` server-side meta-tools (https://docs.docker.com/ai/mcp-catalog-and-toolkit/dynamic-mcp/).

- **A vendor-neutral authority endorses the server-side "search function" / semantic filtering as best practice.** AWS Prescriptive Guidance lists static, dynamic, and **"search function"** discovery, and its best practices recommend "tool filtering or semantic search" to give the LLM "a scoped-down set of tools," filterable by name pattern, description (semantic), or **domain/category tags** (https://docs.aws.amazon.com/prescriptive-guidance/latest/mcp-strategies/mcp-tool-strategy-discovery.html).

MOST IMPORTANT CAVEAT (the nuance that keeps this from being an unqualified SOTA claim)

The claim's "e.g. OpenAI Codex" example is becoming time-sensitive and is the weakest link. As of mid-2026 the **OpenAI API platform has its own client-side tool search** — `tool_search` with `defer_loading: true` for MCP servers on **gpt-5.4+**, including a "hosted (server-side) tool search" mode where OpenAI's platform does the searching (https://developers.openai.com/api/docs/guides/tools-tool-search). The **Codex CLI specifically** has *not yet* wired this up to general MCP tools — they are still injected upfront (open issue #14507, opened ~March 2026: https://github.com/openai/codex/issues/14507), so the premise holds for Codex *right now*. But "clients without a client-side Tool Search Tool" is a **shrinking set**, so the claim is strongest as a *present-tense, client-agnostic portability* recommendation, not a durable architectural truth.

Secondary caveat: a server-side discovery *meta-tool* is **not the only** client-agnostic SOTA option. Server-side **static filtering / "virtual servers" / domain-scoped sub-servers** is a simpler, equally client-agnostic baseline that every serious gateway ships, and **code-execution / Code Mode** posts better token numbers (~99%+ reductions) at higher build cost. So the accurate framing is: a server-side progressive-disclosure mechanism (of which a `find_tools`/discovery meta-tool is the leading, lowest-friction instance) is the right client-agnostic SOTA family — superior to advertising all tools and the only option that works without client-side deferral — rather than the single uniquely-correct mechanism.


### [code-exec-displaces]

I have comprehensive, dated, cross-validated evidence. Here is my verdict.

---

**VERDICT: NUANCED (claim is mostly SUPPORTED on the factual premise, but its inferential clause — "making a discovery meta-tool unnecessary" — is REFUTED by the primary sources).**

**What is solidly SUPPORTED:**
- Anthropic published "Code execution with MCP: building more efficient AI agents" on **Nov 4, 2025**, explicitly promoting the agent-writes-code-that-calls-tools pattern for large catalogs, citing a 150,000→2,000 token (~98.7%) reduction. (https://www.anthropic.com/engineering/code-execution-with-mcp; corroborated same-day by Simon Willison, https://simonwillison.net/2025/Nov/4/code-execution-with-mcp/)
- "Others" are indeed promoting it: Cloudflare "Code Mode" (**Feb 20, 2026**, https://blog.cloudflare.com/code-mode-mcp/) reports ~99.9% reduction on a 2,500-endpoint API; StackOne's comparison (**Mar 31, 2026**, https://www.stackone.com/blog/mcp-token-optimization/) ranks code execution highest on token reduction (98-99% schema + 97-99% response). So "as of late 2025, Anthropic and others promoting code execution as superior for large tool catalogs" is accurate and current.

**What is REFUTED (the decisive caveat):** The clause "potentially making a discovery meta-tool unnecessary" is contradicted by the very sources promoting code execution. The Anthropic article itself states tool definitions are read on-demand from a filesystem AND explicitly adds: *"a `search_tools` tool can be added to the server to find relevant definitions."* Code execution does **not** displace discovery — it **depends on** a discovery layer (filesystem navigation OR a `search_tools`/search meta-tool) and pairs it with code-based execution. Cloudflare's Code Mode ships a dedicated `search()` tool; StackOne confirms agents "use `search_tools` to discover available functions at runtime" before writing code. Discovery and code execution are **complementary stages of the same progressive-disclosure pipeline**, not substitutes. Code execution mainly adds a second win (keeping intermediate tool *results/responses* out of context) that pure tool-search lacks — it does not remove the need to find tools.

**Most important caveat (the client-agnostic requirement):** Code execution is *more* client-agnostic than Anthropic's Claude-only Tool Search Tool (it "works with any MCP-compatible client: Claude Code, Cursor, VS Code, Windsurf, Gemini CLI"), which superficially strengthens the claim. BUT it is **not a drop-in replacement for a server-side meta-tool**: it requires a sandboxed code-execution runtime (V8 isolates, Cloudflare Workers, containers) with resource limits and monitoring, plus exposing the catalog as a code API. StackOne flags this as its key downside: *"Requires sandbox infrastructure. Higher setup complexity than the other three approaches. Agent must generate correct code."* So for a self-hosted, client-agnostic server, code execution is a heavier *architecture* that still contains a discovery component — it raises the bar for what "discovery" looks like rather than eliminating it. The research context's framing (meta-tool is the lighter, portable choice; code execution is a "bigger architectural shift" that itself "mentions a `search_tools` function") is confirmed correct.

**Bottom line:** Promotion of code execution for large catalogs = real and current. "Makes a discovery meta-tool unnecessary" = false as stated; discovery is retained inside the code-execution approach (`search_tools`/`search()`), so at most code execution changes *how* discovery is hosted, not *whether* it's needed.

Sources: https://www.anthropic.com/engineering/code-execution-with-mcp (2025-11-04) · https://simonwillison.net/2025/Nov/4/code-execution-with-mcp/ (2025-11-04) · https://blog.cloudflare.com/code-mode-mcp/ (2026-02-20) · https://www.stackone.com/blog/mcp-token-optimization/ (2026-03-31)


## Research findings


### [mcp-native-and-gateways]

I have everything needed. Here is the synthesized answer.

---

# State of the art for large MCP tool catalogs (late 2025 / early 2026)

**Bottom line for your case:** For a client-agnostic, self-hosted MCP server that must work with Codex/Cursor/ChatGPT/generic MCP clients, a **server-side discovery meta-tool (`find_tools(query/domain)` that returns matching schemas on demand, then the agent calls the real tool by name) is currently the correct and most portable choice.** It is exactly the pattern that every major MCP gateway has converged on (Docker's `mcp-find`/`mcp-exec`, IBM ContextForge's `search_tools`), because the MCP spec itself has **no adopted native tool-search mechanism** as of the latest releases. The competing approaches (Anthropic's Tool Search Tool, "code execution with MCP") are either client-specific or a heavier architecture. Details and citations below.

---

## (a) MCP spec & SEPs — what exists and its STATUS

The key fact: **as of the 2025-11-25 spec and even the 2026-07-28 release candidate, MCP has NOT adopted any native tool-search / `searchTools` / progressive-disclosure mechanism.** All proposals are still **drafts without sponsors**.

| Proposal | Mechanism | Status | Date |
|---|---|---|---|
| **SEP-1821 "Dynamic Tool Discovery"** | Adds optional `query` param to `tools/list` + `ServerCapabilities.tools.filtering` flag; server returns a filtered subset (substring/semantic/tag). | **Draft** — labeled "SEP proposal without a sponsor" | Opened **Nov 17, 2025** |
| **SEP-1881 "Scope-Filtered Tool Discovery"** | Server filters `tools/list` by the OAuth scopes in the access token (security/visibility, not catalog-size). | **Draft / proposal** | Opened **Nov 24, 2025** |
| **SEP-1888 "Progressive Disclosure for Typed Library Discovery & Introspection"** | A standardized `<library>.searchTools` **meta-tool** with two modes (operations discovery + type introspection); explicitly meant to replace registering hundreds of narrow tools. | **Draft**, no labels/milestone | Opened **Nov 24, 2025** |

- SEP-1821: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1821 (Draft, opened 2025-11-17)
- SEP-1881: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1881 (Draft, opened 2025-11-24)
- SEP-1888: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1888 (Draft, opened 2025-11-24)

What the spec *does* have today (all merely existing primitives, not catalog-scaling solutions):
- `tools/list`, `tools/call`, and `notifications/tools/list_changed` — the last lets a server tell the client the tool list changed (e.g., after auth), but this is **dynamic availability, not search**. MCP spec 2025-06-18 server/tools: https://modelcontextprotocol.io/specification/2025-06-18/server/tools. Speakeasy's "dynamic tool discovery" article confirms `list_changed` + `.enable()/.disable()` is about toggling availability, not large-catalog discovery: https://www.speakeasy.com/mcp/tool-design/dynamic-tool-discovery.
- The **2025-11-25** release added Tasks (async), extensions framework, auth/CIMD, tool icons — **nothing for tool search/filtering**. WorkOS summary: https://workos.com/blog/mcp-2025-11-25-spec-update; anniversary post: https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/.
- The **2026-07-28 release candidate** (announced 2026-05-21) adds stateless core, MCP Apps, Tasks, JSON-Schema 2020-12, plus `ttlMs`/`cacheScope` for **caching** `tools/list` — but explicitly **no search/filter/dynamic discovery**. https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/.

**Status verdict (a):** A server-side search/meta-tool is the direction the spec is *exploring* (SEP-1888 is essentially your `find_tools` idea, blessed as a draft), and SEP-1821 would make it a first-class `tools/list` query. But **none is adopted**, so you cannot rely on a native client-understood mechanism today. Building your own meta-tool is the spec-compatible way to get the behavior now. *(Caveat: SEP dates/status are fast-moving — re-check these three issues before committing.)*

---

## (b) Gateways / proxies / toolkits — what they actually do

The ecosystem has **already converged on two patterns**, and the dominant one for *hundreds of tools* is a **server-side discovery meta-tool + on-demand activation** — i.e., your proposed design.

**1. Docker MCP Gateway / "Dynamic MCP" (the clearest example of the meta-tool pattern).**
Exposes ~6 "primordial" meta-tools and nothing else up front:
- `mcp-find` ("Search for MCP servers in the catalog by name or description"), `mcp-add` (instantiate into the current session), `mcp-config-set`, `mcp-remove`, `mcp-exec` ("Execute a tool by name that exists in the current session"), `code-mode`.
- Flow: agent calls `mcp-find` → `mcp-add` → the tools become callable via `mcp-exec`/by name. True on-demand provisioning; added tools are scoped to the current session. With a custom catalog, `mcp-find` searches only within it.
- Docs: https://docs.docker.com/ai/mcp-catalog-and-toolkit/dynamic-mcp/ ; blog "Dynamic MCPs: Stop Hardcoding Your Agents' World": https://www.docker.com/blog/dynamic-mcps-stop-hardcoding-your-agents-world/ ; gateway repo: https://github.com/docker/mcp-gateway. This is **exactly the `find_tools` → call-by-name pattern you described.**

**2. IBM/ContextForge `mcp-context-forge` — two complementary mechanisms.**
- **Virtual servers** (static filtering): group a chosen subset of tools from multiple backends into one logical server, so a client sees e.g. 3 tools instead of the backend's 100+. Used for role-based access, domain isolation, catalog-size reduction. Docs: https://ibm.github.io/mcp-context-forge/manage/catalog/ ; repo: https://github.com/IBM/mcp-context-forge.
- **`search_tools`** (dynamic meta-tool): "token-efficient external tool discovery… via lazy discovery, where tools are found on-demand through keyword search and only discovered tool schemas are included in the context." This is again your meta-tool pattern. (From the project's own materials, surfaced via search; corroborated by feature issue #2171 on user-context-driven dynamic tools: https://github.com/IBM/mcp-context-forge/issues/2171.)

Note ContextForge's design maps almost 1:1 onto your situation: your existing **server-side registry that narrows tools to a named "domain"** is essentially ContextForge "virtual servers," and adding `find_tools(query/domain)` gives you the `search_tools` half. You'd have both patterns the leading gateway offers.

**3. Other gateways — mostly static filtering / virtual servers, fewer with search meta-tools.**
- **Microsoft `mcp-gateway`**: reverse proxy + session-aware routing/lifecycle in Kubernetes — infrastructure, **not** catalog-search. https://github.com/microsoft/mcp-gateway.
- **Azure API Management / API Center**: runtime AI-gateway that proxies tool calls, enforces policy (Entra ID), and provides a private **MCP registry** (API Center) — governance and a *registry*, not an in-band search meta-tool. https://learn.microsoft.com/en-us/azure/api-management/expose-existing-mcp-server ; governance: https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/governance.
- **Pomerium**: secure access/identity gateway in front of MCP servers — auth/policy, **not** catalog scaling. https://www.pomerium.com/docs/capabilities/mcp.
- **mcp-proxy**: transport bridging (stdio↔HTTP/SSE) only — does not address catalog size.
- **MetaMCP**: "middleware support for dynamic tool filtering" (selective exposure). Pattern survey: https://chatforest.com/guides/mcp-gateway-proxy-patterns/.

**Most common pattern across gateways:** **static filtering / "virtual servers"** is the most widely shipped baseline (every serious gateway can subset tools), and the **dynamic search-meta-tool + on-demand load** is the emerging best practice specifically for *hundreds+* of tools, pioneered by Docker Dynamic MCP and ContextForge `search_tools`. Both are server-side and therefore **client-agnostic** — which is what you need.

---

## How this contrasts with the non-portable / heavier alternatives

You explicitly need something that works *without* Anthropic's client-side tool. For completeness, the two most-hyped alternatives and why they don't fit (or only partly fit):

- **Anthropic "Tool Search Tool"** (`tool_search_tool_regex_20251119` / `..._bm25_20251119`, released 2025-11-19): a **client-side / Claude-API feature**. You mark tools `defer_loading: true`; the *model platform* searches and expands `tool_reference` blocks. It supports up to 10,000 tools, returns 3–5 per search, ~85% token reduction — **but it is specific to the Claude Developer Platform / Claude models (Sonnet 4+, Opus 4+, Haiku 4.5+) and Bedrock; it does NOT work for Codex/Cursor/ChatGPT/generic MCP clients.** Docs: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool ; engineering post "advanced tool use": https://www.anthropic.com/engineering/advanced-tool-use. (Interesting detail: it has a *custom client-side implementation* path where your own search tool returns `tool_reference` blocks — but that still presumes an Anthropic client.) **Not viable as your primary mechanism**, though you could layer `defer_loading` for Anthropic clients on top of a server-side `find_tools` for everyone else.

- **"Code execution with MCP" (Anthropic, Nov 4 2025)**: present tools as files/code APIs on a filesystem; the agent reads tool definitions on demand and even composes calls in code. Reports 150k→2k tokens (~98.7%). It *mentions* a `search_tools` function as an alternative discovery method. https://www.anthropic.com/engineering/code-execution-with-mcp. This is powerful but a **bigger architectural shift** (you need a code-execution sandbox and to expose tools as code), and adoption is uneven. For a drop-in, client-agnostic fix it's heavier than a meta-tool. The same idea underlies Docker's `code-mode`.

- **Industry consensus (early–mid 2026):** the "context bloat crisis" writeups frame the menu as (i) tool search, (ii) lazy schema loading, (iii) pagination/server decomposition into narrow domain servers (the "Pinterest approach"). They note tool-search-style approaches reaching GA in client platforms in **Feb 2026**, but caution that *protocol-standardized, cross-client* adoption is still a "6–12 month window" out. https://agentmarketcap.ai/blog/2026/04/08/mcp-context-bloat-enterprise-scale-tool-definitions-agent-context-budget. (Treat the specific GA dates here as a secondary-source claim, not spec fact.)

---

## Recommendation for your server

1. **Yes — ship the server-side `find_tools(query/domain)` meta-tool.** It is the most portable, client-agnostic answer available today, is the pattern the two leading gateways (Docker Dynamic MCP, IBM ContextForge) actually use, and aligns with the only relevant *draft* spec direction (SEP-1888/SEP-1821). Keep the ~12 "core" tools always-on (non-deferred) and expose the ~138 specialized tools only via discovery — mirroring "keep 3–5 frequent tools loaded, defer the rest."
2. **Reuse your existing domain registry as the discovery backend.** Support both a free-text `query` (BM25/substring is fine — it's what SEP-1821 and Anthropic's BM25 variant use) and an exact `domain` filter. This gives you ContextForge's "virtual server" filtering *and* `search_tools` in one tool.
3. **Return enough to act in one hop:** have `find_tools` return the matching tools' **names + full input schemas** (not just names), so the agent can immediately call the real tool by name — your server already permits direct name calls, which is the same `mcp-exec`/expanded-`tool_reference` end state. (Optionally support a two-stage "names first, schema on demand" mode if context is extremely tight — that's the "lazy schema loading" idea.)
4. **Forward-compat / belt-and-suspenders:** also set `defer_loading: true` on the specialized tools when an Anthropic-platform client connects (via the MCP connector's deferred loading), so Claude clients get native Tool Search while everyone else uses `find_tools`. And watch SEP-1821 — if `tools/list?query=` gets adopted, you can expose the same registry behind the native capability and clients will use it automatically. MCP connector deferred loading: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool (MCP integration section).

**Maturity flag:** the *pattern* is mature and battle-tested in gateways (Docker, IBM — production, 2025), but the *native MCP standard* for it is **immature (drafts only)**. So you are building the right thing, just slightly ahead of the spec — which is exactly why doing it server-side is the safe, client-agnostic bet.

---

### Sources
- MCP SEP-1821 (Dynamic Tool Discovery, Draft, 2025-11-17): https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1821
- MCP SEP-1881 (Scope-Filtered Tool Discovery, Draft, 2025-11-24): https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1881
- MCP SEP-1888 (Progressive Disclosure / `searchTools` meta-tool, Draft, 2025-11-24): https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1888
- MCP spec 2025-06-18 (tools, list_changed): https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- MCP 2025-11-25 release (no tool search): https://workos.com/blog/mcp-2025-11-25-spec-update and https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/
- MCP 2026-07-28 release candidate (no tool search; tools/list caching only): https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/
- Speakeasy, dynamic tool discovery = list_changed/enable-disable: https://www.speakeasy.com/mcp/tool-design/dynamic-tool-discovery
- Docker Dynamic MCP (mcp-find/mcp-add/mcp-exec): https://docs.docker.com/ai/mcp-catalog-and-toolkit/dynamic-mcp/ ; blog: https://www.docker.com/blog/dynamic-mcps-stop-hardcoding-your-agents-world/ ; repo: https://github.com/docker/mcp-gateway
- IBM ContextForge (virtual servers + search_tools): https://github.com/IBM/mcp-context-forge ; catalog docs: https://ibm.github.io/mcp-context-forge/manage/catalog/ ; dynamic tools issue #2171: https://github.com/IBM/mcp-context-forge/issues/2171
- Microsoft mcp-gateway: https://github.com/microsoft/mcp-gateway
- Azure API Management MCP: https://learn.microsoft.com/en-us/azure/api-management/expose-existing-mcp-server ; governance: https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/governance
- Pomerium MCP: https://www.pomerium.com/docs/capabilities/mcp
- Gateway/proxy pattern survey: https://chatforest.com/guides/mcp-gateway-proxy-patterns/
- Anthropic Tool Search Tool (client-side, Claude-only, 2025-11-19): https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool ; advanced tool use: https://www.anthropic.com/engineering/advanced-tool-use
- Anthropic "Code execution with MCP" (2025-11-04): https://www.anthropic.com/engineering/code-execution-with-mcp
- Industry "context bloat" status (early–mid 2026): https://agentmarketcap.ai/blog/2026/04/08/mcp-context-bloat-enterprise-scale-tool-definitions-agent-context-budget


### [discovery-meta-tool]

I now have comprehensive, well-dated coverage across all the angles requested. I have enough authoritative sources to synthesize a definitive answer. Let me compile the findings.

---

# State of the art for client-agnostic tool discovery on a large self-hosted MCP server (late 2025 / early 2026)

## Bottom line up front

For your case — a self-hosted MCP server with ~150 tools that must work for **clients that lack Anthropic's client-side Tool Search Tool** (Codex, Cursor, ChatGPT, generic MCP clients) — a **server-side discovery meta-tool is a legitimate, currently-recommended pattern**, and as of early 2026 it is essentially the *only* fully client-agnostic option. It is what Cloudflare, Synaptic Labs, AWS, and multiple others actually ship. The state of the art has two refinements you should adopt:

1. **The dominant shape is a TWO-tool pair** (`search`/`find_tools` + `execute`), not a single tool, *when you also want to hide the underlying tools from the client*. Because **your server already lets the agent call the real tool by name**, you can instead use a **search-and-return-schema** tool and let the agent call the real tool directly — a valid one-tool variant. Both are in production.
2. **Prefer semantic/embedding search or BM25 over pure substring matching**, and **expose domain/category as a filter**, because the strongest published results come from semantic retrieval, and your existing "narrow to a named domain" registry maps directly onto this.

The thing to know that may change your framing: the *most-hyped* 2025–2026 development (Anthropic's Tool Search Tool) is **client-side and Claude-only**, so it does **not** solve your client-agnostic requirement — but it strongly validates the underlying *idea* with hard numbers. A parallel, also-hyped pattern ("code execution with MCP" / Cloudflare "Code Mode") is a more radical alternative worth knowing about.

Distinguishing **"this exists"** from **"this is recommended"** is called out per-item below.

---

## 1. The two big 2025–2026 developments, and why neither is directly your answer

**(A) Anthropic "Tool Search Tool" — client-side, Claude-only. RECOMMENDED by Anthropic, but not client-agnostic.**
Announced Jan 14, 2026; documented under beta header `advanced-tool-use-2025-11-20`. Tools are marked `defer_loading: true`; only a search tool plus critical tools load up front; Claude searches (regex or BM25) and matching schemas are expanded on demand. It explicitly supports deferring whole MCP servers. Reported figures: ~72K → ~8.7K tokens (**85% reduction**); accuracy Opus 4 **49% → 74%**, Opus 4.5 **79.5% → 88.1%**.
- Anthropic, "Introducing advanced tool use," https://www.anthropic.com/engineering/advanced-tool-use
- Credal (Feb 25, 2026), https://www.credal.ai/blog/meta-tools-in-mcp-why-are-they-important

**Critical caveat for you (production critique):** It "works exclusively with Claude"; multi-vendor/coding-agent setups "won't work across both"; it currently needs Anthropic's SDK + beta header, with LangChain/other-framework support still pending; and it provides no authz/governance.
- Arcade.dev (Dec 2, 2025), https://arcade.dev/blog/anthropic-tool-search-claude-mcp-runtime

**Implication:** Tool Search validates the *defer-and-search* idea with the best public numbers, but because the search happens **client-side inside Anthropic's API**, it cannot serve Codex/Cursor/ChatGPT/generic clients. A **server-side** meta-tool reproduces the same benefit in a client-agnostic way. This is exactly the gap you identified.

**(B) "Code execution with MCP" / Cloudflare "Code Mode" — the rival paradigm. EXISTS and is gaining traction; arguably best token numbers, but heavier to build.**
Instead of exposing many tool schemas, present the catalog as a code/filesystem API and give the agent two tools — `search()` (query the spec/file tree) and `execute()` (run generated code that calls the real tools). Anthropic's own write-up reports a workflow going **~150K → ~2K tokens (98.7% reduction)**; Cloudflare reports their 2,500-endpoint API in **~1,000 tokens (~99.9% reduction)** vs ~1.17M if exposed as individual tools.
- Anthropic / MCP discussion #1780, https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/1780
- Simon Willison (Nov 4, 2025), https://simonwillison.net/2025/Nov/4/code-execution-with-mcp/
- Cloudflare "Code Mode" (Feb 20, 2026), https://blog.cloudflare.com/code-mode-mcp/

Note Cloudflare also ships a plain (non-code) **`search_and_execute` mode** that "hides all upstream tools and exposes only two tools … query … and execute" — i.e., the exact server-side meta-tool pair you're considering. So Cloudflare endorses *both* shapes.

---

## 2. The discovery/meta-tool pattern itself — concrete implementations and which SHAPES win

This is your core question. The pattern is well-regarded and shipped by many; the design space has converged on a few shapes:

**Shape A — TWO tools: `find_tools`/`search` + `execute_tool`.** The agent never sees real tool names; it searches, gets schemas, then calls `execute_tool(name, args)`. Used by:
- **Synaptic Labs "Bounded Context Packs" / meta-tool pattern** — two meta-tools (discovery + execution), domain-organized "agents", schemas returned on request. Claimed ~600 tokens startup + ~150/tool, **85–95% reduction** on a 33-tool server. (Jan 27, 2026) https://blog.synapticlabs.ai/bounded-context-packs-meta-tool-pattern
- **Cloudflare `search_and_execute`** (query/execute). https://blog.cloudflare.com/code-mode-mcp/
- **Speakeasy "Semantic Search" variant** — `find_tools` (embeddings) + `execute_tool`. https://www.speakeasy.com/blog/100x-token-reduction-dynamic-toolsets

**Shape B — THREE tools: `list_tools` + `describe_tools` + `execute_tool`** (Speakeasy "Progressive Search"). Hierarchical/prefix navigation for "complete visibility," at the cost of more round-trips. Same source as above.

**Shape C — ONE tool: search returns schemas, agent calls the REAL tool by name.** This is viable **only when the server already allows direct calls to deferred tools** — which is your situation. Anthropic's Tool Search is conceptually this (search → real tool by name); a server-side analog is straightforward. This is the lowest-friction option *for you specifically*.

**Effectiveness data (cite + date):**
- **Speakeasy head-to-head on a 400-tool server** (vs 405,100 static init tokens): Progressive init 2,500 / Semantic init 1,300; simple task 5,500 vs 4,300; complex task 8,200 vs 9,600. Takeaway: **semantic wins on simple tasks and startup; progressive wins on complex/exploratory tasks**. No single winner declared. https://www.speakeasy.com/blog/100x-token-reduction-dynamic-toolsets
- **Academic, vector/embedding retrieval over MCP tools:** **99.6% token reduction, 97.1% hit-rate @K=3, MRR 0.91**, sub-100ms latency, on 140 queries / 121 tools / 5 servers. This is the strongest evidence that **semantic retrieval is the highest-accuracy discovery shape**. (arXiv 2603.20313) https://arxiv.org/abs/2603.20313
- Another independent implementation reports **89% token / 62% latency reduction at ~100% accuracy** (cited via the search-function literature; treat as vendor-grade, not peer-reviewed).

**Verdict on the pattern's regard today:** Strongly and increasingly endorsed as the client-agnostic answer. AWS Prescriptive Guidance lists exactly three strategies — static, dynamic (load all), and **"search function"** — and its **best practices explicitly recommend** "tool filtering or semantic search" to give the LLM "a scoped-down set of tools," noting filtering can be by name pattern, description (semantic), or **domain/category tags**. This is a vendor-neutral authority endorsing precisely your registry-narrowed-by-domain design. https://docs.aws.amazon.com/prescriptive-guidance/latest/mcp-strategies/mcp-tool-strategy-discovery.html

---

## 3. Pitfalls and postmortems (cite + date) — read these before you build

- **Models hallucinate/misname tools** when they can't see schemas (e.g., calling `fileManager_readFile` when it's `contentManager.read`). Fix: error messages that **reveal available domains and say "use getTools"** — "errors are prompts." Also: **batch multi-step ops** in one call to avoid losing coherence; raw `ENOENT`-style errors confuse models. — Synaptic Labs production patterns (Feb 10, 2026), https://blog.synapticlabs.ai/bounded-context-packs-production-patterns
- **Security:** meta-tools add **tool-poisoning via malicious metadata** and **confused-deputy** risks through the orchestration layer; meta-tooling "requires enterprise-grade governance." For a localhost self-hosted server this is lower-stakes, but the discovery tool's returned schemas are still an injection surface. — Credal (Feb 25, 2026), https://www.credal.ai/blog/meta-tools-in-mcp-why-are-they-important
- **Don't rely on the MCP-native `tools/list_changed` notification as your discovery mechanism.** It needs a persistent transport ("not scalable/feasible in a cluster"), and **client support is inconsistent** — e.g., VS Code does not make tools added mid-conversation via `list_changed` discoverable until the next user turn. A meta-tool that returns schemas *in a tool result* sidesteps this entirely and is more client-agnostic. — MCP spec 2025-06-18 (https://modelcontextprotocol.io/specification/2025-06-18/server/tools); VS Code issue #303012 (https://github.com/microsoft/vscode/issues/303012); IBM mcp-context-forge #2171.
- **Small libraries don't benefit** (<10 tools, or all-tools-used-every-session). Not your case at ~150 tools. — Anthropic, https://www.anthropic.com/engineering/advanced-tool-use

---

## 4. Concrete recommendation for your server

1. **Yes, ship a server-side discovery meta-tool — it is the right call for client-agnosticism.** It's the only approach that works uniformly across Codex, Cursor, ChatGPT, and generic MCP clients today. (Tool Search and Code Mode are either Claude-only or much heavier.)
2. **Make discovery semantic + domain-filterable.** Expose `find_tools(query, domain?)`. Back `query` with embeddings or BM25 over name+description (semantic has the best published hit-rate, 97.1%@3; BM25 is what Anthropic itself uses and needs no model). Wire `domain` straight to your existing registry — AWS explicitly blesses domain/category-tag filtering.
3. **Pick your tool count based on whether you hide names.** Since your server already lets the agent call real tools by name, the **one-tool variant (Shape C: `find_tools` returns schemas → agent calls the real tool)** is the least friction and avoids an extra `execute` indirection. Add the `execute_tool` wrapper (Shape A) only if you later want to hide the catalog or centralize logging/governance.
4. **Keep your ~12 core tools always-loaded** (the Tool Search "critical tools" / `defer_loading:false` idea); defer the ~138 specialized ones behind discovery.
5. **Invest in error messages and batching** per the Synaptic Labs postmortem — return "tool not found; available domains: […]; call find_tools" on misnamed calls, and support a batched/chained call if multi-step tasks are common.
6. **Optionally layer in Anthropic's Tool Search for Claude clients** as a bonus (mark deferred tools), since it composes with a server-side approach — but treat your server-side meta-tool as the baseline that serves everyone.

**Uncertainty / date-sensitivity flags:** The Speakeasy 400-tool numbers and several vendor "89–99%" claims are vendor benchmarks, not peer-reviewed; treat magnitudes as directional. The arXiv paper (2603.20313) is recent and pre-print. Tool Search and Code Mode are both behind betas / fast-moving (Nov 2025–Feb 2026); framework support (LangChain etc.) for Tool Search was still pending as of Dec 2025 and may have shifted. Client behavior around `list_changed` is client-version-specific.

**Sources:**
- https://www.anthropic.com/engineering/advanced-tool-use
- https://arcade.dev/blog/anthropic-tool-search-claude-mcp-runtime
- https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/1780
- https://simonwillison.net/2025/Nov/4/code-execution-with-mcp/
- https://blog.cloudflare.com/code-mode-mcp/
- https://blog.synapticlabs.ai/bounded-context-packs-meta-tool-pattern
- https://blog.synapticlabs.ai/bounded-context-packs-production-patterns
- https://www.speakeasy.com/blog/100x-token-reduction-dynamic-toolsets
- https://arxiv.org/abs/2603.20313
- https://www.credal.ai/blog/meta-tools-in-mcp-why-are-they-important
- https://docs.aws.amazon.com/prescriptive-guidance/latest/mcp-strategies/mcp-tool-strategy-discovery.html
- https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- https://github.com/microsoft/vscode/issues/303012


### [tool-rag-retrieval]

I have everything I need, with strong primary-source corroboration across vendors, the MCP spec, and academic benchmarks. Here is the synthesis.

---

# Tool RAG / dynamic tool retrieval for large MCP tool sets — state of the art (late 2025 / early 2026)

## Bottom line for your case

For a self-hosted, client-agnostic MCP server with ~138 specialized + ~12 core tools and an embeddings stack already on board: **a server-side discovery meta-tool is the correct, current best-practice architecture** — and it is exactly the direction both the MCP spec and the major non-Anthropic clients are converging on. The one upgrade the evidence strongly supports: make that meta-tool's retrieval **hybrid (semantic embeddings + keyword/BM25)** rather than pure keyword. Tool-RAG is *not* overkill at 138 tools — that count sits right in the zone where retrieval starts to matter — but it is also not a heavy lift for you, because the hard part (an embedding model/index) is already shipped. Full "tool-RAG framework" machinery (query rewriting, re-ranking, auto-sync CRUD pipelines from the papers) *is* overkill at this scale.

---

## 1. Is a server-side discovery meta-tool the right call? Yes — it's becoming the standard, cross-vendor.

This is the strongest "recommended, not merely exists" signal I found:

- **The MCP spec itself is adding exactly this.** SEP-1821 "Dynamic Tool Discovery" (Standards Track proposal, **created 2025-11-17**, author Egor Orlov) adds an optional `query` field to `ListToolsRequest` plus a `ServerCapabilities.tools.filtering` flag. Crucially, it **leaves the search method to the server**: *"Server implements simple search strategies optimized for LLM/agent usage (substring matching, semantic search, tag matching, category filtering)."* Status: **Draft, seeking sponsor** (so: not yet ratified — flag this as in-flight). Your `find_tools(query/domain)` is essentially a hand-rolled version of this, and your existing domain registry maps directly onto its category/tag filtering. https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1821 (PR #1822)

- **OpenAI Codex independently converged on the same pattern.** Codex automatically defers MCP tools and exposes an **`MCPSearch`** tool when "MCP tool descriptions exceed 10% of the context window," discovering tools on demand instead of loading them upfront. This is direct evidence the meta-tool/deferral pattern is client-agnostic in practice, not Anthropic-specific. (GitHub issues openai/codex #9266, #2335, #21318; issue dates Jan–May 2026.) https://github.com/openai/codex/issues/9266

- **Anthropic's own Tool Search Tool is, mechanically, a server-side discovery tool** (it runs on Anthropic's API, not in the client) — but it's **model-gated** (Sonnet 4.0+/Opus 4.0+/Haiku 4.5+) and Anthropic-API-specific, so it does *not* solve your "works for Codex/Cursor/generic MCP clients" requirement. Your own server-side meta-tool does. Notably, Anthropic explicitly blesses custom search: *"you can also implement custom search tools using embeddings or other strategies."* https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool ; https://www.anthropic.com/engineering/advanced-tool-use (2025-11-24)

- **Speakeasy's framing** distinguishes "progressive discovery" (hierarchical meta-tools: `list_tools` → `describe_tools` → `execute_tool`) from "semantic search" (`find_tools` → `execute_tool`). Both hit ~**100x token reduction** for a 400-tool server (405K → ~5K tokens). Your design is the `find_tools` shape. https://www.speakeasy.com/blog/100x-token-reduction-dynamic-toolsets

Caveat on "execute_tool": the papers/Speakeasy often route the final call through a generic `execute_tool` proxy. **You don't need that** — your server already lets the agent call the real tool by name after discovery, which is cleaner and avoids an extra indirection layer.

## 2. Is the context-bloat problem real at ~138 tools? Yes — you're past the danger threshold.

- Anthropic: tool-selection accuracy "degrades significantly once you exceed **30–50** available tools." Their MCP eval: Opus 4.5 accuracy went **79.5% → 88.1%** with on-demand loading; Opus 4 **49% → 74%**; context for a multi-server setup dropped ~**77K → 8.7K tokens** (~85% reduction). https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool
- "How Many Tools Should an LLM Agent See? A Chance-Corrected Answer" (**arXiv:2605.24660, 2026-06-07**): adaptive short lists beat fixed lists — **93.1% vs 87.1%** on BFCL, and **76.8% vs 60.9%** on medium-difficulty queries. Key line: *"Show too many tools and the model struggles to choose. Show too few and the correct tool may not appear."* It recommends **query-dependent K**, not a fixed number (e.g., K ranged ~1.4–7.4). https://arxiv.org/html/2605.24660v2
- "Less is More" (Paramanayakam et al., **arXiv:2411.15399**, 2024): with 46 tools the model picked wrong; reducing to 19 fixed it; up to ~70% lower execution time via similarity-based filtering. https://arxiv.org/pdf/2411.15399

So 138 tools is squarely in "retrieval helps a lot" territory.

## 3. Semantic vs. keyword: semantic (ideally hybrid) wins on retrieval accuracy — and retrieval accuracy is the whole ballgame.

The academic "tool-RAG" line is built on **semantic/embedding retrieval**, and the head-to-head industry benchmarks show pure keyword/regex underperforming:

- **RAG-MCP** (arXiv:2505.03275, 2025-05-06): uses **semantic retrieval** over MCP descriptions; >50% prompt-token reduction and **more than triples** selection accuracy (**43.13% vs 13.62%** baseline). https://arxiv.org/abs/2505.03275
- **Toolshed** (arXiv:2410.14594; ICAART 2025): "RAG-Tool Fusion" knowledge base; **+46–56%** absolute Recall@5 improvements on ToolE/Seal-Tools. https://www.scitepress.org/Papers/2025/133030/133030.pdf
- **ScaleMCP** (arXiv:2505.06416, 2025-05-09): benchmarks **5 embedding models × 5 retriever types** over 5,000 MCP servers; its whole premise is embedding-based retrieval, plus a "Tool Document Weighted Average" trick to weight the important parts of each tool doc when embedding. (I couldn't extract the single best retriever from the abstract — flag as not fully verified without the PDF.) https://arxiv.org/abs/2505.06416
- **Industry head-to-head (this is the load-bearing comparison):** Stacklok's MCP Optimizer (**hybrid semantic + BM25**) reports **94% end-to-end / 98% retrieval** accuracy vs Anthropic Tool Search Tool's **34% / 48%** on a large catalog (~2,792 tools). Independently, **Arcade** reported Anthropic Tool Search at **56% (regex) / 64% (BM25)** retrieval across 4,027 tools. Treat the *exact* Stacklok numbers with mild skepticism (vendor-published, favorable framing, large catalog), but the **direction is corroborated by two independent parties and by the academic papers**: hybrid/semantic > pure regex/BM25 on retrieval. https://stacklok.com/blog/stackloks-mcp-optimizer-vs-anthropics-tool-search-tool-a-head-to-head-comparison/ ; https://blog.arcade.dev/anthropic-tool-search-claude-mcp-runtime

Why this matters: if retrieval doesn't surface the right tool, the model never gets a chance to call it. That's the failure mode behind Anthropic's lower scores, and it's the strongest argument for using your existing embeddings stack rather than a bare keyword `find_tools`.

**Tradeoffs / honest caveats:**
- Semantic search needs an embedding model + index. For most self-hosted servers that's the main cost — **but you already ship an embeddings stack**, so your marginal cost is just indexing ~138 tool docs (trivial; even brute-force cosine over 138 vectors is instant — you don't strictly need FAISS at this scale).
- Pure semantic can have "less complete coverage" and does worse on complex multi-tool tasks (Speakeasy: 26,300 vs 5,700 tokens on a complex 400-tool task for semantic vs progressive). The mitigation is **hybrid (semantic + BM25/keyword)** — which is exactly what the top-performing systems (Stacklok) and SEP-1821's flexible design allow.
- Keep your **domain filter** as a structured pre-filter (cheap, deterministic, high-precision), then semantic-rank within/across domains. Your existing "narrow to a named domain" registry is an asset here, not something to throw away. Return top-k ≈ 5 (matches Anthropic's 3–5 and the chance-corrected paper's adaptive K).

## 4. Is tool-RAG SOTA, or overkill for ~138 tools?

- **The pattern (server-side discovery + retrieval-narrowed tool exposure) is SOTA and is being standardized** (SEP-1821), shipped by OpenAI (MCPSearch) and Anthropic (Tool Search Tool), and validated by 4+ academic papers. So the *approach* is right.
- **Heavyweight tool-RAG frameworks** (auto-syncing CRUD tool stores like ScaleMCP, multi-stage query rewriting + self-reflection + re-ranking like Toolshed) are designed for **thousands–to–tens-of-thousands** of tools. At 138, that machinery is **overkill** and adds latency/complexity for little gain.
- **The sweet spot for you:** a single server-side `find_tools(query, domain?)` meta-tool that (a) optionally pre-filters by your existing domain registry, (b) ranks with **hybrid semantic+BM25** over name/description/arg-names using the embeddings you already have, (c) returns top ~5 tool schemas, after which the agent calls the real tool by name. Keep your ~12 core tools always-loaded (non-deferred), defer the ~138 specialized ones. This mirrors Anthropic's "keep 3–5 frequent tools non-deferred" guidance and the spec's filtering capability.

**Things to flag as date/version-dependent or uncertain:**
- SEP-1821 is a **draft** (as of 2025-11-17); the `tools/list` `query` field is not yet ratified MCP. Your meta-tool is the pragmatic bridge until/if it lands, and is forward-compatible with it.
- Anthropic Tool Search Tool variant IDs are dated (`*_20251119`) and **beta**; model-gated. Don't depend on it for non-Claude clients.
- The Stacklok 34% vs 94% figures are vendor-published; the *gap direction* is corroborated, the *magnitude* is not independently confirmed at your scale.
- I could not extract ScaleMCP's single best retriever or RAG-MCP's exact encoder from the abstracts (PDFs needed) — treat those specifics as unverified.

---

### Key sources (with dates)
- Anthropic Tool Search Tool docs (variants dated 2025-11-19; beta): https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool
- Anthropic, "Advanced tool use," 2025-11-24: https://www.anthropic.com/engineering/advanced-tool-use
- MCP SEP-1821 Dynamic Tool Discovery (draft, 2025-11-17): https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1821
- OpenAI Codex MCPSearch / lazy loading (2025–2026): https://github.com/openai/codex/issues/9266 ; https://github.com/openai/codex/issues/2335
- Speakeasy, progressive vs semantic discovery (~100x token reduction): https://www.speakeasy.com/blog/100x-token-reduction-dynamic-toolsets
- RAG-MCP, arXiv:2505.03275 (2025-05-06): https://arxiv.org/abs/2505.03275
- ScaleMCP, arXiv:2505.06416 (2025-05-09): https://arxiv.org/abs/2505.06416
- Toolshed, arXiv:2410.14594 / ICAART 2025: https://www.scitepress.org/Papers/2025/133030/133030.pdf
- "How Many Tools Should an LLM Agent See?", arXiv:2605.24660 (2026-06-07): https://arxiv.org/html/2605.24660v2
- "Less is More," arXiv:2411.15399 (2024): https://arxiv.org/pdf/2411.15399
- Stacklok vs Anthropic head-to-head (vendor, treat magnitude cautiously): https://stacklok.com/blog/stackloks-mcp-optimizer-vs-anthropics-tool-search-tool-a-head-to-head-comparison/
- Arcade independent retrieval numbers: https://blog.arcade.dev/anthropic-tool-search-claude-mcp-runtime


### [code-execution-tools-as-code]

I have enough from authoritative, dated sources to answer decisively. Here is my finding for the parent agent.

---

## ANGLE FINDING: "Code execution / code mode" as an alternative to a discovery meta-tool

### What it is (mechanism)

The trend has **two distinct variants**, and the distinction is decisive for our client-agnostic, self-hosted LibreOffice case:

**1. Anthropic "Code execution with MCP" (the client-side pattern)**
- Published **Nov 4, 2025**, by Adam Jones & Conor Kelly. (https://www.anthropic.com/engineering/code-execution-with-mcp)
- Mechanism: instead of loading 100+ tool defs into context, the MCP servers' tools are presented to the agent as a **filesystem of TypeScript modules** (e.g. `servers/google-drive/getDocument.ts`). The agent **writes code** that imports and chains only the tools it needs; intermediate results are filtered/transformed *in the execution environment* and never round-tripped through the model.
- Claimed savings: **~150,000 → ~2,000 tokens (98.7%)** on a Google-Drive-to-Salesforce example.
- Status: explicitly an **architectural pattern, not a product**. Anthropic provides *no reference implementation*. Simon Willison (same day, https://simonwillison.net/2025/Nov/4/code-execution-with-mcp/) confirms: "Anthropic outline the proposal... but provide no code to execute on it!" — "Not ready for general use," implementation "remains theoretical." He likes the idea ("looks very solid") but flags it's a proposal.
- **Requirements (the catch): a secure code sandbox + filesystem on the CLIENT/HARNESS side.** Anthropic itself warns it "adds operational overhead and security considerations that direct tool calls avoid." Willison: "Requires special support — agents need filesystem access... and code execution capability."
- **Client-agnostic? NO.** This variant lives in the agent's harness. It does **not** work for a generic MCP client (Codex/Cursor/ChatGPT) unless that client ships a code-execution runtime. It is *not* something our server can unilaterally provide.

**2. Cloudflare "Code Mode" (server-side `search()`/`execute()` — the relevant one for us)**
- Original "Code Mode: the better way to use MCP" — **Sept 26, 2025** (https://blog.cloudflare.com/code-mode/). Core argument: "LLMs have seen a lot of code. They have not seen a lot of 'tool calls.'" Converts MCP tool schemas into a TypeScript API the model writes against; runs in a **V8 isolate** (Worker Loader API).
- Productized as the **Code Mode MCP server** — "give agents an entire API in 1,000 tokens," **Feb 20, 2026** (https://blog.cloudflare.com/code-mode-mcp/). The server exposes **only two tools: `search()` and `execute()`**. `search()` lets the agent query a typed representation of the (OpenAPI) spec to find endpoints without loading them; `execute()` runs agent-written JS that chains calls. Result: **~2,500 tools / ~1.17M tokens → ~1,000 tokens (~99.9% reduction)**. Code runs **server-side** in a Dynamic Worker V8 isolate (no filesystem, no env vars exposed).
- **Client-agnostic? YES** for this variant. InfoQ (Apr 16, 2026, https://www.infoq.com/news/2026/04/cloudflare-code-mode-mcp-server/) and the Feb 2026 post indicate the sandbox/execution is **entirely server-side**, so "no special agent-side modifications are required — agents use standard MCP tool calling conventions." It looks like a normal 2-tool MCP server to any compliant client. (InfoQ hedges that it doesn't *explicitly* certify universal client support, but the 2-tool design implies it.)
- Cloudflare **open-sourced a Code Mode SDK** in the Cloudflare Agents SDK so the pattern can be reused in your own servers — **but the production runtime leans on Cloudflare Workers / V8 isolates**; that's the part we'd have to replace ourselves. Worker Loader was beta as of the Sept 2025 post.

### Maturity (dated)
- Anthropic pattern: **proposal-stage, no official code** (Nov 2025). Ecosystem implementations have since appeared, but Anthropic shipped none.
- Cloudflare: **shipped** — hosted server live and SDK open-sourced (Feb–Apr 2026), though tied to Cloudflare's isolate infra for the turnkey version.

### Verdict for our Mode 3 (self-hosted LibreOffice MCP, client-agnostic)

**Recommendation: do NOT adopt code-execution as the primary client-agnostic mechanism; keep the server-side `find_tools(query/domain)` discovery meta-tool as Mode 3.** Reasoning:

1. **The genuinely client-agnostic property comes from "few tools at the MCP boundary + on-demand discovery," not from code execution per se.** Cloudflare's `search()`/`execute()` and our `find_tools()` are the *same architectural idea* (progressive tool disclosure behind a tiny fixed tool surface). The token win is mostly from *not loading 138 schemas*, which the discovery meta-tool already achieves.

2. **The Anthropic-style "tools as code" variant is the one we cannot use client-agnostically** — it requires a sandbox/filesystem in the *client harness*, which Codex/Cursor/ChatGPT/generic clients do not provide. Adopting it would re-introduce exactly the client-specific dependency we're trying to avoid (the same reason Anthropic's client-side Tool Search Tool is off the table for us).

3. **`execute()`-style server-side code is strictly heavier than `find_tools()`** for our situation: it means embedding and securing a code interpreter inside a *LibreOffice extension process* (untrusted JS/Python sandboxing, resource limits, escaping the document model) — the operational/security overhead Anthropic itself flags — for a catalog of only ~150 tools. The discovery meta-tool needs none of that and our server already lets the agent call real tools by name after discovery.

4. **Where code-mode genuinely beats a discovery tool is multi-call chaining** (filtering/looping over large intermediate results without round-tripping). That matters at Cloudflare's 2,500-tool / large-payload scale. For ~150 LibreOffice doc-manipulation tools it's a marginal benefit that doesn't justify shipping a sandbox.

**Net:** treat code-execution/code-mode as a *future optimization*, not the Mode 3 mechanism. The state-of-the-art, client-agnostic move for a self-hosted server is precisely the small-fixed-surface + server-side progressive disclosure that your `find_tools(query/domain)` meta-tool implements; Cloudflare's `search()`/`execute()` validates that shape. Only consider adding server-side `execute()` later if/when chaining over large intermediate payloads becomes a real bottleneck — and only with a properly sandboxed runtime, which is a significant build inside a LibreOffice extension.

### Caveats / uncertainty
- "Client-agnostic" for Cloudflare's server-side model is **strongly implied but not formally certified** in the sources (InfoQ explicitly hedges).
- Token-savings figures are **vendor-reported** on favorable examples (150k→2k; 1.17M→1k); real savings depend on schema sizes and call patterns and will be smaller for ~150 tools.
- The field is **fast-moving and date-sensitive**: Anthropic's pattern was code-less in Nov 2025; Cloudflare productized Feb–Apr 2026. Anthropic's *client-side* Tool Search Tool (separate from this) is the officially-shipped Anthropic answer but is not client-agnostic — which is why your Mode 3 exists.

**Sources:** [Anthropic, Code execution with MCP, 2025-11-04](https://www.anthropic.com/engineering/code-execution-with-mcp) · [Simon Willison, 2025-11-04](https://simonwillison.net/2025/Nov/4/code-execution-with-mcp/) · [Cloudflare, Code Mode, 2025-09-26](https://blog.cloudflare.com/code-mode/) · [Cloudflare, Code Mode MCP / 1,000 tokens, 2026-02-20](https://blog.cloudflare.com/code-mode-mcp/) · [InfoQ, Cloudflare Code Mode MCP Server, 2026-04-16](https://www.infoq.com/news/2026/04/cloudflare-code-mode-mcp-server/)


### [consensus-and-portability]

I have everything I need. The research is comprehensive and converges cleanly. Let me synthesize the final answer.

---

# State of the art (late 2025 / early 2026): server-side tool discovery for a client-agnostic MCP server

## Bottom line up front

For your exact situation — a self-hosted MCP server with ~150 tools that must serve clients that may NOT have provider-native tool search (Codex, Cursor, ChatGPT, generic MCP clients) — **a server-side discovery/meta-tool is the correct and recommended call.** It is the only approach that is portable across all MCP clients today, and it is precisely the pattern that the MCP ecosystem's own tooling (FastMCP, Speakeasy, Stainless-style guidance) and the draft MCP spec (SEP-1821) have converged on. The provider-native features (Anthropic Tool Search Tool, OpenAI tool search) are real and excellent, but they are **API/client-side**, opt-in by whoever makes the model call, and you (the server) cannot rely on them being present. Field confidence in "use a server-side discovery layer for portability" is **high**; confidence in *which specific server-side shape wins long-term* (meta-tool vs. native `tools/list` filtering) is **medium** and date-dependent.

---

## (b) Provider portability — the decisive facts

**Anthropic Tool Search Tool — confirmed API/client-side, not server-side-MCP.**
- Launched as part of "advanced tool use" on **2025-11-20**; beta header `advanced-tool-use-2025-11-20`. It works by you passing tools with `defer_loading: true` plus a `tool_search_tool_regex_20251119` / `tool_search_tool_bm25_20251119` tool in the **`tools` array of the Messages API request**. The search runs inside the inference request, and discovered tools are expanded into context. ([anthropic.com/engineering/advanced-tool-use](https://www.anthropic.com/engineering/advanced-tool-use), 2025-11-20; [platform.claude.com tool-search-tool docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool))
- Anthropic's docs literally call it a **"server-side tool"** — but "server-side" there means *Anthropic's API server*, not your MCP server. The whole mechanism lives in the Anthropic Messages API and requires the caller to set `defer_loading` and include the search tool. For MCP, deferral is configured via `mcp_toolset` / `default_config` in the **MCP connector** with the `mcp-client-2025-11-20` header — again, on the API caller's side. ([platform.claude.com tool-search-tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool))
- Model-gated: Sonnet 4.0+, Opus 4.0+, Haiku 4.5+ (and newer); not universal. A separate roll-out brought "MCP Tool Search" into Claude Code, announced ~**2026-01-14**. ([atcyrus.com guide](https://www.atcyrus.com/stories/mcp-tool-search-claude-code-context-pollution-guide); search-surfaced announcement dated 2026-01-14)
- Key implication for you: **if the client isn't using Anthropic's API with these headers/models, none of this exists.** You cannot depend on it.

**OpenAI — has an equivalent, also API/client-side, also model-gated.**
- OpenAI shipped **tool search + `defer_loading`** in the Responses API / Agents SDK. You mark tools (including hosted MCP servers, via `defer_loading: true` on the MCP tool/`tool_config`) and the model loads only what it needs. **Only `gpt-5.4` and later** support `tool_search`. ([developers.openai.com tool-search guide](https://developers.openai.com/api/docs/guides/tools-tool-search); [OpenAI Agents SDK tools](https://openai.github.io/openai-agents-python/tools/))
- Important nuance that matters for you: OpenAI defines **two modes** — *hosted* tool search (OpenAI's servers do the lookup) and **client-executed tool search** (the model emits a `tool_search_call`, **your application performs the lookup** and returns `tool_search_output`). The client-executed mode is essentially an officially-blessed hook for your own/server-side search. After discovery, in both modes the model calls the real tool by name — exactly your intended flow. ([developers.openai.com tool-search guide](https://developers.openai.com/api/docs/guides/tools-tool-search))

**Google Gemini — no equivalent yet (gap).**
- As of early 2026, the Gemini API does **not** support `defer_loading` / `tool_search`; there's an open parity feature request (`googleapis/python-genai#2185`) explicitly asking for parity with Anthropic and OpenAI. Gemini can do crude "load tools based on query/context," but no native deferred-tool-search primitive. ([github.com/googleapis/python-genai#2185](https://github.com/googleapis/python-genai/issues/2185))

**Generic / third-party MCP clients (Cursor, ChatGPT-as-MCP-client, custom clients) — no native deferred tool loading.**
- These features are properties of the *model API*, not the MCP protocol, so a generic MCP client gets the full tool list unless something narrows it. There is no portable, client-side standard you can assume. ([startdebugging.net, 2026-05](https://startdebugging.net/2026/05/how-to-reduce-the-number-of-mcp-tools-claude-loads/); search results above show no generic-client support)

**Is a client-agnostic *standard* emerging? Yes — at the protocol level, but still draft.**
- **SEP-1821 "Dynamic Tool Discovery"** proposes adding an optional `query` param to `tools/list` plus a `ServerCapabilities.tools.filtering` flag, so a server can do text/semantic/fuzzy filtering natively in MCP. Status: **Draft, Standards Track, "seeking sponsor," as of 2025-11-17** — i.e., not yet adopted. ([github.com/modelcontextprotocol/modelcontextprotocol#1821](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1821))
- Until that lands and clients implement it, the **portable mechanism that works on *every* MCP client today is the server-side meta-tool**, because it only relies on the universally-supported `tools/list` + `tools/call` primitives.

---

## (a) What the authoritative guides recommend as the default

The independent MCP-ecosystem sources converge on **server-side meta-tools** as the client-agnostic default for huge catalogs:

- **FastMCP "Tool Search" transform (v3.1.0):** Replaces the full catalog with two synthetic tools — `search_tools` (returns full definitions of matches) and `call_tool` (executes a discovered tool by name) — built purely on standard `list_tools()`/`call_tool()`. Offers `RegexSearchTransform` (zero index) and `BM25SearchTransform` (relevance ranking), default 5 results, `always_visible` to pin hot tools, and respects auth/visibility middleware so filtered tools never appear. This is exactly your proposed `find_tools` design. ([gofastmcp.com/servers/transforms/tool-search](https://gofastmcp.com/servers/transforms/tool-search))
- **Speakeasy "100x token reduction with dynamic toolsets":** Recommends **server-side meta-tools** as the core solution, comparing *progressive discovery* (3 meta-tools: `list_tools`/`describe_tools`/`execute_tool`) vs *semantic search* (2 meta-tools: `find_tools`/`execute_tool`). For very large catalogs they favor semantic search because initial token cost stays flat (~1,300 tokens) regardless of catalog size. Both expose meta-tools rather than raw operations. ([speakeasy.com/blog/100x-token-reduction-dynamic-toolsets](https://www.speakeasy.com/blog/100x-token-reduction-dynamic-toolsets))
- **Anthropic itself blesses a custom/server-side search path:** the Tool Search docs include a **"Custom tool search implementation"** section — you return `tool_reference` blocks from your own tool using embeddings/semantic search. This shows even Anthropic expects sophisticated catalogs to plug in their own (often server-side) discovery logic rather than rely solely on the built-in regex/BM25. ([platform.claude.com tool-search-tool, "Custom tool search implementation"](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool))
- **Enterprise/gateway view (TrueFoundry, updated 2026-02-11):** For multi-tenant/enterprise scale, recommends putting discovery behind an **MCP Gateway** that does policy-aware, identity-scoped filtering — "discovery itself is a security boundary." This is a heavier variant of the same server-side-discovery idea; relevant if you later need per-client scoping, but likely more than a single self-hosted extension needs today. ([truefoundry.com/blog/mcp-tool-discovery-for-enterprise-ai-agents](https://www.truefoundry.com/blog/mcp-tool-discovery-for-enterprise-ai-agents))

"Merely exists" vs "recommended": provider-native tool search **exists and is recommended *when you control the model call*** (Anthropic/OpenAI). The **server-side meta-tool is the recommended default *when you must be client-agnostic*** — your case.

---

## The single most-recommended approach for your situation

**Ship a server-side discovery meta-tool, and lean on the domain registry you already have.** Concretely:

1. Keep your **~12 core tools always listed** (the FastMCP `always_visible` / Anthropic "keep 3–5 hot tools loaded" principle — yours is a bit larger, which is fine). ([gofastmcp tool-search](https://gofastmcp.com/servers/transforms/tool-search); [platform.claude.com tool-search-tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool))
2. Expose **one discovery tool — `find_tools(query, domain?)`** — that returns full schemas for matching specialized tools (your ~138 across ~30 domains). Because you already have a registry that narrows by named domain, support **both** a `domain` filter (cheap, deterministic, like progressive discovery) **and** a free-text `query` (BM25/embedding ranked, like semantic search). This hybrid is exactly what Speakeasy/FastMCP describe. The agent then calls the real tool by name, which your server already allows — no separate `execute_tool` indirection needed since real tools remain callable. ([speakeasy 100x](https://www.speakeasy.com/blog/100x-token-reduction-dynamic-toolsets); [gofastmcp tool-search](https://gofastmcp.com/servers/transforms/tool-search))
3. **Why this and not the alternatives:** it works on **every** MCP client (only needs `tools/list` + `tools/call`); it degrades gracefully — clients that DO have Anthropic/OpenAI tool search can still defer-load your already-small surface, so you compose with, rather than fight, the native features; and it positions you to adopt **SEP-1821 native `tools/list` filtering** with near-zero rework once it's standardized. ([SEP-1821](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1821))
4. **Don't rely on provider-native tool search as your primary mechanism** — it's API-side, model-gated (Sonnet/Opus 4.x+, GPT-5.4+, no Gemini), and absent on generic clients. Treat it as an optional accelerator the *client* may add, not a substitute for the server-side layer. ([anthropic advanced-tool-use](https://www.anthropic.com/engineering/advanced-tool-use); [openai tool-search](https://developers.openai.com/api/docs/guides/tools-tool-search); [python-genai#2185](https://github.com/googleapis/python-genai/issues/2185))

**Watch items (version/date-dependent):**
- **SEP-1821** is still *Draft / no sponsor* (2025-11-17). If it advances and clients implement `tools/list?query=`, that becomes the cleaner native path — design your `find_tools` so its logic can be re-exposed through filtered `tools/list` later. ([SEP-1821](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1821))
- One caveat on the meta-tool pattern: a couple of practitioner reports (e.g., Stacklok, Growth Method, late 2025/early 2026) note current tool-search implementations can be rough at very large catalogs — invest in good tool **names/descriptions/keywords and domain tagging**, since all search variants match on those fields. ([dev.to/stacklok comparison](https://dev.to/stacklok/stackloks-mcp-optimizer-vs-anthropics-tool-search-tool-a-head-to-head-comparison-2f32); [growthmethod.com/anthropic-tool-search](https://growthmethod.com/anthropic-tool-search/))

**Field confidence:** High that a **server-side discovery layer is the right client-agnostic choice today**; Medium on the long-run winner between "meta-tool" and "native `tools/list` filtering (SEP-1821)" — but both are server-side, so building the meta-tool now is low-regret.

Sources:
- https://www.anthropic.com/engineering/advanced-tool-use
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool
- https://developers.openai.com/api/docs/guides/tools-tool-search
- https://openai.github.io/openai-agents-python/tools/
- https://github.com/googleapis/python-genai/issues/2185
- https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1821
- https://gofastmcp.com/servers/transforms/tool-search
- https://www.speakeasy.com/blog/100x-token-reduction-dynamic-toolsets
- https://www.truefoundry.com/blog/mcp-tool-discovery-for-enterprise-ai-agents
- https://www.atcyrus.com/stories/mcp-tool-search-claude-code-context-pollution-guide
- https://startdebugging.net/2026/05/how-to-reduce-the-number-of-mcp-tools-claude-loads/
- https://dev.to/stacklok/stackloks-mcp-optimizer-vs-anthropics-tool-search-tool-a-head-to-head-comparison-2f32
- https://growthmethod.com/anthropic-tool-search/
