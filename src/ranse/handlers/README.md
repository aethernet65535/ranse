# Handler business rules — the shipped e-RPH fill

The handler **system** (protocols, registry, two-phase pipeline, profile
schema) is framework and is documented in `docs/DESIGN.md` §3–§5. This file
documents what the four **shipped handlers actually do** — the e-RPH business
rules that must stay out of `core/` (decision 6).

Contract, for reference (details in `docs/DESIGN.md`):

- handlers are listed explicitly and in order in the profile (decision 1) and
  discovered only from `handlers/registry.py` (decision 2);
- `phase: "resolve"` handlers compute `ctx` inputs and **write no cells**;
  `phase: "fill"` handlers are the only code allowed to write, and only
  through `ctx.workbook` (the core write API);
- each handler validates its own `params` at build time — a broken profile
  fails before any cell is touched;
- in the fill phase the **last writer wins** on a shared cell (risk 9).

| Handler | Phase | Rules defined here |
|---|---|---|
| `week` | resolve | date → minggu/siri → timetable path |
| `menu` | fill | the MENU sheet owns all time data (decision 14), its layout and clearing rules |
| `fixed_cells` | fill | constant cells, `int(value)` timing |
| `dskp` | fill | day-sheet DSKP blocks, automatic section pair, entry order |

Cross-references: the calendar consumed by `week` is specified in
[`config/README.md`](../../../config/README.md); the timetable and DSKP source
formats are specified in [`docs/input-formats.md`](../../../docs/input-formats.md);
framework design in [`docs/DESIGN.md`](../../../docs/DESIGN.md).

Risk numbers (4, 7–12) continue the global list in `docs/DESIGN.md` §10.

---

## `week` (resolve)

`src/ranse/handlers/week.py` turns a date into `Week(minggu, siri)` plus a
timetable path; it never writes a cell.

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
(decision 13).

---

## `menu` (fill)

### The MENU sheet is the only place time is written

This is the load-bearing rule of the fill business (decision 14, risk 12):

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
  `ranse write --profile P --minggu N MENU!<cell> "<value>"` (decision 9).
- Because everything time-related lives on one sheet, a wrong week cannot
  half-apply: MENU is either fully rewritten for the week or left untouched.

### Layout

Day blocks are 10 rows apart, starting at row 5 (decision 12: constants stay
in `handlers/menu.py`, `NUM_PERIODS = 8`):

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

### Merged lessons

`merge_periods` (in `model.py`, so both `menu` and `dskp` share it) merges
consecutive periods that have the same class, subject and tingkatan **and**
contiguous time (`entry.start == previous.end`). Two back-to-back Bahasa Cina
periods therefore occupy one MENU row covering 07:40–09:00, and a gap in time
ends a run even when the same lesson resumes (risk 4,
[`docs/input-formats.md`](../../../docs/input-formats.md)).

The row index `i` is the index of the merged lesson, not the period number:
merged lesson *i* is written to row `header_row + 1 + i`.

### Time suffix (PAGI / TGH / TPTG)

`_time_with_suffix` is keyed on whole hours: `hour < 11` → `PAGI`,
`11 ≤ hour < 14` → `TGH`, `hour ≥ 14` → `TPTG`.

The fallback is pinned on purpose: only `HH:00` keys are in the cache, and
every real period time has non-zero minutes, so the template really contains
strings like `09:00 PAGI` and `11:30 PAGI`. The golden baselines encode this
(risk 11). Do not "fix" it silently — changing it changes every filled
workbook.

### Where to change what

| I want to change … | It lives in | How |
|---|---|---|
| this week's date | calendar → `MENU!I6` | `--date 2026-09-20`, or edit the `minggu` records |
| which timetable a week uses | `jadual_siri` (or `siri:` in the record) | edit `config/jadual-minggu.yaml` (see [`config/README.md`](../../../config/README.md)) |
| the period times themselves | `PERIOD_TIMES` in `inputs/timetable.py` | edit the table (affects every week at once, risk 4) |
| one period's class / time for one week | **MENU sheet**, columns C–G | `ranse write` on that cell — note the next `ranse fill` for the same week rewrites it |
| the DSKP standards on a day sheet | DSKP blocks | `dskp` handler params; never a time edit |

---

## `fixed_cells` (fill)

Writes the profile's constant cells — teacher name, year — before the later
fillers get their turn:

