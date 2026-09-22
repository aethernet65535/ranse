"""DSKP content: automatic two-section selection + cell filling."""

import json
import os
import re
import sys
from typing import List
from xml.etree import ElementTree as ET

from .. import _REPO_ROOT
from ..core.refs import _cell_ref, _resolve_path
from ..errors import ProfileError
from ..inputs.timetable import DAY_ORDER
from ..model import merge_periods
from .base import Context

_DSKP_CONTENT_CACHE = {}


# {tingkatan} / {t} / {T} in the params' `file` → the lesson's tingkatan number
_DSKP_TINGKATAN_PLACEHOLDER = re.compile(r"\{(?:tingkatan|t|T)\}")


def _dskp_file_for_tingkatan(tingkatan, params, base_dir=None):
    """tingkatan ('1'..'5') → DSKP txt/json file path, or None.

    `params.file` picks the source file and auto-detects the tingkatan
    through the {tingkatan} placeholder:

        file: assets/bc-dskp/t{tingkatan}.txt   # T1 → assets/bc-dskp/t1.txt

    It may also be a per-tingkatan map (keys '1'..'5' or 'T1'..'T5'):

        file:
          1: assets/bc-dskp/t1.txt
          2: assets/bc-dskp/t2.txt

    When `file` is absent, `params.dskp_files` (same map, older key) and
    finally the built-in ``inputs.dskp.DSKP_FILES`` table are used.
    """
    spec = params.get("file")
    if spec is None:
        spec = params.get("dskp_files")
    if spec is None:
        try:
            from ..inputs import dskp as _gen_dskp_mod
            spec = _gen_dskp_mod.DSKP_FILES
        except ImportError:
            return None

    if isinstance(spec, dict):
        # Keys may be ints (YAML `1:`) or strings ('1', 'T1', 't1')
        lookup = {str(k).strip().upper(): v for k, v in spec.items()}
        path = lookup.get(str(tingkatan).upper()) or lookup.get(f"T{tingkatan}")
    else:
        path = _DSKP_TINGKATAN_PLACEHOLDER.sub(str(tingkatan),
                                               str(spec).strip())
    if not path:
        return None

    bases = [os.getcwd(), _REPO_ROOT]
    if base_dir:
        bases.insert(0, base_dir)
    return _resolve_path(path, bases)


def _section_pair(sections, minggu):
    """Two parent-level sections for this week: (1,2) → (2,3) → … → wrap to (1,2).

    Sections are the X.0 headings of a DSKP (e.g. '1.0 Listening and Speaking'). The pair
    slides forward one section per week and wraps back to the first section
    as soon as there is no next section left.
    """
    if not isinstance(sections, dict):
        return None
    keys = [k for k in sections if str(k).isdigit()]
    if len(keys) < 2:
        return None
    keys.sort(key=int)
    idx = (int(minggu) - 1) % (len(keys) - 1)
    return keys[idx], keys[idx + 1]


def _auto_subject_matchers(params):
    """dskp params → (subject codes set, uppercased names list)."""
    codes = {str(c).strip() for c in params.get("match_codes", ["BC"])}
    names = [str(n).strip().upper()
             for n in params.get("match_names", ["BAHASA CINA", "华文"])]
    return codes, names


def _is_matched_subject(subject, codes, names, subject_map):
    """Does this timetable subject code/name belong to the auto matchers?"""
    mapped = str(subject_map.get(subject, subject)).upper()
    return subject in codes or any(n in mapped for n in names if n)


def schedule_has_auto_match(schedule, params, subjects):
    """True if the timetable has any lesson the auto mode would fill."""
    codes, names = _auto_subject_matchers(params)
    subject_map = subjects or {}
    for day in DAY_ORDER:
        for entry in schedule.day(day).values():
            if _is_matched_subject(entry.subject, codes, names,
                                   subject_map):
                return True
    return False


