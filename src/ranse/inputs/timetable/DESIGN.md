# Timetable reader — formats

`read_timetable_xlsx` and `build_schedule` turn a weekly timetable into a
`Schedule` (`{day: {period: Lesson}}`). This reader is a pure input: it never
touches the target workbook (decision 8,
[`docs/DESIGN.md`](../../../../docs/DESIGN.md)). Two formats are accepted,
`.xlsx` and `.csv`.

---

## xlsx

Layout — row 1 is the header with day names, column A holds the period
number, every other day column holds a class code:

| | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| 1 | Period | Ahad | Isnin | Selasa | Rabu | Khamis |
| 2 | 1 | BC-1A | BI-2B | … | … | … |
| 3 | 2 | … | … | … | … | … |

- **Header detection** — the first row containing a source day name (`Ahad` …
  `Sabtu`, the frozen header spellings mapped to the English day names
  ``Schedule`` carries by `_DAY_HEADERS`: `Ahad` → `Sunday`, …) is the header;
  each cell holding such a name becomes a day column.
- **Sheet selection** — the first sheet of the workbook, unless a sheet name
  contains `timetable` or `sheet` (case-insensitive), which wins.
- **Period number** — the first numeric cell in the row; rows whose number is
  not in the active period table are skipped.
- **Class code** — matched by `([A-Z]+)[–-](\d+)([A-Za-z]+)`, i.e.
  `<SUBJECT>-<FORM><CLASS>` with an ASCII hyphen or an en dash:
  `BC-1A` → subject `BC`, form `1`, class `A`. The timetable's class
  label becomes `form + class` (`1A`), so `5SPA` survives as written. A
  cell that is empty or literally `NaN` is skipped.
- **Value resolution** — shared strings, inline strings and plain numbers are
  all read.

### Day coverage (risk 10)

The school week runs **Sunday … Saturday** and the reader keeps **every day the
source carries** — including Friday/Saturday. A reader must not encode the
target workbook's sheet layout (decision 8), so which days a template
actually has is declared once by the profile in `context.days` and used by
the fillers (`menu` for the MENU row blocks, `dskp` for the day sheets).
Do not "helpfully" filter here — that would move the business rule back
into an input.

---

## csv

Header row with exactly these columns:

```
Date,Class,Start Time,End Time,Subject,Tingkatan
```

| Column | Meaning |
|---|---|
| `Date` | any of `YYYY-MM-DD`, `DD/MM/YYYY`, `YYYY/MM/DD`, `DD-MM-YYYY`; mapped to a day name via the weekday |
| `Class` | class label as the template spells it (`1E`, `5SPA`) |
| `Start Time` / `End Time` | `HH:MM`, must match a key pair of the active period table, else the row is skipped |
| `Subject` | subject code or name (after `context.subjects` mapping it feeds `dskp`'s `match_names`) |
| `Tingkatan` | form number as text |

- A `Date` that cannot be parsed produces a warning on stderr and the row is
  skipped.
- Every weekday is kept — day selection belongs to the fillers
  (`context.days` in the profile), not to this reader (risk 10).

---

## Period times (risk 4)

There is **one** period table at a time, in two directions:

- `PERIOD_TIMES` (period → range) in `__init__.py` is the **built-in
  fallback**, used when the profile references no table. Its values are
  pinned — the golden suite proves it;
- a profile may reference its own table via `inputs.period_times` (a YAML
  file, schema in
  [`config/period-times/DESIGN.md`](../../../../config/period-times/DESIGN.md));
  it **replaces** the built-in table wholesale;
- the CSV direction (range → period) is **derived** from the active table
  (`_reverse_times`), so the two directions can never drift apart — a
  change is made once, in the table.

Built-in values (also the shipped `config/period-times/period-times.yaml`):

| Period | Start–End | | Period | Start–End |
|---|---|---|---|---|
| 1 | 07:40–08:20 | | 6 | 10:50–11:30 |
| 2 | 08:20–09:00 | | 7 | 11:30–12:10 |
| 3 | 09:00–09:40 | | 8 | 12:10–12:50 |
| 4 | 09:40–10:20 | | 9 | 12:50–13:30 |
| 5 | 10:20–10:50 | | 10 | 13:30–14:10 |

- changing any value changes every filled workbook.

**Risk 4** also covers the consumer side: `merge_periods` (in `model.py`)
treats a **time gap as a new run** — two identical lessons separated by a gap
never merge. See
[`src/ranse/handlers/menu/DESIGN.md`](../../handlers/menu/DESIGN.md).
