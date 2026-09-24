# Inputs — index

The `inputs/` layer turns source files into objects; it never touches the
target workbook (decision 8, [`docs/DESIGN.md`](../../../docs/DESIGN.md) S8).
The dependency direction is `cli` / `handlers` → `inputs` → `model`; `core`
never imports from here.

The framework reads exactly one kind of source file itself: the **profile**.
That is bootstrapping, not business — the profile says what to read, so it
has to be read before anything it configures can be found.

| Reader | Reads | Produces | Format |
|---|---|---|---|
| [`yaml/`](yaml/) | the profile YAML | `Profile` | [`yaml/DESIGN.md`](yaml/DESIGN.md) |

**Every other reader belongs to a business** and lives in that business's
plugin: `plugins/<name>/inputs/<reader>/`, one folder per source format, each
with its own `DESIGN.md`. The shipped plugin's readers are indexed in
[`plugins/erph/README.md`](../../../plugins/erph/README.md).

The profile **schema** is contract, not a reader's business, so it is
documented in [`docs/DESIGN.md`](../../../docs/DESIGN.md) S3.3.

## Subcommands a reader may declare

Nothing ships one: `ranse --help` lists only the framework's own `fill` /
`write`, and `ranse fill` imports no reader.

A plugin reader that wants a top-level `ranse <name>` command opts in by
defining `SUBCOMMAND` — spec `{"name", "help", "add_arguments", "run"}`;
[`subcommands()`](__init__.py) collects them from `./plugins` and `cli.py`
adds and dispatches them without knowing what they do.
