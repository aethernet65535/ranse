# Ranse — Design Document

This document describes the **core framework** — the xlsx engine, the CLI, the
handler system, the profile schema and the pipeline that ties them together.
Business rules are documented next to the code that implements them: one
`DESIGN.md` per handler, reader, profile and data file (see the
documentation map in S2). The numbered **decisions** and **risks** are stable
identifiers across the whole doc set, so a comment that cites "decision N" or
"risk N" means this document or the business document that owns it.

---

## 1. What Ranse is

Ranse is a command-line framework that fills a spreadsheet template **in
place**, driven entirely by a YAML **profile**. It reads source files, decides
what to write, and rewrites the target workbook without disturbing any cell it
does not write.

The framework is business-agnostic. A *business* is a **plugin**: a folder
under `plugins/` holding handlers, readers, the profile and the data files
that configure them. This repository ships one worked example,
`plugins/erph/`, whose rules live entirely in that folder and never leak into
the core described here — that boundary is enforced by CI (S9).

Framework-level guarantees:

- **Write-only core** — nothing in the pipeline reads a value back out of the
  target workbook (D7). There is no `read(coord)`.
- **No business logic in the framework** (D6) — domain concepts (dates,
  subjects, layout constants, calendar semantics) exist only inside a plugin.
- **Fail before writing** — the profile structure, the handler names and every
  handler's `params` are validated before a single cell is touched.
- **One-way dependencies** (S2) — `cli → handlers → core`; readers never
  touch the target workbook (D8); a plugin may import the framework, the
  framework imports a plugin only in the loader.
- **Idempotent re-runs** — handlers are stateless between runs; the same
  inputs always produce the same workbook, so a re-run is always safe.

Non-goals are listed in S11.

---

## 2. Architecture

```
+-- CLI (cli.py) ----------------------------------+
|  ranse fill  --profile p.yaml [handler options]  |  <- no --xlsx: the
|  ranse write --profile p.yaml SHEET!CELL "value" |     workbook is a
|  <reader subcommands: none shipped>              |     profile input (D10)
+--------------+-----------------------------------+
               | argparse + pipeline order + RanseError -> exit code (D13)
+-- handlers/ -v-----------------------------------+
|  base.py       Resolver / Filler protocols + Context |
|  loader.py     the registry: handlers the plugins declare |
+--------------+-----------------------------------+
               | may only write through core's write API
+-- core/ -----v---------------+   +-- inputs/ --------+
|  Workbook.open()/save()      |   |  source readers   |
|  sheet(name)                 |   |  yaml.py: profile |
|  write(coord, content)       |   |  x no target-file |
|  merges (format-preserving)  |   |    reading        |
|  x no read(coord)            |   |                   |
|  x no domain constants       |   |                   |
+------------------------------+   +-------------------+

plugins/<name>/            <- one folder per business; the framework
  handlers/<name>/            discovers it (D2) and never names it
  inputs/<name>/
  domain.py  profiles/  config/
```

Dependency direction is strictly one-way:

- `cli → handlers → core`, and `cli`/`handlers` → `inputs`;
- **`core` must not import `handlers` or `inputs`** (D6);
- **`inputs` never touch the target workbook** (D8) — they only read source
  files and produce objects;
- **only the plugin loader imports a plugin** (`plugins.py`, called from
  `handlers/loader.py` and `inputs.subcommands()`, D2 revised);
- **a plugin imports the framework and its own package only** — never
  another plugin (S9);
- **`core` is write-only** towards the target workbook: there is no
  `read(coord)` (D7).

File map:

| Path | Responsibility |
|---|---|
| `src/ranse/cli.py` | argparse, two-phase orchestration, `RanseError` → `Error: …` + exit 1 |
| `src/ranse/model.py` | `Profile` / `ProfileInputs` / `HandlerSpec` — configuration only, no domain types |
| `src/ranse/plugins.py` | plugin discovery: the `./plugins` scan, `sys.path` bootstrap, name conflicts |
| `src/ranse/errors.py` | `RanseError`, `ProfileError`, `SheetError` |
| `src/ranse/core/refs.py` | A1 ↔ (row, col), range top-left, date serial, path resolution — pure functions |
| `src/ranse/core/format.py` | xlsx format primitives: zip parts, sheet map, shared strings (no domain knowledge) |
| `src/ranse/core/xlsx.py` | write-only `Workbook` / `Sheet`, built on `core/format.py` |
| `src/ranse/inputs/yaml/` | the framework's own reader: the profile (index: `src/ranse/inputs/README.md`) |
| `src/ranse/handlers/base.py` | `Resolver` / `Filler` protocols + `Context` |
| `src/ranse/handlers/loader.py` | the handler registry, built from the discovered plugins (D2) |
| `plugins/<name>/` | one folder per business — handlers, readers, domain types, profiles and data files; index: `plugins/<name>/README.md` |
| `tests/` | unit tests + golden regression baselines |

