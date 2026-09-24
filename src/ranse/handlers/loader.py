"""Handler registry: the handlers the installed plugins declare.

Discovery itself lives in :mod:`ranse.plugins` (the folder convention is a
plugin-level idea, shared with readers). This module turns the discovered
handler packages into the registry the orchestrator uses:
``build_handlers`` (name → bound handler, params validated),
``cli_options`` (the options the handlers declare for ``ranse fill``) and
``required_sheets``.

The framework never names a concrete handler: a profile may only use the
names the plugins under ``./plugins`` provide (docs/DESIGN.md D2, revised).
"""

from ..errors import ProfileError
from ..plugins import discovered, has_plugins

# The two handler phases (docs/DESIGN.md S3.2).
_PHASES = ("resolve", "fill")


def handlers():
    """``{name: handler class}`` for every discovered handler package.

    A handler folder ``<plugin>/handlers/<name>/`` registers by convention:
    its ``__init__.py`` defines exactly one class carrying ``name = "<name>"``
    and ``phase = "resolve" | "fill"``.
    """
    registry = {}
    for name, module in discovered("handlers").items():
        registry[name] = _handler_class(name, module)
    return registry


def build_handlers(specs):
    """Profile handler specs → ``[(spec, handler_instance), …]``.

    Unknown names and invalid params raise :class:`ProfileError`; handler
    order in the profile is preserved (see the plugin's handler index: static
    entries are written before the automatic ones).
    """
    registry = handlers()
    bound = []
    for spec in specs:
        cls = registry.get(spec.name)
        if cls is None:
            raise ProfileError(_unknown_handler(spec.name, registry))
        validate = getattr(cls, "validate", None)
        if validate is not None:
            validate(spec.params)
        bound.append((spec, cls()))
    return bound


def cli_options(only=None):
    """The ``ranse fill`` options the registered handlers declare.

    Returns ``[(handler, phase, key, flags, kwargs), …]``, in registry order
    and de-duplicated by key. The declaring handler and its phase travel with
    each option because the CLI presents them as that handler's own help
    section (docs/DESIGN.md S3.4); the orchestrator adds each option with
    ``dest=key`` and hands ``args.<key>`` back through ``ctx.runtime[key]``.

    ``only`` is a list of handler names, in the order they should appear, and
    restricts the result to them — that is how the CLI scopes the option
    surface to the handlers a profile actually names. Names that are not in
    the registry are skipped here; the profile loader reports those, with the
    list of names it did find.
    """
    registry = handlers()
    names = sorted(registry) if only is None else list(only)

    options = []
    seen = set()
    for name in names:
        cls = registry.get(name)
        if cls is None:
            continue
        for key, (flags, kwargs) in getattr(cls, "cli_options", {}).items():
            if key in seen:
                continue
            seen.add(key)
            options.append((name, cls.phase, key, flags, kwargs))
    return options


def required_sheets(handlers):
    """The sheets the built ``handlers`` need, in declaration order, no dups."""
    sheets = []
    for _, handler in handlers:
        for name in getattr(handler, "required_sheets", ()):
            if name not in sheets:
                sheets.append(name)
    return sheets


def _handler_class(name, module):
    """The one class in ``module`` that registers as handler ``name``."""
    candidates = [obj for obj in vars(module).values()
                  if isinstance(obj, type)
                  and getattr(obj, "name", None) == name
                  and getattr(obj, "phase", None) in _PHASES]
    if len(candidates) != 1:
        raise ProfileError(
            f"{module.__name__}: handler {name!r} must define exactly one "
            f"class with name={name!r} and phase in {_PHASES} "
            f"(found {len(candidates)})")
    return candidates[0]


def _unknown_handler(name, registry):
    """ProfileError text for an unresolvable handler name."""
    if registry:
        return (f"unknown handler {name!r} (available: "
                f"{', '.join(sorted(registry))})")
    if not has_plugins():
        return f"unknown handler {name!r}: no plugins found under ./plugins"
    return f"unknown handler {name!r}: no handlers found under ./plugins"
