"""DSKP content: automatic two-section selection + cell filling (stage 1 move)."""

import json
import os
import re
import sys
from xml.etree import ElementTree as ET

from .. import _REPO_ROOT
from ..core.refs import _cell_ref, _resolve_path
from ..core.xlsx import (_find_merge_top_left, _get_merge_ranges,
                         _parse_sheet, write_cell)
from ..inputs.timetable import DAY_ORDER, merge_periods

_DSKP_CONTENT_CACHE = {}


# {tingkatan} / {t} / {T} in dskp_auto.file → the lesson's tingkatan number
_DSKP_TINGKATAN_PLACEHOLDER = re.compile(r"\{(?:tingkatan|t|T)\}")


def _dskp_file_for_tingkatan(tingkatan, auto_cfg, config_dir=None):
    """tingkatan ('1'..'5') → DSKP txt/json file path, or None.

    `dskp_auto.file` picks the source file and auto-detects the tingkatan
    through the {tingkatan} placeholder:

        file: assets/bc-dskp/t{tingkatan}.txt   # T1 → assets/bc-dskp/t1.txt

    It may also be a per-tingkatan map (keys '1'..'5' or 'T1'..'T5'):

        file:
          1: assets/bc-dskp/t1.txt
          2: assets/bc-dskp/t2.txt

    When `file` is absent, `dskp_auto.dskp_files` (same map, older key) and
    finally the built-in gen_dskp.DSKP_FILES table are used.
    """
    spec = auto_cfg.get("file")
    if spec is None:
        spec = auto_cfg.get("dskp_files")
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
    if config_dir:
        bases.insert(0, config_dir)
    return _resolve_path(path, bases)


def _section_pair(sections, minggu):
    """Two parent-level sections for this week: (1,2) → (2,3) → … → wrap to (1,2).

    Sections are the X.0 headings of a DSKP (e.g. '1.0 听说技能'). The pair
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


def _auto_subject_matchers(auto):
    """dskp_auto config → (subject codes set, uppercased names list)."""
    codes = {str(c).strip() for c in auto.get("match_codes", ["BC"])}
    names = [str(n).strip().upper()
             for n in auto.get("match_names", ["BAHASA CINA", "华文"])]
    return codes, names


def _is_matched_subject(subject, codes, names, subject_map):
    """Does this timetable subject code/name belong to dskp_auto?"""
    mapped = str(subject_map.get(subject, subject)).upper()
    return subject in codes or any(n in mapped for n in names if n)


def schedule_has_auto_match(schedule, cfg):
    """True if the timetable has any lesson dskp_auto would fill."""
    auto = cfg.get("dskp_auto") or {}
    if not auto.get("enabled", True):
        return False
    codes, names = _auto_subject_matchers(auto)
    subject_map = cfg.get("subjects") or {}
    for day in DAY_ORDER:
        for entry in schedule.get(day, {}).values():
            if _is_matched_subject(entry["subject"], codes, names,
                                   subject_map):
                return True
    return False


def build_auto_dskp_entries(schedule, minggu, cfg):
    """Turn this week's timetable lessons into DSKP fill entries.

    Every subject listed in dskp_auto.match_codes gets, for each of its
    merged lessons (40 or 80 minutes), two entries: the left column
    (col_start, default B) and the right column (default E) of its class
    block. Returns (entries, report_lines).
    """
    auto = cfg.get("dskp_auto") or {}
    if not auto.get("enabled", True):
        return [], []

    codes, names = _auto_subject_matchers(auto)
    cs_idx = int(auto.get("cs", 1))
    ls_idx = int(auto.get("ls", 1))
    left_col = int(auto.get("left_col", 2))
    right_col = int(auto.get("right_col", 5))
    subject_map = cfg.get("subjects") or {}

    entries, report = [], []
    for day in DAY_ORDER:
        merged = merge_periods(schedule.get(day, {}))
        for class_num, (_, entry) in enumerate(merged, start=1):
            subject = entry["subject"]
            if not _is_matched_subject(subject, codes, names, subject_map):
                continue

            tingkatan = str(entry["tingkatan"]).strip()
            dskp_path = _dskp_file_for_tingkatan(tingkatan, auto,
                                                 cfg.get("_config_dir"))
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
                f"({entry['class']}, {entry['start']}-{entry['end']}, T{tingkatan}): "
                f"{left_title} + {right_title}")

    return entries, report


# ---------------------------------------------------------------------------
# DSKP content filling
# ---------------------------------------------------------------------------

def load_dskp_content(file_path):
    """Load DSKP content from a JSON or txt file (cached per path).

    JSON: output from gen_dskp.py (structured dict).
    TXT: parsed on-the-fly using gen_dskp parser (requires --select).
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
CLASS_HEADER_ROW = 7  # row of "班级: N" / "KELAS: N"
CLASS_OFFSET_TITLE = 6   # +6 from header → title/skill row
CLASS_OFFSET_CS = 7      # +7 → content standard
CLASS_OFFSET_LS = 9      # +9 → learning standard


