# Research appendix — MCP direct tool exposure

Raw output of the multi-agent investigation (branch `explore/mcp-direct-tools`). The consolidated, verified analysis lives in `mcp-direct-tool-exposure.md`; this file is the underlying evidence.


## Adversarial verdicts


### [unadvertised-callable]

I now have decisive evidence on both prongs of the claim. Let me do one more adversarial check: the claim says specialized tools are "excluded because tier=specialized is excluded" — I've confirmed that. But I should verify the claim's framing that this is about the WriterAgent server's *own* routing (it is, via `tools/call` → `registry.get`), and confirm there's no separate validation gate I missed. Let me also pull one more authoritative source on the MCP "Unknown tool" protocol error to test whether an unadvertised-but-registered tool would be rejected.

The evidence is conclusive. Here is my verdict.

---

## VERDICT

**Part 1 — MCP-routing claim (server invokes unadvertised-but-registered tool): SUPPORTED.**

**Part 2 — Tool Search Tool framing ("direct discovery: keep tools/list small, let find_tools reveal schemas, call specialized tools directly, no need to flip listChanged"): NUANCED / partly REFUTED.** The mechanism works on *this* server, but the claim conflates two unrelated discovery systems and misattributes the reason `listChanged` is "not needed."

---

## Decisive evidence — Part 1 (SUPPORTED)

The WriterAgent server filters tiers **only** at `tools/list`, and `tools/call` resolves purely by name with no tier gate. The full chain, quoted:

1. **Tier exclusion exists only in `tools/list`** — `plugin/mcp/mcp_protocol.py:442`:
```python
schemas = self.tool_registry.get_schemas("mcp", doc=doc, exclude_tiers=frozenset({"specialized", "specialized_control"}))
```

2. **`tools/call` resolves by raw name, no tier check** — `mcp_protocol.py:459-460`:
```python
tool = self.tool_registry.get(tool_name)
is_long_running = getattr(tool, "long_running", False) if tool else False
```

3. **`registry.get` is a bare dict lookup** — `plugin/framework/tool.py:646-648`:
```python
def get(self, name: str) -> ToolBase | None:
    """Get a tool by name, or None."""
    return self._tools.get(name)
```

4. **The state machine passes the name straight to execution — no tier branch** — `plugin/mcp/mcp_state.py:122` (confirmed I read the whole `next_state` REQUEST_RECEIVED → DOCUMENT_RESOLVED → ExecuteToolEffect path; the only rejection is empty `tool_name` at `mcp_state.py:100-102`):
```python
effects.append(ExecuteToolEffect(tool_name=typing.cast("str", state.tool_name), arguments=state.arguments, ...))
```

5. **Execution lookup is again a plain dict get, and the only gates are non-tier** — `tool.py:705` (`self._tools.get(tool_name)`), then the gates: document compatibility `tool.py:711-729` (raises `"does not support the current document"`), schema kwarg restriction `:733-736`, `validate()` `:746-748`, and `read_only_target` `:750-756` (which is `False` for MCP — `ToolContext(... caller="mcp")` at `mcp_protocol.py:619` and `:676` never sets it). **`tier` is read nowhere in `execute()`.**

So a client that knows the name (e.g. `footnotes_insert`) can invoke a `specialized`/`specialized_control` tool over `tools/call` even though it never appears in `tools/list`. The investigation context's [crux-routing] finding is accurate and reproduces against the live code.

**Caveat the claim glosses over (this is the load-bearing nuance):** "CAN be invoked" ≠ "will behave correctly." Two real call-time gates can still bite:
- **Document-type mismatch** — a specialized tool declaring `uno_services`/`doc_types` incompatible with the open doc is rejected at `tool.py:729`. Only *universal* or doc-compatible specialized tools execute.
- **Missing scaffolding** — per the [domain-scaffolding] finding, the execute() bodies run fine standalone (they depend only on `ctx.doc`, not agent state), but several domains (charts, analysis, python, calc, shapes, document_research) teach *required-ness, tool routing, live document context, and multi-step discovery* only in the delegate's injected hints/examples (`specialized_base.py:192-267`), not in the tool's own `description`/`parameters`. A raw caller of those would frequently mis-call. The footnotes domain is the best case (guidance baked into description + params), so the claim is most defensible there and weakest for charts/analysis/python.

---

## Decisive evidence — Part 2 (NUANCED / partly REFUTED)

The claim's parenthetical pitch borrows Anthropic "Tool Search Tool" vocabulary ("find_tools reveal schemas," "no need to flip listChanged") and applies it to this server. Three corrections from authoritative docs:

