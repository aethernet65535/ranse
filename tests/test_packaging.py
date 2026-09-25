"""Packaging constraints: what the standalone build needs from the source.

`ranse.spec` builds the frozen app from `src/ranse/__main__.py`. PyInstaller
runs that file as a **top-level** script, so it has no parent package once
frozen — a relative import there survives the build (analysis is static)
and only dies at startup with "attempted relative import with no known
parent package". The suite runs `python -m ranse`, where both spellings
work, so nothing else would notice the regression: this pins it.
"""

from harness import SRC_DIR

ENTRY = SRC_DIR / "ranse" / "__main__.py"


def test_the_module_entry_imports_cli_absolutely():
    text = ENTRY.read_text(encoding="utf-8")
    assert "from ranse.cli import main" in text
    assert "from .cli import" not in text, (
        "a relative import has no parent package in a frozen entry script "
        "(ranse.spec runs this file as top-level __main__)")


def test_the_module_entry_exists_where_the_spec_points():
    # ranse.spec names the entry by path; a rename must fail here rather
    # than at build time.
    assert ENTRY.is_file()
