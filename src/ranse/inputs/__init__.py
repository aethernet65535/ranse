"""Ranse inputs: one reader per source format, each in its own folder.

Inputs never touch the target workbook (docs/DESIGN.md decision 8). The format
each reader accepts is documented in that reader's ``DESIGN.md``; the index is
``inputs/README.md``.

A reader runs standalone as ``python -m ranse.inputs.<name>`` when it ships a
``__main__`` entry (the DSKP reader does). It may *additionally* declare a top
level ``ranse <name>`` subcommand — spec ``{"name", "help", "add_arguments",
"run"}`` — by listing its name in ``_READERS`` below: one line, no changes to
``cli.py`` (static, built-in registry, decision 2: no dynamic import paths, no
entry points). The shipped list is deliberately empty, so the top-level CLI
shows only the framework's own ``fill`` / ``write`` and ``ranse fill`` never
imports a reader.
"""

import importlib

# Readers declaring a SUBCOMMAND; () keeps the top-level CLI framework-only.
_READERS = ()


def subcommands():
    """The subcommand specs the registered readers declare, in list order."""
    specs = []
    for name in _READERS:
        module = importlib.import_module(f".{name}", __name__)
        spec = getattr(module, "SUBCOMMAND", None)
        if spec is not None:
            specs.append(spec)
    return tuple(specs)
