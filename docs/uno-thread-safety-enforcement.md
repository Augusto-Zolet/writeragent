# Enforcing UNO Main-Thread Safety & Deadlock Prevention (Compile / Test / Run time)

## 1. The Problem We Are Trying to Kill

LibreOffice's internal architecture is written in C++ and relies heavily on VCL (Visual Class Library) and the UNO (Universal Network Objects) component model. **LibreOffice's VCL/UNO layer is strictly single-threaded.**

When Python code running in the WriterAgent extension touches a PyUNO object from a background worker thread, catastrophic and erratic failures occur:
- **C++ Memory Corruption & Crashes**: Concurrent invocation of UNO interfaces corrupts internal reference counters and dispatch tables.
- **Visual Glitches**: Concurrent UI operations cause the VCL rendering pipeline to draw black menus, blank sidebars, or freeze desktop windows.
- **Deadlocks (Lock Inversion)**: A background worker thread making a blocking UNO call can take an internal C++ solar mutex or dispatch lock while LibreOffice's main thread is waiting on the worker, deadlocking the entire office suite without a Python traceback.

See [`docs/threading_architecture.md`](threading_architecture.md) and [`docs/streaming-and-threading.md`](streaming-and-threading.md) for the core architectural model: **worker threads perform network I/O, heavy LLM processing, and subprocess IPC; all PyUNO interactions are marshalled back to the main UI thread via [`execute_on_main_thread`](../plugin/framework/queue_executor.py) or [`post_to_main_thread`](../plugin/framework/queue_executor.py).**

### Why Concurrency Bugs Are "Whack-a-Mole"
Historically, threading bugs in this codebase were uncovered only after mysterious production hangs:
- **Timing & Doc-Size Dependent**: Race conditions often do not reproduce on a developer's machine with small documents, but reliably deadlock on large documents or slower machines under GIL contention.
- **No Stack Traces**: When two threads deadlock, neither crashes; the process simply stops responding, leaving no stack trace or error log at the offending call site.
- **Test Invisibility**: Standard unit tests mock UNO calls, and `QueueExecutor` runs inline under `WRITERAGENT_TESTING=1`, meaning unit tests never exercise real thread boundary crossings.

**The Goal**: Make any off-main-thread UNO violation and any synchronous host-dispatch deadlock fail **loudly, deterministically, and immediately** — at author time via linters, in CI via thread-affine mocks, and at runtime via viral proxies — instead of surfacing as rare production deadlocks.

---

## 2. Why Formal Verification (CrossHair / deal) Does Not Help Here

It is critical to understand why our formal verification toolchain ([`docs/formal_verification.md`](formal_verification.md)) cannot solve this problem:

- `deal` and CrossHair prove **value-level properties of pure, single-threaded functions** (e.g. "for all integer inputs $x > 0$, $f(x)$ returns a non-empty string").
- CrossHair executes functions under symbolic execution **in a single thread**. It models neither operating system threads, the Python GIL, nor UNO's C++ thread-affinity constraints. There is no `@deal.pre` contract that can express "this PyUNO object pointer may only be dereferenced from `threading.main_thread()`."
- **Thread affinity is an effect / typestate property** ("which thread is the CPU executing on when this instruction runs"), not a data value property.

The proper computer science model for thread affinity is **Function Coloring** (analogous to `async`/`await` in JavaScript/Python or `Send`/`!Send` in Rust):
- **Red functions** are Main-Thread-Only (PyUNO, UI, document mutations).
- **Blue functions** are Background Worker contexts (I/O, LLM requests, venv IPC).
- **Yellow functions** are Synchronous Host/Bridge Dispatches (Calc `=PY()` / `=PROMPT()`, UNO event listeners, remote PyUNO calls).

A Blue context may only transition to Red across an explicit recoloring boundary (`execute_on_main_thread`). A Yellow context is forbidden from calling blocking Red boundaries. This discipline is enforced through a combination of **runtime tripwires, thread-affine test fixtures, and static taint analysis**.

