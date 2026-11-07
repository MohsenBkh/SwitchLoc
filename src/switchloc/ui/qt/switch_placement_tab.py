# -*- coding: utf-8 -*-
"""تب «روش جایابی بهینهٔ کلید و کاهش EENS».

بازطراحی v1.13 (درخواست کاربر): «این پنجره به دو بخش باکس‌های کنار هم تبدیل
شود، جدول نتایج برگردد، و موارد قفل‌شده کم‌رنگ شوند».

  ┌─────────────────────────┐ ┌──────────────────────────────────────────┐
  │ ۱) نوع کلید و روش       │ │ خلاصهٔ نتیجه (KPI: پایه → نهایی → ٪)     │
  │ ۲) نرخ خرابی و زمان‌ها  │ ├──────────────────────────────────────────┤
  │ ۳) خطای گذرا (ریکلوزر)  │ │ جدول نتایج فیدرها                        │
  │ ۴) محدودیت‌های جست‌وجو   │ ├──────────────────────────────────────────┤
  │ [اجرای جایابی] [نقشه]   │ │ جدول کلیدهای پیشنهادی (نتیجهٔ نهایی)     │
  │ وضعیت                    │ ├─────────────────┬────────────────────────┤
  └─────────────────────────┘ │ جدول کاندیدها   │ گزارش Markdown         │
        (قابل جابه‌جایی)       └─────────────────┴────────────────────────┘

قاعده‌های رابط کاربری
---------------------
* **قفل و کم‌رنگی** — هر ورودی که در روش/نوع کلید انتخابی استفاده نمی‌شود
  غیرفعال و **کم‌رنگ** می‌شود، با برچسب روشن «🔒 خودکار» یا دلیل قفل در
  tooltip؛ بنابراین تفاوت «ورودی مؤثر» و «ورودی نمایشی» واضح است.
* **λ و r در روش‌های واقعی** (دایرکشنال/یکنواخت) از ماتریس λ/r پروژه
  می‌آیند: فیلدهای دستی قفل و مقادیر واقعیِ هر فیدر پس از اجرا زیر همان
  فیلدها نمایش داده می‌شود.
* **زمان بازیابی بار سالم** و پارامترهای گذرا در همهٔ روش‌ها مؤثرند و قفل
  نمی‌شوند (پیش‌تر به‌اشتباه قفل می‌شدند).
* همهٔ مرزها با ``QSplitter`` جابه‌جاشدنی‌اند.

منطق محاسباتی در ``reliability/switch_placement.py`` و سرویس در
``application/switch_placement_service.py`` است؛ این فایل فقط نمایش است.
"""
from __future__ import annotations


