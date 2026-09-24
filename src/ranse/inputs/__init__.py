"""Ranse inputs: the source readers the framework itself ships.

The framework reads exactly one kind of source file itself — the **profile**
— and that reader lives in ``yaml/`` (bootstrapping: the profile has to be
read before anything it configures can be found). Every other reader belongs
to a business and lives in that business's plugin
(``plugins/<name>/inputs/<reader>/``, docs/DESIGN.md S8).

Inputs never touch the target workbook (docs/DESIGN.md decision 8). A plugin
reader may also declare a top-level CLI subcommand — spec ``{"name", "help",
"add_arguments", "run"}`` — by defining ``SUBCOMMAND``; :func:`subcommands`
collects them from the discovered plugins, so ``cli.py`` never names one.
Nothing ships a subcommand, so the stock CLI shows only the framework's own
``fill`` / ``write``.
"""

from ..plugins import reader_subcommands


def subcommands():
    """The subcommand specs the discovered plugin readers declare."""
    return reader_subcommands()
