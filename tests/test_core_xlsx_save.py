"""``Workbook.save`` must never leave a half-written workbook behind.

The pipeline overwrites the workbook in place, so a run interrupted while the
zip is being written (Ctrl+C, a crash) must leave the previous, complete
workbook on disk.
"""

import zipfile

import pytest

from ranse.core.xlsx import Workbook

_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"

WORKBOOK_XML = (
    f'<workbook xmlns="{_MAIN}" xmlns:r="{_R}">'
    '<sheets><sheet name="S1" sheetId="1" r:id="rId1"/></sheets></workbook>')
RELS_XML = (
    f'<Relationships xmlns="{_PKG}">'
    '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
SHEET_XML = f'<worksheet xmlns="{_MAIN}"><sheetData/></worksheet>'


def _tiny_xlsx(path):
    """A minimal workbook: one empty sheet, no styles or shared strings."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/workbook.xml", WORKBOOK_XML)
        zf.writestr("xl/_rels/workbook.xml.rels", RELS_XML)
        zf.writestr("xl/worksheets/sheet1.xml", SHEET_XML)
    return path


def _names(directory):
    return sorted(p.name for p in directory.iterdir())


def test_save_rewrites_the_target_without_leaving_a_temp_file(tmp_path):
    target = _tiny_xlsx(tmp_path / "t.xlsx")
    wb = Workbook.open(str(target))
    wb.sheet("S1").write("A1", "hello")
    wb.save()

    sheet = zipfile.ZipFile(target).read("xl/worksheets/sheet1.xml")
    assert b"hello" in sheet
    assert _names(tmp_path) == ["t.xlsx"]


def test_interrupted_save_keeps_the_previous_workbook(tmp_path, monkeypatch):
    target = _tiny_xlsx(tmp_path / "t.xlsx")
    before = target.read_bytes()
    wb = Workbook.open(str(target))
    wb.sheet("S1").write("A1", "hello")

    writes = {"n": 0}
    real_writestr = zipfile.ZipFile.writestr

    def interrupt(self, name, data):
        writes["n"] += 1
        if writes["n"] == 2:
            raise KeyboardInterrupt  # what Ctrl+C raises mid-write
        return real_writestr(self, name, data)

    monkeypatch.setattr(zipfile.ZipFile, "writestr", interrupt)
    with pytest.raises(KeyboardInterrupt):
        wb.save()

    assert target.read_bytes() == before
    assert _names(tmp_path) == ["t.xlsx"]
