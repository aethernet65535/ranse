"""Week/date resolution: date → minggu/siri → timetable path.

Business rules (cuti weeks, missing minggu, dates outside the calendar) live
here in the handler layer, never in core (docs/DESIGN.md decision 6). Error
reporting keeps the handler style: print to stderr + exit (decision 13).
"""

import os
import sys
from datetime import datetime, timedelta

from ... import _REPO_ROOT
from ...core.refs import _resolve_path
from ...inputs.timetable import load_schedule
from ...inputs.yaml import load_jadual_config
from ...model import Week
from ..base import Context


def _sunday_of(dt):
    """Return the Sunday of the week containing dt (school weeks start Ahad)."""
    return dt - timedelta(days=(dt.weekday() + 1) % 7)


def resolve_week(jadual_cfg, start_date, override=None):
    """Resolve start_date → Week(minggu, siri) (or None if no config).

    Each record takes effect from its `start` date (a Sunday) until the next
    record. Holiday weeks (`cuti`) and records without a minggu number are
    hard errors — a wrong week would silently fill the wrong DSKP content.
    """
    if jadual_cfg is None:
        if override is None:
            return None
        return Week(minggu=int(override), siri=None)

    def _as_date(value):
        return value.date() if isinstance(value, datetime) else value

    records = sorted(
        (e for e in jadual_cfg.get("minggu") or []
         if isinstance(e, dict) and e.get("start")),
        key=lambda e: _as_date(e["start"]))

    if not records:
        print("Error: jadual config contains no dated minggu records",
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
              f"jadual config ({_as_date(records[0]['start'])})",
              file=sys.stderr)
        sys.exit(1)

    if chosen.get("cuti"):
        print(f"Error: {d} falls in a holiday week: {chosen['cuti']} "
              f"(check --date)", file=sys.stderr)
        sys.exit(1)

    minggu = override if override is not None else chosen.get("minggu")
    if minggu is None:
        print(f"Error: jadual record starting {_as_date(chosen['start'])} "
              f"has no 'minggu' number", file=sys.stderr)
        sys.exit(1)
    minggu = int(minggu)

    siri = chosen.get("siri")
    if siri is None:
        per_minggu = jadual_cfg.get("jadual_siri") or {}
        siri = per_minggu.get(minggu, per_minggu.get(str(minggu)))

    return Week(minggu=minggu, siri=siri)


def siri_to_timetable(jadual_cfg, siri):
    """siri number → timetable file path (registered under 'jadual:')."""
    jadual_map = jadual_cfg.get("jadual") or {}
    path = jadual_map.get(siri, jadual_map.get(str(siri)))
    if not path:
        print(f"Error: siri {siri} has no file registered under 'jadual:' "
              f"in the jadual config", file=sys.stderr)
        sys.exit(1)
    return _resolve_path(path, [jadual_cfg.get("_config_dir", _REPO_ROOT),
                                _REPO_ROOT, os.getcwd()])


class WeekResolver:
    """Phase-one resolver: date → minggu/siri → timetable path.

    Reads the profile's ``inputs:`` (jadual calendar, optional timetable /
    csv override) plus the runtime ``--date`` / ``--minggu`` overrides, and
    fills ``ctx.start_date``, ``ctx.week`` and ``ctx.schedule`` — it never
    writes a cell.
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
        "minggu": ("--minggu", {
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
        bases = [ctx.profile.base_dir, os.getcwd(), _REPO_ROOT]

        # --- Resolve the week date (weeks start on Sunday/Ahad) ---
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

        # --- Week number / siri from jadual-minggu.yaml ---
        jadual_cfg = None
        jadual_path = None
        if inputs.jadual:
            jadual_path = _resolve_path(inputs.jadual, bases)
            if not os.path.isfile(jadual_path):
                print(f"Error: file not found: {jadual_path}",
                      file=sys.stderr)
                sys.exit(1)
            jadual_cfg = load_jadual_config(jadual_path)
        ctx.week = resolve_week(jadual_cfg, ctx.start_date,
                                runtime.get("minggu"))

        # --- Timetable source: an explicit input wins, else siri from the week ---
        if inputs.timetable:
            tt_path = _resolve_path(inputs.timetable, bases)
        elif inputs.csv:
            tt_path = _resolve_path(inputs.csv, bases)
        elif ctx.week is not None and ctx.week.siri is not None:
            tt_path = siri_to_timetable(jadual_cfg, ctx.week.siri)
        else:
            tt_path = None

        if (jadual_cfg is not None and not tt_path
                and ctx.week is not None and ctx.week.siri is None):
            print(f"Error: minggu {ctx.week.minggu} has no siri "
                  f"configured yet (fill in jadual_siri in "
                  f"{jadual_path}, or set inputs.timetable / inputs.csv "
                  f"in the profile)", file=sys.stderr)
            sys.exit(1)

        if tt_path and not os.path.isfile(tt_path):
            print(f"Error: file not found: {tt_path}", file=sys.stderr)
            sys.exit(1)

        # Read the timetable here: a resolver may read inputs, the
        # orchestrator only opens the workbook and runs the fillers.
        if tt_path:
            ctx.schedule = load_schedule(tt_path)
        if ctx.week is not None:
            siri_txt = ctx.week.siri if ctx.week.siri is not None else "-"
            print(f"Week: minggu {ctx.week.minggu}, siri {siri_txt}"
                  + (f" ({tt_path})" if tt_path else ""))