def _class_start_row(class_num):
    """Return the header row for class_num (1-based)."""
    return CLASS_HEADER_ROW + (class_num - 1) * CLASS_BLOCK_SIZE


def write_dskp_cells(root, merges, content, col_start, class_num):
    """Write DSKP content to a column block (3 cols wide) in the sheet.

    Args:
        root: sheet XML root element
        merges: list of merge ranges
        content: dict with keys title, content_standard, learning_standard
        col_start: starting column (2=B, 5=E, 9=I)
        class_num: class number (1-based)
    """
    base = _class_start_row(class_num)

    if "title" in content:
        r, c = _find_merge_top_left(merges, base + CLASS_OFFSET_TITLE, col_start)
        write_cell(root, _cell_ref(r, c), content["title"])

    if "content_standard" in content:
        r, c = _find_merge_top_left(merges, base + CLASS_OFFSET_CS, col_start)
        write_cell(root, _cell_ref(r, c), content["content_standard"]["content"])

    if "learning_standard" in content:
        r, c = _find_merge_top_left(merges, base + CLASS_OFFSET_LS, col_start)
        write_cell(root, _cell_ref(r, c), content["learning_standard"]["content"])


def fill_dskp_sheets(zip_data, sheet_map, dskp_configs):
    """Fill DSKP content in specified sheets.

    Each config entry specifies: sheet, class, col_start, file, selection.
    Multiple entries can target different sheets/classes/columns.

    Args:
        zip_data: xlsx zip data dict
        sheet_map: sheet name → path mapping
        dskp_configs: list of dicts from config
    """
    # Cache parsed sheets to avoid re-parsing for multiple entries on same sheet
    parsed_cache = {}  # sheet_name → (root, modified)

    for dskp_cfg in dskp_configs:
        sheet_name = dskp_cfg.get("sheet")
        class_num = dskp_cfg.get("class", 1)
        json_path = dskp_cfg.get("file")
        selection = dskp_cfg.get("selection")
        col_start = dskp_cfg.get("col_start", 2)  # default B

        if not sheet_name:
            print("  Warning: dskp entry missing 'sheet', skipping",
                  file=sys.stderr)
            continue

        if sheet_name not in sheet_map:
            print(f"  Warning: sheet '{sheet_name}' not found, skipping",
                  file=sys.stderr)
            continue

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

        # Get or parse the sheet
        if sheet_name not in parsed_cache:
            path = sheet_map[sheet_name]
            root = _parse_sheet(zip_data[path])
            merges = _get_merge_ranges(root)
            parsed_cache[sheet_name] = (root, merges, False)

        root, merges, _ = parsed_cache[sheet_name]
        write_dskp_cells(root, merges, content, col_start, class_num)
        parsed_cache[sheet_name] = (root, merges, True)

    # Write back all modified sheets
    for sheet_name, (root, merges, modified) in parsed_cache.items():
        if modified:
            path = sheet_map[sheet_name]
            zip_data[path] = ET.tostring(root, xml_declaration=True,
                                         encoding="UTF-8",
                                         short_empty_elements=False)
