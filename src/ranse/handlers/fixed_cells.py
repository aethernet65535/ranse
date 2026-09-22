"""Fixed cell values from the config (stage 1 move)."""

from ..core.refs import _cell_range_top_left, _cell_ref, _parse_cell_ref
from ..core.xlsx import _find_merge_top_left, _get_merge_ranges, write_cell


def write_fixed_cells(root, fixed_entries):
    merges = _get_merge_ranges(root)
    for _, cell_range, value in fixed_entries:
        top_left = _cell_range_top_left(cell_range)
        row, col = _parse_cell_ref(top_left)
        row, col = _find_merge_top_left(merges, row, col)
        try:
            value = int(value)
        except (ValueError, TypeError):
            pass
        write_cell(root, _cell_ref(row, col), value)
