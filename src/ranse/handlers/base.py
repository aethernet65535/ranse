"""Handler protocols + shared context (docs/DESIGN.md §3).

Business logic lives behind these two protocols, which is what keeps it out
of core (decision 6): a Filler can only touch cells through ``ctx.workbook``.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Protocol

from ..core.xlsx import Workbook
from ..model import Profile, Schedule, Week


@dataclass
class Context:
    """Everything handlers may touch.

    ``profile``    the loaded profile (``inputs`` / ``context`` / handlers);
    ``workbook``   the target workbook (write-only core API). It stays None
                   during the resolve phase — the orchestrator opens it once
                   the week (and therefore the template file) is known;
    ``schedule``   timetable lessons, read between resolve and fill;
    ``week``       resolved ``Week`` (or None when no calendar is used);
    ``start_date`` week start (Sunday) the MENU date column is filled from;
    ``params``     params of the handler currently running (set per handler
                   by the orchestrator);
    ``runtime``    CLI overrides: ``--date`` / ``--minggu`` /
                   ``--no-dskp-auto``;
    ``timetable_path`` / ``timetable_is_csv``  resolver output, consumed by
                   the orchestrator to read the timetable;
    ``report``     lines printed by the orchestrator after filling.
    """
    profile: Profile
    workbook: Optional[Workbook] = None
    schedule: Optional[Schedule] = None
    week: Optional[Week] = None
    start_date: Optional[date] = None
    params: dict = field(default_factory=dict)
    runtime: dict = field(default_factory=dict)
    timetable_path: Optional[str] = None
    timetable_is_csv: bool = False
    report: list = field(default_factory=list)


class Resolver(Protocol):
    """Phase one: compute inputs, never write a cell (``phase = "resolve"``)."""
    name: str
    phase: str

    def resolve(self, ctx: Context) -> None: ...


class Filler(Protocol):
    """Phase two: write cells through core (``phase = "fill"``)."""
    name: str
    phase: str

    def fill(self, ctx: Context) -> list: ...
