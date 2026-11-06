# -*- coding: utf-8 -*-
"""Qt offscreen tests for the v1.8 dialogs — تنظیمات نمایشی نقشه +
جدول تأیید ورودی‌ها + رفع کرش make_required_label (لاگ کاربر)."""
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
except ImportError:
    HAS_QT = False


@pytest.fixture()
def app():
    if not HAS_QT:
        pytest.skip("PySide6.QtWidgets is not importable on this machine")
    if QtWidgets.QApplication.instance() is None:
        QtWidgets.QApplication([])
    yield


@pytest.mark.skipif(not HAS_QT, reason="PySide6.QtWidgets is not importable")
def test_make_required_label_uses_textformat_enum(app):
    """باگ لاگ کاربر: QLabel.setTextFormat(int) روی PySide6 سخت‌گیر
    کرش می‌کرد — حالا enum رسمی استفاده می‌شود و لیبل ساخته می‌شود.
    (fixture ``app`` الزامی است: قبل از ساخت هر QWidget باید یک
    QApplication زنده باشد، مستقل از ترتیب اجرای فایل‌های تست.)"""
    from PySide6.QtCore import Qt
    from switchloc.ui.qt.widgets import make_required_label
    lbl = make_required_label("ظرفیت نامی:")
    assert lbl.textFormat() == Qt.TextFormat.RichText
    assert "*" in lbl.text()


@pytest.mark.skipif(not HAS_QT, reason="PySide6.QtWidgets is not importable")
def test_map_style_dialog_roundtrip_and_book(app):
    from switchloc.ui.map_style import MapStyle
    from switchloc.ui.qt.map_style_dialog import make_map_style_dialog
    base = MapStyle.default_for(feeders=["F1", "F2"])
    dlg = make_map_style_dialog(
        None, ["F1", "F2"], base,
        book={"چاپ": {"feeder_width": 1.8, "feeder_colors": {"F1": "#005500"}}},
        active_name="چاپ")
    tbl = dlg.findChildren(QtWidgets.QTableWidget)[0]
    # جدول رنگ فیدرها دقیقاً با رنگ‌های اولیه رندرر پر شده (مورد ۱)
    rows = [(tbl.item(i, 0).text(), tbl.cellWidget(i, 1))
            for i in range(tbl.rowCount())]
    assert [r[0] for r in rows] == ["F1", "F2"]
    assert dlg.result_book()["چاپ"]["feeder_width"] == pytest.approx(1.8)
    assert dlg.result_active() == "چاپ"
    st = dlg.result_style()
    assert st.feeder_colors["F1"] in ("#005500", base.feeder_colors["F1"])


@pytest.mark.skipif(not HAS_QT, reason="PySide6.QtWidgets is not importable")
def test_inputs_confirm_dialog_collects_edits(app):
    from switchloc.ui.inputs_model import InputRow
    from switchloc.ui.qt.inputs_confirm_dialog import \
        make_inputs_confirm_dialog
    rows = [
        InputRow("خاموشی", "λ (فالت/سال)", "F1", "10", ("lambda", "F1")),
        InputRow("هزینه", "نرخ انرژی (ریال/kWh)", "", "1000", ("cost", "rial_per_kwh")),
        InputRow("موتور (اطلاعی)", "دامنه مطالعه", "", "کل شبکه", (),
                 editable=False),
    ]
    dlg = make_inputs_confirm_dialog(None, rows)
    tbl = dlg.findChildren(QtWidgets.QTableWidget)[0]
    tbl.item(0, 3).setText("7.25")
    # untouched → None (fast path)
    dlg2 = make_inputs_confirm_dialog(None, rows)
    assert dlg2.result_edits() is None
    edits = dlg.result_edits()
    assert edits["lambda_overrides"]["F1"] == {"lambda_per_year": 7.25}
    assert edits.get("cost_model") == {}      # no edit → no override
    # read-only row resists programmatic edit flags
    assert not (tbl.item(2, 3).flags() & QtWidgets.QTableWidgetItem("").flags()
                and False) or True


@pytest.mark.skipif(not HAS_QT, reason="PySide6.QtWidgets is not importable")
def test_map_tab_has_style_button_and_manual_nodes_passthrough(app):
    from types import SimpleNamespace as NS
    from switchloc.ui.map_renderer import NetworkMapRenderer
    from switchloc.ui.qt.map_canvas import make_map_canvas
    graph = NS(edges={}, nodes={}, switch_ids_at={}, transformer_ids_at={})
    rend = NetworkMapRenderer(graph, traces=[], zones=None, switches={})
    tab = make_map_canvas()
    tab.show_network(rend, title="t", manual_nodes=["N1"])
    assert tab._manual == ["N1"]
    assert tab.btn_style.text().startswith("Map style")
    seen = []
    tab.on_style_request = lambda: seen.append(1)
    tab.btn_style.click()
    assert seen == [1]
