"""Fill an e-RPH xlsx template with timetable data.

Bypasses openpyxl — reads/writes the xlsx zip directly and uses
xml.etree.ElementTree to surgically patch cell values while
preserving every original attribute (style, type, etc.).

Usage:
    python fill-erph.py --xlsx <template.xlsx> --timetable-xlsx <timetable.xlsx> [--config <config.yaml>] [--date YYYY-MM-DD]
    python fill-erph.py --xlsx <template.xlsx> --csv <timetable.csv> [--config <config.yaml>] [--date YYYY-MM-DD]
"""

import argparse
import csv
import os
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from xml.etree import ElementTree as ET

import yaml

import constants as const

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DAY_ORDER = ["Ahad", "Isnin", "Selasa", "Rabu", "Khamis"]

REQUIRED_SHEETS = ["MENU"] + [d.upper() for d in DAY_ORDER]

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
    schedule = defaultdict(dict)
    for r in rows:
        period = PERIOD_TIMES.get((r["Start Time"], r["End Time"]))
        if period is None:
            continue
        schedule[r["Date"]][period] = {
            "class": r["Class"],
            "start": r["Start Time"],
            "end": r["End Time"],
            "subject": r["Subject"],
            "tingkatan": r["Tingkatan"],
        }
    return schedule


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
        cfg = yaml.safe_load(f)

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
    return cfg


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
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fill an e-RPH xlsx template with timetable data")
    parser.add_argument("--xlsx", required=True,
                        help="Path to the target xlsx file")
    parser.add_argument("--timetable-xlsx", default=None,
                        help="Path to the timetable xlsx file (direct parsing, no CSV needed)")
    parser.add_argument("--csv", default=None,
                        help="Path to the timetable CSV (alternative to --timetable-xlsx)")
    parser.add_argument("--config", default="./erph-config.yaml",
                        help="Path to the config YAML (default: ./erph-config.yaml)")
    parser.add_argument("--date",
                        help="Week start date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    if not os.path.isfile(args.xlsx):
        print(f"Error: file not found: {args.xlsx}", file=sys.stderr)
        sys.exit(1)

    if not args.timetable_xlsx and not args.csv:
        parser.error("Either --timetable-xlsx or --csv is required")

    zip_data = _read_zip(args.xlsx)

    rid_to_target = _parse_sheet_rels(zip_data)
    sheet_map = _parse_sheet_names(zip_data, rid_to_target)

    missing = [s for s in REQUIRED_SHEETS if s not in sheet_map]
    if missing:
        print(f"Error: missing sheets: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    # --- Build schedule from either timetable xlsx or CSV ---
    if args.timetable_xlsx:
        if not os.path.isfile(args.timetable_xlsx):
            print(f"Error: file not found: {args.timetable_xlsx}", file=sys.stderr)
            sys.exit(1)
        tt_zip = _read_zip(args.timetable_xlsx)
        shared_strings = _read_shared_strings(tt_zip)
        schedule = read_timetable_xlsx(tt_zip, shared_strings)
        if not schedule:
            print("Warning: no schedule data found in timetable xlsx",
                  file=sys.stderr)
    else:
        if not os.path.isfile(args.csv):
            print(f"Error: file not found: {args.csv}", file=sys.stderr)
            sys.exit(1)
        rows = read_csv(args.csv)
        schedule = build_schedule(rows)

    cfg = load_config(args.config)
    subject_map = cfg.get("subjects", {})

    if args.date:
        start_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        start_date = datetime.now().replace(hour=0, minute=0, second=0,
                                            microsecond=0)

    # --- Fill MENU sheet ---
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

    # --- Rewrite zip ---
    with zipfile.ZipFile(args.xlsx, "w",
                         compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in zip_data.items():
            zf.writestr(name, data)

    print(f"Done: {args.xlsx}")


if __name__ == "__main__":
    main()
