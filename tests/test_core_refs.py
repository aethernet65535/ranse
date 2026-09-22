"""Cell-reference / date helpers (target home: src/ranse/core/refs.py)."""

from datetime import datetime

from harness import fn

_col_to_num = fn("_col_to_num")
_col_letter = fn("_col_letter")
_parse_cell_ref = fn("_parse_cell_ref")
_cell_range_top_left = fn("_cell_range_top_left")
_date_to_excel = fn("_date_to_excel")


def test_col_to_num():
    assert _col_to_num("A") == 1
    assert _col_to_num("Z") == 26
    assert _col_to_num("AA") == 27
    assert _col_to_num("a") == 1  # lowercase tolerated


def test_col_letter():
    assert _col_letter(1) == "A"
    assert _col_letter(26) == "Z"
    assert _col_letter(27) == "AA"


def test_col_roundtrip():
    for n in (1, 2, 25, 26, 27, 52, 53, 702, 703, 16384):
        assert _col_to_num(_col_letter(n)) == n


def test_parse_cell_ref():
    assert _parse_cell_ref("A1") == (1, 1)
    assert _parse_cell_ref("C6") == (6, 3)
    assert _parse_cell_ref("AA100") == (100, 27)


def test_parse_cell_ref_roundtrip():
    for ref in ("B3", "Z26", "AB42", "ZZ999"):
        row, col = _parse_cell_ref(ref)
        assert _col_letter(col) + str(row) == ref


def test_cell_range_top_left():
    assert _cell_range_top_left("B3:C3") == "B3"
    assert _cell_range_top_left("D10") == "D10"


def test_cell_range_top_left_unparsable_passes_through():
    # no leading <COL><ROW> → returned unchanged (the `if m else` branch)
    assert _cell_range_top_left("bad") == "bad"


def test_date_to_excel_epoch():
    assert _date_to_excel(datetime(1899, 12, 30)) == 0
    assert _date_to_excel(datetime(1900, 1, 1)) == 2
    assert _date_to_excel(datetime(2026, 9, 20)) == 46285
