"""Ranse inputs: one reader per source format, each in its own folder.

Inputs never touch the target workbook (docs/DESIGN.md decision 8). The format
each reader accepts is documented in that reader's ``DESIGN.md``; the index is
``inputs/README.md``.

A reader may also declare a ``ranse <name>`` subcommand (the spec is
``{"name", "help", "add_arguments", "run"}``). The readers that ship one are
listed in ``_READERS`` below — a new business plugs its reader in by adding
one name there, without touching ``cli.py``. The collection stays a static,
built-in registry (decision 2): no dynamic import paths, no entry points.
"""

import importlib

# Readers that may declare a SUBCOMMAND (missing attribute = no subcommand).
_READERS = ("dskp",)


def subcommands():
    """The subcommand specs the registered readers declare, in list order."""
    specs = []
    for name in _READERS:
        module = importlib.import_module(f".{name}", __name__)
        spec = getattr(module, "SUBCOMMAND", None)
        if spec is not None:
            specs.append(spec)
    return tuple(specs)
