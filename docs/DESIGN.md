# Ranse — Design Document

**Status:** as-built design of the **core framework** — the xlsx engine, the
CLI, the handler system, the profile schema and the pipeline that ties them
together. Business rules are documented next to the code that implements
them: one `DESIGN.md` per shipped handler and per shipped profile (see the
documentation map in S2). The numbered **decisions** and **risks** are stable
identifiers across the whole doc set, so a comment that cites "decision N" or
"risk N" means this document or the business document that owns it.

---

## 1. What Ranse is

Ranse is a command-line framework that fills a spreadsheet template **in
place**, driven entirely by a YAML **profile**. It reads source files, decides
what to write, and rewrites the target workbook without disturbing any cell it
does not write.

The framework is business-agnostic. A *business* is a set of handlers plus the
input files and the profile that configure them; this repository ships one
worked example, whose rules live entirely in `handlers/`, `inputs/` and
`profiles/` and never leak into the core described here.

Framework-level guarantees:

- **Write-only core** — nothing in the pipeline reads a value back out of the
  target workbook (D7). There is no `read(coord)`.
- **No business logic in core** (D6) — domain concepts (dates, subjects,
  layout constants, calendar semantics) exist only in `handlers/` and
  `inputs/`.
- **Fail before writing** — the profile structure, the handler names and every
  handler's `params` are validated before a single cell is touched.
- **One-way dependencies** (S2) — `cli → handlers → core`; `inputs` produce
  model objects and never touch the target workbook (D8).
- **Idempotent re-runs** — handlers are stateless between runs; the same
  inputs always produce the same workbook, so a re-run is always safe.

Non-goals are listed in S12.

---

## 2. Architecture

```
+-- CLI (cli.py) ----------------------------------+
|  ranse fill  --profile p.yaml [--date][--minggu] |  <- no --xlsx: the
|  ranse write --profile p.yaml SHEET!CELL "value" |     workbook is a
|  <input-specific subcommands>                    |     profile input (D10)
+--------------+-----------------------------------+
               | argparse + pipeline order + RanseError -> exit code (D13)
+-- handlers/ -v-----------------------------------+
|  base.py       Resolver / Filler protocols + Context |
|  registry.py   built-in registry (only discovery, D2) |
|  <name>/       one folder per handler, + its own DESIGN.md |
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
```

Dependency direction is strictly one-way:

- `cli → handlers → core`, and `cli`/`handlers` → `inputs`;
- **`core` must not import `handlers` or `inputs`** (D6);
- **`inputs` never touch the target workbook** (D8) — they only read source
  files and produce model objects;
- **`core` is write-only** towards the target workbook: there is no
  `read(coord)` (D7).

File map:

| Path | Responsibility |
|---|---|
| `src/ranse/cli.py` | argparse, two-phase orchestration, `RanseError` → `Error: …` + exit 1 |
| `src/ranse/model.py` | `Lesson` / `Schedule` / `Week` / `Profile` dataclasses, `merge_periods` |
| `src/ranse/errors.py` | `RanseError`, `ProfileError`, `WeekError`, `SheetError` |
| `src/ranse/core/refs.py` | A1 ↔ (row, col), range top-left, date serial, path resolution — pure functions |
| `src/ranse/core/xlsx.py` | zip container + write-only `Workbook` / `Sheet` |
| `src/ranse/inputs/` | readers for the example's source files; formats in `docs/input-formats.md` |
| `src/ranse/handlers/base.py` | `Resolver` / `Filler` protocols + `Context` |
| `src/ranse/handlers/registry.py` | the built-in registry (the only discovery, D2) |
| `src/ranse/handlers/<name>/` | one folder per shipped handler, business rules in that folder's `DESIGN.md` |
| `profiles/<name>/` | one shipped profile per folder: `profile.yaml` + `README.md` + `DESIGN.md` |
| `tests/` | unit tests + golden regression baselines |

`model.py` sits at the top level of the package rather than in `core/` because
the model carries domain semantics (day names, class groups, week numbers)
that the pure write engine must not know about.

### Documentation map

The framework is documented here; each business area is documented where it
lives:

| Document | Contents |
|---|---|
| `docs/DESIGN.md` (this file) | core framework: engine, CLI, handler system, profile, pipeline |
| `src/ranse/handlers/README.md` | index of the shipped handlers; each handler carries its own `DESIGN.md` |
| `profiles/<name>/DESIGN.md` | one document per shipped profile: its business design and configuration |
| `docs/input-formats.md` | the on-disk formats the `inputs/` readers accept |
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
    profile; workbook=None; schedule=None; week=None; start_date=None
    params={}          # params of the handler currently running
    runtime={}         # CLI overrides, set by the orchestrator
    timetable_path=None; timetable_is_csv=False
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

Handlers are looked up by name in `handlers/registry.py` (built-in only, D2),
and each handler validates its own `params` at build time — an unknown name or
a malformed `params` fails **before any cell is touched**. A handler may only
write through `ctx.workbook`, which is the core API of S3.1.

The shipped handlers and everything they compute are documented per handler in
`src/ranse/handlers/<name>/DESIGN.md` (index: `src/ranse/handlers/README.md`).

### 3.3 Profile schema

```yaml
profile: example-2026

inputs:
  template: "path/to/*/W{minggu}.xlsx"   # required
  # every other key is handler-specific; the shipped example adds a calendar
  # file, a timetable and a curriculum source here (see its DESIGN.md)
  # templates: {25: "…/W25.xlsx"}       # pin one week when the pattern matches twice

context:
  # values shared by several handlers, written once (e.g. a lookup table)

handlers:
  - name: <resolve-handler>
  - name: <fill-handler>
    params:
      # handler-specific params, see src/ranse/handlers/README.md
```