---

## 3. Function Coloring & Concurrency Architecture

```
  ┌─────────────────────────────────────────────────────────────┐
  │                           RED                               │
  │                  (Main-Thread / UNO)                        │
  │  - PyUNO services & objects (ctx, desktop, doc models)      │
  │  - UI controllers, frames, windows, dialogs                │
  │  - Document modifications (format, insert, styles)          │
  └──────────────────────────────▲──────────────────────────────┘
                                 │
     recoloring boundary via     │   ILLEGAL from Yellow Context
     execute_on_main_thread()    │   (Deadlock Hazard #402)
                                 │
  ┌──────────────────────────────┴──────────────────────────────┐
  │                           BLUE                              │
  │                   (Background Workers)                      │
  │  - HTTP requests & LLM streaming                            │
  │  - File I/O, local caching, embeddings computation          │
  │  - Subprocess IPC (venv worker, audio recorder)             │
  └─────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │                          YELLOW                             │
  │           (Synchronous Host/Bridge Dispatch)                │
  │  - Calc add-in formula eval: =PY(...), =PROMPT(...)         │
  │  - UNO Event Listeners (actionPerformed, textChanged, ...)  │
  │  - Remote PyUNO bridge dispatches & XJob triggers           │
  │                                                             │
  │  INVARIANT: May run on worker threads while main thread is  │
  │  synchronously waiting. MUST NOT block on main thread!      │
  └─────────────────────────────────────────────────────────────┘
```

### The Three Concurrency Colors

| Color | Context / Target | Permitted Operations | Forbidden Operations |
|---|---|---|---|
| **RED** | LibreOffice Main UI Thread | Direct PyUNO calls, UI dialogs, document reads/edits, VCL pump. | Long-running blocking network calls or CPU-heavy loops (freezes UI). |
| **BLUE** | Background Workers (`run_in_background`) | Network I/O, LLM calls, venv IPC, disk access. | Direct PyUNO access (must marshal to Red via `execute_on_main_thread`). |
| **YELLOW** | Synchronous Host Dispatch (Calc Add-ins, Listeners) | In-memory computation, venv execution, non-blocking `post_to_main_thread`. | Calling `execute_on_main_thread` (deadlocks against waiting main thread). |

### The Two Foundational Facts That Make Enforcement Tractable

1. **Background threads have a single birthplace**:
   All background work in WriterAgent is spawned through [`run_in_background`](../plugin/framework/worker_pool.py) (or a strictly allowlisted set of dedicated server/reader loops: `AsyncProcess` pipes, MCP server daemon, venv worker).
2. **UNO objects have a finite set of sources**:
   All PyUNO objects originate from the factory getters in [`plugin/framework/uno_context.py`](../plugin/framework/uno_context.py) (`get_ctx`, `get_desktop`, `get_toolkit`, `get_active_document`, `get_package_info`) and document model resolvers in [`plugin/doc/document_helpers.py`](../plugin/doc/document_helpers.py).

By wrapping the sources and tagging the birthplaces, we achieve complete defense-in-depth across three enforcement layers:

---

## 4. Layer A — Runtime Tripwire & Viral Proxy (Catch Immediately on Dev Machine)

**Status:** Shipped in [`plugin/framework/thread_guard.py`](../plugin/framework/thread_guard.py).
**Configuration**: Active by default in all dev and non-release builds (`WRITERAGENT_UNO_THREAD_GUARD=1`). Opt-out via `WRITERAGENT_UNO_THREAD_GUARD=0`.

Layer A converts what would be a silent race condition or production freeze into an **immediate exception with a complete Python stack trace** pointing directly at the offending line.

