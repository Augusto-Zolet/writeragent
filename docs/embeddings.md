# Embeddings — Development Plan

> **Status (2026-06):** **Phase B shipped** — per-folder `index.db`, `search_embeddings` tool, background folder indexer ([`embeddings_cache.py`](../plugin/doc/embeddings_cache.py), [`embeddings_indexer.py`](../plugin/doc/embeddings_indexer.py), [`embeddings_service.py`](../plugin/framework/client/embeddings_service.py)). **Phase A:** host `embed_texts()` + trusted venv encode ([`embedding_client.py`](../plugin/framework/client/embedding_client.py), [`embeddings_index.py`](../plugin/scripting/embeddings_index.py)). **Search mode:** compile-time `DOCUMENT_RESEARCH_SEARCH_MODE` in [`constants.py`](../plugin/framework/constants.py) — `"grep"` (default) or `"embeddings"` (mutually exclusive tool registration). Bench harness: [`scripts/bench_embeddings.py`](../scripts/bench_embeddings.py). **Scope (MVP):** one cache per **filesystem folder** (all indexable siblings in that directory) — not per-file caches, not a global index, not in-document RAG storage. **On-disk storage:** single `index.db` per folder (locators + vectors) using standard SQLite; both host and warm venv worker open the same file directly and pass references (db path / folder key) rather than bulk corpus data. **vec0** (via `sqlite-vec` in the venv) is the preferred on-disk KNN when available; plain BLOB + NumPy dot + top-k is the graceful fallback using the identical DB file. Embed compute uses the warm-worker Pickle5 path (same as `=PYTHON()`).

**Related:** [cython-extension.md](cython-extension.md) · [enabling_numpy_in_libreoffice.md](enabling_numpy_in_libreoffice.md) · [multi-document-dev-plan.md](multi-document-dev-plan.md) · [langchain-plan.md](langchain-plan.md) (chat memory / summarization only)

---

## Problem

The expensive case is **many documents**, not one.

Today the **outer** [document_research](../plugin/doc/document_research.py) sub-agent discovers siblings with `list_nearby_files`, guesses filenames from vague user language, opens candidates, and greps with `search_in_document` / full reads. That is **better than opening 100 files blindly**, but still slow, token-heavy, and weak on paraphrase ("remote work" vs "WFH policy" in an oddly named `Notes_v3.odt`).

