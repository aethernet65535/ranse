"""ranse — fill spreadsheet templates in place, driven by a profile."""

import os

# Repository root: the directory holding src/, plugins/ and assets/. The
# package sits three levels below it (src/ranse/__init__.py), so it takes
# three dirname() calls.
_REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))

# Only a source checkout has a meaningful repo root: the root must really
# hold this project's files (pyproject + the package under src/). An
# installed wheel's site-packages parent has neither, so the fallbacks built
# on _REPO_ROOT (input paths, plugin discovery) silently stay out of the way
# instead of guessing next to the installed package.
_IS_SOURCE_CHECKOUT = (
    os.path.isfile(os.path.join(_REPO_ROOT, "pyproject.toml"))
    and os.path.isdir(os.path.join(_REPO_ROOT, "src", "ranse")))