def build_auto_dskp_entries(schedule, minggu, params, subjects, base_dir=None):
    """Turn this week's timetable lessons into DSKP fill entries.

    Every subject listed in params.match_codes gets, for each of its
    merged lessons (40 or 80 minutes), two entries: the left column
    (col_start, default B) and the right column (default E) of its class
    block. Returns (entries, report_lines).
    """
    codes, names = _auto_subject_matchers(params)
    cs_idx = int(params.get("cs", 1))
    ls_idx = int(params.get("ls", 1))
    left_col = int(params.get("left_col", 2))
    right_col = int(params.get("right_col", 5))
    subject_map = subjects or {}

    entries, report = [], []
    for day in DAY_ORDER:
        merged = merge_periods(schedule.day(day))
        for class_num, (_, entry) in enumerate(merged, start=1):
            subject = entry.subject
            if not _is_matched_subject(subject, codes, names, subject_map):
                continue

            tingkatan = str(entry.tingkatan).strip()
            dskp_path = _dskp_file_for_tingkatan(tingkatan, params, base_dir)
            if not dskp_path or not os.path.isfile(dskp_path):
                print(f"  Warning: no DSKP file for tingkatan {tingkatan} "
                      f"({day} class {class_num}): "
                      f"{dskp_path or 'file not configured'}, skipping",
                      file=sys.stderr)
                continue

            sections = load_dskp_content(dskp_path)
            pair = _section_pair(sections, minggu)
            if pair is None:
                print(f"  Warning: {dskp_path} has no usable parent sections, "
                      f"skipping", file=sys.stderr)
                continue

            left, right = pair
            for col_start, sec in ((left_col, left), (right_col, right)):
                entries.append({
                    "sheet": day.upper(),
                    "class": class_num,
                    "file": dskp_path,
                    "selection": [int(sec), cs_idx, ls_idx],
                    "col_start": col_start,
                })

            left_title = sections[left].get("title", str(left))
            right_title = sections[right].get("title", str(right))
            report.append(
                f"  {day.upper()} class {class_num} "
                f"({entry.cls}, {entry.start}-{entry.end}, T{tingkatan}): "
                f"{left_title} + {right_title}")

    return entries, report


# ---------------------------------------------------------------------------
# DSKP content filling
# ---------------------------------------------------------------------------

def load_dskp_content(file_path):
    """Load DSKP content from a JSON or txt file (cached per path).

    JSON: output from ``ranse dskp`` (structured dict).
    TXT: parsed on-the-fly by the inputs.dskp parser.
    """
    if file_path in _DSKP_CONTENT_CACHE:
        return _DSKP_CONTENT_CACHE[file_path]

    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    # Try JSON first
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        parsed = None

    if parsed is None:
        # Fall back to txt parsing (full sections, no selection)
        try:
            from ..inputs import dskp as _gen_dskp_mod
            parsed = _gen_dskp_mod.parse_dskp_txt(content)
        except ImportError:
            print("  Warning: gen_dskp.py not found, cannot parse txt",
                  file=sys.stderr)
            parsed = None

    _DSKP_CONTENT_CACHE[file_path] = parsed
    return parsed


# Class block layout: each class is CLASS_BLOCK_SIZE rows apart.
# Class 1 header at row 7, Class 2 at 38, Class 3 at 69, etc.
CLASS_BLOCK_SIZE = 31
CLASS_HEADER_ROW = 7  # row of the class header ("KELAS: N")
CLASS_OFFSET_TITLE = 6   # +6 from header → title/skill row
CLASS_OFFSET_CS = 7      # +7 → content standard
CLASS_OFFSET_LS = 9      # +9 → learning standard


def _class_start_row(class_num):
    """Return the header row for class_num (1-based)."""
    return CLASS_HEADER_ROW + (class_num - 1) * CLASS_BLOCK_SIZE


def _write_dskp_cells(sheet, content, col_start, class_num):
    """Write DSKP content to a column block (3 cols wide) in the sheet.

    Args:
        sheet: writable Sheet (core API)
        content: dict with keys title, content_standard, learning_standard
        col_start: starting column (2=B, 5=E, 9=I)
        class_num: class number (1-based)
    """
    base = _class_start_row(class_num)

    if "title" in content:
        r = base + CLASS_OFFSET_TITLE
        sheet.write(_cell_ref(r, col_start), content["title"])

    if "content_standard" in content:
        r = base + CLASS_OFFSET_CS
        sheet.write(_cell_ref(r, col_start),
                    content["content_standard"]["content"])

    if "learning_standard" in content:
        r = base + CLASS_OFFSET_LS
        sheet.write(_cell_ref(r, col_start),
                    content["learning_standard"]["content"])


