# -*- coding: utf-8 -*-
"""تب «بهینه‌سازی سکشنالایزر و کاهش EENS».

بخش جدید SwitchLoc (درخواست کاربر): روش کد مرجع PowerFactory به‌صورت یک
موتور محاسباتی داخل برنامه — نه انتقال اسکریپت.

Layout (دو ستون، مثل بقیهٔ تب‌های مطالعه):

  * ستون چپ  — تنظیمات موتور (منبع λ، زمان تعمیر/بازیابی، سقف تعداد،
    عمق کمینه، سقف سهم بار پایین‌دست، مدل بازیابی) + دکمهٔ اجرا +
    «نمایش روی نقشه» + جدول خلاصهٔ هر فیدر (EENS پایه/نهایی، کاهش ٪).
  * ستون راست — جدول جزئیات کاندیدها (رتبه، محل، زون، عمق، بار
    پایین‌دست، طول، انتخاب‌شده) + گزارش متنی کامل (Markdown سازگار با
    گزارش‌های رسمی).

منطق محاسباتی در ``reliability/sectionalizer.py`` و سرویس در
``application/sectionalizer_service.py`` است؛ این فایل فقط نمایش است.
"""
from __future__ import annotations


def make_sectionalizer_tab(parent=None):     # pragma: no cover (Qt)
    """ساخت تب بهینه‌سازی سکشنالایزر (Qt) و برگرداندن کنترلر آن."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                                   QFormLayout, QGroupBox, QHBoxLayout,
                                   QLabel, QPushButton, QSpinBox,
                                   QSplitter, QTableWidget, QTextEdit,
                                   QVBoxLayout, QWidget)

    from .widgets import fill_table, make_explain_label

    class SectionalizerTab(QWidget):
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
                "<b>بهینه‌سازی سکشنالایزر و کاهش EENS</b> — روش تحلیلی کد "
                "مرجع PowerFactory (تخصیص λ متناسب با طول، زمان تعمیر/بازیابی، "
                "جست‌وجوی حریصانه) روی گراف و مدل بار همین پروژه.")
            head.setWordWrap(True)
            root.addWidget(head)
            root.addWidget(make_explain_label(
                "λ هر فیدر از ماتریس λ/r واقعی خاموشی خوانده می‌شود (در صورت "
                "نبود، مقدار پیش‌فرض تنظیمات با منبع ثبت‌شده). کلیدهای موجود "
                "(مرزهای زون) در حالت پایه لحاظ می‌شوند تا «EENS پایه» وضعیت "
                "فعلی شبکه باشد. هیچ کلیدی در شبکه تغییر نمی‌کند؛ خروجی فقط "
                "پیشنهاد است."))

            split = QSplitter()
            root.addWidget(split, 1)

            # ---------------- ستون چپ: تنظیمات + خلاصه ----------------
            left = QWidget()
            lv = QVBoxLayout(left)
            lv.setContentsMargins(0, 0, 0, 0)

            box = QGroupBox("تنظیمات موتور")
            form = QFormLayout(box)
            self.cmb_lambda_source = QComboBox()
            self.cmb_lambda_source.addItem("λ واقعی خاموشی (ماتریس λ/r پروژه)",
                                           "outage")
            self.cmb_lambda_source.addItem("λ پیش‌فرض تنظیمات", "configured")
            form.addRow("منبع λ هر فیدر:", self.cmb_lambda_source)

            self.sp_lambda = QDoubleSpinBox()
            self.sp_lambda.setRange(0.0, 500.0)
            self.sp_lambda.setDecimals(3)
            self.sp_lambda.setValue(30.0)
            self.sp_lambda.setToolTip(
                "λ پیش‌فرض هر فیدر (خرابی در سال) — فقط برای فیدرهایی که "
                "ماتریس λ/r واقعی ندارند یا وقتی منبع «پیش‌فرض» انتخاب شود.")
            form.addRow("λ پیش‌فرض (خرابی/سال):", self.sp_lambda)

            self.sp_repair = QDoubleSpinBox()
            self.sp_repair.setRange(0.0, 1440.0)
            self.sp_repair.setDecimals(1)
            self.sp_repair.setValue(50.0)
            form.addRow("زمان تعمیر قطعهٔ معیوب (دقیقه):", self.sp_repair)

            self.sp_restore = QDoubleSpinBox()
            self.sp_restore.setRange(0.0, 1440.0)
            self.sp_restore.setDecimals(1)
            self.sp_restore.setValue(20.0)
            form.addRow("زمان بازیابی بار سالم (دقیقه):", self.sp_restore)

            self.sp_max = QSpinBox()
            self.sp_max.setRange(0, 20)
            self.sp_max.setValue(3)
            form.addRow("حداکثر سکشنالایزر هر فیدر:", self.sp_max)

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

            self.cmb_model = QComboBox()
            self.cmb_model.addItem(
                "یکنواخت — هم‌ارز کد مرجع (همهٔ بار سالم با زمان بازیابی)",
                "uniform")
            self.cmb_model.addItem(
                "شعاعی/جهت‌دار — بالادست بی‌برق نمی‌شود", "directional")
            form.addRow("مدل بازیابی:", self.cmb_model)

            self.chk_existing = QCheckBox(
                "کلیدهای موجود به‌عنوان قطعه‌بندی مبنا لحاظ شوند")
            self.chk_existing.setChecked(True)
            form.addRow("", self.chk_existing)
            self.chk_show_map = QCheckBox(
                "سکشنالایزرهای پیشنهادی روی نقشه نمایش داده شوند")
            self.chk_show_map.setChecked(True)
            form.addRow("", self.chk_show_map)

            # هر تغییر تنظیمات ذخیره می‌شود (KV پروژه) — نه فقط چک‌باکس‌ها
            for w in (self.cmb_lambda_source, self.cmb_model):
                w.currentIndexChanged.connect(self._notify_changed)
            for w in (self.sp_lambda, self.sp_repair, self.sp_restore,
                      self.sp_ratio):
                w.valueChanged.connect(self._notify_changed)
            for w in (self.sp_max, self.sp_depth):
                w.valueChanged.connect(self._notify_changed)
            for w in (self.chk_existing, self.chk_show_map):
                w.toggled.connect(self._notify_changed)

            lv.addWidget(box)

            btns = QHBoxLayout()
            self.btn_run = QPushButton("اجرای بهینه‌سازی")
            self.btn_run.clicked.connect(self._run)
            self.btn_map = QPushButton("نمایش روی نقشه")
            self.btn_map.setEnabled(False)
            self.btn_map.clicked.connect(self._show_map)
            btns.addWidget(self.btn_run)
            btns.addWidget(self.btn_map)
            btns.addStretch(1)
            lv.addLayout(btns)

            self.status = QLabel("آماده — ابتدا پروژه را باز و توپولوژی را اجرا کنید.")
            self.status.setWordWrap(True)
            self.status.setStyleSheet("color:#37474f;")
            lv.addWidget(self.status)

            lv.addWidget(QLabel("خلاصهٔ هر فیدر (EENS پایه → نهایی):"))
            self.summary_table = QTableWidget(0, 10)
            self.summary_table.setAlternatingRowColors(True)
            self.summary_table.setWordWrap(True)
            lv.addWidget(self.summary_table, 1)
            split.addWidget(left)

            # ---------------- ستون راست: جزئیات + گزارش ----------------
            right = QWidget()
            rv = QVBoxLayout(right)
            rv.setContentsMargins(0, 0, 0, 0)
            rv.addWidget(QLabel(
                "جزئیات کاندیدها (مرتب بر اساس بار پایین‌دست) — ستون «انتخاب "
                "شده» نتیجهٔ جست‌وجوی حریصانه است:"))
            self.detail_table = QTableWidget(0, 8)
            self.detail_table.setAlternatingRowColors(True)
            rv.addWidget(self.detail_table, 1)
            rv.addWidget(QLabel("گزارش کامل (Markdown):"))
            self.panel = QTextEdit()
            self.panel.setReadOnly(True)
            rv.addWidget(self.panel, 1)
            split.addWidget(right)
            split.setSizes([430, 950])
            self._load_table_headers()

        # --------------------------------------------------------------
        def _load_table_headers(self) -> None:
            fill_table(self.summary_table, [
                "فیدر", "طول (km)", "بار (kW)", "λ (۱/سال)", "منبع λ",
                "قطعه موجود", "کاندید", "EENS پایه (MWh/سال)",
                "تعداد پیشنهادی", "EENS نهایی (MWh/سال)"], [])
            fill_table(self.detail_table, [
                "فیدر", "رتبه", "محل پیشنهادی", "زون", "عمق",
                "بار پایین‌دست (kW)", "سهم بار", "طول پایین‌دست (km)"], [])

        # --------------------------------------------------------------
        def _notify_changed(self, *_args) -> None:
            if self.on_settings_changed is not None:
                self.on_settings_changed(self.settings())

        def settings(self) -> dict:
            """مقادیر فعلی ویجت‌ها → dict قابل ارسال به سرویس."""
            return {
                "failure_rate_source": self.cmb_lambda_source.currentData(),
                "total_failure_rate_per_year": float(self.sp_lambda.value()),
                "repair_time_min": float(self.sp_repair.value()),
                "restoration_time_min": float(self.sp_restore.value()),
                "max_sectionalizers": int(self.sp_max.value()),
                "min_candidate_depth": int(self.sp_depth.value()),
                "max_downstream_load_ratio": float(self.sp_ratio.value()) / 100.0,
                "restoration_model": self.cmb_model.currentData(),
                "use_existing_switches": bool(self.chk_existing.isChecked()),
                "show_on_map": bool(self.chk_show_map.isChecked()),
            }

        def apply_settings(self, d: dict | None) -> None:
            d = dict(d or {})
            if not d:
                return
            src = d.get("failure_rate_source") or d.get("lambda_source")
            if src:
                ix = self.cmb_lambda_source.findData(src)
                if ix >= 0:
                    self.cmb_lambda_source.setCurrentIndex(ix)
            for key, widget, conv in (
                    ("total_failure_rate_per_year", self.sp_lambda, float),
                    ("repair_time_min", self.sp_repair, float),
                    ("restoration_time_min", self.sp_restore, float),
                    ("max_sectionalizers", self.sp_max, int),
                    ("min_candidate_depth", self.sp_depth, int)):
                if d.get(key) is not None:
                    widget.setValue(conv(d[key]))
            if d.get("max_downstream_load_ratio") is not None:
                self.sp_ratio.setValue(
                    float(d["max_downstream_load_ratio"]) * 100.0)
            model = d.get("restoration_model")
            if model:
                ix = self.cmb_model.findData(model)
                if ix >= 0:
                    self.cmb_model.setCurrentIndex(ix)
            if d.get("use_existing_switches") is not None:
                self.chk_existing.setChecked(bool(d["use_existing_switches"]))

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
        def show_result(self, result, *, show_on_map: bool = True) -> None:
            """نمایش نتیجهٔ سرویس (SectionalizerAppResult)."""
            self._result = result
            study = result.study
            rows = []
            for r in study.summary_rows():
                rows.append([
                    r["feeder_key"],
                    f"{r['line_length_km']:.2f}",
                    f"{r['total_load_kw']:,.1f}",
                    f"{r['failure_rate_per_year']:.2f}",
                    r["failure_rate_source"],
                    str(r["existing_sections"]),
                    str(r["candidate_count"]),
                    f"{r['baseline_eens_mwh']:,.4f}",
                    str(r["selected_count"]),
                    f"{r['best_eens_mwh']:,.4f}"])
            fill_table(self.summary_table, [
                "فیدر", "طول (km)", "بار (kW)", "λ (۱/سال)", "منبع λ",
                "قطعه موجود", "کاندید", "EENS پایه (MWh/سال)",
                "تعداد پیشنهادی", "EENS نهایی (MWh/سال)"], rows)

            det = []
            self._selected_nodes = []
            for r in study.candidate_rows():
                det.append([
                    r["feeder_key"], str(r["rank"]),
                    ("✔ " if r["selected"] else "") + str(r["label"]),
                    (r["zone_id"] or "")[:8],
                    str(r["depth"]),
                    f"{r['downstream_load_kw']:,.1f}",
                    f"{r['downstream_ratio'] * 100:.1f}%",
                    f"{r['downstream_length_km']:.2f}"])
            for f in study.feeders:
                if f.best:
                    self._selected_nodes.extend(c.node for c in f.best.selected)
            fill_table(self.detail_table, [
                "فیدر", "رتبه", "محل پیشنهادی", "زون", "عمق",
                "بار پایین‌دست (kW)", "سهم بار", "طول پایین‌دست (km)"], det)
            self.panel.setPlainText(result.markdown)
            self.btn_map.setEnabled(bool(self._selected_nodes) and show_on_map)
            self.status.setText(
                f"پایان — EENS پایه {study.baseline_eens_kwh / 1000.0:,.2f} "
                f"MWh/سال → {study.best_eens_kwh / 1000.0:,.2f} MWh/سال "
                f"(کاهش {study.improvement_percent:.2f}% با "
                f"{study.total_selected} سکشنالایزر).")

        # --------------------------------------------------------------
        def show_persisted(self, payload: dict | None) -> None:
            """نمایش نتیجهٔ ذخیره‌شده در پروژه (پس از بازکردن پروژه)."""
            data = dict(payload or {})
            study = dict(data.get("study") or {})
            rows = []
            for r in study.get("summary_rows") or []:
                rows.append([
                    r.get("feeder_key", ""),
                    f"{float(r.get('line_length_km') or 0):.2f}",
                    f"{float(r.get('total_load_kw') or 0):,.1f}",
                    f"{float(r.get('failure_rate_per_year') or 0):.2f}",
                    str(r.get("failure_rate_source", "")),
                    str(r.get("existing_sections", "")),
                    str(r.get("candidate_count", "")),
                    f"{float(r.get('baseline_eens_mwh') or 0):,.4f}",
                    str(r.get("selected_count", "")),
                    f"{float(r.get('best_eens_mwh') or 0):,.4f}"])
            fill_table(self.summary_table, [
                "فیدر", "طول (km)", "بار (kW)", "λ (۱/سال)", "منبع λ",
                "قطعه موجود", "کاندید", "EENS پایه (MWh/سال)",
                "تعداد پیشنهادی", "EENS نهایی (MWh/سال)"], rows)
            det = []
            self._selected_nodes = []
            for f in study.get("feeders") or []:
                chosen = {c.get("node") for c in
                          ((f.get("best") or {}).get("selected") or [])}
                for c in f.get("candidates") or []:
                    det.append([
                        f.get("feeder_key", ""), str(c.get("rank", "")),
                        ("✔ " if c.get("node") in chosen else "")
                        + str(c.get("label", "")),
                        str(c.get("zone_id", ""))[:8], str(c.get("depth", "")),
                        f"{float(c.get('downstream_load_kw') or 0):,.1f}",
                        f"{float(c.get('downstream_ratio') or 0) * 100:.1f}%",
                        f"{float(c.get('downstream_length_km') or 0):.2f}"])
                self._selected_nodes.extend(
                    str(c.get("node")) for c in
                    ((f.get("best") or {}).get("selected") or []))
            fill_table(self.detail_table, [
                "فیدر", "رتبه", "محل پیشنهادی", "زون", "عمق",
                "بار پایین‌دست (kW)", "سهم بار", "طول پایین‌دست (km)"], det)
            self.panel.setPlainText(
                str(data.get("markdown") or study.get("markdown") or
                    "نتیجهٔ ذخیره‌شدهٔ این پروژه یافت شد."))
            self.btn_map.setEnabled(bool(self._selected_nodes))
            self.status.setText(
                "نتیجهٔ ذخیره‌شدهٔ پروژه بارگذاری شد؛ برای اجرای جدید تنظیمات "
                "را تأیید و «اجرای بهینه‌سازی» را بزنید.")

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

    return SectionalizerTab(parent)