**Embeddings** replace that **outer-layer grep** with semantic lookup over a **per-directory index**: one `index.db` per filesystem folder ([Corpus storage](#corpus-storage)) — float vectors in sqlite-vec `vec0` plus locators back to `doc_url`, paragraph, offset (not a second full-text cache). The outer agent searches **that folder’s cache** and gets ranked hits **without opening LO**; it then opens **one or a few** files and hands precise locations to the inner read agent. Opening one file at a known locator is cheap compared to opening dozens and searching each.

**Within a single already-open document**, normal search remains enough (`search_in_document`, outline, sheet navigation). **Cross-folder semantic routing for document_research is the main win.**

**One index type per directory:** do **not** maintain FTS5 (or any parallel keyword corpus) alongside embeddings in that folder’s cache — that would be a **double cache** of the same content. Embeddings are the cross-file search layer for **that directory**; after a hit, use existing read tools on the opened file for literals and detail.

**Chat history vs document embeddings:** Sidebar history (`writeragent_history.db`) is unrelated. This is **corpus routing memory**, not turn memory.

---

## Primary use case: outer document_research replaces grep

[multi-document-dev-plan.md](multi-document-dev-plan.md) uses a **two-tier** delegate: **outer** lists/opens/orchestrates; **inner** runs read tools on one opened file. **Embeddings target the outer tier** — the first sub-agent that today picks files and greps.

```mermaid
flowchart LR
  User["User task on active doc"]
  Main[Main chat]
  Outer["Outer document_research sub-agent"]
  Index["Embeddings index\nvectors + locators only"]
  Hits["Top-k: doc_url + para + offset"]
  Inner["Inner sub-agent\none opened file"]
  Read["Read at locator"]
  Main -->|"delegate"| Outer
  Outer -->|"embed query — not grep"| Index
  Index --> Hits
  Hits -->|"open 1–few URLs"| Outer
  Outer -->|"delegate_read_document"| Inner --> Read
```

**Before (outer):** `list_nearby_files(filter="budget")` → guess → open → `search_in_document` / `get_document_content` on each candidate.

**After (outer):** `search_embeddings("Q4 revenue figures")` → `[Budget_2026.ods, sheet hint / loc, score], …` → `delegate_read_document` on **top hits only** → inner `read_cell_range` / `get_document_content` at the referenced region.

Main chat may also call the index before delegating, but the **major integration point is the outer document_research tool surface** — smarter, faster file pick, no filename lottery.

### After the hit: open one file, dig up truth

The index is **not** a document store. It holds:

- Normalized **float32 vectors** in sqlite-vec **`vec0`** (fallback: embedding BLOB + NumPy search — [Corpus storage](#corpus-storage)).
- **Locators** — enough to find the passage again in LO (paragraph + offset, and Calc/Draw-specific fields as needed later).
- **No duplicated chunk text** in the cache (text is read at index time only to **encode** in the venv or cloud API, then discarded from persistent storage).

Lookup returns **where to look**; opening **one** (or a few) files and reading at that locator is intentional and cheap. That beats opening many files and running semantic search inside each.

---

## Vision

- **One minimal index** — vectors + locators; no duplicate FTS/text cache.
- **Outer document_research** queries embeddings instead of grep across opened siblings.
- **Open one (or few) files** at known locations — not semantic search inside every file in the folder.
- Optional in-document injection on main chat send for edge-case huge single files (low priority).

---

## User-facing modes

| Mode | User experience | Priority |
|------|-----------------|----------|
| **Outer semantic find** | document_research outer agent: `search_embeddings` → ranked `doc_url` + locators → open top hits | **Primary** |
| **Index folder / corpus** | Background embed on open/save; revision-keyed invalidation | **Primary** |
| **Main → delegate with hits** | Main chat runs index first, passes paths/locators into delegate task | **Primary** |
| **Cross-doc Q&A** | Top-k locators across corpus, then inner reads on opened files | **Primary** |
| **In-document RAG on send** | Optional chunk inject beside `[DOCUMENT CONTENT]` for one huge file | **Secondary** |

**Benefits available with today's stack (no LangChain):**

- **`sentence-transformers` + NumPy in the user venv** — tier-one **MVP** embedder (offline, batch CPU, no per-paragraph API cost). See [Local embedders (MVP)](#local-embedders-mvp).
- Cloud embed APIs (OpenRouter / Together / Ollama) when no venv or user prefers hosted models.
- [`list_nearby_files`](../plugin/doc/document_research.py) + read-only extract for **indexing**; index for **lookup** before any of that on query.
- **Pickle5 IPC** into the warm venv worker for encode + sqlite-vec KNN (NumPy fallback — [`bench_embeddings.py`](../scripts/bench_embeddings.py) validates the fallback path).
- Stdlib SQLite on host for locator metadata; **sqlite-vec `vec0`** for vectors + search in the venv (same `index.db` file).

---

## Development plan {#development-plan}

**Goal:** outer [document_research](../plugin/doc/document_research.py) calls `search_embeddings(query, k)` → ranked hits **within the active folder’s cache** (`doc_url` + paragraph locators) → open top files → inner read at offset. No parallel FTS index; no chunk text on disk.

### Scope: per-directory cache only (MVP) {#per-directory-cache}

The **only** persisted index shape for now:

| In scope | Out of scope (later or never) |
|----------|-------------------------------|
| **One cache per directory** — all LibreOffice siblings in the same folder share one cache under `writeragent_embeddings/<key>/` | Per-**file** sidecars or per-document `.db` files |
| Folder key = normalized path of the **directory** being searched (parent of active doc + siblings) | Single global index across `~/Documents` |
| `search_embeddings` searches **that directory’s** vec0 index | Cross-directory search in one query |
| Locator rows identify **which file** each vector belongs to (`doc_url`) | Storing full text in the cache |
| Background worker builds/refreshes **the whole directory cache** | In-document-only embed cache beside `[DOCUMENT CONTENT]` (Phase D — separate) |

**Mental model:** the cache mirrors “everything in this folder that document_research could grep today” — one semantic index for that **directory of files**, not one index per open document and not one index for the entire machine.

**Rule:** **each directory gets its own cache.** Work in `/projects/reporting/` uses only `writeragent_embeddings/<key-for-reporting>/`. Work in `/projects/legal/` uses a **different** `<key-for-legal>/` — separate `index.db`, built and refreshed independently. No sharing across directories in MVP.

```text
/home/user/projects/reporting/          ← real user folder (many .odt/.ods)
  Budget.odt
  Notes_v3.odt
  Q4.ods

~/.config/.../user/writeragent_embeddings/
  <key-for-reporting>/                  ← ONE cache for that directory
    index.db                            ← locators + vec0 vectors for ALL files above
```

### What is shipped

| Item | Status |
|------|--------|
| [`scripts/bench_embeddings.py`](../scripts/bench_embeddings.py) | **Done** — batch encode + vectorized search via warm worker |
| `sentence_transformers` on venv whitelist | **Done** — [`sandbox_imports.py`](../plugin/scripting/sandbox_imports.py) |
| `get_safe_module` bypass for ST | **Done** — avoid hang on import ([`local_python_executor.py`](../plugin/contrib/smolagents/local_python_executor.py)) |
| [`embedding_client.py`](../plugin/framework/client/embedding_client.py) | **Done** — `embed_texts()` via venv RPC (Phase A; HTTP deferred) |
| [`embeddings_index.py`](../plugin/scripting/embeddings_index.py) | **Done** — trusted batch encode module (Phase A; index/search in Phase B) |
| Config `embedding_model` / `embedding_provider` | **Done** — defaults in [`config.py`](../plugin/framework/config.py); Settings UI deferred |

See [Benchmark on your machine](#benchmark-on-your-machine) for sample numbers (349 paragraphs, dot+top-k **0.17 ms** median on Arch).

### Transport: warm-worker IPC (MVP — keep)

Reuse [`PythonWorkerManager`](../plugin/scripting/venv_worker.py) / `run_code_in_user_venv` — same Pickle5 path as `=PYTHON()` and `run_venv_python_script`.

The persistent index is a single on-disk SQLite file (`index.db`) that **both processes open directly** from the filesystem. Standard `sqlite3` (no extensions) already supports multiple processes reading and writing the same DB file concurrently (readers + one writer at a time; WAL mode is an optional improvement). We pass lightweight *references* (the `folder_corpus_key` or full path to `index.db`) rather than shipping the corpus, vectors, or full result matrices on every operation.

Typical flow:

1. **Host** extracts paragraph text (Writer read-only extract / ODT unzip for tests) and does filesystem mtime / content_hash comparisons using its own stdlib `sqlite3` connection to `chunks`.
2. **Host → venv (RPC stub):** for indexing, send only the changed paragraphs (via worker **`data=`** Pickle5) + the db path / folder reference. For search, send the query text (or pre-embedded vector) + `k` + the db path / folder reference.
3. **Venv (trusted module):** the fixed stub receives the reference, opens the *same* `index.db` file with stdlib `sqlite3` (standard SQLite concurrency works across the two processes), loads `sqlite_vec` if available, lazily loads the `SentenceTransformer`, does batch `encode` when needed, then performs vec0 DML/search or the BLOB + NumPy fallback entirely against the on-disk data. Only small results travel back (top-k locators+scores, or write confirmations).
4. **Session:** reuse worker `session_id` so the model (and any in-memory cache of a recently opened folder's vectors) survives across calls.

The **LLM / `=PYTHON()` sandbox** blocks `open()`, `sqlite3`, etc. in **user-submitted** scripts — that rule does **not** apply to shipped `plugin.scripting.*` modules invoked from the host. Trusted embeddings code may `open()` `index.db` (by the path reference passed from the host) and call `sqlite_vec.load()` inside e.g. `plugin.scripting.embeddings_index`. Bulk *source text for embedding* still flows over IPC **`data=`** at index time; the persistent vectors and locators live in the shared DB file. On disk, the corpus is under `writeragent_embeddings/<folder_corpus_key>/`.

**Not pursuing for MVP:** host Cython `top_k_dot`, `/tmp` mmap in worker, LangChain vectorstores — see [Future optimizations](#future-optimizations).

### Open idea: dedicated embeddings worker {#dedicated-embeddings-worker}

Today **one** warm venv child serves Calc `=PYTHON()`, chat `run_venv_python_script`, notebooks, and (soon) embeddings. A long encode (~1 s for a full document after model load) could briefly stall another calc script on the same worker — likely rare given measured speeds, but possible.

**Future option:** a second `PythonWorkerManager` instance (embeddings-only session prefix, same venv `python`) so calc/notebook traffic never queues behind batch embed. Same IPC protocol; only process isolation changes. Defer until we see real contention in the wild.

### Phase A — Embed client + config **(shipped — venv-only)**

- [x] Host [`embedding_client.py`](../plugin/framework/client/embedding_client.py) — `embed_texts(ctx, texts) -> EmbeddingBatch` via venv RPC
- [x] Config: `embedding_model`, `embedding_provider` in [`config.py`](../plugin/framework/config.py) (`local` only implemented; HTTP tier deferred; **no Settings UI yet** — edit `writeragent.json` or use defaults)
- [x] Trusted venv module [`embeddings_index.py`](../plugin/scripting/embeddings_index.py) + fixed host stub — see [Trusted extension code in the venv](enabling_numpy_in_libreoffice.md#trusted-extension-code-in-the-venv)
- [x] Tests: mocked venv RPC + mocked SentenceTransformer ([`test_embedding_client.py`](../tests/framework/test_embedding_client.py), [`test_embeddings_index.py`](../tests/scripting/test_embeddings_index.py))
- Default model: `all-MiniLM-L6-v2` ([`DEFAULT_EMBEDDING_MODEL`](../plugin/framework/constants.py)) until multi-model bench says otherwise

#### Phase A — what exists today (handoff for Phase B)

| Piece | Location | Contract |
|-------|----------|----------|
| Host API | [`embedding_client.embed_texts`](../plugin/framework/client/embedding_client.py) | `EmbeddingBatch(model, dim, vectors, indices)` — `vectors` are L2-normalized float32 nested lists; `indices` maps each vector back to the input list position (empty strings skipped) |
| Model config | `get_embedding_model(ctx)` | Reads `embedding_model` from config; falls back to `all-MiniLM-L6-v2` |
| Venv encode | [`embeddings_index.embed_texts`](../plugin/scripting/embeddings_index.py) | Same shape as worker `result` dict; lazy `SentenceTransformer` cache per model name |
| IPC transport | `run_code_in_user_venv` + fixed stub | `session_id=f"embeddings:{model_slug}"` reuses loaded model across calls; timeout from `scripting.python_exec_timeout` |
| Whitelist | [`sandbox_imports.py`](../plugin/scripting/sandbox_imports.py) | `plugin.scripting.embeddings_index` allowed for stub import only |

**Not built in Phase A (do not assume these exist):** `index.db`, folder corpus key helper, paragraph chunker, `knn_search`, `search_embeddings` tool, background indexer, sqlite-vec / vec0 DML, host `sqlite3` locator writes.

**Phase B should reuse `embedding_client.embed_texts`** for any host-side batch encode during indexing (e.g. tests, small batches). Index-time embed at scale and query-time search should add new functions on **`embeddings_index`** (venv opens `index.db`, writes vec0 or BLOBs, runs KNN) — same trusted-module pattern as encode, new fixed stubs from a future host `embeddings_service.py` or similar.

### Phase B — Minimal index + `search_embeddings` tool {#phase-b}

**Shipped.**

**Goal:** outer [document_research](../plugin/doc/document_research.py) calls `search_embeddings(query, k)` → ranked hits in the **active folder’s** cache → open top files → inner read at locator.

**Search mode (compile-time):** `DOCUMENT_RESEARCH_SEARCH_MODE` in [`constants.py`](../plugin/framework/constants.py) — `"grep"` exposes `grep_nearby_files`; `"embeddings"` exposes `search_embeddings` only (see [Search mode flag](#search-mode-flag) below).

**Suggested implementation order** (each step should have tests before moving on):

1. **Folder key + cache paths (host, stdlib only)** — new module e.g. `plugin/doc/embeddings_cache.py`:
   - `folder_corpus_key(directory_path) -> str` — stable hash/normalized path (same sibling scope as [`list_nearby_files`](../plugin/doc/document_research.py))
   - `index_db_path(ctx, folder_key) -> Path` under `…/user/writeragent_embeddings/<folder_key>/index.db` (beside `writeragent.json`)
   - Host creates `chunks` + `corpus_meta` tables ([Corpus storage](#corpus-storage)); no vec extension on host

2. **Paragraph chunker + locator capture (host)** — extract indexable paragraphs from siblings (reuse document_research read-only extract / ODT path from bench); per paragraph: `doc_url`, `para_index`, `char_start`, `char_end`, `content_hash` ([Chunking](#chunking) — paragraph grain for MVP)

3. **Extend `embeddings_index` (venv)** — add encode+persist and search alongside existing `embed_texts`:
   - `index_paragraphs(db_path, model, rows)` — batch embed changed texts, write `vec_chunks` (vec0) or `chunks.embedding` BLOB fallback ([Search fallback](#search-fallback))
   - `knn_search(db_path, query_text, k)` or `knn_search(db_path, query_vec, k)` — vec0 `MATCH` when `sqlite_vec` loads; else NumPy dot + top-k (port search half of [`bench_embeddings.py`](../scripts/bench_embeddings.py))
   - Probe sqlite-vec once at module load; log fallback at debug

4. **`search_embeddings` tool** — register on outer document_research surface ([`document_research_tools.py`](../plugin/doc/document_research_tools.py)); resolve folder from active doc; call venv `knn_search` with `index.db` path reference; return `{doc_url, para_index, char_start, char_end, score}[]`

5. **Background folder indexer (host thread + venv IPC)** — [Background folder indexer](#background-folder-indexer): cold build + mtime/hash incremental refresh; **must not block** tool loop; enqueue on document_research start or first `search_embeddings` miss

6. **Prompt / delegate wiring** — mode-specific hints in [`specialized_base.py`](../plugin/doc/specialized_base.py) via [`get_document_research_workflow_hint`](../plugin/doc/document_research.py)

**Phase B checklist:**

- [x] Paragraph chunker with **locator capture** (`para_index`, `char_start`, `char_end`, `content_hash`)
- [x] Persist per-folder `index.db` under profile cache dir ([Corpus cache layout](#corpus-cache-layout), [Corpus storage](#corpus-storage))
- [x] **`search_embeddings`** on outer document_research tool surface (mutually exclusive with grep via `DOCUMENT_RESEARCH_SEARCH_MODE`)
- [x] Open top 1–few hits → `delegate_read_document` → inner read at locator (prompt guidance)
- [x] Search executes in the venv (worker opens the shared `index.db` by the folder/db reference passed over the RPC stub): sqlite-vec `vec0` KNN when available; else NumPy dot + top-k against the on-disk BLOBs ([Search fallback](#search-fallback))
- [x] Background **index maintenance worker** (separate from agent tool loop) — [Background folder indexer](#background-folder-indexer)

### Search mode flag {#search-mode-flag}

Cross-file discovery tools are **mutually exclusive** at build time:

| `DOCUMENT_RESEARCH_SEARCH_MODE` | Registered | Hidden (`ToolBaseDummy`) |
|---------------------------------|------------|----------------------------|
| `"grep"` (default) | `grep_nearby_files` | `search_embeddings` |
| `"embeddings"` | `search_embeddings` | `grep_nearby_files` |

Edit the constant in [`constants.py`](../plugin/framework/constants.py) before `make release`. No Settings UI yet. `list_nearby_files` and `delegate_read_document` are always available.

### Corpus cache layout {#corpus-cache-layout}

**Per-directory only:** one **`index.db`** per indexed **folder**, holding locators and **`vec0` vectors** for **every indexable file in that folder** ([Scope](#per-directory-cache)). Schema: [Corpus storage](#corpus-storage).

Keep vectors **out of the user’s document folders** — but **do not hide** the cache. Under the WriterAgent user profile (same tree as `writeragent.json`), use a normal, user-visible directory:

```text
…/user/writeragent_embeddings/
  <folder_corpus_key>/          # hash or normalized path of indexed sibling directory
    index.db                    # SQLite: chunks (locators) + vec0 (embeddings) + corpus_meta
```

| Table / object | Contents |
|----------------|----------|
| **`chunks`** | One row per indexed paragraph — `chunk_id`, `doc_url`, `para_index`, offsets, `content_hash`, **`file_mtime`**, **`last_indexed_at`**, optional `embedding` BLOB (fallback path) |
| **`vec_chunks` (`vec0`)** | sqlite-vec virtual table — `chunk_id`, normalized float32 **embedding**; KNN via `MATCH` |
| **`corpus_meta`** | `embedding_model`, `dim`, `schema_version`, storage backend flag (`vec0` vs `blob_fallback`) |

One **`index.db` per directory** (sibling folder around the active doc), never per open document and never one file for the whole profile. Settings / help: *semantic search cache for a folder — vectors from files in that directory only; delete a subfolder under `writeragent_embeddings/` to force re-index for that directory.*

**Linux example:** `~/.config/libreoffice/4/user/writeragent_embeddings/` (or `…/24/user/` depending on profile).

### Background folder indexer {#background-folder-indexer}

Indexing and refresh run on a **background maintenance worker** (host thread + venv IPC) — **not** inside the document_research tool loop and not blocking the outer agent’s LLM turns. Optional **wakeup** when document_research starts in a folder (same folder key as [`list_nearby_files`](../plugin/doc/document_research.py)); the worker can also run on a timer or when the folder cache is first needed for `search_embeddings`.

**Two modes:**

| Mode | When | Work |
|------|------|------|
| **Cold build** | No cache for folder, or `embedding_model` changed | Index **all** indexable siblings — full paragraph extract, batch embed, write cache |
| **Incremental refresh** | Cache exists | Per file: compare **file mtime** vs **`last_indexed_at`**; only if stale, extract paragraphs and **paragraph-hash diff** (below) |

**Incremental refresh (default once cache exists):**

1. List sibling files in the folder (same extensions as `list_nearby_files`).
2. For each `doc_url`, read filesystem **mtime** (last modified) and compare to **`last_indexed_at`** stored in the cache for that file.
3. **`mtime ≤ last_indexed_at`** (and model unchanged) → **skip file** — no extract, no embed.
4. **File may have changed** → read-only extract (same path as document_research) → compute **`content_hash` per paragraph** → compare to locator rows.
5. Send **only paragraphs with new or changed hashes** to the embedder (batch RPC). Unchanged paragraphs keep existing vectors.
6. The background worker passes the changed paragraphs + a reference to the folder's `index.db` to the venv. The trusted module opens the DB, batch-embeds the changed paragraphs, and patches `vec0` (or the `embedding` BLOB column) plus locator rows in one transaction (`UPDATE`/`DELETE`/`INSERT`); sets **`last_indexed_at`** and **`file_mtime`**. The host may also perform some `chunks` writes directly using its stdlib connection to the same file. See [Search fallback](#search-fallback).

Search always uses the **current** index ([Always search](#always-search-update-in-the-background)); maintenance catches up in the background. XProofreading / write-tool hooks ([Phase C](#phase-c-incremental)) mark paragraphs dirty sooner; this **mtime + hash** pass still runs for files edited outside Writer or when proofreading is off.

```mermaid
flowchart TB
  Wake["Wakeup:\ndocument_research\nor search miss"]
  Worker["Background index\nmaintenance worker"]
  Cold{"Cache exists\nfor folder?"}
  Full["Cold: index all\nsiblings"]
  Inc["Incremental:\nmtime vs last_indexed"]
  Hash["Paragraph hash\ndiff per stale file"]
  Embed["Venv batch embed\nchanged paras only"]
  Wake --> Worker
  Worker --> Cold
  Cold -->|no| Full
  Cold -->|yes| Inc
  Inc --> Hash
  Full --> Embed
  Hash --> Embed
```

Do not block `search_embeddings` or document_research on embed completion; enqueue work and return ranked hits from whatever index is on disk.

### Corpus storage (sqlite-vec default) {#corpus-storage}

**Default:** one `index.db` per directory. Locator rows live in **`chunks`**; vectors live in sqlite-vec **`vec0`** (`vec_chunks`). Incremental maintenance uses **`UPDATE` / `DELETE` / `INSERT`** — on-disk size tracks **live chunk count × dim**, not edit history. **No append-only vector logs or snapshot chains.**

```mermaid
flowchart LR
  subgraph primary [Default]
    Vec0["vec0 KNN\nsqlite-vec in venv"]
  end
  subgraph fallback [Fallback]
    NumPy["NumPy np.dot + top-k\nBLOB column in chunks"]
  end
  Query["search_embeddings"] --> Try{"sqlite_vec\nimportable?"}
  Try -->|yes| Vec0
  Try -->|no| NumPy
```

The worker is given a path/reference to the DB file and performs the `try` / open / search (or DML) locally against the on-disk data. No full corpus matrix is shipped over IPC for search.

#### Shared invariants

| Concern | Rule |
|---------|------|
| Scope | One `index.db` per **directory** under `writeragent_embeddings/<folder_corpus_key>/` |
| Metadata | Locators in `chunks`: `doc_url`, `para_index`, offsets, `content_hash`, `file_mtime`, `last_indexed_at`, `embedding_model` |
| Incremental logic | mtime skip → hash diff → batch embed **changed paragraphs only** ([Background folder indexer](#background-folder-indexer)) |
| Model change | Cold rebuild entire folder cache |
| Search latency class | Lazy ~60 s background OK; search reads **current** index, may be briefly stale |

#### Schema (vec0 path)

```sql
-- Host creates locator table (stdlib sqlite3 on index worker thread)
CREATE TABLE chunks (
  chunk_id INTEGER PRIMARY KEY,
  doc_url TEXT NOT NULL,
  para_index INTEGER NOT NULL,
  char_start INTEGER,
  char_end INTEGER,
  content_hash TEXT NOT NULL,
  file_mtime REAL,
  last_indexed_at REAL,
  embedding_model TEXT NOT NULL,
  embedding BLOB  -- optional mirror for NumPy fallback; omit if vec0-only
);
CREATE TABLE corpus_meta (key TEXT PRIMARY KEY, value TEXT);

-- Venv fixed RPC: sqlite_vec.load(db) then create vec0 (dim fixed at cold build)
CREATE VIRTUAL TABLE vec_chunks USING vec0(
  chunk_id INTEGER PRIMARY KEY,
  embedding float[384]  -- dim from embedding_model / corpus_meta
);
```

| Operation | vec0 path |
|-----------|-----------|
| **Changed paragraph** | `UPDATE vec_chunks SET embedding = ? WHERE chunk_id = ?`; sync `chunks.content_hash` |
| **New paragraph** | `INSERT INTO chunks …`; `INSERT INTO vec_chunks …` |
| **Deleted paragraph** | `DELETE FROM vec_chunks WHERE chunk_id = ?`; `DELETE FROM chunks …` |
| **Search** | `SELECT chunk_id, distance FROM vec_chunks WHERE embedding MATCH ? ORDER BY distance LIMIT ?` in venv RPC |

NumPy arrays pass straight into sqlite-vec (`embedding.astype(np.float32)` — see [sqlite-vec Python docs](https://alexgarcia.xyz/sqlite-vec/python.html)).

**Host vs venv (shared DB file):** the *same* `index.db` file is the coordination point and is opened by both processes. The host uses plain stdlib `sqlite3` (no loadable extensions required) to manage the `chunks` locator/metadata table, perform mtime + hash diff decisions in the background indexer, and orchestrate work. The trusted module in the venv is given a path/reference over the RPC, opens the identical file, and (if `sqlite_vec` is importable) loads the extension to create/use the `vec0` virtual table for storage and KNN. Even without sqlite-vec the worker opens the same DB to read/write the `embedding` BLOB column and runs the NumPy path locally. SQLite's normal multi-process concurrency rules apply; the worker performs the vector-sensitive DML and search while the host owns most metadata logic. LLM / `=PYTHON()` scripts remain sandboxed — they must not import `sqlite3` or open index paths directly.

#### Search fallback {#search-fallback}

At worker startup (or first index open), **probe** `import sqlite_vec` and `sqlite_vec.load()` on a throwaway `:memory:` connection.

| Condition | Persist | Search |
|-----------|---------|--------|
| **sqlite-vec OK** | `vec_chunks` vec0 (+ optional BLOB mirror) | vec0 `MATCH` KNN in venv |
| **Import/load fails** | `chunks.embedding` BLOB only; set `corpus_meta.storage_backend=blob_numpy` | Load all BLOBs → `np.stack` → `np.dot` + top-k ([bench path](#benchmark-on-your-machine)) |

Log once at debug level when falling back. Do **not** fail indexing if `sqlite-vec` is missing — embeddings still work, just without vec0 KNN.

**Anti-pattern — do not use:** append-only vector logs, dual-file `vectors.bin` sidecars that grow on every edit without reclaim, or versioned snapshot chains.

#### Installing sqlite-vec in the user venv {#installing-sqlite-vec}

WriterAgent reads **`scripting.python_venv_path`** ([enabling_numpy_in_libreoffice.md](enabling_numpy_in_libreoffice.md)) — install packages **into that venv**, not system Python. The PyPI wheel bundles the sqlite-vec loadable extension; `pip install sqlite-vec` is the supported path ([upstream install guide](https://github.com/asg017/sqlite-vec/blob/main/site/getting-started/installation.md)).

**All platforms (recommended):**

```bash
# Replace with your actual venv path from WriterAgent Settings
VENV=/path/to/your/writeragent/venv

"$VENV/bin/pip" install numpy sentence-transformers sqlite-vec
# sentence-transformers pulls PyTorch CPU; first run downloads model weights.
```

**Verify:**

```bash
"$VENV/bin/python" -c "
import sqlite3, sqlite_vec
db = sqlite3.connect(':memory:')
db.enable_load_extension(True)
sqlite_vec.load(db)
db.enable_load_extension(False)
print('vec_version=', db.execute('select vec_version()').fetchone()[0])
"
```

**Arch Linux notes:**

Arch marks system Python as [externally managed (PEP 668)](https://peps.python.org/pep-0668/) — **`pip install` on `/usr/bin/python3` fails** unless you use a venv. That matches WriterAgent’s design: always use the configured venv subprocess, never LibreOffice’s embedded interpreter for sqlite-vec.

1. **Use the WriterAgent venv (required):**

```bash
# Example: venv already pointed at by scripting.python_venv_path
VENV="$HOME/Desktop/Python/venv"   # adjust to your path

"$VENV/bin/pip" install numpy sentence-transformers sqlite-vec
```

2. **If the venv has no pip** (fresh `python -m venv` on Arch sometimes needs ensurepip):

```bash
pacman -S python-pip    # optional: pacman helper; still install into venv below
"$VENV/bin/python" -m ensurepip --upgrade
"$VENV/bin/pip" install numpy sentence-transformers sqlite-vec
```

3. **AUR (`python-sqlite-vec`) — not a substitute:** [`python-sqlite-vec`](https://aur.archlinux.org/packages/python-sqlite-vec) installs into **system** site-packages via an AUR helper (`yay -S python-sqlite-vec`). WriterAgent’s warm worker uses **`scripting.python_venv_path`**, so you still need **`pip install sqlite-vec` inside that venv**. The AUR package is only relevant if you deliberately run the venv’s Python against system packages (unusual — do not rely on it).

4. **SQLite version:** vec0 works best with SQLite **≥ 3.41**. Check the **venv** interpreter, not system `sqlite3`:

```bash
"$VENV/bin/python" -c "import sqlite3; print(sqlite3.sqlite_version)"
```

Python 3.12+ venvs on Arch usually ship a recent SQLite. If `enable_load_extension` is missing (some macOS system Pythons), use Homebrew Python or `pysqlite3` — see [sqlite-vec Python docs](https://alexgarcia.xyz/sqlite-vec/python.html).

**Do not** vendor sqlite-vec into the OXT or load it in LibreOffice’s embedded Python — venv trusted module only ([Trusted extension code in the venv](enabling_numpy_in_libreoffice.md#trusted-extension-code-in-the-venv)).

#### Rejected alternatives (historical)

| Alternative | Why not default |
|-------------|-----------------|
| Dual-file `index.db` + `vectors.bin` | Two-file sync; append-only `.bin` risk |
| BLOB-only + always IPC full matrix | Works as **fallback**, but vec0 avoids loading all vectors at large N |
| Full sidecar rewrite each batch | Write amplification on small edits |

### Phase C — Incremental maintenance {#phase-c-incremental}

- [ ] Paragraph `content_hash`; skip embed when hash unchanged
- [ ] **`XProofreading` change hook** — separate embeddings maintenance path on the same entry point as grammar ([below](#xproofreading-incremental-hook))
- [ ] **~60 s debounced worker** per `doc_url` before re-embed ([Incremental updates](#incremental-updates))
- [ ] Dirty marks from write tools + hash diff on open (catch edits grammar path misses)
- [ ] Vector patch in place (`vec0` + `chunks`, or BLOB fallback) per [Corpus storage](#corpus-storage); supersede keys like [`grammar_work_queue.py`](../plugin/writer/locale/grammar_work_queue.py)

#### `XProofreading` incremental hook {#xproofreading-incremental-hook}

Writer already calls [`doProofreading`](../plugin/writer/locale/ai_grammar_proofreader.py) on the **`XProofreading`** linguistic path whenever the user types — that is how the native grammar proofreader learns which **text slice** changed. Embeddings maintenance **reuses that entry point** but is a **separate code path**:

| | Grammar proofreader | Embeddings indexer |
|--|---------------------|-------------------|
| **UNO entry** | `XProofreading.doProofreading` | Same call site (parallel hook) |
| **Work** | LLM grammar JSON + squiggles | Paragraph hash diff → venv batch re-embed |
| **Latency** | ~1 s quiet window | **~60 s** quiet window before any embed work |
| **User-visible** | Underlines | None (background index only) |

**Do not** run embed logic inside the grammar proofreader class or share grammar’s sentence queue. Add a thin **embeddings listener** invoked from the same `doProofreading` dispatch (or shared pre-hook) that:

1. Maps the proofread buffer slice to **paragraph index + normalized text** (same BreakIterator / paragraph boundaries grammar already uses — see [`grammar_proofread_text.py`](../plugin/writer/locale/grammar_proofread_text.py)).
2. Compares `content_hash` to the locator row for `(doc_url, para_index)`.
3. On mismatch, **marks paragraph dirty** and resets a **60 s idle timer** for that document — no venv call yet.

When the timer fires (document quiet for **one minute**), drain all dirty paragraphs for that `doc_url` in one batch embed RPC, patch `vec_chunks` + `chunks`, update locator rows. Supersede inflight work if the user keeps typing (same supersede pattern as grammar’s `enqueue_seq`, different timeout constant).

Grammar can be off while embeddings indexing stays on (separate config flags). External saves and non-Writer edits still converge via **mtime + hash diff on open** and the background folder indexer.

### Phase D — Optional later

- Main chat runs index before delegate; pass locators in task string
- In-document chunk inject beside `[DOCUMENT CONTENT]` for one huge file ([Within-document retrieval](#within-document-retrieval-secondary))
- Cloud embed tier-two when no venv ([Cloud embedding APIs](#cloud-embedding-apis-tier-two))

---

## Within-document retrieval (secondary)

For the **active document only**:

- Writer/Calc already expose fast keyword/outline search to tools and users (`search_in_document`, outline helpers, sheet navigation).
- Injecting extra chunks from an embedding index on every chat send is **optional** — useful when the 8k excerpt misses a distant section in a **single** 200-page file, not the usual case.
- Implement after the **corpus index** proves value; same chunker and storage, scoped by `doc_url`.

---

## Architecture

WriterAgent runs NumPy, **sqlite-vec**, and **sentence-transformers** **only in the user venv subprocess** ([`PythonWorkerManager`](../plugin/scripting/venv_worker.py)). LibreOffice's embedded interpreter stays stdlib — no NumPy or sqlite-vec in-process.

```mermaid
flowchart TB
  subgraph host [LO_host]
    Outer["Outer document_research"]
    IndexDB["index.db (shared on-disk file)\nlocators + vec0 / BLOBs"]
    RPC["embed / search RPC (pass db reference)"]
  end
  subgraph venv [Warm_venv_worker]
    ST["SentenceTransformer\nbatch encode"]
    Search["open same DB file\nsqlite-vec KNN or NumPy"]
  end
  Outer --> RPC
  RPC -->|"Pickle5: texts (index) or query+ref (search)"| ST
  ST -->|"worker opens IndexDB by ref"| Search
  Search -->|"small results (locators+scores)"| RPC
  RPC --> Outer
```

**Split responsibilities (shared on-disk DB + reference passing):**

```
┌─────────────────────────────────────────────────────────────┐
│ LibreOffice host (embedded Python — stdlib)                  │
│  • Chunk / extract paragraphs; compute mtime + content_hash  │
│  • Open index.db with plain sqlite3 for `chunks` + meta      │
│  • Background maintenance worker (orchestration + decisions)  │
│  • Pass db_path / folder reference + texts or query over RPC │
│  • Optional HTTP embed when no venv (tier two)               │
└───────────────────────────┬─────────────────────────────────┘
                            │ Pickle5 RPC (texts or query + db reference)
┌───────────────────────────▼─────────────────────────────────┐
│ User venv — warm worker (trusted module, same =PYTHON() venv)│
│  • Opens the *same* index.db file by the reference passed in  │
│  • sentence-transformers — lazy load, batch encode             │
│  • sqlite-vec (if present) — vec0 storage + KNN in the DB    │
│  • or BLOB column + NumPy dot+top-k against the opened DB    │
│  • Returns only compact locator lists / small results        │
└─────────────────────────────────────────────────────────────┘
```

The `index.db` lives on the filesystem and is the single source of truth for both locators and vectors. Standard SQLite (no vec extension) is sufficient for the host and for the fallback search path; both processes can safely open it at the same time.

**MVP path:** the worker receives a *reference* to the shared on-disk `index.db` (plus small payloads) over the RPC and opens the file itself. Encode and search (vec0 `MATCH` when available, otherwise BLOBs + NumPy dot + top-k) happen inside the trusted module in the venv. The bench validates the pure-NumPy path at 349 paragraphs (dot+top-k **0.17 ms** median). See [Development plan](#development-plan), [Installing sqlite-vec](#installing-sqlite-vec), and [Trusted extension code in the venv](enabling_numpy_in_libreoffice.md#trusted-extension-code-in-the-venv). The on-disk DB (opened from both sides via standard sqlite3) is what enables passing references instead of bulk vector data.

**Do not** add `sqlite3` / `os` to the **LLM** import whitelist to support embeddings — implement `open()` and vec0 inside a shipped `plugin.scripting.*` module called from a fixed host stub.

---

## How embeddings work

### Meaning signatures

An embedding is a fixed-length list of floats (e.g. 384 or 1536) representing a chunk of text in multi-dimensional space. Chunks from **many files** live in one index; a query vector compares against all of them to surface the best **document + passage** matches.

- "The dog is barky" and "Canine vocalization" are **close together**.
- "The dog is barky" and "Pythons are interpreted languages" are **very far apart**.

### Closeness = angle, not words

We compare **angles** between vectors. If two vectors point in roughly the same direction, the texts have similar meanings.

- **Dot product**: multiply values at each index and sum.
- **Cosine similarity**: dot product of two **normalized** vectors (length 1.0).

> **Optimization:** Normalize vectors **once** when stored (or when received from the API). Cosine search then reduces to a fast **dot product** scan.

---

## Why NumPy stays in the venv {#why-numpy-stays-in-the-venv}

NumPy carries a heavy "tax" inside a LibreOffice `.oxt`:

- **Binary size**: ~50–100 MB per platform.
- **Complexity**: packaging for Windows, macOS (Intel + Silicon), and Linux (x86 + ARM) is a maintenance nightmare.

**WriterAgent's solution (shipped):** NumPy and **sentence-transformers** run **only in the user venv subprocess** — see [enabling_numpy_in_libreoffice.md](enabling_numpy_in_libreoffice.md). Host↔venv uses **Pickle5** by default (3.11–3.14). For MVP, **encode and search both stay in the venv** over IPC ([Development plan](#development-plan)).

---

## Embedding inference

Two tiers. **Shipped today (Phase A):** local **`sentence-transformers`** in the configured venv only — via [`embedding_client.embed_texts`](../plugin/framework/client/embedding_client.py). **Tier two (not implemented):** OpenRouter / Together / Ollama HTTP when no venv.

**Current dispatch:** `embedding_provider` must be `local` (default). Host calls `run_code_in_user_venv` with a fixed stub → [`embeddings_index.embed_texts`](../plugin/scripting/embeddings_index.py). Requires `scripting.python_venv_path` (or LO fallback interpreter) with `pip install sentence-transformers numpy`.

**Future dispatch (when HTTP ships):** if venv + local model → venv RPC; else if chat endpoint supports embeddings → HTTP; else prompt user to configure venv or API.

**Phase B note:** indexing and search should call **new** `embeddings_index` functions for vec0/BLOB persist and KNN; keep using `embedding_client.embed_texts` only where the host needs raw vectors without touching `index.db`.

---

## Local embedders (MVP) {#local-embedders-mvp}

### Why sentence-transformers is tier one

- **Already fits the venv bridge** — same `PythonWorkerManager` + Pickle5 path as NumPy calc scripts; nothing heavy in LibreOffice.
- **Offline indexing** — embed a whole folder without API keys or rate limits; incremental paragraph re-embed stays cheap.
- **CPU-viable** — many small models encode hundreds of paragraphs in seconds on a laptop when you **batch** and use **NumPy dot products** for search (not Python loops).
- **Same stack as dedup/search prototypes** — proven patterns from [`embeddings_dedup.py`](file:///home/keithcu/Desktop/LinuxReport/embeddings_dedup.py) (LinuxReport project): lazy-loaded model, batch `encode(..., convert_to_tensor=False)`, L2-normalized vectors, `np.dot` for cosine.

### Performance lessons (slow first version → fast second)

The LinuxReport dedup code documents a real refactor:

| Approach | Behavior | Typical cost (200 texts) |
|----------|----------|---------------------------|
| **Slow (v1)** | Per-text encode or Python loop over pairs | ~1.5–2.0 s |
| **Fast (v2)** | Batch `encode` + `np.stack` + matrix `np.dot` | ~0.002 s (~**700–800×** in their benchmark) |

WriterAgent should **never** embed or rank one paragraph at a time in a Python loop for corpus work. MVP pipeline:

1. **Lazy-load** one `SentenceTransformer` per worker process (amortize model load).
2. **Batch** all paragraphs needing embed in one `encode(valid_texts, convert_to_tensor=False)` call.
3. **Normalize once** → float32 in `vec_chunks` vec0 (and optional BLOB mirror for [Search fallback](#search-fallback)).
4. **Query:** encode query → vec0 `MATCH` KNN in venv; on fallback, `np.dot(corpus_matrix, query_vec)` ([bench sample](#benchmark-on-your-machine)).

Optional in-worker **text hash cache** during a single index pass (like LinuxReport's `embedding_cache` dict) avoids re-encoding identical paragraphs across files; persistent dedup uses **`content_hash`** in SQLite instead of storing raw text.

### Model shortlist (beyond legacy MiniLM-only defaults)

`all-MiniLM-L6-v2` (384-dim, ~22M params) is the old default everyone knows — still a solid **baseline**, but test alternatives on **your** CPU before locking config:

| Model (HF id) | Dim | Lean / quality | Notes |
|---------------|-----|----------------|-------|
| **`all-MiniLM-L6-v2`** | 384 | Fastest baseline | LinuxReport default; good for benchmarking “classic” speed. |
| **`BAAI/bge-small-en-v1.5`** | 384 | Fast, strong retrieval | Popular RAG choice; often beats MiniLM on MTEB retrieval at similar size. |
| **`intfloat/e5-small-v2`** | 384 | Fast | Prefix `"query: "` / `"passage: "` at encode time (library or prompt wrapper). |
| **`Snowflake/snowflake-arctic-embed-xs`** | 384 | Fast, newer | Competitive small encoder; worth A/B vs MiniLM. |
| **`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`** | 384 | Medium speed | Non-English folders. |
| **`all-mpnet-base-v2`** | 768 | Slower, higher quality | When CPU budget allows; ~2× dim → larger `index.db`. |
| **`BAAI/bge-base-en-v1.5`** | 768 | Medium–slow | Step up from bge-small when quality gaps show in testing. |
| **`nomic-embed-text-v1.5`** | 768 | Via ST or Ollama | Long-context friendly; heavier — profile before corpus index. |

**Ollama-local** (`nomic-embed-text`, `embeddinggemma`, …) is an alternative **local** path without `sentence-transformers` in venv — still tier one “local”, different packaging. Pick one local stack per install (ST in venv **or** Ollama HTTP to localhost), not both for the same index.

Store **`embedding_model`** in config as the HuggingFace id (local) or provider model string (cloud). Changing model requires cold rebuild of folder `index.db` ([Corpus storage](#corpus-storage)).

### Venv setup (MVP)

See [Installing sqlite-vec in the user venv](#installing-sqlite-vec) for full steps (including **Arch Linux**). Minimum:

```bash
# In the venv referenced by scripting.python_venv_path
pip install sentence-transformers numpy sqlite-vec
# PyTorch CPU wheel is pulled by sentence-transformers; first run downloads model weights.
```

Warm worker loads the model once; subsequent index batches reuse it (same pattern as LinuxReport's global `embedder` lazy init).

### Benchmark on your machine {#benchmark-on-your-machine}

Run [`scripts/bench_embeddings.py`](../scripts/bench_embeddings.py) — document-sized encode + query timing via the **warm venv worker** (Pickle5 IPC, not worker-side file I/O):

```bash
python scripts/bench_embeddings.py
python scripts/bench_embeddings.py --models all-MiniLM-L6-v2,BAAI/bge-small-en-v1.5
```

Uses [`scripts/longdocsample.odt`](../scripts/longdocsample.odt) (349 non-empty paragraphs). Flow:

1. Host extracts paragraphs (stdlib ODT unzip) and passes the text list via worker **`data=`**.
2. **Encode bench:** lazy `SentenceTransformer`, one batch `encode(all_paragraphs)`; `corpus_matrix` stays in worker session.
3. **Search bench:** median over `--search-iters` (default 50) for query encode, `np.dot` + top-k, and combined query time.
4. Host optionally writes `/tmp/writeragent_embed_paragraphs.json` and `/tmp/writeragent_embed_sidecar.bin` for inspection.

**Sample result (Arch Linux, `/home/keithcu/Desktop/Python/venv`, 2026-06):**

| Metric | `all-MiniLM-L6-v2` |
|--------|-------------------|
| Paragraphs / dim | 349 / 384 |
| Sidecar | 0.51 MiB |
| Model load | 2.810 s |
| Batch encode (corpus) | 1.062 s |
| Query encode (median) | 3.715 ms |
| Dot + top-k (median) | 0.167 ms |
| Query total (median) | 3.879 ms |

Top hit for query *"offline-first data collection systems KoboToolbox"*: para 245 (0.84), then title para 0 (0.76). Dot+top-k at sub-ms validates the vectorized search path from LinuxReport [`embeddings_dedup.py`](file:///home/keithcu/Desktop/LinuxReport/embeddings_dedup.py).

Repeat with **2–3 models** from the [shortlist](#local-embedders-mvp); record dim, encode s, query ms, sidecar MB (`N × dim × 4`). Log machine, Python version, and BLAS backend when comparing runs.

**Reference implementation:** [`embeddings_dedup.py`](file:///home/keithcu/Desktop/LinuxReport/embeddings_dedup.py) — `get_embeddings`, `_compute_cosine_similarities` (batch + NumPy). Port the **batch/NumPy** shape into WriterAgent's venv embed module as the **search fallback**; primary persist/search uses sqlite-vec `vec0` ([Corpus storage](#corpus-storage)).

---

## Cloud embedding APIs (tier two)

Use when no venv, or when you want hosted large models (e.g. OpenRouter `text-embedding-3-large`) without local GPU/CPU load.

### OpenRouter

- Endpoint: `POST https://openrouter.ai/api/v1/embeddings`
- Same API key as chat. Request: `model`, `input` (string or array of strings).
- Optional: `dimensions`, `encoding_format`, `input_type`, `provider`.

### Together AI

- Endpoint: `{configured_endpoint}/embeddings` (OpenAI-compatible).
- Models: e.g. BAAI/bge-large-en-v1.5, togethercomputer/m2-bert-80M-8k-retrieval.

### Ollama (local HTTP, no ST venv)

- Endpoint: `POST {base}/api/embed`
- Models: `nomic-embed-text`, `all-minilm`, `embeddinggemma` — local process, not LibreOffice.

### Config

- **`embedding_model`** + **`embedding_model_lru`** (mirror [`get_image_model`](../plugin/framework/client/model_fetcher.py)).
- **`embedding_provider`**: `local` (sentence-transformers in venv) | `openrouter` | `together` | `ollama` — auto-detect from model id / endpoint when unset.

---

## Persistence — keep the cache small {#minimal-index}

**Goal:** one compact **`index.db`** per directory. Vectors in **`vec0`**; metadata in **`chunks`** — locators only in row columns, **no FTS shadow index**. See [Corpus storage](#corpus-storage).

### What we store

| Part | Contents | Size driver |
|------|----------|-------------|
| **`vec_chunks` (vec0)** | Normalized float32 embeddings (primary) | `n × dim × 4` bytes |
| **`chunks` rows** | `chunk_id`, `doc_url`, locators, `content_hash`, optional `embedding` BLOB (fallback) | Tiny per row |

### Locator fields (dig up original text later)

Persist enough to re-read from LO after opening **one** file:

- **`doc_url`** — which file.
- **`doc_revision`** — invalidate when file changes.
- **`para_index`** — paragraph (or outline node) in Writer; analogous anchor for Calc sheet / Draw page when extended.
- **`char_start`**, **`char_end`** — character offsets within that paragraph (or range within sheet cell block).
- **`chunk_id`** — joins `chunks` to `vec_chunks` vec0 row.

At **index time**, extract a chunk of text → **venv batch encode** (MVP) or HTTP embed → write vector + locator → **do not** persist the chunk body. Optional: keep a **short hash** of source text to detect drift; not the text itself.

At **query time**, top-k returns locators → outer agent opens `doc_url` → inner agent uses existing read tools (`get_document_content` with range, `search_in_document` near offset, `read_cell_range`, …) to fetch **live** text.

### Host metadata schema

Locator columns in **`chunks`** — `writeragent_embeddings/<folder_corpus_key>/index.db` ([Corpus cache layout](#corpus-cache-layout), [Corpus storage](#corpus-storage)):

```text
(chunk_id, doc_url, doc_revision, embedding_model,
 para_index, char_start, char_end, content_hash,
 file_mtime, last_indexed_at)
```

Vectors live in **`vec_chunks`** vec0 (same DB). Fallback mode also fills **`chunks.embedding`** BLOB. Extend with Calc/Draw locator columns when those index paths ship; same “reference only” rule.

### Modes

1. **On-disk corpus (default)** — `index.db` with vec0 + chunks; scales to folder-sized corpora.
2. **In-memory subset (optional later)** — bounded “recent N” only; see [HNSW](#hnsw-and-hnsw-lite) in Future optimizations.

### Versioning

Re-index entire doc when `embedding_model` changes. For day-to-day edits, **`content_hash` per paragraph** drives incremental embed ([Incremental updates](#incremental-updates)); `doc_revision` / mtime catches files edited outside WriterAgent.

### Vendoring patterns (no LangChain dependency)

Reference implementations to adapt:

- **langchain_core.vectorstores.in_memory** — dump/load pattern; replace body with `index.db` vec0 layout.
- **langchain_community.vectorstores.sklearn** — `BinaryVectorSerializer` — useful for **NumPy fallback** only.
- **langchain_community.vectorstores.sqlitevec** — primary reference for vec0 integration.

**SQLite note:** Search runs in a **trusted venv module** — sqlite-vec `MATCH` by default; NumPy when [Search fallback](#search-fallback) is active. Host stdlib `sqlite3` may maintain `chunks` locators on the index worker thread ([Trusted extension code in the venv](enabling_numpy_in_libreoffice.md#trusted-extension-code-in-the-venv)).

---

## Indexing pipeline

**Build the minimal corpus index:**

1. **Discover** — document_research in folder → check per-folder cache; if missing, background scan of all siblings ([Background folder indexer](#background-folder-indexer)); else `list_nearby_files` scope for incremental work.
2. **Chunk in memory** — ~500-character windows with paragraph/offset tracking ([Chunking](#chunking)).
3. **Embed** — venv `sentence-transformers` batch (MVP) or cloud HTTP; normalize float32; **discard chunk text** after encode.
4. **Persist** — `vec_chunks` + `chunks` row + **`content_hash`** ([Corpus storage](#corpus-storage)); skip embed when hash unchanged ([Incremental updates](#incremental-updates)).
5. **Outer lookup** — `search_embeddings(query, k)` → locators → open **1–few** files → inner read at offset.

**Optional — active document only:** same pipeline for one `doc_url`; inject live-fetched text on main send (**secondary**).

---

## Incremental index maintenance {#incremental-updates}

The corpus index must stay **current without full re-embeds**. Grammar proofreading already solves a related problem: detect what changed, queue work, supersede stale jobs, write results to a cache — but on a **sentence** cadence with ~**1 s** quiet windows because users want squiggles immediately ([realtime-grammar-checker-plan.md](realtime-grammar-checker-plan.md), [`grammar_work_queue.py`](../plugin/writer/locale/grammar_work_queue.py)). **Embeddings are the opposite latency class:** stale-by-a-minute is acceptable; cost is **CPU batch encode** (local) or HTTP embed batches (cloud) for changed paragraphs only — not per-keystroke work.

### Paragraph hash (primary) vs sentence hash

Store a **content fingerprint per indexed unit** alongside each locator row:

| Granularity | Fingerprint key | Re-embed when | Notes |
|-------------|-------------------|---------------|-------|
| **Paragraph (default)** | `hash(normalized_para_text)` | Paragraph body changes | Matches Writer paragraph boundaries; fewer rows than sentences; aligns with chunker `\n\n` splits. |
| **Sentence (optional)** | `hash(normalized_sentence_text)` | Sentence changes | Finer invalidation inside long paragraphs; more index rows and API calls — use only if profiling shows paragraph grain is too coarse. |

**Schema addition:** `(para_index, content_hash)` — or `(para_index, sent_index, content_hash)` if sentence grain ships later. On index pass, compute hash from extracted text; **skip encode** when hash matches the stored row for that `(doc_url, para_index, embedding_model)`.

Normalized text for hashing should match what the chunker sees (tracked-deletion-free string where grammar uses [`get_string_without_tracked_deletions()`](../plugin/doc/document_helpers.py) — same stability goal as proofreader sentence keys).

### Always search; update in the background

**Lookup never blocks on re-embed.** `search_embeddings` reads the **current** `index.db` (vec0 or BLOB fallback + `chunks` locators):

- **Unchanged paragraphs** — existing vectors remain valid (hash match).
- **Changed paragraphs** — old vectors may still rank until the incremental worker replaces them; locators may drift slightly if paragraph boundaries moved — **re-resolve offset on open** via inner read tools (same as today when structure shifts).
- **New paragraphs** — no row yet → optional low-priority enqueue; search may miss until embedded.
- **Deleted paragraphs** — tombstone or delete locator rows on next maintenance pass.

This is intentional: **semantic find stays fast**; index converges asynchronously.

### Where edits are observed

**Primary — typing in Writer (`XProofreading`):** hook **`doProofreading`** alongside grammar ([XProofreading incremental hook](#xproofreading-incremental-hook)). Separate embeddings listener; **wait 60 s** after last change before batch re-embed. Not sentence-speed — find-doc can be ~1 min stale.

**Secondary — WriterAgent write tools:** after successful `apply_document_content` / Calc·Draw write tools, mark `(doc_url)` dirty (same debounced worker).

**Tertiary — folder / open path:** background folder indexer on document_research; hash diff on doc open; mtime sweep for files edited outside WriterAgent.

**Do not** duplicate UNO mutation listeners everywhere — the proofreading API already delivers paragraph-scale text on every edit when linguistic checking is active; embeddings can subscribe in parallel even when grammar LLM is disabled.

### Debounced worker (~1 minute, not grammar-speed)

Mirror grammar queue **patterns**, not timings. Embeddings **must not** run on every `doProofreading` call — only after **~60 s** with no further dirty marks for that `doc_url`:

| Aspect | Grammar proofreader | Embeddings index |
|--------|---------------------|------------------|
| **User expectation** | Errors visible within ~1 s | Find-doc can be ~1 min stale |
| **Quiet/coalesce window** | ~1 s batch drain (`GRAMMAR_WORKER_PAUSE_TIMEOUT_S`) | **~60 s** (configurable) per `(doc_url)` |
| **Work unit** | Sentence | Paragraph (default) |
| **Supersede** | `inflight_key` + `enqueue_seq` — newest wins | Same idea: `{doc_url}|{para_index}|{embedding_model}` |
| **API call** | Small grammar LLM per batch | **Local:** CPU batch encode in venv; **cloud:** HTTP embed batch for changed hashes only |

On dirty signal: bump `enqueue_seq` for affected paragraph keys; worker waits until the doc is **idle ~60 s**, drains the batch, re-extracts only paragraphs whose **hash ≠ stored hash**, calls `embed_texts` in batch, patches `vec_chunks` + `chunks` ([Corpus storage](#corpus-storage)).

Do **not** embed on every keystroke — that would duplicate grammar's stampede problem at encode cost (local CPU or cloud quota).

### Vector patch strategy

Apply patches with **in-place update semantics** — size tracks live corpus, not edit history ([Corpus storage](#corpus-storage)).

| Backend | Changed paragraph | New paragraph | Deleted paragraph |
|---------|-------------------|---------------|-------------------|
| **vec0 (default)** | `UPDATE vec_chunks …`; sync `chunks.content_hash` | `INSERT` into both tables | `DELETE` from both |
| **BLOB fallback** | `UPDATE chunks SET embedding=?, content_hash=?` | `INSERT` row with BLOB | `DELETE` row |

**Anti-pattern — do not use:** append-only vector logs or dual-file `vectors.bin` sidecars that grow on every edit.

Keep **locators** in sync when paragraph indices shift after large edits (re-walk paragraph list on full doc hash mismatch).

### Fleet / multi-writer note

If **all edits flow through WriterAgent**, each installation updates its local index for docs it modifies — no central server required. Two machines editing the same `file://` URL via sync (Nextcloud, etc.) rely on **revision / mtime + hash diff on open** to reconcile; last writer's embedding pass wins per paragraph hash. Document the conflict model; do not promise CRDT merge in v1.

### Phasing

- **Phase B:** `index.db` + vec0; background folder indexer; NumPy [Search fallback](#search-fallback); hash columns stored.
- **Phase C:** `XProofreading` parallel hook + 60 s debouncer; write-tool dirty marks; vec0 patch; supersede keys.

---

## Chunking {#chunking}

Naive character splits destroy meaning. Vendor MIT **RecursiveCharacterTextSplitter** logic (~100 lines) — no langchain package.

- **Repository:** [langchain-text-splitters](https://github.com/langchain-ai/langchain/tree/master/libs/text-splitters/langchain_text_splitters)
- **Key file:** `recursive_character.py` — separators `["\n\n", "\n", " ", ""]`, `chunk_overlap` for context bridging.
- **Index-time only:** while splitting, record **paragraph index and char offsets** for each chunk so locators can be stored without keeping chunk text on disk.

---

## Corpus intelligence

The index is a **router**, not a library mirror.

### Outer agent: semantic find replaces grep

- **Before:** filename filter + `search_in_document` across many opens.
- **After:** one embedding query → ranked files + paragraph/offset → open winners → inner read.

Opening **one** file at a known locator is the designed happy path. Opening **many** files without the index is what we eliminate.

Pairs with [multi-document-dev-plan.md](multi-document-dev-plan.md): embeddings upgrade the **outer** tier; inner read tools unchanged.

### Thematic clustering (future)

K-Means on document-level vectors to group files by topic without manual folders.

### Synthesis and gap analysis (research)

Compare document vectors to find "semantic delta" — what is in document A but missing from draft B.

---

## Future optimizations {#future-optimizations}

Try these **only when profiling on multi-file corpora** shows IPC NumPy search or encode latency is insufficient. MVP stays on warm-worker Pickle5 IPC ([Development plan](#development-plan)).

### Dedicated embeddings worker {#future-dedicated-worker}

Same idea as [Open idea: dedicated embeddings worker](#dedicated-embeddings-worker) in the dev plan: second `PythonWorkerManager` (embeddings-only) so Calc `=PYTHON()` is not queued behind a ~1 s batch embed. Same venv, same protocol — process isolation only.

### Choosing a search backend {#choosing-a-search-backend}

| Scenario | Default | Fallback / later |
|----------|---------|------------------|
| Single doc / folder, hundreds–few k chunks | sqlite-vec `vec0` KNN in venv | NumPy dot ([Search fallback](#search-fallback)) |
| Large corpus, 5k+ chunks | sqlite-vec `vec0` | HNSW in venv (research) |
| No venv | HTTP embed + stdlib loop on host | Cython top-k |

| Approach | Role | Notes |
|----------|------|-------|
| **Venv + sqlite-vec** | **Default** persist + search | `vec0` in same `index.db` as locators |
| **Venv + NumPy (IPC)** | **Fallback** when sqlite-vec missing | Shipped bench path; sub-ms at N≈350 |
| **Host Cython top-k** | Optional in-process search | [`writeragent_vec_search`](#cython-surface-area) |
| **Parallel FTS + embeddings** | **Don't** | Double cache |

### Host Cython `top_k_dot` {#cython-surface-area}

Mirror [`writeragent_vec`](../native/writeragent_vec/) — one hot function: scan row-major normalized float32 vectors, top-k by dot product. Layout: `native/writeragent_vec_search/` → `plugin/contrib/vec_search/`. Wire with `try: import writeragent_vec_search` and stdlib fallback.

### sqlite-vec in venv {#sqlite-vec-in-venv}

**Primary storage and search** — see [Corpus storage](#corpus-storage) and [Installing sqlite-vec](#installing-sqlite-vec). `sqlite-vec` indexes floats you already have — it does **not** embed text. User `pip install sqlite-vec` in the configured venv; do **not** vendor into OXT or LO process. See [sqlite-vec Python docs](https://alexgarcia.xyz/sqlite-vec/python.html).

### ONNX runtime

`onnxruntime` + exported ONNX weights can shrink dependencies vs full PyTorch for a **fixed** model. Defer — batched `sentence-transformers` is already fast enough ([Benchmark](#benchmark-on-your-machine)).

### HNSW and hnsw-lite {#hnsw-and-hnsw-lite}

Approximate nearest neighbor for bounded in-RAM subsets — not for full corpus streaming search on disk. PyPI: `hnsw-lite`. Rebuild from stored vectors on load; do not persist graphs by default.

### Advanced research

- Document-level vectors, K-Means clustering, semantic “gap analysis” between drafts
- Optional dedicated worker `action` for embed/search (see [Trusted extension code in the venv](enabling_numpy_in_libreoffice.md#trusted-extension-code-in-the-venv)) if stub overhead matters

---

## Related docs

| Topic | Doc |
|-------|-----|
| Cython build matrix | [cython-extension.md](cython-extension.md) |
| Venv / NumPy boundary | [enabling_numpy_in_libreoffice.md](enabling_numpy_in_libreoffice.md) |
| Multi-file discovery | [multi-document-dev-plan.md](multi-document-dev-plan.md) |
| Chat memory / summarization | [langchain-plan.md](langchain-plan.md) |
| Realtime grammar / hash patterns | [realtime-grammar-checker-plan.md](realtime-grammar-checker-plan.md) |
| User profile memory | [agent-memory-and-skills.md](agent-memory-and-skills.md) |
