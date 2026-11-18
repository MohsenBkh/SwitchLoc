# -*- coding: utf-8 -*-
"""UI for exhaustive Level-2 placement (EENS objective + load-flow limits)."""
from __future__ import annotations


def make_level2_placement_tab(parent=None):  # pragma: no cover - Qt UI
    from pathlib import Path

    from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel,
                                   QLineEdit, QMessageBox, QPushButton,
                                   QTextEdit, QVBoxLayout, QWidget)

    class Level2PlacementTab(QWidget):
        def __init__(self, parent_=None):
            super().__init__(parent_)
            self.on_run = None
            self._result = None
            root = QVBoxLayout(self)
            intro = QLabel(
                "<b>جایابی بهینه سطح دوم</b> — جست‌وجوی شمارشی آرایش‌های کلید، "
                "کمینه‌سازی EENS و رد آرایش‌های ناقض قیود پخش بار حالت ماندگار. "
                "بودجه و ورودی‌های واقعی شبکه را در فایل JSON تنظیم کنید.")
            intro.setWordWrap(True)
            root.addWidget(intro)

            row = QHBoxLayout()
            self.config_path = QLineEdit()
            self.config_path.setPlaceholderText("مسیر فایل پیکربندی JSON سطح ۲")
            browse = QPushButton("انتخاب فایل…")
            browse.clicked.connect(self._browse)
            self.run_button = QPushButton("اجرای جایابی سطح ۲")
            self.run_button.clicked.connect(self._run)
            self.save_button = QPushButton("ذخیره گزارش…")
            self.save_button.setEnabled(False)
            self.save_button.clicked.connect(self._save_report)
            row.addWidget(self.config_path, 1)
            row.addWidget(browse)
            row.addWidget(self.run_button)
            row.addWidget(self.save_button)
            root.addLayout(row)

            self.status = QLabel("آماده — اجرای تحلیل به JSON با بودجه، بار، نرخ‌های قابلیت اطمینان و داده‌های پخش بار نیاز دارد.")
            self.status.setWordWrap(True)
            root.addWidget(self.status)
            self.report = QTextEdit()
            self.report.setReadOnly(True)
            self.report.setPlaceholderText("گزارش جایابی سطح دوم پس از اجرا اینجا نمایش داده می‌شود.")
            root.addWidget(self.report, 1)

        def _browse(self):
            path, _ = QFileDialog.getOpenFileName(
                self, "انتخاب پیکربندی جایابی سطح ۲", "", "JSON (*.json)")
            if path:
                self.config_path.setText(path)

        def _run(self):
            path = self.config_path.text().strip()
            if not path or not Path(path).is_file():
                QMessageBox.warning(self, "پیکربندی لازم است",
                                    "یک فایل JSON معتبر برای جایابی سطح ۲ انتخاب کنید.")
                return
            if self.on_run is None:
                QMessageBox.warning(self, "پروژه آماده نیست",
                                    "اجرای سرویس جایابی به پروژهٔ باز نیاز دارد.")
                return
            self.on_run(path)

        def set_busy(self, busy: bool, message: str = ""):
            self.run_button.setEnabled(not busy)
            self.config_path.setEnabled(not busy)
            if message:
                self.status.setText(message)
            elif busy:
                self.status.setText("در حال بررسی آرایش‌های کاندید و حل پخش بار…")

        def show_result(self, result):
            self._result = result
            self.report.setMarkdown(result.markdown)
            self.status.setText(
                f"وضعیت: {result.status} · حالت‌های جست‌وجو: "
                f"{result.search_state_count:,} · "
                f"طرح‌های مجاز: {sum(result.feasible_plan_count_by_type.values()):,} · "
                f"طرح‌های ردشده: {sum(result.rejected_plan_count_by_type.values()):,}")
            self.save_button.setEnabled(True)

        def _save_report(self):
            if self._result is None:
                return
            folder = QFileDialog.getExistingDirectory(
                self, "ذخیره گزارش جایابی سطح ۲")
            if not folder:
                return
            import json
            out = Path(folder)
            (out / "level2_placement_report.md").write_text(
                self._result.markdown, encoding="utf-8")
            (out / "level2_placement_report.json").write_text(
                json.dumps(self._result.as_dict(), ensure_ascii=False,
                           indent=2, default=str), encoding="utf-8")
            self.status.setText(f"گزارش‌ها ذخیره شدند: {out}")

    return Level2PlacementTab(parent)
