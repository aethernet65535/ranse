"""Architecture tests: dependency direction + vocabulary neutrality.

Two contracts live here (docs/DESIGN.md S2/S9):

1. **Dependency direction** — ``core`` knows nothing above it, ``inputs``
   never call back up into the handlers or the CLI, and the framework reaches
   a plugin only through the plugin loader.
2. **Vocabulary neutrality** — the framework names no business at all: its
   code carries neither the old Malay vocabulary nor the business concepts in
   English. The business is ``plugins/``; there it may name whatever it
   owns, except that the frozen spellings of the source artifacts may only
   live in the mirrors whitelisted in ``_MIRROR_EXEMPT``.

The word lists are grep-derived (decision D6, applied to the whole package):
the scan runs over **every** file of ``src/ranse`` with an empty whitelist.
``DSKP`` and ``ERPH`` are never scanned — those two names are the business
itself and stay allowed (docs/DESIGN.md, the anglicization boundary).
"""

import ast
import re
from pathlib import Path

from harness import PLUGINS_DIR, REPO_ROOT, SRC_DIR

PKG = SRC_DIR / "ranse"
PLUGIN_PKGS = sorted(p for p in PLUGINS_DIR.iterdir() if p.is_dir())


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


def _word_hits(path, words):
    """The word list entry that ``path`` speaks, if any (whole words only)."""
    text = path.read_text(encoding="utf-8")
    return sorted({w for w in words
                   if re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE)})


# ---------------------------------------------------------------------------
# 1. dependency direction
# ---------------------------------------------------------------------------

_CORE = _py_files(PKG / "core")
_ALL_INPUTS = _py_files(PKG / "inputs")
_CLI = [PKG / "cli.py"]
_FRAMEWORK = _py_files(PKG)

# The framework may never name a plugin: handlers and readers are reached
# through the plugin loader (plugins.py) instead.
_PLUGINS = tuple(p.name for p in PLUGIN_PKGS)
_LOADER_FILES = {PKG / "plugins.py", PKG / "handlers" / "loader.py"}


def test_core_depends_on_nothing_above_it():
    # core may use errors/model/formats — never the CLI, a handler, a reader,
    # a plugin.
    assert not _violations(
        _CORE, ["ranse.handlers", "ranse.inputs", "ranse.cli", *_PLUGINS])


def test_cli_knows_only_registries_and_the_profile_reader():
    # cli composes base + the plugin loader + profile reader; concrete
    # handlers and readers are reached through the loader, never imported.
    assert not _violations(_CLI, list(_PLUGINS))


def test_only_the_loader_imports_a_plugin():
    # Discovery is the loader's job (decision 2, revised): everything else in
    # the framework stays plugin-agnostic.
    scanned = [p for p in _FRAMEWORK if p not in _LOADER_FILES]
    assert not _violations(scanned, list(_PLUGINS))


def test_only_the_loader_touches_the_import_machinery():
    # Importlib and sys.path manipulation are plugin discovery, nothing else
    # (source-level check, same spirit as the import rules above).
    for path in _FRAMEWORK:
        if path in _LOADER_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        assert "importlib" not in text, (
            f"{path.relative_to(REPO_ROOT)} imports importlib — plugin "
            "discovery belongs in the loader")
        assert "sys.path" not in text, (
            f"{path.relative_to(REPO_ROOT)} touches sys.path — plugin "
            "discovery belongs in the loader")


def test_inputs_never_call_back_up():
    # dependencies go one way: handlers/cli → inputs, never the reverse.
    assert not _violations(_ALL_INPUTS, ["ranse.handlers", "ranse.cli"])


def test_one_folder_per_source_format():
    # One format, one folder: the framework's own profile reader stays
    # independent of a plugin's readers, and a plugin's readers stay
    # independent of each other.
    for plugin in PLUGIN_PKGS:
        assert not _violations(_py_files(PKG / "inputs" / "yaml"),
                               [f"{plugin.name}.inputs"])
        readers = sorted(p.name for p in (plugin / "inputs").iterdir()
                         if p.is_dir())
        for reader in readers:
            siblings = [f"{plugin.name}.inputs.{r}"
                        for r in readers if r != reader]
            assert not _violations(_py_files(plugin / "inputs" / reader),
                                   siblings, root=PLUGINS_DIR)


def test_plugin_readers_never_call_back_up():
    # Same rule as the framework's own readers: a reader may not reach into
    # the handlers or the CLI.
    for plugin in PLUGIN_PKGS:
        assert not _violations(_py_files(plugin / "inputs"),
                               [f"{plugin.name}.handlers", "ranse.cli"],
                               root=PLUGINS_DIR)


def test_a_plugin_imports_only_the_framework_and_itself():
    # A plugin talks to the framework and to its own package, never to
    # another plugin (the plugin loader is what composes them).
    for plugin in PLUGIN_PKGS:
        others = [p.name for p in PLUGIN_PKGS if p.name != plugin.name]
        for path in _py_files(plugin):
            assert not _violations([path], others, root=PLUGINS_DIR), (
                f"{path.relative_to(REPO_ROOT)} imports another plugin")


