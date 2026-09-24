# Configuration — index

Data files the shipped profiles reference, one folder each; the folder's
`DESIGN.md` documents the file it holds:

| Folder | Data file | Documented in |
|---|---|---|
| [`school-weeks/`](school-weeks/) | `school-weeks.yaml` — the school week calendar | [`school-weeks/DESIGN.md`](school-weeks/DESIGN.md) |
| [`period-times/`](period-times/) | `period-times.yaml` — period → [start, end] | [`period-times/DESIGN.md`](period-times/DESIGN.md) |

The framework that loads these files is documented in
[`docs/DESIGN.md`](../docs/DESIGN.md); the handler that consumes the calendar
is [`src/ranse/handlers/week/`](../src/ranse/handlers/week/DESIGN.md).
