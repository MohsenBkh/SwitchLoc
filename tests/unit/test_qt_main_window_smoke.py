# -*- coding: utf-8 -*-
"""Qt offscreen smoke: کل پوستهٔ دسکتاپ باید ساخته شود (بدون حلقهٔ رویداد).

این آزمون ویجت‌به‌ویجت نیست؛ هدفش همان چیزی است که ``ast.parse`` نمی‌بیند:
import‌های تنبل، اتصال سیگنال‌ها، ساخت تب‌ها و ترتیب آن‌ها. اگر ساخت
پنجره در جایی بشکند (مثلاً نام اشتباه یک ویجت یا callback)، این تست
خطا می‌دهد.
"""
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

EXPECTED_TABS = ["Data Import", "Topology", "Placement",
                 "Switch placement & EENS", "Dashboard", "Map"]


@pytest.fixture()
def app():
    if QtWidgets.QApplication.instance() is None:
        QtWidgets.QApplication([])
    yield QtWidgets.QApplication.instance()


def test_desktop_shell_builds_with_sectionalizer_tab(app, monkeypatch, tmp_path):
    from switchloc.ui.qt import main_window

    labels: list[str] = []
    add_tab = QtWidgets.QTabWidget.addTab

    def record(self, widget, label):
        labels.append(str(label))
        return add_tab(self, widget, label)

    windows: list = []
    orig_show = QtWidgets.QMainWindow.show

    def show(self):
        windows.append(self)          # مرجع زنده نگه داشته می‌شود
        return orig_show(self)

    monkeypatch.setattr(QtWidgets.QTabWidget, "addTab", record)
    monkeypatch.setattr(QtWidgets.QMainWindow, "show", show)
    # حلقهٔ رویداد لازم نیست: پنجره پیش از exec ساخته شده است. دیالوگ‌ها هم
    # بی‌درنگ بسته می‌شوند تا خطای احتمالی تست را قفل نکند.
    monkeypatch.setattr(QtWidgets.QApplication, "exec", lambda self: 0)
    monkeypatch.setattr(QtWidgets.QDialog, "exec", lambda self: 0)
    monkeypatch.setenv("SWITCHLOC_HOME", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    rc = main_window.launch(None)
    assert rc == 0
    assert labels == EXPECTED_TABS

    # تب جدید واقعاً همان کلاس کنترلر است (نه فقط یک لیبل)
    assert windows, "پنجرهٔ اصلی ساخته نشد"
    bars = [w for w in windows[0].findChildren(QtWidgets.QTabWidget)
            if [w.tabText(i) for i in range(w.count())] == EXPECTED_TABS]
    assert bars, "نوار تب اصلی با ترتیب انتظار یافت نشد"
    bar = bars[0]
    names = [bar.tabText(i) for i in range(bar.count())]
    sec = bar.widget(names.index("Switch placement & EENS"))
    assert type(sec).__name__ == "SwitchPlacementTab"
    assert hasattr(sec, "show_result") and hasattr(sec, "apply_settings")
