# Ranse refactor implementation plan (for the implementing agent)

> This document is the **single source of truth** for the implementation. All
> architectural decisions have been settled with the maintainer — do not
> propose alternative layering, and do not change the "settled decisions"
> below. Work stage by stage: one commit per stage, and regression tests must be
> fully green before moving on.

---

## 0. Background and current state

Ranse is a CLI tool for Malaysian teachers: it reads a weekly timetable and
automatically fills the e-RPH Excel template. All the logic sits in
`scripts/fill-erph.py` (1231 lines) and mixes five responsibilities:

| Existing code block (line numbers) | Actual responsibility |
|---|---|
| `_read_zip` / `_parse_sheet_rels` / `_parse_sheet_names` / `_read_shared_strings` (140–190) | xlsx container read/write |
| `_parse_sheet` / merge / row / cell / `write_cell` / `_set_cell_value` (196–337) | cell-write primitives |
| `read_csv` / `build_schedule` / `merge_periods` / `read_timetable_xlsx` (343–567) | timetable reading + domain model |
| `load_config` / `load_jadual_config` / `resolve_week` / `siri_to_timetable` (574–698) | config loading + week resolution |
| `build_auto_dskp_entries` / `_section_pair` / `_dskp_file_for_tingkatan` (705–862) | business callbacks (week-sliding DSKP selection) |
| `fill_menu` / `write_fixed_cells` / `write_dskp_cells` / `fill_dskp_sheets` (869–1068) | business callbacks (which cells to write) |
| `main()` (1075–1231) | CLI orchestration |

Companion files: `scripts/constants.py`, `scripts/gen_dskp.py` (265 lines),
`scripts/erph-config.yaml`, `scripts/jadual-minggu.yaml`, `scripts/archived/preview-pdf.py`.

Known problems:
- `sys.exit()` / `print()` are scattered in 20+ places, **including in
  `resolve_week` and `siri_to_timetable`, which should be pure functions**;
- `load_dskp_content` and `build_auto_dskp_entries` use `sys.path.insert` plus a
  dynamic `import gen_dskp`;
- `_parse_sheet` has a global `ET.register_namespace` side effect;
- **there are no tests at all** (`find . -name "test*"` is empty), and only 2 commits.

### ⚠️ Read before starting: the working tree has uncommitted changes

```
 M scripts/fill-erph.py   (+609/-…)      <- lots of uncommitted work
 M scripts/erph-config.yaml
 M README.md  M .gitignore
 D scripts/{LICENSE,README.md,README.ms.md}   <- already moved to the repo root
?? scripts/gen_dskp.py  ?? scripts/jadual-minggu.yaml
```

**The first thing in stage 0**: fold these into a single standalone commit that
serves as the refactor's starting point and the source of the golden baselines.
Baselines must be taken from **the current state of the working tree**, not
`HEAD`. Otherwise the refactor diff gets mixed with WIP and cannot be reviewed or
rolled back.

---

## 1. Settled decisions (do not re-litigate)

| # | Item | Decision |
|---|---|---|
| 1 | Profile shape | **explicit `handlers:` list** (do not "keep the old top-level fields" or "support both") |
| 2 | Handler discovery | **built-in registry only**. No dynamic import paths, no entry-point plugins |
| 3 | Packaging | **build an installable package, keep no `scripts/fill-erph.py` legacy entry**, update the README fully |
| 4 | Equivalence check | **write the regression (golden) tests before touching business code** |
| 5 | Extra scope | dict→dataclass, README + `docs/translations/ms-MY/README.md` updates, absorb `gen_dskp.py` |
| 6 | **Core constraint** | **business logic must not enter core** (no `DAY_ORDER`/`PERIOD_TIMES`/`BC-1A`/`minggu`/`cuti`/`sys.exit` in core) |
| 7 | core read/write boundary | core is **write-only** towards the target workbook: `open / sheet / write(coord, content) / save`. **Do not expose `read(coord)`**; add it later if needed |
| 8 | Where input reading lives | a separate **`inputs/` layer** (timetable xlsx/csv, DSKP txt/json, the two YAML files); not in core, and it never touches the target workbook |
| 9 | `<coord> <write_content>` | **both layers**: the core Python API `wb.write("MENU!B3", "value")`, and the CLI's `ranse write` single-cell subcommand |
| 10 | Template path | **`--xlsx` is a profile-only parameter**, set in `profile.inputs.template`; it is not on the CLI |
| 11 | Calendar file | `jadual-minggu.yaml` is a **standalone data file** referenced by the profile via `inputs.jadual`; it is not merged into the profile |
| 12 | Layout constants | MENU row `5 + day_idx*10`, columns 3–7, `NUM_PERIODS=8`, `CLASS_BLOCK_SIZE=31`, etc. **stay in the handler for v1**; they do not go into the profile |
| 13 | Error handling (minimal scope) | core switches to the `RanseError` exception hierarchy, and the CLI maps it to an exit code. **This is a necessary corollary of decision 6.** Only change core's error propagation, **do not overhaul logging**, and keep the existing `print(..., file=sys.stderr)` style in the CLI/handler layer |

