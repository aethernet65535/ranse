"""Handler protocols + shared context (PLAN.md §3).

Business logic lives behind these two protocols, which is what keeps it out
of core (decision 6): a Filler can only touch cells through ``ctx.workbook``.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Protocol

from ..core.xlsx import Workbook


@dataclass
class Context:
    """Everything handlers may touch.

    ``workbook``   the target workbook (write-only core API);
    ``profile``    the loaded config/profile (plain dict until stage 3);
    ``schedule``   timetable lessons, read between resolve and fill;
    ``week``       ``{'minggu': N, 'siri': S or None}`` once resolved;
    ``start_date`` week start (Sunday) the MENU date column is filled from;
    ``params``     runtime overrides from the CLI (``--date``, ``--minggu``,
                   ``--jadual-config``, ``--timetable-xlsx``, ``--csv``,
                   ``--no-dskp-auto``) plus resolver outputs (timetable path);
    ``report``     lines printed by the orchestrator after filling.
    """
    workbook: Workbook
    profile: dict
    schedule: Optional[dict] = None
    week: Optional[dict] = None
    start_date: Optional[date] = None
    params: dict = field(default_factory=dict)
    report: list = field(default_factory=list)


class Resolver(Protocol):
    """Phase one: compute inputs, never write a cell."""
    name: str

    def resolve(self, ctx: Context) -> None: ...


class Filler(Protocol):
    """Phase two: write cells, only through the core write API."""
    name: str

    def fill(self, ctx: Context) -> list: ...
