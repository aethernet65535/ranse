"""Domain model: lessons, schedules, weeks and the loaded profile.

Deliberately *outside* core (DESIGN.md §2): these types carry timetable / e-RPH
semantics (day names, tingkatan, handler names) that the write-only workbook
engine must not know about. ``inputs`` produce them, ``handlers`` consume them.
"""

from dataclasses import dataclass, field, replace
from typing import Dict, Iterator, List, Optional, Tuple


@dataclass(frozen=True)
class Lesson:
    """One timetable slot: a class studying one subject for one period.

    ``cls`` is the timetable's class label (``"1E"``, ``"5SPA"``, …). The
    field cannot be called ``class`` (Python keyword), which is the only
    difference from the dict form used before stage 3.
    """

    cls: str
    start: str
    end: str
    subject: str
    tingkatan: str


@dataclass
class Schedule:
    """A week of lessons: ``{day_name: {period_number: Lesson}}``.

    Day names are the Malay school days (``"Ahad"`` … ``"Khamis"``) — the
    template only has sheets for those, so Jumaat/Sabtu are dropped while
    reading (DESIGN.md risk 10).
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
    """Merge consecutive periods with the same class/subject/tingkatan.

    Returns ``[(first_period, lesson_with_merged_end), …]`` in period order.
    A gap in time ends a run even when the lesson repeats (DESIGN.md risk 4).
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
                and entry.tingkatan == buf_entry.tingkatan
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
    """A resolved school week: ``minggu`` number + optional ``siri``."""

    minggu: int
    siri: Optional[int] = None


@dataclass(frozen=True)
class HandlerSpec:
    """One entry of the profile's explicit ``handlers:`` list."""

    name: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ProfileInputs:
    """Profile ``inputs:`` — where the files live (decision 10/11).

    ``template`` may contain ``{minggu}`` (resolved once the week is known)
    and/or glob wildcards, so one profile can serve the whole year:
    ``"…/2026/*/M{minggu}.xlsx"``. ``templates`` maps a minggu number to an
    explicit workbook and wins over the pattern (escape hatch for weeks whose
    file is named or placed differently).
    """

    template: str
    jadual: Optional[str] = None
    timetable: Optional[str] = None
    csv: Optional[str] = None
    templates: Dict[str, str] = field(default_factory=dict)


@dataclass
class Profile:
    """A loaded profile file (DESIGN.md §3: explicit handler list)."""

    name: str
    inputs: ProfileInputs
    context: dict = field(default_factory=dict)
    handlers: List[HandlerSpec] = field(default_factory=list)
    base_dir: str = ""
