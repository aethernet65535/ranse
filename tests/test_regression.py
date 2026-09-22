"""Golden regression: run the current implementation and compare sheet XML.

Skipped on a fresh clone — assets/ (template, timetables, DSKP txt) is
gitignored (DESIGN.md risk 5). The pure-function unit tests are the only
protection available without assets.
"""

import gzip
import shutil
import tempfile
from pathlib import Path

import pytest

from harness import (GOLDEN_CASES, GOLDEN_DIR, GOLDEN_ERROR_CASES,
                     TEMPLATE_XLSX, assets_available, run_fill, sheet_filename,
                     sheet_xml_map)

pytestmark = pytest.mark.skipif(
    not assets_available(),
    reason="assets/ not present (gitignored) — see DESIGN.md risk 5")


def _run_in_tmp(date):
    """Copy the template to a writable temp file and run the fill entry point."""
    with tempfile.TemporaryDirectory() as tmp:
        xlsx = Path(tmp) / "template.xlsx"
        shutil.copyfile(TEMPLATE_XLSX, xlsx)
        proc = run_fill(xlsx, date)
        assert proc.returncode == 0, f"fill failed:\n{proc.stderr}"
        return {sheet_filename(name): xml
                for name, xml in sheet_xml_map(xlsx).items()}


@pytest.mark.parametrize("case", sorted(GOLDEN_CASES))
def test_fill_matches_golden(case):
    golden_files = sorted((GOLDEN_DIR / case).glob("*.xml.gz"))
    assert golden_files, (f"no golden for {case} — "
                          f"run: python3 tests/make_golden.py")

    actual = _run_in_tmp(GOLDEN_CASES[case])
    expected = {p.name.removesuffix(".xml.gz"): gzip.decompress(p.read_bytes())
                for p in golden_files}

    assert sorted(actual) == sorted(expected), "sheet set differs from golden"
    for name in sorted(expected):
        assert actual[name] == expected[name], \
            f"{case}: sheet {name} differs from golden"


@pytest.mark.parametrize("case", sorted(GOLDEN_ERROR_CASES))
def test_error_case_stderr_matches_golden(case):
    golden_path = GOLDEN_DIR / case / "stderr.txt"
    assert golden_path.is_file(), (f"missing {golden_path} — "
                                   f"run: python3 tests/make_golden.py")
    date, _ = GOLDEN_ERROR_CASES[case]

    with tempfile.TemporaryDirectory() as tmp:
        xlsx = Path(tmp) / "template.xlsx"
        shutil.copyfile(TEMPLATE_XLSX, xlsx)
        proc = run_fill(xlsx, date)

    assert proc.returncode != 0, "expected a non-zero exit for an error case"
    assert proc.stderr == golden_path.read_text(encoding="utf-8"), \
        f"{case}: stderr wording changed"
