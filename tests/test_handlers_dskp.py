"""DSKP handler: the sliding section pair (DESIGN.md stage 0)."""

from harness import fn

_section_pair = fn("_section_pair")

SECTIONS3 = {"1": {"title": "1.0 Listening and Speaking"},
             "2": {"title": "2.0 Reading"},
             "3": {"title": "3.0 Writing"}}


def test_pair_starts_with_the_first_two_sections():
    assert _section_pair(SECTIONS3, 1) == ("1", "2")


def test_pair_slides_forward_one_section_per_week():
    assert _section_pair(SECTIONS3, 2) == ("2", "3")


def test_pair_wraps_after_the_last_page():
    # week 3 is the last page → back to (1, 2); week 4 slides again
    assert _section_pair(SECTIONS3, 3) == ("1", "2")
    assert _section_pair(SECTIONS3, 4) == ("2", "3")


def test_single_page_never_slides():
    two = {"1": {}, "2": {}}
    assert _section_pair(two, 1) == ("1", "2")
    assert _section_pair(two, 7) == ("1", "2")


def test_too_few_sections_returns_none():
    assert _section_pair({"1": {}}, 1) is None
    assert _section_pair({}, 1) is None


def test_non_dict_returns_none():
    assert _section_pair(None, 1) is None
    assert _section_pair([{"1": {}}], 1) is None


def test_non_numeric_keys_are_ignored():
    mixed = {"meta": {}, "1": {}, "2": {}, "3": {}}
    assert _section_pair(mixed, 2) == ("2", "3")
