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
    order in the profile is preserved (see DESIGN.md risk 9: static DSKP
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
