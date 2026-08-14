"""LibrePy allowlist must cover top-level plugin imports of shipped modules."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.librepy_bundle_paths import collect_librepy_plugin_paths  # noqa: E402

_FORBIDDEN_PREFIXES = (
    "plugin.doc.document_helpers",
    "plugin.framework.client.llm_client",
    "plugin.framework.tool",
    "plugin.main",
    "plugin.embeddings",
    "plugin.writer.ops",
    "plugin.writer.review_authors",
    "plugin.writer.content",
    "plugin.writer.images.image_utils",
    "plugin.writer.images.images",
)

# Lazy attrs on plugin.framework.client that load modules not in the LibrePy OXT.
_FORBIDDEN_CLIENT_ATTRS = frozenset(
    {
        "LlmClient",
        "OPENROUTER_CHAT_EXTRA_BLOCKLIST",
        "merge_openrouter_chat_extra",
        "strip_leaked_chat_template_control_tokens",
        "EmbeddingBatch",
        "embed_texts",
        "get_embedding_model",
        "delete_paragraphs",
        "index_paragraphs",
        "knn_search",
        "iterate_sse",
        "run_trusted_analysis",
    }
)


def _is_type_checking_if(node: ast.If) -> bool:
    test = node.test
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return True
    return False


def _module_level_import_nodes(tree: ast.AST) -> list[ast.AST]:
    nodes: list[ast.AST] = []

    def walk(body: list[ast.stmt]) -> None:
        for stmt in body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                nodes.append(stmt)
            elif isinstance(stmt, ast.If):
                if _is_type_checking_if(stmt):
                    continue
                walk(stmt.body)
                walk(stmt.orelse)
            elif isinstance(stmt, ast.Try):
                handler_names = []
                for handler in stmt.handlers:
                    if handler.type is None:
                        handler_names.append("bare")
                    elif isinstance(handler.type, ast.Name):
                        handler_names.append(handler.type.id)
                    elif isinstance(handler.type, ast.Tuple):
                        handler_names.extend(
                            elt.id for elt in handler.type.elts if isinstance(elt, ast.Name)
                        )
                # Optional imports (Cython accelerator, generated manifest, etc.)
                if "ImportError" in handler_names or "ModuleNotFoundError" in handler_names:
                    walk(stmt.orelse)
                    walk(stmt.finalbody)
                    continue
                walk(stmt.body)
                for handler in stmt.handlers:
                    walk(handler.body)
                walk(stmt.orelse)
                walk(stmt.finalbody)
            elif isinstance(stmt, ast.With):
                walk(stmt.body)

    walk(tree.body)
    return nodes


def _plugin_mod_to_candidates(mod: str) -> tuple[str, ...]:
    rel = mod.replace(".", "/")
    return (rel + ".py", rel + "/__init__.py")


def _imported_plugin_modules(path: Path, tree: ast.AST) -> list[str]:
    pkg_parts = path.relative_to(_REPO_ROOT).with_suffix("").parts
    parent_pkg = pkg_parts[:-1]
    found: list[str] = []
    for node in _module_level_import_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "plugin" or alias.name.startswith("plugin."):
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level > len(parent_pkg):
                    continue
                rel_base = parent_pkg[: len(parent_pkg) - node.level + 1]
                if node.module:
                    mods = [".".join(rel_base + tuple(node.module.split(".")))]
                else:
                    mods = [".".join(rel_base + (alias.name,)) for alias in node.names]
            else:
                mods = [node.module] if node.module else []
            for mod in mods:
                if mod == "plugin" or mod.startswith("plugin."):
                    found.append(mod)
    return found


def _resolved_import_from_module(path: Path, node: ast.ImportFrom) -> str | None:
    pkg_parts = path.relative_to(_REPO_ROOT).with_suffix("").parts
    parent_pkg = pkg_parts[:-1]
    if node.level:
        if node.level > len(parent_pkg):
            return None
        rel_base = parent_pkg[: len(parent_pkg) - node.level + 1]
        if node.module:
            return ".".join(rel_base + tuple(node.module.split(".")))
        return ".".join(rel_base)
    return node.module


def _forbidden_client_attr_hits(path: Path, tree: ast.AST) -> list[str]:
    """``from plugin.framework.client import LlmClient`` is not a llm_client prefix hit."""
    hits: list[str] = []
    for node in _module_level_import_nodes(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if _resolved_import_from_module(path, node) != "plugin.framework.client":
            continue
        if node.names and node.names[0].name == "*":
            hits.append("*")
            continue
        for alias in node.names:
            if alias.name in _FORBIDDEN_CLIENT_ATTRS:
                hits.append(alias.name)
    return hits


def test_librepy_bundle_includes_xl_static_rewrite_and_addin_impl():
    paths = collect_librepy_plugin_paths(str(_REPO_ROOT))
    assert "plugin/calc/python/xl_static_rewrite.py" in paths
    assert "plugin/calc/python/addin_impl.py" in paths
    assert "plugin/scripting/native_binaries.py" in paths
    assert "plugin/scripting/audio_recorder_service.py" not in paths
    assert "plugin/calc/python/workbook_lifecycle.py" in paths


def test_librepy_shipped_toplevel_plugin_imports_are_bundled():
    shipped = set(collect_librepy_plugin_paths(str(_REPO_ROOT)))
    missing: list[str] = []
    for rel in sorted(shipped):
        if not rel.endswith(".py"):
            continue
        path = _REPO_ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for attr in _forbidden_client_attr_hits(path, tree):
            missing.append(f"{rel} top-level-imports-forbidden plugin.framework.client.{attr}")
        for mod in _imported_plugin_modules(path, tree):
            if any(mod == prefix or mod.startswith(prefix + ".") for prefix in _FORBIDDEN_PREFIXES):
                missing.append(f"{rel} top-level-imports-forbidden {mod}")
                continue
            if mod in ("plugin._manifest", "plugin._manifest_librepy"):
                continue
            if rel == "plugin/contrib/smolagents/__init__.py":
                # build_librepy_oxt.py replaces this with a slim stub.
                continue
            cands = _plugin_mod_to_candidates(mod)
            if not any(c in shipped for c in cands):
                # Importing a package (plugin.scripting) is ok if __init__.py ships.
                missing.append(f"{rel} -> {mod} (tried {cands})")
    assert missing == []


def test_from_client_import_llmclient_is_forbidden():
    dummy = _REPO_ROOT / "plugin" / "librepy" / "settings.py"
    tree = ast.parse("from plugin.framework.client import LlmClient, sync_request")
    assert _forbidden_client_attr_hits(dummy, tree) == ["LlmClient"]
    tree_ok = ast.parse("from plugin.framework.client import sync_request")
    assert _forbidden_client_attr_hits(dummy, tree_ok) == []


def test_librepy_entry_imports_avoid_writeragent_only_modules():
    from plugin.tests.testing_utils import setup_uno_mocks

    setup_uno_mocks()
    before = set(sys.modules)
    import plugin.calc.python.editor  # noqa: F401
    import plugin.calc.python.function  # noqa: F401
    import plugin.librepy.python_sidebar  # noqa: F401
    import plugin.librepy.settings  # noqa: F401
    import plugin.scripting.python_runner  # noqa: F401

    loaded = set(sys.modules) - before
    bad = [
        name
        for name in loaded
        if any(name == prefix or name.startswith(prefix + ".") for prefix in _FORBIDDEN_PREFIXES)
    ]
    assert bad == []