1. **Anthropic's Tool Search Tool is a client/API-side feature, not an MCP server capability, and it is *not* what makes WriterAgent's trick work.** Per Anthropic's engineering post: *"You provide all your tool definitions to the API, but mark tools with `defer_loading: true` to make them discoverable on-demand… Deferred tools aren't loaded into Claude's context initially. Claude only sees the Tool Search Tool itself plus any tools with `defer_loading: false`."* That is the API expanding *already-provided* definitions into context — it is orthogonal to a server choosing to omit tools from `tools/list`. WriterAgent's `find_tools`-style reveal is the server's own registry mechanism, not Anthropic's Tool Search Tool. The post *"doesn't mention `tools/list`, `tools/list_changed`, or `listChanged`"* at all. ([anthropic.com/engineering/advanced-tool-use](https://www.anthropic.com/engineering/advanced-tool-use))

2. **The MCP spec is silent on whether a `tools/call` target must appear in `tools/list` — it neither authorizes nor forbids calling unadvertised tools.** The spec frames `tools/list` as *"To discover available tools"* and `tools/call` as taking a `name`, with the only relevant protocol error being `"Unknown tool"` (`-32602`). "Unknown" means *not in the registry*, not *not in the advertised list*. So WriterAgent omitting a registered tool from `tools/list` while still serving it on `tools/call` is **not a spec violation** — but it is also **not a documented/blessed pattern**; it relies on the server choosing not to enforce list-membership. The spec also says servers **MUST** *"Implement proper access controls"* — using tier-exclusion purely as a *list-visibility* filter (not an *access* control) is exactly the gap the claim relies on. ([modelcontextprotocol.io spec 2025-06-18, server/tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools))

3. **"No need to flip listChanged" is true but for a different reason than implied.** `listChanged` / `notifications/tools/list_changed` exists so a server can tell the client *"re-fetch `tools/list`, it changed."* The claim is right that you don't need it — but precisely *because the specialized tools are deliberately never advertised at all*. You're not dynamically revealing them into `tools/list`; you're bypassing the list entirely via out-of-band name knowledge. That's a coherent design, but it is the **opposite** of the listChanged pattern (which exists to keep the advertised list authoritative), not a clever avoidance of it. ([same MCP spec, "List Changed Notification"](https://modelcontextprotocol.io/specification/2025-06-18/server/tools))

---

## Bottom line

- The **core technical assertion is SUPPORTED and verified against the code**: tier filtering is list-only (`mcp_protocol.py:442`); `tools/call` routes by unfiltered name lookup (`mcp_protocol.py:459`, `tool.py:646-648`, `tool.py:705`); no tier check anywhere in the execution path.
- The **"direct discovery" pitch is NUANCED**: it works mechanically, but (a) it borrows Anthropic Tool-Search-Tool terminology for what is actually WriterAgent's own registry behavior — those are different systems; (b) the MCP spec neither blesses nor forbids calling unadvertised tools, and explicitly expects servers to implement *access* controls — here tier is only a *visibility* filter, so this is an unenforced gap, not a sanctioned feature; (c) correctness is **tool-dependent** — robust standalone for footnotes, degraded/failing for charts/analysis/python/calc/shapes whose operative knowledge lives in delegate scaffolding, and hard-blocked for any specialized tool whose `uno_services`/`doc_types` don't match the open document (`tool.py:729`).

Relevant files: `/Users/augustozolet/Documents/Projetos_Escritório/writeragent-explore-mcp/plugin/mcp/mcp_protocol.py`, `/Users/augustozolet/Documents/Projetos_Escritório/writeragent-explore-mcp/plugin/mcp/mcp_state.py`, `/Users/augustozolet/Documents/Projetos_Escritório/writeragent-explore-mcp/plugin/framework/tool.py`.

Sources: [Anthropic — Advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use), [MCP spec 2025-06-18 — Server/Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)


### [tool-search-mechanism]

I have decisive evidence on both clauses. The MCP connector doc confirms the layering claim with the exact config keys. Let me verify the one local code detail the claim implicitly relies on — that the WriterAgent server itself does NOT implement deferral (it just hard-excludes tiers from `tools/list`), which is the contrast the claim draws.

I already have that from `mcp_protocol.py:442` and `tool.py:646-648`. I have everything needed.

---

## VERDICT: SUPPORTED

Both clauses of the claim are accurate. The first clause matches Anthropic's documented mechanism verbatim; the second clause matches the MCP connector spec, which provides client-side `defer_loading` on `mcp_toolset` precisely so a server need not implement deferral itself. The local WriterAgent code is a clean illustration of the contrast (a server that does NOT implement deferral).

### Decisive evidence — Clause 1 (catalog kept out of context, loaded on demand by search)

From the authoritative Anthropic doc, https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool:

> "Instead of loading all tool definitions into the context window upfront, Claude searches your tool catalog ... and loads only the tools it needs."

The documented flow:
> "2. You provide all tool definitions with `defer_loading: true` ... 3. Claude sees only the tool search tool and any non-deferred tools initially. 4. When Claude needs additional tools, it searches ... 5. The API returns 3-5 most relevant `tool_reference` blocks. 6. These references are automatically expanded into full tool definitions."

> "**How deferral works internally:** Deferred tools are not included in the system-prompt prefix. When the model discovers a deferred tool through tool search, the API appends a `tool_reference` block inline ... then expands it into the full tool definition."

Search is real (regex `tool_search_tool_regex_20251119` via `re.search()`, or BM25 `tool_search_tool_bm25_20251119` natural-language), searching "tool names, descriptions, argument names, and argument descriptions." Up to 10,000 tools; ~85% token reduction. This is exactly what the claim describes.

### Decisive evidence — Clause 2 (client can layer deferral over an MCP server without the server implementing it)

From the authoritative MCP connector doc, https://platform.claude.com/docs/en/agents-and-tools/mcp-connector:

The `mcp_toolset` lives in the client's `tools` array and carries the deferral config. The per-tool option table states for `defer_loading`:
> "If true, tool description is not sent to the model initially. Used with Tool search tool." — default `false`.

It is set in `default_config` / `configs` on the `mcp_toolset` (client side), e.g.:
> `"default_config": { "defer_loading": true }`

And explicitly:
> "For large tool sets (dozens of tools across several servers), consider enabling `defer_loading` with the Tool search tool so only relevant tools are surfaced per query."

Nothing in the server definition (`mcp_servers`: only `type`/`url`/`name`/`authorization_token`) carries deferral, and the connector "enables you to connect to remote MCP servers ... without a separate MCP client" / "without implementing an MCP client." So deferral is applied by the Anthropic-side client/connector over a stock MCP server. The server exposes its normal `tools/list`; the client decides which of those to defer. This directly supports the claim's second clause.

### Decisive local-code evidence (the contrasting case the claim sets up)

The WriterAgent MCP server does NOT implement the Anthropic deferral protocol — it just hard-hides tiers from its own `tools/list`, with no `defer_loading`/`tool_reference` machinery:

- `/Users/augustozolet/Documents/Projetos_Escritório/writeragent-explore-mcp/plugin/mcp/mcp_protocol.py:442`
  ```python
  schemas = self.tool_registry.get_schemas("mcp", doc=doc, exclude_tiers=frozenset({"specialized", "specialized_control"}))
  ```
- `tools/call` resolution is ungated, `/Users/augustozolet/Documents/Projetos_Escritório/writeragent-explore-mcp/plugin/mcp/mcp_protocol.py:459`:
  ```python
  tool = self.tool_registry.get(tool_name)
  ```
- `/Users/augustozolet/Documents/Projetos_Escritório/writeragent-explore-mcp/plugin/framework/tool.py:646-648`:
  ```python
  def get(self, name: str) -> ToolBase | None:
      """Get a tool by name, or None."""
      return self._tools.get(name)
  ```

This is a plain custom tier filter, not Anthropic's Tool Search Tool. It confirms the claim's premise that a server need not implement deferral — and indeed this one does not; the connector-side `defer_loading` would be what layers on top.

### Important caveats the claim glosses over

1. **"Without the server needing to implement deferral" is true, but the model-side deferral is still NOT free of integration.** The client must run on Anthropic's MCP connector (beta header `mcp-client-2025-11-20`) or a custom client, AND include a `tool_search_tool_*` entry in the top-level `tools` array. `defer_loading` on the `mcp_toolset` alone hides descriptions but gives the model no way to retrieve them unless a tool search tool (server-side or custom) is also present. The claim implies the client "just searches"; in practice the client wires up both the toolset deferral and the search tool.

2. **Connector transport limits.** The remote MCP-connector path requires a publicly-exposed HTTPS server (Streamable HTTP/SSE); "Local STDIO servers cannot be connected directly." A localhost STDIO/HTTP server like WriterAgent's `localhost:8765/mcp` would go through the client-side helper path (`mcpTools(...)`) rather than the `mcp_servers` connector, but the `defer_loading`/`tool_reference` layering still happens client-side either way — so the claim holds, just via a different code path.

3. **The two "search" mechanisms are not the same thing.** WriterAgent's tier hiding ≠ Anthropic's Tool Search Tool. WriterAgent permanently drops specialized tools from `tools/list` (they're reachable only via its own `delegate_to_specialized_*` gateway, and are in fact still directly callable over `tools/call` since call-time is ungated). Anthropic's mechanism keeps the full catalog available to the model on demand via searchable `tool_reference` expansion. The claim is about Anthropic's mechanism and is correct about it; it should not be conflated with WriterAgent's tier scheme.

4. **Server-side ZDR / retention nuance** (minor): the Tool Search Tool itself is ZDR-eligible, but the MCP connector is explicitly NOT ZDR-eligible. Not central to the claim, but relevant if "layering over MCP" is taken to inherit the search tool's retention properties — it does not.

Sources:
- [Tool search tool — Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- [MCP connector — Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/mcp-connector)


## Investigation findings


### [crux-routing]

Both files read. Here is the precise answer with file:line references and quoted code.

## (a) Does the server look up and EXECUTE a tool that isn't in the advertised `tools/list`?

**It executes it.** The `tools/call` handler resolves the tool by name with **zero tier/exposure check**. The only place `exclude_tiers={"specialized","specialized_control"}` is applied is `tools/list`, not `tools/call`.

`tools/list` (the only place tiers are filtered) — `mcp_protocol.py:442`:
```python
schemas = self.tool_registry.get_schemas("mcp", doc=doc, exclude_tiers=frozenset({"specialized", "specialized_control"}))
```

`tools/call` lookup — `mcp_protocol.py:459`:
```python
tool = self.tool_registry.get(tool_name)
is_long_running = getattr(tool, "long_running", False) if tool else False
```
No tier inspection here. The state machine then routes straight to execution via `ExecuteToolEffect` (`mcp_protocol.py:487-494`), calling `_execute_long_running` or `_execute_with_backpressure`, both of which end in `self.tool_registry.execute(tool_name, context, **arguments)` (`mcp_protocol.py:627` and `mcp_protocol.py:683`). The name is passed through unfiltered.

## (b) Which registry method resolves by name, and does it apply a tier filter?

`ToolRegistry.get(name)` — `tool.py:646-648`:
```python
def get(self, name: str) -> ToolBase | None:
    """Get a tool by name, or None."""
    return self._tools.get(name)
```
A raw dict lookup keyed by name. **No tier, exposure, or `exclude_tiers` filter whatsoever.** Tier filtering lives only in `get_tools(...)` (`tool.py:608-617`), which `tools/call` never calls. The actual execution path `ToolRegistry.execute()` (`tool.py:690-705`) also does its lookup via `self._tools.get(tool_name)` (`tool.py:705`) with no tier check.

## (c) long_running / backpressure / sessions / per-document mutation gating inside `tools/call`

- **long_running**: branch chosen at `mcp_protocol.py:490-493`. `effect.is_long_running` (seeded from `getattr(tool, "long_running", False)` at line 460) picks `_execute_long_running` (runs on the HTTP worker thread, `:578`) vs `_execute_with_backpressure` (runs on the VCL main thread, `:564`).
- **backpressure**: a process-wide `threading.Semaphore(1)` (`:73`). `_execute_with_backpressure` does `_tool_semaphore.acquire(timeout=_WAIT_TIMEOUT)` (`:570`); on failure raises `BusyError` → HTTP 429 (`:549-551`). Long-running tools **skip** this semaphore entirely.
- **sessions**: only a single global `_mcp_session_id` string (`:166`), minted on `initialize` (`:407-408`) and echoed in headers. It is **never read or enforced** in `tools/call` — no per-session auth/scoping gate.
- **per-document mutation gating**: a per-doc `threading.Lock` keyed by document URL/UID (`_doc_gates`, `:79`). Both execution paths wrap the call in `_document_mutation_gate(doc_key, enabled=needs_gate)` (`:625` and `:681`), where `needs_gate = _tool_needs_document_mutation_gate(tool, arguments)` (`:624`/`:680`). This only *serializes* concurrent mutating calls on the same document — it does **not reject** anything based on tier/exposure.

## (d) Per-tool gating at call time (is_mutation, doc_type/uno_services, tier)

All gating happens inside `ToolRegistry.execute()` (`tool.py:690-801`) and concerns **document compatibility and mutation safety — never tier/exposure**:

- **uno_services / doc_types compatibility** — `tool.py:710-729`. If the tool declares `uno_services` or `doc_types` and the current doc matches neither, it raises `ValueError(f"Tool {tool_name} does not support the current document")` (`:729`). A *universal* specialized tool (`uno_services is None and doc_types is None`) is treated as supported (`:725-726`) and passes.
- **is_mutation** — only used for the read-only-target guard at `tool.py:750-756`: rejects writes **only when `ctx.read_only_target` is True**. MCP builds its `ToolContext` with the default `read_only_target=False` (`mcp_protocol.py:619`, `:676`), so this guard never fires for MCP calls.
- **tier** — **not checked anywhere in the execution path.** Searching `execute()` and both MCP execute helpers, `tier` is never read at call time.

There is also `validate()` (`tool.py:746-748`, schema/required-param check) and kwarg restriction to schema props (`:733-736`) — neither tier-aware.

## CONCLUSION

**YES — a `tier="specialized"` (or `specialized_control`) tool CAN be invoked directly over MCP today.** It is merely hidden from `tools/list`; it is not protected at `tools/call`.

Decisive evidence chain:
1. Tier exclusion exists **only** in `tools/list` (`mcp_protocol.py:442`).
2. `tools/call` resolves the tool with `self.tool_registry.get(tool_name)` (`mcp_protocol.py:459`), which is a plain `self._tools.get(name)` with no tier filter (`tool.py:646-648`).
3. Execution calls `self.tool_registry.execute(tool_name, ...)` (`mcp_protocol.py:627`, `:683`), whose lookup is again `self._tools.get(tool_name)` (`tool.py:705`) and whose only gates are uno_services/doc_types compatibility (`tool.py:710-729`), `read_only_target` (False for MCP), and schema validation — **none tier-based**.

The only thing that could block a specialized tool at call time is a **document-type mismatch** (`tool.py:729`): a specialized tool that declares specific `uno_services`/`doc_types` incompatible with the active doc would be rejected with `"does not support the current document"`. Any specialized tool that is universal (no `uno_services`/`doc_types`) or compatible with the open document will execute normally.


### [domain-scaffolding]

I now have everything needed for a precise, evidence-backed assessment. `registry.get(name)` does a plain dict lookup with no tier gating, and the MCP call path (`_execute_with_backpressure` / `_execute_long_running` → `_execute_tool_on_main`) never re-checks tier. So the tier filter exists only at `tools/list` (mcp_protocol.py:442), not at `tools/call`.

---

## What the delegate injects into the specialized sub-agent (beyond the tools)

All assembled in `DelegateToSpecializedBase.execute()` at `plugin/doc/specialized_base.py:107-291`, then handed to `build_toolcalling_agent` (`plugin/chatbot/smol_agent.py:299-309`) which builds a smolagents `ToolCallingAgent`.

### (a) Domain instructions / system prompt — SUBSTANTIAL, dynamically built

- **Base instruction string**: `specialized_base.py:259-263`. A generic preamble: *"You are a specialized {Writer/Calc/Draw} task executor focused on the '{domain}' domain. You have a focused set of tools... Use them to fulfill the user's request."* — then concatenates every hint below.
- This becomes the smolagents `instructions` → injected at `__CUSTOM_INSTRUCTIONS__` in the system prompt template (`plugin/contrib/smolagents/toolcalling_agent_prompts.py:88`).
- The surrounding `SYSTEM_PROMPT_TEMPLATE` (`toolcalling_agent_prompts.py:68-96`) adds the entire ReAct contract: Action/Observation loop semantics, "call the finish tool... it is the only way to end the run", and the 4 numbered rules. None of this is in any tool's description.

### (b) Per-domain examples — MODERATE, but mostly generic

- Selected via `examples_key = f"{label.lower()}:{domain}"` → `get_examples_block(key)` (`specialized_base.py:266-267`), defined in `plugin/chatbot/smol_examples.py:185-203`.
- Reality of the dispatch: only **two** distinct blocks ever apply to specialized delegation:
  - `:python` keys → `PYTHON_SPECIALIZED_EXAMPLES` (`smol_examples.py:165-182`) — substantial: venv import policy + a real `run_venv_python_script` + `specialized_workflow_finished` example.
  - **every other domain** → `DELEGATE_GENERIC_EXAMPLES_BLOCK` (`toolcalling_agent_prompts.py:39-63`) — a generic Guangzhou/Shanghai `web_search` example whose only domain-specific content is showing the `specialized_workflow_finished` finish call. It is **not** tailored to footnotes/charts/tables/etc.
- Injected at `__EXAMPLES_BLOCK__` (`toolcalling_agent_prompts.py:79-81`).

### (c) Hints — SUBSTANTIAL and the most domain-specific scaffolding (`specialized_base.py:192-262`)

These are conditional strings appended to the instruction. They carry real operational knowledge **not present in tool params**:
- **footnotes_hint** (`192-194`): tells the agent to pass the anchor sentence as `insert_after_text` because "the task executor cannot move the view cursor."
- **shapes_canvas** (`196-199`): injects live canvas context via `format_shapes_canvas_context`.
- **charts_hint** (`201-206`): Calc → "you MUST specify the data range explicitly"; Writer/Draw → "you MUST specify both `headers` and `rows`."
- **calc_ctx** (`208-220`): injects the live `[SPREADSHEET CONTEXT]` (cell data, fetched on main thread).
- **document_research_hint + open_docs_context** (`222-242`): workflow hint + `[OPEN DOCUMENTS CONTEXT]` listing.
- **images_hint** (`244-248`): use `list_nearby_image_files` before `insert_image`.
- **analysis_hint** (`249-257`): a paragraph routing to `analyze_data` / `plot_data` / `calc_goal_seek` / `calc_solver` and the data_range convention.
- **python_hint** (`258`): full venv import policy via `python_specialized_sub_agent_hint` (`constants.py:311-327`).

### (d) required_core_tools — STRUCTURAL (controls which tools exist, not prompt text)

- Declared per-domain base class, e.g. base Writer = `{get_document_content, get_document_tree}` (`writer/specialized_base.py:47`); footnotes/fields/styles/bookmarks add `search_in_document` (`:78,135,153,166,196,274`); Calc bases add `get_sheet_summary`/`read_cell_range` (`calc/base.py:37,122`).
- **Consumed** in `ToolRegistry.get_tools` when `active_domain` is set (`framework/tool.py:589-606`): it whitelists the domain's specialized tools + the finish tool + only those core tools named in `required_core_tools`. This is how the sub-agent gets read/discovery tools (e.g. `search_in_document`) it needs to locate anchors before mutating.
- The delegate calls this via `registry.get_tools(..., active_domain=domain, ...)` at `specialized_base.py:181`.

### (e) The finish tool — REQUIRED, structural

- `SpecializedWorkflowFinished` / `specialized_workflow_finished` (`writer/specialized_base.py:278-296`), tier `specialized_control`, `is_final_answer_tool = True`.
- Wired as `final_answer_tool_name="specialized_workflow_finished"` (`specialized_base.py:267`), auto-included by `get_tools` (`tool.py:601-602`), and is the only way the ReAct loop terminates (per system-prompt template line `toolcalling_agent_prompts.py:77`).

---

## KEY QUESTION: would a specialized tool work if called DIRECTLY over MCP (no sub-agent)?

**First, can it even be reached over MCP?** The MCP server **hides** specialized tools from `tools/list` — `exclude_tiers=frozenset({"specialized","specialized_control"})` at `plugin/mcp/mcp_protocol.py:442`. But `tools/call` does **not** re-check the tier: `_mcp_tools_call` → `registry.get(tool_name)` is a bare dict lookup (`framework/tool.py:646-648`), and `_execute_with_backpressure`/`_execute_long_running` (`mcp_protocol.py:564-603`) never inspect tier. So a client that already knows the name (e.g. `footnotes_insert`) **can invoke it directly**, even though it isn't advertised.

**Would it work correctly? — Mixed, and tool-dependent. Verdict: the better-designed tools are self-sufficient; several lean on the scaffolding.**

**Evidence it CAN work standalone (self-sufficient tools):**
- The footnotes tools are a deliberate best case. `footnotes_insert.description` (`writer/specialized/footnotes.py:73-80`) and the `insert_after_text` param doc (`87-95`) **internalize the exact knowledge the footnotes_hint duplicates** — "When the insert position must be specific (e.g. delegated sub-agent work), pass insert_after_text... the task executor cannot move the view cursor." The execute body also has a sane fallback to the view cursor (`134-145`). A direct caller passing `note_type` + `text` (+ optional `insert_after_text`) gets correct behavior with no prompt. The hint is redundant reinforcement, not load-bearing here.
- `footnotes_list/edit/delete/settings_*` are fully self-describing (enums, index-from-list guidance in their own descriptions, `:166-343`).

**Evidence some tools LEAN on the scaffolding:**
- **charts**: the "MUST specify data_range" / "MUST specify headers and rows" requirement lives in `charts_hint` (`specialized_base.py:201-206`), not necessarily in the chart tool's own schema. A direct MCP caller omitting those would fail or misbehave because the *required-ness* is taught only in the injected hint.
- **analysis** (Calc): the entire tool-selection policy (`analyze_data` vs `plot_data` vs `calc_goal_seek` vs `calc_solver`, and "always pass a data_range") is in `analysis_hint` (`249-257`). Without it, a caller has no routing guidance — individual tool descriptions don't cross-reference siblings.
- **python**: `run_venv_python_script` depends on the venv import policy and pre-imported `np/sp/pd` knowledge delivered only via `python_hint` (`258`, `constants.py:311-327`) + `PYTHON_SPECIALIZED_EXAMPLES` (`smol_examples.py:165-182`). A direct call without knowing the pre-imports/policy would frequently write wrong scripts.
- **calc/shapes/document_research**: these depend on *injected live context* (`[SPREADSHEET CONTEXT]`, shapes canvas, open-docs list — `specialized_base.py:196-242`). The tool params can't supply that; a direct caller would be operating blind on document state, though each individual mutation call (given correct addresses) would still execute.
- **required_core_tools dependency**: many domains assume the agent first calls a discovery tool (`search_in_document`, `get_sheet_summary`) to obtain indices/anchors/addresses. Tools like `footnotes_edit`/`footnotes_delete` require an `index` "from footnotes_list" (`footnotes.py:199,237`). A direct caller must replicate that two-step discovery themselves; nothing in the single tool's schema enforces or automates it.

**Bottom line:** Specialized tools are **not uniformly self-sufficient**. The execute() bodies are independent of the sub-agent (no reliance on agent state — only `ctx.doc`), so mechanically they run fine when called directly, and the tier filter is only cosmetic at list-time (call-time is ungated). The well-curated domains (footnotes) bake their critical guidance into description+params and would work correctly standalone. But domains whose **requiredness, tool-routing, live document context, or multi-step discovery** is taught only in the injected hints/examples/required_core_tools (charts, analysis, python, calc, shapes, document_research) would degrade or fail when called raw over MCP, because that knowledge lives in the scaffolding (`specialized_base.py:192-267`), not in the tools' own `description`/`parameters`.

### File:line index
- Delegate orchestration / all hints: `plugin/doc/specialized_base.py:107-291` (instructions `259-263`; hints `192-258`; tool gathering `181`; examples key `266-267`; agent build `267`)
- Agent factory + system-prompt wiring: `plugin/chatbot/smol_agent.py:299-309`; template `plugin/contrib/smolagents/toolcalling_agent_prompts.py:68-96`
- Examples: `plugin/chatbot/smol_examples.py:185-203`; generic block `plugin/contrib/smolagents/toolcalling_agent_prompts.py:39-63`
- required_core_tools: declarations `plugin/writer/specialized_base.py:47,78,135,153,166,196,274`, `plugin/calc/base.py:37,122`; consumption `plugin/framework/tool.py:589-606`
- Finish tool: `plugin/writer/specialized_base.py:278-296`
- python hint: `plugin/framework/constants.py:311-327`
- Self-sufficient tool sample: `plugin/writer/specialized/footnotes.py:71-100` (insert), `166-343` (rest)
- MCP exposure (list excludes specialized): `plugin/mcp/mcp_protocol.py:442`; call path ungated: `plugin/mcp/mcp_protocol.py:451-603`, `plugin/framework/tool.py:646-648`


### [quantify]

# Specialized tool catalog — quantified

Tools are auto-discovered by `ToolRegistry.auto_discover` (`plugin/framework/tool.py:506`): a class registers iff it inherits `ToolBase`, is concrete, isn't a `ToolBaseDummy`, and defines a `name`. "Specialized" = effective `tier == "specialized"` (set on the per-app `*SpecialBase` at `plugin/{writer,calc,draw}/...` and inherited by per-domain bases). `uno` isn't importable outside LibreOffice, so I enumerated via AST inheritance resolution rather than a live registry. I verified the edge cases (the 35 mock tools in `writer/specialized/mock_domains.py` are inside a `'''...'''` block = inert; `web_research`/`visit_webpage` are core-tier, not specialized; `ListOpenDocuments` is `tier="mcp"`).

## (a) Counts: 138 concrete specialized tools, 30 active domains

Base classes live in: `writer/specialized_base.py`, `calc/base.py:25+`, `draw/base.py:25+`, `doc/specialized_base.py`. The gateway `delegate_to_specialized_*_toolset` tools are core-tier (not counted).

**WRITER — 82 tools, 14 domains** (`uno_services=[TextDocument]`; the 4 chatbot-hosted ones physically live in `plugin/chatbot/` but are Writer domains):
- `tracking` (11): track_changes_{accept,accept_all,reject,reject_all,list,show,start,stop,comment_insert,comment_delete,comment_list} — `writer/tracking.py`
- `images` (9): generate_image, insert_image, replace_image, delete_image, download_image, get_image_info, set_image_properties, list_images, list_nearby_image_files — `writer/images/images.py`
- `bookmarks` (7): create/delete/get/list/rename/resolve/cleanup_bookmark(s) — `writer/specialized/bookmarks.py`
- `page` (7): get/set_page_style_properties, get/set_page_columns, get/set_header_footer_text, insert_page_break — `writer/page.py`
- `footnotes` (6): footnotes_{insert,edit,delete,list,settings_get,settings_update} — `writer/footnotes` 
- `forms` (6): create_form, generate_form, create/edit/delete_form_control, list_form_controls — `writer/specialized/forms.py`
- `shapes` (6): upsert_shape, delete_shape, shapes_connect, shapes_group, get_draw_summary, list_writer_images — `writer/specialized/shapes.py`
- `structural` (6): navigate_heading, get_heading_children, get_surroundings, goto_page, list_sections, read_section — `writer/structural.py`
- `fields` (5): fields_{insert,delete,list,update_all}, update_fields
- `indexes` (5): indexes_{create,add_mark,list,update_all}, refresh_indexes
- `styles` (5): create/update_style, get_style_info, list_styles, import_styles — `writer/styles.py`
- `comments` (4): list/delete/resolve_comment, workflow
- `textframes` (3): list/get_text_frame_info, set_text_frame_properties
- `embedded` (2): embedded_insert, embedded_edit
- `brainstorming` (2): brainstorm_research_web, save_design_spec — `chatbot/brainstorming.py:86,111`
- `writing_plan` (2): writing_research_web, write_document_section — `chatbot/writing.py:85,110`

(brainstorming+writing_plan = the 4 "chatbot-hosted" tools; fold them into Writer and the Writer total is 82 with 14 domains.)

**CALC — 35 tools, 10 domains** (`calc/base.py` bases):
- `sheets` (9): list/create/delete/rename/switch/protect_sheet, apply/clear/get_sheet_filter — `calc/sheets.py`, `calc/sheet_filter.py`
- `analysis` (5): analyze_data, optimize_data, plot_data, calc_goal_seek, calc_solver — `calc/analysis.py`, `calc/optimize.py`
- `charts` (5): upsert_chart, delete_chart, list_charts, get_chart_info, manage_charts — `calc/charts.py`
- `comments` (3): add/delete/list_cell_comment(s)
- `conditional_formatting` (3): add/list/remove_conditional_format(s)
- `pivot_tables` (3): create/list/refresh_pivot_table — `calc/pivot.py`
- `errors` (2): detect_and_explain_errors, evaluate_formula
- `python` (2): run_venv_python_script, symbolic_math — `calc/venv_python.py`, `calc/symbolic_math.py`
- `search` (2): search/replace_in_spreadsheet
- `ranges` (1): sort_range

**DRAW/IMPRESS — 13 tools, 5 domains** (`draw/base.py` bases):
- `slide_transitions` (4): get/set_slide_transition, get/set_slide_layout — `draw/transitions.py`
- `slide_masters` (3): list_master_slides, get/set_slide_master — `draw/masters.py`
- `speaker_notes` (2): get/set_speaker_notes — `draw/notes.py`
- `headers_footers` (2): get/set_headers_footers — `draw/headers_footers.py`
- `math` (1): insert_math — `draw/math_insert.py`

**SHARED (cross-app, one `document_research` toolset) — 5 tools, 1 domain** (used by all three apps' delegation):
- `document_research` (5): list_nearby_files (`doc/document_research_tools.py:18`), grep_nearby_files (`doc/document_research_grep_tool.py:18`), delegate_read_document (`doc/document_research_specialized.py:102`), search_embeddings (`embeddings/document_research_search_tool.py:23`), search_nearby_files (`embeddings/document_research_fts_tool.py:21`)

Note: `web_research` domain has base classes but **0 leaf tools** — it's served by the core-tier `web_research` tool (`chatbot/web_research.py:30`), not a specialized leaf.

## (b) Representative schemas + token sizes (chars/4)

| Tool | App / domain | file:line | props | ~tokens |
|---|---|---|---|---|
| `create_pivot_table` | calc/pivot_tables | `calc/pivot.py:130` | 9 | **356** |
| `generate_image` | writer/images | `writer/images/images.py:55` | 9 | **305** |
| `create_form_control` | writer/forms | `writer/specialized/forms.py:126` | 9 | **307** |
| `set_slide_transition` | draw/slide_transitions | `draw/transitions.py:148` | 6 | **289** |
| `search_embeddings` | shared/document_research | `embeddings/document_research_search_tool.py:23` | 0 | **79** |
| `create_bookmark` | writer/bookmarks | `writer/specialized/bookmarks.py:178` | 1 | **78** |
| `track_changes_accept` | writer/tracking | `writer/tracking.py:256` | 1 | **71** |
| `upsert_chart` | calc/charts | `calc/charts.py:618` | 0* | **34** |

(*upsert_chart/the shapes tools build their schema at runtime, so the static literal is small — real advertised size is larger.) Sum of these 8 ≈ **1,519 tokens**; mean ≈ **190 tok/tool**. Schemas range from ~34 (thin wrappers) to ~356 (multi-param tools); the heavy ones (image gen, pivot, forms, transitions, analysis) cluster at 280–360.

## (c) Flat-exposure bloat vs core list

- **ALL 138 specialized schemas at once:** total ≈ **66,934 chars ≈ 16,734 tokens**. Per-app: writer ≈ 9,072, calc ≈ 4,943, draw ≈ 1,646, document_research ≈ 664 (doc 516 + embeddings 148), chatbot-hosted writer ≈ 408.
- **Core tool list:** a single-app session exposes ~12 core tools (5 app-specific + `humanize` + `upsert_memory` + the `delegate_to_specialized_*` gateway + `web_research`/document-research gateway). The full union of 17 registered `tier="core"` tools (across all apps) measures **9,560 chars ≈ 2,390 tokens**; a single app's ~12-tool slice is in the ~1.5–2k range.

**Bloat ratio: advertising every specialized schema flat (~16.7k tok) is ≈ 7× the core list (~2.4k tok)** — and ~70× a single thin tool. This is exactly what the `tier="specialized"` + `exclude_tiers` + `delegate_to_specialized_*` gateway design avoids: instead of paying ~16.7k tokens up front, the agent sees ~12 core tools (~2.4k) plus one-line domain descriptions on the gateway tool, and only loads a domain's 2–11 schemas (~0.4–2.5k tokens) when it delegates into that domain.

Key files: registry/tiers `plugin/framework/tool.py:243,529,604`; gateway descriptions `plugin/framework/constants.py:362,443,450`; per-app bases `writer/specialized_base.py:31`, `calc/base.py:25`, `draw/base.py:25`; shared gateway `doc/specialized_base.py:56`.


### [registry-mechanics]

I now have a complete, verified picture. Here is the implementation-ready map.

---

# Implementation map: `mcp.tool_exposure_mode`

## Current state (verified anchors)

- **The MCP filter site is `mcp_protocol.py:442`** inside `_mcp_tools_list`:
  ```python
  schemas = self.tool_registry.get_schemas("mcp", doc=doc, exclude_tiers=frozenset({"specialized", "specialized_control"}))
  ```
  Note: this hardcodes `exclude_tiers` and does **not** pass `active_domain`. So `tools/list` always omits `specialized` + `specialized_control` tiers and runs the `else`/`to_exclude` branch of `get_tools` (`tool.py:608-614`). (Compare `_DEFAULT_EXCLUDE_TIERS` at `tool.py:439` which also adds `"mcp"`; the MCP call deliberately omits `"mcp"` so MCP-only tools stay visible.)
- **Narrowing logic lives in `tool.py`:** `get_tools` `active_domain` branch at `tool.py:584-606`; `_is_specialized_domain_tool` at `tool.py:414-435` (handles composite `python:writer` domains and `specialized_cross_cutting`). `get_schemas` at `tool.py:624-639` forwards `active_domain` + `**kwargs` to `get_tools` and maps through `to_mcp_schema`.
- **Config access in the handler:** `MCPProtocolHandler.__init__` stores `self.services` (`mcp_protocol.py:185`). `services.config` is the `ConfigService` (`config_service.py:82`). The module convention is `services.config.proxy_for("mcp").get("<key>")` (see `mcp/__init__.py:83,104,123`), which auto-prefixes to `mcp.<key>` (`config_service.py:330-332`) and enforces the public/private access check (`config_service.py:303-311`). Dotted reads also work directly: `services.config.get("mcp.tool_exposure_mode")`.
- **Delegate tool / domain machinery for Options B & C:** `DelegateToSpecializedWriter` at `specialized_base.py:51-69` with `_special_base_class = ToolWriterSpecialBase`, `_agent_label = "Writer"`. The execute body is inherited from `DelegateToSpecializedBase` (`plugin/doc/specialized_base.py`, domain-scan at line 69-74). Domain catalog helper: `format_specialized_domains_description(base_cls, agent_label=...)` at `constants.py:671` and the underlying `_get_specialized_domains_str` at `constants.py:630`.

---

## Config declaration (shared by all three options)

**File `plugin/mcp/module.yaml`** — add under the existing `config:` block (after `mcp_port`, before `cors_allow_private_origins`). Keys here become `mcp.<field>` in `ConfigService` (`config_service.py:100-104`):

```yaml
  tool_exposure_mode:
    type: string
    default: delegate          # preserves today's behavior
    widget: select             # enum: delegate | direct_flat | direct_discovery
    options: [delegate, direct_flat, direct_discovery]
    label: MCP Tool Exposure
    helper: How specialized tools are surfaced to MCP clients. delegate=hidden behind the delegate gateway (default); direct_flat=all specialized tools in tools/list; direct_discovery=small list plus a find_tools search tool.
    public: true
```

Read it at the filter site (`_mcp_tools_list`, `mcp_protocol.py:432-443`). Add once near the top of the method:

```python
mode = self.services.config.proxy_for("mcp").get("tool_exposure_mode") or "delegate"
```

(`get` falls back to the manifest default, `config_service.py:171-173`, so a missing key yields `"delegate"`.)

---

## Option A — `direct_flat`: include the specialized tier in the MCP filter

The single touch-point is **`mcp_protocol.py:442`**. The hardcoded `exclude_tiers` is what hides the tier; flip it based on `mode`.

Replace line 442 with:

```python
if mode == "direct_flat":
    exclude_tiers = frozenset({"specialized_control"})   # expose "specialized", keep control tools hidden
else:
    exclude_tiers = frozenset({"specialized", "specialized_control"})
schemas = self.tool_registry.get_schemas("mcp", doc=doc, exclude_tiers=exclude_tiers)
```

Mechanics: dropping `"specialized"` from `exclude_tiers` makes `get_tools` keep those tools through the `_tier_excluded` filter (`tool.py:608-614`), so `to_mcp_schema` emits all of them. No change needed in `tool.py`. Decision to keep `specialized_control` excluded: that tier holds `specialized_workflow_finished` (`specialized_base.py:283`) and similar control tools that only make sense inside an active delegated domain — exposing them flat would be noise. (If you want them too, use `frozenset()`.)

Caveat to note for the implementer: `to_mcp_schema` (`tool.py:104-144`) injects a `document_url` property and, for the delegate gateway, a long `domain` description; the specialized tools themselves carry no such injection, so flat exposure is clean. The flat list will be large (every `ToolWriterSpecialBase`/`Calc`/`Draw` subclass), which is the known trade-off of this mode.

---

## Option B — `direct_discovery`: small list + a `find_tools` MCP tool

**Where it lives:** a new method `_mcp_find_tools(self, params, document_url=None)` on `MCPProtocolHandler` in `mcp_protocol.py`, plus a registration entry in the method dispatch dict at **`mcp_protocol.py:531`** and the explicit dispatch in `_process_jsonrpc` (`mcp_protocol.py:541-546`).

Two surfaces to wire:

1. **Keep `tools/list` small** — at `mcp_protocol.py:442` keep the current `exclude_tiers={"specialized","specialized_control"}` for `delegate` and `direct_discovery`. The branch from Option A only widens for `direct_flat`. So the same `mode` switch covers both A and B.

2. **Expose `find_tools` to the client.** MCP clients only see tools via `tools/list`, so `find_tools` must itself be a `core`/`mcp`-tier `ToolBase` (so it shows up in the small list). Two viable shapes:

   - **(B-preferred) A real registered tool** — new `plugin/mcp/find_tools_tool.py` defining `class FindToolsTool(ToolBase)` with `tier = "mcp"` (so it appears in MCP lists but not chat, per `_DEFAULT_EXCLUDE_TIERS` at `tool.py:439`), `name = "find_tools"`, parameters `{query: string (optional), domain: string (optional)}`. It is auto-discovered like every other tool. Its `execute(ctx, query=None, domain=None)` calls back into the registry via `ctx.services.tools`:

     ```python
     reg = ctx.services.tools
     schemas = reg.get_schemas(
         "mcp",
         doc=ctx.doc,
         doc_type=ctx.doc_type,
         active_domain=domain,                       # reuses tool.py:584-606 narrowing
         exclude_tiers=frozenset(),                  # allow specialized tier through
     ) if domain else reg.get_schemas("mcp", doc=ctx.doc, doc_type=ctx.doc_type,
                                      exclude_tiers=frozenset({"specialized_control"}))
     if query:
         q = query.lower()
         schemas = [s for s in schemas if q in s["name"].lower() or q in (s.get("description","").lower())]
     return {"status": "ok", "tools": schemas}
     ```

     Key reuse point: passing `active_domain=domain` triggers exactly the `_is_specialized_domain_tool` narrowing (`tool.py:599`, via `_is_specialized_domain_tool` `tool.py:414-435`), so `find_tools(domain="tables")` returns precisely that domain's specialized schemas plus its `required_core_tools`. This is the cleanest design because it goes through the normal tool-execution path (`tool_registry.execute`, `mcp_protocol.py:627/683`) and `ToolContext` already carries `services` (`tool.py:194`), so no protocol-handler plumbing is needed beyond the config gate. **Gate visibility:** in `_mcp_tools_list`, only inject/keep `find_tools` when `mode == "direct_discovery"` — since it's auto-discovered it would otherwise always appear; filter it out for `delegate`/`direct_flat` by adding `names`-less post-filter, or give it `tier="mcp"` and drop it from the schema list when `mode != "direct_discovery"`.

   - **(B-alt) A protocol-level method** — add `"find_tools": self._mcp_find_tools` to the dispatch dict at `mcp_protocol.py:531` and an `elif method == "find_tools":` branch at `mcp_protocol.py:543`. `_mcp_find_tools` resolves the doc the same way `_mcp_tools_list` does (`mcp_protocol.py:433-440`) then calls `self.tool_registry.get_schemas("mcp", doc=doc, active_domain=params.get("domain"), exclude_tiers=frozenset())` and applies the `query` substring filter. Downside: a custom JSON-RPC method is not discoverable by standard MCP clients (they won't know to call it), so B-preferred is the recommended integration. Use B-alt only if you also advertise it some other way.

   **The registry call is identical in both:** `get_schemas("mcp", doc=..., active_domain=<domain>, exclude_tiers=frozenset())`. That is the exact integration point with `tool.py` — `get_schemas` (`tool.py:624`) → `get_tools(active_domain=...)` (`tool.py:632` → `tool.py:584-606`).

---

## Option C — single specialized-request tool (sketch)

Instead of N specialized schemas or a discovery search, expose **one** MCP tool that takes a `domain` + `task` (and optional `args`) and runs the whole specialized request server-side. This is essentially re-exposing the existing delegate gateway under MCP.

- **Reuse what exists:** `DelegateToSpecializedWriter` (`specialized_base.py:51`) already is this tool for chat — `domain` + `task`, with `_special_base_class`/`_agent_label` driving the domain catalog in its schema via `to_mcp_schema`'s special-base branch (`tool.py:127-143`). Its `tier` is `"specialized_control"` (inherited path) so it's currently excluded from MCP lists.
- **Integration:** in `_mcp_tools_list` (`mcp_protocol.py:442`), when `mode` selects Option C, build the schema list as the small core set **plus** the delegate gateway tool(s). Easiest: `exclude_tiers=frozenset({"specialized"})` (keep `specialized_control` so the gateway + finish tool show) — or explicitly append the gateway by name. Because the gateway's `to_mcp_schema` already emits the full domain list in its `domain` property description (`tool.py:141-142` → `format_specialized_domains_description`, `constants.py:671`), the MCP client sees one tool whose schema self-documents every domain.
- **Execution:** unchanged. `tools/call` with `name="delegate_to_specialized_writer_toolset"`, `arguments={domain, task}` flows through `_mcp_tools_call` → `_execute_with_backpressure`/`_execute_long_running` → `tool_registry.execute` (`mcp_protocol.py:627/683`), and `DelegateToSpecializedBase.execute` spins the sub-agent. Note `requires_document_lock` is overridden on delegate tools (`tool.py:259-266`) so read-only domains skip the mutation gate — already handled.
- **Net new code is minimal:** only the `_mcp_tools_list` schema-assembly branch; no new tool class, no new dispatch method.

---

## Summary of touch-points

| Concern | File:line |
|---|---|
| Config key declaration | `plugin/mcp/module.yaml` config block (after `mcp_port`) |
| Read config at filter site | `plugin/mcp/mcp_protocol.py:432-443` (`_mcp_tools_list`), via `self.services.config.proxy_for("mcp").get("tool_exposure_mode")` |
| **Option A** — flip `exclude_tiers` | `plugin/mcp/mcp_protocol.py:442` (only line that changes) |
| Narrowing reused by all options | `plugin/framework/tool.py:584-606` (`get_tools` active_domain) + `tool.py:414-435` (`_is_specialized_domain_tool`); entered via `get_schemas` `tool.py:624-639` |
| **Option B** — `find_tools` tool (preferred) | new `plugin/mcp/find_tools_tool.py` (`ToolBase`, `tier="mcp"`); calls `ctx.services.tools.get_schemas("mcp", doc=ctx.doc, active_domain=domain, exclude_tiers=frozenset())`; visibility gated in `_mcp_tools_list` |
| **Option B-alt** — protocol method | dispatch dict `mcp_protocol.py:531` + branch `mcp_protocol.py:543`; new `_mcp_find_tools` resolving doc like `mcp_protocol.py:433-440` |
| **Option C** — single gateway tool | `_mcp_tools_list` schema assembly at `mcp_protocol.py:442` (include delegate gateway); reuses `DelegateToSpecializedWriter` `specialized_base.py:51` and existing call path `mcp_protocol.py:627/683` — no new tool class |

One correctness note for whoever implements this: `_mcp_tools_list` currently passes `exclude_tiers` but **never** passes `active_domain`, and `_DEFAULT_EXCLUDE_TIERS` (`tool.py:439`) differs from the MCP-hardcoded set (it adds `"mcp"`). Keep the MCP call explicit (don't switch to the default) so MCP-only tools — including a B-preferred `find_tools` with `tier="mcp"` — remain visible.


### [mcp-server-mechanics]

I have everything needed. Here is the full map.

---

# WriterAgent MCP server — code map

All paths absolute. Three files do the work: `plugin/mcp/server.py` (transport), `plugin/mcp/mcp_protocol.py` (JSON-RPC + execution), `plugin/mcp/__init__.py` (`McpModule` lifecycle/route wiring), with `plugin/mcp/mcp_state.py` (FSM), `plugin/mcp/routes.py` (route registry), `plugin/mcp/cors.py` (CORS/headers) supporting.

## (a) Initialize handshake + advertised capabilities

`_mcp_initialize` at **mcp_protocol.py:420-427**:
```python
def _mcp_initialize(self, params):
    client_version = params.get("protocolVersion", MCP_PROTOCOL_VERSION)
    return {
        "protocolVersion": client_version,
        "capabilities": {"tools": {"listChanged": False}, "resources": {"listChanged": False}, "prompts": {"listChanged": False}},
        "serverInfo": {"name": "WriterAgent MCP", "version": self.version},
        "instructions": ("WriterAgent MCP — AI document workspace. WORKFLOW: ...")
    }
```
- `listChanged` is hard-coded **False** for tools, resources, and prompts (line 424). This is what option B2 must flip.
- Protocol version advertised: `MCP_PROTOCOL_VERSION = "2025-11-25"` (**mcp_protocol.py:42**); accepted on the HTTP header are `{MCP_PROTOCOL_VERSION, "2024-11-05"}` (**:43**). Note initialize *echoes the client's* `protocolVersion` rather than forcing the server's.
- Session id is **minted after** a successful initialize, in `_handle_mcp` at **mcp_protocol.py:407-408**: `if is_initialize and status == 200: _mcp_session_id = str(uuid.uuid4())`. It is a single module-global `_mcp_session_id` (**:166**), not per-client. Every response sets `Mcp-Session-Id`/`Mcp-Protocol-Version` via `_send_mcp_response_headers` (**:63-68**).
- The `initialized`/`notifications/*` client notification has no handler; it arrives as a request with `id == None` and is dropped at **mcp_protocol.py:528-529** (`if req_id is None: return None`) → HTTP 202 (`_handle_mcp` **:400-404**).

## (b) tools/list and tools/call handlers

Method dispatch table — **mcp_protocol.py:531**:
```python
handler = {"initialize": ..., "ping": ..., "tools/list": self._mcp_tools_list, "tools/call": self._mcp_tools_call, "resources/list": ..., "prompts/list": ...}.get(method)
```
Unknown method → JSON-RPC `-32601` at **:535-536**. (`resources/list` and `prompts/list` return empty lists, **:445-449**.)

**tools/list** — `_mcp_tools_list` **mcp_protocol.py:432-443**:
```python
def _mcp_tools_list(self, params, document_url=None):
    def _get_doc():
        doc_svc = self.services.document
        if document_url:
            doc, _ = doc_svc.resolve_document_by_url(document_url)
            return doc
        return doc_svc.get_active_document()
    doc = self.queue_executor.execute(_get_doc, timeout=10.0)
    schemas = self.tool_registry.get_schemas("mcp", doc=doc, exclude_tiers=frozenset({"specialized", "specialized_control"}))
    return {"tools": schemas}
```
The exposed set is **already document-dependent**: it resolves the active doc (or `X-Document-URL`) on the main thread, then filters by doc type / UNO services via `ToolRegistry.get_schemas("mcp", doc=...)` (`plugin/framework/tool.py:624-639` → `get_tools` `:529-622`). So the list returned for the same client *changes* when the user switches Writer↔Calc↔Draw — but with `listChanged:False` the server never tells the client, so clients cache the initial list. This is the precise gap B2 closes.

**tools/call** — `_mcp_tools_call` **mcp_protocol.py:451-512**. Drives the FSM in `mcp_state.py`:
- Pops `document_url` out of `arguments` (an arg overrides the header, **:456-458**).
- Reads `is_long_running = getattr(tool, "long_running", False)` (**:460**).
- Runs the event loop (`next_state`, `mcp_state.py:89-146`): `REQUEST_RECEIVED → ParseRequestEffect + ResolveDocumentEffect → ExecuteToolEffect → TOOL_COMPLETED → StreamResponseEffect`.
- `ResolveDocumentEffect` is a no-op stub: it immediately emits `DOCUMENT_RESOLVED` with `doc_type:"writer"` and null context (**:481-485**) — real resolution happens later inside the execute methods, not in the FSM.
- `ExecuteToolEffect` branch (**:487-499**) picks the path: `is_long_running → _execute_long_running` else `_execute_with_backpressure`.
- Result is wrapped as MCP content at **:507**: `{"content":[{"type":"text","text": json.dumps(result)}], "isError": effect.is_error}`. `is_error` is set when the tool returns `{"status":"error"}` (`mcp_state.py:131`).
- Emits `mcp:request` / `mcp:result` on the event bus (**:479, :505**) for the sidebar/telemetry.

JSON-RPC error mapping for both is in `_process_jsonrpc` **:540-560**: `BusyError → 429 / -32000`, `TimeoutError → 504 / -32001`, `WriterAgentException/other → 500 / -32603`.

## (c) long_running / backpressure / per-document gate / sessions

**Backpressure** — global single-flight semaphore: `_tool_semaphore = threading.Semaphore(1)`, `_WAIT_TIMEOUT=5.0`, `_PROCESS_TIMEOUT=60.0` (**mcp_protocol.py:73-75**). `_execute_with_backpressure` **:564-576**:
```python
acquired = _tool_semaphore.acquire(timeout=_WAIT_TIMEOUT)
if not acquired:
    raise BusyError("LibreOffice is busy processing another tool call. ...")
try:
    return self.queue_executor.execute(self._execute_tool_on_main, tool_name, arguments, document_url, timeout=_PROCESS_TIMEOUT)
finally:
    _tool_semaphore.release()
```
So normal tools are serialized to **one at a time across the whole server** and run on the VCL main thread via `queue_executor`.

**long_running** — `_execute_long_running` **:578-633** *skips the semaphore* and runs the tool body on the HTTP worker thread; only context resolution (`_get_context`, **:586-602**) hops to the main thread. UNO inside such tools must use `execute_on_main_thread` itself (per the docstring, **:582-584**).

**Per-document mutation gate** — `_doc_gates: dict[str, threading.Lock]` guarded by `_doc_gates_guard` (**:79-80**). Key resolved by `_resolve_mcp_doc_key` **:83-103** (normalized URL → `doc.getURL()`/`RuntimeUID` → `_ACTIVE_DOCUMENT_SENTINEL` fallback, **:77**). `_get_document_mutation_gate` lazily creates per-key locks (**:106-114**). `_tool_needs_document_mutation_gate` **:117-123** gates only mutating tools: `tool.requires_document_lock(arguments)` falling back to `tool.detects_mutation()` (defs in `plugin/framework/tool.py:259, 251`). The `@contextmanager _document_mutation_gate(doc_key, enabled=...)` **:126-134** is entered in *both* execute paths (`_execute_long_running` **:625**, `_execute_tool_on_main` **:681**) so the two paths serialize against each other per-document; read-only tools pass `enabled=False`. Both paths stamp `result["_elapsed_ms"]` (**:631, :687**).

**Sessions** — minimal. Single module-global `_mcp_session_id` (**:166**), set post-initialize (**:407-408**), echoed on responses. `DELETE /mcp` (`handle_mcp_delete` **:228-234**) just 200s without clearing it. No per-session tool state, no client isolation.

**SSE** — `GET /mcp` (`handle_mcp_sse` **:214-226**) and legacy `GET /sse` (`handle_sse_stream` **:235-248**) open a keepalive-only stream (`_run_sse_keepalive_loop` **:250-283**) that writes `: keepalive` every 15s and watches for disconnect. **No server→client message is ever pushed on it today** — this is the channel B2 needs.

## (d) Supporting dynamic tool lists (notifications/tools/list_changed) for option B2

The transport substrate already exists; what's missing is (1) the capability flag, (2) an emit path, (3) a place to detect the change. Concretely:

1. **Flip the capability** — `mcp_protocol.py:424`: change `"tools": {"listChanged": False}` → `{"listChanged": True}`. (Leave resources/prompts False since those lists are empty.)

2. **Add a push mechanism on the SSE stream.** Today `_run_sse_keepalive_loop` (**:250-283**) only writes keepalives and has no registry of open streams. You need to (a) register each open `GET /mcp` SSE `handler.wfile` into a thread-safe set of subscribers when `handle_mcp_sse` runs (**:214-226**), removing it on disconnect in the loop's `finally` (**:282-283**); and (b) add a `broadcast_notification(method, params)` that writes a framed SSE `data: {jsonrpc:"2.0","method":"notifications/tools/list_changed"}\n\n` to each subscriber (guard writes with try/except for `BrokenPipeError` like the existing loop). MCP `notifications/*` are id-less JSON-RPC, so no response correlation is needed.

3. **Detect when the exposed set actually changes.** The exposed set is a pure function of the resolved document type and the registry contents (`_mcp_tools_list` → `get_schemas("mcp", doc=...)`). The cheapest correct trigger is the **active-document-changed / doc-type-changed event**. There is already an event bus (`self.event_bus`, **:189**; `services.events`) and the module subscribes to bus events elsewhere (`McpModule._on_config_changed` subscribes to `config:changed`, `__init__.py:90-91`). So:
   - Have `MCPProtocolHandler` subscribe to whatever doc-activation event the document service emits (the same signal the sidebar uses to re-render). On that event, compute the new tool-name set and compare to a cached last-sent set; if different, call `broadcast_notification("notifications/tools/list_changed")`.
   - Compare on the cheap summary, not full schemas: `tool_registry.get_tool_summaries(doc=...)` (`tool.py:641-644`) or just the sorted name list — avoids spurious notifications when only descriptions differ.
   - Edge cases to respect: the global single `_mcp_session_id` means you cannot target a specific client; broadcast is fine because a stale notification just triggers a harmless `tools/list` re-fetch. Also emit on registry mutation if tools can be (un)registered at runtime — today `_register_mcp_routes`/`_unregister_mcp_routes` (`__init__.py:192-225`) toggle the *MCP routes*, not individual tools, so doc-type change is the dominant trigger.

No new dependency or protocol-version bump is required: `2025-11-25` already supports `notifications/tools/list_changed`, and `tools/list` is re-fetched by the client on receipt — the server side is purely "advertise True + push the notification on the existing SSE channel."

## (e) Where a `find_tools` tool or a "direct mode" integrates; constraints

**A new `find_tools` tool** (server-side tool-search / progressive disclosure):
- Register it like any other tool in the registry so it flows through `get_schemas("mcp", ...)` (**mcp_protocol.py:442**) and executes through the normal `tools/call` → `_execute_with_backpressure` path. Give it `tier="core"` so it survives the `exclude_tiers={"specialized","specialized_control"}` filter at **:442**, and `doc_types=None`/`uno_services=None` so `get_tools.supports_doc` (`tool.py:548-570`) treats it as universal and it appears for every document type.
- It is read-only (no UNO mutation) → leave `detects_mutation()`/`requires_document_lock()` false so `_tool_needs_document_mutation_gate` (**:117-123**) returns False and it never takes a doc gate. It still passes through the global `_tool_semaphore`, which is fine for a fast lookup; if you want it to bypass even that, mark it `long_running=True` (then it runs on the HTTP worker via `_execute_long_running`, **:490-491**) — but it doesn't touch UNO so backpressure is cheap and simpler.
- Implementation can reuse `ToolRegistry.get_tool_summaries(**filters)` (`tool.py:641-644`) to return `{name, description, tier, intent}` for matches — exactly the catalogue shape a search/disclosure tool wants. This is the natural companion to B2: expose a tiny always-on toolset (`find_tools` + a generic `call`/direct executor) and let the model pull in the rest.

**A "direct mode"** (call a tool by name without it being in the advertised list):
- The executor already supports this: `tools/call` looks the tool up by `self.tool_registry.get(tool_name)` (**:459**), which is **not** filtered by tier/doc-type — only `tools/list` filters. So a direct-call entry point can dispatch to any registered tool today. You'd add either a wrapper tool whose argument is `{tool, args}` and which calls `_execute_with_backpressure`/`_execute_long_running` internally, or a new JSON-RPC method in the dispatch dict at **:531**. Reuse the existing `_debug_call_tool` (**:693-697**) as the reference shape — it already does name→backpressure execution.

**Constraints to honor for either:**
- **Localhost / auth.** There is no auth on `/mcp` itself — it relies on binding to `localhost` (default host `localhost`/port `8765`, `__init__.py:154`) and CORS. Only `/debug` enforces a localhost-IP check (`handle_debug_post` **:340-345**: blocks non-`127.0.0.1/::1/localhost`). A `find_tools`/direct-mode endpoint that can invoke arbitrary tools is as powerful as `tools/call`, so if you expose it as a *new HTTP route* (rather than a registered tool) you should replicate that localhost gate; if you expose it as a *registered tool* it inherits `/mcp`'s posture (no extra check) — prefer the tool route to avoid widening attack surface.
- **CORS / origin reflection.** `is_safe_origin` (`cors.py:41-51`) reflects only localhost origins (`_ORIGIN_RE` **:36**) plus configured extras; allowed request headers are fixed in `_BASE_ALLOW_HEADERS` (**:24-32**) — if direct mode needs a new request header, add it there or it'll fail preflight. Any new MCP response must go through `_send_mcp_response_headers` (**:63-68**) for the session/version headers.
- **Streaming HTTP.** Responses are single-shot JSON (`_handle_mcp` writes one body, **:410-416**); the only streaming surface is the keepalive SSE GET. A `find_tools` result is a normal JSON-RPC reply, no streaming needed. If direct-mode tools are long-running, route them through `_execute_long_running` (HTTP-worker thread) so they don't block the `_tool_semaphore`/main thread for `_PROCESS_TIMEOUT=60s`.
- **Thread safety.** Anything touching UNO must run on the main thread via `self.queue_executor.execute(...)` (as `_mcp_tools_list` does at **:440**). A pure-registry `find_tools` needs no main-thread hop; a direct-mode tool that mutates a document does and must keep the per-doc gate (`_tool_needs_document_mutation_gate`, **:117-123**) intact.

A natural B2 + (e) combination: register `find_tools` (and optionally a direct-call tool) as always-exposed `core` tools, flip `listChanged:True` at **mcp_protocol.py:424**, and push `notifications/tools/list_changed` over the already-open SSE stream whenever the resolved document type changes the output of `get_schemas("mcp", doc=...)`.


### [anthropic-tool-search]

I have all the authoritative documentation I need from the official Anthropic docs. Here is the precise, current explanation.

---

# Anthropic Tool Search Tool — Precise, Current Explanation

## (a) The problem it solves

Tool definitions (name, description, full JSON input schema, argument descriptions) are injected into the model's context **upfront**, before any work begins. This compounds badly as catalogs grow. Per Anthropic's docs, the Tool Search Tool addresses two coupled problems:

- **Context bloat:** A typical multi-server setup (GitHub, Slack, Sentry, Grafana, Splunk) can consume **~55K tokens in definitions** before Claude does anything; larger deployments reach 100K+. Tool search "typically reduces this by over 85%," loading only the 3–5 tools actually needed.
- **Tool-selection accuracy:** Selection accuracy "degrades significantly once you exceed 30–50 available tools." Surfacing a focused relevant subset on demand keeps accuracy high "even across thousands of tools." Anthropic's benchmark: Opus 4 improved 49% → 74%; Opus 4.5 improved 79.5% → 88.1% with tool search enabled.

It is an instance of the "just-in-time retrieval" pattern applied to the tool catalog itself.

## (b) The exact mechanism and API surface

**Two server-side search-tool variants** (you put one in your `tools` array; it is itself a tool):

| Type string | Query language |
|---|---|
| `tool_search_tool_regex_20251119` | Claude writes **Python `re.search()` regex** patterns, NOT natural language (e.g. `"(?i)slack"`, `"get_.*_data"`). Max query length **200 chars**. Case-sensitive by default. |
| `tool_search_tool_bm25_20251119` | Claude uses **natural-language** queries. |

Definition shape: `{"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"}`. This search tool itself must **never** be deferred.

**Marking tools deferred:** Add `"defer_loading": true` to a regular tool definition. Non-deferred tools (keep your 3–5 most-used) load immediately; deferred tools load only on discovery. Both variants search across **tool names, descriptions, argument names, and argument descriptions**.

**The flow** (per docs):
1. You include a tool-search tool plus all tool definitions, with `defer_loading: true` on the ones to hide.
2. Claude initially sees only the search tool + non-deferred tools.
3. When it needs more, Claude calls the search tool → emits a `server_tool_use` block.
4. The API returns the **3–5 most relevant** matches as a `tool_search_tool_result` block whose content is `{"type": "tool_search_tool_search_result", "tool_references": [{"type": "tool_reference", "tool_name": "..."}]}`.
5. Those `tool_reference` blocks are **automatically expanded into full tool definitions** by the API before Claude sees them — you don't handle expansion yourself, provided every referenced tool has a full definition in the top-level `tools` array.
6. Claude then emits a normal `tool_use` for the discovered tool.

**Internals / prompt-caching:** Deferred tools are excluded from the system-prompt prefix. On discovery, the API appends the `tool_reference` **inline in the conversation body** and expands it there; the prefix is untouched, so **prompt caching is preserved**. Expansion is applied across the whole conversation history, so a discovered tool is reusable on later turns without re-searching. `defer_loading` also composes with strict mode without grammar recompilation.

**Usage tracking:** `usage.server_tool_use.tool_search_requests`.

**Custom (client-side) search:** You can implement your own search (e.g. embeddings/semantic) by returning a standard `tool_result` whose content contains `{"type": "tool_reference", "tool_name": "..."}` blocks. Every referenced tool must still have a full definition with `defer_loading: true` in `tools`. (The `tool_search_tool_result` envelope is the internal server-side format; custom implementations use the plain `tool_result` format.)

**Key errors:** 400 "All tools have defer_loading set. At least one tool must be non-deferred."; 400 "Tool reference '…' has no corresponding tool definition." Runtime (200-status) error codes inside `tool_search_tool_result_error`: `too_many_requests`, `invalid_pattern`, `pattern_too_long`, `unavailable`. Also: tool search is **not compatible with tool-use examples**.

## (c) MCP interoperability

Yes — MCP tools can be deferred and searched, and it is **client/caller-driven**, configured in the API request (not something the MCP server declares). It works through the **MCP connector** (remote URL servers). In the `tools` array you add an `mcp_toolset` referencing the server, and set deferral via `default_config` (server-wide) and `configs` (per-tool overrides):

```json
{
  "type": "mcp_toolset",
  "mcp_server_name": "google-calendar-mcp",
  "default_config": { "enabled": false, "defer_loading": true },
  "configs": {
    "search_events": { "enabled": true, "defer_loading": false },
    "list_events":  { "enabled": true }
  }
}
```

`defer_loading` on a tool config = "tool description is not sent to the model initially," explicitly "Used with Tool search tool." Precedence: per-tool `configs` > `default_config` > system defaults (`enabled: true`, `defer_loading: false`). So you can defer an entire MCP server while keeping a few hot tools eager. This pattern is the headline use case ("MCP-powered systems with multiple servers (200+ tools)").

**Important version note:** the MCP connector here uses beta header `anthropic-beta: mcp-client-2025-11-20` (the older `mcp-client-2025-04-04`, which put config in `tool_configuration`/`allowed_tools` on the server definition, is **deprecated**). The connector supports remote HTTPS servers only (Streamable HTTP/SSE) — not local STDIO. For self-managed/local MCP clients, the SDK helpers (`mcpTools`, etc.) convert MCP tools to API tools, and you'd apply `defer_loading` on the resulting tool definitions yourself.

## (d) Model support, limits, status

**Beta header (Tool Search Tool feature):** `anthropic-beta: advanced-tool-use-2025-11-20` (SDK `betas=["advanced-tool-use-2025-11-20"]`).

> Caveat: the Anthropic engineering blog states this header. The dedicated tool-search-tool docs page shows code examples **without** the beta header (plain `client.messages.create`), whereas the MCP connector page consistently shows `mcp-client-2025-11-20`. There's some inconsistency in how prominently the beta header is presented across pages — treat `advanced-tool-use-2025-11-20` as the feature's beta gate but verify against the SDK version you use.

**Status:** **Beta** (introduced 2025-11-19/20, the `_20251119` type suffix). Not announced as GA in the sources I read. ZDR-eligible (the tool-search feature itself; note the MCP connector is **not** ZDR-eligible).

**Limits:**
- Max catalog size: **10,000 tools**.
- Search returns **3–5** tools per query.
- Regex pattern max length: **200 characters**.
- Bedrock: server-side tool search only via `InvokeModel` API, **not** the Converse API. Available on the Claude API and Claude Platform on AWS; Batches API supported.

**Model support (as listed on the docs page):** "Claude Fable 5, Claude Mythos 5, Claude Mythos Preview, Sonnet 4.0+, Opus 4.0+, Haiku 4.5+."

> Flag: those "Fable 5 / Mythos 5 / Mythos Preview" names are unfamiliar/likely newer-than-my-knowledge codenames appearing in the live docs, and the doc examples all use `model: "claude-opus-4-8"`. The named-tier list resolves in practice to Sonnet 4.0+, Opus 4.0+, and Haiku 4.5+ (plus the newer codenamed models). I'm surfacing the exact doc wording rather than normalizing it, since I can't independently confirm those product names.

---

## Things I could not fully resolve / version-dependent flags

- **Beta-header inconsistency** between the engineering blog (`advanced-tool-use-2025-11-20`) and the docs-page code samples (no header shown) — verify for your SDK version.
- **Model-name list** on the live docs ("Fable 5", "Mythos 5", "Mythos Preview") includes codenames I cannot verify; I reproduced them verbatim.
- **Beta vs GA:** sources indicate beta; I found no explicit GA announcement.
- I successfully fetched all primary sources below; nothing failed to load.

## Sources

- [Tool search tool — Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool) (primary: mechanism, type strings, `defer_loading`, response format, custom search, limits, model support, errors)
- [Introducing advanced tool use on the Claude Developer Platform — Anthropic Engineering](https://www.anthropic.com/engineering/advanced-tool-use) (problem framing, ~55K-token figure, benchmarks, `advanced-tool-use-2025-11-20` beta header, MCP per-server/per-tool defer)
- [MCP connector — Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/mcp-connector) (`mcp_toolset`, `default_config`/`configs`, per-tool `defer_loading`, precedence, `mcp-client-2025-11-20` beta header, client-driven config, client-side helpers)
- [Tool reference — Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-reference) (tool catalog / compatibility)


### [mcp-dynamic-tools]

I now have comprehensive, well-sourced material across all three topics, including the critical real-world nuance that the spec defines no prohibition on calling unadvertised tools, and that client support for `list_changed` is uneven in practice. Here is the synthesized research.

---

# MCP Dynamic Tool Lists, Unadvertised Tool Calls, and Large-Catalog Patterns

## (a) `notifications/tools/list_changed` — how it works, and which clients honor it

### What the spec says (authoritative)

Per the official MCP spec, **Tools** page ([modelcontextprotocol.io/specification/2025-11-25/server/tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)):

- A server that supports tools **MUST** declare the `tools` capability. The optional `listChanged` flag inside it signals dynamic updates:
  ```json
  { "capabilities": { "tools": { "listChanged": true } } }
  ```
  "`listChanged` indicates whether the server will emit notifications when the list of available tools changes."

- "When the list of available tools changes, servers that declared the `listChanged` capability **SHOULD** send a notification":
  ```json
  { "jsonrpc": "2.0", "method": "notifications/tools/list_changed" }
  ```
  Note this is a JSON-RPC **notification** (no `id`, no params, no response).

- The intended client behavior is shown in the spec's Message Flow diagram: `Server --) Client: tools/list_changed` → `Client -> Server: tools/list` → `Server --> Client: Updated tools`. The notification carries **no payload** — it is a hint to re-fetch; the client must issue a fresh `tools/list` (which is paginated) to learn the new set.

So the contract is: **server SHOULD notify; client SHOULD re-fetch.** Crucially, the spec does *not* make client re-fetching a MUST, and there is no negotiated client-side capability for "I will react to list_changed" in the base spec — which is exactly the interoperability gap below.

### Which clients actually honor it (this is the messy part)

Client support is **uneven and historically buggy**, even within Anthropic's own products. The community built a registry (`mcp-client-capabilities`) precisely because this can't be assumed — see PulseMCP's "Mind the MCP Client Capability Gap" (Dec 23, 2025): "Most MCP clients support only the most basic protocol features." ([pulsemcp.com](https://www.pulsemcp.com/posts/mcp-client-capabilities-gap)).

Concrete, sourced status:

- **Claude Code** — *partial, with documented gaps.* The v2.1.0 changelog claimed list_changed support, but issue [#13646](https://github.com/anthropics/claude-code/issues/13646) reports a decompile showing the Zod schema existed while `setNotificationHandler` was never wired up. The consolidated compliance issue [#31893](https://github.com/anthropics/claude-code/issues/31893) (closed "not planned", labeled stale) states it works **across prompt turns** (new tools appear next turn) but **not within the same turn** — a tool registered mid-turn fails with `Error: No such tool available`, plus startup race conditions for async registration. Sibling notifications (`prompts/list_changed`, `resources/list_changed`) were reported not implemented ([#4118](https://github.com/anthropics/claude-code/issues/4118), [#2722](https://github.com/anthropics/claude-code/issues/2722), [#4094](https://github.com/anthropics/claude-code/issues/4094)). Treat "supported" as "eventually re-fetches between turns," not "live."
- **Claude Desktop** — *reported non-compliant in at least one version.* Issue [#50339](https://github.com/anthropics/claude-code/issues/50339) ("Claude Desktop ignores notifications/tools/list_changed — spec non-compliance in directMcpHost (v1.3109.0)") and a feature request to refresh tools without restarting ([#39901](https://github.com/anthropics/claude-code/issues/39901)). Historically Claude Desktop required a restart to pick up tool changes.
- **ChatGPT (Apps SDK / MCP connectors)** — *not clearly documented as honoring `list_changed`.* OpenAI's Apps SDK docs describe the minimal server as "list tools / call tools" over SSE or streamable HTTP and say tools can be added/removed server-side, but I found **no OpenAI documentation confirming the client re-fetches on `notifications/tools/list_changed`** ([developers.openai.com/apps-sdk/concepts/mcp-server](https://developers.openai.com/apps-sdk/concepts/mcp-server)). Flag as **uncertain / likely not live-honored**; refresh behavior appears tied to connector reconnect rather than the notification.
- **Other clients (for context):** Vercel AI SDK had an open discussion to *add* support ([#8144](https://github.com/vercel/ai/discussions/8144)); Gemini CLI had an open feature request ([#13850](https://github.com/google-gemini/gemini-cli/issues/13850)); LibreChat had an enhancement request ([#7117](https://github.com/danny-avila/LibreChat/issues/7117)). I did **not** find authoritative confirmation for Cursor/VS Code/Cline/Windsurf in fetchable sources — the canonical place to check per-client is the `mcp-client-capabilities` registry referenced by PulseMCP, not vendor blogs.

**Bottom line for (a):** the protocol mechanism is simple and well-defined (declare `listChanged`, fire a payload-less notification, client re-fetches via paginated `tools/list`). But you cannot rely on clients reacting promptly — and especially not **mid-turn**. Design servers so they don't *depend* on the client noticing a change during an active tool-call loop.

---

## (b) Can a server handle `tools/call` for a tool never returned by `tools/list`?

**Short answer: The spec does not forbid it. "Unknown tool" is defined only as the error a server returns when it doesn't recognize a name — there is no rule that a callable tool *must* have appeared in `tools/list`.**

### What the spec actually says ([Tools §Error Handling](https://modelcontextprotocol.io/specification/2025-11-25/server/tools))

The spec distinguishes two error channels:

1. **Protocol Errors** — standard JSON-RPC errors, explicitly listing "**Unknown tools**" as an example, alongside malformed requests and server errors. The canonical example:
   ```json
   { "jsonrpc": "2.0", "id": 3,
     "error": { "code": -32602, "message": "Unknown tool: invalid_tool_name" } }
   ```
   `-32602` is the JSON-RPC "Invalid params" code. (The initial search-engine summary that asserted an error is "required" overstated it — the spec frames `-32602`/"Unknown tool" as an *example* of how a server reports a name it doesn't recognize, not as a prohibition on serving unadvertised names.)

2. **Tool Execution Errors** — returned in a *successful* result with `isError: true` (API failures, input validation, business logic).

What the spec **does not** state:
- It never says a tool must have been returned by `tools/list` to be callable.
- It never says the server **MUST** reject a name that wasn't advertised.
- `tools/list` is described as the **discovery** mechanism, not an allow-list / authorization boundary.

### Practical implication (and the real-world pattern)

Because `tools/list` is advertisement, **a server is free to accept `tools/call` for names it never listed** — the spec only obliges it to return an "Unknown tool" error for names it genuinely doesn't *implement*. Whether to serve a known-but-unadvertised name is the server's choice.

This is an established pattern: servers expose **hidden/private tools** by filtering them out of `tools/list` (e.g., FastMCP listing-filter middleware) while keeping them callable by clients that know the name ([smrati katiyar, Medium](https://medium.com/@smrati.katiyar/making-your-mcp-tools-private-3415dee1c56a)). The security corollary, noted in the same space, is that "hidden" ≠ "disabled": an unadvertised tool that the server still routes is callable by anyone who knows its name and schema, so hiding is **not** an access control ([dev.to: "tools/list is not enough"](https://dev.to/k08200/mcp-ci-gates-need-receipts-toolslist-is-not-enough-29o4)).

**Caveats / uncertainty:**
- This is what the *server* may do. The **client/model** side is the practical blocker: most clients only know about tools they've seen in `tools/list`, so the model won't *spontaneously* call an unlisted tool. The pattern works when something tells the client the name (a meta/gateway tool — see (c)).
- The spec also says tool names **SHOULD** be unique within a server and gives naming rules, but says nothing tying callability to prior listing.
- Security guidance (Tools §Security) says servers **MUST** validate inputs and implement access controls — so "unadvertised but callable" should still be gated by real authorization, not obscurity.

---

## (c) Patterns for exposing LARGE tool catalogs

The core problem (well-documented): one-tool-per-operation "floods the context," inflates token cost, and degrades tool-selection accuracy past ~50–100 tools. The dominant answer is **progressive disclosure via meta-tools** (a.k.a. gateway/discovery tools), which directly exploits the (b) insight: only a handful of tools are advertised; the rest are reached by name through an `execute`-style meta-tool.

### Real examples / prior art

1. **fastmcp-gateway** (Ultrathink-Solutions, built on FastMCP) — [github.com/Ultrathink-Solutions/fastmcp-gateway](https://github.com/Ultrathink-Solutions/fastmcp-gateway). Aggregates many upstream MCP servers and exposes exactly **four meta-tools**:
   - `discover_tools()` — browse domains and tool inventories (supports `domain=...` scoping and `format="signatures"`)
   - `get_tool_schema(name)` — fetch a single tool's JSON Schema on demand (fuzzy matching)
   - `execute_tool(...)` — route the call to the correct upstream
   - `refresh_registry()` — re-query upstreams for changes
   
   Collision handling: identically-named upstream tools are auto-prefixed by domain (`apollo_search`, `hubspot_search`) — a **namespacing** pattern. Stated value prop: "the LLM starts with 4 meta-tools and loads individual schemas on demand." (Note: the repo gives no concrete token benchmark; the big numbers below come from other sources.)

2. **MCP SEP #1888 — "Progressive Disclosure for Typed Library Discovery & Introspection"** ([modelcontextprotocol#1888](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1888)). A proposal to **standardize** this. Status: **Draft/Open** (PR: TBD, Sponsor: TBD — not accepted/merged). Mechanism: a single `<library>.searchTools` meta-tool with `mode: "operations"` (filter by resourceType/action/scope/riskLevel) and `mode: "types"` (fetch machine-readable type defs). Reference impl "ProDisco" for Kubernetes. Motivation quote: instead of registering `listPods`, `createDeployment`, etc., "servers expose a single standardized meta-tool." Treat this as **direction-of-travel, not yet spec.**

3. **The Meta-Tool Pattern / "Bounded Context Packs"** (Synaptic Labs) — [blog.synapticlabs.ai](https://blog.synapticlabs.ai/bounded-context-packs-meta-tool-pattern). Two registered tools (a discovery tool + an execution tool) front many capabilities: "Instead of loading 29 tool schemas at startup, you load a discovery tool and an execution tool."

4. **Speakeasy** has two relevant writeups: "Dynamic tool discovery in MCP" ([speakeasy.com/mcp/tool-design/dynamic-tool-discovery](https://www.speakeasy.com/mcp/tool-design/dynamic-tool-discovery)) and "Comparing Progressive Discovery and Semantic Search for Powering Dynamic MCP" ([speakeasy.com/blog/100x-token-reduction-dynamic-toolsets](https://www.speakeasy.com/blog/100x-token-reduction-dynamic-toolsets)). The token math cited in search results: a static catalog of hundreds of tools can consume ~**405,000 tokens before any work**, whereas a meta-tool approach is ~600 tokens for the two meta-schemas + ~150 tokens per fetched tool (≈1,050 vs ≈8,250 tokens for a 3-tool task). This is the headline argument for progressive disclosure, and contrasts it with an alternative: **semantic search** over the tool catalog.

5. **Obot AI — "MCP Tool Discovery"** ([obot.ai/resources/learning-center/mcp-tool-discovery](https://obot.ai/resources/learning-center/mcp-tool-discovery)) surveys the tooling/gateway landscape (filtering, discovery layers). Good orientation source for "5 tools to know."

### Taxonomy of patterns observed

- **Tool filtering / curation** — advertise a subset in `tools/list`; keep the rest hidden-but-callable (FastMCP listing middleware; ties directly to (b)).
- **Namespacing / domain prefixes** — disambiguate collisions across aggregated servers (`domain_toolname`); also the spec's own naming rules allow dots (`admin.tools.list`).
- **Meta / gateway / discovery tools (progressive disclosure)** — the dominant pattern: 2–4 stable tools (`discover` / `get_schema` / `execute`, optionally `refresh`) that load schemas on demand. fastmcp-gateway, SEP #1888, Synaptic Labs.
- **Semantic search over tools** — embed tool descriptions; return the top-k relevant tools per query rather than the whole catalog (Speakeasy's alternative to enumerate-then-disclose).
- **Dynamic toolsets via `list_changed`** — swap the advertised set per state/context and fire `notifications/tools/list_changed` — *but* this inherits all the client-support caveats from (a), so the meta-tool approach is generally more robust because it doesn't depend on the client reacting to notifications.

---

## How the three topics connect (the load-bearing takeaway)

For a server with a large catalog, the **most robust** design today combines (b) + (c) and avoids leaning on (a): advertise a few **meta-tools** in `tools/list`, keep the long tail **unadvertised but callable by name** (the spec permits this — "Unknown tool" is only required for names you don't implement), and let an `execute_tool`/`searchTools` meta-tool bridge the model to those names. `notifications/tools/list_changed` is the *spec-blessed* way to mutate the visible set, but real clients honor it inconsistently — Claude Code only between turns (and historically not at all per [#13646](https://github.com/anthropics/claude-code/issues/13646)), Claude Desktop reportedly ignored it ([#50339](https://github.com/anthropics/claude-code/issues/50339)), and ChatGPT's behavior is undocumented — so don't make correctness depend on it, especially mid-turn.

### Uncertainty flags
- I could **not** find authoritative, fetchable confirmation of `list_changed` handling for ChatGPT, Cursor, VS Code, Cline, or Windsurf. The PulseMCP `mcp-client-capabilities` registry is the right primary source to check per-client; I did not fetch its raw data.
- Claude Code/Desktop statuses come from **GitHub issues** (some closed "not planned"/stale), not formal docs — version-dependent and may have changed after the issue dates.
- SEP #1888 is a **draft proposal**, not adopted spec.
- The Speakeasy token figures are illustrative numbers from that vendor, not independently verified.

### Sources
- [MCP spec — Tools (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [PulseMCP — Mind the MCP Client Capability Gap (Dec 23, 2025)](https://www.pulsemcp.com/posts/mcp-client-capabilities-gap)
- [Claude Code #31893 — MCP spec compliance (list_changed/progress/sampling/async)](https://github.com/anthropics/claude-code/issues/31893)
- [Claude Code #13646 — tool list not refreshed on list_changed](https://github.com/anthropics/claude-code/issues/13646)
- [Claude Code #4118 — capture MCP tools-changed notifications](https://github.com/anthropics/claude-code/issues/4118)
- [Claude Code #50339 — Claude Desktop ignores list_changed](https://github.com/anthropics/claude-code/issues/50339)
- [Claude Code #39901 — refresh MCP tools without restart](https://github.com/anthropics/claude-code/issues/39901)
- [OpenAI Apps SDK — MCP server concepts](https://developers.openai.com/apps-sdk/concepts/mcp-server)
- [Vercel AI #8144](https://github.com/vercel/ai/discussions/8144), [Gemini CLI #13850](https://github.com/google-gemini/gemini-cli/issues/13850), [LibreChat #7117](https://github.com/danny-avila/LibreChat/issues/7117)
- [Making your MCP tools private (hidden-but-callable) — Medium](https://medium.com/@smrati.katiyar/making-your-mcp-tools-private-3415dee1c56a)
- [MCP CI gates need receipts: tools/list is not enough — dev.to](https://dev.to/k08200/mcp-ci-gates-need-receipts-toolslist-is-not-enough-29o4)
- [fastmcp-gateway](https://github.com/Ultrathink-Solutions/fastmcp-gateway)
- [MCP SEP #1888 — Progressive Disclosure](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1888)
- [Synaptic Labs — The Meta-Tool Pattern](https://blog.synapticlabs.ai/bounded-context-packs-meta-tool-pattern)
- [Speakeasy — Dynamic tool discovery](https://www.speakeasy.com/mcp/tool-design/dynamic-tool-discovery) · [Speakeasy — Progressive Discovery vs Semantic Search](https://www.speakeasy.com/blog/100x-token-reduction-dynamic-toolsets)
- [Obot AI — MCP Tool Discovery](https://obot.ai/resources/learning-center/mcp-tool-discovery/)