```yaml
- name: fixed_cells
  params:
    cells:
      - [MENU, "B3:C3", "ALI BIN ABU"]   # writes to the top-left of the range
      - [MENU, "B4", 2026]                # numbers stay numbers
```

- `cells` must be a list of `[sheet, range, value]` triples; anything else is
  a `ProfileError` at build time.
- Values that look like integers are converted with `int(value)` **at write
  time**, not at profile-load time (risk 8) — keep that timing or a type change
  breaks the golden suite.
- A missing sheet is a warning on stderr and the cell is skipped; it does not
  abort the run.
- Because it runs in profile order, a `fixed_cells` entry **after** `menu`
  overrides MENU's own values on a shared cell (risk 9).

---

## `dskp` (fill)

`dskp` fills the standard rows of each class block on the day sheets. It is the
only handler that writes to `AHAD`–`KHAMIS`, and it writes **content only** —
which is exactly why MENU can own all time data (decision 14).

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

- **Block layout** (decision 12, `handlers/dskp.py`): class *n* (1-based)
  starts at row `7 + (n-1) * 31` (`CLASS_BLOCK_SIZE = 31`); from that header
  the handler writes the title row `+6`, the content standard `+7` and the
  learning standard `+9`.
- **Columns**: the left half defaults to column B (`left_col: 2`), the right
  half to column E (`right_col: 5`).
- **Automatic mode** (`mode: auto`, the default): for every merged lesson of a
  matched subject, two **parent-level** sections (`X.0` headings) are written
  side by side, sliding one section forward per week:
  `idx = (minggu - 1) % (len(sections) - 1)` → `keys[idx]`, `keys[idx+1]`.
  When there is no next section the pair wraps back to the first two, so a
  week number alone always determines the content:

  ```
  week 1 → 1.0 Listening and Speaking  |  2.0 Reading
  week 2 → 2.0 Reading  |  3.0 Writing
  ...
  no next section → wrap back to 1.0 + 2.0
  ```
- **Matching**: `match_codes` matches the timetable's subject codes
  (`BC-1A`); `match_names` matches the subject name after `context.subjects`
  mapping (the CSV direction). A subject that matches nothing is skipped.
- **Static entries** (`params.entries`) are written first, then automatic
  entries are appended, so on the same cell the automatic entry wins
  (risk 9).
- **`file`** accepts `{tingkatan}` (`t1.txt`, `t2.txt`, …), a per-tingkatan
  map, or nothing — then the built-in `DSKP_FILES` table is used. The source
  formats (txt / JSON from `ranse dskp`) are specified in
  [`docs/input-formats.md`](../../../docs/input-formats.md).
- **Warnings, not errors**: a missing DSKP file, a file with no usable parent
  sections, or an unknown sheet is reported on stderr and skipped, so one bad
  class does not abort the week.
- `--no-dskp-auto` (or `mode: static`) disables the automatic part for a run;
  with no week known the handler prints a note instead of guessing.

---

## Fill order (risk 9)

Order in the profile's `handlers:` list decides who wins on a shared cell —
the last writer wins. The shipped profile relies on:

1. `menu` writes the week's time data first;
2. `fixed_cells` may override MENU cells (e.g. a hand-written name);
3. `dskp` writes static `entries` first, then automatic ones, so on the same
   cell the automatic entry wins.

Reordering the list changes results; the golden suite will say so.

---

## Risks defined here

| # | Risk |
|---|---|
| 7 | **`menu` writes empty rows as `""`** to clear a previous run's result — do not delete that branch |
| 8 | **`fixed_cells` values pass through an `int(value)` attempt at write time**, not at profile-load time; keep that timing or a type change breaks golden |
| 9 | **Order matters in the fill phase**: static DSKP entries before automatic ones, and the profile's handler order decides who wins on a shared MENU cell |
| 11 | **The PAGI/TGH/TPTG suffix only applies to `HH:00`**; real period times fall back to `PAGI`, and the templates rely on it — changing it changes every filled workbook |
| 12 | **MENU is the only time writer** (decision 14): adding a time write somewhere else (a day sheet, a new handler) breaks the invariant that one sheet decides the week's dates and periods |

Risks 4 and 10 (timetable reading) are defined in
[`docs/input-formats.md`](../../../docs/input-formats.md); the framework risks
(1, 2, 3, 5, 6) in [`docs/DESIGN.md`](../../../docs/DESIGN.md) §10.
