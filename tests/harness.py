"""Shared test-support helpers.

- path constants (repo root, template, golden dir, golden case table);
- ``run_fill``   — the single place that knows how to invoke the fill entry
  point (``python -m ranse``), driven by a profile whose ``inputs.template``
  points at the temporary workbook copy — the template path is profile-only
  (decision 10), so the real asset stays read-only;
- ``fn(name)``   — find a function by name in ``src/ranse``. Unit tests call
  ``fn`` instead of importing a fixed module, so moving code between modules
  does not require editing the tests;
- ``call_error`` — run a function and return its error text, whether the code
  exits (print to stderr + ``sys.exit``) or raises a ``RanseError`` subclass
  carrying the same wording (decision 13);
- ``sheet_xml_map`` / ``gzip_bytes`` — per-sheet XML extraction used by the
  golden generator and the regression test (golden compares sheet XML bytes,
  never zip bytes: zip entry order/timestamps would produce false diffs).
"""

import gzip as _gzip
import importlib
import io
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from contextlib import redirect_stderr
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO_ROOT / "tests"
SRC_DIR = REPO_ROOT / "src"
PLUGINS_DIR = REPO_ROOT / "plugins"
GOLDEN_DIR = TESTS_DIR / "golden"

TEMPLATE_XLSX = REPO_ROOT / "assets" / "ALI BIN ABU" / "12. ERPH" / "template.xlsx"
TIMETABLE_DIR = REPO_ROOT / "assets" / "timetable"
DSKP_DIR = REPO_ROOT / "assets" / "bc-dskp"
PLUGIN_DIR = PLUGINS_DIR / "erph"
PROFILE_YAML = PLUGIN_DIR / "profiles" / "ali-bin-abu" / "profile.yaml"
CALENDAR_YAML = PLUGIN_DIR / "config" / "school-weeks" / "school-weeks.yaml"
PERIOD_TIMES_YAML = PLUGIN_DIR / "config" / "period-times" / "period-times.yaml"

# Golden cases: two normal weeks …
GOLDEN_CASES = {
    "week-33": "2026-09-20",
    "week-34": "2026-09-27",
}
# … and an error case: name → (date, substrings the stderr must contain).
GOLDEN_ERROR_CASES = {
    "holiday": ("2026-01-04", "holiday week"),
}


def assets_available():
    """assets/ is gitignored — a fresh clone must still have green unit tests."""
    return (TEMPLATE_XLSX.is_file()
            and TIMETABLE_DIR.is_dir()
            and DSKP_DIR.is_dir()
            and PROFILE_YAML.is_file()
            and CALENDAR_YAML.is_file())


# ---------------------------------------------------------------------------
# Running the fill entry point
# ---------------------------------------------------------------------------

def _pythonpath():
    """Environment with ``src/`` and ``plugins/`` on PYTHONPATH.

    ``src/`` makes ``python -m ranse`` work; ``plugins/`` makes the plugin
    package (``erph``) importable, exactly like the user's own checkout.
    """
    parts = [str(SRC_DIR), str(PLUGINS_DIR)]
    if os.environ.get("PYTHONPATH"):
        parts.append(os.environ["PYTHONPATH"])
    return {**os.environ, "PYTHONPATH": os.pathsep.join(parts)}


def run_fill(xlsx_path, date, extra_args=()):
    """Run the current fill entry point against a writable xlsx copy.

    The ONLY place that knows the CLI invocation (``python -m ranse fill``;
    the installed console script runs the same entry point). The shipped
    profile is copied to a temp file with ``inputs.template`` pointing at
    ``xlsx_path`` — the CLI has no ``--xlsx`` on purpose (decision 10).

    The profile's own relative paths (``../../config/…``) resolve against
    the profile folder, which moves to a temp directory here, so every
    file-referencing input is pinned to an absolute path.
    Returns a ``subprocess.CompletedProcess``.
    """
    with tempfile.TemporaryDirectory() as tmp:
        raw = yaml.safe_load(PROFILE_YAML.read_text(encoding="utf-8"))
        raw["inputs"]["template"] = str(xlsx_path)
        raw["inputs"]["calendar"] = str(CALENDAR_YAML)
        raw["inputs"]["period_times"] = str(PERIOD_TIMES_YAML)
        # The shipped profile's template is a {week} pattern; a per-week
        # override would beat the temp copy, so drop it.
        raw["inputs"].pop("templates", None)
        profile_path = Path(tmp) / "profile.yaml"
        profile_path.write_text(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        cmd = [
            sys.executable, "-m", "ranse", "fill",
            "--profile", str(profile_path),
            "--date", str(date),
            *extra_args,
        ]
        return subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True,
                              text=True, env=_pythonpath())


