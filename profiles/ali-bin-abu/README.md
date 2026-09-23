# Profile — ALI BIN ABU (2026)

The shipped example profile. `profile.yaml` is the only input `ranse fill` /
`ranse write` need; everything about *what* this profile fills lives in this
folder:

| File | Contents |
|---|---|
| `profile.yaml` | the profile itself — `inputs` / `context` / `handlers`; schema in [`docs/DESIGN.md`](../../docs/DESIGN.md) S3.3 |
| `DESIGN.md` | this profile's business design: the teacher, the template layout, the subject map and the handler pipeline |

## Running it

```bash
ranse fill  --profile profiles/ali-bin-abu/profile.yaml --date 2026-09-20
ranse write --profile profiles/ali-bin-abu/profile.yaml --minggu 33 MENU!B3 "ALI BIN ABU"
```

`ranse fill` is idempotent: the same week always produces the same workbook,
so re-running a week is safe.

## Where to look

- framework that loads the profile: [`docs/DESIGN.md`](../../docs/DESIGN.md);
- handler rules the `handlers:` list names: [`src/ranse/handlers/README.md`](../../src/ranse/handlers/README.md);
- formats the profile's `inputs` point at: [`docs/input-formats.md`](../../docs/input-formats.md);
- school calendar data file: [`config/jadual-minggu/DESIGN.md`](../../config/jadual-minggu/DESIGN.md).