def make_sectionalizer_tab(parent=None):     # pragma: no cover (Qt)
    """ساخت تب «روش جایابی بهینهٔ کلید» (Qt) و برگرداندن کنترلر آن."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                                   QFormLayout, QFrame, QGroupBox,
                                   QHBoxLayout, QHeaderView, QLayout,
                                   QLabel, QPushButton, QScrollArea,
                                   QSizePolicy, QSpinBox, QSplitter,
                                   QTableWidget, QTextEdit, QVBoxLayout,
                                   QWidget)

    from ...application.switch_placement_service import (EENS_METHOD_FA,
                                                         EENS_METHOD_ORDER)
    from ...reliability.switch_placement import (SWITCH_DISCONNECTOR,
                                                 SWITCH_RECLOSER,
                                                 SWITCH_TYPES,
                                                 SWITCH_TYPE_FA)
    from .widgets import fill_table, make_explain_label

    # سرستون‌ها یک‌خطی‌اند تا در ارتفاع هدر بریده نشوند؛ واحدها در عنوان
    # هر گروه نوشته می‌شوند (قبلاً «EENS پایه (MWh)» دو خط می‌شد و بریده بود).
    SUMMARY_HEADERS = ["فیدر", "طول (km)", "بار (kW)", "λ (۱/سال)",
                       "r (دقیقه)", "منبع λ", "قطعه", "کاندید",
                       "EENS پایه", "کلید", "EENS نهایی", "کاهش ٪"]
    RESULT_HEADERS = ["فیدر", "کلید پیشنهادی", "زون", "بار پایین‌دست",
                      "EENS پایه", "EENS نهایی", "کاهش ٪"]
    DETAIL_HEADERS = ["فیدر", "رتبه", "محل پیشنهادی", "زون", "عمق",
                      "بار پایین‌دست", "سهم بار", "طول پایین‌دست"]

    #: کم‌رنگ‌کردن ورودی‌های قفل‌شده (درخواست کاربر)
    LOCK_STYLE = (
        "QDoubleSpinBox:disabled, QSpinBox:disabled, QComboBox:disabled,"
        " QCheckBox:disabled { color:#b4b4b4; background:#f5f5f5;"
        " border:1px solid #e3e3e3; }"
        " QLabel[locked=\"true\"] { color:#b4b4b4; }"
        " QLabel#lockBadge { color:#8d6e63; background:#fff3e0;"
        " border:1px solid #ffe0b2; border-radius:3px; padding:1px 4px; }"
        " QLabel#kpiValue { color:#0d47a1; font-weight:bold; }"
    )

    def _ltr(text: str) -> str:
        """محصورکردن عدد/عبارت لاتین با نشانهٔ جهت تا در متن فارسی جابه‌جا نشود."""
        return "\u2066" + str(text) + "\u2069"

    def _first_clause(text: str, limit: int = 90) -> str:
        """کوتاه‌کردن متن توضیح برای نمایش در یک خط (بدون بریدن کلمه)."""
        text = str(text or "").strip()
        for sep in ("؛", "،", ".", "—"):
            head = text.split(sep)[0].strip()
            if 12 <= len(head) <= limit:
                return head
        return text if len(text) <= limit else text[:limit].rstrip() + "…"

    class SwitchPlacementTab(QWidget):
        """کنترلر تب — سیم‌کشی با main_window از طریق callback‌ها."""

        def __init__(self, parent_=None):
            super().__init__(parent_)
            self.on_run = None           # callback(settings dict)
            self.on_show_map = None      # callback(selected node ids)
            self.on_settings_changed = None
            self._result = None
            self._selected_nodes: list[str] = []
            self._suspend_changed = False
            self._lock_pairs: list[tuple[QWidget, QLabel | None, str]] = []
            self._note_labels: list[QLabel] = []   # برچسب‌های چندخطی پنل ورودی
            self._inputs_pane = None
            self._in_relayout = False

            self.setStyleSheet(LOCK_STYLE)

            root = QVBoxLayout(self)
            root.setContentsMargins(6, 6, 6, 6)
            head = QLabel(
                "<b>روش جایابی بهینهٔ کلید و کاهش EENS</b> — جایابی "
                "ریکلوزر، سکشنالایزر و سکسیونر روی گراف و مدل بار همین "
                "پروژه (تخصیص λ متناسب طول، زمان تعمیر/بازیابی، جست‌وجوی "
                "حریصانه).")
            head.setWordWrap(True)
            root.addWidget(head)

            # ==== دو بخش کنار هم: ورودی‌ها | نتایج =======================
            self.main_split = QSplitter(Qt.Orientation.Horizontal)
            self.main_split.setChildrenCollapsible(False)
            root.addWidget(self.main_split, 1)
            self.main_split.addWidget(self._build_inputs_pane())
            self.main_split.addWidget(self._build_results_pane())
            self.main_split.setStretchFactor(0, 0)
            self.main_split.setStretchFactor(1, 1)
            self.main_split.setSizes([610, 830])

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

        # ==============================================================
        # ساخت پنل ورودی‌ها (سمت چپ)
        # ==============================================================
        def _build_inputs_pane(self) -> QWidget:
            pane = QWidget()
            pv = QVBoxLayout(pane)
            pv.setContentsMargins(0, 0, 0, 0)
            pv.setSpacing(6)
            # مهم: بدون این constraint، QScrollArea محتوا را در ارتفاع کم
            # می‌فشرد و عنوان گروه‌ها/ردیف‌های فرم بریده می‌شدند.
            pv.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

            box = QGroupBox("۱) نوع کلید و روش محاسبهٔ EENS")
            bv = QVBoxLayout(box)
            bv.setSpacing(4)
            form = QFormLayout()
            form.setVerticalSpacing(4)
            form.setRowWrapPolicy(
                QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            bv.addLayout(form)

            self.cmb_switch_type = QComboBox()
            for key in SWITCH_TYPES:
                self.cmb_switch_type.addItem(SWITCH_TYPE_FA[key], key)
            form.addRow("نوع کلید:", self.cmb_switch_type)

            self.cmb_method = QComboBox()
            for key in EENS_METHOD_ORDER:       # دایرکشنال، یکنواخت، دستی
                # متن کامل روش‌ها در کمبو جا نمی‌شد و بریده می‌شد؛ توضیح
                # کامل در برچسب زیر فرم و در tooltip آیتم هست.
                self.cmb_method.addItem(
                    str(EENS_METHOD_FA[key]).split(" — ", 1)[0], key)
                self.cmb_method.setItemData(
                    self.cmb_method.count() - 1, EENS_METHOD_FA[key],
                    Qt.ItemDataRole.ToolTipRole)
            self.cmb_method.setCurrentIndex(
                max(0, self.cmb_method.findData("uniform")))
            form.addRow("روش EENS:", self.cmb_method)

            self.lbl_note = self._note_label()
            bv.addWidget(self.lbl_note)
            pv.addWidget(box)

            rates = QGroupBox("۲) نرخ خرابی و زمان‌ها")
            rv = QVBoxLayout(rates)
            rv.setSpacing(4)
            rform = QFormLayout()
            rform.setVerticalSpacing(4)
            rform.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            rform.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            rv.addLayout(rform)

            self.sp_lambda = QDoubleSpinBox()
            self.sp_lambda.setRange(0.0, 500.0)
            self.sp_lambda.setDecimals(3)
            self.sp_lambda.setValue(30.0)
            self.sp_lambda.setToolTip(
                "λ دستی هر فیدر (خرابی/سال) — فقط در روش «دستی» مؤثر است.")
            self._add_locked_row(rform, "λ دستی (خرابی در سال):",
                                 self.sp_lambda)

            self.sp_repair = QDoubleSpinBox()
            self.sp_repair.setRange(0.0, 1440.0)
            self.sp_repair.setDecimals(1)
            self.sp_repair.setValue(50.0)
            self.sp_repair.setToolTip(
                "r دستی (زمان تعمیر، دقیقه) — فقط در روش «دستی» مؤثر است.")
            self._add_locked_row(rform, "r دستی (زمان تعمیر، دقیقه):",
                                 self.sp_repair)

            self.lbl_auto_info = self._note_label(small=True)
            self.lbl_auto_info.setVisible(False)
            rv.addWidget(self.lbl_auto_info)

            self.sp_restore = QDoubleSpinBox()
            self.sp_restore.setRange(0.0, 1440.0)
            self.sp_restore.setDecimals(1)
            self.sp_restore.setValue(20.0)
            self.sp_restore.setToolTip(
                "زمان بازیابی بار سالم (دقیقه) — در همهٔ روش‌ها مؤثر است.")
            rform.addRow("زمان بازیابی بار سالم (دقیقه):", self.sp_restore)

            self.sp_manual_restore = QDoubleSpinBox()
            self.sp_manual_restore.setRange(0.0, 1440.0)
            self.sp_manual_restore.setDecimals(1)
            self.sp_manual_restore.setValue(30.0)
            self.sp_manual_restore.setToolTip(
                "کلید دستی است؛ این زمان جای زمان بازیابی خودکار می‌نشیند.")
            self._add_locked_row(rform, "بازیابی دستی سکسیونر (دقیقه):",
                                 self.sp_manual_restore)
            pv.addWidget(rates)

            self.grp_transient = QGroupBox("۳) خطای گذرا (ویژهٔ ریکلوزر)")
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
            self.grp_transient.setVisible(False)
            pv.addWidget(self.grp_transient)

            limits = QGroupBox("۴) محدودیت‌های جست‌وجو")
            lform = QFormLayout(limits)
            lform.setVerticalSpacing(4)
            lform.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            lform.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            self.sp_max = QSpinBox()
            self.sp_max.setRange(0, 20)
            self.sp_max.setValue(3)
            lform.addRow("حداکثر کلید هر فیدر:", self.sp_max)

            self.sp_depth = QSpinBox()
            self.sp_depth.setRange(0, 100000)
            self.sp_depth.setValue(3)
            self.sp_depth.setToolTip(
                "کمترین فاصله (تعداد یال) از سر فیدر؛ ۰ = بدون محدودیت.")
            lform.addRow("عمق کمینهٔ کاندید:", self.sp_depth)

            self.sp_ratio = QDoubleSpinBox()
            self.sp_ratio.setRange(1.0, 100.0)
            self.sp_ratio.setDecimals(0)
            self.sp_ratio.setValue(80.0)
            self.sp_ratio.setToolTip(
                "کاندیدی که بیش از این درصد از بار فیدر را در پایین‌دست "
                "دارد پیشنهاد نمی‌شود (پرهیز از بی‌برق‌کردن عمدهٔ فیدر).")
            lform.addRow("سقف سهم بار پایین‌دست (٪):", self.sp_ratio)

            self.sp_backup = QDoubleSpinBox()
            self.sp_backup.setRange(0.0, 1e7)
            self.sp_backup.setDecimals(0)
            self.sp_backup.setValue(0.0)
            self.sp_backup.setSpecialValueText("نامحدود")
            self.sp_backup.setToolTip(
                "ظرفیت پشتیبان هر فیدر (kW)؛ صفر = نامحدود (فرض روش مرجع).")
            lform.addRow("ظرفیت پشتیبان (kW):", self.sp_backup)

            self.chk_existing = QCheckBox(
                "کلیدهای موجود به‌عنوان قطعه‌بندی مبنا لحاظ شوند")
            self.chk_existing.setChecked(True)
            lform.addRow("", self.chk_existing)
            self.chk_show_map = QCheckBox(
                "کلیدهای پیشنهادی روی نقشه نمایش داده شوند")
            self.chk_show_map.setChecked(True)
            lform.addRow("", self.chk_show_map)
            pv.addWidget(limits)

            self.grp_run = QGroupBox("اجرا")
            gv = QVBoxLayout(self.grp_run)
            btns = QHBoxLayout()
            self.btn_run = QPushButton("اجرای جایابی")
            self.btn_run.clicked.connect(self._run)
            self.btn_map = QPushButton("نمایش روی نقشه")
            self.btn_map.setEnabled(False)
            self.btn_map.clicked.connect(self._show_map)
            btns.addWidget(self.btn_run)
            btns.addWidget(self.btn_map)
            btns.addStretch(1)
            gv.addLayout(btns)
            self.status = QLabel(
                "آماده — ابتدا پروژه را باز و توپولوژی را اجرا کنید.")
            self.status.setWordWrap(True)
            self._note_labels.append(self.status)
            self.status.setStyleSheet("color:#37474f;")
            gv.addWidget(self.status)
            gv.addWidget(make_explain_label(
                "در روش‌های «دایرکشنال» و «یکنواخت»، λ و r به‌صورت خودکار "
                "از ماتریس λ/r واقعی خاموشی‌های پروژه خوانده می‌شوند و "
                "فیلدهای دستی قفل/کم‌رنگ می‌شوند. هیچ کلیدی در شبکه تغییر "
                "نمی‌کند؛ خروجی فقط پیشنهاد است."))
            pv.addWidget(self.grp_run)
            pv.addStretch(1)

            self._inputs_pane = pane
            self._relayout_inputs()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(pane)
            scroll.setMinimumWidth(560)
            scroll.setMinimumHeight(320)
            scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            return scroll

        # ==============================================================
        # ساخت پنل نتایج (سمت راست)
        # ==============================================================
        def _build_results_pane(self) -> QWidget:
            pane = QWidget()
            pv = QVBoxLayout(pane)
            pv.setContentsMargins(0, 0, 0, 0)
            pv.setSpacing(6)

            kpi = QGroupBox("خلاصهٔ نتیجه")
            kv = QHBoxLayout(kpi)
            self.lbl_kpi_base = self._kpi_block(kv, "EENS پایه")
            self.lbl_kpi_best = self._kpi_block(kv, "EENS نهایی")
            self.lbl_kpi_red = self._kpi_block(kv, "کاهش")
            self.lbl_kpi_keys = self._kpi_block(kv, "کلید پیشنهادی")
            kv.addStretch(1)
            pv.addWidget(kpi)

            self.results_split = QSplitter(Qt.Orientation.Vertical)
            self.results_split.setChildrenCollapsible(False)
            pv.addWidget(self.results_split, 1)

            # ---- جدول نتایج فیدرها ----
            sum_box = QGroupBox(
                "نتایج فیدرها — EENS پایه → نهایی (MWh/سال)")
            sv = QVBoxLayout(sum_box)
            self.summary_table = QTableWidget(0, len(SUMMARY_HEADERS))
            self.summary_table.setAlternatingRowColors(True)
            self.summary_table.setWordWrap(True)
            sv.addWidget(self.summary_table)
            self.results_split.addWidget(sum_box)

            # ---- جدول کلیدهای پیشنهادی (نتیجهٔ نهایی) ----
            res_box = QGroupBox(
                "کلیدهای پیشنهادی — نتیجهٔ جایابی (EENS: MWh/سال)")
            rv2 = QVBoxLayout(res_box)
            self.results_table = QTableWidget(0, len(RESULT_HEADERS))
            self.results_table.setAlternatingRowColors(True)
            self.results_table.setWordWrap(True)
            rv2.addWidget(self.results_table)
            self.results_split.addWidget(res_box)

            # ---- کاندیدها | گزارش ----
            bottom = QSplitter(Qt.Orientation.Horizontal)
            bottom.setChildrenCollapsible(False)
            left = QGroupBox(
                "همهٔ کاندیدها — بار پایین‌دست (kW)، طول (km)")
            self.grp_detail = left
            lv = QVBoxLayout(left)
            self.detail_table = QTableWidget(0, len(DETAIL_HEADERS))
            self.detail_table.setAlternatingRowColors(True)
            lv.addWidget(self.detail_table)
            right = QGroupBox("گزارش کامل (Markdown)")
            rv = QVBoxLayout(right)
            self.panel = QTextEdit()
            self.panel.setReadOnly(True)
            # گزارش Markdown به متن خوانا تبدیل می‌شود: رندر Markdown در Qt
            # تیتر غول‌آسا و جدول‌های بی‌قاعده می‌سازد و متن فارسی را
            # به‌هم می‌ریزد؛ متن ساده + راست‌به‌چپ خواناتر است.
            self.panel.setStyleSheet("font-size:9pt;")
            rv.addWidget(self.panel)
            bottom.addWidget(left)
            bottom.addWidget(right)
            bottom.setSizes([620, 380])
            self.results_split.addWidget(bottom)

            self.results_split.setSizes([210, 150, 260])
            return pane

        # ==============================================================
        def _kpi_block(self, layout: QHBoxLayout, title: str) -> QLabel:
            from PySide6.QtWidgets import QVBoxLayout as _V
            holder = QWidget()
            v = _V(holder)
            v.setContentsMargins(6, 0, 12, 0)
            cap = QLabel(title)
            cap.setStyleSheet("color:#607d8b;")
            value = QLabel("—")
            value.setObjectName("kpiValue")
            # عرض کمینه تا «629.25 MWh/yr» بریده نشود
            value.setMinimumWidth(118)
            value.setSizePolicy(QSizePolicy.Policy.Minimum,
                                QSizePolicy.Policy.Fixed)
            v.addWidget(cap)
            v.addWidget(value)
            holder.setSizePolicy(QSizePolicy.Policy.Preferred,
                                 QSizePolicy.Policy.Fixed)
            layout.addWidget(holder)
            return value

        def _note_label(self, small: bool = False) -> QLabel:
            """برچسب توضیح (نه دکمهٔ راهنما) — متن کامل، شکسته‌شدنی."""
            lbl = QLabel("")
            # ارتفاع برچسب چندخطی باید صریح تنظیم شود؛ QLabel با wordWrap در
            # minimumSizeHint فقط یک خط گزارش می‌کند و چیدمان آن را می‌فشرد
            # (متن بریده یا روی قاب گروه می‌افتاد).
            self._note_labels.append(lbl)
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            # عرض «Ignored» تا متن در ستون فرم بشکند و از پنل بیرون نزند
            lbl.setSizePolicy(QSizePolicy.Policy.Ignored,
                              QSizePolicy.Policy.Minimum)
            size = 8.0 if small else 8.5
            lbl.setStyleSheet(
                f"color:#546e7a; font-size:{size}pt; background:#eceff1;"
                " border-radius:3px; padding:2px 4px;")
            return lbl

        def _relayout_inputs(self) -> None:
            """ارتفاع واقعی برچسب‌های چندخطی پنل ورودی‌ها را تنظیم کن."""
            pane = getattr(self, "_inputs_pane", None)
            if pane is None or getattr(self, "_in_relayout", False):
                return
            self._in_relayout = True
            try:
                width = max(200, pane.width() - 16)
                for lbl in list(getattr(self, "_note_labels", [])):
                    if not lbl.text():
                        continue
                    h = lbl.heightForWidth(width)
                    if h > 0:
                        lbl.setMinimumHeight(h + 6)
                lay = pane.layout()
                if lay is not None:
                    lay.invalidate()
                    lay.activate()
                pane.adjustSize()
            finally:
                self._in_relayout = False

        def resizeEvent(self, event):           # noqa: N802 (Qt API)
            super().resizeEvent(event)
            self._relayout_inputs()
            for name in ("summary_table", "results_table", "detail_table"):
                table = getattr(self, name, None)
                if table is not None and table.columnCount():
                    self._fit_columns(
                        table, allow_scroll=(name == "detail_table"))

        def _add_locked_row(self, form, label_text: str, widget) -> None:
            """ردیف فرم؛ نشان «[قفل]» هنگام قفل‌شدن به متن برچسب می‌چسبد."""
            widget.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Fixed)
            form.addRow(label_text, widget)
            lbl = form.labelForField(widget)
            self._lock_pairs.append((widget, lbl, label_text))

        # --------------------------------------------------------------
        def _lock_info(self, widget):
            for w, lbl, base in self._lock_pairs:
                if w is widget:
                    return lbl, base
            return None, ""

        def _set_locked(self, widget, locked: bool,
                        reason: str = "") -> None:
            """قفل + کم‌رنگ‌کردن یک ورودی و برچسبش.

            برچسبِ ردیف هم کم‌رنگ می‌شود و نشان «🔒» می‌گیرد تا تفاوت
            «ورودی مؤثر» و «ورودی نمایشی» بلافاصله دیده شود.
            """
            label, base = self._lock_info(widget)
            widget.setEnabled(not locked)
            widget.setToolTip(reason if locked else "")
            if label is not None:
                label.setText(f"{base}  [قفل]" if locked else base)
                label.setProperty("locked", bool(locked))
                label.setToolTip(reason if locked else "")
                style = label.style()
                style.unpolish(label)
                style.polish(label)

        # --------------------------------------------------------------
        @staticmethod
        def _fit_columns(table, allow_scroll: bool = False) -> None:
            """عرض ستون‌ها: متناسب با محتوا و عرض پنجره.

            * جدول‌های کوچک (نتایج فیدرها/کلیدها): ستون‌ها متناسب کوچک
              می‌شوند تا در عرض پنل جا شوند و اسکرول افقی لازم نشود.
            * جدول بزرگ کاندیدها (``allow_scroll=True``): عرض بر اساس محتوا
              می‌ماند و جدول افقی اسکرول می‌شود؛ کوچک‌کردن متناسب، همهٔ
              ستون‌ها را ناخوانا می‌کرد.
            """
            header = table.horizontalHeader()
            header.setMinimumHeight(30)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(False)
            table.resizeColumnsToContents()
            table.resizeRowsToContents()
            columns = table.columnCount()
            if not columns:
                return
            widths = [max(44, table.columnWidth(col)) for col in range(columns)]
            viewport = table.viewport().width()
            if viewport <= 0:
                return
            total = sum(widths)
            if allow_scroll:
                header.setStretchLastSection(total < viewport)
                if total < viewport:
                    widths[-1] += viewport - total
            elif total > viewport:
                scale = viewport / float(total)
                widths = [max(44, int(w * scale)) for w in widths]
                over = sum(widths) - viewport
                while over > 0 and max(widths) > 44:
                    widths[widths.index(max(widths))] -= 1
                    over -= 1
            else:
                header.setStretchLastSection(True)
                widths[-1] += viewport - total
            for col, width in enumerate(widths):
                table.setColumnWidth(col, width)
            # متن کامل سلول‌ها در tooltip (ستون‌ها ممکن است باریک شوند)
            if table.rowCount() <= 400:
                for row in range(table.rowCount()):
                    for col in range(columns):
                        item = table.item(row, col)
                        if item is not None and item.text():
                            item.setToolTip(item.text())

        def _load_table_headers(self) -> None:
            fill_table(self.summary_table, SUMMARY_HEADERS, [])
            fill_table(self.results_table, RESULT_HEADERS, [])
            fill_table(self.detail_table, DETAIL_HEADERS, [])
            for table in (self.summary_table, self.results_table,
                          self.detail_table):
                self._fit_columns(table)

        # --------------------------------------------------------------
        def current_switch_type(self) -> str:
            return str(self.cmb_switch_type.currentData() or "sectionalizer")

        def current_method(self) -> str:
            return str(self.cmb_method.currentData() or "uniform")

        def _on_mode_changed(self, *_args) -> None:
            """قفل/کم‌رنگ‌کردن ورودی‌ها بر اساس نوع کلید و روش EENS."""
            switch_type = self.current_switch_type()
            method = self.current_method()
            manual = method == "manual"

            self.grp_transient.setVisible(switch_type == SWITCH_RECLOSER)

            auto_reason = ("خودکار از ماتریس λ/r واقعی خاموشی‌های پروژه — "
                           "برای ورود دستی، روش «دستی» را انتخاب کنید.")
            for w in (self.sp_lambda, self.sp_repair):
                self._set_locked(w, not manual, auto_reason)

            is_disc = switch_type == SWITCH_DISCONNECTOR
            self._set_locked(
                self.sp_manual_restore, not is_disc,
                "این زمان فقط برای «سکسیونر» (کلید دستی) معنا دارد.")

            # زمان بازیابی بار سالم در همهٔ روش‌ها مؤثر است → هرگز قفل نمی‌شود
            self.sp_restore.setEnabled(True)

            self._update_notes()
            self._notify_changed()

        def _update_notes(self) -> None:
            from ...reliability.switch_placement import (SWITCH_TYPE_FA,
                                                         SWITCH_TYPE_NOTE_FA)
            switch_type = self.current_switch_type()
            method = self.current_method()
            note = EENS_METHOD_FA[method].split(" — ", 1)
            detail = note[1] if len(note) > 1 else ""
            self.lbl_note.setText(
                "<b>" + SWITCH_TYPE_FA[switch_type].split(" (")[0] + ":</b> "
                + _first_clause(SWITCH_TYPE_NOTE_FA[switch_type]) +
                "<br><b>روش:</b> " + _first_clause(detail, 110))

        def _notify_changed(self, *_args) -> None:
            if self._suspend_changed:
                return
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

        @staticmethod
        def _coerce_number(value):
            """عدد از مقدار ذخیره‌شده: عدد، رشته، یا dict (مثل backup_kw)."""
            if isinstance(value, dict):
                vals = [v for v in value.values() if v is not None]
                if not vals:
                    return None
                try:
                    return max(float(v) for v in vals)
                except (TypeError, ValueError):
                    return None
            if isinstance(value, (list, tuple)):
                vals = [v for v in value if v is not None]
                if not vals:
                    return None
                try:
                    return max(float(v) for v in vals)
                except (TypeError, ValueError):
                    return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def apply_settings(self, d: dict | None) -> None:
            raw = dict(d or {})
            if not raw:
                return
            # snapshot سرویس دو سطح دارد: engine (تنظیمات موتور) + تنظیمات
            # تب؛ سطح بیرونی بر داخلی مقدم است. پروژه‌های قدیمی فقط engine
            # دارند و همان هم باید بازخوانی شود.
            engine = raw.get("engine")
            if isinstance(engine, dict) and engine:
                d = {**engine, **{k: v for k, v in raw.items() if k != "engine"}}
            else:
                d = raw
            if not d:
                return
            # یک اعلان در پایان، نه یکی برای هر ویجت (بهبود کارایی)
            self._suspend_changed = True
            try:
                for key, cmb in (("switch_type", self.cmb_switch_type),
                                 ("method", self.cmb_method)):
                    if d.get(key):
                        ix = cmb.findData(str(d[key]))
                        if ix >= 0:
                            cmb.setCurrentIndex(ix)
                # سازگاری با تنظیمات قدیمی (restoration_model / source)
                if not d.get("method"):
                    # «λ/r دستی» بر مدل بازیابی قدیمی مقدم است
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
                        ("manual_restoration_time_min",
                         self.sp_manual_restore),
                        ("transient_max_duration_min", self.sp_transient_min),
                        ("transient_interruption_min",
                         self.sp_transient_time),
                        ("reclose_time_min", self.sp_reclose_time),
                        ("backup_kw", self.sp_backup)):
                    number = self._coerce_number(d.get(key))
                    if number is not None:
                        widget.setValue(number)
                for key, widget in (("max_sectionalizers", self.sp_max),
                                    ("min_candidate_depth", self.sp_depth)):
                    number = self._coerce_number(d.get(key))
                    if number is not None:
                        widget.setValue(int(number))
                ratio = self._coerce_number(d.get("max_downstream_load_ratio"))
                if ratio is not None:
                    self.sp_ratio.setValue(ratio * 100.0)
                prob = self._coerce_number(d.get("reclose_success_probability"))
                if prob is not None:
                    self.sp_reclose_p.setValue(prob * 100.0)
                if d.get("use_existing_switches") is not None:
                    self.chk_existing.setChecked(
                        bool(d["use_existing_switches"]))
                if d.get("show_on_map") is not None:
                    self.chk_show_map.setChecked(bool(d["show_on_map"]))
            finally:
                self._suspend_changed = False
            self._on_mode_changed()

        # --------------------------------------------------------------
        def set_busy(self, busy: bool, text: str = "") -> None:
            self.btn_run.setEnabled(not busy)
            self.btn_run.setText("در حال محاسبه…" if busy else "اجرای جایابی")
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
                f"{float(r.get('baseline_eens_mwh') or 0):,.2f}",
                str(r.get("selected_count", "")),
                f"{float(r.get('best_eens_mwh') or 0):,.2f}",
                f"{float(r.get('improvement_percent') or 0):.2f}",
            ]

        @staticmethod
        def _short_place(label, feeder_key: str = "",
                         keep_coords: bool = True) -> str:
            """برچسب کوتاه محل: بدون تکرار نام فیدر و (اختیاری) بدون مختصات."""
            parts = [p.strip() for p in str(label or "").split(" · ")]
            parts = [p for p in parts if p and p != str(feeder_key)]
            if not keep_coords:
                parts = [p for p in parts if not p.startswith("@")]
            return " · ".join(parts) or str(label or "")

        @staticmethod
        def _result_row(feeder_key: str, c: dict, row: dict) -> list:
            """یک ردیف «کلید پیشنهادی» با نتیجهٔ همان فیدر."""
            return [
                feeder_key,
                SwitchPlacementTab._short_place(c.get("label"), feeder_key,
                                                keep_coords=False),
                str(c.get("zone_id", ""))[:8] or "—",
                f"{float(c.get('downstream_load_kw') or 0):,.1f}",
                f"{float(row.get('baseline_eens_mwh') or 0):,.2f}",
                f"{float(row.get('best_eens_mwh') or 0):,.2f}",
                f"{float(row.get('improvement_percent') or 0):.2f}",
            ]

        @staticmethod
        @staticmethod
        def _place_text(c: dict, feeder_key: str) -> str:
            """«مختصات (LTR) · نوع خط» — مختصات هرگز در متن فارسی جابه‌جا نشود."""
            label = SwitchPlacementTab._short_place(
                c.get("label"), feeder_key, keep_coords=False)
            coord = c.get("coord") or c.get("coord_utm") or c.get("xy")
            try:
                x, y = float(coord[0]), float(coord[1])
            except (TypeError, ValueError, IndexError, KeyError):
                return label
            nums = _ltr(f"@ {x:,.0f}, {y:,.0f} m")
            return f"{nums} · {label}" if label else nums

        @staticmethod
        def _detail_row(feeder_key: str, c: dict, selected: bool) -> list:
            return [
                feeder_key, str(c.get("rank", "")),
                ("● " if selected else "")
                + SwitchPlacementTab._place_text(c, feeder_key),
                str(c.get("zone_id", ""))[:8], str(c.get("depth", "")),
                f"{float(c.get('downstream_load_kw') or 0):,.1f}",
                f"{float(c.get('downstream_ratio') or 0) * 100:.1f}%",
                f"{float(c.get('downstream_length_km') or 0):.2f}",
            ]

        # --------------------------------------------------------------
        @staticmethod
        def _md_to_text(markdown: str) -> str:
            """Markdown → متن خوانا برای پنل گزارش (بدون «|» و «#»)."""
            out: list[str] = []
            for raw in str(markdown or "").splitlines():
                line = raw.rstrip()
                if not line.strip():
                    out.append("")
                    continue
                body = line.strip()
                if set(body) <= set("|-: "):          # جداکنندهٔ جدول
                    continue
                if body.startswith("|"):
                    cells = [c.strip() for c in body.strip("|").split("|")]
                    cells = [c for c in cells if c]
                    out.append(" · ".join(cells))
                    continue
                text = body.lstrip("#").strip()
                text = text.replace("**", "").replace("`", "")
                out.append(text)
            return "\n".join(out).strip()

        def _set_markdown_panel(self, markdown: str) -> None:
            self.panel.setPlainText(self._md_to_text(markdown))

        def _set_kpis(self, base_mwh, best_mwh, reduction, keys) -> None:
            def _fmt(v):
                return "—" if v is None else f"{float(v):,.3f}"

            self.lbl_kpi_base.setText(
                _ltr(f"{_fmt(base_mwh)} MWh/yr") if base_mwh is not None
                else "—")
            self.lbl_kpi_best.setText(
                _ltr(f"{_fmt(best_mwh)} MWh/yr") if best_mwh is not None
                else "—")
            self.lbl_kpi_red.setText(
                f"{float(reduction):.2f}٪" if reduction is not None else "—")
            self.lbl_kpi_keys.setText(
                "—" if keys is None else f"{int(keys)} کلید")
            for lbl in (self.lbl_kpi_base, self.lbl_kpi_best,
                        self.lbl_kpi_red, self.lbl_kpi_keys):
                lbl.setMinimumWidth(118)
                lbl.updateGeometry()

        # --------------------------------------------------------------
        def _auto_rates_text(self, from_settings: dict | None) -> str:
            rates = dict((from_settings or {}).get("failure_rates") or {})
            repairs = dict((from_settings or {}).get("repair_time_by_feeder")
                           or {})
            if not rates and not repairs:
                return ("پس از اجرا، λ و r واقعی هر فیدر این‌جا نمایش "
                        "داده می‌شود.")
            parts = []
            for key in sorted(set(rates) | set(repairs)):
                lam = f"{rates[key]:.3f}" if key in rates else "—"
                r_val = f"{repairs[key]:.1f}" if key in repairs else "—"
                parts.append(f"{key}: λ={lam}، r={r_val}")
            return " · ".join(parts)

        # --------------------------------------------------------------
        #: سقف ردیف‌های جدول کاندیدها (کارایی QTableWidget)
        DETAIL_LIMIT_PER_FEEDER = 60

        def _detail_rows(self, rows) -> tuple[list, int, int]:
            """(ردیف‌های نمایشی، تعداد نمایش‌داده‌شده، تعداد کل).

            با هزاران کاندید، پرکردن QTableWidget کند می‌شود؛ برای هر فیدر
            فقط ``DETAIL_LIMIT_PER_FEEDER`` ردیف اول (رتبه‌بندی‌شده) نمایش
            داده می‌شود و همین در عنوان جدول صریح نوشته می‌شود. فهرست کامل
            در گزارش Markdown و JSON پروژه هست.
            """
            per_feeder: dict[str, int] = {}
            out, total = [], 0
            for r in rows:
                total += 1
                key = str(r.get("feeder_key", ""))
                idx = per_feeder.get(key, 0)
                if idx >= self.DETAIL_LIMIT_PER_FEEDER:
                    continue
                per_feeder[key] = idx + 1
                out.append(self._detail_row(key, r, bool(r["selected"])))
            return out, len(out), total

        def show_result(self, result, *, show_on_map: bool = True) -> None:
            """نمایش نتیجهٔ سرویس (SwitchPlacementAppResult)."""
            self._result = result
            study = result.study
            rows = [self._summary_row(r) for r in study.summary_rows()]
            fill_table(self.summary_table, SUMMARY_HEADERS, rows)
            self._fit_columns(self.summary_table)

            # ---- جدول کلیدهای پیشنهادی (نتیجهٔ نهایی) ----
            by_feeder = {str(r.get("feeder_key")): r
                         for r in study.summary_rows()}
            res_rows = []
            self._selected_nodes = []
            for f in study.feeders:
                if not f.best or not f.best.selected:
                    continue
                row = by_feeder.get(str(f.feeder_key), {})
                res_rows.extend(
                    self._result_row(str(f.feeder_key), {
                        "label": c.label, "zone_id": c.zone_id,
                        "downstream_load_kw": c.downstream_load_kw}, row)
                    for c in f.best.selected)
                self._selected_nodes.extend(c.node for c in f.best.selected)
            fill_table(self.results_table, RESULT_HEADERS, res_rows)
            self._fit_columns(self.results_table)

            det, shown, total = self._detail_rows(
                study.candidate_rows())
            fill_table(self.detail_table, DETAIL_HEADERS, det)
            self._fit_columns(self.detail_table, allow_scroll=True)
            self.grp_detail.setTitle(
                "همهٔ کاندیدها — بار پایین‌دست (kW)، طول (km)" +
                (f" — نمایش {shown:,} از {total:,} ردیف (برای کارایی)"
                 if shown < total else f" — {total:,} ردیف"))
            self._set_markdown_panel(result.markdown)
            self.btn_map.setEnabled(bool(self._selected_nodes) and show_on_map)
            st = study.settings or {}
            self._auto_rates_text_set(st)
            self._set_kpis(study.baseline_eens_kwh / 1000.0,
                           study.best_eens_kwh / 1000.0,
                           study.improvement_percent,
                           study.total_selected)
            switch_fa = str(st.get("switch_type_fa", "کلید")).split(" (")[0]
            method_fa = str(st.get("method_fa", "")).split(" — ")[0]
            numbers = _ltr(
                f"EENS {study.baseline_eens_kwh / 1000.0:,.2f} → "
                f"{study.best_eens_kwh / 1000.0:,.2f} MWh/yr")
            self.status.setText(
                f"پایان — {switch_fa} · روش {method_fa}\n"
                f"{numbers} · کاهش "
                f"{_ltr(f'{study.improvement_percent:.2f}٪')} · "
                f"{study.total_selected} کلید پیشنهادی")
            self._relayout_inputs()

        def _auto_rates_text_set(self, settings_dict: dict | None) -> None:
            if self.current_method() == "manual":
                text = "روش دستی — λ و r از فیلدهای بالا خوانده می‌شود."
            else:
                text = self._auto_rates_text(settings_dict)
            self.lbl_auto_info.setText(text)
            self.lbl_auto_info.setVisible(bool(text))

        # --------------------------------------------------------------
        def show_persisted(self, payload: dict | None) -> None:
            """نمایش نتیجهٔ ذخیره‌شده در پروژه (پس از بازکردن پروژه)."""
            data = dict(payload or {})
            study = dict(data.get("study") or {})
            rows_data = list(study.get("summary_rows") or [])
            fill_table(self.summary_table, SUMMARY_HEADERS,
                       [self._summary_row(r) for r in rows_data])
            self._fit_columns(self.summary_table)

            by_feeder = {str(r.get("feeder_key")): r for r in rows_data}
            res_rows = []
            self._selected_nodes = []
            for f in study.get("feeders") or []:
                best = (f.get("best") or {})
                chosen_cs = best.get("selected") or []
                row = by_feeder.get(str(f.get("feeder_key")), {})
                for c in chosen_cs:
                    res_rows.append(self._result_row(
                        str(f.get("feeder_key", "")), c, row))
                    self._selected_nodes.append(str(c.get("node")))
            fill_table(self.results_table, RESULT_HEADERS, res_rows)
            self._fit_columns(self.results_table)

            flat = []
            for f in study.get("feeders") or []:
                chosen = {c.get("node") for c in
                          ((f.get("best") or {}).get("selected") or [])}
                for c in f.get("candidates") or []:
                    flat.append(dict(c, feeder_key=str(f.get("feeder_key", "")),
                                     selected=c.get("node") in chosen))
            det, shown, total = self._detail_rows(flat)
            fill_table(self.detail_table, DETAIL_HEADERS, det)
            self._fit_columns(self.detail_table)
            self._set_markdown_panel(
                str(data.get("markdown") or study.get("markdown") or
                    "نتیجهٔ ذخیره‌شدهٔ این پروژه یافت شد."))
            self.btn_map.setEnabled(bool(self._selected_nodes))
            self._auto_rates_text_set(study.get("settings") or {})
            total_base = sum(float(r.get("baseline_eens_mwh") or 0)
                             for r in rows_data) or None
            total_best = sum(float(r.get("best_eens_mwh") or 0)
                             for r in rows_data) or None
            reduction = None
            if total_base:
                reduction = (total_base - (total_best or 0)) / total_base * 100
            self._set_kpis(total_base, total_best, reduction,
                           len(self._selected_nodes))
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
