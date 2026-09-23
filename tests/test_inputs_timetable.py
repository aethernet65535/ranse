"""Timetable input parsing."""

from harness import fn

_parse_class_code = fn("_parse_class_code")


def test_parse_class_code_ascii_hyphen():
    assert _parse_class_code("BC-1A") == ("BC", "1", "A")


def test_parse_class_code_en_dash():
    # timetable exports use an en dash instead of '-'
    assert _parse_class_code("BC–1A") == ("BC", "1", "A")


def test_parse_class_code_multi_letter_subject():
    assert _parse_class_code("MATH-5C") == ("MATH", "5", "C")


def test_parse_class_code_two_digit_tingkatan():
    assert _parse_class_code("BC-10A") == ("BC", "10", "A")


def test_parse_class_code_non_matching_returns_input_unchanged():
    assert _parse_class_code("BIOLOGI") == ("BIOLOGI", "", "")
    assert _parse_class_code("Pendidikan Islam") == ("Pendidikan Islam", "", "")
    assert _parse_class_code("") == ("", "", "")
