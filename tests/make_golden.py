#!/usr/bin/env python3
"""Generate golden baselines from the CURRENT implementation (manual step).

    python3 tests/make_golden.py

For each case the template is copied into a temp directory first (the fill
script overwrites its target in place, and the real template is read-only),
then the resulting per-sheet XML is stored under:

    tests/golden/<case>/<sheet>.xml.gz      normal weeks
    tests/golden/<case>/stderr.txt          error cases (exit code + wording)

Golden compares sheet XML byte-for-byte, never zip bytes — zip entry order
and timestamps would produce false diffs (docs/DESIGN.md risks 1–2).

Run this once when baselines must be (re)generated, review the diff, commit
the result to git.
"""

import shutil
import sys
import tempfile
from pathlib import Path

from harness import (GOLDEN_CASES, GOLDEN_DIR, GOLDEN_ERROR_CASES,
                     TEMPLATE_XLSX, assets_available, gzip_bytes, run_fill,
                     sheet_filename, sheet_xml_map)


def _prepare_case_dir(name):
    case_dir = GOLDEN_DIR / name
    shutil.rmtree(case_dir, ignore_errors=True)
    case_dir.mkdir(parents=True)
    return case_dir


def _copy_template(tmp):
    # copyfile copies content only — the asset itself is read-only.
    xlsx = Path(tmp) / "template.xlsx"
    shutil.copyfile(TEMPLATE_XLSX, xlsx)
    return xlsx


def make_case(name, date):
    """Run a normal week and store its per-sheet XML."""
    case_dir = _prepare_case_dir(name)
    with tempfile.TemporaryDirectory() as tmp:
        xlsx = _copy_template(tmp)
        proc = run_fill(xlsx, date)
        if proc.returncode != 0:
            sys.exit(f"{name}: fill failed (exit {proc.returncode})\n"
                     f"{proc.stderr}")
        sheets = sheet_xml_map(xlsx)
    for sheet_name, xml in sheets.items():
        out = case_dir / f"{sheet_filename(sheet_name)}.xml.gz"
        out.write_bytes(gzip_bytes(xml))
    print(f"{name}: exit 0, {len(sheets)} sheets -> {case_dir}")


def make_error_case(name, date, expect):
    """Run a failing week; store its stderr wording (golden for the message)."""
    case_dir = _prepare_case_dir(name)
    with tempfile.TemporaryDirectory() as tmp:
        xlsx = _copy_template(tmp)
        proc = run_fill(xlsx, date)
    if proc.returncode == 0:
        sys.exit(f"{name}: expected a non-zero exit, got success")
    if expect not in proc.stderr:
        sys.exit(f"{name}: stderr does not contain {expect!r}:\n{proc.stderr}")
    (case_dir / "stderr.txt").write_text(proc.stderr, encoding="utf-8")
    print(f"{name}: exit {proc.returncode}, stderr -> {case_dir}")


def main():
    if not assets_available():
        sys.exit("assets/ incomplete (template/timetable/bc-dskp) — "
                 "cannot build golden baselines")
    for name, date in GOLDEN_CASES.items():
        make_case(name, date)
    for name, (date, expect) in GOLDEN_ERROR_CASES.items():
        make_error_case(name, date, expect)
    print("done — review `git status tests/golden` and commit.")


if __name__ == "__main__":
    main()
