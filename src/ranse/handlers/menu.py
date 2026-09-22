"""MENU sheet filling: layout rows, time suffixes, merged periods."""

from ..core.refs import _cell_ref, _date_to_excel
from ..inputs.timetable import DAY_ORDER
from ..model import merge_periods
from .base import Context

# --- MENU layout (decision 12: layout constants stay in the handler) ------
NUM_PERIODS = 8

_TIME_SUFFIX_CACHE = {}
for _h in range(24):
    _t = f"{_h:02d}:00"
    if _h < 11:
        _TIME_SUFFIX_CACHE[_t] = f"{_t} PAGI"
    elif _h < 14:
        _TIME_SUFFIX_CACHE[_t] = f"{_t} TGH"
    else:
        _TIME_SUFFIX_CACHE[_t] = f"{_t} TPTG"


def _time_with_suffix(t):
    hour = int(t.split(":")[0])
    key = f"{hour:02d}:{t.split(':')[1]}"
    return _TIME_SUFFIX_CACHE.get(key, f"{t} PAGI")


class MenuFiller:
    """Fill the MENU sheet with this week's merged lessons."""

    name = "menu"
    phase = "fill"

    @staticmethod
    def validate(params):
        """The MENU layout is fixed (decision 12): no params to validate."""

    def fill(self, ctx: Context) -> list:
        schedule = ctx.schedule
        if not schedule:
            # Without a timetable there is nothing to write into MENU —
            # and the sheet must stay untouched (not even re-serialized).
            return []

        subject_map = ctx.profile.context.get("subjects", {})
        sheet = ctx.workbook.sheet("MENU")

        for day_idx, day_name in enumerate(DAY_ORDER):
            merged = merge_periods(schedule.day(day_name))

            header_row = 5 + day_idx * 10

            if day_idx == 0:
                date_serial = _date_to_excel(ctx.start_date)
                sheet.write(_cell_ref(header_row + 1, 9), date_serial)

            for i in range(NUM_PERIODS):
                row = header_row + 1 + i
                entry = merged[i][1] if i < len(merged) else None

                if entry:
                    cells = [
                        (3, entry.cls),
                        (4, _time_with_suffix(entry.start)),
                        (5, _time_with_suffix(entry.end)),
                        (6, subject_map.get(entry.subject, entry.subject)),
                        (7, int(entry.tingkatan)),
                    ]
                    for col, val in cells:
                        sheet.write(_cell_ref(row, col), val)
                else:
                    # Empty rows are written as "" — that CLEARS the results
                    # of a previous run (PLAN.md risk 7). Keep this branch.
                    for col in range(3, 8):
                        sheet.write(_cell_ref(row, col), "")

        return []
