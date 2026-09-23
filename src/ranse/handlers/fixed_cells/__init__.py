"""Fixed cell values from the profile's ``handlers[].params.cells``."""

import sys
from typing import List

from ...errors import ProfileError
from ..base import Context


class FixedCellsFiller:
    """Write the configured constant cells, e.g. the school name.

    Profile form::

        - name: fixed_cells
          params:
            cells:
              - [MENU, "B3:C3", "ALI BIN ABU"]
    """

    name = "fixed_cells"
    phase = "fill"

    @staticmethod
    def validate(params):
        cells = params.get("cells", [])
        if not isinstance(cells, list):
            raise ProfileError("fixed_cells handler: 'cells' must be a list")
        for i, cell in enumerate(cells, start=1):
            if not isinstance(cell, (list, tuple)) or len(cell) != 3:
                raise ProfileError(
                    f"fixed_cells handler: cells[{i}] must be "
                    f"[sheet, range, value]")
            sheet_name, cell_range, value = cell
            if not isinstance(sheet_name, str) or not isinstance(cell_range,
                                                                 str):
                raise ProfileError(
                    f"fixed_cells handler: cells[{i}] sheet/range must be "
                    f"strings")
            if not isinstance(value, (str, int, float)):
                raise ProfileError(
                    f"fixed_cells handler: cells[{i}] value must be a "
                    f"string or a number")

    def fill(self, ctx: Context) -> List[str]:
        report: List[str] = []
        for sheet_name, cell_range, value in ctx.params.get("cells", []):
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
