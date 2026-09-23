# `week` handler (resolve)

Turns a date into `Week(minggu, siri)` plus a timetable path; it never writes a
cell. Business rules live here in the handler layer, never in core
(decision 6, [`docs/DESIGN.md`](../../../../docs/DESIGN.md)).

Protocol/registry contract: [parent index](../README.md).
Calendar format it consumes: [`config/jadual-minggu/DESIGN.md`](../../../../config/jadual-minggu/DESIGN.md).
Timetable formats it resolves to: [`inputs/timetable/DESIGN.md`](../../inputs/timetable/DESIGN.md).

## Resolution rules

1. The week start is the **Sunday** of the date's week (`--date` defaults to
   today; other weekdays roll back to their Sunday). MENU's date cell is that
   Sunday.
2. `minggu` records in the calendar take effect **from their `start` date until
   the next record**. The record whose `start ≤ date` is chosen.
3. `siri` comes from the record itself, else from `jadual_siri[minggu]`.
4. The timetable path is `jadual[siri]`, unless the profile sets
   `inputs.timetable` / `inputs.csv`, which win.

## Hard errors

A wrong week would silently fill the wrong content, so all of these abort the
run (printed to stderr + exit 1, decision 13):

- the calendar has no dated `minggu` records;
- the date is earlier than the first record;
- the chosen record is a holiday week (`cuti: …`);
- the chosen record has no `minggu` number;
- the week has no `siri` configured and no explicit timetable input;
- the resolved file does not exist.

## Params and CLI options

The week handler has no `params` of its own — everything it reads lives in the
profile's `inputs:`. It declares the two `ranse fill` options that shape the
week, whose values arrive in `ctx.runtime`:

| Option | Runtime key | Effect |
|---|---|---|
| `--date YYYY-MM-DD` | `date` | the week start (default: the Sunday of the current week) |
| `--minggu N` | `minggu` | overrides the week number resolved from the calendar |
