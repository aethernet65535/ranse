"""Built-in handler registry — the only discovery mechanism (decision 2).

No dynamic import paths, no entry points: a profile may only name handlers
listed here. Building also validates each handler's ``params`` so a broken
profile fails before any cell is touched.
"""

from ..errors import ProfileError
from .dskp import DskpFiller
from .fixed_cells import FixedCellsFiller
from .menu import MenuFiller
from .week import WeekResolver

HANDLERS = {
    WeekResolver.name: WeekResolver,
    MenuFiller.name: MenuFiller,
    FixedCellsFiller.name: FixedCellsFiller,
    DskpFiller.name: DskpFiller,
}


def build_handlers(specs):
    """Profile handler specs → ``[(spec, handler_instance), …]``.

    Unknown names and invalid params raise :class:`ProfileError`; handler
    order in the profile is preserved (see handlers/README.md risk 9: static
    entries are written before the automatic ones).
    """
    bound = []
    for spec in specs:
        cls = HANDLERS.get(spec.name)
        if cls is None:
            raise ProfileError(
                f"unknown handler {spec.name!r} (available: "
                f"{', '.join(sorted(HANDLERS))})")
        validate = getattr(cls, "validate", None)
        if validate is not None:
            validate(spec.params)
        bound.append((spec, cls()))
    return bound


def cli_options():
    """The ``ranse fill`` options the registered handlers declare.

    Returns ``[(key, flags, kwargs), …]`` in registry order, de-duplicated by
    key. The orchestrator adds each one with ``dest=key`` and hands
    ``args.<key>`` back to the handlers through ``ctx.runtime[key]``.
    """
    options = []
    seen = set()
    for cls in HANDLERS.values():
        for key, (flags, kwargs) in getattr(cls, "cli_options", {}).items():
            if key in seen:
                continue
            seen.add(key)
            options.append((key, flags, kwargs))
    return options


def required_sheets(handlers):
    """The sheets the built ``handlers`` need, in declaration order, no dups."""
    sheets = []
    for _, handler in handlers:
        for name in getattr(handler, "required_sheets", ()):
            if name not in sheets:
                sheets.append(name)
    return sheets
