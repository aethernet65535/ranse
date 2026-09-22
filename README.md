# Ranse (染色)

**Auto-fill e-RPH xlsx templates with your weekly timetable data — in one command.**

## What is Ranse?

Ranse is a command-line tool designed for Malaysian school teachers. It takes your weekly class timetable (in xlsx or csv format) and automatically fills in the **e-RPH** (electronic Rancangan Pengajaran Harian) Excel template, so you don't have to do it manually every week.

If you've ever spent time copying class names, periods, and subjects into the e-RPH form by hand, Ranse can save you that effort.

## Features

- **Preserves original formatting** — Directly edits the xlsx file's internal XML, so all cell styles, merged cells, and borders remain untouched.
- **Two input formats** — Read your timetable from an `.xlsx` file or a `.csv` file.
- **Automatic period merging** — Consecutive periods with the same class and subject are merged into one row (e.g., two back-to-back Bahasa Cina periods become one entry).
- **Configurable subject mapping** — Map short codes like `BC` to full names like "BAHASA CINA 华文".
- **Fixed cell values** — Write constant values (e.g., teacher name) to specific cells across multiple sheets.
- **Date-aware** — The date defaults to the Sunday of the current week; override it with `--date`.
- **Week-aware (minggu → siri)** — With `--jadual-config`, the week number is resolved from the date, the matching timetable (siri 1, 7, …) is picked automatically, and holidays are detected.
- **Automatic content standards** — Every Bahasa Cina lesson is filled with two parent-level content standards side by side (left/right columns), sliding forward one section per week: `1+2 → 2+3 → … → wrap back to 1+2`.

## Project Structure

```
fill-erph.py        # Main script
gen_dskp.py         # Parse DSKP txt/pdf into structured content
constants.py        # Period times, day names, and other constants
erph-config.yaml    # Configuration file (subject codes, fixed cells, dskp_auto)
jadual-minggu.yaml  # Week calendar: minggu → siri → timetable file
```

## Requirements

