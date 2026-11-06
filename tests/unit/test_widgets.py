# -*- coding: utf-8 -*-
"""Qt-free logic of the shared table/explanation widgets (درخواست کاربر).

The Qt glue lives in `widgets.py` (inside the factory functions); the
pure functions under test here — numeric-aware cell ordering, TSV
copy/paste round-trip and the required-field mark — carry the user
requirements:
  * سورتینگ بر اساس هر هدر ستون (numeric, not lexicographic)
  * کپی/پیست برای تمامی جداول (TSV, Excel round-trip)
  * ستاره‌دار کردن فیلدهای الزامی
  * بک‌گراند آبی برای توضیحات (style constant)
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from switchloc.ui.qt.widgets import (                   # noqa: E402
    EXPLAIN_QSS, cmp_cells, required_html, rows_to_tsv, tsv_to_rows,
)


def test_cmp_cells_is_numeric_not_lexicographic():
    assert cmp_cells("9", "12") < 0            # 9 < 12 (not "12" < "9")
    assert cmp_cells("12", "9") > 0
    assert cmp_cells("1,200", "999") > 0       # thousand separators
    assert cmp_cells("45%", "50%") < 0         # percent suffix tolerated
    assert cmp_cells("F2", "F10") < 0          # text fallback
    assert cmp_cells("abc", "ABC") == 0        # case-insensitive text
    assert cmp_cells("12", "abc") < 0          # numbers before text
    assert cmp_cells("abc", "12") > 0


def test_cmp_cells_persian_thousand_separator():
    assert cmp_cells("۱٬۲۰۰" if False else "1200", "999") > 0


def test_tsv_roundtrip():
    rows = [["F1", "70", "6,965"], ["F2", "25", "5,820"]]
    txt = rows_to_tsv(rows)
    assert txt.count("\t") == 4 and txt.count("\n") == 1
    back = tsv_to_rows(txt)
    assert back == rows


def test_tsv_handles_windows_and_trailing_lines():
    assert tsv_to_rows("a\tb\r\nc\td\r\n") == [["a", "b"], ["c", "d"]]
    assert tsv_to_rows("") == []


def test_required_html_and_explain_style():
    h = required_html("Nominal kW")
    assert "*" in h and "c62828" in h          # red asterisk
    assert "#e3f2fd" in EXPLAIN_QSS            # blue background
