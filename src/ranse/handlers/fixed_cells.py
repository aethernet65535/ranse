"""Fixed cell values from the config (stage 2: Filler form)."""

import sys
from typing import List

from .base import Context


class FixedCellsFiller:
    """Write the configured constant cells, e.g. the school name."""

    name = "fixed_cells"

    def fill(self, ctx: Context) -> List[str]:
        report: List[str] = []
        for sheet_name, cell_range, value in ctx.profile.get("fixed_cells", []):
            if sheet_name not in ctx.workbook.sheets:
                print(f"  Warning: sheet '{sheet_name}' not found, skipping",
                      file=sys.stderr)
                continue
            try:
                value = int(value)
            except (ValueError, TypeError):
                pass
            ctx.workbook.sheet(sheet_name).write(cell_range, value)
        return report
