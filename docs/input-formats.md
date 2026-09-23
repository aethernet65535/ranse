# Input file formats

The readers in `src/ranse/inputs/` turn source files into model objects
(`Schedule`, DSKP section dicts) and never touch the target workbook
(decision 8, [`docs/DESIGN.md`](DESIGN.md) S8). This document specifies the
**on-disk formats** those readers accept.

| Input | Format | Reader |
|---|---|---|
| Timetable | xlsx | `inputs/timetable.py` → `read_timetable_xlsx` |
| Timetable | csv | `inputs/timetable.py` → `build_schedule` |
| DSKP | txt / pdf / JSON | `inputs/dskp.py` |
| School calendar | yaml | `inputs/yaml.py` → `load_jadual_config` — specified in [`config/README.md`](../config/README.md) |
| Profile | yaml | `inputs/yaml.py` → `load_profile` — schema in [`docs/DESIGN.md`](DESIGN.md) S3.3 |

Risk numbers run project-wide. The framework risks (1–3, 5–6) live in
[`docs/DESIGN.md`](DESIGN.md) S10; risks 4 and 10 are defined below.

---

## Timetable (xlsx)

Layout — row 1 is the header with day names, column A holds the period
number, every other day column holds a class code:

| | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| 1 | Period | Ahad | Isnin | Selasa | Rabu | Khamis |
| 2 | 1 | BC-1A | BI-2B | … | … | … |
| 3 | 2 | … | … | … | … | … |

- **Header detection** — the first row containing a day name from `DAY_ORDER`
  (`Ahad`, `Isnin`, `Selasa`, `Rabu`, `Khamis`) is the header; each cell
  holding such a name becomes a day column.
- **Sheet selection** — the first sheet of the workbook, unless a sheet name
  contains `timetable` or `sheet` (case-insensitive), which wins.
- **Period number** — the first numeric cell in the row; rows whose number is
  not in `PERIOD_TIMES` (1–10) are skipped.
- **Class code** — matched by `([A-Z]+)[–-](\d+)([A-Za-z]+)`, i.e.
  `<SUBJECT>-<TINGKATAN><CLASS>` with an ASCII hyphen or an en dash:
  `BC-1A` → subject `BC`, tingkatan `1`, class `A`. The timetable's class
  label becomes `tingkatan + class` (`1A`), so `5SPA` survives as written. A
  cell that is empty or literally `NaN` is skipped.
- **Value resolution** — shared strings, inline strings and plain numbers are
  all read.

### Day coverage (risk 10)

The school week runs **Ahad … Khamis**; the e-RPH template only has sheets
for those five days, so **Jumaat/Sabtu columns and rows are dropped while
reading** — an existing business rule that lives outside `core/`. Do not
"helpfully" keep them: downstream fillers assume the five-day `DAY_ORDER`.

---

## Timetable (csv)

Header row with exactly these columns:

```
Date,Class,Start Time,End Time,Subject,Tingkatan
```

| Column | Meaning |
|---|---|
| `Date` | any of `YYYY-MM-DD`, `DD/MM/YYYY`, `YYYY/MM/DD`, `DD-MM-YYYY`; mapped to a day name via the weekday |
| `Class` | class label as the template spells it (`1E`, `5SPA`) |
| `Start Time` / `End Time` | `HH:MM`, must match a `TIME_PERIOD` key pair, else the row is skipped |
| `Subject` | subject code or name (after `context.subjects` mapping it feeds `dskp`'s `match_names`) |
| `Tingkatan` | tingkatan number as text |

- A `Date` that cannot be parsed produces a warning on stderr and the row is
  skipped.
- Days outside `DAY_ORDER` (Jumaat/Sabtu) are skipped (risk 10).

---

## Period times (risk 4)

Both period tables live in `inputs/timetable.py` and their **values are
pinned** — the MENU fill and the CSV reader disagree with nothing today, and
the golden suite proves it:

| Period | Start–End | | Period | Start–End |
|---|---|---|---|---|
| 1 | 07:40–08:20 | | 6 | 10:50–11:30 |
| 2 | 08:20–09:00 | | 7 | 11:30–12:10 |
| 3 | 09:00–09:40 | | 8 | 12:10–12:50 |
| 4 | 09:40–10:20 | | 9 | 12:50–13:30 |
| 5 | 10:20–10:50 | | 10 | 13:30–14:10 |

- `PERIOD_TIMES` (period → range) fills the MENU rows;
- `TIME_PERIOD` (range → period) is the CSV direction — the same data, so a
  change must be made in **both** maps;
- changing any value changes every filled workbook.

**Risk 4** also covers the consumer side: `merge_periods` (in `model.py`)
treats a **time gap as a new run** — two identical lessons separated by a gap
never merge. See
[`src/ranse/handlers/menu/DESIGN.md`](../src/ranse/handlers/menu/DESIGN.md).

---

## DSKP

DSKP (*Dokumen Standard Kurikulum Pentaksiran*) sources are parsed by
`inputs/dskp.py`, used both by the `ranse dskp` subcommand and by the `dskp`
handler's entries.

### txt

A plain-text export where **every line starts with a number**:

| Line shape | Meaning |
|---|---|
| `1.0 Listening and Speaking` | parent section (`X.0`) — starts a new section |
| `1.1 …` | content standard inside the current section |
| `1.1.1 …` | learning standard inside the current content standard |
| any other non-empty line | continuation of the previous entry (joined with a space) |
| empty line | ends a continuation |

Lines starting with `=`, `-`, `KSSM`, `DSKP` or `【` are skipped (separators,
headers, cross-reference blocks). Number detection is language-neutral, so the
same parser works for English and Bahasa Malaysia documents.

### JSON

The structured output of `ranse dskp` (and the input of `dskp` entries):

```json
{
  "1": {
    "title": "1.0 Listening and Speaking",
    "content_standards": {
      "1": {
        "id": "1.1",
        "content": "…",
        "learning_standards": { "1": { "id": "1.1.1", "content": "…" } }
      }
    }
  }
}
```

Section keys are digits only — the automatic section pair relies on that
(`_section_pair` filters `str(k).isdigit()`).

### pdf

`ranse dskp --pdf F --pages 35-45` extracts text with **pdfplumber** (an
optional dependency — a clear error if it is missing) and parses it exactly
like txt. Page ranges accept `35-45`, `35,37,39` or a mix.

### Selection

`--select S CS LS` (and the handler's `selection: [S, CS, LS]`) addresses one
triple inside the structure — section `S.0`, content standard `S.CS`, learning
standard `S.CS.LS` — and resolves to
`{title, content_standard, learning_standard}`, the three rows the handler
writes into a class block.

### Built-in file table

`inputs/dskp.py` carries a `DSKP_FILES` table (`T1` → `assets/bc-dskp/t1.txt`
… `T5`) used when a `dskp` handler configures no `file:`; `ranse dskp --list`
prints it. The `assets/` directory itself is gitignored.
