"""School-calendar YAML (school-weeks) → plain dict.

The shipped example's calendar format — one folder per source format
(``inputs/README.md``). The schema is contract, documented with the data
file it reads: ``config/school-weeks/DESIGN.md``. It is a pure input: it
never touches the target workbook (decision 8).
"""

import os

import yaml

from ranse.errors import ProfileError


def load_calendar_config(path):
    """Load school-weeks.yaml: {timetable: {series: path},
    week_series: {week: series}, weeks: [{start, week, holiday, series}...]}"""
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise ProfileError(f"{path} has no 'weeks' records")
    if not isinstance(cfg.get("weeks"), list) or not cfg["weeks"]:
        raise ProfileError(f"{path} has no 'weeks' records")
    cfg["_config_dir"] = os.path.dirname(os.path.abspath(path))
    return cfg