`model.py` sits at the top level of the package rather than in `core/` because
it is configuration the CLI and the loader share; the **domain** types a
business needs (day names, class groups, week numbers) live in that plugin's
`domain.py`, where the pure write engine cannot see them.

### Documentation map

The framework is documented here; each business area is documented where it
lives:

| Document | Contents |
|---|---|
| `docs/DESIGN.md` (this file) | core framework: engine, CLI, handler system, profile, pipeline |
| `plugins/<name>/README.md` | index of that business: its handlers, readers, profile and data files |
| `plugins/<name>/handlers/<handler>/DESIGN.md` | one document per handler: its rules, params and risks |
| `plugins/<name>/inputs/<reader>/DESIGN.md` | one document per reader: the format it accepts |
| `plugins/<name>/profiles/<profile>/DESIGN.md` | one document per profile: its configuration and business design |
| `plugins/<name>/config/<folder>/DESIGN.md` | one document per data file: its schema |
| `src/ranse/inputs/README.md` | the framework's own reader (the profile YAML) |
| `docs/translations/ms-MY/README.md` | README in Bahasa Melayu |

---

## 3. Interfaces

### 3.1 Core write API (strictly write-only)

```python
class Workbook:
    @classmethod
    def open(cls, path) -> "Workbook": ...
    @property
    def sheets(self) -> list[str]: ...
    def sheet(self, name: str) -> "Sheet": ...
    def write(self, ref: str, content) -> None: ...   # "SHEET!B3" or "SHEET!B3:C3"
    def save(self, path=None) -> None: ...            # None = overwrite in place

class Sheet:
    def write(self, coord: str, content) -> None: ...
    def merges(self) -> list[tuple[int, int, int, int]]: ...
```

Rules:

- **no `read(coord)`** — nothing in the pipeline reads a value back out of the
  target workbook (D7);
- a range or merged-range coordinate writes its **top-left** cell, so every
  caller does not have to do the merge lookup by hand;
- strings are written as `t="inlineStr"` + `<is><t>`, numbers as `<v>`, and
  **every other attribute of the `<c>` element is preserved** (style,
  number format, …);
- missing `<row>` / `<c>` elements are created and re-sorted into order.

### 3.2 Handler protocol and `Context`

```python
@dataclass
class Context:
    profile; workbook=None
    template_vars={}   # values resolvers publish for the {…} template
                       # placeholders (e.g. {"week": 33})
    params={}          # params of the handler currently running
    runtime={}         # values of the handler-declared CLI options
    report=[]

class Resolver(Protocol):   # phase one: compute inputs, write no cells
    name: str
    phase: str               # "resolve"
    def resolve(self, ctx: Context) -> None: ...

class Filler(Protocol):     # phase two: write cells through core only
    name: str
    phase: str               # "fill"
    def fill(self, ctx: Context) -> list[str]: ...   # returns report lines
```

