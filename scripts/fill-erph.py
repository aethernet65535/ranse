"""Fill an e-RPH xlsx template with timetable data.

Bypasses openpyxl — reads/writes the xlsx zip directly and uses
xml.etree.ElementTree to surgically patch cell values while
preserving every original attribute (style, type, etc.).

Usage:
    python fill-erph.py --xlsx <template.xlsx> --timetable-xlsx <timetable.xlsx> [--config <config.yaml>] [--date YYYY-MM-DD]
    python fill-erph.py --xlsx <template.xlsx> --csv <timetable.csv> [--config <config.yaml>] [--date YYYY-MM-DD]
    python fill-erph.py --xlsx <template.xlsx> --jadual-config jadual-minggu.yaml [--date YYYY-MM-DD]

With --jadual-config the week number is resolved from --date (default:
the Sunday of the current week), the timetable is picked automatically
via minggu → siri → jadual file, and every Bahasa Cina lesson is filled
with two parent-level content standards (left/right columns).
"""

import argparse
import csv
import json
import os
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

import yaml

import constants as const

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DAY_ORDER = ["Ahad", "Isnin", "Selasa", "Rabu", "Khamis"]

# Monday-first weekday index → Malay day name (same order as DAY_ORDER for
# the school week, which starts on Sunday/Ahad).
DAY_BY_WEEKDAY = ["Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"]

REQUIRED_SHEETS = ["MENU"] + [d.upper() for d in DAY_ORDER]

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PERIOD_TIMES = {
    ("07:40", "08:20"): 1,
    ("08:20", "09:00"): 2,
    ("09:00", "09:40"): 3,
    ("09:40", "10:20"): 4,
    ("10:20", "10:50"): 5,
    ("10:50", "11:30"): 6,
    ("11:30", "12:10"): 7,
    ("12:10", "12:50"): 8,
    ("12:50", "13:30"): 9,
    ("13:30", "14:10"): 10,
}

NUM_PERIODS = 8

_TIME_SUFFIX_CACHE = {}
for _h in range(24):
    _t = f"{_h:02d}:00"
    if _h < 11:
        _TIME_SUFFIX_CACHE[_t] = f"{_t} PAGI"
    elif _h < 14:
        _TIME_SUFFIX_CACHE[_t] = f"{_t} TGH"
    else:
        _TIME_SUFFIX_CACHE[_t] = f"{_t} TPTG"

_EXCEL_EPOCH = datetime(1899, 12, 30)

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _col_to_num(col_str):
    """'A' → 1, 'Z' → 26, 'AA' → 27."""
    n = 0
    for ch in col_str.upper():
        n = n * 26 + (ord(ch) - 64)
    return n


