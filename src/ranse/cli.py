"""Command-line orchestration: load → resolve → read → fill → save.

Only orchestration lives here: argparse, the pipeline order and turning a
RanseError into `Error: …` + exit code 1 (decision 13). Handlers keep their
own print-to-stderr warnings.
"""

import argparse
import os
import sys

from .core.xlsx import Workbook, _read_shared_strings, _read_zip
from .errors import RanseError
from .handlers.base import Context
from .handlers.dskp import (DskpFiller, build_auto_dskp_entries,
                            schedule_has_auto_match)
from .handlers.fixed_cells import FixedCellsFiller
from .handlers.menu import MenuFiller
from .handlers.week import WeekResolver
from .inputs.timetable import (DAY_ORDER, build_schedule, read_csv,
                               read_timetable_xlsx)
from .inputs.yaml import load_config

REQUIRED_SHEETS = ["MENU"] + [d.upper() for d in DAY_ORDER]


def main():
    parser = argparse.ArgumentParser(
        description="Fill an e-RPH xlsx template with timetable and/or DSKP data")
    parser.add_argument("--xlsx", required=True,
                        help="Path to the target xlsx file")
    parser.add_argument("--timetable-xlsx", default=None,
                        help="Path to the timetable xlsx file")
    parser.add_argument("--csv", default=None,
                        help="Path to the timetable CSV (alternative to --timetable-xlsx)")
    parser.add_argument("--config", default="./erph-config.yaml",
                        help="Path to the config YAML (default: ./erph-config.yaml)")
    parser.add_argument("--jadual-config", default=None,
                        help="Path to jadual-minggu.yaml (minggu → siri → timetable); "
                             "enables week-aware automatic filling")
    parser.add_argument("--minggu", type=int, default=None,
                        help="Override the week number (default: resolved from --date)")
    parser.add_argument("--no-dskp-auto", action="store_true",
                        help="Disable automatic DSKP content-standard filling")
    parser.add_argument("--date",
                        help="Week start date YYYY-MM-DD "
                             "(default: the Sunday of the current week)")
    args = parser.parse_args()

    try:
        _run(parser, args)
    except RanseError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _run(parser, args):
    if not os.path.isfile(args.xlsx):
        print(f"Error: file not found: {args.xlsx}", file=sys.stderr)
        sys.exit(1)

    # --- Profile / config (stage 3 replaces this with the profile schema) ---
    cfg = load_config(args.config)

    # --- Target workbook ---
    wb = Workbook.open(args.xlsx)
    missing = [s for s in REQUIRED_SHEETS if s not in wb.sheets]
    if missing:
        print(f"Error: missing sheets: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    ctx = Context(
        workbook=wb,
        profile=cfg,
        params={
            "date": args.date,
            "minggu": args.minggu,
            "jadual_config": args.jadual_config,
            "timetable_xlsx": args.timetable_xlsx,
            "csv": args.csv,
            "no_dskp_auto": args.no_dskp_auto,
        },
    )

    # --- Phase one: resolve inputs (no cell writes) ---
    WeekResolver().resolve(ctx)

    tt_path = ctx.params["timetable_path"]
    tt_is_csv = ctx.params["timetable_is_csv"]

    if not tt_path and not cfg.get("dskp"):
        parser.error("Nothing to do: provide --timetable-xlsx, --csv or "
                     "--jadual-config, or add dskp entries to the config")

    # --- Read the timetable (inputs layer; the target workbook stays write-only) ---
    schedule = {}
    if tt_path and tt_is_csv:
        schedule = build_schedule(read_csv(tt_path))
    elif tt_path:
        tt_zip = _read_zip(tt_path)
        shared_strings = _read_shared_strings(tt_zip)
        schedule = read_timetable_xlsx(tt_zip, shared_strings)
    ctx.schedule = schedule

    if ctx.week is not None:
        siri_txt = ctx.week["siri"] if ctx.week.get("siri") is not None else "-"
        print(f"Week: minggu {ctx.week['minggu']}, siri {siri_txt}"
              + (f" ({tt_path})" if tt_path else ""))

    # --- Automatic DSKP entries: two parent sections per BC lesson ---
    # Static entries come first, auto entries are appended after them so
    # they win on the same cell (PLAN.md risk 9).
    auto_report = []
    if schedule and ctx.week is not None and not args.no_dskp_auto:
        auto_entries, auto_report = build_auto_dskp_entries(
            schedule, ctx.week["minggu"], cfg)
        cfg["dskp"] = cfg.get("dskp", []) + auto_entries
        for line in auto_report:
            print(line)
    elif schedule and ctx.week is None and not args.no_dskp_auto:
        # Without a week number there is no section pair to pick — say so
        # instead of silently writing nothing.
        if schedule_has_auto_match(schedule, cfg):
            print("Note: automatic DSKP filling skipped (no week known) — "
                  "add --jadual-config or --minggu N to enable it")

    # --- Phase two: fillers (the only code allowed to touch cells) ---
    for filler in (MenuFiller(), FixedCellsFiller(), DskpFiller()):
        ctx.report.extend(filler.fill(ctx))
    for line in ctx.report:
        print(line)

    wb.save()
    print(f"Done: {args.xlsx}")
