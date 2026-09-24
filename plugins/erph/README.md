# `erph` plugin — business index

The shipped business: filling Malaysian **e-RPH** (*Rancangan Pengajaran
Harian*) workbooks from a weekly timetable. Everything it needs — handlers,
readers, the profile and the data files — lives in this folder.

The **framework** (the xlsx engine, the CLI, the handler/reader system and
the profile schema) is documented in
[`docs/DESIGN.md`](../../docs/DESIGN.md). This file is the index for the
business: what the shipped handlers do, which readers feed them, and which
data files the profile references. Risk numbers run project-wide.

```
erph/
  domain.py            the business types: Lesson / Schedule / Week / merge_periods
  handlers/            one folder per handler — the folder name is the handler name
    week/  menu/  fixed_cells/  dskp/
  inputs/              one folder per source format — the folder name is the reader name
    calendar/  timetable/  dskp/
  profiles/            the shipped example profile (+ its README / DESIGN)
  config/              the data files that profile references
```

Registration is the folder itself (docs/DESIGN.md D2, revised): the framework
scans `./plugins`, and `handlers/<name>/` or `inputs/<name>/` with a legal
snake_case name and an `__init__.py` is picked up. No manifest, no entry
point, no framework edit.

---

## Handlers

Each handler lives in its own folder, with its business rules in that
folder's `DESIGN.md`:

| Handler | Phase | Rules |
|---|---|---|
| [`week/`](handlers/week/) | resolve | date → week number/series → timetable path ([`week/DESIGN.md`](handlers/week/DESIGN.md)) |
| [`menu/`](handlers/menu/) | fill | the MENU sheet owns all time data (decision 14), layout, clearing ([`menu/DESIGN.md`](handlers/menu/DESIGN.md)) |
| [`fixed_cells/`](handlers/fixed_cells/) | fill | constant cells, `int(value)` timing ([`fixed_cells/DESIGN.md`](handlers/fixed_cells/DESIGN.md)) |
| [`dskp/`](handlers/dskp/) | fill | day-sheet DSKP blocks, automatic section pair ([`dskp/DESIGN.md`](handlers/dskp/DESIGN.md)) |

### Shared handler contract

- handlers are listed explicitly and in order in the profile (decision 1) and
  discovered only from the plugin folders (decision 2);
- `phase: "resolve"` handlers compute `ctx` inputs and **write no cells**;
  `phase: "fill"` handlers are the only code allowed to write, and only
  through `ctx.workbook` (the core write API, `docs/DESIGN.md` S3.1);
- each handler validates its own `params` at build time — a broken profile
  fails before any cell is touched;
- a handler that needs a command-line switch declares it in `cli_options`
  (`{runtime_key: (flags, argparse_kwargs)}`); `ranse fill` adds them and the
  parsed value comes back in `ctx.runtime[runtime_key]`. They are added under
  that handler's own `--help` section, and only when the profile names the
  handler — `ranse fill`'s option surface is the profile's (framework S3.4);
- a handler declares what else it needs in `required_sheets` (sheets the
  workbook must have before any fill) and `requires` (names of `ctx` values
  the resolvers must publish, e.g. `("schedule",)` — the orchestrator only
  checks presence, never interprets the names);
- errors are reported the handler way: `print(…, file=sys.stderr)` +
  `sys.exit(1)` for business errors, `  Warning: …` + skip for skippable
  problems (decision 13).

### Fill order (risk 9)

Order in the profile's `handlers:` list decides who wins on a shared cell —
the last writer wins. The shipped profile relies on:

1. `menu` writes the week's time data first;
2. `fixed_cells` may override MENU cells (e.g. a hand-written name);
3. `dskp` writes static `entries` first, then automatic ones, so on the same
   cell the automatic entry wins.

Reordering the list changes results; the golden suite will say so.

---

## Readers

The readers turn the plugin's source files into the types in
[`domain.py`](domain.py); they never touch the target workbook
(decision 8). Each folder documents the format it accepts:

| Reader | Reads | Produces | Format |
|---|---|---|---|
| [`calendar/`](inputs/calendar/) | the school calendar YAML (`school-weeks.yaml`) | calendar config dict | [`calendar/DESIGN.md`](inputs/calendar/DESIGN.md) |
| [`timetable/`](inputs/timetable/) | a weekly timetable (xlsx or csv) | `Schedule` | [`timetable/DESIGN.md`](inputs/timetable/DESIGN.md) |
| [`dskp/`](inputs/dskp/) | curriculum documents (txt / pdf) and the JSON they produce | nested section dicts | [`dskp/DESIGN.md`](inputs/dskp/DESIGN.md) |

The DSKP reader also runs standalone — from the repository root, with the
plugin folder on the import path:

```bash
PYTHONPATH=plugins python -m erph.inputs.dskp --list
```

The framework's own reader (the profile YAML) lives in
[`src/ranse/inputs/yaml/`](../../src/ranse/inputs/yaml/DESIGN.md).

---

## Data files (`config/`)

The data files the shipped profile references, one folder each; the folder's
`DESIGN.md` documents the file it holds:

| Folder | Data file | Documented in |
|---|---|---|
| [`school-weeks/`](config/school-weeks/) | `school-weeks.yaml` — the school week calendar | [`school-weeks/DESIGN.md`](config/school-weeks/DESIGN.md) |
| [`period-times/`](config/period-times/) | `period-times.yaml` — period → [start, end] | [`period-times/DESIGN.md`](config/period-times/DESIGN.md) |

The profile reaches them with paths relative to its own folder
(`../../config/…`), which is what keeps the plugin self-contained: move the
whole `erph/` folder into another checkout's `plugins/` and its inputs still
resolve.

---

## Profile

[`profiles/ali-bin-abu/`](profiles/ali-bin-abu/) is the shipped example: one
teacher, one workbook per week.

```bash
ranse fill --profile plugins/erph/profiles/ali-bin-abu/profile.yaml --date 2026-09-20
```

Its own [`README.md`](profiles/ali-bin-abu/README.md) and
[`DESIGN.md`](profiles/ali-bin-abu/DESIGN.md) cover the teacher, the
template layout, the subject map and the pipeline.

---

## Risk map

| Risks | Defined in |
|---|---|
| 7, 11, 12 | [`menu/DESIGN.md`](handlers/menu/DESIGN.md) (clearing branch, time suffix, MENU-only time writer) |
| 8 | [`fixed_cells/DESIGN.md`](handlers/fixed_cells/DESIGN.md) (`int(value)` at write time) |
| 9 | this file (fill order, above) |
| 4 | [`inputs/timetable/DESIGN.md`](inputs/timetable/DESIGN.md) + [`config/period-times/DESIGN.md`](config/period-times/DESIGN.md) (one period table, derived reverse direction) |
| 10 | [`profiles/ali-bin-abu/DESIGN.md`](profiles/ali-bin-abu/DESIGN.md) (`context.days`: which day sheets this template has — the reader keeps every day, the fillers select) |
| 1, 2, 3, 5, 6 | [`docs/DESIGN.md`](../../docs/DESIGN.md) S10 (framework) |

## Cross-references

- Framework design: [`docs/DESIGN.md`](../../docs/DESIGN.md)
- School calendar data file: [`config/school-weeks/DESIGN.md`](config/school-weeks/DESIGN.md)
- Example profile: [`profiles/ali-bin-abu/profile.yaml`](profiles/ali-bin-abu/profile.yaml)
