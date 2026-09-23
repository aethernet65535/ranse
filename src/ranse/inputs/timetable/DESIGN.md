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
reading** — a business rule that lives outside `core/`. Do not "helpfully"
keep them: downstream fillers assume the five-day `DAY_ORDER`.

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
| `Start Time` / `End Time` | `HH:MM`, must match a `TIME_PERIOD` key pair, else the row is skipped |
| `Subject` | subject code or name (after `context.subjects` mapping it feeds `dskp`'s `match_names`) |
| `Tingkatan` | tingkatan number as text |

- A `Date` that cannot be parsed produces a warning on stderr and the row is
  skipped.
- Days outside `DAY_ORDER` (Jumaat/Sabtu) are skipped (risk 10).

---

## Period times (risk 4)

Both period tables live in `__init__.py`, next to this file, and their
**values are pinned** — the MENU fill and the CSV reader disagree with
nothing today, and the golden suite proves it:

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
[`src/ranse/handlers/menu/DESIGN.md`](../../handlers/menu/DESIGN.md).