Notes on the current state of "reading" (confirmed by the maintainer):
1. **Reading target-template cell values** — does not exist and is not needed (`_read_cell_value` only serves timetable reading);
2. **Reading the input timetable** — required, belongs in `inputs/`;
3. **Reading data files** (DSKP / profile / calendar) — required, belongs in `inputs/`.

Reading merge ranges and the `<c>` `s=` style attribute while writing is there to
**preserve formatting**; it is structural metadata, not value reading, so it stays in core.

---

## 2. Target architecture

```
+-- CLI ---------------------------------------------+
|  ranse fill  --profile p.yaml [--date][--minggu]   |  <- --xlsx lives only in the profile
|  ranse write --profile p.yaml MENU!B3 "value"      |  <- direct single-cell write
|  ranse dskp  --txt ... --select 1 1 1 -o out.json  |
+--------------+-------------------------------------+
               | orchestration + exceptions -> exit code only
+-- handlers/ -v-------------------------------------+
|  base.py       Resolver / Filler Protocol + Context|
|  registry.py   built-in registry (only discovery)  |
|  week.py       calendar -> minggu/siri/timetable   |
|  menu.py       MENU layout + time suffix + merging |
|  fixed_cells.py / dskp.py   layout constants here  |
+--------------+-------------------------------------+
               | may only call core's write API
+-- core/ -----v---------------+   +-- inputs/ -------+
|  Workbook.open()/save()      |   |  timetable.py    |
|  sheet(name)                 |   |  dskp.py         |
|  write(coord, content)       |   |  yaml.py         |
|  merges (keeps formatting)   |   |  calendar loader |
|  x no read(coord)            |   |  x never touches |
|  x no DAY_ORDER/PERIOD_...   |   |    the workbook  |
+------------------------------+   +------------------+
```

Dependency direction is strictly one-way: `cli → handlers → core`, `cli/handlers → inputs`.
**`core` must not import `handlers` or `inputs`.**

### Target file list

```
pyproject.toml                       # [project] + console script + dev extra (pytest)
src/ranse/__init__.py
src/ranse/__main__.py                # python -m ranse
src/ranse/errors.py                  # RanseError / ProfileError / WeekError / SheetError
src/ranse/cli.py                     # argparse subcommands + two-phase orchestration + exceptions->exit code
src/ranse/core/__init__.py
src/ranse/core/refs.py               # A1 <-> (row,col), range top-left, Excel date serial
src/ranse/core/xlsx.py               # Workbook.open/save/sheet/write/merges
src/ranse/inputs/__init__.py
src/ranse/inputs/timetable.py        # read_csv / read_xlsx -> Schedule
src/ranse/inputs/dskp.py             # <- absorbs gen_dskp.py (including its CLI main)
src/ranse/inputs/yaml.py             # profile + calendar loading and structural validation
src/ranse/handlers/__init__.py
src/ranse/handlers/base.py           # Resolver / Filler Protocol + Context dataclass
src/ranse/handlers/registry.py       # built-in registry
src/ranse/handlers/{week,menu,fixed_cells,dskp}.py
src/ranse/model.py                   # Lesson / Schedule / Week dataclass + merge_periods
profiles/ali-bin-abu.yaml            # explicit handlers list, including inputs.template
config/jadual-minggu.yaml            # standalone calendar (originally scripts/jadual-minggu.yaml)
tests/golden/                        # baseline sheet XML (.gz, committed to git)
tests/make_golden.py                 # run once by hand to generate the baselines
tests/test_core_refs.py
tests/test_handlers_menu.py
tests/test_week.py
tests/test_profile.py
tests/test_regression.py             # depends on assets/; pytest.skip when missing
README.md + docs/translations/ms-MY/README.md   # rewrite of the structure/usage/configuration chapters

Delete: the whole scripts/ directory (fill-erph.py, gen_dskp.py, constants.py,
      erph-config.yaml, jadual-minggu.yaml, archived/)
```

