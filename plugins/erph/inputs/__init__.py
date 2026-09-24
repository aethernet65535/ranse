"""erph readers — one folder per source format, the folder name is the name.

These readers turn the plugin's source files into the objects in
[`domain.py`](../domain.py); they never touch the target workbook. Each
folder carries its own ``DESIGN.md``. A reader that should also be a
standalone module ships a ``__main__.py`` (``python -m erph.inputs.dskp``).
"""