### A1. Reusable Assert & `@main_thread_only` Decorator
```python
def assert_main_thread(what: str) -> None:
    """Raise (if guard on) or log warning+stack (if guard off) when off the main thread."""
    if on_main_thread():
        return
    task = get_background_task_name() or threading.current_thread().name
    msg = "UNO thread violation: %r touched UNO from background task %r; marshal via execute_on_main_thread()." % (what, task)
    if GUARD_ON:
        _notify_thread_violation(msg)
        raise RuntimeError(msg)
    log.warning(msg, stack_info=True)
```
- Decorates primary UNO entry points (`get_desktop`, `get_active_document`, `confirm_unsaved_cell_edit`, etc.).
- When `GUARD_ON` is active, displays a deduplicated modal error box on the UI thread (dev builds only) and raises `RuntimeError`.
- When `GUARD_ON` is inactive (field/release builds), logs `log.warning(msg, stack_info=True)` so call sites are captured in logs without crashing user sessions.

### A2. Thread Tagging at Birth
In `run_in_background`, a thread-local task name is stamped on the worker thread for the duration of the task. Pooled workers (`wa-bg-*`) clear the tag in a `finally` block so recycled threads do not carry stale task identifiers. The runtime error message explicitly names the culprit task (e.g. `"touched UNO from background task 'web-search-embeddings'"`).

### A3. Viral Guarding Proxy (`_UnoThreadGuardProxy` / `guard_uno`)
Decorators only guard functions we remember to decorate. To protect arbitrary UNO object graphs (such as `doc.getCurrentController().getViewCursor().getText().getEnd()`), all UNO sources wrap returned objects in `_UnoThreadGuardProxy`:
1. On every attribute lookup (`__getattr__`), method call (`__call__`), property setter (`__setattr__`), item lookup (`__getitem__`), and interface query (`queryInterface`), the proxy invokes `assert_main_thread(...)`.
2. Any PyUNO object returned by an attribute access or method call is **recursively wrapped** in another `_UnoThreadGuardProxy`. Plain Python values (strings, integers, booleans, lists) pass through untouched.
3. If a guarded proxy is passed back into a property setter on a UNO object, the proxy automatically unwraps itself (`_unwrap_uno`) to prevent wrapping overhead from leaking into LibreOffice C++.

### A4. Yellow Context Refusal (`sync_host_dispatch`)
When Calc evaluates an add-in formula like `=PY("1+1")` or `=PROMPT(...)` via a remote PyUNO bridge, or when LibreOffice invokes a UNO listener callback, execution occurs in a **Yellow Context**:
- Managed via `@contextmanager def sync_host_dispatch()` and `def in_sync_host_dispatch() -> bool`.
- Inside `QueueExecutor.execute()`, if `in_sync_host_dispatch()` is True on a non-main thread, execution is **refused immediately** with:
  ```
  RuntimeError: marshal refused: execute_on_main_thread called from synchronous host dispatch context (deadlock hazard #402, fn=...)
  ```
- This completely eliminates 30-second timeouts and lock inversions.

---

## 5. Layer B — Test-Time Enforcement & Determinism

**Status:** Shipped in [`tests/framework/thread_safety.py`](../tests/framework/thread_safety.py) and [`tests/framework/test_thread_affinity.py`](../tests/framework/test_thread_affinity.py).

### B1. Real PyUNO Test Suite with Active Guard (`make lo-test-threadguard`)
Native UNO tests (`plugin/testing_runner.py`) run against a live LibreOffice instance with real C++ PyUNO objects. `make lo-test-threadguard` executes the full suite with `WRITERAGENT_UNO_THREAD_GUARD=1`:
```make
lo-test-threadguard:
	WRITERAGENT_UNO_THREAD_GUARD=1 $(LO_PYTHON) -m plugin.testing_runner; \
	EXIT_CODE=$$?; $(MAKE) lo-kill; exit $$EXIT_CODE
```
Any worker thread that reaches a real UNO object without marshalling aborts the test with a stack trace.

