# Enabling Basic Numpy in LibreOffice

Getting a C-compiled library like `numpy` to run reliably inside a LibreOffice extension is challenging, primarily because LibreOffice ships with its own embedded Python interpreter. 

This document outlines what it takes to get `numpy` functioning properly in your extension and evaluates the potential approaches.

## The Core Challenge: ABI Mismatches
`numpy` is not a pure Python library; it contains compiled C/C++ extensions. These compiled libraries must be built against the exact version and ABI (Application Binary Interface) of the Python interpreter that runs them.

- **The Problem**: If a user runs `pip install numpy` using their system Python (e.g., Python 3.12) and your extension loads that `numpy` bundle into LibreOffice's embedded Python (e.g., Python 3.8 or 3.9), the entire LibreOffice instance will fatally crash because the C-extensions are binary-incompatible.
- **The Requirement**: To run `numpy`, it **must** be downloaded or compiled using the exact `python` executable that LibreOffice is using.

---

## Strategy 1: The LibrePythonista Approach (Pip Bootstrapping)
Instead of trying to ship `numpy` inside the `.oxt` extension file, the extension ships with `pip` and installs `numpy` directly into LibreOffice's environment at runtime.

### What it takes:
1. Bundle a script like `get-pip.py` or a `pip` `.whl` inside your `.oxt`.
2. On extension startup, resolve the physical path to LibreOffice's python (using `sys.executable` or inferring it from `uno.__file__`).
3. Determine a safe user-writable path (handling quirks for Windows, macOS, Flatpak sandbox boundaries).
4. Run a background process: `[sys.executable, 'get-pip.py', '--target', safe_path]`.
5. Run a second background process: `[sys.executable, '-m', 'pip', 'install', 'numpy', '--target', safe_path]`.
6. At the top of your extension script, `sys.path.append(safe_path)` and then `import numpy`.

*(Note: LibrePythonista contains over 2,000 lines of code specifically dedicated to handling the weird edge cases of OS and Flatpak paths to make this reliable).*

---

## Strategy 2: The Managed Venv Approach (Deferred/Alternative)
Instead of manually overriding target directories, you could have the extension create its own standard virtual environment.

**Status**: **Deferred**. While this is theoretically the most seamless, we favor Strategy 3 because power users often have custom-optimized `numpy` or `scipy` builds (e.g. MKL, OpenBLAS) or complex data science stacks in their own venvs. Forcing them into a "managed" venv might prevent them from using their preferred, high-performance environments.

---

## Strategy 3: Pointing to an Existing "User-Provided" Venv (CHOSEN)
Rather than creating or bootstrapping a Python environment internally, the extension lets the user point to an existing `.venv` directory they already created on their system.

### The Safe Way (Out-of-Process Execution / Persistent RPC)
Instead of importing `numpy` inside the LibreOffice Python instance, we never mix memory. We shell out to the `python` executable located *inside* the user's venv.

1. **Persistent Worker**: We spawn the process once and keep it alive (using the `PythonWorkerManager` singleton).
2. **Notebook State**: We maintain the execution state (`globals()`) across calls, allowing for multi-step data analysis.
3. **RPC**: Communication happens over stdin/stdout using JSON-RPC.

**Pros**: Completely sidesteps ABI issues. `Numpy` will never crash LibreOffice. Supports any Python version (3.11–3.14). State persistence enables complex multi-turn workflows.
**Cons**: Requires the user to have a venv ready.

---

If you choose this route, there are two fundamentally different ways you can execute their `numpy` installation:

### A: The Dangerous Way (In-Process `sys.path` Injection)
You configure your extension to read the user's provided path and append it to LibreOffice's internal Python path:
```python
import sys
# The user types this path into a LibreOffice settings dialog
user_venv_path = get_user_setting("custom_venv_path")
sys.path.insert(0, f"{user_venv_path}/lib/python3.x/site-packages")

import numpy # Will attempt to load from the user's venv
```
- **The Catch**: This is notoriously fragile. If the user created their `.venv` using their system's Python 3.12, but LibreOffice embeds Python 3.8, `numpy` will immediately crash with a fatal ABI/DLL error. This approach *only* works if the user went out of their way to purposefully construct their `.venv` using the exact minor version (and architecture) of the Python interpreter embedded in LibreOffice.

