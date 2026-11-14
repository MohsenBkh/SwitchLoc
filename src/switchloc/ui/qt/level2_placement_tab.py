# -*- coding: utf-8 -*-
"""Direct-entry UI for exhaustive Level-2 placement (no config-file upload)."""
from __future__ import annotations

import math


def make_level2_placement_tab(parent=None):  # pragma: no cover - Qt UI
    from pathlib import Path

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                                   QFileDialog, QFormLayout, QGroupBox,
                                   QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                                   QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
                                   QTextEdit, QVBoxLayout, QWidget)

    class Level2PlacementTab(QWidget):
        def __init__(self, parent_=None):
            super().__init__(parent_)
            self.on_run = None
            self.on_refresh = None
            self._result = None
            self._feeders: list[str] = []
            self._types: list[str] = []
            self._project_key = None
            root = QVBoxLayout(self)
            intro = QLabel(
                "<b>جایابی سطح ۲ مبتنی بر EENS و پخش بار</b> — اطلاعات مطالعه را "
                "مستقیماً در جدول‌ها وارد کنید. فیدرها و تایپ هادی از پروژه/GIS "
                "خوانده می‌شوند؛ R/X و Ithr از کاتالوگ types_override.xlsx خوانده می‌شوند "
                "و Ithr با تبدیل kA به A اعمال می‌شود. بار و قابلیت اطمینان را بررسی کنید؛ "
                "آمپاسیتی تایپ نیز در صورت نیاز قابل اصلاح است.")
            intro.setWordWrap(True)
            root.addWidget(intro)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            panel = QWidget()
            form = QVBoxLayout(panel)
            scroll.setWidget(panel)
            root.addWidget(scroll, 2)

            search_box = QGroupBox("فضای جست‌وجو")
            search = QFormLayout(search_box)
            self.no_budget = self._spin(0, 1000, 0)
            self.max_states = self._spin(1, 100_000_000, 100_000)
            self.candidate_mode = QComboBox()
            self.candidate_mode.addItem("فقط نقاط بار (پیشنهادی)", "load_points")
            self.candidate_mode.addItem("همهٔ گره‌ها (جست‌وجوی بزرگ)", "all_nodes")
            search.addRow("تعداد کلیدهای NO برای بررسی:", self.no_budget)
            search.addRow("حداکثر حالت‌های شمارش کامل:", self.max_states)
            search.addRow("مجموعهٔ کاندید نصب NC:", self.candidate_mode)
            types_row = QHBoxLayout()
            self.type_checks = {}
            for code, label in (("recloser", "ریکلوزر"),
                                ("sectionalizer", "سکشنالایزر"),
                                ("disconnector", "سکسیونر")):
                check = QCheckBox(label)
                check.setChecked(True)
                self.type_checks[code] = check
                types_row.addWidget(check)
            types_row.addStretch(1)
            search.addRow("انواع کلید:", types_row)
            form.addWidget(search_box)

            feeders_box = QGroupBox(
                "ورودی به‌ازای فیدر — NC، بار P/Q، قابلیت اطمینان و ظرفیت پشتیبان")
            feeders_layout = QVBoxLayout(feeders_box)
            note = QLabel(
                "بودجهٔ NC صفر مجاز است. P/Q را بر حسب kW/kvar وارد کنید؛ "
                "اگر مدل بار معتبر در پروژه ذخیره شده، گزینهٔ استفاده از مدل پروژه را بزنید. "
                "خانه‌های λ و زمان تعمیر را خالی بگذارید تا از سوابق خاموشی پروژه خوانده شوند؛ "
                "در نبود داده، مقدار هر دو را صریح وارد کنید.")
            note.setWordWrap(True)
            feeders_layout.addWidget(note)
            self.use_project_load = QCheckBox("استفاده از مدل بار ذخیره‌شده در پروژه به‌جای P/Q این جدول")
            self.use_project_load.setChecked(True)
            self.use_project_load.toggled.connect(self._toggle_load_cells)
            feeders_layout.addWidget(self.use_project_load)
            self.feeder_table = QTableWidget(0, 8)
            self.feeder_table.setHorizontalHeaderLabels([
                "فیدر", "بودجه NC", "P بار (kW)", "Q بار (kvar)",
                "λ خرابی/سال", "تعمیر (دقیقه)", "λ گذرا/سال", "پشتیبان (kW)"])
            self.feeder_table.horizontalHeader().setStretchLastSection(True)
            self.feeder_table.setMinimumHeight(180)
            feeders_layout.addWidget(self.feeder_table)
            form.addWidget(feeders_box)

            flow_box = QGroupBox("قیود پخش بار متعادل")
            flow = QFormLayout(flow_box)
            self.base_kv = QLineEdit()
            self.base_kv.setPlaceholderText("ولتاژ نامی واقعی فیدر بر حسب kV")
            self.source_pu = self._double(0.01, 2, 1.0, 4)
            self.vmin = self._double(0.01, 2, 0.95, 4)
            self.vmax = self._double(0.01, 2, 1.05, 4)
            self.transformer_limit = self._double(1, 1000, 100.0, 1)
            self.power_factor = self._double(0.01, 1, 0.95, 3)
            flow.addRow("ولتاژ مبنا (kV):", self.base_kv)
            flow.addRow("ولتاژ منبع (pu):", self.source_pu)
            flow.addRow("حد پایین ولتاژ (pu):", self.vmin)
            flow.addRow("حد بالای ولتاژ (pu):", self.vmax)
            flow.addRow("حد بارگیری ترانس (%):", self.transformer_limit)
            flow.addRow("ضریب توان برای Q ناموجود:", self.power_factor)
            self.ampacity_table = QTableWidget(0, 2)
            self.ampacity_table.setHorizontalHeaderLabels(["تایپ هادی از GIS / کاتالوگ", "حد جریان Ithr (A؛ قابل اصلاح)"])
            self.ampacity_table.horizontalHeader().setStretchLastSection(True)
            self.ampacity_table.setMinimumHeight(100)
            flow.addRow("آمپاسیتی هادی‌ها:", self.ampacity_table)
            form.addWidget(flow_box)

            reliability_box = QGroupBox("مدل بازیابی EENS")
            reliability = QFormLayout(reliability_box)
            self.restoration_model = QComboBox()
            self.restoration_model.addItem("یکنواخت (uniform)", "uniform")
            self.restoration_model.addItem("جهت‌دار (directional)", "directional")
            self.repair_engine = self._double(0, 100_000, 50.0, 1)
            self.restore_time = self._double(0, 100_000, 30.0, 1)
            self.transient_duration = self._double(0, 100_000, 3.0, 1)
            self.min_candidate_depth = self._spin(0, 100_000, 3)
            self.max_downstream_ratio = self._double(0.01, 1.0, 0.80, 3)
            self.transient_interruption = self._double(0, 100_000, 1.0, 2)
            self.reclose_time = self._double(0, 100_000, 0.25, 2)
            self.reclose_success = self._double(0, 1, 0.70, 3)
            self.manual_restore = self._double(0, 100_000, 30.0, 1)
            self.use_existing_switches = QCheckBox("در نظر گرفتن کلیدهای موجود در مدل EENS")
            self.use_existing_switches.setChecked(True)
            self.exclude_existing = QCheckBox("کاندید نکردن گره‌های دارای کلید")
            self.exclude_existing.setChecked(True)
            self.exclude_transformer_nodes = QCheckBox("مستثنا کردن گره‌های ترمینال ترانس از کاندیدها")
            reliability.addRow("قاعدهٔ بازیابی:", self.restoration_model)
            reliability.addRow("زمان تعمیر پیش‌فرض موتور (دقیقه):", self.repair_engine)
            reliability.addRow("زمان بازیابی بار سالم (دقیقه):", self.restore_time)
            reliability.addRow("مرز خطای گذرا (دقیقه):", self.transient_duration)
            reliability.addRow("کمترین عمق محل کاندید:", self.min_candidate_depth)
            reliability.addRow("حداکثر سهم بار پایین‌دست:", self.max_downstream_ratio)
            reliability.addRow("مدت وقفهٔ خطای گذرا (دقیقه):", self.transient_interruption)
            reliability.addRow("زمان وصل مجدد (دقیقه):", self.reclose_time)
            reliability.addRow("احتمال موفقیت وصل مجدد:", self.reclose_success)
            reliability.addRow("زمان بازیابی دستی (دقیقه):", self.manual_restore)
            reliability.addRow(self.use_existing_switches)
            reliability.addRow(self.exclude_existing)
            reliability.addRow(self.exclude_transformer_nodes)
            form.addWidget(reliability_box)
            form.addStretch(1)

            controls = QHBoxLayout()
            self.run_button = QPushButton("اجرای جایابی سطح ۲")
            self.run_button.clicked.connect(self._run)
            self.save_button = QPushButton("ذخیره گزارش…")
            self.save_button.setEnabled(False)
            self.save_button.clicked.connect(self._save_report)
            controls.addWidget(self.run_button)
            controls.addWidget(self.save_button)
            controls.addStretch(1)
            root.addLayout(controls)
            self.status = QLabel("آماده — ابتدا پروژهٔ GIS را باز کنید و ورودی‌های مهندسی لازم را بررسی کنید.")
            self.status.setWordWrap(True)
            root.addWidget(self.status)
            self.report = QTextEdit()
            self.report.setReadOnly(True)
            self.report.setPlaceholderText("گزارش جایابی سطح دوم پس از اجرا اینجا نمایش داده می‌شود.")
            root.addWidget(self.report, 1)

        @staticmethod
        def _spin(minimum, maximum, value):
            widget = QSpinBox()
            widget.setRange(minimum, maximum)
            widget.setValue(value)
            return widget

        @staticmethod
        def _double(minimum, maximum, value, decimals):
            widget = QDoubleSpinBox()
            widget.setRange(minimum, maximum)
            widget.setDecimals(decimals)
            widget.setValue(value)
            return widget

        def showEvent(self, event):
            super().showEvent(event)
            if self.on_refresh is not None:
                self.on_refresh()

        def set_project_data(self, feeders, line_types=(), load_model=None,
                             saved_settings=None, project_key=None,
                             line_ampacities=None):
            """Refresh dynamic inputs from the currently open GIS project."""
            feeders = sorted({str(x) for x in feeders if str(x)})
            project_changed = project_key != self._project_key
            if project_changed:
                for row in range(self.feeder_table.rowCount()):
                    for col in range(1, self.feeder_table.columnCount()):
                        if self.feeder_table.item(row, col):
                            self.feeder_table.item(row, col).setText(
                                "0" if col == 1 else "")
                for row in range(self.ampacity_table.rowCount()):
                    if self.ampacity_table.item(row, 1):
                        self.ampacity_table.item(row, 1).setText("")
            changed = (feeders != self._feeders or project_changed)
            if feeders != self._feeders:
                self._feeders = feeders
                self.feeder_table.setRowCount(len(feeders))
                for row, feeder in enumerate(feeders):
                    item = QTableWidgetItem(feeder)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.feeder_table.setItem(row, 0, item)
                    self.feeder_table.setItem(row, 1, QTableWidgetItem("0"))
                    for col in range(2, 8):
                        self.feeder_table.setItem(row, col, QTableWidgetItem(""))
                self._toggle_load_cells(self.use_project_load.isChecked())
            types = sorted({str(x) for x in line_types if str(x)})
            if types != self._types:
                changed = True
                old = self._read_ampacities()
                self._types = types
                self.ampacity_table.setRowCount(len(types))
                for row, type_name in enumerate(types):
                    name = QTableWidgetItem(type_name)
                    name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.ampacity_table.setItem(row, 0, name)
                    ampacity = old.get(type_name)
                    if not ampacity and line_ampacities:
                        ampacity = str(line_ampacities.get(type_name, "") or "")
                    self.ampacity_table.setItem(
                        row, 1, QTableWidgetItem(ampacity or ""))
            if changed and saved_settings:
                self._apply_settings(saved_settings)
            elif changed:
                self.use_project_load.setChecked(bool(load_model))
            self._project_key = project_key
            if not feeders:
                self.status.setText("فیدری از پروژهٔ باز تشخیص داده نشد؛ ابتدا GIS را وارد و توپولوژی را بسازید.")

        def _toggle_load_cells(self, use_project):
            for row in range(self.feeder_table.rowCount()):
                for col in (2, 3):
                    item = self.feeder_table.item(row, col)
                    if item is not None:
                        item.setFlags((item.flags() | Qt.ItemFlag.ItemIsEditable)
                                      if not use_project else
                                      (item.flags() & ~Qt.ItemFlag.ItemIsEditable))

        def _read_ampacities(self):
            result = {}
            for row in range(self.ampacity_table.rowCount()):
                name, value = self.ampacity_table.item(row, 0), self.ampacity_table.item(row, 1)
                if name and value:
                    result[name.text()] = value.text().strip()
            return result

        @staticmethod
        def _optional_number(text, label):
            text = str(text or "").strip()
            if not text:
                return None
            try:
                value = float(text.replace(",", "."))
            except ValueError as exc:
                raise ValueError(f"مقدار «{label}» باید عددی باشد.") from exc
            if not math.isfinite(value):
                raise ValueError(f"مقدار «{label}» باید متناهی باشد.")
            return value

        def settings_data(self):
            feeders = {}
            pqs, rates, repairs, transients, backup = {}, {}, {}, {}, {}
            for row in range(self.feeder_table.rowCount()):
                feeder = self.feeder_table.item(row, 0).text()
                try:
                    budget = int(self.feeder_table.item(row, 1).text() or 0)
                except ValueError as exc:
                    raise ValueError(f"بودجهٔ NC فیدر {feeder} باید عدد صحیح باشد.") from exc
                if budget < 0:
                    raise ValueError(f"بودجهٔ NC فیدر {feeder} نمی‌تواند منفی باشد.")
                feeders[feeder] = budget
                cells = [self.feeder_table.item(row, col).text()
                         for col in range(2, 8)]
                p, q, rate, repair, transient, backup_kw = [
                    self._optional_number(value, f"{feeder}, ستون {col}")
                    for col, value in enumerate(cells, start=2)]
                if not self.use_project_load.isChecked():
                    if p is None or q is None or p <= 0 or q < 0:
                        raise ValueError(f"P/Q معتبر برای فیدر {feeder} وارد کنید (P>0، Q≥0).")
                    pqs[feeder] = {"p_kw": p, "q_kvar": q}
                for value, mapping, label in (
                        (rate, rates, "λ"), (repair, repairs, "زمان تعمیر"),
                        (transient, transients, "λ گذرا"), (backup_kw, backup, "پشتیبان")):
                    if value is not None:
                        if value < 0 or (label == "زمان تعمیر" and value <= 0):
                            raise ValueError(f"{label} فیدر {feeder} نامعتبر است.")
                        mapping[feeder] = value
                if (rate is None) != (repair is None):
                    raise ValueError(f"برای فیدر {feeder}، λ و زمان تعمیر را هر دو وارد کنید یا هر دو را خالی بگذارید.")

            ampacities = {}
            for row in range(self.ampacity_table.rowCount()):
                name = self.ampacity_table.item(row, 0).text()
                raw = self.ampacity_table.item(row, 1).text().strip()
                if raw:
                    value = self._optional_number(raw, f"آمپاسیتی {name}")
                    if value is None or value <= 0:
                        raise ValueError(f"آمپاسیتی تایپ {name} باید آمپر مثبت باشد.")
                    ampacities[name] = value
            base_kv = self._optional_number(self.base_kv.text(), "ولتاژ مبنا")
            if base_kv is None or base_kv <= 0:
                raise ValueError("ولتاژ نامی واقعی شبکه را بر حسب kV وارد کنید.")
            chosen_types = [key for key, check in self.type_checks.items() if check.isChecked()]
            if not chosen_types:
                raise ValueError("حداقل یک نوع کلید انتخاب کنید.")
            if self.no_budget.value() == 0 and not any(feeders.values()):
                raise ValueError("حداقل یک بودجهٔ NC یا NO بزرگ‌تر از صفر وارد کنید.")
            load_model = ({"level": "scaled", "feeder_pq": pqs}
                          if not self.use_project_load.isChecked() else {})
            return {
                "level2": {"nc_budget_by_feeder": feeders,
                           "no_budget": self.no_budget.value(),
                           "max_search_states": self.max_states.value(),
                           "candidate_mode": self.candidate_mode.currentData(),
                           "switch_types": chosen_types},
                "load_model": load_model,
                "power_flow": {
                    "base_voltage_kv": base_kv,
                    "source_voltage_pu": self.source_pu.value(),
                    "voltage_min_pu": self.vmin.value(),
                    "voltage_max_pu": self.vmax.value(),
                    "transformer_loading_limit_pct": self.transformer_limit.value(),
                    "assumed_power_factor": self.power_factor.value(),
                    "type_ampacity_a": ampacities},
                "reliability": {
                    "failure_rates": rates,
                    "repair_times_min": repairs,
                    "transient_rates": transients,
                    "backup_kw": backup,
                    "transient_max_duration_min": self.transient_duration.value(),
                    "engine": {"restoration_model": self.restoration_model.currentData(),
                               "repair_time_min": self.repair_engine.value(),
                               "restoration_time_min": self.restore_time.value(),
                               "min_candidate_depth": self.min_candidate_depth.value(),
                               "max_downstream_load_ratio": self.max_downstream_ratio.value(),
                               "transient_interruption_min": self.transient_interruption.value(),
                               "reclose_time_min": self.reclose_time.value(),
                               "reclose_success_probability": self.reclose_success.value(),
                               "manual_restoration_time_min": self.manual_restore.value(),
                               "use_existing_switches": self.use_existing_switches.isChecked(),
                               "exclude_nodes_with_switch": self.exclude_existing.isChecked(),
                               "exclude_transformer_terminal_nodes":
                                   self.exclude_transformer_nodes.isChecked()}},
                "persist": True,
            }

        def _apply_settings(self, data):
            level = data.get("level2", {})
            by_feeder = level.get("nc_budget_by_feeder", {})
            for row in range(self.feeder_table.rowCount()):
                key = self.feeder_table.item(row, 0).text()
                if key in by_feeder:
                    self.feeder_table.item(row, 1).setText(str(by_feeder[key]))
            self.no_budget.setValue(int(level.get("no_budget", self.no_budget.value())))
            self.max_states.setValue(int(level.get("max_search_states", self.max_states.value())))
            mode = level.get("candidate_mode", "load_points")
            ix = self.candidate_mode.findData(mode)
            if ix >= 0:
                self.candidate_mode.setCurrentIndex(ix)
            for code, check in self.type_checks.items():
                check.setChecked(code in level.get("switch_types", self.type_checks.keys()))
            load_data = data.get("load_model", {}) or {}
            scaled = load_data.get("level") == "scaled"
            self.use_project_load.setChecked(not scaled)
            pqs = load_data.get("feeder_pq", {})
            reliability = data.get("reliability", {}) or {}
            maps = (pqs, reliability.get("failure_rates", {}),
                    reliability.get("repair_times_min", {}),
                    reliability.get("transient_rates", {}),
                    reliability.get("backup_kw", {}))
            for row in range(self.feeder_table.rowCount()):
                key = self.feeder_table.item(row, 0).text()
                values = [pqs.get(key, {}).get("p_kw", ""),
                          pqs.get(key, {}).get("q_kvar", ""),
                          maps[1].get(key, ""), maps[2].get(key, ""),
                          maps[3].get(key, ""), maps[4].get(key, "")]
                for col, value in enumerate(values, start=2):
                    self.feeder_table.item(row, col).setText(str(value))
            pf = data.get("power_flow", {}) or {}
            if "base_voltage_kv" in pf:
                self.base_kv.setText(str(pf["base_voltage_kv"]))
            for key, widget in (("source_voltage_pu", self.source_pu),
                                ("voltage_min_pu", self.vmin),
                                ("voltage_max_pu", self.vmax),
                                ("transformer_loading_limit_pct", self.transformer_limit),
                                ("assumed_power_factor", self.power_factor)):
                if key in pf:
                    widget.setValue(float(pf[key]))
            for row in range(self.ampacity_table.rowCount()):
                name = self.ampacity_table.item(row, 0).text()
                self.ampacity_table.item(row, 1).setText(
                    str((pf.get("type_ampacity_a", {}) or {}).get(name, "")))
            engine = reliability.get("engine", {}) or {}
            self.repair_engine.setValue(float(engine.get("repair_time_min", self.repair_engine.value())))
            self.restore_time.setValue(float(engine.get("restoration_time_min", self.restore_time.value())))
            self.min_candidate_depth.setValue(int(engine.get(
                "min_candidate_depth", self.min_candidate_depth.value())))
            self.max_downstream_ratio.setValue(float(engine.get(
                "max_downstream_load_ratio", self.max_downstream_ratio.value())))
            self.transient_interruption.setValue(float(engine.get(
                "transient_interruption_min", self.transient_interruption.value())))
            self.reclose_time.setValue(float(engine.get(
                "reclose_time_min", self.reclose_time.value())))
            self.reclose_success.setValue(float(engine.get(
                "reclose_success_probability", self.reclose_success.value())))
            self.manual_restore.setValue(float(engine.get(
                "manual_restoration_time_min", self.manual_restore.value())))
            self.use_existing_switches.setChecked(bool(engine.get(
                "use_existing_switches", self.use_existing_switches.isChecked())))
            self.exclude_existing.setChecked(bool(engine.get(
                "exclude_nodes_with_switch", self.exclude_existing.isChecked())))
            self.exclude_transformer_nodes.setChecked(bool(engine.get(
                "exclude_transformer_terminal_nodes",
                self.exclude_transformer_nodes.isChecked())))
            self.transient_duration.setValue(float(reliability.get(
                "transient_max_duration_min", self.transient_duration.value())))
            ix = self.restoration_model.findData(engine.get("restoration_model", "uniform"))
            if ix >= 0:
                self.restoration_model.setCurrentIndex(ix)

        def _run(self):
            if self.on_refresh is not None:
                self.on_refresh()
            if self.on_run is None:
                QMessageBox.warning(self, "پروژه آماده نیست", "ابتدا یک پروژهٔ GIS باز کنید.")
                return
            try:
                data = self.settings_data()
            except (ValueError, AttributeError) as exc:
                QMessageBox.warning(self, "ورودی جایابی سطح ۲", str(exc))
                return
            self.on_run(data)

        def set_busy(self, busy: bool, message: str = ""):
            self.run_button.setEnabled(not busy)
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