Handlers are looked up by name in `handlers/loader.py`, which builds the
registry from the plugins under `./plugins` (D2 revised), and each handler
validates its own `params` at build time — an unknown name or a malformed
`params` fails **before any cell is touched**. A handler may only write
through `ctx.workbook`, which is the core API of S3.1. A handler may declare
what it needs as class attributes: `cli_options` (the `ranse fill` options it
adds, S3.4), `required_sheets` (sheets the workbook must have before any
fill) and `requires` (names of context values this filler cannot run without
— the orchestrator only checks presence, never interprets the names: they are
the handlers' own vocabulary).

A resolve-phase handler **publishes** the values the rest of the run needs by
setting them on the context (`ctx.<name> = value`) and, for the `{…}`
placeholders in `inputs.template`, into `ctx.template_vars`. The framework
stores what a resolver publishes and never interprets it, so no domain type
crosses the framework boundary in either direction.

The shipped plugin's handlers and everything they compute are documented per
handler in `plugins/erph/handlers/<name>/DESIGN.md` (index:
`plugins/erph/README.md`).

### 3.3 Profile schema

```yaml
profile: example-2026

inputs:
  template: "path/to/*/W{week}.xlsx"   # required
  # every other key is handler-specific; the shipped plugin's profile adds a
  # calendar file, a timetable and a curriculum source here (see its DESIGN)
  # templates: {25: "…/W25.xlsx"}       # pin one week when the pattern matches twice

context:
  # values shared by several handlers, written once (e.g. a lookup table)

handlers:
  - name: <resolve-handler>
  - name: <fill-handler>
    params:
      # handler-specific params, see plugins/erph/README.md
```

Schema:

| Section | Shape | Meaning |
|---|---|---|
| `inputs` | mapping | where the files live; `template` is **required** (D10), everything else optional and handler-specific |
| `context` | mapping | values shared by several handlers, so a value used twice is written once |
| `handlers` | ordered list of `{name, params}` | the pipeline itself (D1); a name must be one a plugin provides (D2) |

Validation rules: a missing `inputs.template` or a malformed `handlers:` list
raises `ProfileError` from the `inputs/yaml/` reader; an unknown handler name or
invalid handler params raises `ProfileError` from the plugin loader (it lists
the names it did find, or says there are no plugins under `./plugins`).
Relative paths resolve against the profile's own directory, then the current
directory, then — only in a source checkout — the repo root
(`inputs.input_bases`; an installed package has no repo root, so the fallback
stays out of the way). Plugin discovery searches `./plugins` the same way.

`inputs.template` may contain the `{week}` placeholder — substituted with the
number a resolve-phase handler publishes in `ctx.template_vars` — and glob
wildcards; it must match exactly one workbook, otherwise the error lists the
candidates. `inputs.templates` pins a specific workbook by that number and
wins over the pattern (D10).

`week` is the one name the framework itself carries here, exactly like the
`fill` / `write` subcommands: the profile names it, the placeholder
substitution and the `inputs.templates` key are defined in terms of it, and
everything else a resolver publishes stays opaque (S3.2). The framework never
derives a week number — only the handler knows one.

Standalone data files are never inlined into the profile: a profile
*references* them from `inputs`, and the handlers that read them own their
formats (D11).

### 3.4 CLI

```
ranse fill  --profile P [handler options]
ranse write --profile P SHEET!CELL VALUE
```

`fill` and `write` are the only subcommands the framework ships, so
`ranse --help` carries no business vocabulary. A plugin reader may still
declare one of its own by defining a `SUBCOMMAND` spec;
`inputs.subcommands()` collects them from the discovered plugins, so the
framework adds and dispatches a subcommand without knowing what it does, and
`ranse fill` never imports a reader.

A plugin's reader can also run as its own module — the shipped plugin's
document reader does, from the repository root:

```bash
PYTHONPATH=plugins python -m erph.inputs.dskp --list
```

`ranse fill` adds only `--profile` itself. Every other option is declared by
a handler (`cli_options`) and its value reaches that handler through
`ctx.runtime`; the handler's own `DESIGN.md` says what it means. `ranse write`
has no options of its own either: it runs the profile's resolve phase to find
the workbook, then writes the one cell.

There is deliberately **no `--xlsx`**: the workbook is a profile input, so a
mistake in the shell cannot overwrite the wrong file (D10).

`ranse write` always writes **text**; a value that must stay a number belongs
in a handler (see that handler's `DESIGN.md`).

---

## 4. Settled decisions

These were agreed with the maintainer and are not up for re-litigation. The
identifiers are cited from code and tests as "decision N". D1–D13 are the
framework decisions; D14 is a business decision and is defined with the
handler that owns it.

| # | Item | Decision |
|---|---|---|
| D1 | Profile shape | An **explicit ordered `handlers:` list**; do not support both an implicit and an explicit form |
| D2 | Handler discovery | **Local directory scan**: the folders under `./plugins` are the registry (`plugins/<name>/handlers/<handler>/` = handler, `inputs/<reader>/` = reader, the folder name is the name). No manifest file, no dynamic import path, no entry point, no install metadata — dropping a directory in is the whole registration step. *Revised from "built-in registry only"; the framework is now plugin-agnostic and `src/ranse` carries no handler or reader names.* |
| D3 | Packaging | An **installable package**; no loose script entry point at the repo root |
| D4 | Equivalence check | Write the **golden regression tests before touching business code** |
| D5 | Extra scope | Use dataclasses for the model; keep the README and its translation in sync; generator tooling lives with the business that uses it (the shipped plugin's readers). *Extended by the plugin reorganisation: the repository is fully anglicized outside the frozen artifacts, so the code references in the translation follow the code.* |
| D6 | Framework constraint | **No business logic in the framework**: no domain constants, no domain vocabulary, no `sys.exit` — and no business name at all, in any language (CI: S9) |
| D7 | Core boundary | Core is **write-only** towards the target workbook: `open / sheet / write / save`; **no `read(coord)`** |
| D8 | Input reading | Lives in a separate **`inputs/` layer** (the source readers + YAML loaders); it never touches the target workbook |
| D9 | Single-cell writes | Both layers: the core API `wb.write("SHEET!B3", "value")` **and** the CLI subcommand `ranse write` |
| D10 | Template path | **`--xlsx` is a profile-only parameter** (`inputs.template`); it is not on the CLI |
| D11 | Standalone data files | Data files are **referenced by the profile**, never merged into it: a handler reads them through `inputs` |
| D12 | Layout constants | Layout constants (row formulas, column numbers, block sizes) **stay in the handlers for v1**; they do not go into the profile |
| D13 | Error handling | Core raises `RanseError` subclasses; the CLI maps them to `Error: …` + exit code 1. Handlers and inputs keep `print(..., file=sys.stderr)`; **no logging framework** |

---

## 5. Lifecycle (two-phase orchestration)

`ranse fill` runs one deterministic pipeline (`cli.py`):

1. **Load the profile** (the `inputs/yaml/` reader), **discover the plugins**
   (`./plugins`) and **build the handlers** from them (the loader): unknown
   names and bad params fail here, before any I/O to the workbook.
2. **Resolve phase** — every handler with `phase == "resolve"` runs in profile
   order. Resolvers read the source files and compute `ctx` inputs (the week,
   the schedule) and publish `ctx.template_vars`; they write no cells.
3. **Pick the workbook** — `resolve_template()` substitutes `{week}` from
   `ctx.template_vars` and resolves glob wildcards; zero matches or several
   matches are both errors that list the candidates and point at
   `inputs.templates`.
4. **Open it** (`Workbook.open`) and check that the sheets the handlers
   declared (`required_sheets`) are present. The target workbook stays
   write-only throughout.
5. **Fill phase** — every handler with `phase == "fill"` runs in profile
   order. **Order is significant**: the last writer wins on a shared cell
   (risk 9, defined with the handlers).
6. **Save** (`wb.save()` overwrites the template in place) and print the
   report.

Handlers are stateless between runs: the same inputs produce the same result
whatever ran before, so a re-run is always safe.

---

## 6. Errors and exit codes

- `core` / `inputs` raise `RanseError` subclasses (`ProfileError`,
  `SheetError`).
- `cli` catches `RanseError` and prints `Error: <message>` on stderr, exit 1.
- Handlers report their own errors: `print(…, file=sys.stderr)` +
  `sys.exit(1)` for business errors, and a `  Warning: …` line for skippable
  problems.
- argparse usage errors go through `parser.error` and exit 2.

Anything that could fill the wrong cell is a hard error; a skippable problem
is a warning. Which is which is a business decision, documented with the
handler that raises it.

---

## 7. Workbook engine (core)

An xlsx is a zip of XML parts. Ranse deliberately avoids `openpyxl`: it edits
the sheet XML directly so that styles, merged cells, borders and print settings
survive untouched.

- `Workbook.open()` reads **all zip entries into memory**, parses
  `xl/workbook.xml` + `xl/_rels/workbook.xml.rels` to map sheet names to parts,
  and registers the XML namespaces **once** (the `ET.register_namespace` side
  effect lives here, not in every parse) with the exact prefixes/URIs the
  templates use (risk 1).
- Sheets are parsed **lazily** on first access and cached.
- `save()` re-serializes **only the sheets that received a write**; every other
  zip entry is copied through **byte-for-byte**, so untouched parts of the
  template cannot drift.
- `save()` builds the zip in a **temporary file next to the target** and
  renames it into place, so a run stopped mid-write (Ctrl+C, a crash) leaves
  the previous workbook intact instead of a truncated one.
- Serialized sheets keep the original declaration and formatting:
  `xml_declaration=True, encoding="UTF-8", short_empty_elements=False`.
- Writes are merge-aware: the coordinate's top-left cell is used, and if it
  falls inside a merged area, the area's top-left cell is used.

The engine is intentionally dumb: no domain names, no domain constants, no
exit codes (D6).

---

## 8. Inputs layer

`inputs/` turns source files into objects; it never writes the target
workbook (D8), and `core` has no import from this layer.

The framework reads exactly one kind of source file itself: the **profile**,
in `inputs/yaml/`. That is bootstrapping rather than business — the profile
says what to read, so it has to be read before anything it configures can be
found.

Every other reader belongs to a business and lives in that business's plugin,
`plugins/<name>/inputs/<reader>/`, one folder per source format; the folder
name is the reader name. Each reader documents the format it accepts in its
own `DESIGN.md`, and the plugin's `README.md` indexes them.

### 8.1 Plugin discovery

`plugins.py` is the framework's only plugin-aware module. It:

- scans `./plugins` (current directory first, then — only in a source
  checkout — the repository root, the same fallback the input paths use);
- accepts a plugin folder when it is a legal snake_case package
  (`__init__.py` present) and registers `handlers/<name>/` and
  `inputs/<name>/` inside it;
- puts the plugin root on `sys.path` so `<plugin>.handlers.<name>` imports,
  and imports each folder once;
- fails at load time when two plugins declare the same name, listing both
  sources — a profile naming an ambiguous handler would be a bug, not a
  preference.

A handler folder registers by convention: its `__init__.py` defines exactly
one class carrying `name = "<folder name>"` and `phase = "resolve" | "fill"`.
The loader looks for nothing else — no manifest, no decorator, no entry
point.

---

## 9. Testing

Three layers, all of which must stay green (D4):

1. **Pure unit tests** — no `assets/` dependency, so a fresh clone can run
   them: cell-reference round trips, date serials, the section-pair sliding
   and wrap, lesson merging (contiguous runs merge, gaps do not), week
   resolution, class-code parsing, and the time-suffix boundaries.
2. **Golden regression** — fills a **temporary copy** of the example's
   template and compares each sheet's XML bytes against
   `tests/golden/<case>/<sheet>.xml.gz`. The case table lives in
   `tests/harness.py`; regenerate the baselines with `tests/make_golden.py`.

Baselines are per-sheet XML, never whole-zip bytes: zip entry order and
timestamps would produce false diffs (risk 2). The suite **skips** when
`assets/` is missing (gitignored), which is why the unit tests must be
self-contained (risk 5).

The golden cases pin the **shipped example**: a change to a handler rule in
`plugins/erph/` must regenerate them deliberately.

3. **Architecture** (`tests/test_architecture.py`) turns the two contracts
   above into CI assertions instead of conventions:

   - **dependency direction** — `core` imports nothing above it; a plugin is
     imported only by the plugin loader; `importlib` / `sys.path` appear only
     in that loader; a plugin imports the framework and its own package only;
   - **vocabulary neutrality** — the scan runs over **every** `.py` file of
     `src/ranse`, with an empty whitelist, and fails on either the old Malay
     vocabulary (`jadual`, `minggu`, the seven Malay day names, …) or the
     business concepts in English (`lesson`, `timetable`, `calendar`,
     `holiday`, …). `DSKP` / `ERPH` are never scanned: they *are* the
     business, and the requirement was to leave those two names alone.

   Inside a plugin the business vocabulary is expected. The exception is the
   **frozen spellings of the source artifacts** — the timetable's headers and
   the workbook's day-sheet names — which may only live in the plugin's
   mirror module (`plugins/erph/domain.py`), whitelisted by file **with a
   reason** and kept honest by a test. Everything downstream of a reader
   speaks canonical English.

   Two guards keep the scan meaningful: one asserts the word lists still
   contain the full Malay set, one feeds the scanner a sample file and
   expects it to catch the words — a scan that silently passes everything is
   worse than no scan.

---

## 10. Risks and pitfalls

Numbering is global and stable across the project: a comment that cites
"risk N" means this document (the framework risks below) or the business
document that owns the rule (risks 4, 7–12).

1. **Serialization must be byte-for-byte**: keep
   `xml_declaration=True, encoding="UTF-8", short_empty_elements=False` and
   every `register_namespace` prefix/URI, or every golden test fails.
2. **Golden compares sheet XML, not zip bytes.**
3. **Values shared by two handlers belong in `context:`** — not duplicated
   into both handlers' params.
5. **`assets/` is not committed** → regression tests skip on a fresh clone; the
   pure-function tests are the safety net there.
6. **The template is large and overwritten in place** → always copy it to a
   temp directory before filling it in a test.

Risks 4 and 7–12 are business risks: each is defined next to the rule that
carries it (see the documentation map, S2).

---

## 11. Out of scope and future work

Not to be done with the current design:

- introducing `openpyxl` (or any library that rewrites the whole workbook);
- a logging framework, or rewording the existing error messages;
- moving layout constants (row formulas, column numbers) into the profile
  (D12);
- installing plugins as packages: they are local directories under
  `./plugins`, with no entry point and no install metadata (D2). The wheel
  ships the framework only;
- a loose script entry point at the repo root (D3);
- edits under the example's asset directory — `assets/`, and every spelling
  a real workbook or source file carries, is frozen.

Planned or possible later:

- a standalone Windows executable (no Python required);
- an optional core read API, if a feature ever needs to inspect values before
  writing;
- per-week overrides of time data, expressed as workbook values rather than a
  second source of times;
- the remaining source files the example's configuration expects.