### B: The Safe Way (Out-of-Process Execution / RPC)
Instead of importing `numpy` inside the LibreOffice Python instance, you never modify `sys.path`. Instead, your extension acts as a thin UI that shells out to the `python` executable located *inside* the user's venv.
1. The user interacts with the UI in LibreOffice.
2. The extension writes target data to a temporary JSON or CSV file.
3. The extension triggers the user's external Python process using `subprocess.Popen("/their/custom/venv/bin/python worker.py")`.
4. That background process loads `numpy`, applies operations, and writes the results back.
5. The LibreOffice extension reads the results back into the spreadsheet/document.

**Pros**: Completely sidesteps ABI issues and embedded interpreter limits. `Numpy` will never crash LibreOffice because the two Python interpreters never mix memory. 
**Cons**: Slower execution due to file/socket I/O overhead. Requires you to handle subprocess lifecycles reliably.

---
---

# Python Venv Proxy — User & Developer Specification

## 1. Vision & User Story

WriterAgent users should be able to say things like *"Generate a Monte Carlo simulation with 10,000 samples and put the results in a chart"* and have the AI:

1. Write Python code that uses `numpy`, `pandas`, `scipy`, etc.
2. Execute that code safely against the user's own venv.
3. Use WriterAgent's existing Calc tool-calling APIs (`write_formula_range`, `set_style`, `create_chart`, etc.) to push results into the spreadsheet.

The user never leaves LibreOffice. They never see a terminal. The extension manages the entire lifecycle.

### What the user configures

A single setting in **Settings → Python**:

| Setting | Description | Example |
|---------|-------------|---------|
| `python_venv_path` | Absolute path to an existing Python venv directory | `~/.writeragent_venv` or `/home/user/data-science-venv` |

If the path is empty, the Python execution feature is disabled. No automatic venv creation — the user brings their own. This is the simplest initial approach and avoids all the ABI/pip bootstrapping complexity from Strategies 1–2 above.

### What the user experiences

1. They ask the AI to perform data analysis, statistical computation, or any task requiring libraries not available in LibreOffice's embedded Python.
2. The AI generates Python code (visible in the "Thinking" panel if enabled).
3. A status message appears: *"Running Python script..."*
4. Results flow back into the spreadsheet via normal tool calls.
5. If the script fails, the AI sees the error and can retry with corrected code.

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                    LibreOffice Process                    │
│                                                          │
│  ┌─────────────┐    ┌──────────────────────────────────┐ │
│  │  LLM / Chat │───▶│  Tool: run_python_script         │ │
│  │  (tool loop) │    │  (async, specialized domain)     │ │
│  └─────────────┘    └──────────┬───────────────────────┘ │
│                                │                         │
│                     ┌──────────▼───────────────────────┐ │
│                     │  Safety Gate                     │ │
│                     │  ├─ AST pre-scan (blocklist)     │ │
│                     │  ├─ Timeout / resource limits    │ │
│                     │  └─ Import whitelist check       │ │
│                     └──────────┬───────────────────────┘ │
│                                │                         │
│                     ┌──────────▼───────────────────────┐ │
│                     │  PythonWorkerManager             │ │
│                     │  (Persistent Subprocess)         │ │
│                     │  venv/bin/python                  │ │
│                     │  worker_harness.py                │ │
│                     │  stdin/stdout JSON-RPC            │ │
│                     └──────────┬───────────────────────┘ │
│                                │                         │
│                     ┌──────────▼───────────────────────┐ │
│                     │  Result Collector                │ │
│                     │  ├─ Captures stdout, return val  │ │
│                     │  ├─ Serializes numpy → lists     │ │
│                     │  └─ Feeds back to LLM            │ │
│                     └──────────┬───────────────────────┘ │
│                                │                         │
│                     ┌──────────▼───────────────────────┐ │
│                     │  LLM calls Calc tools:           │ │
│                     │  write_formula_range, set_style, │ │
│                     │  create_chart, etc.              │ │
│                     └──────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### Why subprocess-only (no in-process execution)

