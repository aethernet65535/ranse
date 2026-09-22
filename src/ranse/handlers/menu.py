"""MENU sheet filling: layout rows, time suffixes, merged periods (stage 1 move)."""

from ..core.refs import _cell_ref, _date_to_excel
from ..core.xlsx import (_find_merge_top_left, _get_merge_ranges,
                         write_cell)
from ..inputs.timetable import (DAY_ORDER, NUM_PERIODS, _time_with_suffix,
                                merge_periods)


def fill_menu(root, schedule, subject_map, start_date):
    """Fill the MENU sheet tree with schedule data (mutates root)."""
    merges = _get_merge_ranges(root)

    for day_idx, day_name in enumerate(DAY_ORDER):
        day_schedule = schedule.get(day_name, {})
        merged = merge_periods(day_schedule)

        header_row = 5 + day_idx * 10

        if day_idx == 0:
            date_serial = _date_to_excel(start_date)
            r, c = _find_merge_top_left(merges, header_row + 1, 9)
            write_cell(root, _cell_ref(r, c), date_serial)

        for i in range(NUM_PERIODS):
            row = header_row + 1 + i
            entry = merged[i][1] if i < len(merged) else None

            if entry:
                cells = [
                    (3, entry["class"]),
                    (4, _time_with_suffix(entry["start"])),
                    (5, _time_with_suffix(entry["end"])),
                    (6, subject_map.get(entry["subject"], entry["subject"])),
                    (7, int(entry["tingkatan"])),
                ]
                for col, val in cells:
                    wr, wc = _find_merge_top_left(merges, row, col)
                    write_cell(root, _cell_ref(wr, wc), val)
            else:
                for col in range(3, 8):
                    wr, wc = _find_merge_top_left(merges, row, col)
                    write_cell(root, _cell_ref(wr, wc), "")
