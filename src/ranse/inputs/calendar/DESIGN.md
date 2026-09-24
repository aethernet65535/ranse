# Calendar reader — school-weeks schema

Reads the shipped example's school-calendar YAML (one folder per source
format, [`inputs/README.md`](../README.md)). It is a pure input: it never
touches the target workbook (decision 8,
[`docs/DESIGN.md`](../../../../docs/DESIGN.md)).

Loader: `load_calendar_config(path)` → dict. It validates only that a `weeks:`
list exists (otherwise `ProfileError`, decision 13) and adds `_config_dir`
so relative paths inside the file resolve next to it.

The schema itself is contract, documented with the data file:
[`config/school-weeks/DESIGN.md`](../../../../config/school-weeks/DESIGN.md).

A profile references this file through its own `inputs.calendar` key; the
`week` handler reads that key and calls this loader (D11: data files are
referenced by the profile, and the handler that reads them owns their use).
