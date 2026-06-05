# Engineering Design: Lightweight Vector Search in LibreOffice

**Author**: Antigravity AI (original); KeithCu / WriterAgent (2026-06 stack update)
**Date**: April 2, 2026 (updated June 2026)
**Target Audience**: Python Experts / Vector Novices

> **See also:** [langchain-plan.md](langchain-plan.md) (Phase 4 RAG), [enabling_numpy_in_libreoffice.md](enabling_numpy_in_libreoffice.md) (venv compute bridge), [cython-extension.md](cython-extension.md) (host-side Cython for tight loops — no NumPy in LO).

---

## Recommended stack (2026-06)

WriterAgent **already** runs NumPy and scientific Python **only in a user venv subprocess** (`PythonWorkerManager`). LibreOffice’s embedded interpreter must **not** import NumPy or load SQLite vector extensions — ABI crashes and `enable_load_extension` gaps (especially macOS) make in-process vector search a poor default.

### Decision summary

| Approach | Verdict | Notes |
|----------|---------|-------|
| **Vector search in user venv** (extend warm worker or thin RPC) | **Recommended** | Reuse `scripting.python_venv_path`; `pip install sqlite-vec numpy` in that venv; index DB under config dir |
| **Separate “vector-only” subprocess** | **Optional** | Same venv binary; only worth a dedicated long-lived worker if index load latency dominates (large sqlite DB). Otherwise extend existing worker protocol |
| **Vendoring `sqlite-vec` into the OXT / LO process** | **Not recommended** | Per-OS `.so` wheels, SQLite version coupling, macOS extension blocking; duplicates venv path users already configure |
| **Cython cosine / top-k in LO host** | **Strong no-venv fallback** | Ship tagged `.so` in `plugin/contrib/` (same ABI matrix as audio / `writeragent_vec`); streaming dot-product over mmap’d float32 — no NumPy, no `sqlite-vec` load in LO. See [cython-extension.md](cython-extension.md) |
| **Pure-Python cosine in LO process** | **Last-resort fallback** | Stdlib `struct` + loop when Cython tag missing; OK for &lt; ~1k chunks |
| **LangChain vectorstores / community** | **Skip as dependency** | Vendor **patterns** only (splitter, serializer); see [langchain-plan.md](langchain-plan.md) |

### Split responsibilities (recommended)

```
┌─────────────────────────────────────────────────────────────┐
│ LibreOffice host (embedded Python — stdlib + optional Cython) │
│  • HTTP embedding API (OpenRouter / Together / Ollama)      │
│  • Chunk text + metadata in sqlite3 (FTS5 optional)         │
│  • writeragent_vectors.db path next to writeragent.json     │
│  • No venv: Cython top-k over binary vectors (fallback: py) │
│  • On send: embed query → venv RPC or host Cython → inject  │
└───────────────────────────┬─────────────────────────────────┘
                            │ JSON lines (extend worker protocol)
┌───────────────────────────▼─────────────────────────────────┐
│ User venv subprocess (any Python 3.x user configures)        │
│  • numpy — batch dot products, normalize vectors            │
│  • sqlite-vec — vec0 virtual tables, cosine KNN in C/SIMD   │
│  • optional hnsw-lite for in-RAM ANN on “recent” subset       │
└─────────────────────────────────────────────────────────────┘
```

**Embeddings (inference)** stay on the **host**: one small HTTP client reusing `get_api_config` — same story as Phase 4 in [langchain-plan.md](langchain-plan.md). **`sqlite-vec` does not embed text**; it only indexes float vectors you already have.

**Indexing (search)** runs in the **venv**: pass query vector + DB path; return top-k `(chunk_id, score)` JSON to the host; host resolves chunk text from its metadata table.

### FAQ: Do I need to vendor SQLite? Different wheels per Python version?

**Short answers**

