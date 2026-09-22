# Ranse — Design Document

**Status:** as-built design for the current code. This document supersedes
`PLAN.md` (the refactor plan, which is complete). The numbered **decisions**
(D1–D14) and **risks** are stable identifiers: code and test comments that
cite "decision N" or "risk N" mean the tables in §4 and §13.

---

## 1. What Ranse is

Ranse is a command-line tool for Malaysian school teachers. It reads a weekly
class timetable (xlsx or csv) plus a school calendar, works out which week a
date falls in, and fills the corresponding **e-RPH** (electronic *Rancangan
Pengajaran Harian*) Excel workbook — in place, without disturbing any cell it
does not write.

Inputs:

- a **profile** YAML (where the files are, which handlers run);
- the **school calendar** (`config/jadual-minggu.yaml`: date → minggu → siri →
  timetable file);
- the **timetable** for that week (xlsx or csv);
- the **e-RPH workbook** the profile points at.

Output: the workbook itself, with the MENU sheet and the DSKP blocks of the
day sheets filled. Nothing else is printed, mirrored or uploaded.

Non-goals are listed in §15. The single most important behavioural rule is
§6: **time-related data is written to the MENU sheet and nowhere else.**

---

## 2. Architecture

```
+-- CLI (cli.py) -----------------------------------+
|  ranse fill  --profile p.yaml [--date][--minggu]  |  <- --xlsx lives only in the profile (D10)
|  ranse write --profile p.yaml MENU!B3 "value"     |  <- direct single-cell write (D9)
|  ranse dskp  --txt ... --select 1 1 1 -o out.json |
+--------------+------------------------------------+
               | argparse + pipeline order + RanseError -> exit code (D13)
+-- handlers/ -v------------------------------------+
|  base.py       Resolver / Filler protocols + Context |
|  registry.py   built-in registry (the only discovery, D2) |
|  week.py       calendar -> minggu / siri / timetable path |
|  menu.py       MENU layout, time suffixes, period merging |
|  fixed_cells.py / dskp.py   layout constants live here |
+--------------+------------------------------------+
               | may only write through core's write API
+-- core/ -----v---------------+   +-- inputs/ --------+
|  Workbook.open()/save()      |   |  timetable.py     |
|  sheet(name)                 |   |  dskp.py          |
|  write(coord, content)       |   |  yaml.py          |
|  merges (format-preserving)  |   |  x no workbook    |
|  x no read(coord)            |   |    reading of the |
|  x no DAY_ORDER/PERIOD_TIMES |   |    target file    |
+------------------------------+   +-------------------+
```

Dependency direction is strictly one-way:

- `cli → handlers → core`, and `cli`/`handlers` → `inputs`;
- **`core` must not import `handlers` or `inputs`** (D6);
- **`inputs` never touch the target workbook** (D8) — they only read source
  files and produce model objects;
- **`core` is write-only** towards the target workbook: there is no
  `read(coord)` (D7).

File map:

| Path | Responsibility |
|---|---|
| `src/ranse/cli.py` | argparse, two-phase orchestration, `RanseError` → `Error: …` + exit 1 |
| `src/ranse/model.py` | `Lesson` / `Schedule` / `Week` / `Profile` dataclasses, `merge_periods` |
| `src/ranse/errors.py` | `RanseError`, `ProfileError`, `WeekError`, `SheetError` |
| `src/ranse/core/refs.py` | A1 ↔ (row, col), range top-left, Excel date serial, path resolution — pure functions |
| `src/ranse/core/xlsx.py` | zip container + write-only `Workbook` / `Sheet` |
| `src/ranse/inputs/timetable.py` | timetable csv/xlsx → `Schedule`; `PERIOD_TIMES`, `TIME_PERIOD`, `DAY_ORDER` |
| `src/ranse/inputs/dskp.py` | DSKP txt/pdf parsing, `resolve_selection`, the `ranse dskp` CLI |
| `src/ranse/inputs/yaml.py` | profile + calendar loading and validation, `resolve_template` |
| `src/ranse/handlers/*.py` | `week` resolver, `menu` / `fixed_cells` / `dskp` fillers |
| `profiles/*.yaml` | one profile per teacher/template |
| `config/jadual-minggu.yaml` | standalone school calendar (D11) |
| `tests/` | unit tests + golden regression baselines |

