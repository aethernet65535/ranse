"""erph — the shipped business plugin (Malaysian e-RPH workbooks).

A plugin is a folder under ``./plugins`` following the framework's
convention: ``handlers/<name>/`` registers a handler, ``inputs/<name>/`` a
reader (docs/DESIGN.md S8). Nothing in here is imported by the framework
itself — the plugin is found from the directory it sits in.

| Folder | Contents |
|---|---|
| [`domain.py`](domain.py) | the business types: lessons, schedules, weeks |
| [`handlers/`](handlers/) | the four handlers (`week`, `menu`, `fixed_cells`, `dskp`) |
| [`inputs/`](inputs/) | the three file readers (`calendar`, `timetable`, `dskp`) |
| [`profiles/`](profiles/) | the shipped example profile |
| [`config/`](config/) | the data files the shipped profile references |
| [`README.md`](README.md) | the business index (start here) |
"""