| Question | Answer |
|----------|--------|
| **Vendor SQLite itself?** | **No.** Python’s stdlib `sqlite3` already embeds/links a SQLite library. You open `sqlite3.connect(path)` and optionally load extensions into that connection. There is no separate SQLite package to ship in the OXT. |
| **Vendor `sqlite-vec`?** | **Not on the recommended path.** User runs `pip install sqlite-vec` in their **venv**. You only “vendor” if you insist on in-process search in LO — we **don’t** recommend that. |
| **Different `sqlite-vec` builds per Python 3.11 / 3.12 / 3.13?** | **No** (for PyPI wheels). The package publishes **`py3-none-*`** wheels: one native `vec0` binary **per OS/CPU**, not per CPython minor. The same `manylinux2014_x86_64` wheel works in a 3.11 venv and a 3.14 venv on that machine. |
| **Must the venv Python match LibreOffice’s embedded Python?** | **No.** Venv is a separate interpreter. LO can embed 3.11 while the venv is 3.12; `sqlite-vec` installs into whichever `python` owns that venv. |
| **What *does* vary by Python version?** | **Host Cython** modules (`writeragent_vec`, future `writeragent_vec_search`): those use **`cp311` / `cp312` / …** tags like audio’s cffi — see [cython-extension.md](cython-extension.md). That is unrelated to `sqlite-vec` wheel tags. |
| **What varies by platform?** | **`sqlite-vec`:** `manylinux_*`, `macosx_*`, `win_*` (and arch: x86_64, aarch64, …). User’s `pip` picks the right wheel on install — you don’t ship a matrix in the OXT. |
| **Hidden coupling (not Python version)** | The interpreter’s **`sqlite3` must support `enable_load_extension`** and ideally SQLite **≥ 3.41**. That depends on **how that Python was built**, not on `sqlite-vec`’s wheel tag. macOS system Python often fails here; Homebrew/pyenv venvs usually work ([sqlite-vec Python docs](https://alexgarcia.xyz/sqlite-vec/python.html)). |

**Three storage/search layers (don’t conflate them)**

| Layer | What it is | Vendor? | Per-Python-minor wheels? |
|-------|------------|---------|---------------------------|
| **Host metadata DB** | stdlib `sqlite3`, chunk text, FTS5, no vector extension | No — already in LO Python | N/A (stdlib) |
| **Vector index (recommended)** | `sqlite-vec` in **user venv** via `pip` | No — user installs | **No** — `py3-none` per platform |
| **Vector search without venv** | Cython top-k over binary float32 file on host | Yes — contrib `.so` like audio | **Yes** — `cp311`, `cp312`, … per [cython-extension.md](cython-extension.md) |

**If you ignored the recommendation and vendored `sqlite-vec` into the OXT anyway:** you would copy `vec0.so` (or equivalent) from the PyPI wheel per **platform**, still not per Python minor — but you would *also* need LO’s embedded `sqlite3` to support extension loading, which is the fragile part. That is why venv + `pip` is simpler.

### `sqlite-vec` in the venv vs vendoring into the extension

| Question | Answer |
|----------|--------|
| LO embedded `sqlite3` for vectors? | Irrelevant if search runs in venv. Host metadata DB uses stdlib `sqlite3` only (no `sqlite-vec`). |
| Vendoring the Python package into OXT? | Unnecessary on the recommended path; duplicates platform packaging work you already avoid for NumPy. |

### Worker integration options

1. **Extend `run_code_in_user_venv`** — add whitelisted helpers / a `vector_search` script template the tool loop calls (simplest; cold start amortized by warm worker).
2. **New host API** — `search_document_vectors(ctx, query_embedding, k)` → one JSON RPC line to worker, no LLM-visible Python.
3. **Dedicated vector worker** — second persistent subprocess only if profiling shows reload cost &gt; query cost; share the same `scripting.python_venv_path`.

**Do not** add `sqlite3` to the venv sandbox whitelist for arbitrary LLM scripts unless you intend user-authored index access; keep vector RPC on a **fixed host module** invoked from the tool loop.

### Tiered behavior

| User config | Search backend |
|-------------|----------------|
| Venv + `sqlite-vec` installed | `vec0` KNN in venv + optional FTS5 hybrid on host |
| Venv + NumPy only | NumPy batch cosine in venv over mmap’d float32 file |
| No venv + Cython extension available | Host Cython streaming top-k (normalized float32 file); `try: import writeragent_vec_search` → stdlib fallback — [cython-extension.md](cython-extension.md) |
| No venv, no Cython tag | Pure-Python streaming top-k (slow) |
| No venv + tiny store | In-memory dict at index time (dev / tests) |

**Cython vs venv:** Cython accelerates **host-side** brute-force KNN when the user has not configured a venv — it does **not** replace `sqlite-vec` for large corpora. Prefer venv + `sqlite-vec` when `scripting.python_venv_path` is set; use Cython so RAG still works offline without asking users to create a venv first. Same packaging rules as `writeragent_vec`: per-ABI `.so` in contrib, no UNO from C, no in-process NumPy.

### What to build first

1. **Recursive character chunker** — vendor MIT `RecursiveCharacterTextSplitter` logic (~100 lines), no langchain package.
2. **Host metadata schema** — `(chunk_id, doc_url, doc_revision, text, embedding_model, byte_offset)` in stdlib SQLite; vectors in sidecar file or venv-managed `vec0` DB.
3. **Embedding client** — one HTTP function, config key `embedding_model`.
4. **Venv search RPC** — normalize query vector, `sqlite_vec.load(conn)`, `MATCH` top-k.
5. **Inject retrieved chunks** beside existing `[DOCUMENT CONTENT]` block (cap total injected chars).

---

## 1. Abstract
When building a "Chat with Document" feature for LibreOffice, the core challenge is **Retrieval**: how do we find the *relevant* 200 words in a 200-page document to send to the LLM?

Traditional keyword search (CTRL+F / BM25) fails when the user's vocabulary differs from the document's. This document outlines a cross-platform, dependency-light strategy for **Vector Similarity Search** using the standard Python library and a ~1MB SQLite extension (`sqlite-vec`).

## 2. The Vector Search Primitive (for Pythonistas)

### 2.1 What is an Embedding?
Think of an LLM Embedding as a "Meaning Signature." It is a fixed-length list of floating-point numbers (e.g., 1536 floats) that represents a chunk of text in a multi-dimensional space.

In this space:
- "The dog is barky" and "Canine vocalization" are **close together**.
- "The dog is barky" and "Pythons are interpreted languages" are **very far apart**.

### 2.2 The Math of "Closeness"
To find if two sentences are similar, we don't compare words; we compare **angles**. If the 1536-dimensional vectors are pointing in roughly the same direction, the sentences have similar meanings.

- **Dot Product**: Multiply the values at each index and sum them up. 
- **Cosine Similarity**: The dot product of two **normalized** vectors (vectors with a length of 1.0).

> [!NOTE]
> **Optimization Trick**: If we normalize our vectors *once* when we receive them from the LLM, the expensive "Cosine Similarity" formula simplifies to a lightning-fast "Dot Product."

## 3. The Deployment Dilemma: The "NumPy Tax"

Usually, Python developers reach for `numpy` for vector math. However, for a LibreOffice extension (`.oxt`), NumPy carries a heavy "tax":
- **Binary Size**: ~50–100MB per platform.
- **Complexity**: Packaging NumPy for Windows, macOS (Intel + Silicon), and Linux (x86 + ARM) inside a single extension is a maintenance nightmare.

**WriterAgent’s solution (shipped):** NumPy runs **only in the user venv subprocess** — see [enabling_numpy_in_libreoffice.md](enabling_numpy_in_libreoffice.md). Vector search should follow the **same boundary**: host orchestrates, venv computes.

**For vector indexing specifically:** prefer a specialized **vector engine** (`sqlite-vec`) in that venv rather than shipping raw NumPy loops in the OXT. The extension stays stdlib-only in-process.

## 4. The `sqlite-vec` Breakthrough

`sqlite-vec` is a modern, lightweight C-extension for SQLite. It is the spiritual successor to the older `sqlite-vss`. 

### 4.1 Key Features:
- **Tiny Footprint**: ~1MB per OS binary.
- **Native SQL Syntax**: You search vectors using `SELECT` statements.
- **Specialized Storage**: It stores vectors in a compact, bit-packed format in `BLOB` columns.
- **Support for Hybrid Search**: It is compatible with SQLite's FTS5 (Full Text Search) for combining keyword and vector results.

### 4.2 Why this is a "Porsche" for extensions:
Unlike NumPy, which runs in the Python interpreter's loop, `sqlite-vec` performs the vector math in **optimized C loops with SIMD (Single Instruction, Multiple Data) acceleration** directly inside the database engine. It can scan 10,000 vectors in a fraction of a millisecond.

### 4.3 The Generation Gap: Search vs. Inference
It is critical to note that **`sqlite-vec` does not create vectors**. 

In the AI pipeline, there are two distinct steps:
1.  **Inference (Generation)**: An LLM or Embedding Model takes a sentence (String) and converts it into a list of floats (Vector).
2.  **Indexing (Search)**: A Vector Database (like `sqlite-vec`) takes those floats and performs high-speed comparisons.

The `sqlite-vec` extension assumes you are providing the floats. For a lightweight LibreOffice extension, the most efficient path is calling a remote LLM API (Gemini, OpenAI) for the inference step, then using `sqlite-vec` for the local indexing step.

## 5. How it works in Python

You don't need a new library. You use the built-in `sqlite3` module:

```python
import sqlite3

# 1. Connect to the database
conn = sqlite3.connect("document_vectors.db")

# 2. Load the lightweight extension
conn.enable_load_extension(True)
conn.load_extension("./vec0") # The ~1MB binary

# 3. Create a Vector Virtual Table
conn.execute("CREATE VIRTUAL TABLE vec_chunks USING vec0(embedding float[1536])")

# 4. Search by meaning
# The 'vec_distance_cosine' function is provided by the C extension
results = conn.execute("""
    SELECT doc_id, text_content 
    FROM vec_chunks 
    WHERE embedding MATCH ? 
    ORDER BY distance 
    LIMIT 5
""", [query_embedding])
```

## 6. Hybrid Search: The Secret Sauce

In a real-world document, users often search for specific terms (acronyms, names, product codes) that an embedding model might not "understand" deeply. This is where **Hybrid Search** wins.

### 6.1 The Two Pillars
1.  **BM25 (Keyword Search)**: Measures how often a specific word (e.g., "TX-900") appears in a chunk. It is highly precise for exact matches.
2.  **Semantic (Vector Search)**: Measures how similar the *concept* is (e.g., "The latest hardware" vs. "TX-900"). It is broad and covers paraphrasing.

### 6.2 The "Reciprocal Rank Fusion" (RRF) Strategy
To combine these, we don't just "add" the scores (since they are in different units). Instead, we use RRF:
- We run both searches.
- We look at the top results for both.
- A result that appears in the top 3 of **both** searches gets a massive "boost" in the final ranking.

**The Benefit**: If a user searches for "How do I fix the TX-900?", the keyword search finds the manual page for "TX-900", and the vector search finds the section about "fixing hardware." The hybrid result brings the exact correct page to the top.

## 7. The "Everything Else" (WriterAgent Roadmap)

Integrating this into `WriterAgent` involves three "non-vector" primitives that we must implement:

1.  **Semantic Chunking**: A text-parsing strategy that splits LibreOffice paragraphs into ~500-character windows, ensuring we don't split a sentence in the middle.
2.  **Versioning**: Embedding models change. We need a schema that allows us to re-index a document if the model (e.g., from OpenAI to Gemini) is swapped.
3.  **The Fallback**: **Cython** streaming top-k on the host when no venv is configured ([cython-extension.md](cython-extension.md)); pure-Python `dot_product` when the tagged `.so` is missing; in the **venv** without `sqlite-vec`, NumPy batch cosine.

**Chat history vs document RAG:** Sidebar **conversation history** is already persisted (`writeragent_history.db`) — that is **not** vector search. RAG here means **retrieving document chunks** (and optionally cross-document corpora) when the fixed 8k `[DOCUMENT CONTENT]` excerpt is insufficient. See [langchain-plan.md § What is still worth doing](langchain-plan.md#what-is-still-worth-doing-next).

## 8. Local Inference (The "Offline" Option)

If the 4MB footprint constraint is ever relaxed to **~100MB**, we can implement fully local embedding generation. This removes API latency and costs.

### The "Tiny-Runtime" Stack:
- **Engine**: `onnxruntime-cpu` (~15-20MB). This is the fastest, leanest way to run local models without `torch` or `tensorflow`.
- **Model**: `all-MiniLM-L6-v2` (ONNX format). This is the gold standard for "fast and small" local embeddings (~45MB–90MB depending on precision).
- **The Process**: Python pulls the text from Writer -> Passes it to `onnxruntime` -> Receives the 384-dimensional vector -> Saves it to `sqlite-vec`.

## 9. Conclusion
Vector search in LibreOffice doesn't require a 100MB dependency bundle. By leveraging the built-in SQLite engine and a tiny, specialized C extension, we can provide industry-standard "Meaning Search" with a negligible impact on the extension's size and performance.

This turns `WriterAgent` from a simple wrapper UI into a powerful **Local Knowledge Base** for the user's documents.

## 10. Multi-Document Intelligence: Beyond "Similar Paragraphs"

The true "killer app" for vector search in LibreOffice is not just finding a similar sentence in the *current* file; it's understanding a **global corpus of documents**.

### 10.1 The Universal Semantic Index
By indexing every document the user opens or saves into a single `sqlite-vec` database, we enable:
- **Global Q&A**: "Across all my documents, what is our policy on remote work?"
- **Cross-File Discovery**: While writing "Project_X_Proposal.odt", the sidebar can automatically suggest: *"You wrote a similar section in '2025_Budget_Plan.ods' last year."*

### 10.2 Thematic Clustering
Since vectors are coordinates in a "Meaning Space," we can use standard clustering algorithms (like K-Means) to automatically group documents by topic.
- A user with 1,000 files can suddenly see them categorized into "Invoices," "Design Specs," and "Personal Notes" without ever creating a folder.

### 10.3 Synthesis & Gap Analysis
By comparing the vectors of two different documents, we can perform **Synthesis**:
- "What information is in Document A that is missing from my draft (Document B)?"
- Vector math can identify the "Semantic Delta" between files, helping the user ensure consistency across a large project.

## 11. The Recursive Splitter: Vetted Implementation

The most critical part of the "Everything Else" roadmap is the text splitter. A naive split by character index will cut words in half, destroying the embedding's meaning. 

To ensure stability and handle complex edge cases (e.g., massive paragraphs without punctuation), we recommend adapting the **RecursiveCharacterTextSplitter** from the FOSS **LangChain** ecosystem. This implementation has been battle-tested on millions of documents and is MIT licensed.

### Where to Grab the Code:
- **Repository**: [langchain-text-splitters (GitHub)](https://github.com/langchain-ai/langchain/tree/master/libs/text-splitters/langchain_text_splitters)
- **Key File**: `recursive_character.py` (Look for the `RecursiveCharacterTextSplitter` class).
- **The Core Logic**: It recursively attempts to split text using a prioritized set of separators: `["\n\n", "\n", " ", ""]`. If a chunk exceeds the `chunk_size`, it tries the next separator in the list.

### Why use the "Standard" version:
1.  **Paragraph Integrity**: It prioritizes keeping double-newlines (`\n\n`) together to preserve atomic ideas.
2.  **Smart Recombination**: After splitting, it smartly recombines pieces into the largest possible chunks that still fit within your size limit.
3.  **Proven Overlap Support**: Its `chunk_overlap` logic ensures that context from one chunk is correctly "bridged" into the next, which is vital for search accuracy.

## 12. Conclusion
Vector search in LibreOffice doesn't require a 100MB dependency bundle. By leveraging the built-in SQLite engine and a tiny, specialized C extension, we can provide industry-standard "Meaning Search" with a negligible impact on the extension's size and performance.

This turns `WriterAgent` from a simple wrapper UI into a powerful **Local Knowledge Base** for the user's documents.
