# Ranse

**Fill spreadsheet templates in place from your weekly data — with one command.**

## What is Ranse?

Ranse is a command-line tool that fills an Excel (xlsx) workbook **in place**
from source data files, without disturbing any cell it does not write. It is
driven entirely by a YAML **profile**: where the files are, what is shared,
and which **handlers** run, in order.

It ships configured for its first business: filling Malaysian **e-RPH**
(*Rancangan Pengajaran Harian*) workbooks from a weekly timetable. That
business — and every other business you could configure — lives entirely in
handlers and data files, never in the core framework described below.

## Features

- **Preserves original formatting** — edits the xlsx file's internal XML
  directly, so all cell styles, merged cells and borders remain untouched.
  Sheets nobody writes to are copied through byte-for-byte.
- **Write-only core** — the engine cannot read a cell back; it has no
  knowledge of days, subjects or layouts, and none of that can leak into it.
- **Profile-driven** — one YAML per teacher/template declares `inputs`
  (where the files are), `context` (shared values) and `handlers` (the
  explicit, ordered pipeline). The workbook can be a `{week}`
  pattern (`…/M{week}.xlsx`), so one profile serves the whole year.
- **Two-phase pipeline** — `resolve` handlers compute inputs first, `fill`
  handlers write cells second; handler names and params are validated before
  anything is touched, and the last writer wins on a shared cell.
- **Two input formats** — read the timetable from `.xlsx` or `.csv`.
- **Single-cell writes** — `ranse write MENU!B3 "ALI BIN ABU"` for one-off
  corrections.
- **Date-aware** — the date defaults to the Sunday of the current week;
  override it with `--date`.
- **Deterministic re-runs** — handlers are stateless; running a week twice
  produces the same workbook.
- **Typed errors** — failures print `Error: …` on stderr and exit 1; usage
  mistakes exit 2.

## Documentation

The framework and each business area are documented separately:

| Document | Contents |
|---|---|
| [`docs/DESIGN.md`](docs/DESIGN.md) | core framework design: engine, CLI, handler system, profile schema, pipeline |
| [`src/ranse/handlers/README.md`](src/ranse/handlers/README.md) | shipped handler business rules — index; each handler has its own DESIGN.md in its own folder |
| [`src/ranse/inputs/README.md`](src/ranse/inputs/README.md) | source-file reader index; each reader has its own DESIGN.md |
| [`config/README.md`](config/README.md) | the school week calendar (`jadual-minggu.yaml`) |
| [`docs/translations/ms-MY/README.md`](docs/translations/ms-MY/README.md) | this README in Bahasa Melayu |

## Project Structure

```
profiles/                    # One profile per teacher/template (start here)
  ali-bin-abu/               # one folder per profile: profile.yaml + docs
    profile.yaml
config/jadual-minggu/        # School calendar data file (see config/README.md)
docs/
  DESIGN.md                  # Core framework design
src/ranse/
  cli.py                     # ranse fill / write
  model.py                   # Lesson / Schedule / Week / Profile
  core/                      # write-only xlsx engine (no business knowledge)
  inputs/                    # one folder + DESIGN.md per reader (timetable, dskp, yaml)
  handlers/                  # week/ menu/ fixed_cells/ dskp/ — one folder + DESIGN.md each
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
ranse fill --profile profiles/ali-bin-abu/profile.yaml --date 2026-09-20
```

One command resolves the inputs, opens the profile's workbook, runs the
handlers in order and overwrites the workbook **in place**. Nothing has to be
edited between weeks.

| Option | Required | Description |
|---|---|---|
| `--profile` | Yes | Path to the profile YAML (`inputs` + `handlers`) |

`--profile` is the only option `ranse fill` adds itself. Every other option
comes from a handler the profile enables, and each handler documents its own
in its `DESIGN.md` (index:
[`src/ranse/handlers/README.md`](src/ranse/handlers/README.md)). With the
shipped profile that is:

| Option | Declared by | Description |
|---|---|---|
| `--date YYYY-MM-DD` | [`week`](src/ranse/handlers/week/DESIGN.md) | Week start (default: the Sunday of the current week; other days roll back to their Sunday) |
| `--minggu N` | [`week`](src/ranse/handlers/week/DESIGN.md) | Override the week number (default: resolved from `--date`) |
| `--no-dskp-auto` | [`dskp`](src/ranse/handlers/dskp/DESIGN.md) | Skip that handler's automatic filling for this run |

There is deliberately no `--xlsx`: the workbook is a profile input, so a
mistake in the shell cannot overwrite the wrong file.

### `ranse write` — one cell

```bash
ranse write --profile profiles/ali-bin-abu/profile.yaml MENU!B3 "ALI BIN ABU"
```

Writes a single cell (`SHEET!CELL`, or `SHEET!FROM:TO` — the top-left of a range or merged range is used) and saves the workbook. It takes no options beyond `--profile`: it runs the profile's resolve phase, so which week's workbook it writes to is decided exactly the way `ranse fill` decides it. The value is written as text; use `ranse fill` with a `fixed_cells` handler for values that must be numbers.