Schema:

| Section | Shape | Meaning |
|---|---|---|
| `inputs` | mapping | where the files live; `template` is **required** (D10), everything else optional and handler-specific |
| `context` | mapping | values shared by several handlers, so a value used twice is written once |
| `handlers` | ordered list of `{name, params}` | the pipeline itself (D1); names must exist in the registry (D2) |

Validation rules: a missing `inputs.template` or a malformed `handlers:` list
raises `ProfileError` from `inputs/yaml.py`; an unknown handler name or invalid
handler params raises `ProfileError` from the registry. Relative paths resolve
against the profile's own directory, then the current directory, then the repo
root.

`inputs.template` may contain `{minggu}` (substituted once the week number is
known) and glob wildcards; it must match exactly one workbook, otherwise the
error lists the candidates and points at `inputs.templates` (D10). Standalone
data files are never inlined into the profile: a profile *references* them
from `inputs`, and the handlers that read them own their formats (D11).

### 3.4 CLI

```
ranse fill  --profile P [--date YYYY-MM-DD] [--minggu N] [handler flags]
ranse write --profile P [--minggu N] SHEET!CELL VALUE
```

`fill` and `write` are the framework subcommands; the example adds an
input-specific subcommand documented with that input.

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
| D2 | Handler discovery | **Built-in registry only** — no dynamic import paths, no entry-point plugins |
| D3 | Packaging | An **installable package**; there is no legacy script entry point |
| D4 | Equivalence check | Write the **golden regression tests before touching business code** |
| D5 | Extra scope | dict → dataclass; README kept in sync with its translation; the standalone generator script absorbed into `inputs/` |
| D6 | Core constraint | **No business logic in core**: no domain constants, no domain vocabulary, no `sys.exit` |
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

1. **Load the profile** (`inputs/yaml.py`) and **build the handlers**
   (registry): unknown names and bad params fail here, before any I/O to the
   workbook.
2. **Resolve phase** — every handler with `phase == "resolve"` runs in profile
   order. Resolvers compute `ctx` inputs (the week, the paths to read) and
   write no cells.
3. **Pick the workbook** — `resolve_template()` substitutes `{minggu}` and
   resolves glob wildcards; zero matches or several matches are both errors
   that list the candidates and point at `inputs.templates`.
4. **Open it** (`Workbook.open`) and check that the sheets the profile's
   handlers need are present.
5. **Read the source inputs** into model objects. The target workbook stays
   write-only throughout.
6. **Fill phase** — every handler with `phase == "fill"` runs in profile
   order. **Order is significant**: the last writer wins on a shared cell
   (risk 9, defined with the handlers).
7. **Save** (`wb.save()` overwrites the template in place) and print the
   report.

Handlers are stateless between runs: the same inputs produce the same result
whatever ran before, so a re-run is always safe.

---

## 6. Errors and exit codes

- `core` / `inputs` raise `RanseError` subclasses (`ProfileError`,
  `WeekError`, `SheetError`).
- `cli` catches `RanseError` and prints `Error: <message>` on stderr, exit 1.
- Handlers keep the legacy style: `print(…, file=sys.stderr)` +
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
- Serialized sheets keep the original declaration and formatting:
  `xml_declaration=True, encoding="UTF-8", short_empty_elements=False`.
- Writes are merge-aware: the coordinate's top-left cell is used, and if it
  falls inside a merged area, the area's top-left cell is used.

The engine is intentionally dumb: no domain names, no domain constants, no
exit codes (D6).

---

## 8. Inputs layer

`inputs/` turns source files into model objects; it never writes the target
workbook (D8). It holds the YAML loaders (the profile, and any data file a
handler references) plus one reader per source format. The formats are
specified in `docs/input-formats.md`; `core` has no import from this layer.

---

## 9. Testing

Two layers, both must stay green (D4):

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
`src/ranse/handlers/` must regenerate them deliberately.

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

## 11. Implementation history

The current layout was reached in five stages, one commit each, with the golden
suite green at every step (D4). Test comments cite these as "stage N":

| Stage | Content |
|---|---|
| 0 | Fold in the work-in-progress changes; add `pyproject.toml`, the golden baselines and the pure-function unit tests (baselines taken from the **working tree**, not from the previous commit) |
| 1 | Pure move into `src/ranse/` — imports and file placement only, no logic or string changes |
| 2 | De-business-ify `core` (`RanseError` instead of `sys.exit`), extract the example's handlers into their own folders, drop `sys.path.insert` + the dynamic generator import, move the namespace registration into `Workbook` |
| 3 | Profile schema + two-phase orchestration + dataclasses (`Lesson` / `Schedule` / `Week` / `Profile`) |
| 4 | Packaging (`ranse` console script), the subcommands, delete `scripts/`, rewrite README + the Malay translation |

---

## 12. Out of scope and future work

Not to be done with the current design:

- introducing `openpyxl` (or any library that rewrites the whole workbook);
- a logging framework, or rewording the existing error messages;
- moving layout constants (row formulas, column numbers) into the profile
  (D12);
- dynamic third-party handler loading (D2);
- a legacy script entry point (D3);
- edits under the example's asset directory.

Planned or possible later:

- a standalone Windows executable (no Python required);
- an optional core read API, if a feature ever needs to inspect values before
  writing;
- per-week overrides of time data, expressed as workbook values rather than a
  second source of times;
- the remaining source files the example's configuration expects.
