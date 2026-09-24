"""Calendar reader: schema errors surface as ProfileError (decision 13)."""

import pytest

from harness import fn

load_calendar_config = fn("load_calendar_config")
ProfileError = fn("ProfileError")


def test_missing_week_records_is_a_profile_error(tmp_path):
    path = tmp_path / "cal.yaml"
    path.write_text("jadual: {}\n", encoding="utf-8")
    with pytest.raises(ProfileError) as exc:
        load_calendar_config(str(path))
    assert "has no 'minggu' records" in str(exc.value)


def test_non_mapping_yaml_is_a_profile_error(tmp_path):
    path = tmp_path / "cal.yaml"
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ProfileError) as exc:
        load_calendar_config(str(path))
    assert "has no 'minggu' records" in str(exc.value)


def test_config_dir_is_added_next_to_the_file(tmp_path):
    path = tmp_path / "cal.yaml"
    path.write_text("minggu:\n  - {start: 2026-01-01}\n", encoding="utf-8")
    cfg = load_calendar_config(str(path))
    assert cfg["_config_dir"] == str(tmp_path)
