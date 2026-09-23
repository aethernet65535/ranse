# Handler business rules — index

The handler **system** (protocols, registry, two-phase pipeline, profile
schema) is framework and is documented in [`docs/DESIGN.md`](../../../docs/DESIGN.md)
§3–§5. This directory holds the four **shipped e-RPH handlers** — the
business rules that must stay out of `core/` (decision 6). Each handler lives
in its own folder, with its business rules in that folder's DESIGN.md:

| Handler | Phase | Rules |
|---|---|---|
| [`week/`](week/) | resolve | date → minggu/siri → timetable path ([`week/DESIGN.md`](week/DESIGN.md)) |
| [`menu/`](menu/) | fill | the MENU sheet owns all time data (decision 14), layout, clearing ([`menu/DESIGN.md`](menu/DESIGN.md)) |
| [`fixed_cells/`](fixed_cells/) | fill | constant cells, `int(value)` timing ([`fixed_cells/DESIGN.md`](fixed_cells/DESIGN.md)) |
| [`dskp/`](dskp/) | fill | day-sheet DSKP blocks, automatic section pair ([`dskp/DESIGN.md`](dskp/DESIGN.md)) |

`base.py` (the `Resolver` / `Filler` protocols + `Context`) and
`registry.py` (the built-in registry, decision 2) are framework, not
business, and are documented in `docs/DESIGN.md` §3.2.

Risk numbers (4, 7–12) continue the global list in
[`docs/DESIGN.md`](../../../docs/DESIGN.md) §10.

---

## Shared contract

- handlers are listed explicitly and in order in the profile (decision 1) and
  discovered only from `handlers/registry.py` (decision 2);
- `phase: "resolve"` handlers compute `ctx` inputs and **write no cells**;
  `phase: "fill"` handlers are the only code allowed to write, and only
  through `ctx.workbook` (the core write API, `docs/DESIGN.md` §3.1);
- each handler validates its own `params` at build time — a broken profile
  fails before any cell is touched;
- errors are reported the handler way: `print(…, file=sys.stderr)` +
  `sys.exit(1)` for business errors, `  Warning: …` + skip for skippable
  problems (decision 13).

---

## Fill order (risk 9)

Order in the profile's `handlers:` list decides who wins on a shared cell —
the last writer wins. The shipped profile relies on:

1. `menu` writes the week's time data first;
2. `fixed_cells` may override MENU cells (e.g. a hand-written name);
3. `dskp` writes static `entries` first, then automatic ones, so on the same
   cell the automatic entry wins.

Reordering the list changes results; the golden suite will say so.

**Risk 9** is this rule: order matters in the fill phase — static DSKP
entries before automatic ones, and the profile's handler order decides who
wins on a shared MENU cell.

---

## Risk map

| Risks | Defined in |
|---|---|
| 7, 11, 12 | [`menu/DESIGN.md`](menu/DESIGN.md) (clearing branch, time suffix, MENU-only time writer) |
| 8 | [`fixed_cells/DESIGN.md`](fixed_cells/DESIGN.md) (`int(value)` at write time) |
| 9 | this file (fill order, above) |
| 4, 10 | [`docs/input-formats.md`](../../../docs/input-formats.md) (period tables, Jumaat/Sabtu dropped) |
| 1, 2, 3, 5, 6 | [`docs/DESIGN.md`](../../../docs/DESIGN.md) §10 (framework) |

---

## Cross-references

- School calendar consumed by `week`: [`config/README.md`](../../../config/README.md)
- Timetable / DSKP source formats: [`docs/input-formats.md`](../../../docs/input-formats.md)
- Framework design: [`docs/DESIGN.md`](../../../docs/DESIGN.md)
- Example profile naming these handlers: [`profiles/ali-bin-abu.yaml`](../../../profiles/ali-bin-abu.yaml)