### B2. Pytest Thread-Affine Mocks & Synthetic Pump (`uno_thread_safety` Fixture)
For fast CI tests where LibreOffice is not running:
1. `make_thread_affine_mock(raw_mock)` wraps unit test mocks in a `ThreadAffineMock` that asserts access is only made from the designated main thread.
2. `set_designated_main_thread(pump_thread)` instructs `thread_guard.on_main_thread()` to follow a synthetic test pump thread.
3. `set_force_marshal_mode(True)` disables the `WRITERAGENT_TESTING=1` inline shortcut, forcing `QueueExecutor.execute` to enqueue real `_WorkItem` objects and block until the `TestMainPump` thread drains the queue.
4. If a worker touches a mock directly without `execute_on_main_thread()`, the mock immediately raises `AssertionError`, turning concurrency bugs into deterministic red CI tests.

### B3. Concurrency Regression Test Suite
- `test_yellow_context_refuses_execute_on_main_thread`: Asserts immediate `RuntimeError` when off-main host dispatch attempts blocking marshal.
- `test_yellow_context_allows_inline_when_on_main_thread`: Asserts GUI formula evaluation on main thread executes inline without errors.
- `test_notify_thread_violation_never_blocks`: Asserts guard violation reporting uses non-blocking `post_to_main_thread`.
- `test_charts_process_events_regression_must_marshal`: Prevents regressions of the chart event loop hang (commit `0cfc6891`).

---

## 6. Layer C — Build-Time Static Analysis & Linters

Executed automatically via **`make test`** and **`make uno-thread-lint`** (**`make opengrep-lint`** + **`make thread-safety-lint`**).

```
                      ┌────────────────────────┐
                      │    make uno-thread-lint │
                      └───────────┬────────────┘
                                  │
         ┌────────────────────────┴────────────────────────┐
         │                                                 │
┌────────▼───────────────┐                     ┌───────────▼────────────┐
│   make opengrep-lint   │                     │ make thread-safety-lint│
│ (tests/semgrep/*.yml)  │                     └───────────┬────────────┘
└────────────────────────┘                                 │
                                   ┌───────────────────────┴───────────────────────┐
                                   │                                               │
                      ┌────────────▼───────────────┐                  ┌────────────▼───────────────┐
                      │ scripts/lint_thread_safety │                  │ scripts/analyze_thread_     │
                      │ (AST structural visitor)   │                  │  deadlocks.py (Call Graph) │
                      └────────────────────────────┘                  └────────────────────────────┘
```

### C1. Opengrep Taint Analysis ([`tests/semgrep/uno_thread_safety.yml`](../tests/semgrep/uno_thread_safety.yml))
Uses `opengrep scan --taint-intrafile` to track cross-function dataflow within files:
- **Blue Roots (Taint Sources)**: Functions decorated with `@background`, worker functions passed to `run_in_background()`, and add-in entry points.
- **Red Sinks (UNO Operations)**: `uno_context` getters, `createUnoService`, `createInstanceWithContext`, `uno.getComponentContext`, document format/edit helpers.
- **Sanitizers**: `execute_on_main_thread()`, `post_to_main_thread()`, and enclosing `if on_main_thread():` branches.
- **Core Rules**:
  - `uno-off-main-thread` (ERROR): Flags direct UNO access in background workers.
  - `raw-uno-thread-ban` (ERROR): Rejects raw `threading.Thread`/`Timer` instantiation outside approved subsystems.
  - `blocking-marshal-in-sync-dispatch` (ERROR): Rejects `execute_on_main_thread` inside add-in evaluations and synchronous callbacks.
  - `raw-process-events-to-idle` (ERROR): Rejects direct VCL event pumps outside approved queue drain points.

