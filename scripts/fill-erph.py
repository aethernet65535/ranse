#!/usr/bin/env python3
"""Deprecated compatibility entry point — all logic moved to the ranse package.

Kept until stage 4 removes scripts/ (PLAN.md decision 3). The invocation is
unchanged:

    python scripts/fill-erph.py --xlsx <template.xlsx> [--config ...] [--date YYYY-MM-DD]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ranse.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
