# -*- mode: python ; coding: utf-8 -*-
"""Build the standalone `ranse` application:

    pip install pyinstaller
    pyinstaller ranse.spec

One folder, deliberately: `plugins/` and `assets/` are directories the app
looks up at runtime (`resource_roots()` checks the executable's own folder
and the bundle folder `_internal/`), and one folder lets a user drop a
plugin in or replace a workbook without unpacking anything. This file is
build configuration, not an entry point — D3 still holds: the package
installs the `ranse` console script.

Entry: `src/ranse/__main__.py`, the module `python -m ranse` runs. It
imports `ranse.cli` absolutely so PyInstaller can run it as a top-level
script (a relative import has no parent package once frozen).

Plugins ship as plain source under `_internal/plugins`, never as compiled
modules: the loader puts that folder on `sys.path` at runtime, which is
exactly how a user-dropped `./plugins` works — so no hiddenimports are
needed, and a plugin placed next to the executable later is found the same
way.

PyInstaller caches its module analysis: after installing a new dependency,
build with `--clean` or the previous result is reused (yaml missing from
the binary is the symptom).
"""

import os

# Fail the build here rather than ship a binary that dies on import: what
# PyInstaller can bundle is what the build environment has installed.
try:
    import yaml  # noqa: F401
except ImportError:
    raise SystemExit(
        "PyYAML is not installed in this environment — install the "
        "project's dependencies first (pip install .) and build again")

# `assets/` is gitignored per-user data — ~300 MB of workbooks. It stays out
# of the bundle: copy `assets/` next to `ranse`, where resource_roots()
# looks first. Set to True to ship it inside `_internal/assets` instead (a
# one-folder build only — onefile would unpack it on every start).
BUNDLE_ASSETS = False

ROOT = os.path.abspath(SPECPATH)

a = Analysis(
    [os.path.join(ROOT, "src", "ranse", "__main__.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=[],
    datas=[(os.path.join(ROOT, "assets"), "assets")] if BUNDLE_ASSETS else [],
    # None: every third-party import is static (PyYAML, which PyInstaller's
    # own hook collects), and the plugin packages arrive as data files.
    hiddenimports=[],
    hookspath=[],
    hooks={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ranse",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # a CLI tool: it reads stdin and writes stdout
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    # The plugin folders, as source: pruned of __pycache__ so the bundle
    # carries no stale bytecode from the build machine.
    Tree(
        os.path.join(ROOT, "plugins"),
        prefix="plugins",
        excludes=["__pycache__"],
    ),
    strip=False,
    upx=False,
    name="ranse",
)
