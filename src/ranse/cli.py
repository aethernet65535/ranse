"""Command-line orchestration: ``ranse fill`` / ``ranse write``.

Only orchestration lives here: argparse, the pipeline order, printing the
report and turning a RanseError into ``Error: …`` + exit code 1 (decision
13). Anything business-specific is declared where it lives — the extra
options and the required sheets come from the handlers the plugins
contribute, and the extra subcommands come from their readers.

There is no ``--xlsx``: the target template is a profile input (decision 10).
"""

import argparse
import sys

from .core.xlsx import Workbook
from .errors import RanseError
from .handlers.base import Context
from .handlers.loader import build_handlers, cli_options, required_sheets
from .inputs import subcommands
from .inputs.yaml import load_profile, resolve_template

# The subcommands the framework itself provides. A plugin reader may add its
# own (`inputs.subcommands()`), but no shipped plugin declares one: the
# top-level help stays framework-only and `ranse fill` imports no reader.
_COMMANDS = ("fill", "write")
_PROFILE_HELP = "Path to the profile YAML (inputs + handlers)"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Reader-declared subcommands are collected here (not at import time)
    # so `import ranse.cli` never pulls a reader's parser stack in.
    specs = {spec["name"]: spec for spec in subcommands()}

    try:
        # `fill`'s options belong to handlers, and which handlers run is the
        # profile's business — so the profile is read here, before the parser
        # exists (`_profile_handlers` explains when that is not possible).
        options = cli_options(_profile_handlers(argv))
        parser = _build_parser(specs, options)
        args = parser.parse_args(argv)

        if args.command == "fill":
            _run_fill(parser, args, options)
        elif args.command == "write":
            _run_write(args)
        else:
            specs[args.command]["run"](args, parser)
    except RanseError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _profile_handlers(argv):
    """The handler names the profile named on the command line enables.

    ``ranse fill``'s options are declared by handlers, so the option surface
    — and therefore the parser — depends on the profile. This is only a
    peek: it looks at the framework's own ``--profile`` flag and returns
    ``None`` when there is no profile to read (a reader subcommand, a bare
    ``ranse fill --help``), so the parser then offers every discovered
    handler's options instead. A path that cannot be opened also returns
    ``None``: the run itself reports that, in its own words.
    """
    path = _profile_argument(argv)
    if path is None:
        return None
    try:
        return [spec.name for spec in load_profile(path).handlers]
    except OSError:
        return None


def _profile_argument(argv):
    """The value of ``--profile`` in argv, or None (only `fill` takes one)."""
    if not argv or argv[0] != "fill":
        return None
    for i, token in enumerate(argv):
        if token == "--profile" and i + 1 < len(argv):
            return argv[i + 1]
        if token.startswith("--profile="):
            return token.split("=", 1)[1]
    return None


def _build_parser(specs, options=None):
    """Build the parser; ``options`` defaults to every discovered handler's."""
    if options is None:
        options = cli_options()
    names = list(_COMMANDS) + list(specs)
    parser = argparse.ArgumentParser(
        prog="ranse",
        description="Fill spreadsheet templates in place, driven by a profile")
    subparsers = parser.add_subparsers(dest="command", required=True,
                                       metavar="{" + ",".join(names) + "}")

    fill = subparsers.add_parser("fill", help="fill the profile's template")
    fill.add_argument("--profile", required=True, help=_PROFILE_HELP)
    _add_handler_options(fill, options)

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


def _add_handler_options(fill, options):
    """Add every handler-declared option, each handler in its own section.

    The framework names no business here: a section is titled with the
    handler's registry name and phase, both of which the plugin supplies
    (decision 2). When the profile is known, the sections follow the
    profile's handler order, so the help reads like the run it configures.
    """
    groups = {}
    for handler, phase, key, flags, kwargs in options:
        group = groups.get(handler)
        if group is None:
            group = fill.add_argument_group(f"'{handler}' handler ({phase})")
            groups[handler] = group
        group.add_argument(flags, dest=key, **kwargs)


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


def _run_fill(parser, args, options):
    profile = load_profile(args.profile)

    # Unknown handler names / invalid params fail here, before any cell is
    # touched (decision 2 + "each handler validates its own params").
    handlers = build_handlers(profile.handlers)

    ctx = Context(
        profile=profile,
        runtime={key: getattr(args, key) for _, _, key, _, _ in options},
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
