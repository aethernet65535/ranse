# `menu` handler (fill)

Fills the MENU sheet with the week's merged lessons. It is the **only**
handler that writes time-related data (decision 14, risk 12).

Protocol/registry contract: [parent index](../README.md).
Framework design: [`docs/DESIGN.md`](../../../../docs/DESIGN.md).

## The MENU sheet is the only place time is written

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

## Layout

Day blocks are 10 rows apart, starting at row 5 (decision 12: constants stay
in this handler's `__init__.py`, `NUM_PERIODS = 8`):

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

## Merged lessons

`merge_periods` (in `model.py`, so both `menu` and `dskp` share it) merges
consecutive periods that have the same class, subject and tingkatan **and**
contiguous time (`entry.start == previous.end`). Two back-to-back Bahasa Cina
periods therefore occupy one MENU row covering 07:40–09:00, and a gap in time
ends a run even when the same lesson resumes (risk 4,
[`docs/input-formats.md`](../../../../docs/input-formats.md)).

The row index `i` is the index of the merged lesson, not the period number:
merged lesson *i* is written to row `header_row + 1 + i`.

## Time suffix (PAGI / TGH / TPTG)

`_time_with_suffix` is keyed on whole hours: `hour < 11` → `PAGI`,
`11 ≤ hour < 14` → `TGH`, `hour ≥ 14` → `TPTG`.

The fallback is pinned on purpose: only `HH:00` keys are in the cache, and
every real period time has non-zero minutes, so the template really contains
strings like `09:00 PAGI` and `11:30 PAGI`. The golden baselines encode this
(risk 11). Do not "fix" it silently — changing it changes every filled
workbook.

## Where to change what

| I want to change … | It lives in | How |
|---|---|---|
| this week's date | calendar → `MENU!I6` | `--date 2026-09-20`, or edit the `minggu` records |
| which timetable a week uses | `jadual_siri` (or `siri:` in the record) | edit `config/jadual-minggu.yaml` (see [`config/README.md`](../../../../config/README.md)) |
| the period times themselves | `PERIOD_TIMES` in `inputs/timetable.py` | edit the table (affects every week at once, risk 4) |
| one period's class / time for one week | **MENU sheet**, columns C–G | `ranse write` on that cell — note the next `ranse fill` for the same week rewrites it |
| the DSKP standards on a day sheet | DSKP blocks | [`dskp` handler](../dskp/DESIGN.md); never a time edit |

## Risks defined here

| # | Risk |
|---|---|
| 7 | **Empty rows are written as `""`** to clear a previous run's result — do not delete that branch |
| 11 | **The PAGI/TGH/TPTG suffix only applies to `HH:00`**; real period times fall back to `PAGI`, and the templates rely on it — changing it changes every filled workbook |
| 12 | **MENU is the only time writer** (decision 14): adding a time write somewhere else (a day sheet, a new handler) breaks the invariant that one sheet decides the week's dates and periods |

Risk numbering continues the global list in
[`docs/DESIGN.md`](../../../../docs/DESIGN.md) §10.
