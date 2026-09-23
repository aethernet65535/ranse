"""Handler protocols + shared context (docs/DESIGN.md S3).

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
    ``schedule``   the input a resolver read for the fillers (or None);
    ``week``       resolved ``Week`` (or None when no calendar is used);
    ``start_date`` the week start a resolver resolved (or None);
    ``params``     params of the handler currently running (set per handler
                   by the orchestrator);
    ``runtime``    values of the CLI options the handlers declared, keyed by
                   each handler's own ``cli_options`` names;
    ``report``     lines printed by the orchestrator after filling.

    A handler may also declare class attributes:

    ``cli_options``      the ``ranse fill`` options it needs (docs/DESIGN.md
                         S3.4);
    ``required_sheets``  workbook sheets that must exist before any fill;
    ``needs_schedule``   True when it cannot work without ``schedule``.
    """
    profile: Profile
    workbook: Optional[Workbook] = None
    schedule: Optional[Schedule] = None
    week: Optional[Week] = None
    start_date: Optional[date] = None
    params: dict = field(default_factory=dict)
    runtime: dict = field(default_factory=dict)
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
