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
from .handlers.registry import build_handlers, cli_options
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
    # Everything else `ranse fill` accepts is declared by a handler.
    for key, flags, kwargs in cli_options():
        fill.add_argument(flags, dest=key, **kwargs)

    write = subparsers.add_parser(
        "write", help="write a single cell on the profile's template")
    write.add_argument("--profile", required=True,
                       help="Path to the profile YAML (inputs + handlers)")
    write.add_argument("ref", metavar="SHEET!CELL",
                       help="Cell to write, e.g. SHEET!B3 or SHEET!B3:C3")
    write.add_argument("value", help="Value to write (written as text)")

    dskp = subparsers.add_parser(
        "dskp", help="parse a DSKP txt/pdf into structured JSON")
    dskp_input.add_arguments(dskp)

    return parser


def _run_write(args):
    """``ranse write`` — one cell through the core write API (decision 9).

    ``write`` has no options of its own: the profile names the workbook, and
    the profile's resolve-phase handlers decide which week's file that is.
    """
    profile = load_profile(args.profile)
    ctx = Context(profile=profile)
    _resolve_phase(build_handlers(profile.handlers), ctx)
    template = resolve_template(profile, ctx.week.minggu if ctx.week else None)
    wb = Workbook.open(template)
    wb.write(args.ref, args.value)
    wb.save()
    print(f"Done: {args.ref} = {args.value!r} ({template})")


def _resolve_phase(handlers, ctx):
    """Run every resolve-phase handler in profile order (no cell writes)."""
    for spec, handler in handlers:
        if handler.phase != "resolve":
            continue
        ctx.params = spec.params
        handler.resolve(ctx)


def _run_fill(parser, args):
    profile = load_profile(args.profile)

    # Unknown handler names / invalid params fail here, before any cell is
    # touched (decision 2 + "each handler validates its own params").
    handlers = build_handlers(profile.handlers)

    ctx = Context(
        profile=profile,
        runtime={key: getattr(args, key) for key, _, _ in cli_options()},
    )

    # --- Phase one: resolvers compute the inputs (no cell writes) ---
    _resolve_phase(handlers, ctx)

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
