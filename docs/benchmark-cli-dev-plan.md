# Benchmark CLI Development Plan

**Goal**: Add a simple CLI entry point to the existing eval suite so AI developers can run benchmarks without digging into the codebase.

## Overview

The existing infrastructure in `scripts/prompt_optimization/` already supports:
- Multi-model benchmarking with cost tracking (intelligence-per-dollar)
- LLM-as-a-Judge scoring with weighted criteria (Accuracy, Formatting, Naturalness)
- Multiple backends: in-memory string simulation (`string`) and headless LibreOffice (`lo`)
- Tool loop evaluation matching production chat semantics
- Gold standard generation for reference answers

This document outlines adding a simple CLI wrapper that makes it easier to run.

---

## What We Need

| Feature | Status | Priority |
|---------|--------|----------|
| Run benchmarks against any OpenAI-compatible endpoint | **Exists** | High |
| Multi-model comparison with cost tracking | **Exists** | High |
| JSON/CSV output formats | **Exists** | High |
| Configurable system prompt | **Exists** | Medium |
| Tool loop evaluation (matching production) | **Exists** | High |
| LLM-as-a-Judge scoring | **Exists** | Medium |
| Simple CLI wrapper | **Missing** | High |
| Custom task support (user-provided prompts) | **Missing** | Medium |

---

## Plan

### Step 1: Add a CLI script
Create `scripts/benchmark.py` that wraps `run_eval_multi.py` with simpler arguments.

### Step 2: Simplify the interface
```bash
# Current (complex)
cd scripts/prompt_optimization
python run_eval_multi.py --models openai/gpt-oss-120b --api-key XXX -j 4

# New (simple)
python scripts/benchmark.py --models openai/gpt-oss-120b --api-key XXX
```

### Step 3: Add custom task support
Allow users to pass a prompt + document directly:
```bash
python scripts/benchmark.py --task "Make a table" --document "Item: Apple\nPrice: 1" --model llama3.2
```

---

## Code Changes

### 1. Create `scripts/benchmark.py`

A thin wrapper that calls `run_eval_multi.py` with sensible defaults:

```python
#!/usr/bin/env python3
"""
Simple benchmark CLI for WriterAgent.

Usage:
    python scripts/benchmark.py --model llama3.2 --api-key XXX
    python scripts/benchmark.py --models openai/gpt-oss-120b,google/gemini-3-flash-preview --api-key XXX
    python scripts/benchmark.py --task "Make a table" --document "Item: Apple\nPrice: 1" --model llama3.2
"""
import sys
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PO_DIR = SCRIPT_DIR / "prompt_optimization"

def main():
    import argparse
    parser = argparse.ArgumentParser(description="WriterAgent Benchmark")
    parser.add_argument("--model", "-m", help="Single model to benchmark")
    parser.add_argument("--models", help="Comma-separated list of models")
    parser.add_argument("--api-key", "-k", help="API key for endpoint")
    parser.add_argument("--endpoint", "-e", default="https://openrouter.ai/api/v1",
                        help="API endpoint (default: OpenRouter)")
    parser.add_argument("--output", "-o", default="benchmark_results.json",
                        help="Output file (json or csv)")
    parser.add_argument("--backend", choices=["string", "lo"], default="string",
                        help="Backend: string (in-memory) or lo (LibreOffice)")
    parser.add_argument("--examples", "-n", type=int, default=None,
                        help="Number of examples to run")
    parser.add_argument("--parallel", "-j", type=int, default=4,
                        help="Number of parallel model evaluations")
    parser.add_argument("--verbose", "-v", action="store_true")
    
    # Custom task support
    parser.add_argument("--task", help="Custom task prompt")
    parser.add_argument("--document", help="Custom document content")
    parser.add_argument("--category", choices=["structural", "creative"], 
                        default="structural", help="Task category for scoring")
    
    args = parser.parse_args()
    
    # Build command for run_eval_multi.py
    cmd = [sys.executable, str(PO_DIR / "run_eval_multi.py")]
    
    # Handle models
    if args.model:
        cmd.extend(["--models", args.model])
    elif args.models:
        cmd.extend(["--models", args.models])
    
    # API config
    if args.api_key:
        cmd.extend(["--api-key", args.api_key])
    if args.endpoint != "https://openrouter.ai/api/v1":
        cmd.extend(["--api-base", args.endpoint])
    
    # Output
    cmd.extend(["--out", args.output])
    
    # Backend and options
    cmd.extend(["--backend", args.backend])
    if args.examples:
        cmd.extend(["-n", str(args.examples)])
    cmd.extend(["-j", str(args.parallel)])
    if args.verbose:
        cmd.append("-j 1")  # Sequential for verbose output
        cmd.append("--verbose")
    
    # Custom task (not in run_eval_multi yet - Phase 2)
    if args.task:
        print("Custom task support: TODO in Phase 2")
        sys.exit(1)
    
    # Run it
    subprocess.run(cmd, cwd=SCRIPT_DIR, check=True)

if __name__ == "__main__":
    main()
```

### 2. Phase 2: Add custom task support to `run_eval_multi.py`

Modify `run_eval_multi.py` to accept `--task` and `--document` arguments and dynamically create an example.



---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `scripts/benchmark.py` | **Create** | Simple CLI wrapper |
| `scripts/prompt_optimization/run_eval_multi.py` | Modify | Add `--task`/`--document` support |

---

## Testing

Test by running:
```bash
python scripts/benchmark.py --model openai/gpt-oss-120b --api-key XXX -n 2
```

Verify it produces the same results as:
```bash
cd scripts/prompt_optimization
python run_eval_multi.py --models openai/gpt-oss-120b --api-key XXX -n 2
```

---

## Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Phase 1 | 1 hour | Working CLI wrapper |
| Phase 2 | 1 hour | Custom task support |
| **Total** | **~2 hours** | Simple benchmark CLI |

---

## Notes

- Keep it simple: just a wrapper, not a new package
- Reuse existing code in `scripts/prompt_optimization/`
- No new dependencies needed
- Backward compatible: existing scripts still work