# ---------------------------------------------------------------------------
# 2. vocabulary neutrality (decision 6)
# ---------------------------------------------------------------------------

# The old Malay vocabulary, in full — the language the business used to be
# written in, and the language of the frozen artifacts (see S9).
_MALAY_WORDS = (
    "jadual", "minggu", "cuti", "siri", "tingkatan", "hari", "waktu",
    "sekolah", "murid", "guru", "kelas", "rancangan", "pengajaran",
    "harian", "aktiviti", "tarikh",
    "ahad", "isnin", "selasa", "rabu", "khamis", "jumaat", "sabtu",
)

# The business in English: concepts the framework must not name, whatever
# language it speaks them in. `week` is deliberately absent — it is the
# framework's own template contract (`inputs.template` may contain the
# `{week}` placeholder, and `inputs.templates` is keyed by the value
# published under it; docs/DESIGN.md S3.3 / D10).
_BUSINESS_ENGLISH = (
    "lesson", "schedule", "subject", "timetable", "calendar", "holiday",
    "series", "day", "school", "teacher", "pupil", "student", "classroom",
    "menu", "dskp", "erph", "rph",
)

_FRAMEWORK_WORDS = _MALAY_WORDS + _BUSINESS_ENGLISH

# The whole framework package, with nothing whitelisted: after the plugin
# reorganisation there is no plug-in point left inside src/ranse that could
# legitimately name the business (D2 revised — the plug-in points are
# directories under ./plugins).
_VOCAB_FILES = _FRAMEWORK
_VOCAB_EXEMPT = {}

# Inside a plugin the business vocabulary is expected — except the *frozen
# spellings of the source artifacts*, which may only live in the mirrors that
# exist to translate them, one file per plugin with a reason.
_MIRROR_EXEMPT = {
    "erph/domain.py":
        "the source mirrors: the timetable's day headers (xlsx and csv) and "
        "the workbook's day-sheet names are frozen artifact and must keep "
        "matching, so their spellings live here and nowhere else",
}


def test_framework_code_carries_no_business_vocabulary():
    for path in _VOCAB_FILES:
        if path in _VOCAB_EXEMPT:
            continue
        hits = _word_hits(path, _FRAMEWORK_WORDS)
        assert not hits, (
            f"{path.relative_to(REPO_ROOT)} speaks business vocabulary "
            f"{hits} — the framework names no business at all "
            "(docs/DESIGN.md decision 6); the business belongs in "
            "plugins/")


def test_the_framework_whitelist_is_empty():
    # The point of the reorganisation: no exemption is needed any more.
    assert _VOCAB_EXEMPT == {}


def test_plugin_code_carries_only_the_frozen_artifact_spellings():
    for plugin in PLUGIN_PKGS:
        for path in _py_files(plugin):
            key = str(path.relative_to(PLUGINS_DIR))
            if key in _MIRROR_EXEMPT:
                continue
            hits = _word_hits(path, _MALAY_WORDS)
            assert not hits, (
                f"{path.relative_to(REPO_ROOT)} speaks Malay vocabulary "
                f"{hits} — the plugin's own prose is English; a frozen "
                "artifact spelling belongs in the plugin's mirror module "
                "(add it to _MIRROR_EXEMPT with a reason if it must)")


def test_every_mirror_exemption_is_used_and_lives_in_a_plugin():
    # keep the mirror whitelist honest: the file must exist, must be part of
    # a plugin, and must still be the place the frozen spellings live.
    for key, reason in _MIRROR_EXEMPT.items():
        path = PLUGINS_DIR / key
        assert path.is_file(), f"stale mirror exemption: {key}"
        assert reason, f"mirror exemption without a reason: {key}"
        assert _word_hits(path, _MALAY_WORDS), (
            f"mirror exemption {key} names no frozen spelling any more — "
            "drop it")


def test_the_word_lists_keep_the_whole_malay_set():
    # A guard on the word list itself: all seven Malay day names and the
    # words the scan was written around must stay in the list.
    for word in ("jadual", "minggu", "cuti", "siri", "tingkatan",
                 "Ahad", "Isnin", "Selasa", "Rabu", "Khamis", "Jumaat",
                 "Sabtu"):
        assert word.lower() in _MALAY_WORDS, f"{word} left the word list"
    # DSKP / ERPH are the business itself: never scanned (S9).
    assert "dskp" not in _MALAY_WORDS and "erph" not in _MALAY_WORDS


def test_the_vocabulary_scan_is_not_vacuous(tmp_path):
    # Negative control: the scans above are only worth anything if they
    # would catch a business word (and if they really read the package).
    sample = tmp_path / "sample.py"
    sample.write_text("DAYS = ('Ahad',)\n# the weekly timetable\n",
                      encoding="utf-8")
    assert _word_hits(sample, _FRAMEWORK_WORDS) == ["ahad", "timetable"]
    assert len(_VOCAB_FILES) > 10
    assert _py_files(PKG)
