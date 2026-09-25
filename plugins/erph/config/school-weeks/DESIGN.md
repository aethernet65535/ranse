# The school week calendar — `school-weeks.yaml`

This folder holds the standalone **school calendar** data file
([`school-weeks.yaml`](school-weeks.yaml), decision 11,
[`docs/DESIGN.md`](../../../../docs/DESIGN.md) S3.3). It is not part of any profile:
a profile *references* it via `inputs.calendar`, and the `week` handler reads it
to answer two questions:

1. **Which week is today?** `--date` (default: this week's Sunday) → the
   `weeks` table.
2. **Which timetable does that week use?** `week_series` / `timetable` → the
   timetable file (formats: [`inputs/timetable/DESIGN.md`](../../inputs/timetable/DESIGN.md)).

```yaml
# in a profile
inputs:
  calendar: "../../config/school-weeks/school-weeks.yaml"
```

```bash
ranse fill --profile plugins/erph/profiles/ali-bin-abu/profile.yaml                  # this week
ranse fill --profile plugins/erph/profiles/ali-bin-abu/profile.yaml --date 2026-09-20
```

---

## Structure

```yaml
# series number → timetable file (relative to the repo root; absolute works too)
# Paths resolve next to this file first, then the current directory, then the
# repo root — see input_bases() in inputs/yaml/ and resource_roots().
timetable:
  1: assets/timetable/jadual-waktu-2026-siri-1.xlsx
  7: assets/timetable/jadual-waktu-2026-siri-7.xlsx

week_series:            # week → series (fill this in)
  33: 7
  34: 7

weeks:                  # each record takes effect from its start date
  - start: 2026-09-20
    week: 33
  - start: 2026-09-27
    week: 34
```

| Key | Shape | Meaning |
|---|---|---|
| `timetable` | `series → path` | which timetable file a series uses |
| `week_series` | `week → series` | which series a week uses (fill in later) |
| `weeks` | list of dated records | the calendar itself |

Each `weeks` record:

| Field | Required | Meaning |
|---|---|---|
| `start` | yes | effective date (normally a Sunday); the record holds until the next record |
| `week` | yes, unless `holiday` | the week number |
| `holiday` | — | marks a **holiday week**; hitting one is a hard error |
| `series` | no | overrides `week_series` for this record |

---

## Resolution rules

Implemented by the `week` handler; the full rules and error list are in
[`handlers/week/DESIGN.md`](../../handlers/week/DESIGN.md).
In short:

- records are sorted by `start`; the chosen record is the last one whose
  `start ≤ date`;
- `--week N` overrides the record's week number but not the timetable
  lookup chain;
- `series` precedence: the record's own `series:` → `week_series[week]`;
- timetable precedence: `inputs.timetable` / `inputs.csv` in the profile →
  `timetable[series]`;
- holiday weeks (`holiday`), missing `week` numbers, unconfigured `series` and
  missing files are **hard errors**, never a silent wrong fill.

---

## Maintaining this file

- The `weeks` table mirrors the school calendar (its official DATA columns
  TARIKH → MINGGU, M01…M43). When the school calendar changes,
  add/remove/edit records — each record takes effect from its `start` date
  until the next one.
- `week_series` maps every week to its series:
  `series 1: M1-M5`, `series 2: M6`, `series 3: M7-M9`, `series 4: M10-M14`,
  `series 5: M15-M24`, `series 6: M25-M28`, `series 7: M29-M44`.
- The timetable files for **series 2–6 are not registered under `timetable:`**
  yet, so those weeks currently report a missing-file error.
- Relative paths resolve against this file's directory first, then the repo
  root, then the current directory.

## Cross-references

- Handler rules that consume this file: [`handlers/week/DESIGN.md`](../../handlers/week/DESIGN.md)
- Timetable file formats picked here: [`inputs/timetable/DESIGN.md`](../../inputs/timetable/DESIGN.md)
- Profile key (`inputs.calendar`, read by the `week` handler): profile schema [`docs/DESIGN.md`](../../../../docs/DESIGN.md) S3.3
- Example profile: [`profiles/ali-bin-abu/profile.yaml`](../../profiles/ali-bin-abu/profile.yaml)
