"""Week/date resolution: date → minggu/siri → timetable path (stage 1 move)."""

import os
import sys
from datetime import datetime, timedelta

from .. import _REPO_ROOT
from ..core.refs import _resolve_path
from ..inputs.yaml import load_jadual_config
from .base import Context


def _sunday_of(dt):
    """Return the Sunday of the week containing dt (school weeks start Ahad)."""
    return dt - timedelta(days=(dt.weekday() + 1) % 7)


def resolve_week(jadual_cfg, start_date, override=None):
    """Resolve start_date → {'minggu': N, 'siri': S or None} (or None if no config).

    Each record takes effect from its `start` date (a Sunday) until the next
    record. Holiday weeks (`cuti`) and records without a minggu number are
    hard errors — a wrong week would silently fill the wrong DSKP content.
    """
    if jadual_cfg is None:
        if override is None:
            return None
        return {"minggu": int(override), "siri": None}

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

    return {"minggu": minggu, "siri": siri}


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
    """Phase-one resolver: date → minggu/siri → timetable path (stage 2).

    Reads only the runtime params (``--date``, ``--minggu``,
    ``--jadual-config``, ``--timetable-xlsx``, ``--csv``) and fills
    ``ctx.start_date``, ``ctx.week`` and the timetable path — it never
    writes a cell. Error reporting keeps the handler-layer style: print to
    stderr + exit (decision 13).
    """

    name = "week"

    def resolve(self, ctx: Context) -> None:
        params = ctx.params

        # --- Resolve the week date (weeks start on Sunday/Ahad) ---
        if params.get("date"):
            try:
                raw_date = datetime.strptime(params["date"], "%Y-%m-%d")
            except ValueError:
                print(f"Error: invalid --date {params['date']!r} "
                      f"(expected YYYY-MM-DD)", file=sys.stderr)
                sys.exit(1)
        else:
            raw_date = datetime.now()
        ctx.start_date = _sunday_of(raw_date).replace(
            hour=0, minute=0, second=0, microsecond=0)

        # --- Week number / siri from jadual-minggu.yaml ---
        jadual_cfg = None
        if params.get("jadual_config"):
            if not os.path.isfile(params["jadual_config"]):
                print(f"Error: file not found: {params['jadual_config']}",
                      file=sys.stderr)
                sys.exit(1)
            jadual_cfg = load_jadual_config(params["jadual_config"])
        ctx.week = resolve_week(jadual_cfg, ctx.start_date, params.get("minggu"))

        # --- Timetable source: explicit flag wins, else siri from the week ---
        if params.get("timetable_xlsx"):
            tt_path, tt_is_csv = params["timetable_xlsx"], False
        elif params.get("csv"):
            tt_path, tt_is_csv = params["csv"], True
        elif ctx.week is not None and ctx.week.get("siri") is not None:
            tt_path = siri_to_timetable(jadual_cfg, ctx.week["siri"])
            tt_is_csv = tt_path.lower().endswith(".csv")
        else:
            tt_path, tt_is_csv = None, False

        if (jadual_cfg is not None and not tt_path
                and ctx.week.get("siri") is None):
            print(f"Error: minggu {ctx.week['minggu']} has no siri "
                  f"configured yet (fill in jadual_siri in "
                  f"{params['jadual_config']}, or pass "
                  f"--timetable-xlsx/--csv)", file=sys.stderr)
            sys.exit(1)

        if tt_path and not os.path.isfile(tt_path):
            print(f"Error: file not found: {tt_path}", file=sys.stderr)
            sys.exit(1)

        ctx.params["timetable_path"] = tt_path
        ctx.params["timetable_is_csv"] = tt_is_csv
