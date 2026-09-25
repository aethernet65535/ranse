"""ranse — fill spreadsheet templates in place, driven by a profile."""

import os
import sys

# Repository root: the directory holding src/, plugins/ and assets/. The
# package sits three levels below it (src/ranse/__init__.py), so it takes
# three dirname() calls.
_REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))

# Only a source checkout has a meaningful repo root: the root must really
# hold this project's files (pyproject + the package under src/). An
# installed wheel's site-packages parent has neither, so resource_roots()
# (input paths, plugin discovery) silently stays out of the way instead of
# guessing next to the installed package.
_IS_SOURCE_CHECKOUT = (
    os.path.isfile(os.path.join(_REPO_ROOT, "pyproject.toml"))
    and os.path.isdir(os.path.join(_REPO_ROOT, "src", "ranse")))

# Nuitka deliberately sets no ``sys.frozen`` ("it usually triggers inferior
# code" — user manual); a compiled module carries ``__compiled__`` instead,
# and its containing folder is where its files live. Resolved once here, so
# the NameError is paid at import time only. Plain CPython and PyInstaller
# both leave it undefined.
try:
    _COMPILED_DIR = __compiled__.containing_dir
except NameError:
    _COMPILED_DIR = None


def resource_roots():
    """The roots holding this application's own files, in resolution order.

    Callers put these **last** — after whatever the user pointed them at —
    because they are the application's, not the project's.

    A source checkout contributes its repository root (and only then: see
    ``_IS_SOURCE_CHECKOUT``). A packaged app contributes the folder of the
    executable the user actually launched — its working directory may be
    anywhere (a Windows shortcut that lacks "Start in" starts the program
    in System32), so the current directory is never this app's anchor —
    plus, depending on how it was packaged, the folder the bootloader
    unpacks to (PyInstaller) or the compiled module's containing folder
    (Nuitka).
    """
    if getattr(sys, "frozen", False):
        candidates = (os.path.dirname(os.path.abspath(sys.executable)),
                      getattr(sys, "_MEIPASS", None))
    else:
        candidates = (_REPO_ROOT if _IS_SOURCE_CHECKOUT else None,
                      _COMPILED_DIR)

    roots = []
    for candidate in candidates:
        if candidate and candidate not in roots:
            roots.append(candidate)
    return roots
