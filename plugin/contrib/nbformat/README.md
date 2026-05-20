# Vendored nbformat (stripped)

Subset of [jupyter/nbformat](https://github.com/jupyter/nbformat) (BSD-3-Clause) for reading `.ipynb` files inside WriterAgent.

**Shipped:** v4 JSON read path — `rejoin_lines`, `strip_transient`, `NotebookNode`.

**Not shipped:** v1/v2/v3 converters, JSON schema validation (`fastjsonschema`), `traitlets`, `jupyter_core`.

**Deferred:** nbformat v3 upgrade (`v4/convert.py` in upstream). Revisit when users need legacy `.ipynb` files; see [enabling_numpy_in_libreoffice.md](../../docs/enabling_numpy_in_libreoffice.md#jupyter-notebook-import-ipynb).

**Upstream sources vendored from:**

- `nbformat/notebooknode.py`
- `nbformat/_struct.py` (trimmed)
- `nbformat/v4/rwbase.py`
- `nbformat/v4/nbjson.py` (read + write helpers)
- `nbformat/reader.py` (v4-only dispatch)
