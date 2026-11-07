# -*- coding: utf-8 -*-
"""دیالوگ «رتبه‌بندی مکان‌های خاموشی» (درخواست کاربر).

فهرست مکان‌ها را بر اساس **تعداد تکرار خاموشی** مرتب می‌کند: رتبه، مکان،
فیدر، تعداد، سهم درصدی، توزیع وضعیت بازبینی، زون غالب و مختصات مرکز.
خروجی قابل ذخیره به‌صورت CSV است تا در گزارش رسمی استفاده شود.

منطق گروه‌بندی در ``application/outage_review.py::outage_place_ranking``
است (Qt-free و آزمون‌شده)؛ این فایل فقط نمایش است.
"""
from __future__ import annotations


def show_outage_ranking_dialog(parent, points, *, title: str = "",
                               on_focus=None):     # pragma: no cover (Qt)
    """نمایش جدول رتبه‌بندی مکان‌های خاموشی؛ برگرداندن دیالوگ اجراشده."""
    import csv

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog,
                                   QHBoxLayout, QLabel, QMessageBox,
                                   QPushButton, QSplitter, QTableWidget,
                                   QTableWidgetItem, QTextEdit, QVBoxLayout,
                                   QWidget)

    from ...application.outage_review import outage_place_ranking
    from .widgets import fill_table

    rows = outage_place_ranking(points or [])
    headers = ["رتبه", "مکان", "فیدر", "تعداد خاموشی", "سهم (٪)",
               "تأیید مهندسی", "در انتظار", "رد‌شده", "زون", "X", "Y"]

    dlg = QDialog(parent)
    dlg.setWindowTitle(title or "SwitchLoc — رتبه‌بندی مکان‌های خاموشی")
    dlg.setMinimumSize(680, 420)
    dlg.resize(900, 560)

    root = QVBoxLayout(dlg)
    head = QLabel(
        "<b>رتبه‌بندی مکان‌های خاموشی</b> — بر اساس تعداد تکرار، به‌همراه "
        "سهم درصدی و ترکیب وضعیت بازبینی. با دوبار کلیک روی یک ردیف، "
        "همان نقطه روی نقشه برجسته می‌شود.")
    head.setWordWrap(True)
    root.addWidget(head)

    split = QSplitter(Qt.Orientation.Vertical)
    split.setChildrenCollapsible(True)
    root.addWidget(split, 1)

    table = QTableWidget(0, len(headers))
    table.setSortingEnabled(True)
    table.setSelectionBehavior(
        QAbstractItemView.SelectionBehavior.SelectRows)
    table.setAlternatingRowColors(True)
    data = [[str(r["rank"]), r["place"], r["feeder"], str(r["count"]),
             f"{r['share_percent']:.2f}", str(r["confirmed"]),
             str(r["pending"]), str(r["rejected"]),
             (r["zone_id"] or "")[:8], f"{r['x']:,.0f}", f"{r['y']:,.0f}"]
            for r in rows]
    fill_table(table, headers, data)
    split.addWidget(table)

    summary = QTextEdit()
    summary.setReadOnly(True)
    total = sum(r["count"] for r in rows)
    top = rows[:10]
    text = [f"مجموع رخدادها: {total} — تعداد مکان‌ها: {len(rows)}", ""]
    for r in top:
        text.append(f"{r['rank']:>2}. {r['place']} — {r['count']} خاموشی "
                    f"({r['share_percent']:.1f}٪) · فیدر {r['feeder'] or '—'}")
    summary.setPlainText("\n".join(text))
    split.addWidget(summary)
    split.setSizes([380, 150])

    btns = QHBoxLayout()
    btn_csv = QPushButton("ذخیرهٔ CSV")
    btn_close = QPushButton("بستن")

    def _save_csv() -> None:
        path, _ = QFileDialog.getSaveFileName(
            dlg, "ذخیرهٔ رتبه‌بندی", "outage_place_ranking.csv",
            "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                wr = csv.writer(fh)
                wr.writerow(headers)
                wr.writerows(data)
        except OSError as exc:                     # noqa: BLE001
            QMessageBox.warning(dlg, "ذخیرهٔ CSV", f"نوشتن فایل ناموفق بود: {exc}")
            return
        QMessageBox.information(dlg, "ذخیرهٔ CSV", f"ذخیره شد:\n{path}")

    def _focus(_row: int, _col: int = 0) -> None:
        if on_focus is None:
            return
        row = table.currentRow()
        if 0 <= row < len(rows):
            on_focus(float(rows[row]["x"]), float(rows[row]["y"]), rows[row])

    btn_csv.clicked.connect(_save_csv)
    btn_close.clicked.connect(dlg.accept)
    table.cellDoubleClicked.connect(_focus)
    btns.addWidget(btn_csv)
    btns.addStretch(1)
    btns.addWidget(btn_close)
    root.addLayout(btns)
    dlg.exec()
    return dlg
