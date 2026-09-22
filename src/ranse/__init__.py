"""ranse — fill Malaysian e-RPH Excel templates from weekly timetables."""

import os

# Repository root: the directory holding src/, profiles/, config/ and
# assets/. The package sits three levels below it (src/ranse/__init__.py),
# so it takes three dirname() calls. _resolve_path bases depend on this value
# (relative profile/calendar paths fall back to the repo root).
_REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
