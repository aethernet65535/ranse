# `week` handler (resolve)

Turns a date into `Week(number, series)` plus a timetable path; it never writes a
cell. Business rules live here in the handler layer, never in core
(decision 6, [`docs/DESIGN.md`](../../../../docs/DESIGN.md)).

Protocol/plugin contract: [parent index](../../README.md).
Calendar format it consumes: [`config/school-weeks/DESIGN.md`](../../config/school-weeks/DESIGN.md).
Timetable formats it resolves to: [`inputs/timetable/DESIGN.md`](../../inputs/timetable/DESIGN.md).

## Resolution rules

1. The week start is the **Sunday** of the date's week (`--date` defaults to
   today; other weekdays roll back to their Sunday). MENU's date cell is that
   Sunday.
2. `weeks` records in the calendar take effect **from their `start` date until
   the next record**. The record whose `start ≤ date` is chosen.
3. `series` comes from the record itself, else from `week_series[week]`.
4. The timetable path is `timetable[series]`, unless the profile sets
   `inputs.timetable` / `inputs.csv`, which win.

## Hard errors

A wrong week would silently fill the wrong content, so all of these abort the
run (printed to stderr + exit 1, decision 13):

- the calendar has no dated `weeks` records;
- the date is earlier than the first record;
- the chosen record is a holiday week (`holiday: …`);
- the chosen record has no `week` number;
- the week has no `series` configured and no explicit timetable input;
- the resolved file does not exist.

## Params and CLI options

The week handler has no `params` of its own — everything it reads lives in the
profile's `inputs:`. It declares the two `ranse fill` options that shape the
week, whose values arrive in `ctx.runtime`:

| Option | Runtime key | Effect |
|---|---|---|
| `--date YYYY-MM-DD` | `date` | the week start (default: the Sunday of the current week) |
| `--week N` | `week` | overrides the week number resolved from the calendar |

The resolver also reads the resolved timetable into `ctx.schedule` (the
orchestrator only opens the workbook and runs the fillers) and prints the
resolved week: `Week N, series S (path)`.
