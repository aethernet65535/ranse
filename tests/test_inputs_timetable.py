"""Timetable input parsing: class codes, day coverage, period tables."""

from harness import fn

_parse_class_code = fn("_parse_class_code")
build_schedule = fn("build_schedule")
load_period_times = fn("load_period_times")
ProfileError = fn("ProfileError")


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


# --- day coverage (risk 10: the reader keeps every day the source has) -----

def _csv_row(date, **overrides):
    row = {"Start Time": "07:40", "End Time": "08:20", "Date": date,
           "Class": "1E", "Subject": "BC", "Tingkatan": "1"}
    row.update(overrides)
    return row


def test_build_schedule_keeps_every_weekday():
    # 2026-09-25 is a Friday: the reader must keep it — which days a
    # template carries is the fillers' business (context.days), not its.
    schedule = build_schedule([_csv_row("2026-09-25")])
    assert schedule.days["Jumaat"][1].cls == "1E"


def test_build_schedule_maps_dates_to_day_names():
    # 2026-09-20 is a Sunday (school weeks start Ahad)
    schedule = build_schedule([_csv_row("2026-09-20")])
    assert schedule.days["Ahad"][1].start == "07:40"


# --- period tables ---------------------------------------------------------

def test_build_schedule_uses_the_builtin_table_by_default():
    schedule = build_schedule([_csv_row("2026-09-20")])
    assert schedule.days["Ahad"][1].end == "08:20"
    # A time outside the built-in table is skipped.
    skipped = build_schedule([_csv_row("2026-09-20",
                                       **{"Start Time": "08:00",
                                          "End Time": "08:30"})])
    assert not skipped.days


def test_build_schedule_accepts_a_replacement_table():
    custom = {1: ("08:00", "08:30")}
    schedule = build_schedule(
        [_csv_row("2026-09-20",
                  **{"Start Time": "08:00", "End Time": "08:30"})],
        period_times=custom)
    assert schedule.days["Ahad"][1].start == "08:00"


def test_load_period_times_round_trip(tmp_path):
    path = tmp_path / "pt.yaml"
    path.write_text(
        "1: [\"07:40\", \"08:20\"]\n2: [\"08:20\", \"09:00\"]\n",
        encoding="utf-8")
    assert load_period_times(str(path)) == {1: ("07:40", "08:20"),
                                            2: ("08:20", "09:00")}


def test_shipped_period_times_match_the_builtin_table(tmp_path):
    from harness import REPO_ROOT
    shipped = load_period_times(
        str(REPO_ROOT / "config" / "period-times" / "period-times.yaml"))
    PERIOD_TIMES = fn("PERIOD_TIMES")
    assert shipped == PERIOD_TIMES


def test_load_period_times_rejects_a_non_mapping(tmp_path):
    import pytest
    path = tmp_path / "pt.yaml"
    path.write_text("- [\"07:40\", \"08:20\"]\n", encoding="utf-8")
    with pytest.raises(ProfileError) as exc:
        load_period_times(str(path))
    assert "mapping of period" in str(exc.value)


def test_load_period_times_rejects_a_bad_value(tmp_path):
    import pytest
    path = tmp_path / "pt.yaml"
    path.write_text("1: \"07:40\"\n", encoding="utf-8")
    with pytest.raises(ProfileError) as exc:
        load_period_times(str(path))
    assert "period 1" in str(exc.value)


def test_load_period_times_rejects_a_non_numeric_key(tmp_path):
    import pytest
    path = tmp_path / "pt.yaml"
    path.write_text("one: [\"07:40\", \"08:20\"]\n", encoding="utf-8")
    with pytest.raises(ProfileError) as exc:
        load_period_times(str(path))
    assert "not a number" in str(exc.value)
