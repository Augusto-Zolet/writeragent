<!-- Branch: explore/mcp-direct-tools · Status: VERIFIED design analysis (multi-agent research) -->
<!-- Relates to: discussion #315, item 4. Raw investigation in mcp-direct-tool-exposure-appendix.md -->

# WriterAgent Design Analysis — Expose Specialized Tools Directly Over MCP + On-Demand Discovery

**Discussion #315, item 4** · Audience: Keith (maintainer) + contributor · Optimize for: correctness, concreteness
**Repo root:** `/Users/augustozolet/Documents/Projetos_Escritório/writeragent-explore-mcp/`
All `file:line` references are relative to `plugin/` unless otherwise noted.

---

## 1. Confirmed current architecture

Three independent narrowing mechanisms gate which tools a model sees, and they operate at different layers. Understanding that they are *separate* is the key to the whole design.

### 1.1 The MCP tier filter (list-time only)

The MCP server hides specialized tools from `tools/list` and **only** there:

- `mcp_protocol.py:442` (`_mcp_tools_list`):
  ```python
  schemas = self.tool_registry.get_schemas("mcp", doc=doc, exclude_tiers=frozenset({"specialized", "specialized_control"}))
  ```
- This hardcodes `exclude_tiers` and deliberately does **not** pass `active_domain`, and deliberately omits `"mcp"` from the exclusion set (compare `_DEFAULT_EXCLUDE_TIERS` at `tool.py:439`, which adds `"mcp"`) so that MCP-only tools stay visible.
- The list is **already document-dependent**: `_mcp_tools_list` resolves the active document (or the `X-Document-URL` header) on the VCL main thread, then `get_schemas("mcp", doc=...)` filters by doc type / UNO services. So the advertised set changes when the user switches Writer↔Calc↔Draw — but with `listChanged:false` (`mcp_protocol.py:424`) the server never tells the client, so clients cache the initial list. (See §6.)

The `initialize` handshake advertises `{"tools": {"listChanged": False}, "resources": {"listChanged": False}, "prompts": {"listChanged": False}}` (`mcp_protocol.py:424`), protocol version `MCP_PROTOCOL_VERSION = "2025-11-25"` (`mcp_protocol.py:42`), and echoes the client's `protocolVersion`. Sessions are a single module-global `_mcp_session_id` (`mcp_protocol.py:166`), minted post-initialize (`:407-408`), never enforced per-client.

### 1.2 The delegate + sub-agent gateway and its LLM dependency

The chat-facing path to specialized tools is the `delegate_to_specialized_*_toolset` gateway (core tier, advertised). It does **not** call a tool; it spins up a second LLM agent:

- `DelegateToSpecializedBase.execute()` — `doc/specialized_base.py:107-291` — assembles a domain-specific instruction block + hints + examples and hands them to `build_toolcalling_agent` (`chatbot/smol_agent.py:299-309`), which builds a smolagents `ToolCallingAgent`.
- That sub-agent runs a full ReAct Action/Observation loop (system-prompt template `contrib/smolagents/toolcalling_agent_prompts.py:68-96`) and terminates only by calling the `specialized_workflow_finished` finish tool (`writer/specialized_base.py:278-296`, tier `specialized_control`, `is_final_answer_tool=True`).

**LLM dependency (load-bearing):** every delegated specialized request costs a *second LLM invocation* — the sub-agent. The tier/gateway design trades up-front token cost for that extra round-trip. Any option that exposes tools directly removes the sub-agent and therefore removes both the token cost *and* the scaffolding the sub-agent injects (§5).

### 1.3 The registry / `active_domain` narrowing (structural)

When the delegate runs, it narrows the tool set the sub-agent sees:

