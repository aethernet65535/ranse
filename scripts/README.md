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
- **Date-aware** — Set the week start date to automatically fill in the correct date column.

## Project Structure

```
fill-erph.py       # Main script
constants.py       # Period times, day names, and other constants
erph-config.yaml   # Configuration file (subject codes, fixed cells)
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

### All options

| Option | Required | Description |
|---|---|---|
| `--xlsx` | Yes | Path to the e-RPH xlsx template file |
| `--timetable-xlsx` | One of `--timetable-xlsx` or `--csv` is required | Path to the timetable xlsx file |
| `--csv` | One of `--timetable-xlsx` or `--csv` is required | Path to the timetable csv file |
| `--config` | No | Path to config YAML (default: `./erph-config.yaml`) |
| `--date` | No | Week start date in `YYYY-MM-DD` format (default: today) |

### Example

```bash
python fill-erph.py \
  --xlsx my-eRPH.xlsx \
  --timetable-xlsx jadual-mingguan.xlsx \
  --config erph-config.yaml \
  --date 2026-09-21
```

This will:
1. Read the timetable from `jadual-mingguan.xlsx`
2. Fill the e-RPH template `my-eRPH.xlsx` with the schedule for the week starting 21 September 2026
3. Overwrite `my-eRPH.xlsx` with the filled result

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