### C2. Custom AST Linter ([`scripts/lint_thread_safety.py`](../scripts/lint_thread_safety.py))
Parses Python ASTs across add-in and scripting boundary modules to enforce:
1. `unguarded-uno-access`: UNO source getters (`get_desktop`, `get_ctx`, `_get_calc_doc`) must be structurally protected by an `if on_main_thread():` block or `@main_thread_only` decorator.
2. `blocking-marshal-in-sync-dispatch`: Synchronous add-in functions (`execute_python_addin`, `execute_prompt_addin`, `session_key`) cannot contain calls to `execute_on_main_thread`.

### C3. Static Lock Hierarchy & Transition Analyzer ([`scripts/analyze_thread_deadlocks.py`](../scripts/analyze_thread_deadlocks.py))
Builds a global function call graph across `plugin/` starting from `SYNC_HOST_ENTRYPOINTS` (`execute_python_addin`, `execute_prompt_addin`, `py`, listener callbacks like `actionPerformed`, `textChanged`, `disposing`, `trigger`).
- Walks call edges to detect if any synchronous host dispatch can reach `BLOCKING_OPERATIONS` (`execute_on_main_thread`).
- Uses a curated `GENERIC_METHOD_NAMES` filter to prevent false-positive call graph edges on common method names (`get`, `set`, `dispatch`, `forward`, `handle`, `step`).

---

## 7. Infection-Start Chokepoints (Layer A Reference)

All UNO objects must be wrapped at birth using `guard_uno(obj)` or obtained via `get_ctx()` (which is pre-wrapped). Direct unmanaged calls to `uno.getComponentContext()` are strictly prohibited.