`model.py` sits at the top level of the package rather than in `core/` because
`Lesson`/`Schedule`/`Week` carry timetable and e-RPH semantics (day names,
tingkatan, week numbers) that the pure write engine must not know about.

---

## 3. Interfaces

### 3.1 Core write API (strictly write-only)

```python
class Workbook:
    @classmethod
    def open(cls, path) -> "Workbook": ...
    @property
    def sheets(self) -> list[str]: ...
    def sheet(self, name: str) -> "Sheet": ...
    def write(self, ref: str, content) -> None: ...   # "MENU!B3" or "MENU!B3:C3"
    def save(self, path=None) -> None: ...            # None = overwrite in place

class Sheet:
    def write(self, coord: str, content) -> None: ...
    def merges(self) -> list[tuple[int, int, int, int]]: ...
```

Rules:

- **no `read(coord)`** — nothing in the pipeline reads a value back out of the
  target workbook (D7);
- a range or merged-range coordinate writes its **top-left** cell, so every
  caller does not have to do the merge lookup by hand;
- strings are written as `t="inlineStr"` + `<is><t>`, numbers as `<v>`, and
  **every other attribute of the `<c>` element is preserved** (style,
  number format, …);
- missing `<row>` / `<c>` elements are created and re-sorted into order.

### 3.2 Handler protocol and `Context`

```python
@dataclass
class Context:
    profile; workbook=None; schedule=None; week=None; start_date=None
    params={}          # params of the handler currently running
    runtime={}         # --date / --minggu / --no-dskp-auto
    timetable_path=None; timetable_is_csv=False
    report=[]

class Resolver(Protocol):   # phase one: compute inputs, write no cells
    name: str
    def resolve(self, ctx: Context) -> None: ...

class Filler(Protocol):     # phase two: write cells through core only
    name: str
    def fill(self, ctx: Context) -> list[str]: ...   # returns report lines
```

Handlers are looked up by name in `handlers/registry.py` (built-in only, D2),
and each handler validates its own `params` at build time — an unknown name or
a malformed `params` fails **before any cell is touched**.

### 3.3 Profile schema

