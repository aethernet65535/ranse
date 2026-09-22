"""Command-line orchestration: argparse + pipeline + exit codes (stage 1 move)."""

import argparse
import os
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from xml.etree import ElementTree as ET

from .core.xlsx import (_parse_sheet, _parse_sheet_names, _parse_sheet_rels,
                        _read_shared_strings, _read_zip)
from .handlers.dskp import (build_auto_dskp_entries, fill_dskp_sheets,
                            schedule_has_auto_match)
from .handlers.fixed_cells import write_fixed_cells
from .handlers.menu import fill_menu
from .handlers.week import _sunday_of, resolve_week, siri_to_timetable
from .inputs.timetable import (DAY_ORDER, build_schedule, read_csv,
                               read_timetable_xlsx)
from .inputs.yaml import load_config, load_jadual_config

REQUIRED_SHEETS = ["MENU"] + [d.upper() for d in DAY_ORDER]


def main():
    parser = argparse.ArgumentParser(
        description="Fill an e-RPH xlsx template with timetable and/or DSKP data")
    parser.add_argument("--xlsx", required=True,
                        help="Path to the target xlsx file")
    parser.add_argument("--timetable-xlsx", default=None,
                        help="Path to the timetable xlsx file")
    parser.add_argument("--csv", default=None,
                        help="Path to the timetable CSV (alternative to --timetable-xlsx)")
    parser.add_argument("--config", default="./erph-config.yaml",
                        help="Path to the config YAML (default: ./erph-config.yaml)")
    parser.add_argument("--jadual-config", default=None,
                        help="Path to jadual-minggu.yaml (minggu → siri → timetable); "
                             "enables week-aware automatic filling")
    parser.add_argument("--minggu", type=int, default=None,
                        help="Override the week number (default: resolved from --date)")
    parser.add_argument("--no-dskp-auto", action="store_true",
                        help="Disable automatic DSKP content-standard filling")
    parser.add_argument("--date",
                        help="Week start date YYYY-MM-DD "
                             "(default: the Sunday of the current week)")
    args = parser.parse_args()

    if not os.path.isfile(args.xlsx):
        print(f"Error: file not found: {args.xlsx}", file=sys.stderr)
        sys.exit(1)

    # --- Resolve the week date (weeks start on Sunday/Ahad) ---
    if args.date:
        try:
            raw_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"Error: invalid --date {args.date!r} (expected YYYY-MM-DD)",
                  file=sys.stderr)
            sys.exit(1)
    else:
        raw_date = datetime.now()
    start_date = _sunday_of(raw_date).replace(hour=0, minute=0, second=0,
                                              microsecond=0)

    # --- Week number / siri from jadual-minggu.yaml ---
    jadual_cfg = None
    if args.jadual_config:
        if not os.path.isfile(args.jadual_config):
            print(f"Error: file not found: {args.jadual_config}", file=sys.stderr)
            sys.exit(1)
        jadual_cfg = load_jadual_config(args.jadual_config)
    week = resolve_week(jadual_cfg, start_date, args.minggu)

    cfg = load_config(args.config)

    # --- Timetable source: explicit flag wins, else siri from the week ---
    if args.timetable_xlsx:
        tt_path, tt_is_csv = args.timetable_xlsx, False
    elif args.csv:
        tt_path, tt_is_csv = args.csv, True
    elif week is not None and week.get("siri") is not None:
        tt_path = siri_to_timetable(jadual_cfg, week["siri"])
        tt_is_csv = tt_path.lower().endswith(".csv")
    else:
        tt_path, tt_is_csv = None, False

    if (jadual_cfg is not None and not tt_path
            and week.get("siri") is None):
        print(f"Error: minggu {week['minggu']} has no siri configured yet "
              f"(fill in jadual_siri in {args.jadual_config}, or pass "
              f"--timetable-xlsx/--csv)", file=sys.stderr)
        sys.exit(1)

    if not tt_path and not cfg.get("dskp"):
        parser.error("Nothing to do: provide --timetable-xlsx, --csv or "
                     "--jadual-config, or add dskp entries to the config")

    if tt_path and not os.path.isfile(tt_path):
        print(f"Error: file not found: {tt_path}", file=sys.stderr)
        sys.exit(1)

    zip_data = _read_zip(args.xlsx)
    rid_to_target = _parse_sheet_rels(zip_data)
    sheet_map = _parse_sheet_names(zip_data, rid_to_target)

    missing = [s for s in REQUIRED_SHEETS if s not in sheet_map]
    if missing:
        print(f"Error: missing sheets: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    # --- Build schedule (optional) ---
    schedule = {}
    if tt_path and tt_is_csv:
        schedule = build_schedule(read_csv(tt_path))
    elif tt_path:
        tt_zip = _read_zip(tt_path)
        shared_strings = _read_shared_strings(tt_zip)
        schedule = read_timetable_xlsx(tt_zip, shared_strings)

    if week is not None:
        siri_txt = week["siri"] if week.get("siri") is not None else "-"
        print(f"Week: minggu {week['minggu']}, siri {siri_txt}"
              + (f" ({tt_path})" if tt_path else ""))

    # --- Automatic DSKP entries: two parent sections per BC lesson ---
    auto_report = []
    if schedule and week is not None and not args.no_dskp_auto:
        auto_entries, auto_report = build_auto_dskp_entries(
            schedule, week["minggu"], cfg)
        cfg["dskp"] = cfg.get("dskp", []) + auto_entries
        for line in auto_report:
            print(line)
    elif schedule and week is None and not args.no_dskp_auto:
        # Without a week number there is no section pair to pick — say so
        # instead of silently writing nothing.
        if schedule_has_auto_match(schedule, cfg):
            print("Note: automatic DSKP filling skipped (no week known) — "
                  "add --jadual-config or --minggu N to enable it")

    subject_map = cfg.get("subjects", {})

    # --- Fill MENU sheet (if schedule available) ---
    if schedule:
        menu_path = sheet_map["MENU"]
        menu_root = _parse_sheet(zip_data[menu_path])
        fill_menu(menu_root, schedule, subject_map, start_date)
        zip_data[menu_path] = ET.tostring(menu_root, xml_declaration=True,
                                          encoding="UTF-8", short_empty_elements=False)

    # --- Write fixed cells (grouped by sheet) ---
    fixed_by_sheet = defaultdict(list)
    for sheet_name, cell_range, value in cfg.get("fixed_cells", []):
        if sheet_name not in sheet_map:
            print(f"  Warning: sheet '{sheet_name}' not found, skipping",
                  file=sys.stderr)
            continue
        fixed_by_sheet[sheet_name].append((sheet_name, cell_range, value))

    for sheet_name, entries in fixed_by_sheet.items():
        path = sheet_map[sheet_name]
        root = _parse_sheet(zip_data[path])
        write_fixed_cells(root, entries)
        zip_data[path] = ET.tostring(root, xml_declaration=True,
                                     encoding="UTF-8", short_empty_elements=False)

    # --- Fill DSKP cells (static config entries first, then auto entries) ---
    dskp_configs = cfg.get("dskp", [])
    if dskp_configs:
        fill_dskp_sheets(zip_data, sheet_map, dskp_configs)

    # --- Rewrite zip ---
    with zipfile.ZipFile(args.xlsx, "w",
                         compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in zip_data.items():
            zf.writestr(name, data)

    print(f"Done: {args.xlsx}")
