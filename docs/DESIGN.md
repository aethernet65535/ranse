# Ranse — Design Document

**Status:** as-built design of the **core framework**. This document covers the
framework only — the xlsx engine, the CLI, the handler system, the profile
schema and the pipeline that ties them together. The business rules of the
shipped e-RPH filling are documented next to the code that implements them
(§2, Documentation map). The numbered **decisions** (D1–D14) and **risks**
(1–12) are stable identifiers across the whole doc set: code and test comments
that cite "decision N" or "risk N" mean §4 and §10 here, or the business
document §10 points at.

---

## 1. What Ranse is

Ranse is a command-line framework that fills a spreadsheet template **in
place**, driven entirely by a YAML **profile**. It reads source files (a
school calendar, a weekly timetable, curriculum documents), decides what to
write, and rewrites the target workbook without disturbing any cell it does
not write.

The shipped business — filling Malaysian **e-RPH** (*Rancangan Pengajaran
Harian*) workbooks from a weekly timetable — is one configuration of that
framework: four handlers plus a calendar file. None of its knowledge lives in
the framework itself.

Framework-level guarantees:

- **Write-only core** — nothing in the pipeline reads a value back out of the
  target workbook (D7). There is no `read(coord)`.
- **No business logic in core** (D6) — dates, subjects, layout constants and
  school-week semantics exist only in `handlers/` and `inputs/`.
- **Fail before writing** — the profile structure, the handler names and every
  handler's `params` are validated before a single cell is touched.
- **One-way dependencies** (§2) — `cli → handlers → core`; `inputs` produce
  model objects and never touch the target workbook (D8).
- **Idempotent re-runs** — handlers are stateless between runs; the same
  inputs always produce the same workbook, so re-running a week is safe.

Non-goals are listed in §12.

---

## 2. Architecture

```
+-- CLI (cli.py) -----------------------------------+
|  ranse fill  --profile p.yaml [--date][--minggu]  |  <- no --xlsx: the
|  ranse write --profile p.yaml MENU!B3 "value"     |     workbook is a
|  ranse dskp  --txt ... --select 1 1 1 -o out.json |     profile input (D10)
+--------------+------------------------------------+
               | argparse + pipeline order + RanseError -> exit code (D13)
+-- handlers/ -v------------------------------------+
|  base.py       Resolver / Filler protocols + Context |
|  registry.py   built-in registry (the only discovery, D2) |
|  business handlers: week / menu / fixed_cells / dskp   |
+--------------+------------------------------------+
               | may only write through core's write API
+-- core/ -----v---------------+   +-- inputs/ --------+
|  Workbook.open()/save()      |   |  timetable.py     |
|  sheet(name)                 |   |  dskp.py          |
|  write(coord, content)       |   |  yaml.py          |
|  merges (format-preserving)  |   |  x no workbook    |
|  x no read(coord)            |   |    reading of the |
|  x no DAY_ORDER/PERIOD_TIMES |   |    target file    |
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
| `src/ranse/core/refs.py` | A1 ↔ (row, col), range top-left, Excel date serial, path resolution — pure functions |
| `src/ranse/core/xlsx.py` | zip container + write-only `Workbook` / `Sheet` |
| `src/ranse/inputs/timetable.py` | timetable csv/xlsx → `Schedule`; `PERIOD_TIMES`, `TIME_PERIOD`, `DAY_ORDER` |
| `src/ranse/inputs/dskp.py` | DSKP txt/pdf parsing, `resolve_selection`, the `ranse dskp` CLI |
| `src/ranse/inputs/yaml.py` | profile + calendar loading and validation, `resolve_template` |
| `src/ranse/handlers/` | the built-in handlers — one folder each, **business rules live in that folder's README** |
| `profiles/*.yaml` | one profile per teacher/template |
| `config/jadual-minggu.yaml` | standalone school calendar (D11) |
| `tests/` | unit tests + golden regression baselines |

`model.py` sits at the top level of the package rather than in `core/` because
`Lesson`/`Schedule`/`Week` carry timetable and e-RPH semantics (day names,
tingkatan, week numbers) that the pure write engine must not know about.

### Documentation map

The framework is documented here; each business area is documented where it
lives:

| Document | Contents |
|---|---|
| `docs/DESIGN.md` (this file) | core framework: engine, CLI, handler system, profile, pipeline |
| `src/ranse/handlers/README.md` | shipped handler business rules — **index**; each handler has its own folder + README |
| `docs/input-formats.md` | source file formats: timetable xlsx/csv, DSKP txt/pdf/json |
| `config/README.md` | the school week calendar (`jadual-minggu.yaml`) |
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
    def write(self, ref: str, content) -> None: ...   # "MENU!B3" or "MENU!B3:C3"
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
    runtime={}         # --date / --minggu / --no-dskp-auto
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
write through `ctx.workbook`, which is the core API of §3.1.

The shipped handlers (`week`, `menu`, `fixed_cells`, `dskp`) and everything
they compute are documented per handler in `src/ranse/handlers/<name>/DESIGN.md`
(index: `src/ranse/handlers/README.md`).

### 3.3 Profile schema

```yaml
profile: ali-bin-abu-2026

inputs:
  template: "assets/ALI BIN ABU/12. ERPH/2026/*/M{minggu}.xlsx"  # required
  jadual: "config/jadual-minggu.yaml"
  # templates: {25: "…/M25.xlsx"}   # pin a week when the pattern is ambiguous
  # timetable: "…/jadual-waktu-2026-siri-7.xlsx"
  # csv: "…/timetable.csv"

