"""Xlsx format primitives: zip parts, sheet map, shared strings (decision 7).

Format-level only — no business knowledge and no write state. Two kinds of
callers use these:

- the write-only ``Workbook`` / ``Sheet`` in :mod:`ranse.core.xlsx`, which
  build on them to edit the **target** workbook;
- the source readers in ``inputs/``, which parse a **source** workbook
  (e.g. a weekly schedule xlsx) the same way.

Reading through here never violates the write-only rule (D7): that rule is
about the target workbook — nothing in the pipeline reads a value back out
of a workbook ranse wrote. Splitting the read primitives out of
``core/xlsx.py`` keeps that module's public surface exactly
``open / sheets / sheet / write / save``.

``ET.register_namespace`` side effects stay in ``Workbook.open`` (see
``core/xlsx.py``).
"""

import re
import zipfile
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def read_zip(path):
    """Read every entry of a zip file into memory: ``{name: bytes}``."""
    with zipfile.ZipFile(path, "r") as zf:
        return {info.filename: zf.read(info.filename) for info in zf.infolist()}


def parse_sheet_rels(zip_data):
    """``xl/_rels/workbook.xml.rels`` → ``{relationship id: target}``."""
    rels_xml = zip_data.get("xl/_rels/workbook.xml.rels", b"").decode("utf-8")
    rid_to_target = {}
    for m in re.finditer(r'<Relationship([^>]+)/>', rels_xml):
        attrs = dict(re.findall(r'(\w+)="([^"]+)"', m.group(1)))
        rid = attrs.get("Id")
        target = attrs.get("Target")
        if rid and target:
            rid_to_target[rid] = target
    return rid_to_target


def parse_sheet_names(zip_data, rid_to_target):
    """``xl/workbook.xml`` → ``{sheet name: zip path}`` in workbook order."""
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


def read_shared_strings(zip_data):
    """``xl/sharedStrings.xml`` → list of strings (``[]`` when absent)."""
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
