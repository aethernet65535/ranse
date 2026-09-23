"""Cell/area reference helpers and low-level path resolution.

Pure functions only — no business knowledge (docs/DESIGN.md decision 6).
"""

import os
import re
from datetime import datetime

from ..errors import SheetError

_EXCEL_EPOCH = datetime(1899, 12, 30)


def _col_to_num(col_str):
    """'A' → 1, 'Z' → 26, 'AA' → 27."""
    n = 0
    for ch in col_str.upper():
        n = n * 26 + (ord(ch) - 64)
    return n


def _col_letter(n):
    """1 → 'A', 26 → 'Z', 27 → 'AA'."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell_ref(row, col):
    """(6, 3) → 'C6'."""
    return f"{_col_letter(col)}{row}"


def _parse_cell_ref(ref):
    """'C6' → (row=6, col=3)."""
    m = re.match(r"([A-Z]+)(\d+)", ref)
    if m is None:
        # core never lets a bare AttributeError escape (decision 13)
        raise SheetError(f"invalid cell reference: {ref!r}")
    return int(m.group(2)), _col_to_num(m.group(1))


def _date_to_excel(dt):
    return (dt - _EXCEL_EPOCH).days


def _cell_range_top_left(range_str):
    """'B3:C3' → 'B3'."""
    m = re.match(r"([A-Z]+\d+)", range_str)
    return m.group(1) if m else range_str


def _resolve_path(path, bases):
    """Resolve a possibly-relative path against a list of base directories."""
    if os.path.isabs(path):
        return path
    for base in bases:
        candidate = os.path.join(base, path)
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(bases[0], path)
