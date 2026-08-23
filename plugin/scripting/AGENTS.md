# Scripting / LibrePy

Root **Do not redo** still applies. This file is the local map.

## Entry points

- Public script API, sandbox, venv worker (not for user imports): this package, `venv/`, `import_policy.py`, `sandbox.py`, `venv_worker.py`, `venv_diagnostics.py`
- LibrePy bootstrap: `plugin/main_core.py`, `plugin/librepy/`, `plugin/calc/python/addin_librepy.py`
- Bundle file list: `scripts/librepy_bundle_paths.py`

Topic docs: [docs/scripting-librepy-split.md](../../docs/scripting-librepy-split.md),
[docs/scripting-numpy-serialization.md](../../docs/scripting-numpy-serialization.md),
[docs/scripting-serialization-verification.md](../../docs/scripting-serialization-verification.md),
[docs/scripting-numpy-domains.md](../../docs/scripting-numpy-domains.md),
[docs/scripting-ms-py-compatibility.md](../../docs/scripting-ms-py-compatibility.md),
[docs/archive/scripting-domain-debt-dev-plan.md](../../docs/archive/scripting-domain-debt-dev-plan.md).

## Sharp edges

- Do **not** invent `python_config.py` or rename `writeragent.json` for LibrePy.
- Do **not** split `payload_codec.py` flatten/unpack without serialization A/B tests.
- Envelope-detector `@deal` + Hypothesis oracles on `payload_codec` (`is_split_grid`, `is_multi_data`, image / dataframe / calc_range) are **shipped**.
- Scripting domain registries (Phases 1–6) are shipped — do not add a fourth ad-hoc registry.
- `venv/calc_functions_*.py` alphabet splits are intentional; do not merge them.
- Do **not** slim `trusted_action_registry.py` / `venv_diagnostics.py` for LibrePy while those modules still work.
- Do **not** drop `plugin/calc/analyzer.py` from the LibrePy bundle.
- Shipped LibrePy (`make deploy-core`) defaults to `log_level` WARN; a checkout that still has `plugin/tests/` defaults to DEBUG.
