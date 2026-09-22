# Ranse (染色)

**Auto-fill e-RPH xlsx templates with your weekly timetable data — in one command.**

## What is Ranse?

Ranse is a command-line tool designed for Malaysian school teachers. It takes your weekly class timetable (in xlsx or csv format) and automatically fills in the **e-RPH** (electronic Rancangan Pengajaran Harian) Excel template, so you don't have to do it manually every week.

If you've ever spent time copying class names, periods, and subjects into the e-RPH form by hand, Ranse can save you that effort.

## Features

- **Preserves original formatting** — Directly edits the xlsx file's internal XML, so all cell styles, merged cells, and borders remain untouched.
- **Profiles** — One YAML file per teacher says where the files live (`inputs`), what is shared between handlers (`context`) and which handlers run (`handlers`). The workbook can be a `{minggu}` pattern (`…/M{minggu}.xlsx`), so one profile serves the whole year.
- **Two input formats** — Read your timetable from an `.xlsx` file or a `.csv` file.
- **Automatic period merging** — Consecutive periods with the same class and subject are merged into one row (e.g., two back-to-back Bahasa Cina periods become one entry).
- **Configurable subject mapping** — Map short codes like `BC` to full names like "BAHASA CINA 华文".
- **Fixed cell values** — Write constant values (e.g., teacher name) to specific cells.
- **Single-cell writes** — `ranse write MENU!B3 "ALI BIN ABU"` for one-off corrections.
- **Date-aware** — The date defaults to the Sunday of the current week; override it with `--date`.
- **Week-aware (minggu → siri)** — The week number is resolved from the date, the matching timetable (siri 1, 7, …) is picked automatically, and holiday weeks are reported instead of silently filling the wrong week.
- **Automatic content standards** — Every matched lesson is filled with two parent-level content standards side by side (left/right columns), sliding forward one section per week: `1+2 → 2+3 → … → wrap back to 1+2`.
- **DSKP toolkit** — `ranse dskp` parses a DSKP txt/pdf into structured JSON for the manual entries.

## Project Structure

```
profiles/                    # One profile per teacher/template (start here)
  ali-bin-abu.yaml
config/jadual-minggu.yaml    # School calendar: date → minggu → siri → timetable
src/ranse/
  cli.py                     # ranse fill / write / dskp
  model.py                   # Lesson / Schedule / Week / Profile
  core/                      # write-only xlsx engine (no school knowledge)
  inputs/                    # timetable, DSKP and YAML readers
  handlers/                  # week / menu / fixed_cells / dskp
tests/                       # unit tests + golden regression baselines
```

## Requirements

