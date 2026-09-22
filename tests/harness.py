"""Shared test-support helpers.

Everything the tests need in order to survive the refactor with minimal churn:

- path constants (repo root, template, golden dir, golden case table);
- ``run_fill``   — the single place that knows how to invoke the fill entry
  point (stage 4 swaps ``scripts/fill-erph.py`` → ``ranse fill`` here);
- ``fn(name)``   — find a function by name: first in ``src/ranse`` (once it
  exists), then in the legacy ``scripts/``. Unit tests call ``fn`` instead of
  importing a fixed module, so moving code between stages does not require
  editing the tests (PLAN.md: "纯函数单测不变全绿");
- ``call_error`` — run a function and return its error text, whether the code
  reports errors the legacy way (print to stderr + sys.exit) or the stage-2 way
  (raise a RanseError subclass carrying the same wording);
- ``sheet_xml_map`` / ``gzip_bytes`` — per-sheet XML extraction used by the
  golden generator and the regression test (golden compares sheet XML bytes,
  never zip bytes: zip entry order/timestamps would produce false diffs).
"""

import gzip as _gzip
import importlib
import importlib.util
import io
import re
import subprocess
import sys
import zipfile
from contextlib import redirect_stderr
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO_ROOT / "tests"
SRC_DIR = REPO_ROOT / "src"
SCRIPTS_DIR = REPO_ROOT / "scripts"
FILL_SCRIPT = SCRIPTS_DIR / "fill-erph.py"
GOLDEN_DIR = TESTS_DIR / "golden"

TEMPLATE_XLSX = REPO_ROOT / "assets" / "ALI BIN ABU" / "12. ERPH" / "template.xlsx"
TIMETABLE_DIR = REPO_ROOT / "assets" / "timetable"
DSKP_DIR = REPO_ROOT / "assets" / "bc-dskp"
CONFIG_YAML = SCRIPTS_DIR / "erph-config.yaml"
JADUAL_YAML = SCRIPTS_DIR / "jadual-minggu.yaml"

# Stage-0 golden cases (PLAN.md stage 0): two normal weeks …
GOLDEN_CASES = {
    "minggu-33": "2026-09-20",
    "minggu-34": "2026-09-27",
}
# … and an error case: name → (date, substrings the stderr must contain).
GOLDEN_ERROR_CASES = {
    "cuti": ("2026-01-04", "holiday week"),
}


def assets_available():
    """assets/ is gitignored — a fresh clone must still have green unit tests."""
    return (TEMPLATE_XLSX.is_file()
            and TIMETABLE_DIR.is_dir()
            and DSKP_DIR.is_dir()
            and CONFIG_YAML.is_file()
            and JADUAL_YAML.is_file())


# ---------------------------------------------------------------------------
# Running the fill entry point
# ---------------------------------------------------------------------------

def run_fill(xlsx_path, date):
    """Run the current fill entry point against a writable xlsx copy.

    The ONLY place that knows the CLI invocation: stage 4 replaces the
    ``scripts/fill-erph.py`` call with the installed ``ranse fill``.
    Returns a ``subprocess.CompletedProcess``.
    """
    cmd = [
        sys.executable, str(FILL_SCRIPT),
        "--xlsx", str(xlsx_path),
        "--config", str(CONFIG_YAML),
        "--jadual-config", str(JADUAL_YAML),
        "--date", str(date),
    ]
    return subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)


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
# Function lookup (survives code moving between stages)
# ---------------------------------------------------------------------------

_PACKAGE_CANDIDATES = (
    "ranse.errors",
    "ranse.model",
    "ranse.core.refs",
    "ranse.core.xlsx",
    "ranse.inputs.timetable",
    "ranse.inputs.dskp",
    "ranse.inputs.yaml",
    "ranse.handlers.week",
    "ranse.handlers.menu",
    "ranse.handlers.fixed_cells",
    "ranse.handlers.dskp",
)
_LEGACY_CANDIDATES = (
    (SCRIPTS_DIR / "fill-erph.py", "_legacy_fill_erph"),
    (SCRIPTS_DIR / "gen_dskp.py", "_legacy_gen_dskp"),
)

_modules = {}


def _exec_legacy(path, mod_name):
    """Execute scripts/<file> as a module (filenames contain '-')."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod  # register BEFORE exec (dataclasses need it)
    spec.loader.exec_module(mod)
    return mod


def fn(name):
    """Return ``name`` from the ranse package if present, else from scripts/."""
    if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    for mod_name in _PACKAGE_CANDIDATES:
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        if hasattr(mod, name):
            return getattr(mod, name)
    for path, mod_name in _LEGACY_CANDIDATES:
        if not path.is_file():
            continue
        if mod_name not in _modules:
            _modules[mod_name] = _exec_legacy(path, mod_name)
        if hasattr(_modules[mod_name], name):
            return getattr(_modules[mod_name], name)
    raise AttributeError(
        f"{name!r} not found in src/ranse or scripts/ — did a stage move "
        f"rename it without updating the tests?")


# ---------------------------------------------------------------------------
# Error assertions (legacy sys.exit vs stage-2 RanseError)
# ---------------------------------------------------------------------------

def call_error(func, *args, **kwargs):
    """Run ``func``; return its error text (stderr output + exception message).

    The legacy code reports errors via ``print(..., file=sys.stderr)`` +
    ``sys.exit(1)``; stage 2 switches to RanseError exceptions with the same
    wording (PLAN.md decision 13). Catching BaseException and concatenating
    stderr with ``str(exc)`` keeps the assertions valid across both styles.
    """
    buf = io.StringIO()
    try:
        with redirect_stderr(buf):
            result = func(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001 — SystemExit included on purpose
        return buf.getvalue() + str(exc)
    raise AssertionError(f"expected an error, got {result!r}")
