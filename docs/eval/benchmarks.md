# LLM Evaluation Suite & Benchmarks

WriterAgent includes an in-LibreOffice **LLM Evaluation Suite** for real-world tasks in Writer, Calc, and Draw. Runs track accuracy and **Intelligence-per-Dollar**: **Value (C²/$)** = average metric score squared ÷ average dollars per task (higher is better), using live OpenRouter pricing where available.

How to run evals from the repo: [scripts/prompt_optimization/README.md](../../scripts/prompt_optimization/README.md). Broader plan notes: [eval-dev-plan.md](eval-dev-plan.md). String harness (no LO ranking): [string-harness-upgrade.md](string-harness-upgrade.md).

## Snapshot ranking (2026-09-01)

**17-task string harness** (`--backend string`, OpenRouter). First pass on the hardened pack (Writer + Draw flowchart + Calc sort/tax + two `=PY` dest rows). Not LO-backed — fidelity smoke only.

Artifacts: [`scripts/prompt_optimization/benchmark_results.json`](../../scripts/prompt_optimization/benchmark_results.json) and `benchmark_results_details.json`. Failure triage: [benchmark-failure-analysis-2026-09-01.md](benchmark-failure-analysis-2026-09-01.md).

**Excluded (3 of 23 models):** `nvidia/nemotron-3.5-lightning` and `qwen/qwen3.8-flash` (429 rate limits on all tasks); `minimax/minimax-m3` (harness crash on `format_preservation` — [stream-normalizer-delta-crash.md](stream-normalizer-delta-crash.md), re-run after fix).

Ranked by **hard pass → agent score → metric**. **Hard pass** = document substring + result oracles + process oracles, no API error. **Agent** = same gate including tool-process checks. **Quality** = LLM judge among creative/table passes only.

| Rank | Model | Hard pass | Agent | Correctness | Quality | Tokens/task | $/task | C²/$ |
| ---- | ----- | --------- | ----- | ----------- | ------- | ----------- | ------ | ---- |
| 1 | openai/gpt-oss-120b | 1.000 | 1.000 | 0.971 | 0.90 | 12263 | 0.00054 | 1339.5 |
| 2 | x-ai/grok-4.6 | 1.000 | 1.000 | 0.982 | 0.94 | 20647 | 0.04653 | 12.9 |
| 3 | google/gemma-4-31b-it | 0.941 | 0.941 | 0.918 | 0.90 | 16844 | 0.00162 | 376.2 |
| 4 | openai/gpt-5.6-luna | 0.941 | 0.941 | 0.922 | 0.94 | 21376 | 0.00512 | 107.7 |
| 5 | z-ai/glm-5.3-flash | 0.941 | 0.941 | 0.913 | 0.90 | 40361 | 0.00412 | 119.3 |
| 6 | deepseek/deepseek-v4-flash-0731 | 0.941 | 0.941 | 0.928 | 0.96 | 48581 | 0.00389 | 125.5 |
| 7 | meta/muse-glimmer-30b | 0.941 | 0.941 | 0.928 | 0.96 | 27899 | 0.01078 | 41.4 |
| 8 | meta/muse-spark-1.2-contributor | 0.882 | 0.882 | 0.874 | 0.96 | 29419 | 0.00330 | 133.6 |
| 9 | qwen/qwen3.8-27b | 0.882 | 0.882 | 0.922 | 0.92 | 41809 | 0.02460 | 14.7 |
| 10 | inception/mercury-2 | 0.824 | 0.824 | 0.814 | 0.97 | 14267 | 0.00397 | 124.6 |
| 11 | bytedance-seed/seed-2.0-mini | 0.824 | 0.824 | 0.800 | 0.90 | 37491 | 0.00601 | 60.7 |
| 12 | poolside/laguna-xs-2.1 | 0.824 | 0.824 | 0.767 | 0.81 | 35088 | 0.00216 | 161.9 |
| 13 | ibm-granite/granite-4.2-8b | 0.765 | 0.765 | 0.802 | 0.93 | 66636 | 0.00735 | 26.0 |
| 14 | openai/gpt-oss-20b | 0.706 | 0.706 | 0.687 | 0.89 | 16062 | 0.00065 | 537.4 |
| 15 | upstage/solar-pro4 | 0.706 | 0.706 | 0.682 | 0.90 | 20429 | 0.00065 | 440.4 |
| 16 | google/gemini-3.5-flash-lite | 0.647 | 0.647 | 0.688 | 0.93 | 14130 | 0.00495 | 67.0 |
| 17 | poolside/laguna-s-2.1 | 0.647 | 0.647 | 0.700 | 0.90 | 21250 | 0.00216 | 130.2 |
| 18 | google/gemma-4-26b-a4b-it | 0.647 | 0.647 | 0.621 | 0.89 | 19992 | 0.00151 | 157.9 |
| 19 | z-ai/glm-5.3 | 0.647 | 0.647 | 0.702 | 0.97 | 33578 | 0.06972 | 3.4 |
| 20 | mistralai/mistral-small-2603 | 0.588 | 0.588 | 0.571 | 0.85 | 13614 | 0.00214 | 111.4 |

## Key insights

1. **Perfect hard pass:** `openai/gpt-oss-120b` and `x-ai/grok-4.6` cleared every task on the hard gate. Grok leads on raw correctness; gpt-oss-120b dominates **C²/$** (~$0.0005/task).
2. **Mid-tier cluster:** Gemma 4 31B, GPT-5.6 Luna, GLM 5.3 Flash, DeepSeek V4 Flash, and Muse Glimmer sit at ~94% hard pass — strong cost/quality tradeoffs below the top two.
3. **Calc/oracle hotspots:** `tax_column`, `data_sorting`, and `flowchart_gen` separated the middle from the bottom; most failures are model-side (wrong formulas, incomplete diagrams), not harness bugs.
4. **Do not read 429 zeros:** Nemotron 3.5 Lightning and Qwen3.8 Flash scored 0% only because OpenRouter rate-limited every task — excluded above.
5. **MiniMax M3 held out:** One task hit a streaming normalizer contract bug; re-run after [stream-normalizer-delta-crash.md](stream-normalizer-delta-crash.md) is fixed.

## Scoring approach

Structural tasks are scored from the **exported final document** (HTML / Draw tree / Calc grid) via result oracles — not tool-name traces. Creative tasks (resume, logical rewriting, summarization) and the two table tasks use an LLM judge (default `openai/gpt-oss-120b:nitro`) plus gold references in `gold_standards.json` (hand-written from the rubrics).

**Fine-tuning direction:** the same eval signal (correct vs incorrect tool use, minimal vs verbose traces) could train a smaller specialist for this tool distribution—fewer tokens at similar correctness, better Value (C²/$).
