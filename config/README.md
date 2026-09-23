# The school week calendar — `jadual-minggu.yaml`

This directory holds the standalone **school calendar** data file (decision 11,
[`docs/DESIGN.md`](../docs/DESIGN.md) S3.3). It is not part of any profile: a
profile *references* it via `inputs.jadual`, and the `week` handler reads it
to answer two questions:

1. **Which week is today?** `--date` (default: this week's Sunday) → the
   `minggu` table.
2. **Which timetable does that week use?** `jadual_siri` / `jadual` → the
   timetable file (formats: [`docs/input-formats.md`](../docs/input-formats.md)).

```yaml
# in a profile
inputs:
  jadual: "config/jadual-minggu.yaml"
```

```bash
ranse fill --profile profiles/ali-bin-abu/profile.yaml                  # this week
ranse fill --profile profiles/ali-bin-abu/profile.yaml --date 2026-09-20
```

---

## Structure

```yaml
# siri number → timetable file (relative to the repo root; absolute works too)
jadual:
  1: assets/timetable/jadual-waktu-2026-siri-1.xlsx
  7: assets/timetable/jadual-waktu-2026-siri-7.xlsx

jadual_siri:            # minggu → siri (fill this in)
  33: 7
  34: 7

minggu:                 # each record takes effect from its start date
  - start: 2026-09-20
    minggu: 33
  - start: 2026-09-27
    minggu: 34
```

| Key | Shape | Meaning |
|---|---|---|
| `jadual` | `siri → path` | which timetable file a siri uses |
| `jadual_siri` | `minggu → siri` | which siri a week uses (fill in later) |
| `minggu` | list of dated records | the calendar itself |

Each `minggu` record:

| Field | Required | Meaning |
|---|---|---|
| `start` | yes | effective date (normally a Sunday); the record holds until the next record |
| `minggu` | yes, unless `cuti` | the week number |
| `cuti` | — | marks a **holiday week**; hitting one is a hard error |
| `siri` | no | overrides `jadual_siri` for this record |

---

## Resolution rules

Implemented by the `week` handler; the full rules and error list are in
[`src/ranse/handlers/week/DESIGN.md`](../src/ranse/handlers/week/DESIGN.md). In short:

- records are sorted by `start`; the chosen record is the last one whose
  `start ≤ date`;
- `--minggu N` overrides the record's week number but not the timetable
  lookup chain;
- `siri` precedence: the record's own `siri:` → `jadual_siri[minggu]`;
- timetable precedence: `inputs.timetable` / `inputs.csv` in the profile →
  `jadual[siri]`;
- holiday weeks (`cuti`), missing `minggu` numbers, unconfigured `siri` and
  missing files are **hard errors**, never a silent wrong fill.

---

## Maintaining this file

- The `minggu` table was generated from the school calendar (TARIKH → MINGGU,
  M01…M43). If the school calendar changes, add/remove/edit records — each
  record simply takes effect from its `start` date until the next one.
- `jadual_siri` maps every week to its siri:
  `siri 1: M1-M5`, `siri 2: M6`, `siri 3: M7-M9`, `siri 4: M10-M14`,
  `siri 5: M15-M24`, `siri 6: M25-M28`, `siri 7: M29-M44`.
- The timetable files for **siri 2–6 are not registered under `jadual:`**
  yet, so those weeks currently report a missing-file error.
- Relative paths resolve against this file's directory first, then the repo
  root, then the current directory.

## Cross-references

- Handler rules that consume this file: [`src/ranse/handlers/week/DESIGN.md`](../src/ranse/handlers/week/DESIGN.md)
- Timetable file formats picked here: [`docs/input-formats.md`](../docs/input-formats.md)
- Profile schema (`inputs.jadual`): [`docs/DESIGN.md`](../docs/DESIGN.md) S3.3
- Example profile: [`profiles/ali-bin-abu/profile.yaml`](../profiles/ali-bin-abu/profile.yaml)