def _col_letter(n):
    """1 → 'A', 26 → 'Z', 27 → 'AA'."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell_ref(row, col):
    """(6, 3) → 'C6'."""
    return f"{_col_letter(col)}{row}"


def _parse_cell_ref(ref):
    """'C6' → (row=6, col=3)."""
    m = re.match(r"([A-Z]+)(\d+)", ref)
    return int(m.group(2)), _col_to_num(m.group(1))


def _date_to_excel(dt):
    return (dt - _EXCEL_EPOCH).days


def _cell_range_top_left(range_str):
    """'B3:C3' → 'B3'."""
    m = re.match(r"([A-Z]+\d+)", range_str)
    return m.group(1) if m else range_str


def _sunday_of(dt):
    """Return the Sunday of the week containing dt (school weeks start Ahad)."""
    return dt - timedelta(days=(dt.weekday() + 1) % 7)


def _resolve_path(path, bases):
    """Resolve a possibly-relative path against a list of base directories."""
    if os.path.isabs(path):
        return path
    for base in bases:
        candidate = os.path.join(base, path)
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(bases[0], path)


# ---------------------------------------------------------------------------
# Xlsx zip read / write
# ---------------------------------------------------------------------------

def _read_zip(path):
    with zipfile.ZipFile(path, "r") as zf:
        return {info.filename: zf.read(info.filename) for info in zf.infolist()}


def _parse_sheet_rels(zip_data):
    rels_xml = zip_data.get("xl/_rels/workbook.xml.rels", b"").decode("utf-8")
    rid_to_target = {}
    for m in re.finditer(r'<Relationship([^>]+)/>', rels_xml):
        attrs = dict(re.findall(r'(\w+)="([^"]+)"', m.group(1)))
        rid = attrs.get("Id")
        target = attrs.get("Target")
        if rid and target:
            rid_to_target[rid] = target
    return rid_to_target


def _parse_sheet_names(zip_data, rid_to_target):
    wb_xml = zip_data.get("xl/workbook.xml", b"").decode("utf-8")
    sheet_map = {}
    for m in re.finditer(
            r'<sheet[^>]*\s+name="([^"]+)"[^>]*r:id="([^"]+)"', wb_xml):
        name, rid = m.group(1), m.group(2)
        target = rid_to_target.get(rid, "")
        if target.startswith("/"):
            target = target[1:]
        elif not target.startswith("xl/"):
            target = "xl/" + target
        sheet_map[name] = target
    return sheet_map


def _read_shared_strings(zip_data):
    raw = zip_data.get("xl/sharedStrings.xml")
    if raw is None:
        return []
    root = ET.fromstring(raw)
    strings = []
    for si in root.iter(f"{NS}si"):
        t = si.find(f"{NS}t")
        if t is not None and t.text:
            strings.append(t.text)
            continue
        parts = []
        for r_elem in si.iter(f"{NS}r"):
            t2 = r_elem.find(f"{NS}t")
            if t2 is not None and t2.text:
                parts.append(t2.text)
        strings.append("".join(parts))
    return strings


# ---------------------------------------------------------------------------
# Sheet XML parsing (ElementTree-based)
# ---------------------------------------------------------------------------

def _parse_sheet(xml_bytes):
    """Parse sheet XML bytes → (ElementTree root, namespace map)."""
    # Register namespaces so serialisation keeps the original prefixes.
    ET.register_namespace("", NS[1:-1])  # strip braces
    ET.register_namespace("r", NS_R[1:-1])
    # Also register common xlsx namespaces to prevent 'ns0:' prefixes.
    for prefix, uri in [
        ("mc", "http://schemas.openxmlformats.org/markup-compatibility/2006"),
        ("x14ac", "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"),
        ("xr", "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"),
        ("xr6", "http://schemas.microsoft.com/office/spreadsheetml/2014/revision6"),
        ("xr10", "http://schemas.microsoft.com/office/spreadsheetml/2014/revision10"),
    ]:
        ET.register_namespace(prefix, uri)
    root = ET.fromstring(xml_bytes)
    return root


def _get_merge_ranges(root):
    """Return list of (min_row, min_col, max_row, max_col) from <mergeCells>."""
    mc = root.find(f"{NS}mergeCells")
    if mc is None:
        return []
    ranges = []
    for merge_cell in mc.iter(f"{NS}mergeCell"):
        ref = merge_cell.get("ref", "")
        if ":" not in ref:
            continue
        tl, br = ref.split(":")
        r1, c1 = _parse_cell_ref(tl)
        r2, c2 = _parse_cell_ref(br)
        ranges.append((r1, c1, r2, c2))
    return ranges


def _find_merge_top_left(merges, row, col):
    for mr1, mc1, mr2, mc2 in merges:
        if mr1 <= row <= mr2 and mc1 <= col <= mc2:
            return mr1, mc1
    return row, col


def _get_row_map(root):
    """Return {row_num: row_element} for all <row> in <sheetData>."""
    sd = root.find(f"{NS}sheetData")
    if sd is None:
        return {}
    return {int(row.get("r")): row for row in sd.iter(f"{NS}row")}


def _get_cell_map(row_elem):
    """Return {col_num: cell_element} for all <c> in a <row>."""
    cells = {}
    for c in row_elem.iter(f"{NS}c"):
        ref = c.get("r")
        if ref:
            _, col = _parse_cell_ref(ref)
            cells[col] = c
    return cells


def _set_cell_value(cell_elem, value):
    """Set the <v> content of an existing cell element.

    Preserves ALL original attributes (s, t, style, etc.) on <c>.
    For strings, sets t="inlineStr" and uses <is><t>…</t></is>.
    For numbers, removes any t= attribute and uses <v>…</v>.
    """
    if isinstance(value, str):
        # --- string: use inline string format ---
        cell_elem.set("t", "inlineStr")
        # Remove existing <v> and <is>
        for old in cell_elem.findall(f"{NS}v"):
            cell_elem.remove(old)
        for old in cell_elem.findall(f"{NS}is"):
            cell_elem.remove(old)
        # Build <is><t>text</t></is>
        is_elem = ET.SubElement(cell_elem, f"{NS}is")
        t_elem = ET.SubElement(is_elem, f"{NS}t")
        t_elem.text = value
    else:
        # --- number: use <v>…</v> ---
        # Remove t= attribute (numbers don't need it).
        if "t" in cell_elem.attrib:
            del cell_elem.attrib["t"]
        # Remove existing <v> and <is>
        for old in cell_elem.findall(f"{NS}v"):
            cell_elem.remove(old)
        for old in cell_elem.findall(f"{NS}is"):
            cell_elem.remove(old)
        v_elem = ET.SubElement(cell_elem, f"{NS}v")
        v_elem.text = str(value)


def _ensure_row(root, row_num):
    """Return the <row r="row_num"> element, creating it if needed."""
    row_map = _get_row_map(root)
    if row_num in row_map:
        return row_map[row_num]

    sd = root.find(f"{NS}sheetData")
    new_row = ET.SubElement(sd, f"{NS}row")
    new_row.set("r", str(row_num))

    # Re-sort rows in sheetData so the new row is in the right position.
    rows = sorted(sd.findall(f"{NS}row"), key=lambda r: int(r.get("r", 0)))
    for r in sd.findall(f"{NS}row"):
        sd.remove(r)
    for r in rows:
        sd.append(r)

    return new_row


def _ensure_cell(row_elem, ref):
    """Return the <c r="ref"> element, creating it if needed."""
    row_num, col_num = _parse_cell_ref(ref)
    cell_map = _get_cell_map(row_elem)
    if col_num in cell_map:
        return cell_map[col_num]

    new_c = ET.SubElement(row_elem, f"{NS}c")
    new_c.set("r", ref)

    # Re-sort cells in row so the new cell is in column order.
    cells = sorted(row_elem.findall(f"{NS}c"),
                   key=lambda c: _parse_cell_ref(c.get("r", "A1"))[1])
    for c in row_elem.findall(f"{NS}c"):
        row_elem.remove(c)
    for c in cells:
        row_elem.append(c)

    return new_c


def write_cell(root, ref, value):
    """Write a value to a specific cell in the parsed sheet tree."""
    row_num, col_num = _parse_cell_ref(ref)
    row_elem = _ensure_row(root, row_num)
    cell_elem = _ensure_cell(row_elem, ref)
    _set_cell_value(cell_elem, value)


# ---------------------------------------------------------------------------
# CSV / schedule helpers
# ---------------------------------------------------------------------------

def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_schedule(rows):
    """Build a schedule from CSV rows, keyed by day name (as read_timetable_xlsx)."""
    schedule = defaultdict(dict)
    for r in rows:
        period = PERIOD_TIMES.get((r["Start Time"], r["End Time"]))
        if period is None:
            continue
        day = _day_name_from_date(r.get("Date", ""))
        if day is None:
            print(f"  Warning: cannot read day from Date={r.get('Date')!r}, skipping row",
                  file=sys.stderr)
            continue
        if day not in DAY_ORDER:
            # Jumaat/Sabtu have no sheet in the template.
            continue
        schedule[day][period] = {
            "class": r["Class"],
            "start": r["Start Time"],
            "end": r["End Time"],
            "subject": r["Subject"],
            "tingkatan": r["Tingkatan"],
        }
    return schedule


def _day_name_from_date(value):
    """'2026-09-20' → 'Ahad'. Returns None if the date cannot be parsed."""
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            d = datetime.strptime(value, fmt)
        except ValueError:
            continue
        return DAY_BY_WEEKDAY[d.weekday()]
    return None


def merge_periods(day_schedule):
    """Merge consecutive periods with the same class/subject/tingkatan."""
    periods = sorted(day_schedule.keys())
    if not periods:
        return []

    merged = []
    buf_start = periods[0]
    buf_entry = day_schedule[periods[0]]

    for p in periods[1:]:
        entry = day_schedule[p]
        same = (entry["class"] == buf_entry["class"]
                and entry["subject"] == buf_entry["subject"]
                and entry["tingkatan"] == buf_entry["tingkatan"]
                and entry["start"] == buf_entry["end"])
        if same:
            buf_entry = {**buf_entry, "end": entry["end"]}
        else:
            merged.append((buf_start, buf_entry))
            buf_start = p
            buf_entry = entry

    merged.append((buf_start, buf_entry))
    return merged


def _time_with_suffix(t):
    hour = int(t.split(":")[0])
    key = f"{hour:02d}:{t.split(':')[1]}"
    return _TIME_SUFFIX_CACHE.get(key, f"{t} PAGI")


# ---------------------------------------------------------------------------
# Timetable xlsx reading
# ---------------------------------------------------------------------------

CLASS_CODE_RE = re.compile(r"([A-Z]+)[–-](\d+)([A-Za-z]+)")


def _parse_class_code(code):
    """Parse 'BC-1A' → ('BC', '1', 'A')."""
    m = CLASS_CODE_RE.match(code)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return code, "", ""


def _read_cell_value(cell_elem, shared_strings):
    """Read the text value from a <c> element, resolving shared strings."""
    t = cell_elem.get("t")
    v = cell_elem.find(f"{NS}v")
    is_elem = cell_elem.find(f"{NS}is")

    # Inline string: <is><t>…</t></is>
    if is_elem is not None:
        t_elem = is_elem.find(f"{NS}t")
        if t_elem is not None and t_elem.text:
            return t_elem.text
        return ""

    # Shared string reference
    if t == "s" and v is not None and v.text:
        idx = int(v.text)
        if idx < len(shared_strings):
            return shared_strings[idx]
        return ""

    # Inline string via t="inlineStr"
    if t == "inlineStr":
        if is_elem is not None:
            t_elem = is_elem.find(f"{NS}t")
            if t_elem is not None and t_elem.text:
                return t_elem.text
        return ""

    # Number or other
    if v is not None and v.text:
        return v.text
    return ""


def _parse_sheet_xml(xml_bytes):
    """Parse sheet XML bytes into a grid dict {row: {col: value_str}}."""
    ET.register_namespace("", NS[1:-1])
    ET.register_namespace("r", NS_R[1:-1])
    root = ET.fromstring(xml_bytes)
    grid = {}
    sd = root.find(f"{NS}sheetData")
    if sd is None:
        return grid
    for row in sd.iter(f"{NS}row"):
        row_num = int(row.get("r", 0))
        grid[row_num] = {}
        for c in row.iter(f"{NS}c"):
            ref = c.get("r", "")
            if ref:
                rn, cn = _parse_cell_ref(ref)
                grid[row_num][cn] = c
    return grid


def read_timetable_xlsx(zip_data, shared_strings):
    """Read a timetable xlsx and return a schedule dict keyed by day name.

    The timetable layout:
        Row 1 (header):  "Period"  "Ahad"  "Isnin"  "Selasa"  "Rabu"  "Khamis"
        Row 2+:          period_num  code   code     code      code    code

    Returns:
        { day_name: { period_num: { class, start, end, subject, tingkatan } } }
    """
    rid_to_target = _parse_sheet_rels(zip_data)
    sheet_map = _parse_sheet_names(zip_data, rid_to_target)

    # Use the first sheet (or the one named "Sheet1" / "Timetable")
    target_path = next(iter(sheet_map.values()))
    for name, tgt in sheet_map.items():
        if "timetable" in name.lower() or "sheet" in name.lower():
            target_path = tgt
            break

    grid = _parse_sheet_xml(zip_data[target_path])
    if not grid:
        return {}

    # --- Locate header row and map column indices to day names ---
    header_row = None
    day_col_map = {}  # col_index → day_name
    for row_num in sorted(grid.keys()):
        cells = grid[row_num]
        for col_num, cell_elem in cells.items():
            val = _read_cell_value(cell_elem, shared_strings).strip()
            if val in DAY_ORDER:
                day_col_map[col_num] = val
                if header_row is None:
                    header_row = row_num

    if header_row is None or not day_col_map:
        return {}

    # --- Parse data rows ---
    schedule = defaultdict(dict)
    for row_num in sorted(grid.keys()):
        if row_num <= header_row:
            continue
        cells = grid[row_num]
        if not cells:
            continue

        # Find period number: first numeric cell value
        period_num = None
        for col_num in sorted(cells.keys()):
            val = _read_cell_value(cells[col_num], shared_strings).strip()
            try:
                period_num = int(val)
                break
            except (ValueError, TypeError):
                continue

        if period_num is None or period_num not in const.PERIOD_TIMES:
            continue

        # Read class codes from day columns
        for day_col, day_name in day_col_map.items():
            if day_col not in cells:
                continue
            code = _read_cell_value(cells[day_col], shared_strings).strip()
            if not code or code == "NaN":
                continue

            subject, tingkatan, cls = _parse_class_code(code)
            start, end = const.PERIOD_TIMES[period_num]

            schedule[day_name][period_num] = {
                "class": f"{tingkatan}{cls}",
                "start": start,
                "end": end,
                "subject": subject,
                "tingkatan": tingkatan,
            }

    return schedule


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Relative paths in the config (dskp_auto.file, static dskp files, ...)
    # resolve against the config's own directory first.
    cfg["_config_dir"] = os.path.dirname(os.path.abspath(path))

    fixed = []
    raw = cfg.get("fixed_cells", "")
    if isinstance(raw, str):
        for line in raw.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                sheet, cell_range, value = parts[0], parts[1], "\t".join(parts[2:])
                fixed.append((sheet, cell_range, value))
    cfg["fixed_cells"] = fixed

    # Parse DSKP config: list of {sheet, class, file, selection, col_start}
    raw_dskp = cfg.get("dskp", [])
    if isinstance(raw_dskp, dict):
        raw_dskp = [raw_dskp]
    dskp_list = []
    for entry in raw_dskp:
        if isinstance(entry, dict) and "file" in entry:
            dskp_list.append({
                "sheet": entry.get("sheet"),
                "class": entry.get("class", 1),
                "file": entry["file"],
                "selection": entry.get("selection"),
                "col_start": entry.get("col_start", 2),
            })
    cfg["dskp"] = dskp_list

    return cfg


# ---------------------------------------------------------------------------
# Week / jadual resolution (jadual-minggu.yaml)
# ---------------------------------------------------------------------------

def load_jadual_config(path):
    """Load jadual-minggu.yaml: {jadual: {siri: path}, jadual_siri: {minggu: siri},
    minggu: [{start, minggu, cuti, siri}...]}"""
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg.get("minggu"), list) or not cfg["minggu"]:
        print(f"Error: {path} has no 'minggu' records", file=sys.stderr)
        sys.exit(1)
    cfg["_config_dir"] = os.path.dirname(os.path.abspath(path))
    return cfg


def resolve_week(jadual_cfg, start_date, override=None):
    """Resolve start_date → {'minggu': N, 'siri': S or None} (or None if no config).

    Each record takes effect from its `start` date (a Sunday) until the next
    record. Holiday weeks (`cuti`) and records without a minggu number are
    hard errors — a wrong week would silently fill the wrong DSKP content.
    """
    if jadual_cfg is None:
        if override is None:
            return None
        return {"minggu": int(override), "siri": None}

    def _as_date(value):
        return value.date() if isinstance(value, datetime) else value

    records = sorted(
        (e for e in jadual_cfg.get("minggu") or []
         if isinstance(e, dict) and e.get("start")),
        key=lambda e: _as_date(e["start"]))

    if not records:
        print("Error: jadual config contains no dated minggu records",
              file=sys.stderr)
        sys.exit(1)

    d = start_date.date()
    chosen = None
    for rec in records:
        if _as_date(rec["start"]) <= d:
            chosen = rec
        else:
            break

    if chosen is None:
        print(f"Error: {d} is earlier than the first record in the "
              f"jadual config ({_as_date(records[0]['start'])})",
              file=sys.stderr)
        sys.exit(1)

    if chosen.get("cuti"):
        print(f"Error: {d} falls in a holiday week: {chosen['cuti']} "
              f"(check --date)", file=sys.stderr)
        sys.exit(1)

    minggu = override if override is not None else chosen.get("minggu")
    if minggu is None:
        print(f"Error: jadual record starting {_as_date(chosen['start'])} "
              f"has no 'minggu' number", file=sys.stderr)
        sys.exit(1)
    minggu = int(minggu)

    siri = chosen.get("siri")
    if siri is None:
        per_minggu = jadual_cfg.get("jadual_siri") or {}
        siri = per_minggu.get(minggu, per_minggu.get(str(minggu)))

    return {"minggu": minggu, "siri": siri}


def siri_to_timetable(jadual_cfg, siri):
    """siri number → timetable file path (registered under 'jadual:')."""
    jadual_map = jadual_cfg.get("jadual") or {}
    path = jadual_map.get(siri, jadual_map.get(str(siri)))
    if not path:
        print(f"Error: siri {siri} has no file registered under 'jadual:' "
              f"in the jadual config", file=sys.stderr)
        sys.exit(1)
    return _resolve_path(path, [jadual_cfg.get("_config_dir", _REPO_ROOT),
                                _REPO_ROOT, os.getcwd()])


# ---------------------------------------------------------------------------
# Automatic DSKP entries (timetable + week → two content standards per lesson)
# ---------------------------------------------------------------------------

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
            import gen_dskp as _gen_dskp_mod
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
# MENU sheet filling
# ---------------------------------------------------------------------------

def fill_menu(root, schedule, subject_map, start_date):
    """Fill the MENU sheet tree with schedule data (mutates root)."""
    merges = _get_merge_ranges(root)

    for day_idx, day_name in enumerate(DAY_ORDER):
        day_schedule = schedule.get(day_name, {})
        merged = merge_periods(day_schedule)

        header_row = 5 + day_idx * 10

        if day_idx == 0:
            date_serial = _date_to_excel(start_date)
            r, c = _find_merge_top_left(merges, header_row + 1, 9)
            write_cell(root, _cell_ref(r, c), date_serial)

        for i in range(NUM_PERIODS):
            row = header_row + 1 + i
            entry = merged[i][1] if i < len(merged) else None

            if entry:
                cells = [
                    (3, entry["class"]),
                    (4, _time_with_suffix(entry["start"])),
                    (5, _time_with_suffix(entry["end"])),
                    (6, subject_map.get(entry["subject"], entry["subject"])),
                    (7, int(entry["tingkatan"])),
                ]
                for col, val in cells:
                    wr, wc = _find_merge_top_left(merges, row, col)
                    write_cell(root, _cell_ref(wr, wc), val)
            else:
                for col in range(3, 8):
                    wr, wc = _find_merge_top_left(merges, row, col)
                    write_cell(root, _cell_ref(wr, wc), "")


# ---------------------------------------------------------------------------
# Fixed cells
# ---------------------------------------------------------------------------

def write_fixed_cells(root, fixed_entries):
    merges = _get_merge_ranges(root)
    for _, cell_range, value in fixed_entries:
        top_left = _cell_range_top_left(cell_range)
        row, col = _parse_cell_ref(top_left)
        row, col = _find_merge_top_left(merges, row, col)
        try:
            value = int(value)
        except (ValueError, TypeError):
            pass
        write_cell(root, _cell_ref(row, col), value)


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
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import gen_dskp as _gen_dskp_mod
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
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                import gen_dskp as _gen_dskp_mod
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fill an e-RPH xlsx template with timetable and/or DSKP data")
    parser.add_argument("--xlsx", required=True,
                        help="Path to the target xlsx file")
    parser.add_argument("--timetable-xlsx", default=None,
                        help="Path to the timetable xlsx file")
    parser.add_argument("--csv", default=None,
                        help="Path to the timetable CSV (alternative to --timetable-xlsx)")
    parser.add_argument("--config", default="./erph-config.yaml",
                        help="Path to the config YAML (default: ./erph-config.yaml)")
    parser.add_argument("--jadual-config", default=None,
                        help="Path to jadual-minggu.yaml (minggu → siri → timetable); "
                             "enables week-aware automatic filling")
    parser.add_argument("--minggu", type=int, default=None,
                        help="Override the week number (default: resolved from --date)")
    parser.add_argument("--no-dskp-auto", action="store_true",
                        help="Disable automatic DSKP content-standard filling")
    parser.add_argument("--date",
                        help="Week start date YYYY-MM-DD "
                             "(default: the Sunday of the current week)")
    args = parser.parse_args()

    if not os.path.isfile(args.xlsx):
        print(f"Error: file not found: {args.xlsx}", file=sys.stderr)
        sys.exit(1)

    # --- Resolve the week date (weeks start on Sunday/Ahad) ---
    if args.date:
        try:
            raw_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"Error: invalid --date {args.date!r} (expected YYYY-MM-DD)",
                  file=sys.stderr)
            sys.exit(1)
    else:
        raw_date = datetime.now()
    start_date = _sunday_of(raw_date).replace(hour=0, minute=0, second=0,
                                              microsecond=0)

    # --- Week number / siri from jadual-minggu.yaml ---
    jadual_cfg = None
    if args.jadual_config:
        if not os.path.isfile(args.jadual_config):
            print(f"Error: file not found: {args.jadual_config}", file=sys.stderr)
            sys.exit(1)
        jadual_cfg = load_jadual_config(args.jadual_config)
    week = resolve_week(jadual_cfg, start_date, args.minggu)

    cfg = load_config(args.config)

    # --- Timetable source: explicit flag wins, else siri from the week ---
    if args.timetable_xlsx:
        tt_path, tt_is_csv = args.timetable_xlsx, False
    elif args.csv:
        tt_path, tt_is_csv = args.csv, True
    elif week is not None and week.get("siri") is not None:
        tt_path = siri_to_timetable(jadual_cfg, week["siri"])
        tt_is_csv = tt_path.lower().endswith(".csv")
    else:
        tt_path, tt_is_csv = None, False

    if (jadual_cfg is not None and not tt_path
            and week.get("siri") is None):
        print(f"Error: minggu {week['minggu']} has no siri configured yet "
              f"(fill in jadual_siri in {args.jadual_config}, or pass "
              f"--timetable-xlsx/--csv)", file=sys.stderr)
        sys.exit(1)

    if not tt_path and not cfg.get("dskp"):
        parser.error("Nothing to do: provide --timetable-xlsx, --csv or "
                     "--jadual-config, or add dskp entries to the config")

    if tt_path and not os.path.isfile(tt_path):
        print(f"Error: file not found: {tt_path}", file=sys.stderr)
        sys.exit(1)

    zip_data = _read_zip(args.xlsx)
    rid_to_target = _parse_sheet_rels(zip_data)
    sheet_map = _parse_sheet_names(zip_data, rid_to_target)

    missing = [s for s in REQUIRED_SHEETS if s not in sheet_map]
    if missing:
        print(f"Error: missing sheets: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    # --- Build schedule (optional) ---
    schedule = {}
    if tt_path and tt_is_csv:
        schedule = build_schedule(read_csv(tt_path))
    elif tt_path:
        tt_zip = _read_zip(tt_path)
        shared_strings = _read_shared_strings(tt_zip)
        schedule = read_timetable_xlsx(tt_zip, shared_strings)

    if week is not None:
        siri_txt = week["siri"] if week.get("siri") is not None else "-"
        print(f"Week: minggu {week['minggu']}, siri {siri_txt}"
              + (f" ({tt_path})" if tt_path else ""))

    # --- Automatic DSKP entries: two parent sections per BC lesson ---
    auto_report = []
    if schedule and week is not None and not args.no_dskp_auto:
        auto_entries, auto_report = build_auto_dskp_entries(
            schedule, week["minggu"], cfg)
        cfg["dskp"] = cfg.get("dskp", []) + auto_entries
        for line in auto_report:
            print(line)
    elif schedule and week is None and not args.no_dskp_auto:
        # Without a week number there is no section pair to pick — say so
        # instead of silently writing nothing.
        if schedule_has_auto_match(schedule, cfg):
            print("Note: automatic DSKP filling skipped (no week known) — "
                  "add --jadual-config or --minggu N to enable it")

    subject_map = cfg.get("subjects", {})

    # --- Fill MENU sheet (if schedule available) ---
    if schedule:
        menu_path = sheet_map["MENU"]
        menu_root = _parse_sheet(zip_data[menu_path])
        fill_menu(menu_root, schedule, subject_map, start_date)
        zip_data[menu_path] = ET.tostring(menu_root, xml_declaration=True,
                                          encoding="UTF-8", short_empty_elements=False)

    # --- Write fixed cells (grouped by sheet) ---
    fixed_by_sheet = defaultdict(list)
    for sheet_name, cell_range, value in cfg.get("fixed_cells", []):
        if sheet_name not in sheet_map:
            print(f"  Warning: sheet '{sheet_name}' not found, skipping",
                  file=sys.stderr)
            continue
        fixed_by_sheet[sheet_name].append((sheet_name, cell_range, value))

    for sheet_name, entries in fixed_by_sheet.items():
        path = sheet_map[sheet_name]
        root = _parse_sheet(zip_data[path])
        write_fixed_cells(root, entries)
        zip_data[path] = ET.tostring(root, xml_declaration=True,
                                     encoding="UTF-8", short_empty_elements=False)

    # --- Fill DSKP cells (static config entries first, then auto entries) ---
    dskp_configs = cfg.get("dskp", [])
    if dskp_configs:
        fill_dskp_sheets(zip_data, sheet_map, dskp_configs)

    # --- Rewrite zip ---
    with zipfile.ZipFile(args.xlsx, "w",
                         compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in zip_data.items():
            zf.writestr(name, data)

    print(f"Done: {args.xlsx}")


if __name__ == "__main__":
    main()
