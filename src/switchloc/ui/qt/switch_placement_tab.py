# -*- coding: utf-8 -*-
"""تب «روش جایابی بهینهٔ کلید و کاهش EENS».

بخش بهینه‌سازی SwitchLoc — پیش‌تر «بهینه‌سازی سکشنالایزر» نام داشت و اکنون
هر سه نوع کلید (ریکلوزر، سکشنالایزر، سکسیونر) را جایابی می‌کند.

Layout (با مرزهای قابل جابه‌جایی — درخواست کاربر):

  ┌ تنظیمات موتور (نوع کلید، روش EENS، پارامترها) ────────────────────┐
  │  … قابل تغییر اندازه با درگ کردن مرز …                            │
  ├ خلاصهٔ هر فیدر (جدول) ─────────────────────────────────────────────┤
  ├ کاندیدها ─┬ گزارش Markdown ────────────────────────────────────────┤
  └───────────┴───────────────────────────────────────────────────────┘

* **نوع کلید** — ریکلوزر / سکشنالایزر / سکسیونر.
* **روش EENS** — به ترتیب: دایرکشنال (λ و r واقعی)، یکنواخت (λ و r واقعی)،
  دستی. در دو روش واقعی، λ و r خودکار از ماتریس λ/r پروژه می‌آید و
  ورودی‌های دستی غیرفعال می‌شوند (فقط قابل مشاهده).

منطق محاسباتی در ``reliability/switch_placement.py`` و سرویس در
``application/switch_placement_service.py`` است؛ این فایل فقط نمایش است.
"""
from __future__ import annotations


