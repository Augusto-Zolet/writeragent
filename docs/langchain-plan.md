# Langchain & smolagents Integration Plan for WriterAgent

This document outlines a phased development plan to integrate `langchain-core` and adapt code from `smolagents` into WriterAgent, starting with basic conversation history and progressively adding more advanced memory, tools, and agentic features.

> **Status (2026-06):** Most of **Phase 1–2** and **smolagents sub-agent isolation** are **already shipped** without `langchain-core`. See [What is already implemented](#what-is-already-implemented-2026-06) and [What is still worth doing](#what-is-still-worth-doing-next). Full LangChain wiring is **optional**, not a prerequisite for the remaining roadmap.

## Goal Description
Enhance WriterAgent's AI capabilities by replacing manual prompt construction with `langchain-core`'s robust memory and agent abstractions, while vendoring and adapting secure, zero-dependency code from `smolagents`. This will allow the AI to "remember" past interactions, provide a seamless chat experience, and eventually perform complex multi-step document operations autonomously.

---

## What is already implemented (2026-06)

| Planned item | Shipped replacement | Entry points |
|--------------|---------------------|--------------|
| In-memory + persistent chat history | `ChatSession` + `SQLite3History` / `JSONHistory` fallback | [`plugin/chatbot/panel.py`](../plugin/chatbot/panel.py), [`plugin/chatbot/history_db.py`](../plugin/chatbot/history_db.py) |
| Session keyed by document | `WriterAgentSessionID` on document model (URL hash fallback) | [`plugin/chatbot/panel_factory.py`](../plugin/chatbot/panel_factory.py) |
| Document context per send (separate from history) | `get_document_context_for_chat` + `session.set_system_context` | [`plugin/chatbot/tool_loop.py`](../plugin/chatbot/tool_loop.py), [`plugin/doc/document_helpers.py`](../plugin/doc/document_helpers.py) |
| Custom tool-calling loop (not LangChain `AgentExecutor`) | `ToolCallingMixin` / `tool_loop.py` + `LlmClient` | [`plugin/chatbot/tool_loop.py`](../plugin/chatbot/tool_loop.py) |
| Smolagents sub-agents (web research, librarian) | `web_research`, `librarian_onboarding` tools; final answer only in main history | [`plugin/chatbot/web_research.py`](../plugin/chatbot/web_research.py), [`plugin/chatbot/librarian.py`](../plugin/chatbot/librarian.py) |
| Long-term user profile memory (partial) | `upsert_memory` → JSON in `USER.md`; librarian injects profile | [`plugin/chatbot/memory.py`](../plugin/chatbot/memory.py) |
| Scientific Python / NumPy (out-of-process) | Warm venv worker (`run_venv_python_script`, `=PYTHON()`) | [enabling_numpy_in_libreoffice.md](enabling_numpy_in_libreoffice.md) |

**Not in `pyproject.toml`:** `langchain-core` — the sidebar does not depend on it today.

---

## What is still worth doing (next)

Prioritized by leverage vs. complexity. **Do not** re-implement Phases 1–2 via LangChain unless you explicitly want that dependency.

| Priority | Item | Why it matters | Suggested approach |
|----------|------|----------------|-------------------|
| **1** | **Inject `USER.md` into main chat** (Hermes-style read path) | Model sees prefs without `upsert_memory` / `read` calls; librarian already injects for onboarding only | Append `[USER PROFILE]` block in `get_chat_system_prompt_for_document` or `set_system_context`; keep `upsert_memory` for writes |
| **2** | **Chat history summarization** (old Phase 3) | Very long sidebar sessions can exceed model context even when document excerpt is capped at 8k | Token/char budget on `session.messages`; when over threshold, one summarizer LLM call replaces oldest turns with a single system/assistant summary message (persist via `history_db`) |
| **3** | **Embedding HTTP client** (old Phase 4, inference half) | Same providers as chat (OpenRouter / Together / Ollama); no new pip deps in LO | Small module next to `LlmClient`; optional `embedding_model` config key (mirror `image_model`) |
| **4** | **Document RAG** (old Phase 4, retrieval half) | 8k-char excerpt misses distant sections in long docs | Chunking + vector index — venv + `sqlite-vec` when configured; host **Cython** top-k when not ([vector-search-design.md](vector-search-design.md), [cython-extension.md](cython-extension.md)) |
| **5** | **Hybrid keyword + vector search** | Embeddings miss exact tokens (SKUs, acronyms) | SQLite FTS5 on host; fuse with vector ranks (RRF) in venv worker or Cython/stdlib fallback |
| **6** | **Background memory reviewer** | Passive “should we save this?” without burdening main tool loop | Optional second LLM pass after reply (Hermes pattern); uses `MemoryStore` in code, not extra main-chat tools |
| **7** | **Skills tools** | Procedures on disk; guidance exists in constants | Register [`plugin/chatbot/skills.py`](../plugin/chatbot/skills.py) when ready; optional index injection like memory |
| **Low** | **Full `langchain-core` integration** | Runnable chains, community vendoring | Only if you want LangChain ecosystem interop; duplicates working `ChatSession` + `tool_loop` |

**Explicitly deprioritized:** Replacing `tool_loop.py` with LangChain `create_tool_calling_agent` / `AgentExecutor` — current FSM, streaming, and UNO drain are tightly coupled to the custom loop.

---

## Proposed Changes

### Phase 1: Foundation & Short-Term Memory — **DONE (without LangChain)**
**Objective**: Introduce `langchain-core` and implement basic `ConversationBufferMemory` for the current session's chat.

> **Superseded:** `ChatSession` + `history_db.py` fulfill this phase. Skip LangChain `ConversationBufferMemory` unless you adopt `langchain-core` for other reasons.

- **Dependency Management**: 
  - Add `langchain-core` (and potentially `langchain` or specific provider packages) to the project requirements.
  - Ensure compatibility with LibreOffice's bundled Python environment.
- **Refactor [core/api.py](file:///home/keithcu/Desktop/Python/writeragent/core/api.py)**:
  - Implement a custom LangChain `BaseChatModel` wrapper (`WriterAgentLangChainModel`) around the existing `LlmClient`. This avoids the bloat of native provider packages (like `langchain-openai` which brings heavy dependencies like `httpx`) and retains our LibreOffice-optimized streaming loop, connection pooling, and error mapping.
  - Introduce `ConversationBufferMemory` to automatically manage the message history.
- **Update `chat_panel.py`**:
  - Instead of rebuilding the context string manually via `get_document_context_for_chat` with every message, inject the document state as a dynamic system prompt or context variable within a LangChain `Runnable` or `Chain`.

### Phase 2: Persistent Conversation History — **DONE**
**Objective**: Allow chats to persist across LibreOffice restarts.

> **Shipped:** `writeragent_history.db` (SQLite) with per-`session_id` rows; JSON fallback when `sqlite3` unavailable. Clear via session API / UI wiring as implemented in the panel.

- **Storage Mechanism**:
  - Implement a local storage solution (e.g., a simple JSON file per document URL under `~/.config/libreoffice/4/user/config/writeragent_chat_history/` or an **SQLite database** — Python’s `sqlite3` is stdlib on all major OSes, so no extra dependency).
  - Use LangChain's `BaseChatMessageHistory` interface (e.g., `FileChatMessageHistory` or a custom implementation) to load and save messages.
- **Session Management**:
  - Tie conversation histories to document URLs (`doc.getURL()`).
  - Add a "Clear History" button to the chat sidebar.

### Phase 3: Token Management & Summarization Memory
**Objective**: Prevent the conversation history from exceeding the LLM's context window during long sessions.

- **Summarization**:
  - Replace `ConversationBufferMemory` with `ConversationSummaryBufferMemory`.
  - Configure a background LLM call to summarize older messages when the token count reaches a configured threshold (e.g., 80% of `chat_context_length`).
- **Config Updates**:
  - Add settings for `memory_strategy` (Buffer vs. Summary) and `max_memory_tokens`.(

### Phase 4: Long-Term Document Memory (RAG) — **NEXT (see vector-search-design.md)**
**Objective**: Enable the AI to recall specific edits, user preferences, or distant sections of a very large document.

> **2026-06 decision:** Run **vector math and `sqlite-vec` in the user venv subprocess** (same bridge as `run_venv_python_script`), not in LibreOffice’s embedded interpreter. Host process keeps **stdlib SQLite** for chunk metadata / FTS5 and calls the **embedding API** over HTTP. Details: [vector-search-design.md § Recommended stack](vector-search-design.md#recommended-stack-2026-06). Vendoring `sqlite-vec` into the OXT is **not** recommended (platform wheels, `enable_load_extension` gaps on macOS, SQLite version coupling).

- **Vector Store — tiered**:
  - **With venv (recommended):** NumPy batch dot products and/or **`pip install sqlite-vec`** inside the user venv; index file lives under the config dir next to `writeragent_history.db`.
  - **No venv — host Cython (available):** streaming top-k cosine/dot-product over a binary float32 sidecar — same contrib wheel matrix as audio / `writeragent_vec` ([cython-extension.md](cython-extension.md)). No NumPy in LO; stdlib Python fallback when the tagged `.so` is missing.
  - **No venv — last resort:** pure-Python `struct` loop (slow beyond ~1k chunks).
  - **Do not** import NumPy or load `sqlite-vec` in-process in LibreOffice — ABI and extension-loading constraints are documented in [enabling_numpy_in_libreoffice.md](enabling_numpy_in_libreoffice.md).
  - **Optional — in-memory ANN:** `hnsw-lite` in the venv only when the working set is a bounded “recent N days” subset; persist vectors in sqlite-vec or binary+JSON, rebuild graph on load.
- **Embeddings**: Prefer **embedding APIs from the same providers** WriterAgent already uses, so RAG works with no extra dependencies and the same credentials:
  - **OpenRouter**: `POST https://openrouter.ai/api/v1/embeddings` with the same API key as chat; `model` selects the embedding model (list via models API).
  - **Together AI**: `POST {endpoint}/embeddings` (e.g. `https://api.together.xyz/v1/embeddings`), OpenAI-compatible; same API key; models include BGE, M2-BERT (2k/8k/32k context).
  - **Ollama**: `POST {ollama_base}/api/embed` (e.g. `http://localhost:11434/api/embed`); no key; `model` e.g. `nomic-embed-text`, `embeddinggemma`, `all-minilm`.
- Implement a small **embedding client** that, given current `get_api_config(ctx)` (or equivalent) and an optional `embedding_model` config key, dispatches to the correct URL and payload (OpenRouter vs Together vs Ollama) and returns vectors. The vendored vector store accepts this as the embedding callable. **Fallback**: a small local embedder (e.g. sentence-transformers in venv) for offline use when no embedding API is configured.
- **Retrieval Augmented Generation**:
  - Build a retriever on top of the vendored store (same interface as LangChain’s `as_retriever()`: take a query, return top-k documents). Inject retrieved snippets into the chat prompt so the AI can answer about distant document parts.

#### Embedding APIs from existing providers

Many embedding models are available through the same gateways WriterAgent already uses for chat. Using them for Phase 4 RAG avoids extra dependencies and reuses endpoint + API key.

- **OpenRouter**
  - Endpoint: `POST https://openrouter.ai/api/v1/embeddings`.
  - Same API key as chat. Request: `model` (embedding model id), `input` (string or array of strings).
  - Optional: `dimensions`, `encoding_format`, `input_type`, `provider`.
  - Embedding models are listed via OpenRouter's models API.
- **Together AI**
  - Endpoint: `POST https://api.together.xyz/v1/embeddings` (OpenAI-compatible).
  - Same API key as chat.
  - Models: e.g. BAAI/bge-large-en-v1.5, BAAI/bge-base-en-v1.5, WhereIsAI/UAE-Large-V1, togethercomputer/m2-bert-80M-8k-retrieval (and 2k/32k).
  - When the user's config endpoint is Together's base URL, use `endpoint + "/embeddings"` with the same key.
- **Ollama**
  - Endpoint: `POST {base}/api/embed` (e.g. `http://localhost:11434/api/embed`).
  - No API key. Body: `model`, `input`; optional `truncate`, `dimensions`, `keep_alive`.
  - Recommended models: `all-minilm`, `nomic-embed-text`, `embeddinggemma`.
  - Same host as chat when Ollama is used locally; only path and payload differ.
- **Config**
  - Reuse existing endpoint and API key from `get_api_config(ctx)` where applicable.
  - Add an optional **embedding model** setting (e.g. `embedding_model` and `embedding_model_lru`), analogous to `image_model` / `image_model_lru`, so the user can choose the embedding model per provider.
  - Default behavior: when the configured endpoint is OpenRouter, Together, or Ollama, use the embedding API above; otherwise fall back to a local embedder if available.
- **Local / offline**
  - Keep the existing "small local embedder" option (e.g. sentence-transformers in a venv) for users without an embedding API or for offline use.

#### Persistence for the Vector Store

**Persistence options (stdlib only, no NumPy):**

- **JSON only**: Simple and human-readable; good for small stores (hundreds of chunks). For large stores, file size and load/save time grow quickly. **Use for**: MVP or when document chunks are limited.
- **Binary vectors + JSON (recommended, stdlib only)**: **Vectors**: one file, e.g. header `[n, dim]` (2 × uint32), then `n` × `dim` × 4 bytes (float32 via `struct.pack('<f', x)`). **Text/metadata**: separate JSON keyed by id. Allows **streaming search**: read the vector file sequentially, unpack with `struct.unpack`, compute cosine in pure Python, maintain top-k heap — no need to load the full dataset into RAM. Optional **offset index** (id → byte offset) for "get by id".

**Index vs full load**: With an **in-memory** store we load the whole dataset (or subset) into RAM and build the index at load time. For a **year of conversations** we avoid that by **streaming search**: store vectors in a binary file; on query, read sequentially, compute similarity (pure Python or NumPy when available), keep a running top-k heap — memory O(k), never load all data. Pure-Python similarity over many vectors will be slow; when we allow a system/venv NumPy dependency, use it for these calculations. Optional offset index (id → byte offset) for random access. Support **two modes**: (1) **Streaming** for large stores (binary file + JSON text/metadata); (2) **In-memory** for "recent only" (load subset into dict or vendored HNSW).

**Libraries/code to grab**: (1) **langchain_core.vectorstores.in_memory**: dump/load pattern; replace body with our binary+JSON and optional streaming. (2) **hnsw-lite**: copy HNSW graph logic, replace distance with pure-Python cosine for optional in-memory ANN without NumPy. (3) **langchain_community.vectorstores.sklearn**: serializer pattern `save(data)` / `load()` / `extension()`; implement `BinaryVectorSerializer` (struct + JSON).


### Phase 5: Agentic Workflows & Multi-Step Reasoning
**Objective**: Transition from a simple "Chat + Tools" model to autonomous problem solving.

- **Agent Orchestration**:
  - Use LangChain's `create_tool_calling_agent` and `AgentExecutor` to replace the custom tool execution loop in `chat_panel.py`.
  - Allow the agent to plan multi-step tasks (e.g., "Analyze this table, find errors, and format the erroneous cells red").
- **Human-in-the-Loop**:
  - Implement LangChain callbacks to pause execution and ask the user for confirmation before applying destructive changes to the document.

## Note: SQLite ships with Python

**`sqlite3` is part of the Python standard library** on all major OSes (Windows, macOS, Linux) in normal CPython builds — no `pip install` required. That opens several storage options without adding dependencies:

- **Phase 2 (persistent chat history)**: SQLite is a natural fit for conversation history (e.g. one table per document URL, or a single DB with a doc key). No extra dependency.
- **Phase 4 (RAG)**: Stdlib SQLite does **not** provide vector similarity search (no sqlite-vector), so we still use binary vectors + JSON (or streaming search) for embeddings. We can still use SQLite for **metadata and chunk text** (e.g. id, document URL, chunk text, timestamps) and keep vectors in a separate binary file keyed by id — or use SQLite as the primary store for everything except the vector math. So SQLite can still be helpful for structured persistence even when the vector store itself is custom.

Keeping this in mind makes it easier to choose stdlib-friendly storage (e.g. SQLite for history and RAG metadata) without pulling in heavier backends.

**Vector extension in stdlib?** As of early 2025 there is **no plan or PEP** to add a vector/similarity-search extension to Python’s standard library. Stdlib `sqlite3` stays as the DB-API interface to stock SQLite; vector search is provided by **loadable extensions** (e.g. `sqlite-vec`, `sqlite-vector`) that are third-party and require `conn.enable_load_extension(True)` and `conn.load_extension(...)`. So for the foreseeable future, “stdlib-only” RAG means our own vector store (binary + JSON, pure-Python or optional NumPy) — we can’t rely on stdlib SQLite gaining vector search.

---

## Research: `langchain-community`

**Value it can add:**
`langchain-community` provides a massive collection of third-party integrations. For WriterAgent, its main value would be ready-made components for Phase 2 (e.g., `SQLChatMessageHistory` to store conversations in SQLite) and Phase 4 (various document loaders, text splitters, and vector store wrappers).

**Dependency weight and NumPy:**
While it offers convenience, `langchain-community` is a very heavy package. A basic `pip install langchain-community` pulls in numerous dependencies including `SQLAlchemy`, `PyYAML`, `requests`, `aiohttp`, `dataclasses-json`, and **`numpy`**.
Because it forces a `numpy` installation (and other heavy libraries) just for the base package, it directly conflicts with our "minimal dependencies" constraint for LibreOffice.

**Conclusion: Vendoring Strategy**
Instead of installing `langchain-community` as a dependency, we should treat its [open-source repository](https://github.com/langchain-ai/langchain) as a reference implementation library. We continue to depend strictly on `langchain-core` as planned. When we need specific functionality, we will **find the relevant code in `langchain-community`, copy it into our source tree (vendoring), and adapt it** to work within our LibreOffice constraints. This allows us to leverage community-built logic while keeping our footprint small and `numpy` cleanly optional.

### Vendoring Candidates
Based on a review of the `langchain-community` codebase, here are specific components we can vendor:

- **Database Chat History (`SQLChatMessageHistory`)**: Located in `chat_message_histories/sql.py`. The upstream version is tightly coupled to `SQLAlchemy` to support multiple database engines. We can use its structural design as a reference but rewrite the database interface to use Python's built-in `sqlite3` module, avoiding the `SQLAlchemy` dependency.
- **SQLite Vector Store (`SQLiteVec`)**: Located in `vectorstores/sqlitevec.py`. It uses the standard library `sqlite3` and `struct` for storing embeddings as raw bytes. While it relies on the `sqlite-vec` C-extension, we can take its class structure and replace the similarity search backend with our own pure-Python streaming search logic.
- **File/Text Based Components**: Components like `FileChatMessageHistory` (`chat_message_histories/file.py`) and `TextLoader` (`document_loaders/text.py`) have zero external dependencies. They rely solely on standard Python modules like `pathlib` and `json`, and can be copy-pasted almost verbatim if needed.

#### Future Possibilities (Catalog of Ideas)
While we don't need these immediately for the core LibreOffice integration, the repository contains a massive collection of reference implementations we could vendor if users request specific features:
- **Document Loaders (170+ integrations)**: If we ever want to allow users to load data into LibreOffice from external sources, there are ready-made classes for Cloud Drives (Google Drive, OneDrive, S3), Workspaces (Confluence, Notion, Slack), and file formats (PDFs, ePub, Dataframes).
- **Agent Orchestration and Tools (via `smolagents`)**: We have actively begun vendoring and integrating `smolagents` into WriterAgent to handle complex, multi-step sub-agent tasks. This serves as a lightweight alternative to heavier `langchain` paradigms:
  - **ToolCallingAgent & Memory (`smolagents.agents`, `smolagents.memory`)**: We've vendored the core `ToolCallingAgent` and its associated memory structures structure (`ActionStep`). We bridged this to WriterAgent's existing `LlmClient` via a custom `WriterAgentSmolModel` wrapper, allowing for autonomous ReAct loops (like web searching) without polluting the main LangChain agent's context.
  - **Zero-Dependency Web Tools (`smolagents/default_tools.py`)**: We adapted their `DuckDuckGoSearchTool` and `VisitWebpageTool` to use pure `urllib.request` and standard library `html.parser`, bypassing external dependencies like `requests`, `beautifulsoup4`, or `markdownify`.
  - **Secure Local Python Execution (`smolagents.local_python_executor`)**: (Future Candidate) This zero-dependency gem uses Python's `ast` to safely evaluate Python code with strict bounds (preventing dangerous imports, limiting loops). We can vendor this to give our AI a `python_interpreter` tool for processing LibreCalc data safely without heavy sandboxes.
  - **Web Browsing (`smolagents/vision_web_browser.py`)**: Currently uses `selenium` and `helium`. For WriterAgent, we should conceptually port the interaction logic (like `_escape_xpath_string` and semantic navigation) to a PyCDP (Chrome) or Marionette (Firefox) backend for a lightweight, dependency-free browser automation implementation.
- **Retrievers (40+ strategies)**: Beyond standard vector search, it contains implementations for Lexical/Keyword search (BM25, TF-IDF, SVM) and Hybrid approaches, which we could adapt for local document search.
- **Third-Party Model Integrations**: Communication plates for nearly every LLM provider, providing a solid reference if we ever need to expand our `LlmClient` to support obscure model gateways.

---

## Architecture Decision: Custom Wrapper vs. Provider Packages
We will proceed with writing a custom LangChain wrapper (`WriterAgentLangChainModel`) around our existing `LlmClient` rather than importing heavy provider packages like `langchain-openai` or `langchain-ollama`. WriterAgent runs in LibreOffice's constrained Python environment; keeping dependencies minimal (just `langchain-core`) is critical to avoid bloat and cross-platform installation issues, while allowing us to keep our custom UI streaming loops and connection management.

For Phase 4 (RAG), the **vector store is tiered** (see [vector-search-design.md § Recommended stack](vector-search-design.md#recommended-stack-2026-06)): **venv + `sqlite-vec`** for heavy search; **host Cython** (`writeragent_vec_search` or similar) for streaming top-k when no venv — same contrib ABI matrix as [cython-extension.md](cython-extension.md); pure-Python last resort. Persistence: binary float32 sidecar + stdlib SQLite for chunk metadata/FTS5. Optional: `hnsw-lite` in venv for bounded in-RAM ANN. No Chroma, FAISS, or in-process `sqlite-vec` in LO. Embeddings via existing providers (OpenRouter, Together, Ollama) or local embedder in venv.

---

## Appendix: HNSW and hnsw-lite

This section explains the HNSW algorithm and the hnsw-lite library, and gives a short tutorial. It supports Phase 4’s optional in-memory index for faster approximate search.

### What is HNSW?

**HNSW** (Hierarchical Navigable Small World) is an algorithm for **approximate nearest neighbor (ANN)** search in high-dimensional vector spaces. It is described in Malkov & Yashunin, “Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs” (IEEE TPAMI, 2018).

- **Problem**: Given many vectors (e.g. embeddings of document chunks) and a query vector, find the k vectors closest to the query. A naive linear scan is O(n) per query; for millions of vectors this is too slow.
- **Idea**: Build a **graph** where each vector is a node and edges connect “nearby” vectors. The graph has the **small world** property: you can reach any node in a small number of hops. Add **hierarchy** (multiple layers, like skip lists): top layers have long-range links for fast coarse search; bottom layer has fine-grained neighborhoods. Search starts at the top, narrows in, then refines at the bottom.
- **Trade-off**: Search is **approximate** — you get the true k nearest neighbors only with some probability (recall). In practice, recall is often 95%+ with sub-millisecond query time and O(log n) scaling.
- **Parameters**: (1) **M** — max number of connections per node; higher M → better recall, more memory and slower. (2) **ef_construction** — size of the candidate list during index build; higher → better graph quality, slower build. (3) **ef_search** (at query time in some impls) — how many candidates to consider during search; higher → better recall, slower query.

HNSW is used in many vector DBs (e.g. Pinecone, Weaviate, Qdrant) and libraries (e.g. hnswlib, nmslib).

### What is hnsw-lite?

**hnsw-lite** is a **pure Python** implementation of HNSW: no C/C++ extensions. It is lightweight and easy to vendor or depend on.

- **PyPI**: `pip install hnsw-lite`
- **Dependency**: Declares NumPy (used for distance calculations). For a zero-NumPy setup we could vendor it and replace the distance layer with pure-Python cosine.
- **Features**: Cosine and Euclidean distance; optional metadata per vector; configurable M and ef_construction.
- **API**: Build an index with `insert(vector, metadata)`, then run `knn_search(query_node, k)` to get k approximate nearest neighbors. Vectors are Python lists (or NumPy arrays when NumPy is used).

### Tutorial: using hnsw-lite

**1. Install and create an index**

```python
# pip install hnsw-lite
from hnsw import HNSW
from hnsw.node import Node

# space: "cosine" or "euclidean"
# M: max connections per node (e.g. 16); higher = better recall, more memory
# ef_construction: build-time quality (e.g. 200); higher = better graph, slower build
hnsw = HNSW(space="cosine", M=16, ef_construction=200)
```

**2. Insert vectors (e.g. document chunk embeddings)**

```python
# Each vector is a list of floats (embedding dimension, e.g. 384 or 768)
vectors = [
    [0.1, 0.2, ...],  # chunk 1
    [0.3, 0.1, ...],  # chunk 2
    # ...
]
for i, vec in enumerate(vectors):
    hnsw.insert(vec, {"id": i, "text": "Snippet of document chunk..."})
```

**3. Query for nearest neighbors**

```python
query_embedding = [0.15, 0.18, ...]  # same dimension as stored vectors
query_node = Node(query_embedding, level=0)
k = 5
results = hnsw.knn_search(query_node, k)

# results: list of (distance, node) — note distances may be negated (check library)
for dist, node in results:
    print(node.metadata["id"], node.metadata["text"][:50])
```

**4. Tuning**

- **M=8–12**: Faster, lower recall; good for speed-critical or small datasets.
- **M=15–20**: Balanced; good default for most uses.
- **M=25–40**: Higher recall, slower and more memory.
- **ef_construction=200**: Solid default; increase (e.g. 300–500) for better graph quality if build time is acceptable.

### How this fits the WriterAgent plan

- **When to use**: For the **in-memory index** path in Phase 4: when we load a subset of vectors (e.g. “recent 30 days”) into RAM and want **fast approximate search** instead of a linear scan. We can vendor hnsw-lite (or depend on it in a venv with NumPy) and use it as the in-memory index; use NumPy for distance when available, pure-Python fallback when not.
- **Persistence**: hnsw-lite does not persist the graph by default. We would need to implement save/load (e.g. serialize the graph and metadata to our binary+JSON format) or build the index on load from our stored vectors.
- **Streaming vs HNSW**: For a **year of conversations** we do **streaming search** (no full load) and do not use HNSW for that path. HNSW is for the **loaded subset** path where we have a bounded number of vectors in memory and want O(log n) approximate search.

## Verification Plan
### Automated & Manual Verification
- **Phase 1**: Verify that multi-turn conversations maintain context without manually re-reading the entire chat history in the prompt.
- **Phase 2**: Close a document, reopen it, and verify the chat sidebar restores previous context.
- **Phase 3**: Conduct a very long chat session and verify that older messages are summarized and the LLM does not return context limit errors.
