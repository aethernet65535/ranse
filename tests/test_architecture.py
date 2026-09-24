"""Architecture tests: dependency direction + vocabulary neutrality.

docs/DESIGN.md decision 6 (no business logic or vocabulary in `core`; the
business sits behind declarative extension points) and the dependency
direction (core knows nothing above it; inputs never call back up into the
handlers or the CLI) are contract — this module turns them into CI
assertions instead of conventions.

Deliberately NOT subject to the vocabulary scan:
- ``model.py`` — the domain model carries business semantics by design (S2);
- ``handlers/<name>/``, ``inputs/{calendar,dskp,timetable}/`` — those *are*
  the business (business handlers and business readers);
- the registry files are whitelisted (see ``_VOCAB_EXEMPT``): they are the
  plug-in points where business names legitimately live (decision 2).
"""

import ast
from pathlib import Path

from harness import REPO_ROOT, SRC_DIR

PKG = SRC_DIR / "ranse"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _py_files(*parts):
    return sorted(Path(*parts).rglob("*.py"), key=str)


def _module_name(path):
    """'ranse.core.xlsx' for src/ranse/core/xlsx.py ('ranse' for __init__)."""
    parts = path.relative_to(SRC_DIR).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_modules(path):
    """Every module this file imports, with relative imports resolved."""
    module = _module_name(path)
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


def _violations(paths, forbidden):
    """Human-readable violations of an import rule."""
    out = []
    for path in paths:
        for mod in _imported_modules(path):
            if any(mod == f or mod.startswith(f + ".") for f in forbidden):
                out.append(f"{path.relative_to(REPO_ROOT)} imports {mod}")
    return out


# ---------------------------------------------------------------------------
# 1. dependency direction
# ---------------------------------------------------------------------------

_CORE = _py_files(PKG / "core")
_ALL_INPUTS = _py_files(PKG / "inputs")
_CLI = [PKG / "cli.py"]

# Concrete handlers/readers the orchestrator must never name (it learns them
# from handlers/registry.py and inputs/__init__.py instead).
_CONCRETE = [
    "ranse.handlers.week", "ranse.handlers.menu",
    "ranse.handlers.fixed_cells", "ranse.handlers.dskp",
    "ranse.inputs.timetable", "ranse.inputs.dskp", "ranse.inputs.calendar",
]


def test_core_depends_on_nothing_above_it():
    # core may use errors/model/formats — never the CLI, a handler, a reader.
    assert not _violations(
        _CORE, ["ranse.handlers", "ranse.inputs", "ranse.cli"])


def test_cli_knows_only_registries_and_the_profile_reader():
    # cli composes base + registry + profile reader; concrete handlers and
    # readers are reached through the registries, never imported.
    assert not _violations(_CLI, _CONCRETE)


def test_inputs_never_call_back_up():
    # dependencies go one way: handlers/cli → inputs, never the reverse.
    assert not _violations(_ALL_INPUTS, ["ranse.handlers", "ranse.cli"])


def test_generic_readers_do_not_import_each_other():
    # one format one folder (inputs/README.md): the profile reader and the
    # calendar reader stay independent of the other readers.
    readers = ("yaml", "calendar", "timetable", "dskp")
    for reader in ("yaml", "calendar"):
        paths = _py_files(PKG / "inputs" / reader)
        siblings = [f"ranse.inputs.{r}" for r in readers if r != reader]
        assert not _violations(paths, siblings)


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
    PKG / "handlers" / "registry.py",
]

# Plug-in points are allowed to name the business — that is where the
# business plugs in (built-in registries, decision 2).
_VOCAB_EXEMPT = {
    PKG / "inputs" / "__init__.py": "the reader registry (business plug-in point)",
    PKG / "handlers" / "registry.py": "the handler registry (business plug-in point)",
}


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
