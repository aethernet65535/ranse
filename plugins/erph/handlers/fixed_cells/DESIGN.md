# `fixed_cells` handler (fill)

Writes the profile's constant cells — teacher name, year — before the later
fillers get their turn.

Protocol/plugin contract: [parent index](../../README.md).
Framework design: [`docs/DESIGN.md`](../../../../docs/DESIGN.md).

## Params

```yaml
- name: fixed_cells
  params:
    cells:
      - [MENU, "B3:C3", "ALI BIN ABU"]   # writes to the top-left of the range
      - [MENU, "B4", 2026]                # numbers stay numbers
```

## Rules

- `cells` must be a list of `[sheet, range, value]` triples; anything else is
  a `ProfileError` at build time — before any cell is touched.
- Values that look like integers are converted with `int(value)` **at write
  time**, not at profile-load time (risk 8) — keep that timing or a type
  change breaks the golden suite.
- A missing sheet is a `  Warning: …` on stderr and the cell is skipped; it
  does not abort the run.
- Because it runs in profile order, a `fixed_cells` entry **after** `menu`
  overrides MENU's own values on a shared cell — and one **before** `dskp`
  gets overridden by automatic DSKP entries (risk 9,
  [fill order](../../README.md#fill-order-risk-9)).
- `ranse write` always writes **text**; a value that must stay a number
  belongs here, which keeps the `int(value)` path (risk 8).

## Risks defined here

| # | Risk |
|---|---|
| 8 | **Values pass through an `int(value)` attempt at write time**, not at profile-load time; keep that timing or a type change breaks golden |

Risk numbers run project-wide; the framework risks (1–3, 5–6) live in
[`docs/DESIGN.md`](../../../../docs/DESIGN.md) S10, the business risks here.
