# Inputs — index

The `inputs/` layer turns source files into model objects; it never touches
the target workbook (decision 8, [`docs/DESIGN.md`](../../../docs/DESIGN.md)
S8). The dependency direction is `cli` / `handlers` → `inputs` → `model`;
`core` never imports from here.

Each reader lives in its own folder, with the format it accepts documented in
that folder's `DESIGN.md`:

| Reader | Reads | Produces | Format |
|---|---|---|---|
| [`yaml/`](yaml/) | the profile YAML | `Profile` | [`yaml/DESIGN.md`](yaml/DESIGN.md) |
| [`calendar/`](calendar/) | the school calendar YAML (jadual-minggu) | calendar config dict | [`calendar/DESIGN.md`](calendar/DESIGN.md) |
| [`timetable/`](timetable/) | a weekly timetable (xlsx or csv) | `Schedule` | [`timetable/DESIGN.md`](timetable/DESIGN.md) |
| [`dskp/`](dskp/) | curriculum documents (txt / pdf) and the JSON they produce | nested section dicts | [`dskp/DESIGN.md`](dskp/DESIGN.md) |

The YAML **schemas** are contract, not a reader's business, so they are
documented elsewhere: the profile schema in
[`docs/DESIGN.md`](../../../docs/DESIGN.md) S3.3, the example's calendar data
file in [`config/`](../../../config/README.md).

The DSKP reader also runs standalone: `python -m ranse.inputs.dskp`.

## Subcommands a reader may declare

The shipped registry is deliberately empty: `ranse --help` lists only the
framework's own `fill` / `write`, and `ranse fill` never imports a reader.

A reader that wants a top-level `ranse <name>` command opts in by defining
`SUBCOMMAND` — spec `{"name", "help", "add_arguments", "run"}` — and adding
its name to `_READERS` (`inputs/__init__.py`); `inputs.subcommands()`
collects them and `cli.py` adds and dispatches them without knowing what
they do.