The codebase contains `plugin/contrib/smolagents/local_python_executor.py` — a full AST-walking restricted Python interpreter with whitelisted builtins, dunder blocking, import restrictions, operation/iteration limits, and timeouts. It might seem like a natural fast-path for simple math code. However, **it cannot be used here** because of Python version mismatch:

- LibreOffice ships its own embedded Python (often 3.8–3.11 depending on build/platform).
- The user's venv will typically use a newer system Python (3.12, 3.13, 3.14+).
- `ast.parse()` inside LO's Python would reject syntax valid in newer Python versions (e.g. `match` statements from 3.10, `type` aliases from 3.12, PEP 695 generics from 3.12+).
- Even without syntax differences, stdlib module behavior varies between minor versions (e.g. `statistics.fmean` added in 3.8, `math.cbrt` in 3.11, `itertools.batched` in 3.12). Code tested against the user's Python version would silently break or produce wrong results in LO's older runtime.

The `LocalPythonExecutor` remains valuable for its original purpose — executing smolagents-generated code in the tool-calling loop — where the code is LLM-generated against LO's own Python. But for user-facing "run a script" functionality, **all execution goes through the user's venv subprocess**. This guarantees version consistency, full library access, and complete memory isolation from LibreOffice.

---

## 3. Developer Specification

### 3.1 New config keys

Added to `WriterAgentConfig` in `plugin/framework/config.py`:

```python
python_venv_path: str = ""           # Absolute path to user's venv directory
python_exec_timeout: int = 120       # Max seconds for subprocess execution
python_exec_enabled: bool = True     # Master enable/disable
```

### 3.2 Tool: `run_python_script`

A new tool registered in a new module `plugin/calc/python_exec.py` (and/or `plugin/writer/python_exec.py` for Writer context):

```python
class RunPythonScript(ToolBase):
    name = "run_python_script"
    description = """Execute a Python script in the user's configured venv (isolated subprocess).
    Supports numpy, pandas, scipy, scikit-learn, and any library installed in the venv.
    The script should assign results to a variable called `result`.
    Numpy arrays and pandas DataFrames are automatically serialized to lists/dicts."""

    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python source code to execute. Assign output to `result`."
            }
        },
        "required": ["code"]
    }

    # Calc + Writer (data analysis applies to both)
    uno_services = [
        "com.sun.star.sheet.SpreadsheetDocument",
        "com.sun.star.text.TextDocument",
    ]
    tier = "specialized"
    specialized_domain = "python"
    long_running = True

    def is_async(self):
        return True

    def execute(self, ctx, *, code: str) -> dict:
        ...
```

### 3.3 Subprocess executor

The extension already ships `local_python_executor.py` (in `plugin/contrib/smolagents/`) as part of the OXT package on disk. The worker harness is a small script that the venv's Python runs directly from the extension's install path — it just imports the executor from next door. No copying, no build step, no extra packaging. The venv provides the Python interpreter; the extension provides the safety layer.

#### Worker harness (`plugin/python/worker_harness.py`)

Runs in the user's venv Python. Imports `local_python_executor.py` from the extension's own install directory. The venv's `ast` module parses the code (so 3.14 syntax works), and the venv's packages are importable (so numpy/pandas work), but dangerous modules are blocked by the executor.