Notes:
- `model.py` lives at the top level of `src/ranse/` rather than `core/`, because
  `Lesson/Schedule/Week` carry `DAY_ORDER`-related semantics and belong to the
  domain model, not to the pure write engine; `inputs` produce them and
  `handlers` consume them. (If the implementer prefers `core/model.py`, that is
  acceptable, but **no e-RPH layout knowledge may appear there**.)
- `assets/` stays in `.gitignore` and **is not package data**. Path-resolution
  bases stay as they are: profile directory → cwd → repo root (reuse the
  existing `_resolve_path`).
- `requires-python = ">=3.9"` (dataclass + modern packaging). The README
  currently says "Python 3.6+"; change that too.
- `scripts/archived/preview-pdf.py` and `assets/timetable/src/*.jpg` are out of
  scope; keep them as they are.

---

## 3. Interface draft

### core API (strictly write-only)

```python
# src/ranse/core/xlsx.py
class Workbook:
    @classmethod
    def open(cls, path: str | Path) -> "Workbook": ...
    @property
    def sheets(self) -> list[str]: ...
    def sheet(self, name: str) -> "Sheet": ...
    def save(self, path: str | Path | None = None) -> None: ...   # None = overwrite in place

class Sheet:
    def write(self, coord: str, content: str | int | float) -> None:
        """coord is like 'B3' or 'B3:C3' (the top-left cell is used, respecting merges)."""
    def merges(self) -> list[tuple[int, int, int, int]]: ...
```

Requirements:
- **do not provide `read(coord)`**.
- when writing, keep every original attribute on `<c>` (`s`/`t`, etc.); for
  strings write `t="inlineStr"` + `<is><t>`; for numbers drop `t` and use `<v>`
  — exactly like the current `_set_cell_value`; **the serialization result must
  not change**.
- auto-create missing `<row>` / `<c>` and keep rows/columns ordered (the current
  `_ensure_row` / `_ensure_cell` logic).
- move the `ET.register_namespace` side effect into a `Workbook` instance method
  rather than scattering it globally — but **the registered prefixes and URIs
  must match the current ones exactly**, or the golden tests fail.

### Handler interface (the interface itself keeps business logic out of core)

```python
# src/ranse/handlers/base.py
@dataclass
class Context:
    workbook: Workbook
    profile: Profile
    schedule: Schedule | None = None
    week: Week | None = None
    params: dict = field(default_factory=dict)   # this handler's own params
    report: list[str] = field(default_factory=list)

class Resolver(Protocol):        # phase one: compute inputs, write no cells
    name: str
    def resolve(self, ctx: Context) -> None: ...

class Filler(Protocol):          # phase two: write cells only through core
    name: str
    def fill(self, ctx: Context) -> list[str]: ...   # returns report lines
```

The orchestrator `cli.py` is responsible only for:
`load profile → build Workbook → run all Resolvers → (read timetable, if needed) → run all Fillers → save → print report`.

### Profile schema (explicit handlers list)

```yaml
# profiles/ali-bin-abu.yaml
profile: ali-bin-abu-2026
inputs:
  template: "assets/ALI BIN ABU/12. ERPH/template.xlsx"   # the --xlsx location
  jadual:   "config/jadual-minggu.yaml"                     # standalone calendar, not part of the profile

context:                        # shared across handlers; never duplicate it into handler params
  subjects:
    BC: "BAHASA CINA 华 文"

handlers:
  - name: week                  # phase: resolve
  - name: menu                  # phase: fill
  - name: fixed_cells
    params:
      cells: [[MENU, "B3:C3", "ALI BIN ABU"]]
  - name: dskp
    params:
      mode: auto
      match_codes: [BC]
      match_names: ["BAHASA CINA", "华文"]
      cs: 1
      ls: 1
      left_col: 2
      right_col: 5
```

Validation rules: an unknown `name` → `ProfileError`; `params` are validated by
each handler itself before it reports an error; a missing `inputs.template` →
`ProfileError`.

### CLI

```
ranse fill  --profile profiles/ali-bin-abu.yaml [--date 2026-09-20] [--minggu 33] [--no-dskp-auto]
ranse write --profile profiles/ali-bin-abu.yaml MENU!B3 "ALI BIN ABU"
ranse dskp  --txt assets/bc-dskp/t1.txt [--select 1 1 1] [-o out.json] | [--pdf x.pdf --pages 35-45] | [--list]
```

