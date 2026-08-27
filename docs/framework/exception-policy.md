# UNO exception policy (disposed vs expected failures)

Do **not** catch `com.sun.star.uno.Exception` in order to “avoid” `DisposedException`. In UNO, `DisposedException` subclasses `RuntimeException`, which subclasses `uno.Exception`, so that catch still swallows disposal.

Use the helpers in `plugin/framework/errors.py`: `is_disposed_exception`, `suppress_disposed`, `DocumentDisposedError`.

| Layer | On disposal / bridge teardown | On expected UNO/Python errors | Silent `except Exception: pass` |
|--------|-------------------------------|-------------------------------|----------------------------------|
| UI lifecycle (sidebar, rich text, panel) | `with suppress_disposed(...)` | Keep fallbacks; unexpected errors are logged (`suppress_all=True`) | Replace with `suppress_disposed` |
| Document tools (`visual_helpers`, edit review, charts, shapes, notebook) | Re-raise or wrap `DocumentDisposedError` | Leaf types only: `UnknownPropertyException`, `NoSuchElementException`, `IndexOutOfBoundsException`, `IllegalArgumentException`, `AttributeError`, `ValueError` | `log.exception` / `log.debug(..., exc_info=True)` or drop the catch |

Best-effort probes (missing properties, optional controllers, “is this a graphic?”) may still catch `Exception` and return empty. That is not the hang class of bug. Re-raise disposal where a UI callback or tool loop would otherwise keep running on a dead object; do not sprinkle re-raises through every helper.

Related: [chat sidebar lifecycle](../chat/sidebar-implementation.md#ui-lifecycle-exception-handling-suppress_disposed), [UNO thread safety](uno-thread-safety.md).
