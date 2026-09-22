"""Profile/config YAML loading (moved verbatim from fill-erph.py, stage 1)."""

import os
import sys

import yaml


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Relative paths in the config (dskp_auto.file, static dskp files, ...)
    # resolve against the config's own directory first.
    cfg["_config_dir"] = os.path.dirname(os.path.abspath(path))

    fixed = []
    raw = cfg.get("fixed_cells", "")
    if isinstance(raw, str):
        for line in raw.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                sheet, cell_range, value = parts[0], parts[1], "\t".join(parts[2:])
                fixed.append((sheet, cell_range, value))
    cfg["fixed_cells"] = fixed

    # Parse DSKP config: list of {sheet, class, file, selection, col_start}
    raw_dskp = cfg.get("dskp", [])
    if isinstance(raw_dskp, dict):
        raw_dskp = [raw_dskp]
    dskp_list = []
    for entry in raw_dskp:
        if isinstance(entry, dict) and "file" in entry:
            dskp_list.append({
                "sheet": entry.get("sheet"),
                "class": entry.get("class", 1),
                "file": entry["file"],
                "selection": entry.get("selection"),
                "col_start": entry.get("col_start", 2),
            })
    cfg["dskp"] = dskp_list

    return cfg


def load_jadual_config(path):
    """Load jadual-minggu.yaml: {jadual: {siri: path}, jadual_siri: {minggu: siri},
    minggu: [{start, minggu, cuti, siri}...]}"""
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg.get("minggu"), list) or not cfg["minggu"]:
        print(f"Error: {path} has no 'minggu' records", file=sys.stderr)
        sys.exit(1)
    cfg["_config_dir"] = os.path.dirname(os.path.abspath(path))
    return cfg
