"""Weekly timetable reading (CSV / xlsx) → schedule structures.

Both period tables live here (docs/input-formats.md risk 4, values unchanged):

- ``PERIOD_TIMES`` (period → time range) fills the MENU rows;
- ``TIME_PERIOD`` (time range → period) is the CSV direction. The two cannot
  share one name inside this module, so the CSV direction got its own;
  ``build_schedule`` is its only caller.
"""

import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from xml.etree import ElementTree as ET

from ..core.refs import _parse_cell_ref
from ..core.xlsx import (NS, NS_R, _parse_sheet_names, _parse_sheet_rels,
                         _read_shared_strings, _read_zip)
from ..model import Lesson, Schedule

DAY_ORDER = ["Ahad", "Isnin", "Selasa", "Rabu", "Khamis"]

# Monday-first weekday index → Malay day name (same order as DAY_ORDER for
# the school week, which starts on Sunday/Ahad).
DAY_BY_WEEKDAY = ["Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"]

# period number → (start, end)   [was scripts/constants.py]
PERIOD_TIMES = {
    1: ("07:40", "08:20"),
    2: ("08:20", "09:00"),
    3: ("09:00", "09:40"),
    4: ("09:40", "10:20"),
    5: ("10:20", "10:50"),
    6: ("10:50", "11:30"),
    7: ("11:30", "12:10"),
    8: ("12:10", "12:50"),
    9: ("12:50", "13:30"),
    10: ("13:30", "14:10"),
}

# (start, end) → period number   [the CSV direction of the legacy
# PERIOD_TIMES map; renamed because both maps now live in this module]
TIME_PERIOD = {
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

# NUM_PERIODS + the PAGI/TGH/TPTG suffix cache moved to handlers/menu/ in
# stage 2: decision 12 keeps MENU layout constants in the handler.

CLASS_CODE_RE = re.compile(r"([A-Z]+)[–-](\d+)([A-Za-z]+)")


# ---------------------------------------------------------------------------
# CSV / schedule helpers
# ---------------------------------------------------------------------------

def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_schedule(rows):
    """Build a Schedule from CSV rows (same shape as read_timetable_xlsx)."""
    schedule = defaultdict(dict)
    for r in rows:
        period = TIME_PERIOD.get((r["Start Time"], r["End Time"]))
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
        schedule[day][period] = Lesson(
            cls=r["Class"],
            start=r["Start Time"],
            end=r["End Time"],
            subject=r["Subject"],
            tingkatan=r["Tingkatan"],
        )
    return Schedule(days=dict(schedule))


def load_schedule(path):
    """Read a timetable file (``.csv`` or ``.xlsx``) into a Schedule."""
    if str(path).lower().endswith(".csv"):
        return build_schedule(read_csv(path))
    zip_data = _read_zip(path)
    return read_timetable_xlsx(zip_data, _read_shared_strings(zip_data))


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


# ---------------------------------------------------------------------------
# Timetable xlsx reading
# ---------------------------------------------------------------------------

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
        Schedule — { day_name: { period_num: Lesson } }
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

        if period_num is None or period_num not in PERIOD_TIMES:
            continue

        # Read class codes from day columns
        for day_col, day_name in day_col_map.items():
            if day_col not in cells:
                continue
            code = _read_cell_value(cells[day_col], shared_strings).strip()
            if not code or code == "NaN":
                continue

            subject, tingkatan, cls = _parse_class_code(code)
            start, end = PERIOD_TIMES[period_num]

            schedule[day_name][period_num] = Lesson(
                cls=f"{tingkatan}{cls}",
                start=start,
                end=end,
                subject=subject,
                tingkatan=tingkatan,
            )

    return Schedule(days=dict(schedule))
