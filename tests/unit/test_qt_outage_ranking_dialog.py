# -*- coding: utf-8 -*-
"""Qt offscreen: دیالوگ «رتبه‌بندی مکان‌های خاموشی» (درخواست کاربر — بند ۷)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest                                        # noqa: E402

try:
    from PySide6 import QtWidgets                    # noqa: E402
    HAS_QT = True
except ImportError:                                  # pragma: no cover
    HAS_QT = False

pytestmark = pytest.mark.skipif(
    not HAS_QT, reason="PySide6.QtWidgets is not importable")


@pytest.fixture()
def app():
    if QtWidgets.QApplication.instance() is None:
        QtWidgets.QApplication([])
    yield


def _points():
    return [
        {"id": f"e{i}", "x": 100.0 + i, "y": 200.0 + i, "place": "کرندق",
         "feeder": "F3", "status": "confirmed", "zone_id": "z1"}
        for i in range(3)
    ] + [
        {"id": "n1", "x": 300.0, "y": 400.0, "place": "نوده",
         "feeder": "F5", "status": "pending", "zone_id": "z2"},
    ]


def test_dialog_lists_places_ranked_by_count(app, monkeypatch):
    from switchloc.ui.qt.outage_ranking_dialog import \
        show_outage_ranking_dialog

    monkeypatch.setattr(QtWidgets.QDialog, "exec", lambda self: 0)
    dlg = show_outage_ranking_dialog(None, _points())
    tables = [t for t in dlg.findChildren(QtWidgets.QTableWidget)
              if t.rowCount()]
    assert tables, "جدول رتبه‌بندی ساخته نشد"
    tbl = tables[0]
    assert tbl.rowCount() == 2                       # دو مکان
    assert tbl.item(0, 1).text() == "کرندق"          # بیشترین تعداد اول
    assert tbl.item(0, 3).text() == "3"
    assert tbl.item(0, 4).text() == "75.00"
    assert tbl.item(1, 1).text() == "نوده"


def test_dialog_focus_callback_gets_coordinates(app, monkeypatch):
    from switchloc.ui.qt.outage_ranking_dialog import \
        show_outage_ranking_dialog

    monkeypatch.setattr(QtWidgets.QDialog, "exec", lambda self: 0)
    seen = []
    dlg = show_outage_ranking_dialog(None, _points(),
                                     on_focus=lambda x, y, row: seen.append(
                                         (x, y, row["place"])))
    tbl = [t for t in dlg.findChildren(QtWidgets.QTableWidget)
           if t.rowCount()][0]
    tbl.setCurrentCell(0, 0)
    tbl.cellDoubleClicked.emit(0, 0)
    assert seen and seen[0][2] == "کرندق"
    assert seen[0][0] == pytest.approx(101.0)        # مرکز سه نقطهٔ کرندق


def test_empty_point_list_is_stated(app, monkeypatch):
    from switchloc.ui.qt.outage_ranking_dialog import \
        show_outage_ranking_dialog

    monkeypatch.setattr(QtWidgets.QDialog, "exec", lambda self: 0)
    dlg = show_outage_ranking_dialog(None, [])
    tables = [t for t in dlg.findChildren(QtWidgets.QTableWidget)]
    assert tables and tables[0].rowCount() == 0