context:
  subjects:
    BC: "BAHASA CINA 华 文"

handlers:
  - name: week
  - name: menu
  - name: fixed_cells
    params:
      cells: [[MENU, "B3:C3", "ALI BIN ABU"]]
  - name: dskp
    params:
      mode: auto
      # … handler-specific params, see src/ranse/handlers/README.md
```

Schema:

| Section | Shape | Meaning |
|---|---|---|
| `inputs` | mapping | where the files live; `template` is **required** (D10), everything else optional |
| `context` | mapping | values shared by several handlers (e.g. one `subjects` map used by two handlers) |
| `handlers` | ordered list of `{name, params}` | the pipeline itself (D1); names must exist in the registry (D2) |

Validation rules: a missing `inputs.template` or a malformed `handlers:` list
raises `ProfileError` from `inputs/yaml.py`; an unknown handler name or invalid
handler params raises `ProfileError` from the registry. Relative paths resolve
against the profile's own directory, then the current directory, then the repo
root.

`inputs.template` may contain `{minggu}` (substituted once the week is known)
and glob wildcards; it must match exactly one workbook, otherwise the error
lists the candidates and points at `inputs.templates` (D10). The calendar
referenced by `inputs.jadual` is a standalone data file (D11), documented in
`config/README.md`.

### 3.4 CLI

```
ranse fill  --profile P [--date YYYY-MM-DD] [--minggu N] [--no-dskp-auto]
ranse write --profile P [--minggu N] SHEET!CELL VALUE
ranse dskp  --txt FILE [--select S CS LS] [-o out.json] | --pdf F --pages 35-45 | --list
```

There is deliberately **no `--xlsx`**: the workbook is a profile input, so a
mistake in the shell cannot overwrite the wrong file (D10).

`ranse write` always writes **text**; a value that must stay a number (a year,
an amount) belongs in a `fixed_cells` handler, which keeps the `int(value)`
path (risk 8, `src/ranse/handlers/fixed_cells/DESIGN.md`).

---

## 4. Settled decisions

These were agreed with the maintainer and are not up for re-litigation. The
identifiers D1–D14 are cited from code and tests as "decision N".

| # | Item | Decision |
|---|---|---|
| D1 | Profile shape | An **explicit ordered `handlers:` list**; do not support both an implicit and an explicit form |
| D2 | Handler discovery | **Built-in registry only** — no dynamic import paths, no entry-point plugins |
| D3 | Packaging | An **installable package**; there is no `scripts/fill-erph.py` legacy entry |
| D4 | Equivalence check | Write the **golden regression tests before touching business code** |
| D5 | Extra scope | dict → dataclass, README + `docs/translations/ms-MY/README.md` kept in sync, `gen_dskp.py` absorbed into `inputs/dskp.py` |
| D6 | Core constraint | **No business logic in core**: no `DAY_ORDER`/`PERIOD_TIMES`/`BC-1A`/`minggu`/`cuti`/`sys.exit` |
| D7 | Core boundary | Core is **write-only** towards the target workbook: `open / sheet / write / save`; **no `read(coord)`** |
| D8 | Input reading | Lives in a separate **`inputs/` layer** (timetable, DSKP, the two YAML files); it never touches the target workbook |
| D9 | Single-cell writes | Both layers: the core API `wb.write("MENU!B3", "value")` **and** the CLI subcommand `ranse write` |
| D10 | Template path | **`--xlsx` is a profile-only parameter** (`inputs.template`); it is not on the CLI |
| D11 | Calendar file | `jadual-minggu.yaml` is a **standalone data file** referenced by the profile via `inputs.jadual`; it is not merged into the profile |
| D12 | Layout constants | MENU row `5 + day_idx*10`, columns 3–7, `NUM_PERIODS=8`, `CLASS_BLOCK_SIZE=31`, … **stay in the handlers for v1**; they do not go into the profile |
| D13 | Error handling | Core raises `RanseError` subclasses; the CLI maps them to `Error: …` + exit code 1. Handlers and inputs keep `print(..., file=sys.stderr)`; **no logging framework** |
| D14 | Time ownership (business) | **All time-related data is written to the MENU sheet** — the shipped e-RPH rule, defined in `src/ranse/handlers/menu/DESIGN.md` |

---

## 5. Lifecycle (two-phase orchestration)

`ranse fill` runs one deterministic pipeline (`cli.py`):

1. **Load the profile** (`inputs/yaml.py`) and **build the handlers**
   (registry): unknown names and bad params fail here, before any I/O to the
   workbook.
2. **Resolve phase** — every handler with `phase == "resolve"` runs in profile
   order. The shipped `week` resolver computes `ctx.start_date`, `ctx.week`
   (minggu + siri) and the timetable path. Resolvers write no cells.
3. **Pick the workbook** — `resolve_template()` substitutes `{minggu}` and
   resolves glob wildcards; zero matches or several matches are both errors
   that list the candidates and point at `inputs.templates`.
4. **Open it** (`Workbook.open`) and check the required sheets exist (`MENU`
   plus the day sheets — the set the shipped business needs).
5. **Read the timetable** (`inputs/timetable.py`) into a `Schedule`. The target
   workbook stays write-only: the timetable is a separate file.
6. **Fill phase** — every handler with `phase == "fill"` runs in profile
   order: in the shipped profile `menu`, then `fixed_cells`, then `dskp`.
   **Order is significant**: the last writer wins on a shared cell (risk 9,
   `src/ranse/handlers/README.md`).
7. **Save** (`wb.save()` overwrites the template in place) and print the report.

Handlers are stateless between runs: the same week produces the same result
whatever ran before, and re-running a week is always safe.

---

## 6. Errors and exit codes

- `core` / `inputs` raise `RanseError` subclasses (`ProfileError`,
  `WeekError`, `SheetError`).
- `cli` catches `RanseError` and prints `Error: <message>` on stderr, exit 1.
- Handlers keep the legacy style: `print(…, file=sys.stderr)` +
  `sys.exit(1)` for business errors, and a `  Warning: …` line for skippable
  problems.
- argparse usage errors (e.g. "Nothing to do: set inputs.timetable …") go
  through `parser.error` and exit 2.

Anything that could fill the wrong week or the wrong cell is a hard error. A
missing source file for one class is a warning — the classification is the
business docs' subject (`src/ranse/handlers/README.md`).

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

The engine is intentionally dumb: no day names, no period times, no week
numbers, no exit codes (D6).

---

## 8. Inputs layer

`inputs/` turns source files into model objects; it never writes the target
workbook (D8). What each reader produces:

| Reader | Consumes | Produces |
|---|---|---|
| `inputs/yaml.py` | the profile YAML, the calendar YAML, `inputs.template` patterns | `Profile`, `Week`-calendar config, the resolved workbook path |
| `inputs/timetable.py` | a timetable `.xlsx` or `.csv` | `Schedule` (`{day: {period: Lesson}}`) |
| `inputs/dskp.py` | DSKP `.txt` / `.pdf` | nested section dicts; `resolve_selection` picks one title/CS/LS triple |

The **formats** of the timetable and DSKP source files are specified in
`docs/input-formats.md`; the calendar YAML is specified in
`config/README.md`. `core` has no import from this layer.

---

## 9. Testing

Two layers, both must stay green (D4):

1. **Pure unit tests** — no `assets/` dependency, so a fresh clone can run
   them: cell-reference round trips, Excel date serials, `_section_pair`
   sliding and wrap, `merge_periods` (contiguous merges, gaps do not), week
   resolution (cuti / missing minggu / out-of-range dates), class-code parsing
   (`BC-1A`, en-dash variant), and the PAGI/TGH/TPTG boundaries.
2. **Golden regression** — fills a **temporary copy** of the real template and
   compares each sheet's XML bytes against `tests/golden/<case>/<sheet>.xml.gz`:

   | Case | Date | Expectation |
   |---|---|---|
   | `minggu-33` | 2026-09-20 | siri 7 timetable, full fill |
   | `minggu-34` | 2026-09-27 | siri 7 timetable, full fill |
   | `cuti` | 2026-01-04 | non-zero exit, "holiday week" on stderr |

   Baselines are per-sheet XML, never whole-zip bytes: zip entry order and
   timestamps would produce false diffs (risk 2). Regenerate them with
   `tests/make_golden.py`. The suite **skips** when `assets/` is missing
   (gitignored), which is why the unit tests must be self-contained
   (risk 5).

The golden cases pin the **shipped business**: a change to the handler rules
in `src/ranse/handlers/` (per-handler READMEs) must regenerate them
deliberately.

---

## 10. Risks and pitfalls

Numbering is global and stable: risks 1–12 are cited from code as "risk N".
The framework risks live here; the business risks are defined in the document
that owns the rule.

1. **Serialization must be byte-for-byte**: keep
   `xml_declaration=True, encoding="UTF-8", short_empty_elements=False` and
   every `register_namespace` prefix/URI, or every golden test fails.
2. **Golden compares sheet XML, not zip bytes.**
3. **The `subjects` map is shared** by two handlers → it belongs in the
   profile `context:`, not duplicated into both handlers' params.
5. **`assets/` is not committed** → regression tests skip on a fresh clone; the
   pure-function tests are the safety net there.
6. **The template is large and overwritten in place** → always copy it to a
   temp directory before filling it in a test.

Business risks (defined at the target, numbering continues from above):

| Risk | Concern | Defined in |
|---|---|---|
| 4 | the two period tables keep their values; a time gap ends a merged run | `docs/input-formats.md` |
| 7 | `menu` writes empty rows as `""` to clear a previous run — do not delete that branch | `src/ranse/handlers/menu/DESIGN.md` |
| 8 | `fixed_cells` converts `int(value)` at write time, not at profile-load time | `src/ranse/handlers/fixed_cells/DESIGN.md` |
| 9 | order matters in the fill phase (last writer wins) | `src/ranse/handlers/README.md` |
| 10 | Jumaat/Sabtu are dropped while reading the timetable | `docs/input-formats.md` |
| 11 | the PAGI/TGH/TPTG suffix only applies to `HH:00` keys | `src/ranse/handlers/menu/DESIGN.md` |
| 12 | MENU is the only place time-related data is written (D14) | `src/ranse/handlers/menu/DESIGN.md` |

---

## 11. Implementation history

The current layout was reached in five stages, one commit each, with the golden
suite green at every step (D4). Test comments cite these as "stage N":

| Stage | Content |
|---|---|
| 0 | Fold in the work-in-progress changes; add `pyproject.toml`, the golden baselines and the pure-function unit tests (baselines taken from the **working tree**, not from the previous commit) |
| 1 | Pure move into `src/ranse/` — imports and file placement only, no logic or string changes |
| 2 | De-business-ify `core` (RanseError instead of `sys.exit`), extract `week` / `menu` / `fixed_cells` / `dskp` handlers, drop `sys.path.insert` + dynamic `gen_dskp` import, move the namespace registration into `Workbook` |
| 3 | Profile schema + two-phase orchestration + dataclasses (`Lesson` / `Schedule` / `Week` / `Profile`) |
| 4 | Packaging (`ranse` console script), the three subcommands, delete `scripts/`, rewrite README + the Malay translation |

---

## 12. Out of scope and future work

Not to be done with the current design:

- introducing `openpyxl` (or any library that rewrites the whole workbook);
- a logging framework, or rewording the existing error messages;
- moving layout constants (row formulas, column numbers) into the profile
  (D12);
- dynamic third-party handler loading (D2);
- a `scripts/fill-erph.py` compatibility entry (D3);
- edits under `assets/`.

Planned or possible later:

- a standalone Windows executable (no Python required) for teachers;
- an optional core read API, if a feature ever needs to inspect values before
  writing;
- per-week time overrides — **which, per D14, must be expressed as MENU-sheet
  values**, never as a second source of times;
- timetable files for siri 2–6 (the calendar reports missing files today).
