"""The e-RPH domain model: lessons, schedules, weeks and the day mirrors.

These types carry business semantics, which is why they live with the
business and not in the framework (docs/DESIGN.md S2): the framework knows
only profiles, handlers and the write-only workbook API. ``inputs`` produce
them, ``handlers`` consume them.

The two mirror tables at the bottom are the **only** places this plugin
stores the frozen Malay tokens of the source artifacts: the timetable's own
column headers, and the workbook's day-sheet names. Everything downstream of
a reader speaks the canonical English day names, so the artifact spellings
never travel; docs/DESIGN.md S9 keeps the exemption list honest.
"""

from dataclasses import dataclass, field, replace
from typing import Dict, Iterator, List, Optional, Tuple


@dataclass(frozen=True)
class Lesson:
    """One timetable slot: a class studying one subject for one period.

    ``cls`` is the timetable's class label (``"1E"``, ``"5SPA"``, …). The
    field cannot be called ``class`` (a Python keyword).
    """

    cls: str
    start: str
    end: str
    subject: str
    form: str


@dataclass
class Schedule:
    """A week of lessons: ``{day_name: {period_number: Lesson}}``.

    Day names are the canonical English labels this plugin speaks; a reader
    keeps every one of them, however many the source carries. Which days a
    template actually has is declared once by the profile
    (``context.days``) and used by the fillers (risk 10,
    ``inputs/timetable/DESIGN.md``).
    """

    days: Dict[str, Dict[int, Lesson]] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.days)

    def day(self, name: str) -> Dict[int, Lesson]:
        """Lessons of one day as ``{period: Lesson}`` (empty when free)."""
        return self.days.get(name) or {}

    def lessons(self) -> Iterator[Lesson]:
        for periods in self.days.values():
            for lesson in periods.values():
                yield lesson


def merge_periods(day_schedule: Dict[int, Lesson]) -> List[Tuple[int, Lesson]]:
    """Merge consecutive periods with the same class/subject/form.

    Returns ``[(first_period, lesson_with_merged_end), …]`` in period order.
    A gap in time ends a run even when the lesson repeats
    (risk 4, ``inputs/timetable/DESIGN.md``).
    """
    periods = sorted(day_schedule.keys())
    if not periods:
        return []

    merged: List[Tuple[int, Lesson]] = []
    buf_start = periods[0]
    buf_entry = day_schedule[periods[0]]

    for p in periods[1:]:
        entry = day_schedule[p]
        same = (entry.cls == buf_entry.cls
                and entry.subject == buf_entry.subject
                and entry.form == buf_entry.form
                and entry.start == buf_entry.end)
        if same:
            buf_entry = replace(buf_entry, end=entry.end)
        else:
            merged.append((buf_start, buf_entry))
            buf_start = p
            buf_entry = entry

    merged.append((buf_start, buf_entry))
    return merged


@dataclass(frozen=True)
class Week:
    """A resolved school week: ``number`` + optional ``series``."""

    number: int
    series: Optional[int] = None


# ---------------------------------------------------------------------------
# Day-name mirrors (the frozen artifact spellings)
# ---------------------------------------------------------------------------

# Source timetable headers → the canonical day names ``Schedule`` carries.
# The shipped timetables spell their columns in Malay and those tokens are
# frozen artifact: they must keep matching, so the translation happens here
# and nowhere else. Day names the reader recognises, Sunday first.
DAY_HEADERS = {
    "Ahad": "Sunday",
    "Isnin": "Monday",
    "Selasa": "Tuesday",
    "Rabu": "Wednesday",
    "Khamis": "Thursday",
    "Jumaat": "Friday",
    "Sabtu": "Saturday",
}

# Weekday index (Monday-first, datetime.weekday()) → canonical day name; the
# school week starts on Sunday.
DAY_BY_WEEKDAY = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                  "Saturday", "Sunday"]

# The day blocks the shipped template has, in order. A profile declares the
# same list once as ``context.days`` (a value shared by two handlers belongs
# in the profile); this tuple is the fallback for profiles that do not.
DEFAULT_DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday")

# Canonical day name → the shipped template's actual day-sheet name. Those
# sheet names are frozen artifact as well; writes go through this reverse
# mirror so English day names land on the right sheet.
SHEET_BY_DAY = {
    "Sunday": "AHAD",
    "Monday": "ISNIN",
    "Tuesday": "SELASA",
    "Wednesday": "RABU",
    "Thursday": "KHAMIS",
}
