"""Write-only Workbook / Sheet API (docs/DESIGN.md decision 7).

Write-only towards the target workbook: there is no ``read(coord)``.
Serialization details (attribute preservation, inline strings, namespace
prefixes, xml declaration flags) must stay byte-identical — the golden
regression suite checks exactly that (docs/DESIGN.md risk 1-2).

The read/format primitives (zip parts, sheet map, shared strings) live in
:mod:`ranse.core.format`; this module's public surface is exactly
``open / sheets / sheet / write / save``.

``ET.register_namespace`` side effects live in ``Workbook.open`` (once per
open) instead of inside every parse; the registered prefixes/URIs must keep
the templates' original prefixes (risk 1).
"""

import os
import tempfile
import zipfile
from xml.etree import ElementTree as ET

from ..errors import SheetError
from .format import (NS, NS_R, parse_sheet_names, parse_sheet_rels,
                     read_shared_strings, read_zip)
from .refs import _cell_range_top_left, _cell_ref, _parse_cell_ref


# ---------------------------------------------------------------------------
# Xlsx zip write
# ---------------------------------------------------------------------------

def _file_mode(target):
    """Mode to give a replaced file: the target's, else the umask default."""
    if os.path.exists(target):
        return os.stat(target).st_mode
    mask = os.umask(0)
    os.umask(mask)
    return 0o666 & ~mask


# ---------------------------------------------------------------------------
# Sheet XML parsing (ElementTree-based)
# ---------------------------------------------------------------------------

def _parse_sheet(xml_bytes):
    """Parse sheet XML bytes → ElementTree root.

    Namespace registration happens in Workbook.open — not here (it must run
    once per open, not per parse).
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise SheetError(f"invalid sheet XML: {exc}") from exc
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
# Public API: Workbook / Sheet (decision 7 — strictly write-only)
# ---------------------------------------------------------------------------

class Workbook:
    """An xlsx opened for writing: open() / sheets / sheet() / save().

    Sheets are parsed lazily on first access, kept in memory, and only the
    sheets that received at least one write() are re-serialized on save() —
    every other zip entry keeps its original bytes (same as the original
    script's behaviour).
    """

    def __init__(self, path, zip_data, sheet_map):
        self._path = path
        self._zip_data = zip_data
        self._sheet_map = sheet_map
        self._roots = {}    # zip path → parsed sheet root
        self._merges = {}   # zip path → merge ranges (structural metadata,
                            # needed to preserve formatting — not a value read)
        self._dirty = set()  # zip paths with at least one write()

    @classmethod
    def open(cls, path):
        """Open the workbook at path (all zip entries are read into memory)."""
        # Register namespaces so serialisation keeps the original prefixes:
        # the prefixes/URIs must stay identical or the golden suite fails
        # (risk 1).
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

        zip_data = read_zip(path)
        rid_to_target = parse_sheet_rels(zip_data)
        sheet_map = parse_sheet_names(zip_data, rid_to_target)
        return cls(path, zip_data, sheet_map)

    @property
    def sheets(self):
        """Sheet names in workbook order."""
        return list(self._sheet_map)

    def write(self, ref, content):
        """Write one cell addressed as ``"SHEET!COORD"`` (decision 9).

        ``ref`` is ``"SHEET!B3"`` or ``"SHEET!B3:C3"`` — a range / merged
        range writes its top-left cell, exactly like :meth:`Sheet.write`.
        """
        sheet_name, sep, coord = str(ref).partition("!")
        if not sep or not coord:
            raise SheetError(
                f"invalid cell reference: {ref!r} (expected SHEET!A1)")
        self.sheet(sheet_name).write(coord, content)

    def sheet(self, name):
        """Return the writable Sheet called name."""
        if name not in self._sheet_map:
            raise SheetError(f"missing sheet: {name!r}")
        return Sheet(self, name)

    def save(self, path=None):
        """Write the workbook back (None = overwrite the opened file).

        Only sheets with dirty state are re-serialized; every other zip
        entry is copied through byte-for-byte.

        The zip is built in a temporary file next to the target and renamed
        into place, so an interrupted run (Ctrl+C, a crash) leaves the target
        workbook as it was instead of half-written.
        """
        target = self._path if path is None else str(path)
        directory = os.path.dirname(os.path.abspath(target)) or "."
        handle, tmp = tempfile.mkstemp(dir=directory, prefix=".ranse-",
                                       suffix=".tmp")
        os.close(handle)
        try:
            with zipfile.ZipFile(tmp, "w",
                                 compression=zipfile.ZIP_DEFLATED) as zf:
                for name, data in self._zip_data.items():
                    if name in self._dirty:
                        data = ET.tostring(self._roots[name],
                                           xml_declaration=True,
                                           encoding="UTF-8",
                                           short_empty_elements=False)
                    zf.writestr(name, data)
            os.chmod(tmp, _file_mode(target))
            os.replace(tmp, target)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    # -- internal helpers used by Sheet ------------------------------------
    def _root(self, zip_path):
        if zip_path not in self._roots:
            self._roots[zip_path] = _parse_sheet(self._zip_data[zip_path])
        return self._roots[zip_path]

    def _merges_for(self, zip_path, root):
        if zip_path not in self._merges:
            self._merges[zip_path] = _get_merge_ranges(root)
        return self._merges[zip_path]


class Sheet:
    """A single writable sheet: write(coord, content) + merges()."""

    def __init__(self, workbook, name):
        self._workbook = workbook
        self._name = name
        self._zip_path = workbook._sheet_map[name]

    def write(self, coord, content):
        """Write content to coord ('B3' or 'B3:C3').

        The top-left cell of the coordinate range is used, and if it falls
        inside a merged area the write goes to that area's top-left cell, so
        callers do not have to do the merge lookup by hand.
        """
        top_left = _cell_range_top_left(coord)
        row, col = _parse_cell_ref(top_left)
        root = self._workbook._root(self._zip_path)
        merges = self._workbook._merges_for(self._zip_path, root)
        row, col = _find_merge_top_left(merges, row, col)
        write_cell(root, _cell_ref(row, col), content)
        self._workbook._dirty.add(self._zip_path)

    def merges(self):
        """Merged ranges as (min_row, min_col, max_row, max_col) tuples."""
        root = self._workbook._root(self._zip_path)
        return self._workbook._merges_for(self._zip_path, root)
