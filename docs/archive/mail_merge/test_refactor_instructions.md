# Test Refactoring Instructions - TestingFactory Migration

## Objective

Consolidate test infrastructure by replacing manual mock setups, redundant `MockDoc` classes, and boilerplate `ToolContext` initialization with the shared stubs and `TestingFactory` in [`tests/testing_utils.py`](../../tests/testing_utils.py) (imported as `plugin.tests.testing_utils`).

## Key utilities

| API | Role |
|-----|------|
| `WriterDocStub` / `ElementStub` | Stateful Writer document for pure pytest |
| `CalcDocStub` (+ sheet/cell/range) | Stateful Calc document for pure pytest |
| `TestingFactory.create_doc(doc_type=...)` | Returns `WriterDocStub` or `CalcDocStub` (no MagicMock wrapper) |
| `TestingFactory.create_context(...)` | Builds a `ToolContext`; mock env creates a stub doc when `doc` omitted; pass `services=` for live plugin registry |
| `TestingFactory.execute_tool(doc, ctx, name, args, doc_type=...)` | Shared native tool runner (replaces per-file `_execute_calc_tool`) |
| `TestingFactory.create_native_doc` / `native_doc` / `@with_native_doc` | Live LibreOffice documents for `*_uno.py` tests |

### `create_doc` notes

- **Writer:** `content=` list of `ElementStub` paragraphs; `items=` style-family map for `getStyleFamilies()`.
- **Calc:** prefer `data=` 2D grid; also `selection=`, `props=`, `command_values=`.
- Native creation is **not** via `create_doc(env="native")` — use `create_native_doc(ctx, ...)` or `@with_native_doc`.

### `create_context` notes

- **Mock:** `TestingFactory.create_context(doc_type="writer"|"calc")`.
- **Native:** must pass an existing `doc=` (compose with `@with_native_doc`). Does not open documents itself.

## Refactoring patterns

### 1. Replacing manual MockDoc

```python
from plugin.tests.testing_utils import TestingFactory
doc = TestingFactory.create_doc(doc_type="writer")  # WriterDocStub
# or
doc = TestingFactory.create_doc(doc_type="calc", data=(("a", 1),))
```

### 2. Replacing manual ToolContext

```python
from plugin.tests.testing_utils import TestingFactory
ctx = TestingFactory.create_context(doc_type="writer")
# When the tool needs UNO surfaces the stub does not model yet:
ctx = TestingFactory.create_context(doc=MagicMock(), doc_type="writer")
```

### 3. Native test setup

```python
from plugin.tests.testing_utils import TestingFactory, with_native_doc

@with_native_doc("writer")
def test_something(ctx, doc):
    tool_ctx = TestingFactory.create_context(doc=doc, ctx=ctx, env="native")
    ...
```

## Step-by-step

1. Prefer `WriterDocStub` / `CalcDocStub` over ad-hoc `MagicMock` document stacks.
2. Import from `plugin.tests.testing_utils`.
3. Use `create_context` instead of hand-rolled `ToolContext` / `DummyContext`.
4. Keep format-heavy Calc stacks (`test_cells.py`) on MagicMock until number-format stubs exist.
5. Run `pytest` for unit files; native suites via `testing_runner` / `make test`.

## Example files

- [`tests/framework/test_tool.py`](../../tests/framework/test_tool.py)
- [`tests/writer/test_styles.py`](../../tests/writer/test_styles.py)
- [`tests/calc/test_editselection.py`](../../tests/calc/test_editselection.py)
- [`tests/test_testing_utils.py`](../../tests/test_testing_utils.py)