```yaml
profile: ali-bin-abu-2026

inputs:
  template: "assets/ALI BIN ABU/12. ERPH/2026/*/M{minggu}.xlsx"  # required
  jadual: "config/jadual-minggu.yaml"
  # templates: {25: "…/M25.xlsx"}   # pin a week when the pattern is ambiguous
  # timetable: "…/jadual-waktu-2026-siri-7.xlsx"
  # csv: "…/timetable.csv"

context:
  subjects:
    BC: "BAHASA CINA 华 文"

handlers:
  - name: week
  - name: menu
  - name: fixed_cells
    params:
      cells: [[MENU, "B3:C3", "ALI BIN ABU"]]
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

Validation rules: a missing `inputs.template` or a malformed `handlers:` list
raises `ProfileError` from `inputs/yaml.py`; an unknown handler name or invalid
handler params raises `ProfileError` from the registry. Relative paths resolve
against the profile's own directory, then the current directory, then the repo
root.

`context` exists so shared values are not duplicated into several handlers —
`subjects` is used by both the `menu` and the `dskp` handler.

### 3.4 CLI

```
ranse fill  --profile P [--date YYYY-MM-DD] [--minggu N] [--no-dskp-auto]
ranse write --profile P [--minggu N] SHEET!CELL VALUE
ranse dskp  --txt FILE [--select S CS LS] [-o out.json] | --pdf F --pages 35-45 | --list
```

There is deliberately **no `--xlsx`**: the workbook is a profile input, so a
mistake in the shell cannot overwrite the wrong file (D10).

`ranse write` always writes **text**; a value that must stay a number (a year,
an amount) belongs in a `fixed_cells` handler, which keeps the `int(value)`
path (risk 8).

---

## 4. Settled decisions

These were agreed with the maintainer and are not up for re-litigation. D1–D13
came from `PLAN.md`; D14 is the MENU-sheet rule from §6.

| # | Item | Decision |
|---|---|---|
| D1 | Profile shape | An **explicit ordered `handlers:` list**; do not support both an implicit and an explicit form |
| D2 | Handler discovery | **Built-in registry only** — no dynamic import paths, no entry-point plugins |
| D3 | Packaging | An **installable package**; there is no `scripts/fill-erph.py` legacy entry |
| D4 | Equivalence check | Write the **golden regression tests before touching business code** |
| D5 | Extra scope | dict → dataclass, README + `docs/translations/ms-MY/README.md` kept in sync, `gen_dskp.py` absorbed into `inputs/dskp.py` |
| D6 | Core constraint | **No business logic in core**: no `DAY_ORDER`/`PERIOD_TIMES`/`BC-1A`/`minggu`/`cuti`/`sys.exit` |
| D7 | Core boundary | Core is **write-only** towards the target workbook: `open / sheet / write / save`; **no `read(coord)`** |
| D8 | Input reading | Lives in a separate **`inputs/` layer** (timetable, DSKP, the two YAML files); it never touches the target workbook |
| D9 | Single-cell writes | Both layers: the core API `wb.write("MENU!B3", "value")` **and** the CLI subcommand `ranse write` |
| D10 | Template path | **`--xlsx` is a profile-only parameter** (`inputs.template`); it is not on the CLI |
| D11 | Calendar file | `jadual-minggu.yaml` is a **standalone data file** referenced by the profile via `inputs.jadual`; it is not merged into the profile |
| D12 | Layout constants | MENU row `5 + day_idx*10`, columns 3–7, `NUM_PERIODS=8`, `CLASS_BLOCK_SIZE=31`, … **stay in the handlers for v1**; they do not go into the profile |
| D13 | Error handling | Core raises `RanseError` subclasses; the CLI maps them to `Error: …` + exit code 1. Handlers and inputs keep `print(..., file=sys.stderr)`; **no logging framework** |
| D14 | Time ownership | **All time-related data is written to the MENU sheet** — see §6. No other sheet receives dates, times or per-period classes, and no other writer competes for those cells |

---

## 5. Lifecycle (two-phase orchestration)

`ranse fill` runs one deterministic pipeline:

1. **Load the profile** (`inputs/yaml.py`) and **build the handlers**
   (registry): unknown names and bad params fail here, before any I/O to the
   workbook.
2. **Resolve phase** — every handler with `phase == "resolve"` runs in profile
   order. In practice this is `week`, which computes `ctx.start_date`,
   `ctx.week` (minggu + siri) and the timetable path. Resolvers write no cells.
3. **Pick the workbook** — `resolve_template()` substitutes `{minggu}` and
   resolves glob wildcards; zero matches or several matches are both errors
   that list the candidates and point at `inputs.templates`.
4. **Open it** (`Workbook.open`) and check the required sheets exist:
   `MENU`, `AHAD`, `ISNIN`, `SELASA`, `RABU`, `KHAMIS`.
5. **Read the timetable** (`inputs/timetable.py`) into a `Schedule`. The target
   workbook stays write-only: the timetable is a separate file.
6. **Fill phase** — every handler with `phase == "fill"` runs in profile
   order: `menu`, then `fixed_cells`, then `dskp` in the shipped profile.
   **Order is significant**: the last writer wins on a shared cell, which is
   how `fixed_cells` overrides MENU's own values and how automatic DSKP
   entries override static ones (risk 9).
7. **Save** (`wb.save()` overwrites the template in place) and print the report.

Handlers are stateless between runs: the same week produces the same result
whatever ran before, and re-running a week is always safe.

---

## 6. The MENU sheet is the only place time is written

This is the load-bearing rule of the fill business (D14):

> **If a piece of information is about time — the week's date, when a period
> starts and ends, which class sits in a period — it is written to the MENU
> sheet and nowhere else.**

Consequences:

- The **day sheets (`AHAD` … `KHAMIS`) carry content only** — the DSKP
  standard rows. They never receive a date, a time or a class label.
- No handler other than `menu` writes a time-related cell; `fixed_cells` and
  `dskp` are not used for times in the shipped profile.
- A correction to time-related data is a **MENU-sheet edit**: change the
  timetable (or the calendar) and re-run, or use the single-cell escape hatch
  `ranse write --profile P --minggu N MENU!<cell> "<value>"` (D9).
- Because everything time-related lives on one sheet, a wrong week cannot
  half-apply: MENU is either fully rewritten for the week or left untouched.

### 6.1 MENU layout

Day blocks are 10 rows apart, starting at row 5 (D12: constants stay in
`handlers/menu.py`, `NUM_PERIODS = 8`):

| Block | Header row | Period rows | Date cell |
|---|---|---|---|
| Ahad | 5 | 6–13 | **I6** |
| Isnin | 15 | 16–23 | — |
| Selasa | 25 | 26–33 | — |
| Rabu | 35 | 36–43 | — |
| Khamis | 45 | 46–53 | — |

For each day, up to eight rows are written after the header row (`header_row +
1 + i`), one per merged lesson, with these columns:

| Column | Content | Source |
|---|---|---|
| C | class label as the timetable spells it (`1E`, `5SPA`, …) | `Lesson.cls` |
| D | period start time + day-part suffix | `Lesson.start` |
| E | period end time + day-part suffix | `Lesson.end` |
| F | subject name | `context.subjects` lookup, else the raw code |
| G | tingkatan, written as a **number** | `int(Lesson.tingkatan)` |

The week's date is written **only** to `MENU!I6`, as an Excel date serial
(`_date_to_excel`), for the Sunday the week starts on. Other day blocks have no
date cell.

Two clearing rules keep a re-run honest:

- after the merged lessons of a day, the remaining rows of the block are
  written as `""` in C–G, which **clears the previous run's leftovers**
  (risk 7 — do not delete that branch);
- if the profile has no timetable at all (`ctx.schedule` is empty) the MENU
  sheet is not touched, not even re-serialized, so an unfilled week stays
  byte-identical.

### 6.2 Merged lessons

`merge_periods` (in `model.py`, so both `menu` and `dskp` share it) merges
consecutive periods that have the same class, subject and tingkatan **and**
contiguous time (`entry.start == previous.end`). Two back-to-back Bahasa Cina
periods therefore occupy one MENU row covering 07:40–09:00, and a gap in time
ends a run even when the same lesson resumes (risk 4).

The row index `i` is the index of the merged lesson, not the period number:
merged lesson *i* is written to row `header_row + 1 + i`.

### 6.3 Time suffix (PAGI / TGH / TPTG)

`_time_with_suffix` is keyed on whole hours: `hour < 11` → `PAGI`,
`11 ≤ hour < 14` → `TGH`, `hour ≥ 14` → `TPTG`.

The fallback is pinned on purpose: only `HH:00` keys are in the cache, and
every real period time has non-zero minutes, so the template really contains
strings like `09:00 PAGI` and `11:30 PAGI`. The golden baselines encode this
(risk 11). Do not "fix" it silently — changing it changes every filled
workbook.

### 6.4 Where to change what

| I want to change … | It lives in | How |
|---|---|---|
| this week's date | calendar → `MENU!I6` | `--date 2026-09-20`, or edit the `minggu` records |
| which timetable a week uses | `jadual_siri` (or `siri:` in the record) | edit `config/jadual-minggu.yaml` |
| the period times themselves | `PERIOD_TIMES` in `inputs/timetable.py` | edit the table (affects every week at once) |
| one period's class / time for one week | **MENU sheet**, columns C–G | `ranse write` on that cell — note the next `ranse fill` for the same week rewrites it |
| the DSKP standards on a day sheet | DSKP blocks | `dskp` handler params; never a time edit |

---

## 7. Week resolution (`week` handler)

The resolver turns a date into `Week(minggu, siri)` plus a timetable path:

1. The week start is the **Sunday** of the date's week (`--date` defaults to
   today; other weekdays roll back to their Sunday). MENU's date cell is that
   Sunday.
2. `minggu` records in the calendar take effect **from their `start` date until
   the next record**. The record whose `start ≤ date` is chosen.
3. `siri` comes from the record itself, else from `jadual_siri[minggu]`.
4. The timetable path is `jadual[siri]`, unless the profile sets
   `inputs.timetable` / `inputs.csv`, which win.

Hard errors (a wrong week would silently fill the wrong content):

- the calendar has no dated `minggu` records;
- the date is earlier than the first record;
- the chosen record is a holiday week (`cuti: …`);
- the chosen record has no `minggu` number;
- the week has no `siri` configured and no explicit timetable input;
- the resolved file does not exist.

Errors are reported the handler way — `print(…, file=sys.stderr)` + exit 1
(D13).

---

## 8. DSKP filling

`dskp` fills the standard rows of each class block on the day sheets. It is the
only handler that writes to `AHAD`–`KHAMIS`, and it writes **content only** —
which is exactly why MENU can own all time data (§6).

- **Block layout** (D12, `handlers/dskp.py`): class *n* (1-based) starts at row
  `7 + (n-1) * 31` (`CLASS_BLOCK_SIZE = 31`); from that header the handler
  writes the title row `+6`, the content standard `+7` and the learning
  standard `+9`.
- **Columns**: the left half defaults to column B (`left_col: 2`), the right
  half to column E (`right_col: 5`).
- **Automatic mode** (`mode: auto`, the default): for every merged lesson of a
  matched subject, two **parent-level** sections (`X.0` headings) are written
  side by side, sliding one section forward per week:
  `idx = (minggu - 1) % (len(sections) - 1)` → `keys[idx]`, `keys[idx+1]`.
  When there is no next section the pair wraps back to the first two, so a
  week number alone always determines the content.
- **Matching**: `match_codes` matches the timetable's subject codes
  (`BC-1A`); `match_names` matches the subject name after `context.subjects`
  mapping (the CSV direction). A subject that matches nothing is skipped.
- **Static entries** (`params.entries`) are written first, then automatic
  entries are appended, so on the same cell the automatic entry wins
  (risk 9).
- **`file`** accepts `{tingkatan}` (`t1.txt`, `t2.txt`, …), a per-tingkatan
  map, or nothing — then the built-in `DSKP_FILES` table is used.
- **Warnings, not errors**: a missing DSKP file, a file with no usable parent
  sections, or an unknown sheet is reported on stderr and skipped, so one bad
  class does not abort the week.
- `--no-dskp-auto` (or `mode: static`) disables the automatic part for a run;
  with no week known the handler prints a note instead of guessing.

---

## 9. Workbook engine (core)

An xlsx is a zip of XML parts. Ranse deliberately avoids `openpyxl`: it edits
the sheet XML directly so that styles, merged cells, borders and print settings
survive untouched.

- `Workbook.open()` reads **all zip entries into memory**, parses
  `xl/workbook.xml` + `xl/_rels/workbook.xml.rels` to map sheet names to parts,
  and registers the XML namespaces **once** (the `ET.register_namespace` side
  effect lives here, not in every parse) with the exact prefixes/URIs the
  templates use (risk 1).
- Sheets are parsed **lazily** on first access and cached.
- `save()` re-serializes **only the sheets that received a write**; every other
  zip entry is copied through **byte-for-byte**, so untouched parts of the
  template cannot drift.
- Serialized sheets keep the original declaration and formatting:
  `xml_declaration=True, encoding="UTF-8", short_empty_elements=False`.
- Writes are merge-aware: the coordinate's top-left cell is used, and if it
  falls inside a merged area, the area's top-left cell is used.

The engine is intentionally dumb: no day names, no period times, no week
numbers, no exit codes.

---

## 10. Inputs and data formats

| Input | Format | Notes |
|---|---|---|
| Profile | YAML | `inputs` / `context` / `handlers` (§3.3) |
| Calendar | YAML | `jadual` (siri → file), `jadual_siri` (minggu → siri), `minggu` (dated records) |
| Timetable | xlsx | row 1 = header with day names, column A = period number, other columns = `SUBJECT-TINGKATANCLASS` codes (`BC-1A`) |
| Timetable | csv | `Date,Class,Start Time,End Time,Subject,Tingkatan` |
| DSKP | txt / JSON | txt parsed on the fly; JSON produced by `ranse dskp` |

Both period tables live in `inputs/timetable.py`: `PERIOD_TIMES` (period →
start/end, used by the MENU fill) and `TIME_PERIOD` (start/end → period, used
by the CSV reader). Values are unchanged from the original script (risk 4).

`Jumaat` / `Sabtu` columns are dropped while reading, because the template only
has sheets for Ahad–Khamis (risk 10). CSV rows whose `Date` cannot be parsed
produce a warning and are skipped.

---

## 11. Errors and exit codes

- `core` / `inputs` raise `RanseError` subclasses (`ProfileError`,
  `WeekError`, `SheetError`).
- `cli` catches `RanseError` and prints `Error: <message>` on stderr, exit 1.
- Handlers keep the legacy style: `print(…, file=sys.stderr)` + `sys.exit(1)`
  for business errors, and a `  Warning: …` line for skippable problems.
- argparse usage errors (e.g. "Nothing to do: set inputs.timetable …") go
  through `parser.error` and exit 2.

Anything that could fill the wrong week or the wrong cell is a hard error. A
missing DSKP file for one class is a warning.

---

## 12. Testing

Two layers, both must stay green (D4):

1. **Pure unit tests** — no `assets/` dependency, so a fresh clone can run
   them: cell-reference round trips, Excel date serials, `_section_pair`
   sliding and wrap, `merge_periods` (contiguous merges, gaps do not), week
   resolution (cuti / missing minggu / out-of-range dates), class-code parsing
   (`BC-1A`, en-dash variant), and the PAGI/TGH/TPTG boundaries.
2. **Golden regression** — fills a **temporary copy** of the real template and
   compares each sheet's XML bytes against `tests/golden/<case>/<sheet>.xml.gz`:

   | Case | Date | Expectation |
   |---|---|---|
   | `minggu-33` | 2026-09-20 | siri 7 timetable, full fill |
   | `minggu-34` | 2026-09-27 | siri 7 timetable, full fill |
   | `cuti` | 2026-01-04 | non-zero exit, "holiday week" on stderr |

   Baselines are per-sheet XML, never whole-zip bytes: zip entry order and
   timestamps would produce false diffs (risk 2). Regenerate them with
   `tests/make_golden.py`. The suite **skips** when `assets/` is missing
   (gitignored), which is why the unit tests must be self-contained
   (risk 5).

---

## 13. Risks and pitfalls

1. **Serialization must be byte-for-byte**: keep
   `xml_declaration=True, encoding="UTF-8", short_empty_elements=False` and
   every `register_namespace` prefix/URI, or every golden test fails.
2. **Golden compares sheet XML, not zip bytes.**
3. **The `subjects` map is shared** by `menu` and `dskp` → it belongs in the
   profile `context:`, not duplicated into both handlers' params.
4. **Two period tables** (`PERIOD_TIMES`, `TIME_PERIOD`) with unchanged
   values; `merge_periods` must treat a time gap as a new run.
5. **`assets/` is not committed** → regression tests skip on a fresh clone; the
   pure-function tests are the safety net there.
6. **The template is large and overwritten in place** → always copy it to a
   temp directory before filling it in a test.
7. **`menu` writes empty rows as `""`** to clear a previous run's result — do
   not delete that branch.
8. **`fixed_cells` values pass through an `int(value)` attempt at write time**,
   not at profile-load time; keep that timing or a type change breaks golden.
9. **Order matters in the fill phase**: static DSKP entries are written before
   automatic ones (auto wins on the same cell), and the profile's handler order
   decides who wins on a shared MENU cell.
10. **Jumaat/Sabtu are dropped** while reading the timetable — an existing
    business rule that lives outside core.
11. **The PAGI/TGH/TPTG suffix only applies to `HH:00`**; real period times
    fall back to `PAGI`, and the templates rely on that (§6.3). Changing it
    changes every filled workbook.
12. **MENU is the only time writer** (D14): adding a time write somewhere else
    (a day sheet, a new handler) breaks the invariant that one sheet decides
    the week's dates and periods.

---

## 14. Implementation history

The current layout was reached in five stages, one commit each, with the golden
suite green at every step (D4):

| Stage | Content |
|---|---|
| 0 | Fold in the work-in-progress changes; add `pyproject.toml`, the golden baselines and the pure-function unit tests (baselines taken from the **working tree**, not from the previous commit) |
| 1 | Pure move into `src/ranse/` — imports and file placement only, no logic or string changes |
| 2 | De-business-ify `core` (RanseError instead of `sys.exit`), extract `week` / `menu` / `fixed_cells` / `dskp` handlers, drop `sys.path.insert` + dynamic `gen_dskp` import, move the namespace registration into `Workbook` |
| 3 | Profile schema + two-phase orchestration + dataclasses (`Lesson` / `Schedule` / `Week` / `Profile`) |
| 4 | Packaging (`ranse` console script), the three subcommands, delete `scripts/`, rewrite README + the Malay translation |

`PLAN.md` was the plan for those stages; it is superseded by this document.

---

## 15. Out of scope and future work

Not to be done with the current design:

- introducing `openpyxl` (or any library that rewrites the whole workbook);
- a logging framework, or rewording the existing error messages;
- moving layout constants (row formulas, column numbers) into the profile
  (D12);
- dynamic third-party handler loading (D2);
- a `scripts/fill-erph.py` compatibility entry (D3);
- edits under `assets/`.

Planned or possible later:

- a standalone Windows executable (no Python required) for teachers;
- an optional core read API, if a feature ever needs to inspect values before
  writing;
- per-week time overrides — **which, per D14, must be expressed as MENU-sheet
  values**, never as a second source of times;
- timetable files for siri 2–6 (the calendar reports missing files today).
