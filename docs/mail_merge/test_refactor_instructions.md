# Test Refactoring Instructions - TestingFactory Migration

## Objective
Consolidate test infrastructure by replacing manual mock setups, redundant `MockDoc` classes, and boilerplate `ToolContext` initialization with calls to the unified `TestingFactory` in `plugin/tests/testing_utils.py`.

## Key Utility: `TestingFactory`
Located in: [testing_utils.py](file:///home/keithcu/Desktop/Python/writeragent/plugin/tests/testing_utils.py)

### Main Methods:
- `TestingFactory.create_doc(env="mock", doc_type="writer", content=None, **kwargs)`
  - Returns a mock document (default) or a stub.
  - Supports `items` (for style families/collections) and `content` (list of paragraph stubs).
- `TestingFactory.create_context(doc=None, ctx=None, env="mock", doc_type="writer")`
  - Returns a `ToolContext` initialized with mock or native services.
- `TestingFactory.setup_tool(tool_class, env="mock", doc_type="writer", ...)`
  - Convenience helper to get a tool instance and its context.
- `TestingFactory.create_native_doc(ctx, doc_type="writer")`
  - Creates a real LibreOffice document (requires a valid UNO context).

## Refactoring Patterns

### 1. Replacing manual MockDoc
**Before:**
```python
class MockDoc:
    def supportsService(self, s): ...
doc = MockDoc()
```
**After:**
```python
from plugin.tests.testing_utils import TestingFactory
doc = TestingFactory.create_doc(doc_type="writer")
```

### 2. Replacing manual ToolContext
**Before:**
```python
ctx = ToolContext(doc=doc, ctx=None, doc_type="writer", services=ServiceRegistry())
```
**After:**
```python
from plugin.tests.testing_utils import TestingFactory
ctx = TestingFactory.create_context(doc=doc, doc_type="writer")
```

### 3. Native Test Setup
**Before:**
```python
@setup
def setup_tests(ctx):
    desktop = get_desktop(ctx)
    _test_doc = desktop.loadComponentFromURL("private:factory/swriter", ...)
```
**After:**
```python
@setup
def setup_tests(ctx):
    _test_doc = TestingFactory.create_native_doc(ctx, "writer")
```

## Step-by-Step for Agent
1. **Identify** redundant mock classes (like `MockDoc`, `MockContext`) and remove them.
2. **Import** `TestingFactory` from `plugin.tests.testing_utils`.
3. **Replace** document/context creation with factory methods.
4. **Verify** that test-specific properties (like `items` for style tests) are passed to `create_doc`.
5. **Run** the specific test file using `pytest` (for unit tests) or `testing_runner` (for native tests).
6. **Ensure** all tests in the file pass before completing.

## Example Refactored Files
- [test_tool.py](file:///home/keithcu/Desktop/Python/writeragent/plugin/tests/test_tool.py)
- [test_writer_styles.py](file:///home/keithcu/Desktop/Python/writeragent/plugin/tests/test_writer_styles.py)
- [uno/test_writer.py](file:///home/keithcu/Desktop/Python/writeragent/plugin/tests/uno/test_writer.py)
