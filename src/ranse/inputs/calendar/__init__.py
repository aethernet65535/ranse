"""School-calendar YAML (jadual-minggu) → plain dict.

The shipped example's calendar format — one folder per source format
(``inputs/README.md``). The schema is contract, documented with the data
file it reads: ``config/jadual-minggu/DESIGN.md``. It is a pure input: it
never touches the target workbook (decision 8).
"""

import os

import yaml

from ...errors import ProfileError


def load_jadual_config(path):
    """Load jadual-minggu.yaml: {jadual: {siri: path}, jadual_siri: {minggu: siri},
    minggu: [{start, minggu, cuti, siri}...]}"""
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise ProfileError(f"{path} has no 'minggu' records")
    if not isinstance(cfg.get("minggu"), list) or not cfg["minggu"]:
        raise ProfileError(f"{path} has no 'minggu' records")
    cfg["_config_dir"] = os.path.dirname(os.path.abspath(path))
    return cfg
