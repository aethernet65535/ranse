"""Xlsx zip container read + surgical cell-write primitives.

Write-only towards the target workbook (PLAN.md decision 7): there is no
``read(coord)``. Serialization details (attribute preservation, inline
strings, namespace prefixes, xml declaration flags) must stay byte-identical
— the golden regression suite checks exactly that (PLAN.md risk 1-2).
"""

import re
import zipfile
from xml.etree import ElementTree as ET

from .refs import _parse_cell_ref

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


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