# ---------------------------------------------------------------------------
# Sheet XML extraction / golden serialisation
# ---------------------------------------------------------------------------

def sheet_filename(sheet_name):
    """Sheet name → golden file name stem (all current names are plain)."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", sheet_name)


def sheet_xml_map(xlsx_path):
    """{sheet_name: raw worksheet XML bytes} for every sheet of a workbook."""
    with zipfile.ZipFile(xlsx_path) as zf:
        rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        rid_to_target = {}
        for m in re.finditer(r"<Relationship([^>]+)/>", rels):
            attrs = dict(re.findall(r'(\w+)="([^"]+)"', m.group(1)))
            if attrs.get("Id") and attrs.get("Target"):
                rid_to_target[attrs["Id"]] = attrs["Target"]

        wb_xml = zf.read("xl/workbook.xml").decode("utf-8")
        sheets = {}
        for m in re.finditer(
                r'<sheet[^>]*\s+name="([^"]+)"[^>]*r:id="([^"]+)"', wb_xml):
            name, rid = m.group(1), m.group(2)
            target = rid_to_target.get(rid, "")
            if target.startswith("/"):
                target = target[1:]
            elif not target.startswith("xl/"):
                target = "xl/" + target
            sheets[name] = zf.read(target)
    return sheets


def gzip_bytes(data):
    """Deterministic gzip (mtime=0, no embedded filename)."""
    buf = io.BytesIO()
    with _gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as f:
        f.write(data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Function lookup
# ---------------------------------------------------------------------------

_PACKAGE_CANDIDATES = (
    # framework (src/ranse)
    "ranse.errors",
    "ranse.model",
    "ranse.core.refs",
    "ranse.core.format",
    "ranse.core.xlsx",
    "ranse.plugins",
    "ranse.inputs.yaml",
    "ranse.handlers.loader",
    "ranse.handlers.base",
    "ranse.inputs",
    "ranse.cli",
    # the shipped plugin (plugins/erph)
    "erph.domain",
    "erph.inputs.timetable",
    "erph.inputs.dskp",
    "erph.inputs.calendar",
    "erph.handlers.week",
    "erph.handlers.menu",
    "erph.handlers.fixed_cells",
    "erph.handlers.dskp",
)


def fn(name):
    """Return ``name`` from the framework or the shipped plugin.

    Unit tests call ``fn`` instead of importing a fixed module, so moving
    code between modules does not require editing the tests.
    """
    for path in (SRC_DIR, PLUGINS_DIR):
        if path.is_dir() and str(path) not in sys.path:
            sys.path.insert(0, str(path))
    for mod_name in _PACKAGE_CANDIDATES:
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        if hasattr(mod, name):
            return getattr(mod, name)
    raise AttributeError(
        f"{name!r} not found in src/ranse — did a rename land without "
        f"updating the tests?")


# ---------------------------------------------------------------------------
# Error assertions
# ---------------------------------------------------------------------------

def call_error(func, *args, **kwargs):
    """Run ``func``; return its error text (stderr output + exception message).

    Code reports errors either via ``print(..., file=sys.stderr)`` +
    ``sys.exit(1)`` or by raising a ``RanseError`` with the same wording
    (decision 13). Catching BaseException and concatenating stderr with
    ``str(exc)`` covers both styles.
    """
    buf = io.StringIO()
    try:
        with redirect_stderr(buf):
            result = func(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001 — SystemExit included on purpose
        return buf.getvalue() + str(exc)
    raise AssertionError(f"expected an error, got {result!r}")
