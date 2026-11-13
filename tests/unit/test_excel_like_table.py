# -*- coding: utf-8 -*-
"""Excel-like grid behavior for the outage review table (درخواست کاربر):
copy/paste of whole rows/columns and header-line selection.

The Qt glue in ``ui.qt.widgets`` is exercised here with a lightweight fake
``QTableWidget`` so the logic (bounding-rect block copy, combo-cell paste
matching, read-only skip counting) is verified without PySide6.
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from switchloc.application.outage_review import (GAZETTEER_ENV_VAR,
                                                 default_gazetteer_path)
from switchloc.ui.qt import widgets


# ---------------------------------------------------------------------------
# بارگذار جعلی PySide6.QtCore فقط برای پرچم ItemIsEditable
# ---------------------------------------------------------------------------
@pytest.fixture()
def fake_qtcore(monkeypatch):
    mod = types.ModuleType("PySide6.QtCore")

    class _ItemFlag:
        ItemIsEditable = 0x0001

    mod.Qt = SimpleNamespace(ItemFlag=_ItemFlag)
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", mod)
    return mod


class FakeItem:
    def __init__(self, text: str, editable: bool = True):
        self._text = str(text)
        self._editable = editable

    def text(self):
        return self._text

    def setText(self, v):
        self._text = str(v)

    def flags(self):
        return 0x0002 | (0x0001 if self._editable else 0)


class FakeCombo:
    """کمینهٔ QComboBox: متن نمایشی + findText/findData."""

    def __init__(self, options, datas=None):
        self._options = list(options)
        self._datas = list(datas) if datas is not None else list(options)
        self._idx = 0

    def count(self):
        return len(self._options)

    def itemText(self, k):
        return self._options[k]

    def currentText(self):
        return self._options[self._idx] if self._options else ""

    def currentData(self):
        return self._datas[self._idx] if self._datas else None

    def findText(self, s):
        needle = str(s).strip().casefold()
        for k, o in enumerate(self._options):
            if o.strip().casefold() == needle:
                return k
        return -1

    def findData(self, d):
        for k, v in enumerate(self._datas):
            if str(v) == str(d):
                return k
        return -1

    def setCurrentIndex(self, k):
        self._idx = int(k)


class FakeRange:
    def __init__(self, top, bottom, left, right):
        self._v = (int(top), int(bottom), int(left), int(right))

    def topRow(self):
        return self._v[0]

    def bottomRow(self):
        return self._v[1]

    def leftColumn(self):
        return self._v[2]

    def rightColumn(self):
        return self._v[3]


class FakeTable:
    def __init__(self, rows: int, cols: int):
        self._rows, self._cols = rows, cols
        self._items = {}
        self._widgets = {}
        self._ranges = []
        self._current = (0, 0)

    # -- ساختار -----------------------------------------------------------
    def rowCount(self):
        return self._rows

    def columnCount(self):
        return self._cols

    def setItem(self, i, j, item):
        self._items[(i, j)] = item

    def item(self, i, j):
        return self._items.get((i, j))

    def setCellWidget(self, i, j, widget):
        self._widgets[(i, j)] = widget

    def cellWidget(self, i, j):
        return self._widgets.get((i, j))

    # -- انتخاب -------------------------------------------------------------
    def setRanges(self, ranges):
        self._ranges = [FakeRange(*r) for r in ranges]

    def selectedRanges(self):
        return list(self._ranges)

    def currentItem(self):
        return self._items.get(self._current)

    def currentRow(self):
        return self._current[0]

    def currentColumn(self):
        return self._current[1]

    def setCurrent(self, i, j):
        self._current = (i, j)


def _grid(rows=2, cols=4):
    t = FakeTable(rows, cols)
    for i in range(rows):
        for j in range(cols):
            t.setItem(i, j, FakeItem(f"r{i}c{j}", editable=(j != 0)))
    return t


# ---------------------------------------------------------------------------
# کپی: کل سطر/ستون/بازه → TSV (خانهٔ کمبو متن نمایشی را می‌دهد)
# ---------------------------------------------------------------------------
def test_copy_whole_column_selection(fake_qtcore):
    t = _grid(2, 3)
    t.setRanges([(0, 1, 2, 2)])                    # کل ستون ۲
    assert widgets._selected_rows(t) == [["r0c2"], ["r1c2"]]


def test_copy_bounding_rectangle_with_widget_cell(fake_qtcore):
    t = _grid(2, 3)
    t.setCellWidget(0, 2, FakeCombo(["خواجه بلاغی (زیاد)"]))
    # بازهٔ ناپیوسته: سلول (۱,۰) پوشش داده نمی‌شود → خالی می‌ماند
    t.setRanges([(0, 0, 0, 2), (1, 1, 1, 2)])
    rows = widgets._selected_rows(t)
    assert rows == [["r0c0", "r0c1", "خواجه بلاغی (زیاد)"],
                    ["", "r1c1", "r1c2"]]
    assert "\t".join(rows[0]) == "r0c0\tr0c1\tخواجه بلاغی (زیاد)"


def test_copy_current_cell_when_no_selection(fake_qtcore):
    t = _grid(2, 3)
    t.setCurrent(1, 1)
    assert widgets._selected_rows(t) == [["r1c1"]]


# ---------------------------------------------------------------------------
# پیست: آیتم‌های قابل‌ویرایش نوشته می‌شوند؛ فقط‌خواندنی‌ها رد می‌شوند؛
# کمبو با متن/داده تطبیق می‌یابد و هیچ مقدار حدسی ساخته نمی‌شود
# ---------------------------------------------------------------------------
def test_paste_writes_editable_items_and_skips_read_only(fake_qtcore):
    t = _grid(2, 3)
    t.setCurrent(0, 0)                              # j=0 فقط‌خواندنی است
    pasted, skipped = widgets._paste_rows(t, [["a", "b", "c"]])
    assert (pasted, skipped) == (2, 1)
    assert t.item(0, 0).text() == "r0c0"
    assert t.item(0, 1).text() == "b"
    assert t.item(0, 2).text() == "c"


def test_paste_into_combo_matches_by_text_and_data(fake_qtcore):
    t = _grid(1, 2)
    combo = FakeCombo(["—", "زرج آباد (زیاد)", "کجین (متوسط)"],
                      datas=["", "p-zaraj", "p-kojan"])
    t.setCellWidget(0, 1, combo)
    t.setCurrent(0, 1)
    pasted, skipped = widgets._paste_rows(t, [["زرج آباد (زیاد)"]])
    assert (pasted, skipped) == (1, 0)
    assert combo.currentData() == "p-zaraj"
    # متن ناموجود → هیچ مقداری ساخته نمی‌شود و رد شمرده می‌شود
    pasted, skipped = widgets._paste_rows(t, [["شهر خیالی"]])
    assert (pasted, skipped) == (0, 1)
    assert combo.currentData() == "p-zaraj"
    # تطبیق با داده (place_id) هم مجاز است
    pasted, skipped = widgets._paste_rows(t, [["p-kojan"]])
    assert (pasted, skipped) == (1, 0)
    assert combo.currentData() == "p-kojan"


def test_paste_bounds_are_clipped(fake_qtcore):
    t = _grid(1, 2)
    t.setCurrent(0, 1)
    pasted, skipped = widgets._paste_rows(t, [["x", "y", "z"], ["w"]])
    assert (pasted, skipped) == (1, 0)               # سرریز پیست سکوت می‌شود


# ---------------------------------------------------------------------------
# مسیر بانک آفلاین مکان‌ها: بدون ایجاد فایل، با قابلیت override محیطی
# ---------------------------------------------------------------------------
def test_default_gazetteer_path_prefers_env_override(tmp_path, monkeypatch):
    bank = tmp_path / "bank.sqlite"
    bank.write_bytes(b"")
    monkeypatch.setenv(GAZETTEER_ENV_VAR, str(bank))
    assert default_gazetteer_path() == bank


def test_default_gazetteer_path_falls_back_without_creating(monkeypatch, tmp_path):
    monkeypatch.setenv(GAZETTEER_ENV_VAR, str(tmp_path / "missing.sqlite"))
    # مسیر exe و مسیر ماژول را هر دو به پوشهٔ موقتِ بدون data/ ببریم —
    # نتیجهٔ «هیچ بانک معتبری نیست» باید قطعی و مستقل از ماشین باشد
    monkeypatch.setattr("switchloc.application.outage_review.__file__",
                        str(tmp_path / "pkg" / "outage_review.py"))
    monkeypatch.setattr("sys.executable", str(tmp_path / "bin" / "python"))
    monkeypatch.delattr("sys._MEIPASS", raising=False)
    assert default_gazetteer_path() is None
    assert not (tmp_path / "missing.sqlite").exists()   # هیچ فایلی ساخته نشد


def test_default_gazetteer_path_returns_none_for_bad_env_value(monkeypatch, tmp_path):
    """اگر متغیر محیطی به فایل ناموجود اشاره کند، هیچ جای دیگری سکوت‌وار
    جایگزین نمی‌شود — پیشنهاد مکان غیرفعال می‌ماند (سکوت ممنوع)."""
    monkeypatch.setenv(GAZETTEER_ENV_VAR, str(tmp_path / "missing.sqlite"))
    assert default_gazetteer_path() is None


def test_default_gazetteer_path_reads_exe_dir_layout(monkeypatch, tmp_path):
    """چیدمان نسخهٔ exe: بانک کنار فایل اجرایی در پوشهٔ data/… پیدا شود."""
    bank = tmp_path / "dist" / "data" / "geography" / "ardabil_places.sqlite"
    bank.parent.mkdir(parents=True)
    bank.write_bytes(b"")
    exe = tmp_path / "dist" / "SwitchLoc.exe"
    exe.write_bytes(b"")
    monkeypatch.delenv(GAZETTEER_ENV_VAR, raising=False)
    monkeypatch.setattr("sys.executable", str(exe))
    monkeypatch.delattr("sys._MEIPASS", raising=False)
    assert default_gazetteer_path() == bank


def test_default_gazetteer_path_finds_repo_bank(monkeypatch):
    monkeypatch.delenv(GAZETTEER_ENV_VAR, raising=False)
    path = default_gazetteer_path()
    # در مخزن توسعه، بانک همراه در data/geography موجود است
    assert path is not None and path.is_file()
    assert path.name == "ardabil_places.sqlite"
