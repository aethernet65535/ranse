"""Week resolution: holiday weeks / missing week numbers / out-of-range errors.

All error assertions match substrings of the current wording, which decision
13 freezes ("do not reword error messages"). The resolver returns a ``Week``
dataclass. Fixture dicts keep the calendar file's data keys (`minggu`,
`jadual_siri`, `cuti`) — the schema changes in a later plan phase, the
Python-level names are English now.
"""

from datetime import date, datetime

from harness import call_error, fn

resolve_week = fn("resolve_week")
Week = fn("Week")

HOLIDAY = {"start": date(2026, 1, 1), "cuti": "CUTI A.TAHUN 2026"}
WK1 = {"start": date(2026, 1, 11), "minggu": 1}
WK2 = {"start": date(2026, 1, 18), "minggu": 2}


def calendar_cfg(**overrides):
    cfg = {"minggu": [HOLIDAY, WK1, WK2],
           "jadual_siri": {1: 1, 2: 7},
           "_config_dir": "/nowhere"}
    cfg.update(overrides)
    return cfg


# --- no config -------------------------------------------------------------

def test_no_config_without_override():
    assert resolve_week(None, datetime(2026, 9, 20)) is None


def test_no_config_with_override():
    assert resolve_week(None, datetime(2026, 9, 20), 33) == Week(
        number=33, series=None)


# --- normal resolution -----------------------------------------------------

def test_resolves_number_and_series():
    assert resolve_week(calendar_cfg(), datetime(2026, 1, 18)) == Week(
        number=2, series=7)


def test_record_stays_in_effect_until_the_next_one():
    # 2026-01-19 (a Monday) still belongs to the record starting 2026-01-18
    assert resolve_week(calendar_cfg(), datetime(2026, 1, 19)).number == 2


def test_record_series_overrides_the_series_table():
    cfg = calendar_cfg(minggu=[HOLIDAY, WK1,
                               {"start": date(2026, 1, 18), "minggu": 2,
                                "siri": 3}])
    assert resolve_week(cfg, datetime(2026, 1, 18)) == Week(number=2,
                                                             series=3)


def test_missing_series_lookup_yields_none():
    assert resolve_week(calendar_cfg(jadual_siri={}),
                        datetime(2026, 1, 18)) == Week(number=2, series=None)


def test_override_replaces_the_number_and_series_is_looked_up_for_it():
    cfg = calendar_cfg(jadual_siri={1: 1, 2: 7, 5: 5})
    assert resolve_week(cfg, datetime(2026, 1, 18), override=5) == Week(
        number=5, series=5)


# --- error paths -----------------------------------------------------------

def test_holiday_week_is_an_error():
    msg = call_error(resolve_week, calendar_cfg(), datetime(2026, 1, 4))
    assert "holiday week" in msg
    assert "CUTI A.TAHUN 2026" in msg


def test_date_before_first_record_is_an_error():
    msg = call_error(resolve_week, calendar_cfg(), datetime(2025, 12, 28))
    assert "earlier than the first record" in msg


def test_record_without_a_week_number_is_an_error():
    cfg = calendar_cfg(minggu=[HOLIDAY, WK1, {"start": date(2026, 1, 18)}])
    msg = call_error(resolve_week, cfg, datetime(2026, 1, 18))
    assert "no 'minggu' number" in msg


def test_no_dated_records_is_an_error():
    msg = call_error(resolve_week, calendar_cfg(minggu=[]),
                     datetime(2026, 1, 18))
    assert "no dated 'minggu' records" in msg