```python
#!/usr/bin/env python3
"""WriterAgent Python worker — runs in the user's venv.

Protocol: one JSON object per line on stdin, one JSON object per line on stdout.
Request:  {"id": "...", "code": "..."}
Response: {"id": "...", "status": "ok"|"error", "result": ..., "stdout": "...", "error": "..."}
"""
import json
import sys
import os

# local_python_executor.py is already shipped with the extension.
# Resolve it relative to this file's location in the extension directory.
_ext_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ext_dir, "..", "contrib", "smolagents"))
from local_python_executor import LocalPythonExecutor, InterpreterError

# Libraries the user is allowed to import (beyond the safe base set).
# This is the whitelist — anything not listed here is blocked.
DEFAULT_AUTHORIZED_IMPORTS = [
    "numpy", "numpy.*",
    "pandas", "pandas.*",
    "scipy", "scipy.*",
    "sklearn", "sklearn.*",
    "matplotlib", "matplotlib.*",
    "seaborn", "seaborn.*",
    "sympy", "sympy.*",
    "statsmodels", "statsmodels.*",
    "networkx", "networkx.*",
    "PIL", "PIL.*",
    "cv2",
    "json",
    "csv",
    "decimal",
    "fractions",
    "functools",
    "operator",
    "string",
    "textwrap",
    "enum",
    "dataclasses",
    "typing",
    "copy",
    "pprint",
]

def serialize(obj):
    """Convert numpy/pandas types to JSON-safe Python types."""
    try:
        import numpy as np
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
    except ImportError:
        pass
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            return obj.to_dict(orient="records")
        if isinstance(obj, pd.Series):
            return obj.tolist()
    except ImportError:
        pass
    if isinstance(obj, (list, tuple)):
        return [serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): serialize(v) for k, v in obj.items()}
    return obj

def execute_code(executor: LocalPythonExecutor, code: str) -> dict:
    """Run code through a provided (potentially persistent) executor."""
    try:
        output = executor(code)
        # 'result' variable is preferred, but we fall back to the last expression
        result = executor.state.get("result", output.output)
        return {
            "status": "ok",
            "result": serialize(result),
            "stdout": output.logs,
        }
    except InterpreterError as e:
        return {"status": "error", "error": str(e), "stdout": ""}
    except Exception as e:
        return {"status": "error", "error": str(e), "stdout": ""}

def main():
    # To support state persistence (§4.3), we initialize the executor ONCE
    # outside the loop. The state dictionary persists between lines.
    executor = LocalPythonExecutor(
        additional_authorized_imports=DEFAULT_AUTHORIZED_IMPORTS,
        timeout_seconds=120,
    )
    executor.send_tools({})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if request.get("command") == "reset":
                # Clear variables for a new session
                executor.state = {}
                response = {"status": "ok", "message": "State reset"}
            else:
                response = execute_code(executor, request["code"])

            response["id"] = request.get("id", "")
        except Exception as e:
            response = {"status": "error", "error": str(e), "id": ""}

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
```

#### Subprocess management (in `plugin/python/python_exec.py`)

The tool resolves the harness path from the extension's own install directory and spawns the venv Python to run it. Borrowing robust execution patterns from the **Hermes agent**, we include environment scrubbing, UTF-8 enforcement, and bytecode suppression:

```python
import json
import os
import subprocess
import uuid

# Harness lives in the same package as this file
HARNESS_PATH = os.path.join(os.path.dirname(__file__), "worker_harness.py")

def _scrub_env(env: dict) -> dict:
    """Block API keys and secrets from leaking into the child process."""
    blocked_substrings = ("KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH")
    scrubbed = {}
    for k, v in env.items():
        if any(s in k.upper() for s in blocked_substrings):
            continue
        scrubbed[k] = v
    return scrubbed

def _execute_in_subprocess(code: str, venv_path: str, timeout: int = 120) -> dict:
    """Run code in the user's venv via the worker harness."""
    if os.name == "nt":
        venv_python = os.path.join(venv_path, "Scripts", "python.exe")
    else:
        venv_python = os.path.join(venv_path, "bin", "python")

    if not os.path.isfile(venv_python):
        return {"status": "error", "error": f"Python not found at {venv_python}"}

    # Environment hardening
    child_env = _scrub_env(os.environ)
    child_env.update({
        "PYTHONIOENCODING": "utf-8",    # Prevent crashes on non-ASCII output
        "PYTHONUTF8": "1",              # Enable UTF-8 mode (PEP 540)
        "PYTHONDONTWRITEBYTECODE": "1", # Keep user's venv clean
    })

    request = json.dumps({"id": str(uuid.uuid4()), "code": code}) + "\n"

    # Use os.setsid on POSIX to ensure child and its descendants can be killed
    popen_args = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "env": child_env,
    }
    if os.name != "nt":
        popen_args["preexec_fn"] = os.setsid

    proc = subprocess.Popen([venv_python, HARNESS_PATH], **popen_args)

    try:
        stdout, stderr = proc.communicate(input=request, timeout=timeout)
        if proc.returncode != 0:
            return {"status": "error", "error": f"Process exited {proc.returncode}: {stderr}"}
        for line in stdout.strip().split("\n"):
            if line.strip():
                return json.loads(line)
        return {"status": "error", "error": "No output from worker"}
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            proc.kill()
        else:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()
        return {"status": "error", "error": f"Execution timed out after {timeout}s"}
```

