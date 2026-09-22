"""Command-line orchestration: ``ranse fill`` / ``write`` / ``dskp``.

Only orchestration lives here: argparse, the pipeline order, printing the
report and turning a RanseError into ``Error: …`` + exit code 1 (decision
13). Every business decision belongs to a handler, which is what keeps this
file free of timetable/DSKP knowledge.

There is no ``--xlsx``: the target template is a profile input (decision 10).
"""

import argparse
import sys

from .core.xlsx import Workbook
from .errors import RanseError
from .handlers.base import Context
from .handlers.registry import build_handlers
from .inputs import dskp as dskp_input
from .inputs.timetable import DAY_ORDER, load_schedule
from .inputs.yaml import load_profile, resolve_template

REQUIRED_SHEETS = ["MENU"] + [d.upper() for d in DAY_ORDER]


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "fill":
            _run_fill(parser, args)
        elif args.command == "write":
            _run_write(args)
        else:
            dskp_input.run(args, parser)
    except RanseError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="ranse",
        description="Fill e-RPH xlsx templates from a weekly timetable")
    subparsers = parser.add_subparsers(dest="command", required=True,
                                       metavar="{fill,write,dskp}")

    fill = subparsers.add_parser(
        "fill", help="fill the profile's template (MENU / fixed cells / DSKP)")
    fill.add_argument("--profile", required=True,
                      help="Path to the profile YAML (inputs + handlers)")
    fill.add_argument("--minggu", type=int, default=None,
                      help="Override the week number "
                           "(default: resolved from --date)")
    fill.add_argument("--no-dskp-auto", action="store_true",
                      help="Disable automatic DSKP content-standard filling")
    fill.add_argument("--date",
                      help="Week start date YYYY-MM-DD "
                           "(default: the Sunday of the current week)")

    write = subparsers.add_parser(
        "write", help="write a single cell on the profile's template")
    write.add_argument("--profile", required=True,
                       help="Path to the profile YAML (inputs + handlers)")
    write.add_argument("--minggu", type=int, default=None,
                       help="Week number, needed only when the profile's "
                            "template contains {minggu}")
    write.add_argument("ref", metavar="SHEET!CELL",
                       help="Cell to write, e.g. MENU!B3 or MENU!B3:C3")
    write.add_argument("value", help="Value to write (written as text)")

    dskp = subparsers.add_parser(
        "dskp", help="parse a DSKP txt/pdf into structured JSON")
    dskp_input.add_arguments(dskp)

    return parser


def _run_write(args):
    """``ranse write`` — one cell through the core write API (decision 9)."""
    profile = load_profile(args.profile)
    template = resolve_template(profile, args.minggu)
    wb = Workbook.open(template)
    wb.write(args.ref, args.value)
    wb.save()
    print(f"Done: {args.ref} = {args.value!r} ({template})")


def _run_fill(parser, args):
    profile = load_profile(args.profile)

    # Unknown handler names / invalid params fail here, before any cell is
    # touched (decision 2 + "params 由各 handler 自己校验").
    handlers = build_handlers(profile.handlers)

    ctx = Context(
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

    # --- Which workbook is this week's? (profile input; {minggu} patterns) ---
    template = resolve_template(profile, ctx.week.minggu if ctx.week else None)
    wb = Workbook.open(template)
    ctx.workbook = wb

    missing = [s for s in REQUIRED_SHEETS if s not in wb.sheets]
    if missing:
        print(f"Error: missing sheets: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

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