def make_sectionalizer_tab(parent=None):     # pragma: no cover (Qt)
    """ساخت تب «روش جایابی بهینهٔ کلید» (Qt) و برگرداندن کنترلر آن."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                                   QFormLayout, QGroupBox, QHBoxLayout,
                                   QLabel, QPushButton, QSpinBox,
                                   QSplitter, QTableWidget, QTextEdit,
                                   QVBoxLayout, QWidget)

    from ...application.switch_placement_service import (EENS_METHOD_FA,
                                                         EENS_METHOD_ORDER)
    from ...reliability.switch_placement import (SWITCH_DISCONNECTOR,
                                                 SWITCH_RECLOSER,
                                                 SWITCH_TYPES,
                                                 SWITCH_TYPE_FA)
    from .widgets import fill_table, make_explain_label

    SUMMARY_HEADERS = ["فیدر", "طول (km)", "بار (kW)", "λ (۱/سال)",
                       "r (دقیقه)", "منبع λ", "قطعه موجود", "کاندید",
                       "EENS پایه (MWh/سال)", "کلید پیشنهادی",
                       "EENS نهایی (MWh/سال)", "کاهش (٪)"]
    DETAIL_HEADERS = ["فیدر", "رتبه", "محل پیشنهادی", "زون", "عمق",
                      "بار پایین‌دست (kW)", "سهم بار", "طول پایین‌دست (km)"]

    class SwitchPlacementTab(QWidget):
        """کنترلر تب — سیم‌کشی با main_window از طریق callback‌ها."""

        def __init__(self, parent_=None):
            super().__init__(parent_)
            self.on_run = None           # callback(settings dict)
            self.on_show_map = None      # callback(selected node ids)
            self.on_settings_changed = None
            self._result = None
            self._selected_nodes: list[str] = []

            root = QVBoxLayout(self)
            root.setContentsMargins(6, 6, 6, 6)
            head = QLabel(
                "<b>روش جایابی بهینهٔ کلید و کاهش EENS</b> — جایابی "
                "ریکلوزر، سکشنالایزر و سکسیونر روی گراف و مدل بار همین "
                "پروژه (تخصیص λ متناسب طول، زمان تعمیر/بازیابی، جست‌وجوی "
                "حریصانه).")
            head.setWordWrap(True)
            root.addWidget(head)

            # ---- مرزهای قابل جابه‌جایی: تنظیمات | خلاصه | جزئیات ----------
            self.main_split = QSplitter(Qt.Orientation.Vertical)
            self.main_split.setChildrenCollapsible(True)
            root.addWidget(self.main_split, 1)

            # =================== ۱) تنظیمات موتور =======================
            top = QWidget()
            tv = QVBoxLayout(top)
            tv.setContentsMargins(0, 0, 0, 0)

            box = QGroupBox("تنظیمات موتور")
            form = QFormLayout(box)

            self.cmb_switch_type = QComboBox()
            for key in SWITCH_TYPES:
                self.cmb_switch_type.addItem(SWITCH_TYPE_FA[key], key)
            form.addRow("نوع کلید:", self.cmb_switch_type)

            self.lbl_switch_note = make_explain_label("")
            form.addRow("", self.lbl_switch_note)

            self.cmb_method = QComboBox()
            for key in EENS_METHOD_ORDER:       # دایرکشنال، یکنواخت، دستی
                self.cmb_method.addItem(EENS_METHOD_FA[key], key)
            self.cmb_method.setCurrentIndex(
                max(0, self.cmb_method.findData("uniform")))
            form.addRow("روش محاسبهٔ EENS:", self.cmb_method)

            self.sp_lambda = QDoubleSpinBox()
            self.sp_lambda.setRange(0.0, 500.0)
            self.sp_lambda.setDecimals(3)
            self.sp_lambda.setValue(30.0)
            form.addRow("λ دستی (خرابی/سال):", self.sp_lambda)

            self.sp_repair = QDoubleSpinBox()
            self.sp_repair.setRange(0.0, 1440.0)
            self.sp_repair.setDecimals(1)
            self.sp_repair.setValue(50.0)
            form.addRow("r دستی — زمان تعمیر (دقیقه):", self.sp_repair)

            self.sp_restore = QDoubleSpinBox()
            self.sp_restore.setRange(0.0, 1440.0)
            self.sp_restore.setDecimals(1)
            self.sp_restore.setValue(20.0)
            form.addRow("زمان بازیابی بار سالم (دقیقه):", self.sp_restore)

            self.sp_manual_restore = QDoubleSpinBox()
            self.sp_manual_restore.setRange(0.0, 1440.0)
            self.sp_manual_restore.setDecimals(1)
            self.sp_manual_restore.setValue(30.0)
            form.addRow("بازیابی دستی سکسیونر (دقیقه):",
                        self.sp_manual_restore)

            # --- پارامترهای خطای گذرا (فقط ریکلوزر) ---
            self.grp_transient = QGroupBox("خطای گذرا (ویژهٔ ریکلوزر)")
            tform = QFormLayout(self.grp_transient)
            self.sp_transient_min = QDoubleSpinBox()
            self.sp_transient_min.setRange(0.0, 60.0)
            self.sp_transient_min.setDecimals(2)
            self.sp_transient_min.setValue(3.0)
            tform.addRow("حداکثر مدت خطای گذرا (دقیقه):",
                         self.sp_transient_min)
            self.sp_transient_time = QDoubleSpinBox()
            self.sp_transient_time.setRange(0.0, 120.0)
            self.sp_transient_time.setDecimals(2)
            self.sp_transient_time.setValue(1.0)
            tform.addRow("وقفهٔ کامل بدون ریکلوزر (دقیقه):",
                         self.sp_transient_time)
            self.sp_reclose_time = QDoubleSpinBox()
            self.sp_reclose_time.setRange(0.0, 60.0)
            self.sp_reclose_time.setDecimals(2)
            self.sp_reclose_time.setValue(0.25)
            tform.addRow("زمان وصل مجدد (دقیقه):", self.sp_reclose_time)
            self.sp_reclose_p = QDoubleSpinBox()
            self.sp_reclose_p.setRange(0.0, 100.0)
            self.sp_reclose_p.setDecimals(0)
            self.sp_reclose_p.setValue(70.0)
            tform.addRow("احتمال موفقیت وصل مجدد (٪):", self.sp_reclose_p)
            tv.addWidget(self.grp_transient)
            self.grp_transient.setVisible(False)

            self.sp_max = QSpinBox()
            self.sp_max.setRange(0, 20)
            self.sp_max.setValue(3)
            form.addRow("حداکثر کلید هر فیدر:", self.sp_max)

            self.sp_depth = QSpinBox()
            self.sp_depth.setRange(0, 100000)
            self.sp_depth.setValue(3)
            self.sp_depth.setToolTip(
                "کمترین فاصله (تعداد یال) از سر فیدر؛ ۰ = بدون محدودیت.")
            form.addRow("عمق کمینهٔ کاندید:", self.sp_depth)

            self.sp_ratio = QDoubleSpinBox()
            self.sp_ratio.setRange(1.0, 100.0)
            self.sp_ratio.setDecimals(0)
            self.sp_ratio.setValue(80.0)
            self.sp_ratio.setToolTip(
                "کاندیدی که بیش از این درصد از بار فیدر را در پایین‌دست "
                "دارد پیشنهاد نمی‌شود (پرهیز از بی‌برق‌کردن عمدهٔ فیدر).")
            form.addRow("سقف سهم بار پایین‌دست (٪):", self.sp_ratio)

            self.sp_backup = QDoubleSpinBox()
            self.sp_backup.setRange(0.0, 1e7)
            self.sp_backup.setDecimals(0)
            self.sp_backup.setValue(0.0)
            self.sp_backup.setSpecialValueText("نامحدود")
            self.sp_backup.setToolTip(
                "ظرفیت پشتیبان هر فیدر (kW)؛ صفر = نامحدود (فرض روش مرجع).")
            form.addRow("ظرفیت پشتیبان (kW):", self.sp_backup)

            self.chk_existing = QCheckBox(
                "کلیدهای موجود به‌عنوان قطعه‌بندی مبنا لحاظ شوند")
            self.chk_existing.setChecked(True)
            form.addRow("", self.chk_existing)
            self.chk_show_map = QCheckBox(
                "کلیدهای پیشنهادی روی نقشه نمایش داده شوند")
            self.chk_show_map.setChecked(True)
            form.addRow("", self.chk_show_map)

            tv.addWidget(box)
            tv.addWidget(make_explain_label(
                "در روش‌های «دایرکشنال» و «یکنواخت»، λ و r به‌صورت خودکار از "
                "ماتریس λ/r واقعی خاموشی‌های پروژه خوانده می‌شوند؛ ورودی‌های "
                "دستی غیرفعال می‌شوند. هیچ کلیدی در شبکه تغییر نمی‌کند؛ "
                "خروجی فقط پیشنهاد است."))

            btns = QHBoxLayout()
            self.btn_run = QPushButton("اجرای جایابی")
            self.btn_run.clicked.connect(self._run)
            self.btn_map = QPushButton("نمایش روی نقشه")
            self.btn_map.setEnabled(False)
            self.btn_map.clicked.connect(self._show_map)
            btns.addWidget(self.btn_run)
            btns.addWidget(self.btn_map)
            btns.addStretch(1)
            tv.addLayout(btns)

            self.status = QLabel(
                "آماده — ابتدا پروژه را باز و توپولوژی را اجرا کنید.")
            self.status.setWordWrap(True)
            self.status.setStyleSheet("color:#37474f;")
            tv.addWidget(self.status)

            # =================== ۲) خلاصهٔ فیدرها =======================
            mid = QWidget()
            mv = QVBoxLayout(mid)
            mv.setContentsMargins(0, 0, 0, 0)
            mv.addWidget(QLabel("خلاصهٔ هر فیدر (EENS پایه → نهایی):"))
            self.summary_table = QTableWidget(0, len(SUMMARY_HEADERS))
            self.summary_table.setAlternatingRowColors(True)
            self.summary_table.setWordWrap(True)
            mv.addWidget(self.summary_table, 1)

            # =================== ۳) جزئیات + گزارش ======================
            bottom = QSplitter(Qt.Orientation.Horizontal)
            left = QWidget()
            lv = QVBoxLayout(left)
            lv.setContentsMargins(0, 0, 0, 0)
            lv.addWidget(QLabel(
                "جزئیات کاندیدها (مرتب بر اساس بار پایین‌دست) — ستون «انتخاب "
                "شده» نتیجهٔ جست‌وجوی حریصانه است:"))
            self.detail_table = QTableWidget(0, len(DETAIL_HEADERS))
            self.detail_table.setAlternatingRowColors(True)
            lv.addWidget(self.detail_table, 1)

            right = QWidget()
            rv = QVBoxLayout(right)
            rv.setContentsMargins(0, 0, 0, 0)
            rv.addWidget(QLabel("گزارش کامل (Markdown):"))
            self.panel = QTextEdit()
            self.panel.setReadOnly(True)
            rv.addWidget(self.panel, 1)

            bottom.addWidget(left)
            bottom.addWidget(right)
            bottom.setSizes([620, 480])

            self.main_split.addWidget(top)
            self.main_split.addWidget(mid)
            self.main_split.addWidget(bottom)
            self.main_split.setStretchFactor(0, 0)
            self.main_split.setStretchFactor(1, 1)
            self.main_split.setStretchFactor(2, 1)
            self.main_split.setSizes([230, 260, 340])

            self._load_table_headers()

            # ---- سیگنال‌ها ----
            for w in (self.cmb_switch_type, self.cmb_method):
                w.currentIndexChanged.connect(self._on_mode_changed)
            for w in (self.sp_lambda, self.sp_repair, self.sp_restore,
                      self.sp_ratio, self.sp_transient_min,
                      self.sp_transient_time, self.sp_reclose_time,
                      self.sp_reclose_p, self.sp_manual_restore,
                      self.sp_backup):
                w.valueChanged.connect(self._notify_changed)
            for w in (self.sp_max, self.sp_depth):
                w.valueChanged.connect(self._notify_changed)
            for w in (self.chk_existing, self.chk_show_map):
                w.toggled.connect(self._notify_changed)
            self._on_mode_changed()

        # --------------------------------------------------------------
        def _load_table_headers(self) -> None:
            fill_table(self.summary_table, SUMMARY_HEADERS, [])
            fill_table(self.detail_table, DETAIL_HEADERS, [])

        # --------------------------------------------------------------
        def current_switch_type(self) -> str:
            return str(self.cmb_switch_type.currentData() or "sectionalizer")

        def current_method(self) -> str:
            return str(self.cmb_method.currentData() or "uniform")

        def _on_mode_changed(self, *_args) -> None:
            """فعال/غیرفعال‌کردن ورودی‌ها بر اساس نوع کلید و روش EENS."""
            switch_type = self.current_switch_type()
            method = self.current_method()
            manual = method == "manual"
            self.grp_transient.setVisible(switch_type == SWITCH_RECLOSER)
            self.sp_manual_restore.setEnabled(
                switch_type == SWITCH_DISCONNECTOR)
            # در روش‌های «واقعی» λ و r خودکارند → فقط نمایش (قابل مشاهده)
            for w in (self.sp_lambda, self.sp_repair):
                w.setEnabled(manual)
                w.setReadOnly(not manual)
                w.setToolTip("" if manual else
                             "خودکار از ماتریس λ/r واقعی خاموشی‌های پروژه")
            self.sp_restore.setEnabled(manual)
            self.lbl_switch_note.setText(
                make_explain_label.__module__ and "")
            self._update_note()
            self._notify_changed()

        def _update_note(self) -> None:
            from ...reliability.switch_placement import (SWITCH_TYPE_FA,
                                                         SWITCH_TYPE_NOTE_FA)
            switch_type = self.current_switch_type()
            text = (f"<i>{SWITCH_TYPE_FA[switch_type]}</i> — "
                    f"{SWITCH_TYPE_NOTE_FA[switch_type]}")
            if self.current_method() != "manual":
                text += ("<br><i>λ و r خودکار از خاموشی‌های واقعی؛ "
                         "ورودی‌های دستی غیرفعال است.</i>")
            self.lbl_switch_note.setText(text)

        def _notify_changed(self, *_args) -> None:
            if self.on_settings_changed is not None:
                self.on_settings_changed(self.settings())

        # --------------------------------------------------------------
        def settings(self) -> dict:
            """مقادیر فعلی ویجت‌ها → dict قابل ارسال به سرویس."""
            method = self.current_method()
            return {
                "switch_type": self.current_switch_type(),
                "method": method,
                "failure_rate_source":
                    "outage" if method != "manual" else "configured",
                "total_failure_rate_per_year": float(self.sp_lambda.value()),
                "repair_time_min": float(self.sp_repair.value()),
                "restoration_time_min": float(self.sp_restore.value()),
                "manual_restoration_time_min":
                    float(self.sp_manual_restore.value()),
                "transient_max_duration_min":
                    float(self.sp_transient_min.value()),
                "transient_interruption_min":
                    float(self.sp_transient_time.value()),
                "reclose_time_min": float(self.sp_reclose_time.value()),
                "reclose_success_probability":
                    float(self.sp_reclose_p.value()) / 100.0,
                "max_sectionalizers": int(self.sp_max.value()),
                "min_candidate_depth": int(self.sp_depth.value()),
                "max_downstream_load_ratio":
                    float(self.sp_ratio.value()) / 100.0,
                "backup_kw": (float(self.sp_backup.value())
                              if self.sp_backup.value() > 0 else 0.0),
                "restoration_model":
                    ("directional" if method == "directional"
                     else "uniform"),
                "use_existing_switches": bool(self.chk_existing.isChecked()),
                "show_on_map": bool(self.chk_show_map.isChecked()),
            }

        def apply_settings(self, d: dict | None) -> None:
            d = dict(d or {})
            if not d:
                return
            for key, cmb in (("switch_type", self.cmb_switch_type),
                             ("method", self.cmb_method)):
                if d.get(key):
                    ix = cmb.findData(str(d[key]))
                    if ix >= 0:
                        cmb.setCurrentIndex(ix)
            # سازگاری با تنظیمات قدیمی (restoration_model / lambda_source)
            if not d.get("method"):
                # «λ/r دستی» بر مدل بازیابی قدیمی مقدم است: اگر منبع λ/r
                # «configured» باشد، کاربر مقادیر را خودش وارد می‌کند.
                model = d.get("restoration_model")
                if d.get("failure_rate_source") == "configured":
                    ix = self.cmb_method.findData("manual")
                    if ix >= 0:
                        self.cmb_method.setCurrentIndex(ix)
                elif model in ("directional", "uniform"):
                    ix = self.cmb_method.findData(model)
                    if ix >= 0:
                        self.cmb_method.setCurrentIndex(ix)
            for key, widget in (
                    ("total_failure_rate_per_year", self.sp_lambda),
                    ("repair_time_min", self.sp_repair),
                    ("restoration_time_min", self.sp_restore),
                    ("manual_restoration_time_min", self.sp_manual_restore),
                    ("transient_max_duration_min", self.sp_transient_min),
                    ("transient_interruption_min", self.sp_transient_time),
                    ("reclose_time_min", self.sp_reclose_time),
                    ("backup_kw", self.sp_backup)):
                if d.get(key) is not None:
                    widget.setValue(float(d[key]))
            for key, widget in (("max_sectionalizers", self.sp_max),
                                ("min_candidate_depth", self.sp_depth)):
                if d.get(key) is not None:
                    widget.setValue(int(d[key]))
            if d.get("max_downstream_load_ratio") is not None:
                self.sp_ratio.setValue(
                    float(d["max_downstream_load_ratio"]) * 100.0)
            if d.get("reclose_success_probability") is not None:
                self.sp_reclose_p.setValue(
                    float(d["reclose_success_probability"]) * 100.0)
            if d.get("use_existing_switches") is not None:
                self.chk_existing.setChecked(
                    bool(d["use_existing_switches"]))
            if d.get("show_on_map") is not None:
                self.chk_show_map.setChecked(bool(d["show_on_map"]))
            self._on_mode_changed()

        # --------------------------------------------------------------
        def set_busy(self, busy: bool, text: str = "") -> None:
            self.btn_run.setEnabled(not busy)
            if text:
                self.status.setText(text)

        def _run(self) -> None:
            if self.on_run is not None:
                self.on_run(self.settings())

        def _show_map(self) -> None:
            if self.on_show_map is not None:
                self.on_show_map(list(self._selected_nodes))

        # --------------------------------------------------------------
        @staticmethod
        def _summary_row(r: dict) -> list:
            return [
                r.get("feeder_key", ""),
                f"{float(r.get('line_length_km') or 0):.2f}",
                f"{float(r.get('total_load_kw') or 0):,.1f}",
                f"{float(r.get('failure_rate_per_year') or 0):.2f}",
                (f"{float(r['repair_time_min']):.1f}"
                 if r.get("repair_time_min") is not None else "—"),
                str(r.get("failure_rate_source", "")),
                str(r.get("existing_sections", "")),
                str(r.get("candidate_count", "")),
                f"{float(r.get('baseline_eens_mwh') or 0):,.4f}",
                str(r.get("selected_count", "")),
                f"{float(r.get('best_eens_mwh') or 0):,.4f}",
                f"{float(r.get('improvement_percent') or 0):.2f}",
            ]

        @staticmethod
        def _detail_row(feeder_key: str, c: dict, selected: bool) -> list:
            return [
                feeder_key, str(c.get("rank", "")),
                ("✔ " if selected else "") + str(c.get("label", "")),
                str(c.get("zone_id", ""))[:8], str(c.get("depth", "")),
                f"{float(c.get('downstream_load_kw') or 0):,.1f}",
                f"{float(c.get('downstream_ratio') or 0) * 100:.1f}%",
                f"{float(c.get('downstream_length_km') or 0):.2f}",
            ]

        # --------------------------------------------------------------
        def show_result(self, result, *, show_on_map: bool = True) -> None:
            """نمایش نتیجهٔ سرویس (SwitchPlacementAppResult)."""
            self._result = result
            study = result.study
            rows = [self._summary_row(r) for r in study.summary_rows()]
            fill_table(self.summary_table, SUMMARY_HEADERS, rows)

            det = []
            self._selected_nodes = []
            for r in study.candidate_rows():
                det.append(self._detail_row(r["feeder_key"], r,
                                            bool(r["selected"])))
            for f in study.feeders:
                if f.best:
                    self._selected_nodes.extend(
                        c.node for c in f.best.selected)
            fill_table(self.detail_table, DETAIL_HEADERS, det)
            self.panel.setPlainText(result.markdown)
            self.btn_map.setEnabled(bool(self._selected_nodes) and show_on_map)
            st = study.settings or {}
            self.status.setText(
                f"پایان — {st.get('switch_type_fa', 'کلید')} · "
                f"{str(st.get('method_fa', '')).split(' — ')[0]} · "
                f"EENS پایه {study.baseline_eens_kwh / 1000.0:,.2f} MWh/سال → "
                f"{study.best_eens_kwh / 1000.0:,.2f} MWh/سال "
                f"(کاهش {study.improvement_percent:.2f}% با "
                f"{study.total_selected} کلید).")

        # --------------------------------------------------------------
        def show_persisted(self, payload: dict | None) -> None:
            """نمایش نتیجهٔ ذخیره‌شده در پروژه (پس از بازکردن پروژه)."""
            data = dict(payload or {})
            study = dict(data.get("study") or {})
            rows = [self._summary_row(r)
                    for r in (study.get("summary_rows") or [])]
            fill_table(self.summary_table, SUMMARY_HEADERS, rows)

            det = []
            self._selected_nodes = []
            for f in study.get("feeders") or []:
                chosen = {c.get("node") for c in
                          ((f.get("best") or {}).get("selected") or [])}
                for c in f.get("candidates") or []:
                    det.append(self._detail_row(
                        str(f.get("feeder_key", "")), c,
                        c.get("node") in chosen))
                self._selected_nodes.extend(
                    str(c.get("node")) for c in
                    ((f.get("best") or {}).get("selected") or []))
            fill_table(self.detail_table, DETAIL_HEADERS, det)
            self.panel.setPlainText(
                str(data.get("markdown") or study.get("markdown") or
                    "نتیجهٔ ذخیره‌شدهٔ این پروژه یافت شد."))
            self.btn_map.setEnabled(bool(self._selected_nodes))
            self.status.setText(
                "نتیجهٔ ذخیره‌شدهٔ پروژه بارگذاری شد؛ برای اجرای جدید "
                "تنظیمات را تأیید و «اجرای جایابی» را بزنید.")

        def selected_nodes(self) -> list:
            return list(self._selected_nodes)

        def selected_zone_map_nodes(self, study) -> list:
            """[(x, y), …] گره‌های پیشنهادی برای نمایش روی نقشه."""
            out = []
            for f in getattr(study, "feeders", []) or []:
                if not f.best:
                    continue
                for c in f.best.selected:
                    if c.coord is not None:
                        out.append({"id": c.node, "x": float(c.coord[0]),
                                    "y": float(c.coord[1]),
                                    "label": c.label})
            return out

    return SwitchPlacementTab(parent)


#: نام قدیمی (سازگاری)
make_switch_placement_tab = make_sectionalizer_tab
