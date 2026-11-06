# -*- coding: utf-8 -*-
"""Placement-inputs confirmation dialog — تأیید نهایی ورودی‌ها
(درخواست کاربر، مورد ۵).

Shows ONE sortable/copyable/editable table of EVERY input the
placement/manual-evaluation logic consumes (λ/r هر فیدر، بار Load
Scaling، ظرفیت‌ها، هزینه‌ها، معیارهای پذیرش، پنجره پوشش داده و وزن‌های
جدول ۱۶).  Only «تأیید و اجرا» lets the run proceed; the edited values
are written back through the Qt-free `apply_row_edits` so the
calculation really uses the confirmed numbers.

Discipline: the data logic lives in ui/inputs_model.py; this module is
the thin Qt glue (same split as settings_dialog).
"""
from __future__ import annotations

from ..inputs_model import InputRow, apply_row_edits


def make_inputs_confirm_dialog(parent, rows: list[InputRow],
                               title: str = "تأیید نهایی داده‌های ورودی محاسبات"):
    """Return the dialog; caller exec()s it and on accept reads
    ``dlg.result_edits()`` (the apply_row_edits bundle) — or None when
    nothing was touched (fast path)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import (QAbstractItemView, QDialog,
                                   QDialogButtonBox, QHBoxLayout, QLabel,
                                   QMessageBox, QPushButton, QTableWidget,
                                   QTableWidgetItem, QVBoxLayout)

    dlg = QDialog(parent)
    dlg.setWindowTitle(f"SwitchLoc — {title}")
    dlg.setMinimumSize(860, 560)
    lay = QVBoxLayout(dlg)

    head = QLabel(
        "<b>قبل از اجرای جایابی، همه داده‌های ورودی محاسبات را تأیید "
        "کنید.</b><br>مقادیر ستون «مقدار» قابل ویرایش‌اند — محاسبات با "
        "همین مقادیر تأییدشده انجام می‌شود (ردیف‌های اطلاعی قابل ویرایش "
        "نیستند). جدول با Ctrl+C قابل کپی است.")
    head.setWordWrap(True)
    lay.addWidget(head)

    tbl = QTableWidget(len(rows), 5)
    tbl.setHorizontalHeaderLabels(["گروه", "پارامتر", "فیدر", "مقدار",
                                   "منشأ / توضیح"])
    tbl.horizontalHeader().setStretchLastSection(True)
    tbl.verticalHeader().setVisible(False)
    tbl.setSortingEnabled(False)          # rows keep the logical order
    tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    lay.addWidget(tbl, 1)

    for i, r in enumerate(rows):
        vals = [r.group, r.param, r.feeder, r.value, r.note]
        for j, v in enumerate(vals):
            it = QTableWidgetItem(str(v))
            if j == 3 and r.editable and r.key:
                pass                       # editable value cell
            else:
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if not r.editable:
                    # AlternateBase یک نقش پالت است نه Qt.GlobalColor —
                    # رنگ پالت تم‌محور است و در آف‌اسکرین هم کار می‌کند.
                    it.setBackground(dlg.palette().color(
                        QPalette.ColorRole.AlternateBase))
            tbl.setItem(i, j, it)
    tbl.resizeColumnsToContents()
    tbl.setColumnWidth(1, 240)
    tbl.setColumnWidth(4, 280)

    btns_row = QHBoxLayout()
    btn_revert = QPushButton("بازگرداندن مقادیر اصلی")
    btn_revert.clicked.connect(lambda: _reload())
    btns_row.addWidget(btn_revert)
    btns_row.addStretch(1)
    lay.addLayout(btns_row)

    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                            QDialogButtonBox.StandardButton.Cancel)
    btns.button(QDialogButtonBox.StandardButton.Ok).setText("تأیید و اجرا")
    btns.button(QDialogButtonBox.StandardButton.Cancel).setText("انصراف")
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)

    def _reload() -> None:
        for i, r in enumerate(rows):
            it = tbl.item(i, 3)
            if it is not None:
                it.setText(str(r.value))

    def result_edits() -> dict | None:
        """Bundle of edits (or None when every cell stayed untouched).

        Only rows whose cell text actually differs from the original
        value reach apply_row_edits — untouched rows must NOT surface
        as overrides (no edit → cost_model == {} and so on)."""
        touched_rows = []
        for i, r in enumerate(rows):
            it = tbl.item(i, 3)
            if r.editable and r.key and it is not None and \
                    it.text() != str(r.value):
                touched_rows.append(
                    InputRow(group=r.group, param=r.param, feeder=r.feeder,
                             value=it.text(), key=r.key, editable=True,
                             note=r.note))
        if not touched_rows:
            return None
        edits = apply_row_edits(touched_rows)
        if edits.get("ignored"):
            QMessageBox.warning(
                dlg, "تأیید ورودی‌ها",
                "برخی مقادیر عددی معتبر نبودند و مقدار اصلی حفظ شد:\n"
                + "، ".join(edits["ignored"]))
        return edits

    dlg.result_edits = result_edits      # type: ignore[attr-defined]
    return dlg
