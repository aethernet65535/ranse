#!/usr/bin/env python3
"""Deprecated compatibility entry point — implementation moved to ranse package.

The parser/selection code now lives in src/ranse/inputs/dskp.py; this shim
keeps `python scripts/gen_dskp.py ...` working until stage 4 removes scripts/
(PLAN.md stage 1: "保留其 main()，阶段 4 接 CLI").
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ranse.inputs.dskp import (  # noqa: F401
    DSKP_FILES,
    main,
    parse_dskp_txt,
    parse_page_range,
    parse_pdf_pages,
    resolve_selection,
)

if __name__ == "__main__":
    main()
