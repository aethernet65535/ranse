# `dskp` handler (fill)

Fills the standard rows of each class block on the day sheets. It is the only
handler that writes to `AHAD`–`KHAMIS`, and it writes **content only** — which
is exactly why [MENU](../menu/DESIGN.md) can own all time data
(decision 14).

Protocol/registry contract: [parent index](../README.md).
Source formats (txt / JSON / pdf): [`docs/input-formats.md`](../../../../docs/input-formats.md).

## Params

```yaml
- name: dskp
  params:
    mode: auto                            # auto (default) | static
    entries:                              # manual entries, written first
      - {sheet: ISNIN, class: 1, file: t1.json,
         selection: [1, 1, 1], col_start: 2}
    file: "assets/bc-dskp/t{tingkatan}.txt"  # source for the automatic pair
    match_codes: [BC]                     # subject codes in the timetable xlsx
    match_names: ["BAHASA CINA", "华文"]   # matched when reading a CSV
    cs: 1                                 # which content standard inside a section
    ls: 1                                 # which learning standard
    left_col: 2                           # left half  = column B
    right_col: 5                          # right half = column E
```

All params are validated at build time (`mode` ∈ `auto|static`, `entries`
well-formed, integer params are integers) — a broken profile fails before any
cell is touched.

## Rules

- **Block layout** (decision 12, this handler's `__init__.py`): class *n*
  (1-based) starts at row `7 + (n-1) * 31` (`CLASS_BLOCK_SIZE = 31`); from
  that header the handler writes the title row `+6`, the content standard
  `+7` and the learning standard `+9`.
- **Columns**: the left half defaults to column B (`left_col: 2`), the right
  half to column E (`right_col: 5`).
- **Automatic mode** (`mode: auto`, the default): for every merged lesson of a
  matched subject, two **parent-level** sections (`X.0` headings) are written
  side by side, sliding one section forward per week:
  `idx = (minggu - 1) % (len(sections) - 1)` → `keys[idx]`, `keys[idx+1]`.
  When there is no next section the pair wraps back to the first two, so a
  week number alone always determines the content:

  ```
  week 1 → 1.0 Listening and Speaking  |  2.0 Reading
  week 2 → 2.0 Reading  |  3.0 Writing
  ...
  no next section → wrap back to 1.0 + 2.0
  ```
- **Matching**: `match_codes` matches the timetable's subject codes
  (`BC-1A`); `match_names` matches the subject name after `context.subjects`
  mapping (the CSV direction). A subject that matches nothing is skipped.
- **Static entries** (`params.entries`) are written first, then automatic
  entries are appended, so on the same cell the automatic entry wins
  (risk 9, [fill order](../README.md#fill-order-risk-9)).
- **`file`** accepts `{tingkatan}` (`t1.txt`, `t2.txt`, …), a per-tingkatan
  map, or nothing — then the built-in `DSKP_FILES` table is used
  ([formats](../../../../docs/input-formats.md#dskp)).
- **Warnings, not errors**: a missing DSKP file, a file with no usable parent
  sections, or an unknown sheet is reported on stderr and skipped, so one bad
  class does not abort the week.
- `--no-dskp-auto` (or `mode: static`) disables the automatic part for a run;
  with no week known the handler prints a note instead of guessing.

Risk numbers run project-wide; the framework risks (1–3, 5–6) live in
[`docs/DESIGN.md`](../../../../docs/DESIGN.md) S10. This handler's own pitfall
is covered by risk 9 in the [parent index](../README.md#fill-order-risk-9).
