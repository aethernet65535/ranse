"""Week/date resolution: date → minggu/siri → timetable path (stage 1 move)."""

import os
import sys
from datetime import datetime, timedelta

from .. import _REPO_ROOT
from ..core.refs import _resolve_path


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
