# Configuration — index

Data files the shipped profiles reference, one folder each; the folder's
`DESIGN.md` documents the file it holds:

| Folder | Data file | Documented in |
|---|---|---|
| [`jadual-minggu/`](jadual-minggu/) | `jadual-minggu.yaml` — the school week calendar | [`jadual-minggu/DESIGN.md`](jadual-minggu/DESIGN.md) |

The framework that loads these files is documented in
[`docs/DESIGN.md`](../docs/DESIGN.md); the handler that consumes the calendar
is [`src/ranse/handlers/week/`](../src/ranse/handlers/week/DESIGN.md).