- **there is no `--xlsx`** (decision 10).
- `fill` overwrites `inputs.template` in place by default, matching the current behaviour.
- The capabilities of the existing `--config` / `--jadual-config` /
  `--timetable-xlsx` / `--csv` are all taken over by the profile's `inputs` and
  `handlers[].params`; the CLI keeps only `--date` / `--minggu` /
  `--no-dskp-auto` as temporary overrides.
- Error exit: `RanseError` → `print(f"Error: {e}", file=sys.stderr)` +
  `sys.exit(1)`; argparse usage errors still go through `parser.error`.

---

## 4. Staged implementation

One stage = one commit. **`pytest` must be fully green at the end of every
stage**, otherwise you may not move on.

### Stage 0 — fold in the WIP + regression baseline (do not touch business code)

1. Commit the existing uncommitted changes separately (something like `chore: fold in existing changes`).
2. Write `tests/make_golden.py` and produce baselines with the **current**
   `scripts/fill-erph.py`:
   - two normal weeks: minggu 33 (siri 1) and minggu 34 (siri 7);
   - the **error path** for a `cuti` week (assert a non-zero exit + stderr wording);
   - copy the template to a temp directory before each run (the script overwrites in place);
   - store the baseline as **per-sheet XML** (gzip), not the whole zip — zip
     entry order/timestamps would cause false diffs;
   - store it under `tests/golden/<case>/<sheet>.xml.gz` and commit it to git.
3. Add pure-function unit tests (no `assets/` dependency; a fresh clone must be
   able to run them):
   `_col_to_num`/`_col_letter`/`_parse_cell_ref` round-trips,
   `_cell_range_top_left`, `_date_to_excel`, `_section_pair` sliding with wrap
   (including the last-page wrap), `merge_periods` (contiguous periods merge,
   non-contiguous do not), `resolve_week` (including cuti / missing minggu /
   out-of-range dates), `_parse_class_code` (`BC-1A`, `BC–1A` with an en dash,
   non-matching returned unchanged), `_time_with_suffix` (PAGI/TGH/TPTG
   boundaries at 11:00/14:00).
4. Create `pyproject.toml` (`[project]` + a `dev` extra with pytest,
   `requires-python = ">=3.9"`).
5. `tests/test_regression.py`, which depends on `assets/`, does `pytest.skip`
   when the assets are missing.

**Acceptance**: `pytest` fully green; golden baselines committed; WIP committed separately.

### Stage 1 — pure move

Only change imports and file placement; **do not change any logic, any string, or
any constant value**:

- lines 140–337 → `core/refs.py` + `core/xlsx.py`;
- lines 343–567 → `inputs/timetable.py` (`constants.PERIOD_TIMES`, `DAY_ORDER`,
  `DAY_BY_WEEKDAY`, `_TIME_SUFFIX_CACHE`, `NUM_PERIODS` move along into inputs or model);
- `gen_dskp.py` → `inputs/dskp.py` (keep its `main()`; stage 4 wires up the CLI);
- `load_config` / `load_jadual_config` → `inputs/yaml.py`;
- `fill_menu` / `write_fixed_cells` / `fill_dskp_*` /
  `build_auto_dskp_entries` / `resolve_week` / `siri_to_timetable` → temporarily
  into `handlers/` (move first, do not change signatures);
- `main()` → `cli.py`.

**Acceptance**: golden output **byte-identical**; pure-function unit tests stay green.

### Stage 2 — de-business-ify core + extract handlers

1. Every `sys.exit` / business message in core → the `RanseError` exception
   hierarchy, mapped to an exit code centrally by `cli.py` (decision 13; **do
   not sneak in a logging framework**).
2. Move week resolution (the business rules in `resolve_week` /
   `siri_to_timetable` / `load_jadual_config`, including the cuti,
   missing-minggu and out-of-range-date messages) into `handlers/week.py`,
   implementing `Resolver`.
3. Extract the Fillers one at a time and run golden after each:
   `menu.py` (layout constants, `_time_with_suffix`, period merging, Excel date
   serial) → `fixed_cells.py` (merge-area top-left + the `int(value)` conversion
   attempt) → `dskp.py` (`_section_pair` sliding, the `_dskp_file_for_tingkatan`
   placeholder, `CLASS_BLOCK_SIZE` and other layout constants, static selection
   writes).