### 3.4 Safety model — no separate safety gate needed

Because the worker harness uses `LocalPythonExecutor`, we **do not need a separate AST safety gate** on the LibreOffice side. The safety is enforced at execution time in the subprocess itself:

| Protection | Mechanism in `LocalPythonExecutor` |
|------------|------------------------------------|
| Dangerous imports (`os`, `sys`, `subprocess`, `socket`, etc.) | `DANGEROUS_MODULES` blocklist — checked at import time |
| Dangerous functions (`eval`, `exec`, `compile`, `__import__`) | `DANGEROUS_FUNCTIONS` blocklist — checked at call time |
| Dunder attribute access (`__class__.__subclasses__()` etc.) | `nodunder_getattr` + attribute evaluation guard |
| Infinite loops | `MAX_WHILE_ITERATIONS = 1_000_000` |
| CPU exhaustion | `MAX_OPERATIONS = 10_000_000` |
| Runaway execution | Configurable timeout (default 30s, we set 120s) |
| Library whitelist | Only `additional_authorized_imports` + `BASE_BUILTIN_MODULES` can be imported |

The **import whitelist is the primary control surface**: `numpy`, `pandas`, `scipy`, etc. are explicitly listed in `DEFAULT_AUTHORIZED_IMPORTS` in the worker harness. Everything not on the list (including `os`, `subprocess`, `pathlib`, `socket`) is blocked by the executor before it can run.

> **Note:** The restricted executor is not a perfect sandbox (Python is too dynamic for language-level sandboxing to be 100% airtight). The subprocess boundary provides the true isolation — even if someone finds an escape path in the AST walker, they're in a separate process with no access to LibreOffice's memory or UNO objects.

### 3.5 State Persistence and Session Management

The implementation uses a **Persistent Worker** model to enable notebook-style state persistence within a chat session.

#### 1. `PythonWorkerManager` (Extension Side)
A singleton class in `plugin/python/python_exec.py` manages the subprocess:
*   **Process Lifecycle**: Spawns the venv Python with the `worker_harness.py` on first use.
*   **Persistence**: Keeps the process alive across multiple `run_python_script` calls.
*   **Health Checks**: Automatically restarts the worker if it crashes.
*   **Serialization**: Handles JSON-RPC communication over stdin/stdout.

#### 2. Notebook-Style State (Worker Side)
The `worker_harness.py` maintains a single `LocalPythonExecutor` instance. Variables created in one turn (e.g., a Pandas DataFrame) persist and are available in subsequent turns, enabling complex workflows like:
1. Turn 1: `df = pd.read_csv("large_data.csv")`
2. Turn 2: `result = df.groupby("category").sum().to_dict()`

#### 3. Session Isolation
To prevent state bleed between different chat sidebars or new conversations:
*   **Session ID**: Each chat session has a unique ID.
*   **Reset Command**: When a new session starts (or the user resets the chat), the extension sends `{"command": "reset"}`.
*   **State Clear**: The harness clears the `executor.state` dictionary, providing a clean slate while keeping the process warm.

### 3.7 LLM integration — the two-phase pattern

The LLM does **not** directly insert data into the spreadsheet from the Python script. Instead, the workflow is:

1. **Phase 1 — Compute:** The LLM calls `run_python_script` with numpy/pandas code. The result comes back as serialized JSON (lists, dicts).
2. **Phase 2 — Insert:** The LLM uses the result to call existing Calc tools (`write_formula_range`, `set_style`, `create_chart`) to place the data.

This means:
- The Python script never needs UNO access.
- The Python script never needs to know about LibreOffice.
- The existing Calc tool API handles all document manipulation.
- The LLM acts as the orchestrator between computation and presentation.

#### System prompt addition