- Python 3.6 or later
- [PyYAML](https://pypi.org/project/PyYAML/)

## Installation

```bash
pip install pyyaml
```

> **Note:** A standalone Windows executable (no Python required) is planned for future release.

## Usage

### Basic command

```bash
python fill-erph.py --xlsx <eRPH_template.xlsx> --timetable-xlsx <timetable.xlsx>
```

Or with a CSV timetable:

```bash
python fill-erph.py --xlsx <eRPH_template.xlsx> --csv <timetable.csv>
```

Full auto (week number → siri timetable → MENU + content standards):

```bash
python fill-erph.py --xlsx <eRPH_template.xlsx> --jadual-config jadual-minggu.yaml
```

### All options

| Option | Required | Description |
|---|---|---|
| `--xlsx` | Yes | Path to the e-RPH xlsx template file |
| `--timetable-xlsx` | One of `--timetable-xlsx`, `--csv` or `--jadual-config` is required (unless the config has `dskp` entries) | Path to the timetable xlsx file |
| `--csv` | One of the above is required | Path to the timetable csv file |
| `--jadual-config` | No | Path to `jadual-minggu.yaml`; enables week-aware filling and automatic content standards |
| `--minggu` | No | Override the week number (default: resolved from `--date`) |
| `--no-dskp-auto` | No | Disable automatic content-standard filling |
| `--config` | No | Path to config YAML (default: `./erph-config.yaml`) |
| `--date` | No | Week start date in `YYYY-MM-DD` format (default: **the Sunday of the current week**; other days are rolled back to their Sunday) |

### Example

```bash
python fill-erph.py \
  --xlsx my-eRPH.xlsx \
  --jadual-config jadual-minggu.yaml \
  --config erph-config.yaml \
  --date 2026-09-20
```

This will:
1. Resolve the week: `2026-09-20` → **minggu 33**, siri from `jadual-minggu.yaml`
2. Read that week's timetable (`jadual-waktu-2026-siri-7.xlsx`)
3. Fill the MENU sheet (dates default to the week's Sunday)
4. Fill every Bahasa Cina lesson with two parent-level content standards (left/right), sliding one section per week
5. Overwrite `my-eRPH.xlsx` with the filled result

## Configuration

The `erph-config.yaml` file has two sections:

### `subjects`

Map short subject codes to their full names as they should appear in the e-RPH:

```yaml
subjects:
  BC: "BAHASA CINA 华文"
  BI: "ENGLISH"
  BM: "BAHASA MELAYU"
  MT: "MATEMATIK"
  SC: "SAINS"
```

Any code not listed here will be written into the template as-is.

### `fixed_cells`

Write fixed values to specific cells. Each line is **tab-separated** with three fields:

```
<SHEET>    <CELL_RANGE>    <VALUE>
```

Example:

```yaml
fixed_cells: |
  MENU	B3:C3	ALI BIN ABU
```

This writes "ALI BIN ABU" to cell `B3` (or the top-left of the merged range `B3:C3`) on the `MENU` sheet.

### `dskp_auto`

Controls automatic content-standard filling (only active together with `--jadual-config`):

```yaml
dskp_auto:
  enabled: true
  match_codes: [BC]                # subject codes in the timetable xlsx
  match_names: ["BAHASA CINA", "华文"]  # matched when reading a CSV
  file: assets/bc-dskp/t{tingkatan}.txt  # source txt/json (see below)
  cs: 1                            # which content standard inside a section
  ls: 1                            # which learning standard
  left_col: 2                      # left half  = column B
  right_col: 5                     # right half = column E
```

#### `dskp_auto.file`

Same source format as the static `dskp` entries — any txt (parsed by `gen_dskp.py`) or JSON produced from it, so a hand-written file works too (e.g. one holding your own teaching objectives 教学目标).

`{tingkatan}` is replaced with the tingkatan of each lesson, so the right file is picked automatically:

```yaml
dskp_auto:
  file: assets/bc-dskp/t{tingkatan}.txt   # T1 → t1.txt, T2 → t2.txt, …
```

A per-tingkatan map works as well, and when `file` is omitted the built-in `assets/bc-dskp/t1.txt` … `t5.txt` table is used. Relative `file` paths are resolved against the config directory, the current directory, then the repo root.

### `dskp` (static entries)

Manual, one explicit selection per cell — see the commented example in `erph-config.yaml`. Automatic entries are appended after these, so they win when both target the same cell.

## Week calendar (`jadual-minggu.yaml`)

The week-aware mode is driven by `scripts/jadual-minggu.yaml`:

```yaml
jadual:                 # siri number → timetable file
  1: assets/timetable/jadual-waktu-2026-siri-1.xlsx
  7: assets/timetable/jadual-waktu-2026-siri-7.xlsx

jadual_siri:            # minggu → siri (fill this in)
  33: 1
  34: 7

minggu:                 # each record takes effect from its start date
  - start: 2026-09-20
    minggu: 33
  - start: 2026-09-27
    minggu: 34
```

- `minggu` records are pre-filled from the school calendar (M01…M43); holiday weeks are marked with `cuti` and cause a clear error instead of silently filling the wrong week.
- `jadual_siri` is the minggu → siri table; you can also put `siri: 7` directly inside a `minggu` record (it wins over `jadual_siri`).
- Weeks without a configured siri are an error unless you pass `--timetable-xlsx`/`--csv` explicitly.

## Automatic content standards

For each merged lesson of the matched subject, two **parent-level** sections of the DSKP (the `X.0` headings) are written side by side — left column first, right column second:

```
week 1 → 1.0 听说技能  |  2.0 阅读技能
week 2 → 2.0 阅读技能  |  3.0 书写技能
week 3 → 3.0 书写技能  |  4.0 趣味语文
...
no next section → wrap back to 1.0 + 2.0
```

The pair is computed from the week number alone, so re-running any week always produces the same result. Each side writes the section title (技能 row), the content standard row, and the learning standard row of its class block.

## How It Works

Ranse bypasses libraries like `openpyxl` and works directly with the xlsx file's internal XML. An xlsx file is actually a ZIP archive containing XML files. Ranse:

1. **Unzips** the xlsx file
2. **Parses** the sheet XML using Python's built-in `xml.etree.ElementTree`
3. **Modifies** only the cell values (`<v>` elements) while keeping every original attribute (style, number format, etc.) intact
4. **Re-zips** everything back into a valid xlsx file

This approach ensures that formatting, merged cells, and other layout details are never lost.

## Timetable Input Format

### xlsx format

The timetable xlsx should have the following layout:

| | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| 1 | Period | Ahad | Isnin | Selasa | Rabu | Khamis |
| 2 | 1 | BC-1A | BI-2B | ... | ... | ... |
| 3 | 2 | ... | ... | ... | ... | ... |

- **Row 1** is the header row with day names
- **Column A** contains the period number
- **Other columns** contain class codes in the format `<SUBJECT>-<TINGKATAN><CLASS>` (e.g., `BC-1A` means Bahasa Cina, Tingkatan 1, Class A)

### csv format

The CSV should have these columns:

```
Date,Class,Start Time,End Time,Subject,Tingkatan
```

## License

This project is licensed under the [GNU General Public License v2.0](LICENSE).
