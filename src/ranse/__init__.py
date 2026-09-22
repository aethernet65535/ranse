"""ranse — fill Malaysian e-RPH Excel templates from weekly timetables."""

import os

# Repository root, kept at its historical VALUE (the directory holding both
# scripts/ and src/). The original definition lived in scripts/fill-erph.py
# as two dirname() levels from that file; the package sits one level deeper
# (src/ranse/), so it takes three here. _resolve_path bases depend on it.
_REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
