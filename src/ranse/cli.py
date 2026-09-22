"""Command-line orchestration: load profile → resolve → read → fill → save.

Only orchestration lives here: argparse, the pipeline order, printing the
report and turning a RanseError into ``Error: …`` + exit code 1 (decision
13). Every business decision belongs to a handler, which is what keeps this
file free of timetable/DSKP knowledge.
"""

import argparse
import os
import sys

from . import _REPO_ROOT
from .core.refs import _resolve_path
from .core.xlsx import Workbook
from .errors import RanseError
from .handlers.base import Context
from .handlers.registry import build_handlers
from .inputs.timetable import DAY_ORDER, load_schedule
from .inputs.yaml import load_profile

REQUIRED_SHEETS = ["MENU"] + [d.upper() for d in DAY_ORDER]


def main():
    parser = argparse.ArgumentParser(
        description="Fill an e-RPH xlsx template from a ranse profile")
    parser.add_argument("--profile", required=True,
                        help="Path to the profile YAML (inputs + handlers)")
    parser.add_argument("--minggu", type=int, default=None,
                        help="Override the week number "
                             "(default: resolved from --date)")
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
    profile = load_profile(args.profile)
    bases = [profile.base_dir, os.getcwd(), _REPO_ROOT]
    template = _resolve_path(profile.inputs.template, bases)
    if not os.path.isfile(template):
        print(f"Error: file not found: {template}", file=sys.stderr)
        sys.exit(1)

    # Unknown handler names / invalid params fail here, before any cell is
    # touched (decision 2 + "params 由各 handler 自己校验").
    handlers = build_handlers(profile.handlers)

    wb = Workbook.open(template)
    missing = [s for s in REQUIRED_SHEETS if s not in wb.sheets]
    if missing:
        print(f"Error: missing sheets: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    ctx = Context(
        workbook=wb,
        profile=profile,
        runtime={
            "date": args.date,
            "minggu": args.minggu,
            "no_dskp_auto": args.no_dskp_auto,
        },
    )

    # --- Phase one: resolvers compute the inputs (no cell writes) ---
    for spec, handler in handlers:
        if handler.phase != "resolve":
            continue
        ctx.params = spec.params
        handler.resolve(ctx)

    if not ctx.timetable_path and not any(spec.name == "dskp"
                                          for spec, _ in handlers):
        parser.error("Nothing to do: set inputs.timetable / inputs.csv or "
                     "inputs.jadual in the profile, or add a dskp handler")

    # --- Read the timetable (inputs layer; target workbook stays write-only) ---
    if ctx.timetable_path:
        ctx.schedule = load_schedule(ctx.timetable_path)

    if ctx.week is not None:
        siri_txt = ctx.week.siri if ctx.week.siri is not None else "-"
        print(f"Week: minggu {ctx.week.minggu}, siri {siri_txt}"
              + (f" ({ctx.timetable_path})" if ctx.timetable_path else ""))

    # --- Phase two: fillers (the only code allowed to touch cells) ---
    for spec, handler in handlers:
        if handler.phase != "fill":
            continue
        ctx.params = spec.params
        ctx.report.extend(handler.fill(ctx))
    for line in ctx.report:
        print(line)

    wb.save()
    print(f"Done: {template}")
