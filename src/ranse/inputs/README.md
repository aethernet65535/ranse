# Inputs — index

The `inputs/` layer turns source files into model objects; it never touches
the target workbook (decision 8, [`docs/DESIGN.md`](../../../docs/DESIGN.md)
S8). The dependency direction is `cli` / `handlers` → `inputs` → `model`;
`core` never imports from here.

Each reader lives in its own folder, with the format it accepts documented in
that folder's `DESIGN.md`:

| Reader | Reads | Produces | Format |
|---|---|---|---|
| [`timetable/`](timetable/) | a weekly timetable (xlsx or csv) | `Schedule` | [`timetable/DESIGN.md`](timetable/DESIGN.md) |
| [`dskp/`](dskp/) | curriculum documents (txt / pdf) and the JSON they produce | nested section dicts | [`dskp/DESIGN.md`](dskp/DESIGN.md) |
| [`yaml/`](yaml/) | the profile YAML, and any data-file YAML a handler references | `Profile`, calendar config | [`yaml/DESIGN.md`](yaml/DESIGN.md) |

The two YAML **schemas** are contract, not a reader's business, so they are
documented elsewhere: the profile schema in
[`docs/DESIGN.md`](../../../docs/DESIGN.md) S3.3, the example's calendar data
file in [`config/`](../../../config/README.md).

The DSKP reader also runs standalone: `python -m ranse.inputs.dskp`.

## Subcommands a reader declares

A reader may also add a `ranse <name>` subcommand of its own:

| Reader | Subcommand |
|---|---|
| [`dskp/`](dskp/) | `ranse dskp` — parse a DSKP txt/pdf into structured JSON |

The spec is `{"name", "help", "add_arguments", "run"}`, collected into
`SUBCOMMANDS` (`inputs/__init__.py`); `cli.py` adds and dispatches it without
knowing what it does.