- Python 3.9 or later
- [PyYAML](https://pypi.org/project/PyYAML/) (installed automatically)

## Installation

```bash
pip install -e .
```

This installs the `ranse` command. `pip install -e ".[dev]"` also installs pytest for development.

> **Note:** A standalone Windows executable (no Python required) is planned for future release.

## Usage

### `ranse fill` — fill this week's workbook

```bash
ranse fill --profile profiles/ali-bin-abu.yaml --date 2026-09-20
```

That single command resolves the week from the calendar, picks that week's workbook, reads the matching timetable, fills the MENU sheet, the fixed cells and the DSKP blocks, and overwrites the workbook **in place**. Nothing has to be edited between weeks.

| Option | Required | Description |
|---|---|---|
| `--profile` | Yes | Path to the profile YAML (`inputs` + `handlers`) |
| `--date` | No | Week start date in `YYYY-MM-DD` (default: **the Sunday of the current week**; other days are rolled back to their Sunday) |
| `--minggu` | No | Override the week number (default: resolved from `--date`) |
| `--no-dskp-auto` | No | Disable automatic content-standard filling for this run |

There is deliberately no `--xlsx`: the workbook is a profile input, so a mistake in the shell cannot overwrite the wrong file.

This will:
1. Resolve the week: `2026-09-20` → **minggu 33**, siri `7` from `config/jadual-minggu.yaml`
2. Pick the workbook for minggu 33 (`…/2026/07. TMP-NEW/M33.xlsx`)
3. Read that week's timetable (`assets/timetable/jadual-waktu-2026-siri-7.xlsx`)
4. Fill the MENU sheet (the date column gets the week's Sunday)
5. Fill every matched lesson with two parent-level content standards (left/right), sliding one section per week
6. Overwrite the workbook in place

### `ranse write` — one cell

```bash
ranse write --profile profiles/ali-bin-abu.yaml --minggu 33 MENU!B3 "ALI BIN ABU"
```

Writes a single cell (`SHEET!CELL`, or `SHEET!FROM:TO` — the top-left of a range or merged range is used) and saves the workbook. `--minggu` is only needed when the profile's `template` contains `{minggu}`. The value is written as text; use `ranse fill` with a `fixed_cells` handler for values that must be numbers.

### `ranse dskp` — parse DSKP content

```bash
ranse dskp --txt assets/bc-dskp/t1.txt --select 1 1 1 -o t1.json
ranse dskp --pdf dskp.pdf --pages 35-45 -o t1.json
ranse dskp --list
```

Produces the structured JSON that the manual `dskp` entries reference.

## Configuration (the profile)

A profile is the only thing `ranse fill` / `ranse write` need. It has three sections:

```yaml
profile: ali-bin-abu-2026

inputs:
  template: "assets/ALI BIN ABU/12. ERPH/2026/*/M{minggu}.xlsx"  # required
  jadual: "config/jadual-minggu.yaml"                            # week calendar
  # templates: {18: "…/06. JUNE/M18.xlsx"}    # pin one week explicitly
  # timetable: "assets/timetable/jadual-waktu-2026-siri-7.xlsx"  # optional override
  # csv: "timetable.csv"

context:
  subjects:
    BC: "BAHASA CINA 华 文"

handlers:
  - name: week
  - name: menu
  - name: fixed_cells
    params:
      cells:
        - [MENU, "B3:C3", "ALI BIN ABU"]
  - name: dskp
    params:
      mode: auto
      file: "assets/bc-dskp/t{tingkatan}.txt"
      match_codes: [BC]
      match_names: ["BAHASA CINA", "华文"]
      cs: 1
      ls: 1
      left_col: 2
      right_col: 5
```

### `inputs`

| Key | Description |
|---|---|
| `template` | **Required.** The e-RPH workbook that gets filled in place. May contain `{minggu}` and glob wildcards |
| `templates` | Optional `minggu → path` map; wins over `template` for those weeks |
| `jadual` | The week calendar (`config/jadual-minggu.yaml`) |
| `timetable` | Optional explicit timetable xlsx; wins over the siri lookup |
| `csv` | Optional explicit timetable csv; wins over the siri lookup |

Relative paths are resolved against the profile's own directory, then the current directory, then the repo root — so the shipped profile works no matter where you run it from.

**One profile per year.** `template` is a pattern: `{minggu}` is replaced with the resolved week number, and `*`/`?` wildcards search for the file. The shipped profile therefore finds `01. JANUARY/M1.xlsx`, `02. FEBRUARY/M4.xlsx` and `07. TMP-NEW/M33.xlsx` from one line, and the timetable side is already mapped by the calendar (`jadual_siri` + `jadual`).

If a week cannot be decided automatically — typically because an old week was copied into another folder, leaving two files called `M<minggu>.xlsx` — `ranse fill` says so and lists the candidates, and you pin that week with `templates`:

```text
Error: 'assets/…/2026/*/M25.xlsx' matches 2 workbooks for minggu 25:
…/05. MAY/M25.xlsx, …/07. TMP-NEW/M25.xlsx
— add an explicit 'inputs.templates' entry to the profile
```

```yaml
inputs:
  templates:
    25: "assets/ALI BIN ABU/12. ERPH/2026/07. TMP-NEW/M25.xlsx"
```

Keeping exactly one file per week number makes the pattern unambiguous for the whole year; a week whose workbook does not exist yet (say you fill week 34 before creating `M34.xlsx`) is reported the same way, with `no workbook matched`.

### `context`

Values shared by several handlers. `subjects` maps subject codes to the names written into the template; a code that is not listed is written as-is.

```yaml
context:
  subjects:
    BC: "BAHASA CINA 华 文"
    BI: "ENGLISH"
```

### `handlers`

An explicit, ordered list. Only built-in handlers can be named — an unknown name is an error, and every handler validates its own `params` before anything is written.

| Handler | Phase | What it does |
|---|---|---|
| `week` | resolve | date → minggu/siri → timetable path (holiday weeks are an error) |
| `menu` | fill | MENU rows: class, times with PAGI/TGH/TPTG suffix, subject name, tingkatan |
| `fixed_cells` | fill | writes `params.cells` — a list of `[sheet, range, value]` |
| `dskp` | fill | DSKP blocks: manual `entries` first, then the automatic week-based pair |

#### `fixed_cells` params

```yaml
- name: fixed_cells
  params:
    cells:
      - [MENU, "B3:C3", "ALI BIN ABU"]   # writes to the top-left of the range
      - [MENU, "B4", 2026]                # numbers stay numbers
```

#### `dskp` params

```yaml
- name: dskp
  params:
    mode: auto                            # auto (default) | static
    entries:                              # manual entries, written first
      - {sheet: ISNIN, class: 1, file: t1.json,
         selection: [1, 1, 1], col_start: 2}
    file: "assets/bc-dskp/t{tingkatan}.txt"  # source for the automatic pair
    match_codes: [BC]                     # subject codes in the timetable xlsx
    match_names: ["BAHASA CINA", "华文"]   # matched when reading a CSV
    cs: 1                                 # which content standard inside a section
    ls: 1                                 # which learning standard
    left_col: 2                           # left half  = column B
    right_col: 5                          # right half = column E
```

`file` accepts a `{tingkatan}` placeholder (T1 → `t1.txt`, T2 → `t2.txt`, …), a per-tingkatan map, or nothing at all — in which case the built-in `assets/bc-dskp/t1.txt` … `t5.txt` table is used. The same source formats as the manual entries are supported: a txt file, or JSON produced by `ranse dskp`.

Automatic entries are appended **after** the manual ones, so on the same cell the automatic entry wins. `--no-dskp-auto` (or `mode: static`) turns the automatic part off for a run.

## Week calendar (`config/jadual-minggu.yaml`)

The week-aware mode is driven by the calendar referenced from `inputs.jadual`:

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

- `minggu` records are pre-filled from the school calendar (M01…M43); holiday weeks are marked with `cuti` and produce a clear error instead of silently filling the wrong week.
- `jadual_siri` is the minggu → siri table; you can also put `siri: 7` directly inside a `minggu` record (it wins over `jadual_siri`).
- Weeks without a configured siri are an error unless `inputs.timetable` / `inputs.csv` is set in the profile.

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

The workbook engine is deliberately write-only — it has no way to read a cell value — and knows nothing about school weeks, subjects or layouts. All of that lives in the handlers, which write through the engine. Sheets nobody wrote to are copied through byte-for-byte, so untouched parts of the template cannot drift.

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

Friday and Saturday columns are ignored: the template only has sheets for Ahad–Khamis.

### csv format

The CSV should have these columns:

```
Date,Class,Start Time,End Time,Subject,Tingkatan
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

`tests/golden/` holds per-sheet XML baselines; the regression test fills a temporary copy of the template and compares sheet XML byte-for-byte. It is skipped when `assets/` (gitignored) is missing, so a fresh clone still runs the unit tests.

## License

This project is licensed under the [GNU General Public License v2.0](LICENSE).
