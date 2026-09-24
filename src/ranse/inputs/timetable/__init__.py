"""Weekly timetable reading (CSV / xlsx) → schedule structures.

This reader recognises the school week's day names (``ALL_DAYS``, Sunday
first) and keeps **every day the source carries** — which days a template
actually has is the fillers' business, declared once by the profile in
``context.days`` (risk 10, defined with the handlers; the reader must not
encode the target workbook's sheet layout, decision 8).

Period times (risk 4 — see DESIGN.md next to this file):

- ``PERIOD_TIMES`` (period → time range) is the built-in fallback table;
- a profile may reference its own table (``inputs.period_times``, a YAML
  file under ``config/period-times/``), which replaces it wholesale;
- the CSV direction (range → period) is *derived* from whichever table is
  active, so the two directions can never drift apart.
"""

import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from xml.etree import ElementTree as ET

import yaml

from ...core.format import (NS, NS_R, parse_sheet_names, parse_sheet_rels,
                            read_shared_strings, read_zip)
from ...core.refs import _parse_cell_ref
from ...errors import ProfileError
from ...model import Lesson, Schedule

# The school week's day names, Sunday first — what the reader *recognises* in
# headers and CSV dates. Selecting the days a template carries is the
# fillers' job (context.days), never this reader's.
ALL_DAYS = ["Ahad", "Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu"]

# Weekday index (Monday-first, datetime.weekday()) → day name; the school
# week starts on Sunday.
DAY_BY_WEEKDAY = ["Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"]

# Built-in fallback: period number → (start, end). The values are pinned by
# the golden suite; a profile's `inputs.period_times` replaces this whole
# table (risk 4 — see DESIGN.md next to this file).
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


def _reverse_times(period_times):
    """(start, end) → period — derived, so it can never drift from the table."""
    return {(start, end): period
            for period, (start, end) in period_times.items()}


def load_period_times(path):
    """Load a profile-referenced period table (``inputs.period_times``).

    YAML mapping of ``period → [start, end]``; when present it **replaces**
    the built-in ``PERIOD_TIMES`` table (one source of truth, no merging).
    Shape errors raise :class:`~ranse.errors.ProfileError` (decision 13).
    """
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict) or not cfg:
        raise ProfileError(
            f"{path}: period times must be a mapping of period → [start, end]")
    out = {}
    for key, value in cfg.items():
        try:
            period = int(key)
        except (TypeError, ValueError):
            raise ProfileError(f"{path}: period key {key!r} is not a number")
        if (not isinstance(value, (list, tuple)) or len(value) != 2
                or not all(isinstance(v, str) and v.strip() for v in value)):
            raise ProfileError(
                f"{path}: period {period} must be [start, end] as HH:MM "
                f"strings")
        out[period] = (value[0].strip(), value[1].strip())
    return out

CLASS_CODE_RE = re.compile(r"([A-Z]+)[–-](\d+)([A-Za-z]+)")


# ---------------------------------------------------------------------------
# CSV / schedule helpers
# ---------------------------------------------------------------------------

def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_schedule(rows, period_times=None):
    """Build a Schedule from CSV rows (same shape as read_timetable_xlsx).

    Every weekday the ``Date`` maps to is kept — selecting the days a
    template carries belongs to the fillers (``context.days``).
    """
    period_times = period_times or PERIOD_TIMES
    time_period = _reverse_times(period_times)
    schedule = defaultdict(dict)
    for r in rows:
        period = time_period.get((r["Start Time"], r["End Time"]))
        if period is None:
            continue
        day = _day_name_from_date(r.get("Date", ""))
        if day is None:
            print(f"  Warning: cannot read day from Date={r.get('Date')!r}, skipping row",
                  file=sys.stderr)
            continue
        schedule[day][period] = Lesson(
            cls=r["Class"],
            start=r["Start Time"],
            end=r["End Time"],
            subject=r["Subject"],
            form=r["Tingkatan"],
        )
    return Schedule(days=dict(schedule))


def load_schedule(path, period_times=None):
    """Read a timetable file (``.csv`` or ``.xlsx``) into a Schedule."""
    if str(path).lower().endswith(".csv"):
        return build_schedule(read_csv(path), period_times=period_times)
    zip_data = read_zip(path)
    return read_timetable_xlsx(zip_data, read_shared_strings(zip_data),
                               period_times=period_times)


def _day_name_from_date(value):
    """Date string → the school day's name. Returns None if unparseable."""
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


def read_timetable_xlsx(zip_data, shared_strings, period_times=None):
    """Read a timetable xlsx and return a schedule dict keyed by day name.

    The timetable layout:
        Row 1 (header):  "Period"  "Ahad"  "Isnin"  "Selasa"  "Rabu"  "Khamis"
        Row 2+:          period_num  code   code     code      code    code

    Returns:
        Schedule — { day_name: { period_num: Lesson } }
    """
    period_times = period_times or PERIOD_TIMES
    rid_to_target = parse_sheet_rels(zip_data)
    sheet_map = parse_sheet_names(zip_data, rid_to_target)

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
            if val in ALL_DAYS:
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

        if period_num is None or period_num not in period_times:
            continue

        # Read class codes from day columns
        for day_col, day_name in day_col_map.items():
            if day_col not in cells:
                continue
            code = _read_cell_value(cells[day_col], shared_strings).strip()
            if not code or code == "NaN":
                continue

            subject, form, cls = _parse_class_code(code)
            start, end = period_times[period_num]

            schedule[day_name][period_num] = Lesson(
                cls=f"{form}{cls}",
                start=start,
                end=end,
                subject=subject,
                form=form,
            )

    return Schedule(days=dict(schedule))
