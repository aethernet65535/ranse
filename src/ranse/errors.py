"""Error hierarchy: core failures raise from here (PLAN.md decision 13).

The CLI catches ``RanseError`` and turns it into ``Error: <msg>`` on stderr
plus exit code 1. Handlers and inputs keep their existing
``print(..., file=sys.stderr)`` style — no logging framework (scope item).
"""


class RanseError(Exception):
    """Base class for all ranse errors."""


class ProfileError(RanseError):
    """Invalid or unknown profile configuration."""


class WeekError(RanseError):
    """Week/calendar resolution failure."""


class SheetError(RanseError):
    """Invalid workbook/sheet/cell reference or sheet XML."""