class DskpFiller:
    """Fill the day sheets' DSKP blocks.

    Entry order is significant: static entries come first, automatic ones
    are appended after them, so on the same cell the automatic entry wins
    (PLAN.md risk 9).

    Profile form::

        - name: dskp
          params:
            mode: auto                # auto (default) | static
            entries:                  # static entries (written first)
              - {sheet: ISNIN, class: 1, file: t1.json,
                 selection: [1, 1, 1], col_start: 2}
            file: assets/bc-dskp/t{tingkatan}.txt
            match_codes: [BC]
            match_names: ["BAHASA CINA", "华文"]
            cs: 1
            ls: 1
            left_col: 2
            right_col: 5
    """

    name = "dskp"
    phase = "fill"

    @staticmethod
    def validate(params):
        mode = params.get("mode", "auto")
        if mode not in ("auto", "static"):
            raise ProfileError(
                f"dskp handler: unknown mode {mode!r} (use 'auto' or 'static')")

        entries = params.get("entries") or []
        if not isinstance(entries, list):
            raise ProfileError("dskp handler: 'entries' must be a list")
        for i, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                raise ProfileError(f"dskp handler: entries[{i}] must be a mapping")
            if not entry.get("sheet"):
                raise ProfileError(
                    f"dskp handler: entries[{i}] is missing 'sheet'")
            if not entry.get("file"):
                raise ProfileError(
                    f"dskp handler: entries[{i}] is missing 'file'")
            selection = entry.get("selection")
            if selection is not None and (
                    not isinstance(selection, (list, tuple))
                    or len(selection) != 3):
                raise ProfileError(
                    f"dskp handler: entries[{i}] 'selection' must be "
                    f"[section, content_standard, learning_standard]")

        for key in ("cs", "ls", "left_col", "right_col", "class", "col_start"):
            if key in params and not isinstance(params[key], int):
                raise ProfileError(
                    f"dskp handler: '{key}' must be an integer")

    def fill(self, ctx: Context) -> List[str]:
        params = ctx.params
        subjects = ctx.profile.context.get("subjects") or {}

        entries = list(params.get("entries") or [])
        report = self._auto_entries(ctx, params, subjects, entries)

        base_dir = ctx.profile.base_dir
        for dskp_cfg in entries:
            sheet_name = dskp_cfg.get("sheet")
            class_num = dskp_cfg.get("class", 1)
            json_path = dskp_cfg.get("file")
            selection = dskp_cfg.get("selection")
            col_start = dskp_cfg.get("col_start", 2)  # default B

            if not sheet_name:
                print("  Warning: dskp entry missing 'sheet', skipping",
                      file=sys.stderr)
                continue

            if sheet_name not in ctx.workbook.sheets:
                print(f"  Warning: sheet '{sheet_name}' not found, skipping",
                      file=sys.stderr)
                continue

            json_path = _resolve_path(json_path, [base_dir, os.getcwd(),
                                                  _REPO_ROOT])
            if not json_path or not os.path.isfile(json_path):
                print(f"  Warning: DSKP file not found: {json_path}",
                      file=sys.stderr)
                continue

            content = load_dskp_content(json_path)

            # Resolve selection if provided
            if selection:
                try:
                    from ..inputs import dskp as _gen_dskp_mod
                    content = _gen_dskp_mod.resolve_selection(content, selection)
                except ImportError:
                    print("  Warning: gen_dskp.py not found, using raw JSON",
                          file=sys.stderr)

            if content is None:
                print(f"  Warning: no content for selection {selection}",
                      file=sys.stderr)
                continue

            _write_dskp_cells(ctx.workbook.sheet(sheet_name), content,
                              col_start, class_num)
        return report

    def _auto_entries(self, ctx, params, subjects, entries):
        """Append this week's automatic entries to ``entries``; return report."""
        if params.get("mode", "auto") != "auto":
            return []
        if ctx.runtime.get("no_dskp_auto"):
            return []

        if ctx.week is not None:
            if not ctx.schedule:
                return []
            auto, report = build_auto_dskp_entries(
                ctx.schedule, ctx.week.minggu, params, subjects,
                ctx.profile.base_dir)
            entries.extend(auto)
            return report

        # Without a week number there is no section pair to pick — say so
        # instead of silently writing nothing.
        if ctx.schedule and schedule_has_auto_match(ctx.schedule, params,
                                                   subjects):
            return ["Note: automatic DSKP filling skipped (no week known) — "
                    "add inputs.jadual to the profile or pass --minggu N "
                    "to enable it"]
        return []
