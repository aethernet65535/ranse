"""Command-line orchestration: ``ranse fill`` / ``ranse write``.

Only orchestration lives here: argparse, the pipeline order, printing the
report and turning a RanseError into ``Error: …`` + exit code 1 (decision
13). Anything business-specific is declared where it lives — the extra
options and the required sheets come from the handlers, and the extra
subcommands come from the readers.

There is no ``--xlsx``: the target template is a profile input (decision 10).
"""

import argparse
import sys

from .core.xlsx import Workbook
from .errors import RanseError
from .handlers.base import Context
from .handlers.registry import build_handlers, cli_options, required_sheets
from .inputs import subcommands
from .inputs.yaml import load_profile, resolve_template

# The subcommands the framework itself provides; every other one is
# declared by the reader that owns it (`inputs.subcommands()`).
_COMMANDS = ("fill", "write")
_PROFILE_HELP = "Path to the profile YAML (inputs + handlers)"


def main(argv=None):
    # Reader-declared subcommands are collected here (not at import time)
    # so `import ranse.cli` never pulls a reader's parser stack in.
    specs = {spec["name"]: spec for spec in subcommands()}
    parser = _build_parser(specs)
    args = parser.parse_args(argv)

    try:
        if args.command == "fill":
            _run_fill(parser, args)
        elif args.command == "write":
            _run_write(args)
        else:
            specs[args.command]["run"](args, parser)
    except RanseError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _build_parser(specs):
    names = list(_COMMANDS) + list(specs)
    parser = argparse.ArgumentParser(
        prog="ranse",
        description="Fill spreadsheet templates in place, driven by a profile")
    subparsers = parser.add_subparsers(dest="command", required=True,
                                       metavar="{" + ",".join(names) + "}")

    fill = subparsers.add_parser("fill", help="fill the profile's template")
    fill.add_argument("--profile", required=True, help=_PROFILE_HELP)
    # Everything else `ranse fill` accepts is declared by a handler.
    for key, flags, kwargs in cli_options():
        fill.add_argument(flags, dest=key, **kwargs)

    write = subparsers.add_parser(
        "write", help="write a single cell on the profile's template")
    write.add_argument("--profile", required=True, help=_PROFILE_HELP)
    write.add_argument("ref", metavar="SHEET!CELL",
                       help="Cell to write, e.g. SHEET!B3 or SHEET!B3:C3")
    write.add_argument("value", help="Value to write (written as text)")

    for spec in specs.values():
        spec["add_arguments"](
            subparsers.add_parser(spec["name"], help=spec["help"]))

    return parser


def _run_write(args):
    """``ranse write`` — one cell through the core write API (decision 9).

    ``write`` has no options of its own: the profile names the workbook, and
    the profile's resolve-phase handlers decide which week's file that is.
    """
    profile = load_profile(args.profile)
    ctx = Context(profile=profile)
    _resolve_phase(build_handlers(profile.handlers), ctx)
    template = resolve_template(profile, ctx.template_vars)
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

    # --- Which workbook is this week's? (profile input; {week} patterns) ---
    template = resolve_template(profile, ctx.template_vars)
    wb = Workbook.open(template)
    ctx.workbook = wb

    missing = [name for name in required_sheets(handlers)
               if name not in wb.sheets]
    if missing:
        print(f"Error: missing sheets: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    _require_something_to_do(parser, handlers, ctx)

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


def _require_something_to_do(parser, handlers, ctx):
    """Fail fast when no fill handler could write anything.

    A filler declares what it cannot work without as ``requires`` — names
    of context values the resolvers publish. The orchestrator only checks
    that each declared name is set; the names are the handlers' own
    vocabulary and are never interpreted here. Fillers with unmet
    requirements simply no-op (their own report lines say why), exactly
    like before, unless *every* filler is blocked.
    """
    fillers = [handler for _, handler in handlers if handler.phase == "fill"]
    blocked = []
    for handler in fillers:
        missing = [name for name in getattr(handler, "requires", ())
                   if getattr(ctx, name, None) is None]
        if missing:
            blocked.append(missing)
    if len(blocked) == len(fillers):
        needed = sorted({name for missing in blocked for name in missing})
        parser.error(
            "nothing to do: "
            + ("no fill handler is configured" if not needed
               else "every filler needs: " + ", ".join(needed)))
