# Profile design — ALI BIN ABU (2026)

Business design of the profile in [`profile.yaml`](profile.yaml). The
framework that loads it is documented in
[`docs/DESIGN.md`](../../docs/DESIGN.md); the handler rules the `handlers:`
list names are indexed in
[`src/ranse/handlers/README.md`](../../src/ranse/handlers/README.md).

## What it fills

The e-RPH workbook of one teacher, one file per week:
`assets/ALI BIN ABU/12. ERPH/2026/*/M{minggu}.xlsx`. `{minggu}` is replaced
with the resolved week number, so a single profile serves the whole year and
the CLI stays week-agnostic.

| Input | Points at | Read by |
|---|---|---|
| `template` | `assets/ALI BIN ABU/12. ERPH/2026/*/M{minggu}.xlsx` | `resolve_template` (framework) |
| `jadual` | `config/jadual-minggu/jadual-minggu.yaml` — the school calendar | the `week` handler |

## Shared context

`context.subjects` maps a subject code to the name written into the workbook.
Two handlers read it (`menu` for the subject column, `dskp` when matching a
CSV), so it lives in `context` and is written once (risk 3, framework):

```yaml
context:
  subjects:
    BC: "BAHASA CINA 华 文"
    BI: "ENGLISH"
```

## Pipeline

| # | Handler | Phase | Why here |
|---|---|---|---|
| 1 | `week` | resolve | date → minggu/siri → timetable path ([rules](../../src/ranse/handlers/week/DESIGN.md)) |
| 2 | `menu` | fill | writes the week's time data to the MENU sheet ([rules](../../src/ranse/handlers/menu/DESIGN.md)) |
| 3 | `fixed_cells` | fill | writes the teacher's name into `MENU!B3:C3` ([rules](../../src/ranse/handlers/fixed_cells/DESIGN.md)) |
| 4 | `dskp` | fill | writes the DSKP standards to the day sheets ([rules](../../src/ranse/handlers/dskp/DESIGN.md)) |

Order is load-bearing (risk 9): `menu` writes first, `fixed_cells` may
override a MENU cell afterwards, and `dskp` runs last so a static entry never
beats an automatic one.

## Business assumptions

- **MENU owns all time data** (D14, risk 12): the week's date and the period
  times live on the MENU sheet and nowhere else — the day sheets carry content
  only.
- **One profile per year** — the template pattern must match exactly one
  workbook per week. If a week matches two files (an old copy in another
  folder), pin it with `inputs.templates`:

  ```yaml
  inputs:
    templates:
      25: "assets/ALI BIN ABU/12. ERPH/2026/07. TMP-NEW/M25.xlsx"
  ```

- A single value is corrected with the escape hatch, not a code change —
  note the next `ranse fill` for the same week rewrites it:

  ```bash
  ranse write --profile profiles/ali-bin-abu/profile.yaml --minggu 33 MENU!B3 "ALI BIN ABU"
  ```

## Risks defined here

The framework risks (1–3, 5–6) are in
[`docs/DESIGN.md`](../../docs/DESIGN.md) S10; this profile relies on the
business risks **4, 7–12**, each defined with the handler or input document
that owns it (see the pipeline table above).