4. Eliminate `sys.path.insert` + the dynamic `import gen_dskp`, replacing them
   with a normal in-package import.
5. Move `_parse_sheet`'s `ET.register_namespace` side effect into `Workbook`.

**Acceptance**: golden output byte-identical; `grep -rn "sys.exit\|DAY_ORDER\|PERIOD_TIMES\|CLASS_BLOCK" src/ranse/core/` returns nothing.

### Stage 3 — Profile schema + two-phase orchestration + dataclasses

1. New profile parsing (explicit `handlers:` list, `inputs`, `context`); an
   unknown handler name is an error.
2. `cli.py` implements the two-phase orchestration: resolve → read timetable →
   fill → save.
3. Bare dicts → dataclasses (`Lesson` / `Schedule` / `Week` / `Profile`).
   **Do this after the handlers are extracted** to keep the change surface
   minimal; replace `entry["class"]` → `entry.class` everywhere.
4. Write `profiles/ali-bin-abu.yaml`, equivalent to the existing
   `erph-config.yaml` plus the `jadual-minggu.yaml` reference.
5. `scripts/jadual-minggu.yaml` → `config/jadual-minggu.yaml` (contents unchanged
   except for the old command name in its comments).

**Acceptance**: golden output byte-identical; `tests/test_profile.py` covers the
three error modes — unknown handler, missing template, and a failing params
validation.

### Stage 4 — packaging + CLI + docs

1. Configure `pyproject` with `[project.scripts] ranse = "ranse.cli:main"`; land
   the three subcommands.
2. Delete the whole `scripts/` directory.
3. Rewrite `README.md`: Project Structure, Installation (`pip install -e .`),
   all command examples, the Configuration chapter as the Profile schema, the
   Python version, and keep "How It Works" with the same meaning.
4. Sync `docs/translations/ms-MY/README.md` (Malay, structure matching the
   English version).
5. Update the `python fill-erph.py ...` usage example in the top comment of
   `config/jadual-minggu.yaml`.

**Acceptance**: after `pip install -e .`, `ranse fill/write/dskp --help` works;
`grep -rn "fill-erph" . --exclude-dir=.git --exclude-dir=assets` leaves nothing
other than CHANGELOG/history mentions; golden fully green.

---

## 5. Risks and pitfalls (check each one while implementing)

1. **Serialization must be byte-for-byte**: keep `xml_declaration=True,
   encoding="UTF-8", short_empty_elements=False` and every `register_namespace`
   prefix/URI unchanged, or every golden test fails.
2. **Golden compares sheet XML, not zip bytes**.
3. **The `subjects` map is shared by `fill_menu` and `dskp`** → put it in the
   profile `context:` section; do not duplicate it into both handlers' params.
4. **`PERIOD_TIMES` exists twice**: `constants.py` has period→time, and the top
   of `fill-erph.py` has time→period (for CSV). Merge both into one place,
   `inputs/timetable.py`, with unchanged values.
5. **`assets/` is not committed** → the regression tests that need the real
   template skip on a fresh clone; the pure-function unit tests must be fully
   self-contained, as they are the only safety net there.
6. **The template is 7.5MB and overwritten in place** → both the golden
   generator and the regression test must copy it to a temp directory first.
7. **`fill_menu` writes empty rows as `""`** (clearing the previous run's
   result); do not delete that else branch when extracting the handler.
8. **`fixed_cells` values go through an `int(value)` conversion attempt** (not
   at `load_config` time but inside `write_fixed_cells`); keep the timing
   identical when migrating, or a type change will break golden.
9. **`dskp_auto` entries are appended after the static `dskp` ones**
   (`cfg["dskp"] = static + auto`); on the same cell, auto overrides static —
   this ordering semantics must be preserved.
10. **Jumaat/Sabtu timetables are dropped** (the template only has sheets for
    Ahad–Khamis); this is an existing business rule that belongs to
    `inputs/timetable.py` or a handler, **not to core**.

---

## 6. Out of scope (do not do)

- Do not introduce `openpyxl` (the README explicitly sells direct XML
  manipulation for formatting preservation).
- Do not overhaul logging or reword error messages.
- Do not push layout constants down into the profile (decision 12).
- Do not support dynamic third-party handler loading in the profile (decision 2).
- Do not keep a `scripts/fill-erph.py` compatibility entry (decision 3).
- Do not modify any file under `assets/`, and do not touch
  `scripts/archived/preview-pdf.py`.
- Do not create extra plan/design documents; this file is the single source of
  truth.
