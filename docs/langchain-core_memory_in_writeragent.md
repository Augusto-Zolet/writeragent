---
name: LangChain-core memory in WriterAgent
overview: Historical plan to integrate langchain-core conversation memory. Most items are superseded by ChatSession + history_db.py (2026-06). Remaining work is summarization, Hermes-style profile injection, and RAG — not a langchain-core dependency.
todos:
  - id: wrap-llmclient-langchain-model
    content: "(Optional) WriterAgentLangChainModel — only if adopting langchain-core for other reasons."
    status: cancelled
  - id: add-inmemory-history
    content: ChatSession + SQLite3History / JSONHistory fallback — shipped.
    status: completed
  - id: persist-history-sqlite
    content: writeragent_history.db keyed by WriterAgentSessionID — shipped.
    status: completed
  - id: add-summarizing-memory
    content: Summarize oldest turns when history approaches context limits (no LangChain required).
    status: pending
  - id: isolate-smolagents-subagent
    content: web_research + librarian_onboarding sub-agents; final answer only in main history — shipped.
    status: completed
  - id: inject-user-profile-main-chat
    content: Inject USER.md into main chat system prompt (librarian already does for onboarding).
    status: pending
isProject: false
---

## Status (2026-06)

**You already handle chat history.** The sidebar uses [`ChatSession`](../plugin/chatbot/panel.py) backed by [`SQLite3History`](../plugin/chatbot/history_db.py) (stdlib `sqlite3`, JSON fallback). Sessions are keyed by `WriterAgentSessionID` on the document ([`panel_factory.py`](../plugin/chatbot/panel_factory.py)). Document excerpt (`[DOCUMENT CONTENT]`) is refreshed each send and kept **separate** from turn history — the same separation this plan wanted via LangChain variables.

**LangChain-core is not a dependency** (`pyproject.toml` has no `langchain-core`). The custom [`tool_loop.py`](../plugin/chatbot/tool_loop.py) + [`LlmClient`](../plugin/framework/client/llm_client.py) stack is the production path.

**What this doc is now:** reference for the original LangChain vs smolagents analysis, plus **remaining gaps** that do not require LangChain.

| Original todo | Today |
|---------------|-------|
| In-memory history | `ChatSession.messages` |
| Persistent SQLite history | `writeragent_history.db` |
| RunnableWithMessageHistory | Manual `session.add_*` + `get_messages()` |
| smolagents isolation | `web_research`, `librarian_onboarding` |
| Long-term user memory | `upsert_memory` → `USER.md` JSON; **main chat does not auto-inject** (librarian does) |
| Summarizing memory | **Not implemented** |
| RAG / corpus embeddings index | **Not implemented** — see [embeddings.md](embeddings.md) (cross-doc find, not in-doc excerpt) |

Broader phased plan (embedding client, RAG, deprioritized LangChain agent): [langchain-plan.md](langchain-plan.md). Embeddings detail: [embeddings.md](embeddings.md).

---

## LangChain vs smolagents memory

### LangChain-core memory model

- **Message-centric design**: LangChain represents history as a list of `BaseMessage` objects (system, human, AI, tool). Memory is usually wired via `RunnableWithMessageHistory`, which automatically:
  - Reads past messages from a `BaseChatMessageHistory` store keyed by a `session_id`.
  - Appends the new human/AI messages after each run.
- **Pluggable history backends**: `BaseChatMessageHistory` has multiple implementations (in-memory, file, SQL/SQLite, custom). This makes it easy to start with an in-process buffer and later persist to disk without changing the agent logic.
- **Buffer vs summary**: Simple setups use buffer-style memory (keep all turns). For long chats, a summarizing memory periodically compresses older messages into a short summary message to stay within context limits.

### Smolagents memory model

- **Step trace, not chat memory**: Smolagents’ `ToolCallingAgent` tracks an internal list of `ActionStep` objects (thought → tool call → observation) for a single agent run. This is great for debugging and reasoning within that run, but it:
  - Is not designed as a general-purpose chat history API.
  - Does not provide pluggable storage or persistent sessions across restarts.
- **Best use in WriterAgent**: Keep smolagents for self-contained sub-agents (like your `web_research` tool) where the agent’s internal step list is sufficient and short-lived.

### Conclusion for WriterAgent (updated)

- **Do not adopt LangChain-core solely for chat history** — `ChatSession` + `history_db.py` already match the intended behavior.
- **Keep smolagents** for web research and librarian onboarding; feed only the **final** sub-agent reply into main history.
- **Next memory work without LangChain:**
  1. **Inject `USER.md`** into the main chat system prompt every send (Hermes read path).
  2. **Summarize** old sidebar turns when total history size threatens context limits.
  3. **Embeddings / corpus index** — outer document_research semantic find (locators only, no FTS double-cache) — see [embeddings.md](embeddings.md).
  4. Optional **background reviewer** to write `USER.md` without expanding the main tool schema ([agent-memory-and-skills.md](agent-memory-and-skills.md)).

---

## Integration design for WriterAgent (historical)

The sections below describe the **original LangChain-first plan**. Steps 1–4 and 6 are largely **done or obsolete**; step 5 (summarization) and profile injection remain relevant with native code.

### 1. Wrap `LlmClient` in a LangChain chat model — **optional / deprioritized**

- **File**: `core/api.py` (path outdated; would be `plugin/framework/client/llm_client.py`).
- **Action**: Only needed if you want LangChain Runnable chains. Otherwise keep `LlmClient` as-is.

### 2. Introduce in-memory, per-document chat history — **DONE**

- Implemented as `ChatSession` + `history_db`, not `RunnableWithMessageHistory`.

### 3. Wire memory into the chat sidebar and menu — **DONE**

- `tool_loop.py` / `send_handlers.py` use `self.session`; document context via `set_system_context`.

### 4. Persistent history across LibreOffice restarts — **DONE**

- `SQLite3History` at `{config_dir}/writeragent_history.db`.

### 5. Summarizing memory when context is large — **still TODO**

- **Goal**: Avoid hitting model context limits in very long chats (history + tools + document excerpt).
- **Action (native, no LangChain):**
  - Track approximate char/token budget for `session.messages` (respect `chat_context_length` from model metadata where available).
  - When over threshold, run one summarizer call via existing `LlmClient` over the oldest portion of history.
  - Replace those messages with one summary message; persist through `history_db`.
  - Optional settings: `memory_strategy` (`buffer` | `summary`), `max_memory_tokens`.

### 6. Keep smolagents usage isolated — **DONE**

- Web research and librarian return a single assistant-visible result; step traces stay inside the sub-agent.

### 7. Configuration and UX

- **Already have:** per-document session id, history persistence, clear-history UX as wired in the panel.
- **Still useful:** `memory_strategy` / summarization thresholds; injection toggle for `USER.md` in main chat (not the same as chat *history*).