```python
PYTHON_EXECUTION_GUIDANCE = """PYTHON EXECUTION:
You can run Python scripts using the run_python_script tool.
- Runs in the user's configured Python venv (isolated subprocess with safety restrictions).
- Supports numpy, pandas, scipy, scikit-learn, matplotlib, sympy, and other whitelisted libraries.
- Assign your output to a variable called `result` — it will be returned to you as JSON.
- numpy arrays → lists, DataFrames → list of row dicts, Series → lists.
- After getting results, use write_formula_range / set_style / create_chart to put data into the spreadsheet.
- Do NOT try to import os, sys, subprocess, or access the filesystem — these are blocked.
- Do NOT try to use open() or pathlib — file access is blocked.

Example workflow:
1. run_python_script(code="import numpy as np\\nresult = np.random.normal(0, 1, 100).tolist()")
2. Use the returned list with write_formula_range to populate cells.
3. Use create_chart to visualize.
"""
```

### 3.8 Settings UI integration

A new Python section in the Settings dialog:

| Control | Type | Config key | Default |
|---------|------|------------|---------|
| Enable Python execution | Checkbox | `python_exec_enabled` | `True` |
| Python venv path | TextField + Browse button | `python_venv_path` | `""` (empty = disabled) |
| Execution timeout (seconds) | NumericField | `python_exec_timeout` | `120` |

The Browse button opens a directory picker dialog. On confirmation, the extension validates:
1. The path exists and is a directory.
2. `bin/python` (or `Scripts/python.exe` on Windows) exists and is executable.
3. Optionally: runs `venv_python --version` to display the Python version to the user.

### 3.7 Module & file layout

No new build steps. The worker harness is just a new `.py` file in `plugin/python/`. It imports the existing `local_python_executor.py` from `plugin/contrib/smolagents/` at runtime.

```
plugin/
├── python/                          # NEW module
│   ├── __init__.py
│   ├── python_exec.py               # RunPythonScript tool + subprocess management
│   └── worker_harness.py            # Entry point run by venv Python (JSON-RPC stdin/stdout)
├── contrib/smolagents/
│   └── local_python_executor.py     # EXISTING — imported by worker_harness.py at runtime
├── framework/
│   ├── config.py                    # MODIFIED — new config keys
│   ├── constants.py                 # MODIFIED — PYTHON_EXECUTION_GUIDANCE
│   └── worker_pool.py              # EXISTING
```

### 3.10 Specialized domain registration

Following the existing pattern in `plugin/calc/base.py`:

```python
class ToolCalcPythonBase(ToolCalcSpecialBase):
    specialized_domain = "python"
    specialized_domain_description: ClassVar[str | None] = (
        "Run Python scripts (numpy, pandas, scipy) and return computed results."
    )
```

This makes the tool available via the existing `delegate_to_specialized_calc_toolset(domain="python")` gateway pattern, keeping it off the default tool list until the LLM needs it.

---

## 4. Future Enhancements

### 4.1 OooDev / ScriptForge integration (deferred)

