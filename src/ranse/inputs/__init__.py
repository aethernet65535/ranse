"""Ranse inputs: one reader per source format, each in its own folder.

Inputs never touch the target workbook (docs/DESIGN.md decision 8). The format
each reader accepts is documented in that reader's ``DESIGN.md``; the index is
``inputs/README.md``.
"""

from . import dskp as _dskp

# Extra ``ranse <name>`` subcommands, each declared by the reader that owns
# it: {"name", "help", "add_arguments", "run"}.
SUBCOMMANDS = (_dskp.SUBCOMMAND,)
