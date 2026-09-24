# Period times — period → [start, end]

The school's timetable periods as a YAML mapping; the timetable reader
loads it through a profile's `inputs.period_times` key:

```yaml
1: ["07:40", "08:20"]
2: ["08:20", "09:00"]
# …
10: ["13:30", "14:10"]
```

| Key | Value |
|---|---|
| period number (YAML int) | `[start, end]` as `HH:MM` strings |

Loader: `load_period_times` in
[`inputs/timetable/`](../../inputs/timetable/DESIGN.md);
shape errors raise `ProfileError` (decision 13).

When the key is present the file **replaces** the reader's built-in
fallback table wholesale (one source of truth, no merging); the CSV
direction (time range → period) is derived from whichever table is active,
so the two directions can never drift apart.

**Risk 4**: changing a value changes every filled workbook — the golden
suite pins the built-in table's values, and a profile that references this
file pins its own.
