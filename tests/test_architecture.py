"""Architecture tests: dependency direction + vocabulary neutrality.

docs/DESIGN.md decision 6 (no business logic or vocabulary in `core`; the
business sits behind declarative extension points) and the dependency
direction (core knows nothing above it; inputs never call back up into the
handlers or the CLI) are contract — this module turns them into CI
assertions instead of conventions.

Deliberately NOT subject to the vocabulary scan:
- everything under ``plugins/`` — that *is* the business (handlers, readers,
  profiles and data files); Phase 4 scans it with the mirror exemption list.
"""

import ast
from pathlib import Path

from harness import PLUGINS_DIR, REPO_ROOT, SRC_DIR

PKG = SRC_DIR / "ranse"
PLUGIN_PKG = PLUGINS_DIR / "erph"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _py_files(*parts):
    return sorted(Path(*parts).rglob("*.py"), key=str)


def _module_name(path, root):
    """'ranse.core.xlsx' for src/ranse/core/xlsx.py ('ranse' for __init__)."""
    parts = path.relative_to(root).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_modules(path, root=SRC_DIR):
    """Every module this file imports, with relative imports resolved."""
    module = _module_name(path, root)
    # Base package for a level-1 relative import: the file's own package
    # (the package itself for __init__.py, the parent otherwise).
    pkg = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                found.append(node.module or "")
            else:
                base_parts = pkg.split(".") if pkg else []
                keep = max(len(base_parts) - (node.level - 1), 0)
                base = ".".join(base_parts[:keep])
                found.append(".".join(p for p in (base, node.module or "") if p))
    return found


def _violations(paths, forbidden, root=SRC_DIR):
    """Human-readable violations of an import rule."""
    out = []
    for path in paths:
        for mod in _imported_modules(path, root):
            if any(mod == f or mod.startswith(f + ".") for f in forbidden):
                out.append(f"{path.relative_to(REPO_ROOT)} imports {mod}")
    return out


# ---------------------------------------------------------------------------
# 1. dependency direction
# ---------------------------------------------------------------------------

_CORE = _py_files(PKG / "core")
_ALL_INPUTS = _py_files(PKG / "inputs")
_CLI = [PKG / "cli.py"]
_FRAMEWORK = _py_files(PKG)
_PLUGIN = _py_files(PLUGIN_PKG)

# The framework may never name a plugin: handlers and readers are reached
# through the plugin loader (handlers/loader.py, plugins.py).
_PLUGIN_IMPORTS = ("erph",)
_LOADER_FILES = {PKG / "plugins.py", PKG / "handlers" / "loader.py"}


def test_core_depends_on_nothing_above_it():
    # core may use errors/model/formats — never the CLI, a handler, a reader.
    assert not _violations(
        _CORE, ["ranse.handlers", "ranse.inputs", "ranse.cli"])


def test_cli_knows_only_registries_and_the_profile_reader():
    # cli composes base + the plugin loader + profile reader; concrete
    # handlers and readers are reached through the loader, never imported.
    assert not _violations(_CLI, list(_PLUGIN_IMPORTS))


def test_only_the_loader_imports_a_plugin():
    # Discovery is the loader's job (decision 2, revised): everything else in
    # the framework stays plugin-agnostic.
    scanned = [p for p in _FRAMEWORK if p not in _LOADER_FILES]
    assert not _violations(scanned, list(_PLUGIN_IMPORTS))


def test_inputs_never_call_back_up():
    # dependencies go one way: handlers/cli → inputs, never the reverse.
    assert not _violations(_ALL_INPUTS, ["ranse.handlers", "ranse.cli"])


def test_one_folder_per_source_format():
    # One format, one folder: the framework's own profile reader stays
    # independent of the plugin's readers, and the plugin's readers stay
    # independent of each other.
    assert not _violations(_py_files(PKG / "inputs" / "yaml"),
                           ["erph.inputs"])
    readers = ("calendar", "timetable", "dskp")
    for reader in readers:
        siblings = [f"erph.inputs.{r}" for r in readers if r != reader]
        assert not _violations(_py_files(PLUGIN_PKG / "inputs" / reader),
                               siblings, root=PLUGINS_DIR)


def test_plugin_readers_never_call_back_up():
    # Same rule as the framework's own readers: a reader may not reach into
    # the handlers or the CLI.
    assert not _violations(_py_files(PLUGIN_PKG / "inputs"),
                           ["erph.handlers", "ranse.cli"], root=PLUGINS_DIR)


def test_plugins_do_not_import_each_other():
    # A plugin talks to the framework and to its own package, never to
    # another plugin (the plugin loader is what composes them).
    plugins = sorted(p.name for p in PLUGINS_DIR.iterdir() if p.is_dir())
    for plugin in plugins:
        for path in _py_files(PLUGINS_DIR / plugin):
            others = [f"{other}" for other in plugins if other != plugin]
            assert not _violations([path], others, root=PLUGINS_DIR), (
                f"{path.relative_to(REPO_ROOT)} imports another plugin")


# ---------------------------------------------------------------------------
# 2. vocabulary neutrality (decision 6)
# ---------------------------------------------------------------------------

_BUSINESS_WORDS = (
    "DSKP", "ERPH", "RPH", "MENU", "jadual", "tingkatan", "minggu",
    "cuti", "siri", "timetable",
    "Ahad", "Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu",
)

_VOCAB_FILES = _CORE + _py_files(PKG / "inputs" / "yaml") + [
    PKG / "cli.py",
    PKG / "errors.py",
    PKG / "inputs" / "__init__.py",
    PKG / "handlers" / "base.py",
    PKG / "handlers" / "loader.py",
    PKG / "plugins.py",
]

# Phase 4 clears this: the framework now names no business at all — the
# plug-in points moved out to `plugins/`, which is scanned separately.
_VOCAB_EXEMPT = {}


def test_framework_code_carries_no_business_vocabulary():
    lower_words = tuple(w.lower() for w in _BUSINESS_WORDS)
    for path in _VOCAB_FILES:
        if path in _VOCAB_EXEMPT:
            continue
        text = path.read_text(encoding="utf-8").lower()
        hits = sorted({w for w in lower_words if w in text})
        assert not hits, (
            f"{path.relative_to(REPO_ROOT)} speaks business vocabulary "
            f"{hits} — business words belong behind the extension points "
            "(docs/DESIGN.md decision 6); a registry/plug-in file may be "
            "whitelisted in _VOCAB_EXEMPT with a reason")


def test_every_vocabulary_exempt_file_still_exists():
    # keep the whitelist honest: no stale exemptions.
    for path in _VOCAB_EXEMPT:
        assert path.exists(), f"stale whitelist entry: {path}"
        assert path in _VOCAB_FILES, f"whitelisted file not scanned: {path}"
