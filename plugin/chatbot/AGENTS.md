# Chatbot / sidebar

Root invariants still apply (`self.ctx`, pure FSM in `service.next_state`,
`StreamQueueKind`, stream-on-worker / drain-on-UI). This file is only
the area gotchas.

## Entry points

- Sidebar factory / panel / document resolve: `panel_factory.py`, `panel.py`
- Tool loop / chat FSM: `tool_loop.py`, `tool_loop_state.py`
- Smol / librarian ReAct (separate runtime; shares `LlmClient`): `smol_agent.py`
- Dialogs / settings: `dialogs.py`, `dialog_views.py`, `settings_dialog.py`
- Memory (experimental): `memory.py` — `MEMORY_GUIDANCE` is in `plugin/framework/prompts.py`

Topic docs: [docs/chat-sidebar-implementation.md](../../docs/chat-sidebar-implementation.md),
[docs/chat-smol-tool-architecture.md](../../docs/chat-smol-tool-architecture.md),
[docs/chat-llm-hacks.md](../../docs/chat-llm-hacks.md),
[docs/framework-streaming-and-threading.md](../../docs/framework-streaming-and-threading.md),
[docs/framework-uno-dialogs.md](../../docs/framework-uno-dialogs.md).

## Sharp edges

- Resolve the document from the **frame only** (`frame.getController().getModel()` in `panel`).
- For Stop / cancel, use **`resolve_stop_checker()`** — not a panel boolean alone.
- Load XDL with `DialogProvider` and the extension `base_url` (see `dialogs` module doc). Settings UI is in `dialog_views`.
- Do **not** merge smol/librarian with the main chat FSM. Smol must use `WriterAgentSmolModel` → `LlmClient.request_with_tools` — no second HTTP client.
- In tests, resolve tools with `plugin.main.get_tools().get("tool_name")`.