| Location | File Path | Guard Mechanism / Role |
|---|---|---|
| Primary UNO getters | `plugin/framework/uno_context.py` | Wrapped via `guard_uno()` on `get_ctx()`, `get_desktop()`, `get_active_document()`, `get_toolkit()`, `get_package_info()`. |
| Document Model Resolver | `plugin/doc/document_helpers.py` | `resolve_document_by_url()` returns `guard_uno(doc)`. |
| Panel Frame Resolver | `plugin/chatbot/panel.py`, `panel_factory.py` | `_get_document_model()` resolves frame controller model with `guard_uno`. |
| Hidden Document Loader | `plugin/doc/document_research.py` | `open_document_for_read()` guards hidden component model. |
| Desktop Enumeration | `plugin/doc/document_research.py` | `_office_model_from_desktop_element()` guards enumerated desktop models. |
| Scripting Calc Resolver | `plugin/scripting/document_scripts.py` | `get_calc_document_from_ctx()` wraps active sheet document. |
| Calc Add-in Doc Lookup | `plugin/calc/python/function.py` | `_get_calc_doc()` returns `None` off-main (#402), guards on-main. |
| Calc Cell Editor Selection | `plugin/calc/python/editor.py` | `_get_active_calc_cell()` guards active cell interface. |
| Graphic Export Bridge | `plugin/calc/image_tools.py` | `export_graphic_to_bytes()` resolves via `get_ctx()`. |
| Locale Resolution | `plugin/framework/i18n.py` | `get_lo_locale()` uses `get_ctx()` on-main, falls back to `en_US` off-main. |
| MCP Send Handlers | `plugin/mcp/server.py` | Context resolution uses `get_ctx()`, not raw bootstrap context. |

### Intentionally Unwrapped Boundaries (By Design)
- `QueueExecutor._get_async_callback`: Unwraps context before creating `com.sun.star.awt.AsyncCallback` service to avoid bootstrap deadlocks during executor initialization.
- `main.py` Menu-Icon `GraphicProvider`: Runs exclusively on the main UI thread during extension load; does not leak document model references.

---

## 8. Case Studies & Resolved Deadlocks

### Case Study 1: Synchronous Bridge & Add-in Deadlock (Issue #402)
- **The Bug**: Assigning `=PY(...)` via remote PyUNO (`sheet.getCellByPosition(0, 0).FormulaLocal = '=PY("1+1")'`) deadlocked LibreOffice against `MainThread`:
  1. The remote UNO dispatch executed Calc formula recalculation synchronously on a remote PyUNO bridge worker thread (`Dummy-2`).
  2. `workbook_session_id()` called `execute_on_main_thread(_workbook_session_id_impl)` (waiting up to 30s).
  3. LibreOffice's main thread was synchronously blocked waiting for the remote UNO RPC dispatch to finish, so it could not pump the `QueueExecutor` work queue.
  4. `session_key()`, `get_python_init_kwargs()`, and `_diagnostics_workbook_key()` called `get_desktop` without checking `on_main_thread()`, tripping the Layer A guard.
  5. The runtime guard's `_notify_thread_violation()` attempted a blocking `execute_on_main_thread(_show_popup, timeout=5.0)`, freezing the thread.
  6. When 30s elapsed, `_format_error_for_display()` mapped the timeout to a misleading `"Error: Python timed out"` message.
- **The Fix**:
  - `sync_host_dispatch()` context manager marks Yellow thread state; `QueueExecutor.execute` immediately refuses blocking calls off-main.
  - `workbook_session_id()` checks `python_session_mode(ctx)` before touching threads or marshalling.
  - Add-in UNO lookups check `on_main_thread()` and return safe no-UNO defaults off-main.
  - `_notify_thread_violation()` uses non-blocking `post_to_main_thread()` only when `AsyncCallback` is ready.

### Case Study 2: Calc Charts Process Events Hang (Commit `0cfc6891`)
- **The Bug**: `_process_events()` in `plugin/calc/charts.py` called `toolkit.processEventsToIdle()` on a path that could run without an active frame or on background worker threads.
- **The Fix**: Direct VCL event pumps are restricted to approved UI drain chokepoints (`pump_ui_idle` / `process_events_to_idle`) and verified by Semgrep rule `raw-process-events-to-idle`.

---

## 9. Specialized Sub-Agents & Tools Threading

Specialized sub-agents (`plugin/doc/specialized_base.py`) run `DelegateToSpecializedBase.execute` on background worker threads when `is_async()` is True.
- **Scaffolding**: `get_tools(doc=...)`, shapes canvas, and open-documents enumeration must marshal through `execute_on_main_thread()`.
- **Sync Domain Tools**: Run via `SmolToolAdapter(main_thread_sync=True)` which marshals tool execution to the main thread.
- **Async Domain Tools** (`image_generate`, `delegate_read_document`): Run on caller worker threads and must marshal PyUNO access internally inside their own `execute()` methods. Verified in [`tests/doc/test_specialized_delegation_threading.py`](../tests/doc/test_specialized_delegation_threading.py).

---

## 10. Summary of Architectural Invariants

1. **No PyUNO Off-Main**: All PyUNO service instantiation, method calls, property reads/writes, and interface queries must execute on `threading.main_thread()`.
2. **Workers Spawn via `run_in_background`**: Raw `threading.Thread` and `threading.Timer` instantiation is banned outside vetted allowlists.
3. **No Blocking Marshal in Yellow Context**: Functions executing inside synchronous host dispatches (Calc add-in evaluation, UNO listener callbacks) must never call `execute_on_main_thread()`.
4. **Viral Proxy on UNO Sources**: All new UNO object sources must return `guard_uno(obj)` to propagate runtime checking across object graph traversals.
5. **Non-Blocking Error Reporting**: Concurrency guard notifications must use `post_to_main_thread()` and never block background workers.

---

## Cross-References

- [`docs/threading_architecture.md`](threading_architecture.md) — Pool architecture, drain ownership, and subprocess IPC pipe safety.
- [`docs/streaming-and-threading.md`](streaming-and-threading.md) — Drain loop, cancellation, and `execute_on_main_thread` checklist.
- [`docs/formal_verification.md`](formal_verification.md) — Why value-level formal verification (CrossHair/deal) does not apply to thread affinity effect typing.
