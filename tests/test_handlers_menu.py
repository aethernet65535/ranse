"""MENU handler behaviour: period merging + time suffixes.

Lessons are ``Lesson`` dataclasses, so the expectations below are built from
``Lesson`` too (``entry.cls`` rather than a dict key).
"""

from harness import fn

merge_periods = fn("merge_periods")
_time_with_suffix = fn("_time_with_suffix")
Lesson = fn("Lesson")


def _entry(start, end, **overrides):
    fields = {"cls": "1E", "subject": "BC", "form": "1",
              "start": start, "end": end}
    fields.update(overrides)
    return Lesson(**fields)


def test_merge_empty_day():
    assert merge_periods({}) == []


def test_merge_contiguous_same_lesson():
    day = {1: _entry("07:40", "08:20"), 2: _entry("08:20", "09:00")}
    assert merge_periods(day) == [(1, _entry("07:40", "09:00"))]


def test_merge_three_periods_into_one_row():
    day = {1: _entry("07:40", "08:20"),
           2: _entry("08:20", "09:00"),
           3: _entry("09:00", "09:40")}
    merged = merge_periods(day)
    assert len(merged) == 1
    start, entry = merged[0]
    assert start == 1
    assert (entry.start, entry.end) == ("07:40", "09:40")


def test_no_merge_when_time_not_contiguous():
    # same lesson but a gap between periods → two rows
    # (risk 4, src/ranse/inputs/timetable/DESIGN.md)
    day = {1: _entry("07:40", "08:20"), 3: _entry("09:00", "09:40")}
    assert [p for p, _ in merge_periods(day)] == [1, 3]


def test_no_merge_different_class():
    day = {1: _entry("07:40", "08:20"),
           2: _entry("08:20", "09:00", cls="2E")}
    assert [p for p, _ in merge_periods(day)] == [1, 2]


def test_no_merge_different_subject():
    day = {1: _entry("07:40", "08:20"),
           2: _entry("08:20", "09:00", subject="BI")}
    assert [p for p, _ in merge_periods(day)] == [1, 2]


def test_no_merge_different_form():
    day = {1: _entry("07:40", "08:20"),
           2: _entry("08:20", "09:00", form="2")}
    assert [p for p, _ in merge_periods(day)] == [1, 2]


def test_merge_splits_then_resumes():
    # A A B A → two runs of A around B
    day = {1: _entry("07:40", "08:20"),
           2: _entry("08:20", "09:00"),
           3: _entry("09:00", "09:40", subject="BI"),
           4: _entry("09:40", "10:20")}
    merged = merge_periods(day)
    assert [(p, e.subject) for p, e in merged] == [(1, "BC"), (3, "BI"),
                                                   (4, "BC")]


def test_time_suffix_day_part_boundaries():
    # PAGI → TGH at 11:00, TGH → TPTG at 14:00 (menu/DESIGN.md, risk 11)
    assert _time_with_suffix("10:00") == "10:00 PAGI"
    assert _time_with_suffix("11:00") == "11:00 TGH"
    assert _time_with_suffix("13:00") == "13:00 TGH"
    assert _time_with_suffix("14:00") == "14:00 TPTG"
    assert _time_with_suffix("23:00") == "23:00 TPTG"


def test_time_suffix_minute_times_fall_back_to_pagi():
    # Current behaviour, pinned on purpose: only HH:00 keys are cached, every
    # other time falls back to "PAGI" (e.g. the template really contains
    # "11:30 PAGI"). Golden output depends on it — do not "fix" silently.
    assert _time_with_suffix("07:40") == "07:40 PAGI"
    assert _time_with_suffix("11:30") == "11:30 PAGI"
    assert _time_with_suffix("14:10") == "14:10 PAGI"
