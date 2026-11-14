# -*- coding: utf-8 -*-
"""preflight_dialog.py — پنجرهٔ «ری‌چک ورودی‌ها» پیش از اجرای جایابی EENS.

درخواست کاربر (v1.15): «قبل از اجرای جایابی بهینهٔ EENS پنجرهٔ ری‌چک کامل
ورودی‌ها برای بررسی نهایی باز شود؛ در حالت فعلی با دادهٔ بار پیش‌فرض کار
می‌کند.»

پنجره فقط **نشان می‌دهد**؛ هیچ عددی را تغییر نمی‌دهد. اگر خطایی وجود
داشته باشد دکمهٔ اجرا غیرفعال می‌شود تا اجرای بی‌معنا (مثلاً بار صفر یا
دامنهٔ خالی) رخ ندهد. هشدارها اجرا را نمی‌بندند ولی صریح می‌گویند کدام
ورودی پیش‌فرض/تخمینی است.
"""
from __future__ import annotations

from ...application.study_preflight import STATUS_FA, PreflightReport


def make_preflight_dialog(parent, report: PreflightReport,
                          *, title: str = "ری‌چک ورودی‌ها پیش از اجرای "
                                           "جایابی بهینهٔ کلید (EENS)"):
    """دیالوگ تأیید ورودی‌ها را می‌سازد و برمی‌گرداند (``exec()`` لازم است)."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                                   QLabel, QScrollArea,
                                   QTableWidget, QTableWidgetItem,
                                   QVBoxLayout, QWidget)

    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumSize(760, 520)
    lay = QVBoxLayout(dlg)

    head = QLabel(
        "این جدول همان ورودی‌هایی است که موتور با آن اجرا می‌شود. "
        "ردیف‌های <span style='color:#c62828'>قرمز</span> مانع اجرا هستند و "
        "ردیف‌های <span style='color:#ef6c00'>نارنجی</span> یعنی مقدار "
        "پیش‌فرض/تخمینی به‌کار می‌رود.")
    head.setWordWrap(True)
    lay.addWidget(head)

    summary = QLabel(report.summary_fa())
    summary.setStyleSheet("font-weight:bold; padding:4px 6px; background:#eceff1;")
    lay.addWidget(summary)

    table = QTableWidget(0, 4)
    table.setHorizontalHeaderLabels(["گروه", "ورودی", "مقدار فعلی", "وضعیت / توضیح"])
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setWordWrap(True)
    table.horizontalHeader().setStretchLastSection(True)
    table.setColumnWidth(0, 120)
    table.setColumnWidth(1, 210)
    table.setColumnWidth(2, 190)

    colors = {"error": QColor("#ffcdd2"), "warn": QColor("#ffe0b2"),
              "ok": QColor("#ffffff")}
    for row in report.rows:
        i = table.rowCount()
        table.insertRow(i)
        note = f"{STATUS_FA.get(row.status, row.status)}"
        if row.note:
            note += f" — {row.note}"
        for col, text in enumerate((row.group, row.item, row.value, note)):
            item = QTableWidgetItem(text)
            item.setBackground(colors.get(row.status, QColor("#ffffff")))
            table.setItem(i, col, item)
    table.resizeRowsToContents()

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    holder = QWidget()
    h = QVBoxLayout(holder)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(table)
    scroll.setWidget(holder)
    lay.addWidget(scroll, 1)

    chk = QCheckBox("ورودی‌ها را بازبینی کردم و با همین مقادیر اجرا شود")
    chk.setChecked(not report.blocking)
    lay.addWidget(chk)

    btns = QDialogButtonBox()
    ok = btns.addButton("تأیید و اجرا", QDialogButtonBox.ButtonRole.AcceptRole)
    cancel = btns.addButton("انصراف", QDialogButtonBox.ButtonRole.RejectRole)
    ok.setEnabled(not report.blocking)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)
    if report.blocking:
        ok.setToolTip("تا رفع خطاها اجرا ممکن نیست.")

    def _sync_ok(_=None) -> None:
        ok.setEnabled(bool(chk.isChecked()) and not report.blocking)
    chk.toggled.connect(_sync_ok)
    _sync_ok()

    dlg.table = table           # برای تست‌های رابط
    dlg.summary_label = summary
    dlg.confirm_checkbox = chk
    dlg.run_button = ok
    dlg.cancel_button = cancel
    dlg.report = report
    return dlg