- `specialized_base.py:181`: `registry.get_tools(..., active_domain=domain, ...)`.
- `ToolRegistry.get_tools` `active_domain` branch — `tool.py:584-606` — whitelists the domain's specialized tools + the finish tool + only the core tools named in each domain's `required_core_tools` (e.g. base Writer `{get_document_content, get_document_tree}` at `writer/specialized_base.py:47`; footnotes/fields/styles add `search_in_document`).
- `_is_specialized_domain_tool` — `tool.py:414-435` — handles composite domains (`python:writer`) and `specialized_cross_cutting`.
- `get_schemas` (`tool.py:624-639`) forwards `active_domain` + `**kwargs` into `get_tools`, mapping through `to_mcp_schema`.

This is the exact machinery Options B and C reuse.

---

## 2. Quantified bloat

Counts derived by AST inheritance resolution (`uno` isn't importable outside LibreOffice). "Specialized" = effective `tier == "specialized"`. The 35 mock tools in `writer/specialized/mock_domains.py` are inside a `'''...'''` block (inert) and excluded; `web_research`/`visit_webpage` are core-tier; `ListOpenDocuments` is `tier="mcp"`.

### 2.1 Real tool counts: **138 concrete specialized tools across 30 active domains**

| App | Tools | Domains | Notable domains (count) |
|---|---|---|---|
| **Writer** | 82 | 14 | tracking (11), images (9), bookmarks (7), page (7), footnotes (6), forms (6), shapes (6), structural (6), fields (5), indexes (5), styles (5), comments (4), textframes (3), embedded (2) + chatbot-hosted brainstorming (2) & writing_plan (2) |
| **Calc** | 35 | 10 | sheets (9), analysis (5), charts (5), comments (3), conditional_formatting (3), pivot_tables (3), errors (2), python (2), search (2), ranges (1) |
| **Draw/Impress** | 13 | 5 | slide_transitions (4), slide_masters (3), speaker_notes (2), headers_footers (2), math (1) |
| **Shared** (`document_research`) | 5 | 1 | list_nearby_files, grep_nearby_files, delegate_read_document, search_embeddings, search_nearby_files |

`web_research` has base classes but **0 leaf tools** (served by the core-tier `web_research` tool). The `delegate_to_specialized_*` gateways are core-tier (not counted).

### 2.2 Token cost: flat exposure vs core list

Schema token sizes (chars/4) range ~34 (thin wrappers like `upsert_chart`, whose schema is built at runtime so the static literal undercounts) to ~356 (`create_pivot_table`, `generate_image`, `create_form_control`, `set_slide_transition`). Mean ≈ **190 tok/tool**.

| Exposure | Tokens | Notes |
|---|---|---|
| **All 138 specialized schemas (flat)** | **≈ 16,734** | writer ≈9,072, calc ≈4,943, draw ≈1,646, document_research ≈664, chatbot-hosted writer ≈408 |
| **Full union of 17 core tools** | ≈ 2,390 | |
| **Single-app core slice (~12 tools)** | ~1,500–2,000 | 5 app tools + `humanize` + `upsert_memory` + delegate gateway + web/doc-research gateway |
| **One domain's schemas loaded on demand** | ~400–2,500 | 2–11 tools per domain |

**Bloat ratio: flat exposure (~16.7k tok) is ≈ 7× the core list (~2.4k tok)**, and ~70× a single thin tool. This is precisely what the tier + `exclude_tiers` + gateway design avoids today.

> **Context for §6:** Anthropic's own framing puts the pain threshold at "30–50 available tools" before selection accuracy degrades; a flat 138-tool list is well past that. ([Anthropic — Advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use))

Key files: registry/tiers `framework/tool.py:243,529,604`; gateway descriptions `framework/constants.py:362,443,450`; per-app bases `writer/specialized_base.py:31`, `calc/base.py:25`, `draw/base.py:25`.

---

## 3. THE KEY FINDING

**Question:** Is an unadvertised (specialized) tool callable directly over MCP today?

**Verified answer: YES.** A `tier="specialized"` (or `specialized_control`) tool *can* be invoked directly over `tools/call` today. It is only *hidden* from `tools/list`; it is **not protected** at call time. This was confirmed against the live code by the adversarial verdict [unadvertised-callable] (**SUPPORTED**).

Decisive evidence chain:

1. Tier exclusion exists **only** in `tools/list` — `mcp_protocol.py:442`.
2. `tools/call` resolves the tool by raw name with no tier check — `mcp_protocol.py:459`:
   ```python
   tool = self.tool_registry.get(tool_name)
   ```
3. `ToolRegistry.get` is a bare dict lookup — `tool.py:646-648`:
   ```python
   def get(self, name: str) -> ToolBase | None:
       return self._tools.get(name)
   ```
4. The FSM passes the name straight to `ExecuteToolEffect` (`mcp_state.py:122`); the only rejection in the state path is an empty `tool_name` (`mcp_state.py:100-102`).
5. Execution (`tool.py:690-801`) re-looks-up via `self._tools.get(tool_name)` (`:705`) and its only gates are **non-tier**: doc-type/uno_services compatibility (`:710-729`, raises `"does not support the current document"`), schema kwarg restriction (`:733-736`), `validate()` (`:746-748`), and `read_only_target` (`:750-756`, which is `False` for all MCP calls — `ToolContext(... caller="mcp")` at `mcp_protocol.py:619,676`). **`tier` is read nowhere in `execute()`.**

**What this unlocks:** Options B and C below do not require any change to the *call* path — the server already serves unadvertised tools by name. The entire design space is about **what to advertise and how the client learns the names**, not about unlocking execution.

**Two call-time caveats the verdict flagged (do not glaze over these):**
- **Document-type mismatch hard-blocks** — a specialized tool declaring `uno_services`/`doc_types` incompatible with the open doc is rejected at `tool.py:729`. Only *universal* (no `uno_services`/`doc_types`) or doc-compatible specialized tools execute. A naive flat exposure will surface tools that 429/error against the wrong document type.
- **"Callable" ≠ "behaves correctly"** — execute() bodies depend only on `ctx.doc`, not agent state, so they *run*; but several domains' operative knowledge lives only in the delegate scaffolding (§5). This is tool-dependent.

**Spec posture (from verdict [unadvertised-callable], NUANCED):** The MCP spec is *silent* on whether a `tools/call` target must have appeared in `tools/list`. "Unknown tool" (`-32602`) means *not in the registry*, not *not advertised*. So serving an unadvertised-but-registered tool is **not a spec violation** — but it is **not a blessed pattern** either, and the spec separately says servers **MUST** implement access controls. Today, tier exclusion is a *visibility* filter, **not** an *access* control. That gap is what makes this possible; it is also a latent security note (§8).

---

## 4. Design options

All three options are gated by a new `mcp.tool_exposure_mode` config flag (§7). The narrowing machinery (`tool.py:584-606` + `:414-435`, entered via `get_schemas` `tool.py:624-639`) is reused identically across B and C.

### Option A — `direct_flat`: advertise every specialized tool

**Touch-point (single line): `mcp_protocol.py:442`.** Flip `exclude_tiers` based on mode:
```python
if mode == "direct_flat":
    exclude_tiers = frozenset({"specialized_control"})   # expose "specialized", keep control tools hidden
else:
    exclude_tiers = frozenset({"specialized", "specialized_control"})
schemas = self.tool_registry.get_schemas("mcp", doc=doc, exclude_tiers=exclude_tiers)
```
Keep `specialized_control` excluded — it holds `specialized_workflow_finished` (`writer/specialized_base.py:283`) and similar control tools that only make sense inside an active delegated domain.

- **Mechanics:** dropping `"specialized"` lets `get_tools` keep those tools through `_tier_excluded` (`tool.py:608-614`); `to_mcp_schema` emits all of them. No `tool.py` change. `to_mcp_schema` (`tool.py:104-144`) injects a `document_url` property; specialized tools carry no other injection, so flat exposure is clean.
- **Context-bloat profile:** worst — **~16.7k tokens** per session (or per-app slice ~1.6–9k since the list is already doc-filtered). Past Anthropic's 30–50-tool accuracy cliff.
- **Tradeoffs:** simplest possible change; immediately useful for power-users who know the names. But pays full token cost up front, surfaces doc-incompatible tools that hard-block (`tool.py:729`), and loses *all* scaffolding (§5). No discovery affordance.

### Option B — `direct_discovery`: small list + a `find_tools` MCP tool

Keep `tools/list` small (same `exclude_tiers` as `delegate`) and add one discovery tool the model calls to pull domain schemas on demand. This mirrors the dominant industry "meta-tool / progressive disclosure" pattern (fastmcp-gateway's `discover_tools`/`get_tool_schema`; MCP SEP #1888's `searchTools`; Synaptic Labs' discovery+execution pair).

**Preferred shape (B-preferred): a real registered tool.** New `plugin/mcp/find_tools_tool.py`:
- `class FindToolsTool(ToolBase)`, `tier = "mcp"` (appears in MCP lists, not chat — survives the `tools/list` filter but is hidden from the sub-agent), `name = "find_tools"`, params `{query: string (optional), domain: string (optional)}`, `doc_types=None`/`uno_services=None` (universal), read-only (no mutation gate).
- `execute(ctx, query=None, domain=None)` calls back through `ctx.services.tools`:
  ```python
  reg = ctx.services.tools
  schemas = reg.get_schemas(
      "mcp", doc=ctx.doc, doc_type=ctx.doc_type,
      active_domain=domain,                 # reuses tool.py:584-606 narrowing
      exclude_tiers=frozenset(),            # allow specialized through
  ) if domain else reg.get_schemas("mcp", doc=ctx.doc, doc_type=ctx.doc_type,
                                   exclude_tiers=frozenset({"specialized_control"}))
  if query:
      q = query.lower()
      schemas = [s for s in schemas if q in s["name"].lower() or q in s.get("description","").lower()]
  return {"status": "ok", "tools": schemas}
  ```
- **Key reuse:** `active_domain=domain` triggers exactly `_is_specialized_domain_tool` narrowing, so `find_tools(domain="footnotes")` returns that domain's schemas **plus** its `required_core_tools` — which is what carries the two-step discovery tools (e.g. `search_in_document`) the caller needs (§5). Goes through the normal execute path; `ToolContext` already carries `services` (`tool.py:194`), so no protocol plumbing beyond the config gate.
- **Visibility gate:** since `find_tools` is auto-discovered it would otherwise always appear. In `_mcp_tools_list`, drop it from the schema list unless `mode == "direct_discovery"`.

**B-alt: a protocol-level `find_tools` JSON-RPC method** — dispatch dict `mcp_protocol.py:531` + branch `:543`, new `_mcp_find_tools` resolving the doc like `_mcp_tools_list` (`:433-440`). **Downside:** a custom JSON-RPC method is *not discoverable* by standard MCP clients — they won't know to call it. Use B-alt only if advertised some other way. **B-preferred is recommended.**

- **Context-bloat profile:** best — small list (~1.5–2k) + ~150 tok per fetched tool, only for domains actually used. Matches the ~7× token reduction the tier design already targets, while restoring direct callability.
- **Tradeoffs:** one new file + a visibility gate; no `tool.py` change. Most robust because it does **not** depend on the client honoring `list_changed` (§6). Caveat: the model still needs a reason to call `find_tools` — fold that into its description and into the gateway's domain catalog.

### Option C — single specialized-request tool

Expose **one** MCP tool that takes `domain` + `task` and runs the whole specialized request server-side — i.e. re-expose the existing delegate gateway over MCP.

- **Reuse:** `DelegateToSpecializedWriter` (`writer/specialized_base.py:51`) already *is* this tool for chat (`domain` + `task`); its `to_mcp_schema` special-base branch (`tool.py:127-143`) emits the full domain catalog in the `domain` property description via `format_specialized_domains_description` (`constants.py:671`). Currently excluded because its tier resolves to `specialized_control`.
- **Integration:** in `_mcp_tools_list` (`mcp_protocol.py:442`), for mode C build the small core set **plus** the delegate gateway — easiest `exclude_tiers=frozenset({"specialized"})` (keeps `specialized_control` so the gateway + finish tool show), or append the gateway by name.
- **Execution:** unchanged — `tools/call name="delegate_to_specialized_writer_toolset"` flows through the normal path; `requires_document_lock` is overridden on delegate tools (`tool.py:259-266`) so read-only domains skip the mutation gate.
- **Net new code:** only the `_mcp_tools_list` schema-assembly branch. No new tool class, no new dispatch method.
- **Context-bloat profile:** smallest advertised footprint (one self-documenting tool). **But** every call still pays the **second-LLM sub-agent cost** (§1.2) — C does not remove the delegate, it relocates it to MCP. It *preserves* all scaffolding automatically (that's its advantage over A/B), at the price of latency and an extra model call the MCP client cannot observe or stream.

**Comparison:**

| | A `direct_flat` | B `direct_discovery` | C single gateway |
|---|---|---|---|
| Advertised tokens | ~16.7k | ~1.5–2k + on-demand | ~1 tool |
| Direct tool call | yes | yes (after discovery) | no (delegated) |
| Sub-agent LLM cost | none | none | **every call** |
| Scaffolding preserved | no | partial (via find_tools) | **yes** |
| New code | 1 line | 1 file + gate | 1 branch |
| Client must honor `list_changed` | no | no | no |

---

## 5. The standalone-usability concern

When the sub-agent is bypassed, the delegate's injected scaffolding is lost. That scaffolding is substantial and, for several domains, **load-bearing**. All injected at `doc/specialized_base.py:107-291`.

**What the delegate injects (and the tools do NOT carry):**
- **Domain instruction preamble** — `specialized_base.py:259-263`, plus the entire ReAct contract from the system-prompt template (`toolcalling_agent_prompts.py:68-96`). None of this is in any tool description.
- **Hints (most domain-specific)** — `specialized_base.py:192-258`:
  - `charts_hint` (`:201-206`): "you MUST specify the data range explicitly" / "MUST specify both headers and rows" — the *required-ness* is taught only here.
  - `analysis_hint` (`:249-257`): the entire routing policy between `analyze_data` / `plot_data` / `calc_goal_seek` / `calc_solver` + the `data_range` convention — individual tool descriptions don't cross-reference siblings.
  - `python_hint` (`:258` → `constants.py:311-327`): venv import policy + pre-imported `np/sp/pd` knowledge.
  - `calc_ctx` / `shapes_canvas` / `document_research_hint` (`:196-242`): inject **live document context** (`[SPREADSHEET CONTEXT]`, shapes canvas, open-docs list) that tool params cannot supply.
- **Examples** — only two distinct blocks ever apply: `PYTHON_SPECIALIZED_EXAMPLES` (`smol_examples.py:165-182`) and an otherwise-generic block (`toolcalling_agent_prompts.py:39-63`).
- **`required_core_tools`** — structural: many domains assume the agent first calls a discovery tool (`search_in_document`, `get_sheet_summary`) to obtain indices/anchors before mutating. E.g. `footnotes_edit`/`footnotes_delete` require an `index` "from footnotes_list" (`writer/specialized/footnotes.py:199,237`).

**Self-sufficiency is uneven (verdict [unadvertised-callable], confirmed):**
- **Best case — footnotes:** `footnotes_insert` bakes the critical `insert_after_text` guidance into its own description + param docs (`footnotes.py:73-95`) and has a view-cursor fallback (`:134-145`). Works correctly standalone; the hint is redundant reinforcement.
- **Degraded/failing raw — charts, analysis, python, calc, shapes, document_research:** required-ness, tool routing, live context, and multi-step discovery live only in the scaffolding. A raw caller mis-calls frequently.

**Concrete mitigations:**
1. **Fold hints into descriptions.** Migrate the operative content of `charts_hint`, `analysis_hint`, `python_hint` into the respective tools' `description`/parameter docs (the footnotes domain is the proven template). This makes A and B viable for those domains and is independently good hygiene. *(Out-of-scope chip candidate — see §8.)*
2. **Make `find_tools` results carry the hint.** In Option B, have `find_tools(domain=...)` attach the domain's hint text as a `domain_guidance` field alongside the schemas (source it from the same hint-assembly functions used at `specialized_base.py:192-258`). This restores routing/required-ness guidance at discovery time without bloating every `tools/list`.
3. **Surface `required_core_tools` in discovery.** Because `find_tools(domain=...)` already returns them (via `active_domain` narrowing), document in the `find_tools` description that the returned set is a *workflow* (discover-then-mutate), not an unordered menu.
4. **Live-context gap is irreducible for A/B.** `[SPREADSHEET CONTEXT]`/shapes-canvas/open-docs cannot be folded into static schemas. For calc/shapes/document_research, **Option C is the only mode that preserves them** — a relevant reason to keep C available for those domains even if A/B is the default elsewhere.

---

## 6. Interplay with Anthropic Tool Search Tool & MCP dynamic lists

This section corrects a conflation flagged in two verdicts ([unadvertised-callable] NUANCED, [tool-search-mechanism] SUPPORTED-with-caveats).

### 6.1 Anthropic's Tool Search Tool is a CLIENT/API feature — not something the server implements

- The client provides *all* tool definitions to the API, marks the long tail `defer_loading: true`, and includes a `tool_search_tool_regex_20251119` or `tool_search_tool_bm25_20251119` tool. The API keeps deferred defs out of the system-prompt prefix and expands `tool_reference` blocks inline on discovery (preserving prompt caching). Up to 10,000 tools; ~85% token reduction; returns 3–5 matches per query. Beta header `advanced-tool-use-2025-11-20`. ([Tool search tool — Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool))
- Over MCP, deferral is configured **client-side** on an `mcp_toolset` via `default_config`/`configs` (`defer_loading: true`), beta header `mcp-client-2025-11-20` — the **server need not implement anything**. ([MCP connector — Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/mcp-connector))

**REFUTED framing to avoid:** WriterAgent's tier-hiding (`mcp_protocol.py:442`) and its `find_tools` (Option B) are the *server's own registry mechanism* — they are **not** Anthropic's Tool Search Tool, and `find_tools` results are not `tool_reference` expansions. Do not describe Option B as "implementing the Tool Search Tool." Caveat from [tool-search-mechanism]: the connector path requires a **public HTTPS** server (Streamable HTTP/SSE) — a `localhost:8765/mcp` server goes through the client-side helper path; deferral still happens client-side either way. The MCP connector is **not** ZDR-eligible.

**Implication for the server:** if a client *does* use Anthropic deferral, WriterAgent should advertise the **full useful set** so the client has definitions to defer. That makes Option A (`direct_flat`) the natural partner for Tool-Search-Tool clients, and Option B redundant *for those clients* (but B remains valuable for clients without deferral).

### 6.2 MCP dynamic lists (`list_changed`) — what the SERVER should do vs CLIENT reality

- **Spec (`2025-11-25`):** declare `tools.listChanged: true`, fire payload-less `notifications/tools/list_changed`; client SHOULD re-fetch `tools/list`. ([MCP spec — Tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools))
- **Client reality is uneven and historically buggy:**
  - **Claude Code** — partial; works **between turns**, not mid-turn; earlier versions never wired the handler ([#13646](https://github.com/anthropics/claude-code/issues/13646), [#31893](https://github.com/anthropics/claude-code/issues/31893)).
  - **Claude Desktop** — reported to **ignore** it in at least one version ([#50339](https://github.com/anthropics/claude-code/issues/50339)).
  - **ChatGPT Apps SDK** — no documentation confirming it honors the notification; refresh appears tied to reconnect. **Uncertain.**
  - Per-client status best checked against the `mcp-client-capabilities` registry ([PulseMCP](https://www.pulsemcp.com/posts/mcp-client-capabilities-gap)).

**Server recommendation:** Today the server already changes its advertised set on doc-type switch but says nothing (`listChanged:false`, `mcp_protocol.py:424`). Flipping to `listChanged:true` is *optionally* worthwhile (mechanism in §8), but **none of Options A/B/C depend on it**:
- A advertises everything (static).
- B keeps the list small and uses an in-band discovery *tool* (robust precisely because it doesn't rely on the client reacting to notifications — the dominant industry conclusion).
- C advertises one tool.

So: **the server should NOT make correctness depend on `list_changed`.** Treat it as a UX nicety for the doc-type-switch case, decoupled from this feature.

---

## 7. Recommended config-flag design + phased plan

### 7.1 `mcp.tool_exposure_mode`

**`plugin/mcp/module.yaml`** — add under the existing `config:` block (after `mcp_port`, before `cors_allow_private_origins`). Keys become `mcp.<field>` in `ConfigService` (`config_service.py:100-104`):
```yaml
  tool_exposure_mode:
    type: string
    default: delegate          # preserves today's behavior
    widget: select
    options: [delegate, direct_flat, direct_discovery]
    label: MCP Tool Exposure
    helper: How specialized tools are surfaced to MCP clients. delegate=hidden behind the delegate gateway (default); direct_flat=all specialized tools in tools/list; direct_discovery=small list plus a find_tools search tool.
    public: true
```
Read once near the top of `_mcp_tools_list` (`mcp_protocol.py:432-443`):
```python
mode = self.services.config.proxy_for("mcp").get("tool_exposure_mode") or "delegate"
```
`get` falls back to the manifest default (`config_service.py:171-173`), so a missing key yields `"delegate"`. (Option C, if pursued, can be a fourth enum value `direct_gateway` rather than a separate flag.)

**Default off (= `delegate`) is non-negotiable:** every other mode is an unenforced visibility change against a localhost server with no auth (§8), and direct exposure surfaces doc-incompatible tools that hard-block.

### 7.2 Phased implementation (smallest viable first, each behind the flag)

**Phase 0 — flag scaffolding.** Add `tool_exposure_mode` to `module.yaml` + read it in `_mcp_tools_list`. No behavior change (only `delegate` wired). Lowest risk; lands the gate everything else hides behind.

**Phase 1 — Option A (`direct_flat`), 1 line.** Implement the `exclude_tiers` flip at `mcp_protocol.py:442`. Smallest viable direct exposure. Validates the call-path (already ungated per §3) end-to-end and immediately serves Tool-Search-Tool clients (§6.1). Ship with a doc note that doc-incompatible specialized tools will error per `tool.py:729`.

**Phase 2 — fold load-bearing hints into descriptions** (charts, analysis, python). Independent of the flag; makes A usable for those domains and is good hygiene regardless. (See §5 mitigation 1.)

**Phase 3 — Option B (`direct_discovery`).** Add `plugin/mcp/find_tools_tool.py` (B-preferred) + the `_mcp_tools_list` visibility gate. Layer in mitigation 2 (`domain_guidance` in results). This is the recommended *steady-state* mode: best token profile, direct callability, no `list_changed` dependency.

**Phase 4 (optional) — Option C and/or `listChanged:true`.** Add the `_mcp_tools_list` gateway-assembly branch for C if live-context domains (calc/shapes/document_research) need their scaffolding preserved. Separately, flip `listChanged:true` + wire the SSE broadcast (§8) purely as a doc-type-switch UX improvement, never as a correctness dependency.

---

## 8. Open questions / risks

1. **Security: tier is visibility, not access control (CONFIRMED gap).** The MCP spec says servers MUST implement access controls (verdict [unadvertised-callable]); WriterAgent gates specialized tools only at list-time. Any specialized tool is *already* callable by name today over the no-auth localhost `/mcp`. Exposing names via A/B doesn't create the capability, but it advertises it. **Decision needed:** is "hidden but callable" acceptable, or should `tools/call` enforce tier/mode (reject specialized calls when `mode == "delegate"`)? Note `/mcp` has no auth — only `/debug` enforces a localhost-IP check (`mcp_protocol.py:340-345`).

2. **Doc-type mismatch UX.** Flat/discovery exposure surfaces tools that hard-block on the wrong document (`tool.py:729`). Should `find_tools`/`tools/list` pre-filter by `ctx.doc_type` (it already can via `get_schemas(doc=...)`), and should the error message be made more actionable?

3. **Live-context domains can't be made standalone.** calc/shapes/document_research need injected `[SPREADSHEET CONTEXT]`/canvas/open-docs (§5 mitigation 4). Open question: accept degraded behavior in A/B, or restrict those domains to Option C / the delegate?

4. **Two-step discovery is unenforced.** Tools requiring an `index` "from footnotes_list" (`footnotes.py:199,237`) don't enforce the prerequisite in their schema. A raw caller can skip it. Should discovery-then-mutate be encoded as a soft contract in descriptions, or validated at call time?

5. **`list_changed` is not worth depending on.** Client support is uneven (Claude Code between-turns-only, Claude Desktop reportedly ignores, ChatGPT undocumented — §6.2). Confirmed risk: do **not** build correctness on it. Mechanism if pursued for UX only: flip `mcp_protocol.py:424` to `True`, register open SSE `GET /mcp` streams (`mcp_protocol.py:214-226`) into a subscriber set, broadcast on doc-type change via the event bus (`McpModule` already subscribes to `config:changed`, `mcp/__init__.py:90-91`), comparing cheap name-sets (`get_tool_summaries`, `tool.py:641-644`) to avoid spurious notifications.

6. **Verdict-flagged doc uncertainties (carry forward, don't treat as settled):** Anthropic beta-header inconsistency between the engineering blog (`advanced-tool-use-2025-11-20`) and the docs-page samples; unverifiable model codenames ("Fable 5 / Mythos 5 / Mythos Preview") in live docs; Tool Search Tool is **beta, not GA**; MCP SEP #1888 (progressive disclosure) is a **draft proposal**, not adopted spec; Speakeasy token figures are illustrative, not independently verified.

7. **Single global session.** `_mcp_session_id` (`mcp_protocol.py:166`) is not per-client, so any `list_changed` broadcast is necessarily un-targeted — acceptable (a stale notification just triggers a harmless re-fetch) but worth noting if multi-client isolation ever matters.

---

*Files cited (absolute): `/Users/augustozolet/Documents/Projetos_Escritório/writeragent-explore-mcp/plugin/mcp/mcp_protocol.py`, `.../plugin/mcp/mcp_state.py`, `.../plugin/mcp/module.yaml`, `.../plugin/mcp/__init__.py`, `.../plugin/framework/tool.py`, `.../plugin/framework/constants.py`, `.../plugin/doc/specialized_base.py`, `.../plugin/writer/specialized_base.py`, `.../plugin/writer/specialized/footnotes.py`, `.../plugin/calc/base.py`, `.../plugin/draw/base.py`, `.../plugin/chatbot/smol_agent.py`, `.../plugin/contrib/smolagents/toolcalling_agent_prompts.py`, `.../plugin/chatbot/smol_examples.py`, `.../plugin/config_service.py`.*
