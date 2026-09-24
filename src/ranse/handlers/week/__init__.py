"""Week/date resolution: date → week number/series → timetable path.

Business rules (holiday weeks, missing week numbers, dates outside the
calendar) live here in the handler layer, never in core (docs/DESIGN.md
decision 6). Error reporting keeps the handler style: print to stderr +
exit (decision 13).
"""

import os
import sys
from datetime import datetime, timedelta

from ...core.refs import _resolve_path
from ...inputs.calendar import load_calendar_config
from ...inputs.timetable import load_period_times, load_schedule
from ...inputs.yaml import input_bases
from ...model import Week
from ..base import Context


def _sunday_of(dt):
    """Return the Sunday of the week containing dt (school weeks start Sunday)."""
    return dt - timedelta(days=(dt.weekday() + 1) % 7)


def resolve_week(calendar_cfg, start_date, override=None):
    """Resolve start_date → Week(number, series) (or None if no config).

    Each record takes effect from its `start` date (a Sunday) until the next
    record. Holiday weeks (`holiday`) and records without a `week` number are
    hard errors — a wrong week would silently fill the wrong DSKP content.
    """
    if calendar_cfg is None:
        if override is None:
            return None
        return Week(number=int(override), series=None)

    def _as_date(value):
        return value.date() if isinstance(value, datetime) else value

    records = sorted(
        (e for e in calendar_cfg.get("weeks") or []
         if isinstance(e, dict) and e.get("start")),
        key=lambda e: _as_date(e["start"]))

    if not records:
        print("Error: the calendar config contains no dated 'weeks' records",
              file=sys.stderr)
        sys.exit(1)

    d = start_date.date()
    chosen = None
    for rec in records:
        if _as_date(rec["start"]) <= d:
            chosen = rec
        else:
            break

    if chosen is None:
        print(f"Error: {d} is earlier than the first record in the "
              f"calendar config ({_as_date(records[0]['start'])})",
              file=sys.stderr)
        sys.exit(1)

    if chosen.get("holiday"):
        print(f"Error: {d} falls in a holiday week: {chosen['holiday']} "
              f"(check --date)", file=sys.stderr)
        sys.exit(1)

    number = override if override is not None else chosen.get("week")
    if number is None:
        print(f"Error: calendar record starting {_as_date(chosen['start'])} "
              f"has no 'week' number", file=sys.stderr)
        sys.exit(1)
    number = int(number)

    series = chosen.get("series")
    if series is None:
        series_by_week = calendar_cfg.get("week_series") or {}
        series = series_by_week.get(number, series_by_week.get(str(number)))

    return Week(number=number, series=series)


def series_to_timetable(calendar_cfg, series):
    """series number → timetable file path (registered under 'timetable:')."""
    timetable_map = calendar_cfg.get("timetable") or {}
    path = timetable_map.get(series, timetable_map.get(str(series)))
    if not path:
        print(f"Error: series {series} has no file registered under "
              f"'timetable:' in the calendar config", file=sys.stderr)
        sys.exit(1)
    # Paths inside the calendar file resolve next to the file first.
    return _resolve_path(
        path, input_bases(first=calendar_cfg.get("_config_dir")))


class WeekResolver:
    """Phase-one resolver: date → week number/series → timetable path.

    Reads the profile's ``inputs:`` (the school-week calendar, optional
    timetable / csv override) plus the runtime ``--date`` / ``--week``
    overrides, and fills ``ctx.start_date``, ``ctx.week`` and
    ``ctx.schedule`` — it never writes a cell.
    """

    name = "week"
    phase = "resolve"
    # The `ranse fill` options this handler needs; the orchestrator adds them
    # to the parser and hands the values back in `ctx.runtime[key]`.
    cli_options = {
        "date": ("--date", {
            "help": "Week start date YYYY-MM-DD "
                    "(default: the Sunday of the current week)",
        }),
        "week": ("--week", {
            "type": int,
            "help": "Override the week number "
                    "(default: resolved from --date)",
        }),
    }

    @staticmethod
    def validate(params):
        """The week handler has no params of its own (inputs live in profile)."""

    def resolve(self, ctx: Context) -> None:
        runtime = ctx.runtime
        inputs = ctx.profile.inputs
        bases = input_bases(ctx.profile)

        # --- Resolve the week date (weeks start on Sunday) ---
        if runtime.get("date"):
            try:
                raw_date = datetime.strptime(runtime["date"], "%Y-%m-%d")
            except ValueError:
                print(f"Error: invalid --date {runtime['date']!r} "
                      f"(expected YYYY-MM-DD)", file=sys.stderr)
                sys.exit(1)
        else:
            raw_date = datetime.now()
        ctx.start_date = _sunday_of(raw_date).replace(
            hour=0, minute=0, second=0, microsecond=0)

        # --- Week number / series from the calendar file ---
        calendar_cfg = None
        calendar_path = None
        calendar_input = inputs.get("calendar")
        if calendar_input:
            calendar_path = _resolve_path(calendar_input, bases)
            if not os.path.isfile(calendar_path):
                print(f"Error: file not found: {calendar_path}",
                      file=sys.stderr)
                sys.exit(1)
            calendar_cfg = load_calendar_config(calendar_path)
        ctx.week = resolve_week(calendar_cfg, ctx.start_date,
                                runtime.get("week"))
        if ctx.week is not None:
            # Publish the number for the framework's {week} placeholder —
            # this is where the domain field name stops being visible.
            ctx.template_vars["week"] = ctx.week.number

        # --- Timetable source: an explicit input wins, else the week's series ---
        timetable_input = inputs.get("timetable")
        csv_input = inputs.get("csv")
        if timetable_input:
            tt_path = _resolve_path(timetable_input, bases)
        elif csv_input:
            tt_path = _resolve_path(csv_input, bases)
        elif ctx.week is not None and ctx.week.series is not None:
            tt_path = series_to_timetable(calendar_cfg, ctx.week.series)
        else:
            tt_path = None

        if (calendar_cfg is not None and not tt_path
                and ctx.week is not None and ctx.week.series is None):
            print(f"Error: week {ctx.week.number} has no series configured "
                  f"yet (fill in week_series in "
                  f"{calendar_path}, or set inputs.timetable / inputs.csv "
                  f"in the profile)", file=sys.stderr)
            sys.exit(1)

        if tt_path and not os.path.isfile(tt_path):
            print(f"Error: file not found: {tt_path}", file=sys.stderr)
            sys.exit(1)

        # Read the timetable here: a resolver may read inputs, the
        # orchestrator only opens the workbook and runs the fillers.
        if tt_path:
            # Optional profile-referenced period table (risk 4); absent
            # means the reader's built-in table.
            period_times = None
            pt_input = inputs.get("period_times")
            if pt_input:
                pt_path = _resolve_path(pt_input, bases)
                if not os.path.isfile(pt_path):
                    print(f"Error: file not found: {pt_path}",
                          file=sys.stderr)
                    sys.exit(1)
                period_times = load_period_times(pt_path)
            ctx.schedule = load_schedule(tt_path, period_times=period_times)
        if ctx.week is not None:
            series_txt = (ctx.week.series
                          if ctx.week.series is not None else "-")
            print(f"Week {ctx.week.number}, series {series_txt}"
                  + (f" ({tt_path})" if tt_path else ""))