### `python -m ranse.inputs.dskp` — parse DSKP content

```bash
python -m ranse.inputs.dskp --txt assets/bc-dskp/t1.txt --select 1 1 1 -o t1.json
python -m ranse.inputs.dskp --pdf dskp.pdf --pages 35-45 -o t1.json
python -m ranse.inputs.dskp --list
```

Produces structured JSON from a DSKP txt/pdf source. The reader runs as its
own module so `ranse --help` lists only the framework's `fill` / `write`.
Formats: [`src/ranse/inputs/dskp/DESIGN.md`](src/ranse/inputs/dskp/DESIGN.md).

## Configuration (the profile)

A profile is the only thing `ranse fill` / `ranse write` need. It has three
sections:

```yaml
profile: ali-bin-abu-2026

inputs:
  template: "assets/ALI BIN ABU/12. ERPH/2026/*/M{week}.xlsx"  # required
  jadual: "config/jadual-minggu/jadual-minggu.yaml"              # week calendar
  period_times: "config/period-times/period-times.yaml"          # period table
  # templates: {18: "…/06. JUNE/M18.xlsx"}    # pin one week explicitly
  # timetable: "assets/timetable/jadual-waktu-2026-siri-7.xlsx"  # optional override
  # csv: "timetable.csv"

context:
  days: [Ahad, Isnin, Selasa, Rabu, Khamis]  # day blocks the template has
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
      # … handler-specific params, see src/ranse/handlers/README.md
```

### `inputs`

| Key | Description |
|---|---|
| `template` | **Required.** The workbook that gets filled in place. May contain `{week}` and glob wildcards |
| `templates` | Optional `minggu → path` map; wins over `template` for those weeks |
| `jadual` | The week calendar data file (documented in [`config/jadual-minggu/DESIGN.md`](config/jadual-minggu/DESIGN.md)) |
| `timetable` | Optional explicit timetable xlsx; wins over the siri lookup |
| `csv` | Optional explicit timetable csv; wins over the siri lookup |
| `period_times` | Optional period table (period → `[start, end]`); replaces the built-in one (documented in [`config/period-times/DESIGN.md`](config/period-times/DESIGN.md)) |

Relative paths are resolved against the profile's own directory, then the current directory, then the repo root (the last step only in a source checkout — an installed package has none) — so the shipped profile works no matter where you run it from.

**One profile per year.** `template` is a pattern: `{week}` is replaced with the resolved week number, and `*`/`?` wildcards search for the file. The pattern must match **exactly one** workbook; if it matches two (e.g. an old week copied into another folder), `ranse fill` lists the candidates and you pin that week:

```yaml
inputs:
  templates:
    25: "assets/ALI BIN ABU/12. ERPH/2026/07. TMP-NEW/M25.xlsx"
```

A week whose workbook does not exist yet is reported the same way, with `no workbook matched`.

### `context`

Values shared by several handlers — written once instead of duplicated into
both params: one `subjects` map used by two handlers, and the `days` list
(the day blocks the template has) that `menu` and `dskp` both walk.

### `handlers`

An explicit, ordered list. Only built-in handlers can be named — an unknown name is an error, and every handler validates its own `params` before anything is written. On a shared cell, **the last handler in the list wins**.

| Handler | Phase | What it does |
|---|---|---|
| `week` | resolve | date → week number/siri → timetable path (holiday weeks are an error) |
| `menu` | fill | writes the week's time data to the MENU sheet |
| `fixed_cells` | fill | writes `params.cells` — a list of `[sheet, range, value]` |
| `dskp` | fill | writes the DSKP standard rows to the day sheets |

Each handler's rules and full `params` reference live in that handler's own
DESIGN.md (index: [`src/ranse/handlers/README.md`](src/ranse/handlers/README.md)).

## Architecture

```
cli.py ──▶ handlers/ ──▶ core/        (write-only Workbook / Sheet API)
              │
              └──────▶ inputs/        (read source files, never the workbook)
```

- **`core/`** — an xlsx is a zip of XML parts; Ranse skips `openpyxl` and
  edits the sheet XML directly, preserving every attribute it does not
  deliberately change. It is strictly write-only and knows nothing about
  school weeks, subjects or layouts.
- **`inputs/`** — readers that turn the calendar, timetable and DSKP files
  into model objects; they never touch the target workbook.
- **`handlers/`** — all business rules, implementing the two protocols
  (`resolve` / `fill`) and looked up from a built-in registry.
- **`cli.py`** — argparse plus the pipeline order; a `RanseError` becomes
  `Error: …` + exit 1.

Full design (interfaces, decisions, lifecycle, risks):
[`docs/DESIGN.md`](docs/DESIGN.md).

## Development

```bash
pip install -e ".[dev]"
pytest
```

`tests/golden/` holds per-sheet XML baselines; the regression test fills a temporary copy of the template and compares sheet XML byte-for-byte. It is skipped when `assets/` (gitignored) is missing, so a fresh clone still runs the unit tests.

## License

This project is licensed under the [GNU General Public License v2.0](LICENSE).