[OOO Development Tools](https://pypi.org/project/ooo-dev-tools/) provides a high-level Pythonic wrapper around UNO. Rather than bundling it (large dependency, complex UNO bootstrap), future work could:

- **Document it as a recommended venv install:** If the user installs `ooo-dev-tools` in their venv, their Python scripts could potentially manipulate documents directly via OooDev's API.
- **Provide a bridge module:** A small shim in the worker harness that exposes simplified document operations via JSON-RPC callbacks to the LibreOffice process.
- **Alternatively, keep the current model:** The LLM uses Python for computation and WriterAgent tools for document manipulation. This is simpler, safer, and doesn't require OooDev at all.

The current two-phase approach (compute in Python → insert via tools) is recommended as the primary path because it requires zero UNO knowledge from the user's scripts.

### 4.2 Managed venv creation (deferred)

A "Setup Python Environment" button in Settings that:
1. Detects LibreOffice's bundled Python version.
2. Creates a venv using the system Python matching that version (or the LO Python itself).
3. Installs a default set of packages (numpy, pandas, matplotlib).
4. Sets `python_venv_path` automatically.

This is Strategy 2 from the first part of this document, deferred to reduce initial complexity and respect user environment preferences.

### 4.3 Result visualization (deferred)

For matplotlib: the worker harness could save figures to a temp file and return the path. The extension would then insert the image into the document using existing image tools.

---

## 5. Security Summary

| Layer | Mechanism | Protects against |
|-------|-----------|-----------------|
| **Restricted executor** | `LocalPythonExecutor` running in subprocess — AST-walking interpreter with whitelisted builtins, dunder blocking, import whitelist, operation/iteration limits, timeouts | Dangerous imports, `eval`/`exec`, dunder escapes, infinite loops, CPU exhaustion |
| **Import whitelist** | Only `DEFAULT_AUTHORIZED_IMPORTS` (numpy, pandas, scipy, etc.) + `BASE_BUILTIN_MODULES` are importable | `os.remove()`, `subprocess.run()`, `socket` connections, filesystem access |
| **Subprocess isolation** | Separate process, separate Python interpreter, no shared memory with LO | ABI crashes, C-extension segfaults, memory corruption, UNO state corruption |
| **Environment scrubbing** | Removing `KEY`, `TOKEN`, `SECRET`, etc. from child process env | LLM-generated scripts exfiltrating API keys or credentials |
| **User-provided venv** | User explicitly opts in and controls what's installed | Supply-chain attacks (user manages their own packages) |
| **Execution timeout** | Configurable per-execution wall clock limit (default 120s) | Runaway computation |

> [!IMPORTANT]
> This architecture draws on best practices from the **Hermes agent**'s robust execution model, including UTF-8 enforcement for stdio, bytecode suppression, and process group isolation (`os.setsid`) to ensure clean resource management.
>
> Two independent layers protect LibreOffice: (1) the restricted executor blocks dangerous code at the AST level before it runs, and (2) the subprocess boundary ensures that even if the executor is bypassed, the attacker is in a separate process with no access to LibreOffice's memory, UNO objects, or document data. The code is LLM-generated (not arbitrary user input), which further limits the threat surface.

---

## 6. Vendoring & Reference Files

We can leverage or vendor specific utility modules from the **Hermes agent** to ensure our subprocess and environment management is robust across all platforms.

### 6.1 Subprocess & Windows Compatibility
**File:** [_subprocess_compat.py](file:///home/keithcu/.hermes/hermes-agent/hermes_cli/_subprocess_compat.py)
*   **What to vendor:** This file is almost entirely standalone.
*   **Key features:**
    *   `windows_hide_flags()`: Returns `CREATE_NO_WINDOW` creation flags for Windows to prevent console flashes during version probes.
    *   `windows_detach_flags()`: Correctly detaches background processes on Windows (where `start_new_session=True` is a no-op).
    *   `resolve_node_command()`: Logic for resolving `.cmd` shims on Windows (useful if we ever add npm-based tools).

### 6.2 Environment Scrubbing & Sandboxing
**File:** [code_execution_tool.py](file:///home/keithcu/.hermes/hermes-agent/tools/code_execution_tool.py)
*   **What to borrow:** Specifically the `_scrub_child_env` function (lines 118-153) and the `_execute_local` block (lines 1165-1241).
*   **Key features:**
    *   **Secret Filtering:** Exhaustive list of substrings (`KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `AUTH`, `CREDENTIAL`) to block from the child process.
    *   **OS Essentials:** Logic for which variables *must* be passed through on Windows for `socket` and `subprocess` to function (e.g., `SYSTEMROOT`, `COMSPEC`).
    *   **UTF-8 Enforcement:** Setting `PYTHONIOENCODING="utf-8"` and `PYTHONUTF8="1"` to prevent encoding-related crashes in the worker.

### 6.3 Output Truncation & Pagination
**File:** [tool_output_limits.py](file:///home/keithcu/.hermes/hermes-agent/tools/tool_output_limits.py)
*   **What to borrow:** The concept of centralized truncation limits (`max_bytes`, `max_lines`) to keep the LLM context window clean.
*   **Key features:**
    *   Standardizing on ~50KB (`DEFAULT_MAX_BYTES`) for large tool outputs (like Pandas dataframes or terminal logs).
    *   `_coerce_positive_int`: Defensive parsing of configuration values.
