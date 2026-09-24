"""Domain model: lessons, schedules, weeks and the loaded profile.

Deliberately *outside* core (docs/DESIGN.md S2): these types carry timetable / e-RPH
semantics (day names, form levels, handler names) that the write-only workbook
engine must not know about. ``inputs`` produce them, ``handlers`` consume them.
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

    Day names are the school-day labels the source carries (a reader
    keeps every one of them); which days a template actually has is
    declared once by the profile (``context.days``) and used by the
    fillers (risk 10, src/ranse/inputs/timetable/DESIGN.md).
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
    (risk 4, src/ranse/inputs/timetable/DESIGN.md).
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


@dataclass(frozen=True)
class HandlerSpec:
    """One entry of the profile's explicit ``handlers:`` list."""

    name: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ProfileInputs:
    """Profile ``inputs:`` — where the files live (decision 10/11).

    The framework itself only knows two keys:

    ``template``   the workbook to fill; may contain ``{week}`` and/or glob
                   wildcards, so one profile can serve the whole year:
                   ``"…/2026/*/M{week}.xlsx"``;
    ``templates``  maps a week number to an explicit workbook and wins over
                   the pattern (escape hatch for weeks whose file is named
                   or placed differently).

    **Every other key is handler-specific**: it passes through verbatim into
    ``extra`` and is interpreted by the handler/reader that declares it —
    the same contract as handler ``params`` (docs/DESIGN.md S3.3: "every
    other key is handler-specific"). Use :meth:`get` to read one.
    """

    template: str
    templates: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, object] = field(default_factory=dict)

    def get(self, key, default=None):
        """One ``inputs:`` value by key — framework keys included.

        ``inputs.get("jadual")`` is what a handler whose profile key is
        ``jadual`` calls; ``template``/``templates`` resolve to the
        framework's own fields.
        """
        if key == "template":
            return self.template
        if key == "templates":
            return self.templates
        return self.extra.get(key, default)


@dataclass
class Profile:
    """A loaded profile file (docs/DESIGN.md S3: explicit handler list)."""

    name: str
    inputs: ProfileInputs
    context: dict = field(default_factory=dict)
    handlers: List[HandlerSpec] = field(default_factory=list)
    base_dir: str = ""
