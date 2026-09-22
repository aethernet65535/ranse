"""Week resolution: cuti / no-minggu / out-of-range errors (DESIGN.md stage 0).

All error assertions match substrings of the CURRENT wording; DESIGN.md scope
item "do not reword error messages" guarantees the wording survives the refactor.
Stage 3 changed the return value from a dict to the ``Week`` dataclass.
"""

from datetime import date, datetime

from harness import call_error, fn

resolve_week = fn("resolve_week")
Week = fn("Week")

CUTI = {"start": date(2026, 1, 1), "cuti": "CUTI A.TAHUN 2026"}
WK1 = {"start": date(2026, 1, 11), "minggu": 1}
WK2 = {"start": date(2026, 1, 18), "minggu": 2}


def jadual(**overrides):
    cfg = {"minggu": [CUTI, WK1, WK2],
           "jadual_siri": {1: 1, 2: 7},
           "_config_dir": "/nowhere"}
    cfg.update(overrides)
    return cfg


# --- no config -------------------------------------------------------------

def test_no_config_without_override():
    assert resolve_week(None, datetime(2026, 9, 20)) is None


def test_no_config_with_override():
    assert resolve_week(None, datetime(2026, 9, 20), 33) == Week(
        minggu=33, siri=None)


# --- normal resolution -----------------------------------------------------

def test_resolves_minggu_and_siri():
    assert resolve_week(jadual(), datetime(2026, 1, 18)) == Week(
        minggu=2, siri=7)


def test_record_stays_in_effect_until_the_next_one():
    # 2026-01-19 (a Monday) still belongs to the record starting 2026-01-18
    assert resolve_week(jadual(), datetime(2026, 1, 19)).minggu == 2


def test_record_siri_overrides_jadual_siri():
    cfg = jadual(minggu=[CUTI, WK1,
                         {"start": date(2026, 1, 18), "minggu": 2,
                          "siri": 3}])
    assert resolve_week(cfg, datetime(2026, 1, 18)) == Week(minggu=2, siri=3)


def test_missing_siri_lookup_yields_none():
    assert resolve_week(jadual(jadual_siri={}),
                        datetime(2026, 1, 18)) == Week(minggu=2, siri=None)


def test_override_replaces_minggu_and_siri_is_looked_up_for_it():
    cfg = jadual(jadual_siri={1: 1, 2: 7, 5: 5})
    assert resolve_week(cfg, datetime(2026, 1, 18), override=5) == Week(
        minggu=5, siri=5)


# --- error paths -----------------------------------------------------------

def test_cuti_week_is_an_error():
    msg = call_error(resolve_week, jadual(), datetime(2026, 1, 4))
    assert "holiday week" in msg
    assert "CUTI A.TAHUN 2026" in msg


def test_date_before_first_record_is_an_error():
    msg = call_error(resolve_week, jadual(), datetime(2025, 12, 28))
    assert "earlier than the first record" in msg


def test_record_without_minggu_is_an_error():
    cfg = jadual(minggu=[CUTI, WK1, {"start": date(2026, 1, 18)}])
    msg = call_error(resolve_week, cfg, datetime(2026, 1, 18))
    assert "no 'minggu' number" in msg


def test_no_dated_records_is_an_error():
    msg = call_error(resolve_week, jadual(minggu=[]), datetime(2026, 1, 18))
    assert "no dated minggu records" in msg
