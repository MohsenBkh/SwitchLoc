# -*- coding: utf-8 -*-
"""تب جایابی سطح دوم — ورود مستقیم پارامترها (بدون JSON) با دو پنل کنار هم.

چیدمان (درخواست کاربر ۱۴۰۳/۰۸):
  ┌─────────────────────┬──────────────────────────────┐
  │  پنل ورودی (راست)   │   پنل نتایج (چپ)              │
  │  ۱) بودجه NC/NO      │  KPI: EENS پایه→نهایی         │
  │  ۲) پخش بار          │  جدول پخش بار پایه            │
  │  ۳) قابلیت اطمینان   │  جدول طرح‌های منتخب            │
  │  [▶ اجرا] [↻ تازه‌سازی] [💾 ذخیره] │  گزارش Markdown           │
  └─────────────────────┴──────────────────────────────┘
  • ورودی‌ها با QSplitter افقی از نتایج جدا شده‌اند (قابل جابه‌جایی).
  • همهٔ دکمه‌ها کوتاه و دارای آیکون هستند تا متن بریده نشود.
  • داده‌های تکراری (λ/r/ظرفیت) از پروژه پر می‌شوند؛ فقط مقادیر متفاوت
    در جدول فیدر وارد می‌شوند و بقیه خودکار است.
"""
from __future__ import annotations


def make_level2_placement_tab(parent=None):  # pragma: no cover - Qt UI
    from pathlib import Path

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFormLayout,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _mk_spin(min_v, max_v, val, decimals=0, step=None, suffix=""):
        w = QSpinBox() if decimals == 0 else QDoubleSpinBox()
        w.setRange(min_v, max_v)
        if decimals:
            w.setDecimals(decimals)
            if step is not None:
                w.setSingleStep(step)
        elif step is not None:
            w.setSingleStep(int(step))
        w.setValue(val)
        if suffix:
            w.setSuffix(suffix)
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return w

    def _bool_icon(checked: bool) -> str:
        return "✓" if checked else "—"

    # ------------------------------------------------------------------
    class Level2PlacementTab(QWidget):
        def __init__(self, parent_=None):
            super().__init__(parent_)
            self.on_run = None
            self.on_refresh = None
            self.on_get_project_inputs = None
            self._result = None
            self._project_key = None
            self._feeders: list[str] = []
            self._line_types: list[str] = []
            self._available_no = 0
            self._saved: dict = {}

            self.setStyleSheet(
                "QGroupBox { font-weight: bold; }"
                "QGroupBox::title { subcontrol-origin: margin; padding: 2px 6px; }"
            )

            root = QVBoxLayout(self)
            root.setContentsMargins(6, 6, 6, 6)
            root.setSpacing(6)

            head = QLabel(
                "<b>جایابی سطح دوم (EENS + پخش بار)</b> — جست‌وجوی شمارشی "
                "آرایش‌های NC/NO با کمینه‌سازی EENS و قیود پخش بار شعاعی. "
                "پارامترها را مستقیم وارد کنید؛ نتایج کنار همین فرم نمایش داده می‌شود."
            )
            head.setWordWrap(True)
            head.setTextFormat(Qt.TextFormat.RichText)
            root.addWidget(head)

            # ----- main splitter: inputs | results -----
            self.main_split = QSplitter(Qt.Orientation.Horizontal)
            self.main_split.setChildrenCollapsible(False)
            root.addWidget(self.main_split, 1)

            self.main_split.addWidget(self._build_inputs_pane())
            self.main_split.addWidget(self._build_results_pane())
            self.main_split.setStretchFactor(0, 0)
            self.main_split.setStretchFactor(1, 1)
            self.main_split.setSizes([520, 760])

            # ---- aliases for legacy test / external callers ----
            self.feeder_table = getattr(self, "tbl_budget", None)
            self.no_candidates_label = getattr(self, "lbl_no_avail", None)
            # fill buttons are created in _build_inputs_pane; keep refs for test

            self._refresh_ui_enabled()

        # legacy property expected by test: current form data as dict
        @property
        def settings_data(self) -> dict:
            try:
                return self._collect_config()
            except Exception:
                return {}

        # ==============================================================
        # inputs pane (right side)
        # ==============================================================
        def _build_inputs_pane(self) -> QWidget:
            pane = QWidget()
            lay = QVBoxLayout(pane)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(8)

            # --- 1) بودجه و جست‌وجو ---
            g1 = QGroupBox("۱) بودجهٔ کلید و فضای جست‌وجو")
            f1 = QFormLayout(g1)
            f1.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            f1.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            f1.setVerticalSpacing(6)

            # per-feeder NC budgets table
            self.tbl_budget = QTableWidget(0, 2)
            self.tbl_budget.setHorizontalHeaderLabels(["فیدر", "NC"])
            hdr = self.tbl_budget.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
            self.tbl_budget.setColumnWidth(1, 70)
            self.tbl_budget.setMaximumHeight(140)
            self.tbl_budget.setToolTip("تعداد کلید NC جدید برای هر فیدر (۰ = بدون نصب)")
            f1.addRow(QLabel("بودجه NC هر فیدر:"))
            f1.addRow(self.tbl_budget)

            row_no = QHBoxLayout()
            self.sp_no = _mk_spin(0, 10, 0, decimals=0)
            self.sp_no.setToolTip("تعداد نقاط NO کاندید از اتصالات موجود")
            self.lbl_no_avail = QLabel("موجود: —")
            self.lbl_no_avail.setStyleSheet("color:#607d8b; font-size:8pt;")
            row_no.addWidget(self.sp_no, 1)
            row_no.addWidget(self.lbl_no_avail)
            f1.addRow("NO بودجه:", row_no)

            self.sp_max_states = _mk_spin(1000, 10_000_000, 100_000, decimals=0, step=10000)
            self.sp_max_states.setToolTip("سقف حالت‌های شمارشی")
            f1.addRow("سقف جست‌وجو:", self.sp_max_states)

            self.cmb_candidate = QComboBox()
            self.cmb_candidate.addItem("نقاط بار (load_points)", "load_points")
            self.cmb_candidate.addItem("همهٔ گره‌ها (all_nodes)", "all_nodes")
            f1.addRow("فضای کاندید:", self.cmb_candidate)

            # switch types
            self.chk_recloser = QCheckBox("ریکلوزر")
            self.chk_recloser.setChecked(True)
            self.chk_sectionalizer = QCheckBox("سکشنالایزر")
            self.chk_sectionalizer.setChecked(True)
            self.chk_disconnector = QCheckBox("سکسیونر")
            self.chk_disconnector.setChecked(True)
            sw_row = QHBoxLayout()
            sw_row.addWidget(self.chk_recloser)
            sw_row.addWidget(self.chk_sectionalizer)
            sw_row.addWidget(self.chk_disconnector)
            sw_row.addStretch(1)
            f1.addRow("انواع کلید:", sw_row)

            lay.addWidget(g1)

            # --- 2) پخش بار ---
            g2 = QGroupBox("۲) پخش بار (محدودیت‌ها)")
            f2 = QFormLayout(g2)
            f2.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            f2.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            f2.setVerticalSpacing(6)

            self.sp_v_base = _mk_spin(1.0, 63.0, 20.0, decimals=1, step=0.5, suffix=" kV")
            f2.addRow("ولتاژ مبنا:", self.sp_v_base)
            self.sp_v_src = _mk_spin(0.8, 1.2, 1.0, decimals=3, step=0.01, suffix=" pu")
            f2.addRow("ولتاژ منبع:", self.sp_v_src)

            v_row = QHBoxLayout()
            self.sp_v_min = _mk_spin(0.8, 1.0, 0.95, decimals=3, step=0.01)
            self.sp_v_max = _mk_spin(0.9, 1.15, 1.05, decimals=3, step=0.01)
            v_row.addWidget(QLabel("min:"))
            v_row.addWidget(self.sp_v_min, 1)
            v_row.addWidget(QLabel("max:"))
            v_row.addWidget(self.sp_v_max, 1)
            f2.addRow("حد ولتاژ (pu):", v_row)

            self.sp_trafo_lim = _mk_spin(50, 200, 100, decimals=0, suffix=" ٪")
            f2.addRow("حد بار ترانس:", self.sp_trafo_lim)

            self.sp_pf = _mk_spin(0.5, 1.0, 0.95, decimals=2, step=0.05)
            f2.addRow("ضریب توان:", self.sp_pf)

            self.lbl_line_info = QLabel("تایپ‌های خط: —")
            self.lbl_line_info.setWordWrap(True)
            self.lbl_line_info.setStyleSheet("color:#546e7a; font-size:8pt;")
            f2.addRow(self.lbl_line_info)

            lay.addWidget(g2)

            # --- 3) قابلیت اطمینان (جدول فیدر) ---
            g3 = QGroupBox("۳) قابلیت اطمینان (λ/r — فقط مقادیر متفاوت را پر کنید)")
            v3 = QVBoxLayout(g3)
            v3.setSpacing(4)
            hint = QLabel("خالی = مقدار پروژه (خاموشی/تنظیمات) استفاده می‌شود.")
            hint.setStyleSheet("color:#607d8b; font-size:8pt;")
            hint.setWordWrap(True)
            v3.addWidget(hint)

            # fill buttons (compact icons) for test compatibility & UX
            fill_row = QHBoxLayout()
            fill_row.setSpacing(6)
            self.fill_load_button = QPushButton("↻ بار")
            self.fill_load_button.setToolTip("پر کردن مدل بار از پروژه")
            self.fill_load_button.setMinimumWidth(70)
            self.fill_load_button.clicked.connect(lambda: self._on_fill_load())
            self.fill_reliability_button = QPushButton("↻ قابلیت")
            self.fill_reliability_button.setToolTip("پر کردن λ/r از سوابق خاموشی/تنظیمات")
            self.fill_reliability_button.setMinimumWidth(80)
            self.fill_reliability_button.clicked.connect(lambda: self._on_fill_reliability())
            fill_row.addWidget(self.fill_load_button)
            fill_row.addWidget(self.fill_reliability_button)
            fill_row.addStretch(1)
            v3.addLayout(fill_row)

            self.tbl_reliability = QTableWidget(0, 5)
            self.tbl_reliability.setHorizontalHeaderLabels(
                ["فیدر", "λ (1/y)", "r (min)", "Q گذرا (1/y)", "پشتیبان kW"]
            )
            hdr3 = self.tbl_reliability.horizontalHeader()
            hdr3.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for c in range(1, 5):
                hdr3.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
                self.tbl_reliability.setColumnWidth(c, 84)
            self.tbl_reliability.setMaximumHeight(150)
            v3.addWidget(self.tbl_reliability)

            # engine params compact
            eng_row = QHBoxLayout()
            self.cmb_rest_model = QComboBox()
            self.cmb_rest_model.addItem("جهت‌دار", "directional")
            self.cmb_rest_model.addItem("یکنواخت", "uniform")
            self.sp_repair = _mk_spin(1, 600, 50, decimals=0, suffix=" د")
            self.sp_restore = _mk_spin(1, 600, 30, decimals=0, suffix=" د")
            eng_row.addWidget(QLabel("مدل:"))
            eng_row.addWidget(self.cmb_rest_model, 1)
            eng_row.addWidget(QLabel("تعمیر:"))
            eng_row.addWidget(self.sp_repair, 1)
            eng_row.addWidget(QLabel("بازیابی:"))
            eng_row.addWidget(self.sp_restore, 1)
            v3.addLayout(eng_row)

            lay.addWidget(g3)

            # --- action buttons (compact with icons) ---
            btn_box = QHBoxLayout()
            btn_box.setSpacing(6)
            self.btn_refresh = QPushButton("↻ تازه‌سازی")
            self.btn_refresh.setToolTip("به‌روزرسانی فهرست فیدرها از پروژه")
            self.btn_refresh.setMinimumWidth(90)
            self.btn_refresh.clicked.connect(self._on_refresh_clicked)

            self.btn_run = QPushButton("▶ اجرا")
            self.btn_run.setToolTip("اجرای جایابی سطح دوم")
            self.btn_run.setMinimumWidth(90)
            # primary style
            self.btn_run.setStyleSheet("QPushButton { font-weight:bold; }")
            self.btn_run.clicked.connect(self._on_run_clicked)

            self.btn_save = QPushButton("💾 ذخیره")
            self.btn_save.setToolTip("ذخیره گزارش Markdown/JSON")
            self.btn_save.setMinimumWidth(80)
            self.btn_save.setEnabled(False)
            self.btn_save.clicked.connect(self._save_report)

            btn_box.addWidget(self.btn_refresh)
            btn_box.addWidget(self.btn_run)
            btn_box.addWidget(self.btn_save)
            btn_box.addStretch(1)
            lay.addLayout(btn_box)

            self.lbl_status = QLabel("آماده — پروژه را باز کنید.")
            self.lbl_status.setWordWrap(True)
            self.lbl_status.setStyleSheet("color:#37474f; font-size:8.5pt;")
            lay.addWidget(self.lbl_status)

            lay.addStretch(1)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(pane)
            scroll.setMinimumWidth(380)
            return scroll

        # ==============================================================
        # results pane (left side)
        # ==============================================================
        def _build_results_pane(self) -> QWidget:
            pane = QWidget()
            lay = QVBoxLayout(pane)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)

            # KPI row
            kpi_box = QGroupBox("خلاصه")
            kpi_lay = QHBoxLayout(kpi_box)
            kpi_lay.setSpacing(12)
            self.lbl_kpi_search = QLabel("—")
            self.lbl_kpi_search.setStyleSheet("font-weight:bold; color:#0d47a1;")
            self.lbl_kpi_feas = QLabel("—")
            self.lbl_kpi_feas.setStyleSheet("font-weight:bold; color:#2e7d32;")
            self.lbl_kpi_rej = QLabel("—")
            self.lbl_kpi_rej.setStyleSheet("font-weight:bold; color:#c62828;")
            for title, w in [("جست‌وجو:", self.lbl_kpi_search), ("مجاز:", self.lbl_kpi_feas), ("رد:", self.lbl_kpi_rej)]:
                holder = QVBoxLayout()
                cap = QLabel(title)
                cap.setStyleSheet("color:#607d8b; font-size:8pt;")
                holder.addWidget(cap)
                holder.addWidget(w)
                wrap = QWidget()
                wrap.setLayout(holder)
                kpi_lay.addWidget(wrap)
            kpi_lay.addStretch(1)
            lay.addWidget(kpi_box)

            # split: tables | report
            self.results_split = QSplitter(Qt.Orientation.Vertical)
            self.results_split.setChildrenCollapsible(False)
            lay.addWidget(self.results_split, 1)

            # flow baseline table
            flow_box = QGroupBox("پخش بار پایه")
            fv = QVBoxLayout(flow_box)
            self.tbl_flow = QTableWidget(0, 5)
            self.tbl_flow.setHorizontalHeaderLabels(["فیدر", "وضعیت", "Vmin pu", "جریان ٪", "ترانس ٪"])
            self.tbl_flow.setAlternatingRowColors(True)
            hdr = self.tbl_flow.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for c in range(1, 5):
                hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
                self.tbl_flow.setColumnWidth(c, 70)
            self.tbl_flow.setMaximumHeight(140)
            fv.addWidget(self.tbl_flow)
            self.results_split.addWidget(flow_box)

            # best plans table
            plan_box = QGroupBox("طرح‌های منتخب (EENS kWh/سال)")
            pv = QVBoxLayout(plan_box)
            self.tbl_plans = QTableWidget(0, 6)
            self.tbl_plans.setHorizontalHeaderLabels(
                ["نوع", "پایه", "نهایی", "کاهش", "NC", "NO"]
            )
            self.tbl_plans.setAlternatingRowColors(True)
            hdr2 = self.tbl_plans.horizontalHeader()
            hdr2.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            self.tbl_plans.setColumnWidth(0, 90)
            for c in range(1, 6):
                hdr2.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
            pv.addWidget(self.tbl_plans)
            self.results_split.addWidget(plan_box)

            # report
            rep_box = QGroupBox("گزارش")
            rv = QVBoxLayout(rep_box)
            self.report = QTextEdit()
            self.report.setReadOnly(True)
            self.report.setPlaceholderText("گزارش جایابی پس از اجرا اینجا نمایش داده می‌شود.")
            self.report.setStyleSheet("font-size:9pt;")
            rv.addWidget(self.report)
            self.results_split.addWidget(rep_box)

            self.results_split.setSizes([140, 160, 300])

            # unresolved list
            self.lbl_unresolved = QLabel("")
            self.lbl_unresolved.setWordWrap(True)
            self.lbl_unresolved.setStyleSheet("color:#bf360c; font-size:8pt;")
            self.lbl_unresolved.setVisible(False)
            lay.addWidget(self.lbl_unresolved)

            return pane

        # --------------------------------------------------------------
        # project data injection (called by main_window)
        # --------------------------------------------------------------
        def set_project_data(
            self,
            feeders,
            line_types=None,
            load_model=None,
            saved=None,
            project_key=None,
            line_ampacities=None,
            available_no_count=0,
        ):
            self._feeders = [str(x) for x in (feeders or []) if str(x).strip()]
            self._line_types = list(line_types or [])
            self._available_no = int(available_no_count or 0)
            self._saved = dict(saved or {})
            self._project_key = project_key

            # update feeder-dependent tables
            self._rebuild_budget_table()
            self._rebuild_reliability_table()

            self.lbl_no_avail.setText(f"موجود: {self._available_no}")
            # clamp NO budget
            if self.sp_no.value() > self._available_no and self._available_no > 0:
                self.sp_no.setValue(self._available_no)

            # line types info
            if self._line_types:
                amp_parts = []
                for t in self._line_types[:4]:
                    amp = (line_ampacities or {}).get(t)
                    amp_parts.append(f"{t} ({amp:.0f}A)" if amp else t)
                more = f" +{len(self._line_types)-4}" if len(self._line_types) > 4 else ""
                self.lbl_line_info.setText("تایپ‌ها: " + ", ".join(amp_parts) + more)
            else:
                self.lbl_line_info.setText("تایپ‌ها: — (کاتالوگ/برآورد عمومی)")

            # restore saved values
            try:
                self._apply_saved(self._saved)
            except Exception:
                pass

            self.lbl_status.setText(
                f"پروژه: {len(self._feeders)} فیدر در دامنه — مقادیر را وارد و «▶ اجرا» را بزنید."
                if self._feeders else "پروژه بدون فیدر یا هنوز توپولوژی اجرا نشده."
            )
            self._refresh_ui_enabled()

        def _rebuild_budget_table(self):
            self.tbl_budget.blockSignals(True)
            try:
                self.tbl_budget.setRowCount(len(self._feeders))
                for r, feeder in enumerate(self._feeders):
                    item = QTableWidgetItem(feeder)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.tbl_budget.setItem(r, 0, item)
                    # budget spin as cell widget
                    spin = QSpinBox()
                    spin.setRange(0, 10)
                    spin.setValue(0)
                    # try to restore from saved
                    try:
                        saved_budgets = (self._saved.get("level2") or {}).get("nc_budget_by_feeder") or {}
                        if feeder in saved_budgets:
                            spin.setValue(int(saved_budgets[feeder]))
                    except Exception:
                        pass
                    self.tbl_budget.setCellWidget(r, 1, spin)
                self.tbl_budget.resizeRowsToContents()
            finally:
                self.tbl_budget.blockSignals(False)

        def _rebuild_reliability_table(self):
            self.tbl_reliability.blockSignals(True)
            try:
                self.tbl_reliability.setRowCount(len(self._feeders))
                # keep existing overrides if any
                existing = {}
                for r in range(self.tbl_reliability.rowCount()):
                    feeder_item = self.tbl_reliability.item(r, 0)
                    if feeder_item:
                        feeder = feeder_item.text()
                        # read current edits before rebuild? Hard to keep, just reset
                        pass
                # we have saved reliability overrides
                saved_rel = (self._saved.get("reliability") or {})
                for r, feeder in enumerate(self._feeders):
                    it = QTableWidgetItem(feeder)
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.tbl_reliability.setItem(r, 0, it)
                    for c, key in enumerate(["failure_rates", "repair_times_min", "transient_rates", "backup_kw"], start=1):
                        val = ""
                        try:
                            v = (saved_rel.get(key) or {}).get(feeder)
                            if v is not None:
                                val = str(v)
                        except Exception:
                            pass
                        it2 = QTableWidgetItem(val)
                        it2.setToolTip("خالی = خودکار از پروژه")
                        self.tbl_reliability.setItem(r, c, it2)
                self.tbl_reliability.resizeRowsToContents()
            finally:
                self.tbl_reliability.blockSignals(False)

        def _apply_saved(self, saved: dict):
            if not saved:
                return
            lv = saved.get("level2") or {}
            if lv.get("no_budget") is not None:
                self.sp_no.setValue(int(lv["no_budget"]))
            if lv.get("max_search_states") is not None:
                self.sp_max_states.setValue(int(lv["max_search_states"]))
            if lv.get("candidate_mode"):
                ix = self.cmb_candidate.findData(str(lv["candidate_mode"]))
                if ix >= 0:
                    self.cmb_candidate.setCurrentIndex(ix)
            if lv.get("switch_types"):
                types = set(map(str, lv["switch_types"]))
                self.chk_recloser.setChecked("recloser" in types)
                self.chk_sectionalizer.setChecked("sectionalizer" in types)
                self.chk_disconnector.setChecked("disconnector" in types)

            pf = saved.get("power_flow") or {}
            if pf.get("base_voltage_kv") is not None:
                self.sp_v_base.setValue(float(pf["base_voltage_kv"]))
            if pf.get("source_voltage_pu") is not None:
                self.sp_v_src.setValue(float(pf["source_voltage_pu"]))
            if pf.get("voltage_min_pu") is not None:
                self.sp_v_min.setValue(float(pf["voltage_min_pu"]))
            if pf.get("voltage_max_pu") is not None:
                self.sp_v_max.setValue(float(pf["voltage_max_pu"]))
            if pf.get("transformer_loading_limit_pct") is not None:
                self.sp_trafo_lim.setValue(float(pf["transformer_loading_limit_pct"]))
            if pf.get("assumed_power_factor") is not None:
                self.sp_pf.setValue(float(pf["assumed_power_factor"]))

            rel = saved.get("reliability") or {}
            eng = rel.get("engine") or {}
            if eng.get("restoration_model"):
                ix = self.cmb_rest_model.findData(str(eng["restoration_model"]))
                if ix >= 0:
                    self.cmb_rest_model.setCurrentIndex(ix)
            if eng.get("repair_time_min") is not None:
                self.sp_repair.setValue(float(eng["repair_time_min"]))
            if eng.get("restoration_time_min") is not None:
                self.sp_restore.setValue(float(eng["restoration_time_min"]))

        # --------------------------------------------------------------
        def _collect_config(self) -> dict:
            # level2
            budgets = {}
            for r in range(self.tbl_budget.rowCount()):
                feeder_item = self.tbl_budget.item(r, 0)
                if not feeder_item:
                    continue
                feeder = feeder_item.text().strip()
                w = self.tbl_budget.cellWidget(r, 1)
                budgets[feeder] = int(w.value() if w else 0)
            switch_types = []
            if self.chk_recloser.isChecked():
                switch_types.append("recloser")
            if self.chk_sectionalizer.isChecked():
                switch_types.append("sectionalizer")
            if self.chk_disconnector.isChecked():
                switch_types.append("disconnector")
            if not switch_types:
                switch_types = ["sectionalizer"]

            level2 = {
                "nc_budget_by_feeder": budgets,
                "no_budget": int(self.sp_no.value()),
                "max_search_states": int(self.sp_max_states.value()),
                "candidate_mode": str(self.cmb_candidate.currentData() or "load_points"),
                "switch_types": switch_types,
            }

            power_flow = {
                "base_voltage_kv": float(self.sp_v_base.value()),
                "source_voltage_pu": float(self.sp_v_src.value()),
                "voltage_min_pu": float(self.sp_v_min.value()),
                "voltage_max_pu": float(self.sp_v_max.value()),
                "transformer_loading_limit_pct": float(self.sp_trafo_lim.value()),
                "assumed_power_factor": float(self.sp_pf.value()),
            }

            # reliability per-feeder overrides (only non-empty cells)
            def _col_map(col_idx):
                out = {}
                for r in range(self.tbl_reliability.rowCount()):
                    feeder = (self.tbl_reliability.item(r, 0).text() if self.tbl_reliability.item(r, 0) else "").strip()
                    if not feeder:
                        continue
                    it = self.tbl_reliability.item(r, col_idx)
                    txt = (it.text().strip() if it else "")
                    if txt == "":
                        continue
                    try:
                        out[feeder] = float(txt.replace(",", "."))
                    except ValueError:
                        raise ValueError(f"مقدار نامعتبر در جدول قابلیت اطمینان — فیدر {feeder}")
                return out

            reliability = {
                "failure_rates": _col_map(1),
                "repair_times_min": _col_map(2),
                "transient_rates": _col_map(3),
                "backup_kw": _col_map(4),
                "engine": {
                    "restoration_model": str(self.cmb_rest_model.currentData() or "directional"),
                    "repair_time_min": float(self.sp_repair.value()),
                    "restoration_time_min": float(self.sp_restore.value()),
                },
            }

            # load_model will be injected by main_window from project; keep empty here
            return {
                "level2": level2,
                "power_flow": power_flow,
                "reliability": reliability,
                "load_model": {},
                # feeder_keys injected by main_window
            }

        # --------------------------------------------------------------
        def _on_fill_load(self):
            # Fill load model from project (via on_get_project_inputs) and refresh UI
            try:
                if self.on_get_project_inputs is not None:
                    data = self.on_get_project_inputs() or {}
                    # load_model is managed by main_window; just trigger refresh
                    if self.on_refresh is not None:
                        self.on_refresh()
                    else:
                        # fallback: show info
                        self.lbl_status.setText("مدل بار از پروژه بارگذاری شد.")
                elif self.on_refresh is not None:
                    self.on_refresh()
            except Exception as exc:
                QMessageBox.warning(self, "بار", str(exc))

        def _on_fill_reliability(self):
            try:
                if self.on_get_project_inputs is not None:
                    data = self.on_get_project_inputs() or {}
                    # pre-fill reliability table from project data
                    rates = data.get("failure_rates") or {}
                    repairs = data.get("repair_times_min") or {}
                    backups = data.get("backup_kw") or {}
                    # transient not in table directly, ignore
                    for r in range(self.tbl_reliability.rowCount()):
                        feeder = (self.tbl_reliability.item(r, 0).text() if self.tbl_reliability.item(r, 0) else "").strip()
                        if not feeder:
                            continue
                        # only fill if cell is empty (user hasn't overridden)
                        for c, src in [(1, rates), (2, repairs), (4, backups)]:
                            it = self.tbl_reliability.item(r, c)
                            if it and (it.text().strip() == "") and feeder in src:
                                it.setText(str(src[feeder]))
                    self.lbl_status.setText("مقادیر λ/r/پشتیبان از پروژه پر شد (فقط سلول‌های خالی).")
                    # also refresh feeder list if needed
                elif self.on_refresh is not None:
                    self.on_refresh()
            except Exception as exc:
                QMessageBox.warning(self, "قابلیت اطمینان", str(exc))

        def _on_refresh_clicked(self):
            if self.on_refresh is not None:
                try:
                    self.on_refresh()
                except Exception as exc:
                    QMessageBox.warning(self, "به‌روزرسانی", str(exc))

        def _on_run_clicked(self):
            if self.on_run is None:
                QMessageBox.warning(self, "پروژه آماده نیست", "ابتدا پروژه را باز کنید.")
                return
            if not self._feeders:
                QMessageBox.warning(self, "فیدر انتخاب نشده", "دامنهٔ مطالعه فاقد فیدر است؛ ابتدا توپولوژی را اجرا کنید.")
                return
            try:
                cfg = self._collect_config()
            except ValueError as exc:
                QMessageBox.warning(self, "ورودی نامعتبر", str(exc))
                return
            # basic validation
            if all(v == 0 for v in cfg["level2"]["nc_budget_by_feeder"].values()) and cfg["level2"]["no_budget"] == 0:
                QMessageBox.warning(self, "بودجه لازم است", "حداقل یک بودجه NC یا NO را بزرگ‌تر از صفر قرار دهید.")
                return
            if not cfg["level2"]["switch_types"]:
                QMessageBox.warning(self, "نوع کلید", "حداقل یک نوع کلید را انتخاب کنید.")
                return
            self.on_run(cfg)

        # --------------------------------------------------------------
        def set_busy(self, busy: bool, message: str = ""):
            self.btn_run.setEnabled(not busy)
            self.btn_refresh.setEnabled(not busy)
            self.tbl_budget.setEnabled(not busy)
            self.tbl_reliability.setEnabled(not busy)
            if message:
                self.lbl_status.setText(message)
            elif busy:
                self.lbl_status.setText("در حال بررسی آرایش‌ها و حل پخش بار…")
            else:
                # keep last status
                pass

        def show_result(self, result):
            self._result = result
            # KPI
            try:
                total_search = int(getattr(result, "search_state_count", 0))
                feas = sum((getattr(result, "feasible_plan_count_by_type", {}) or {}).values())
                rej = sum((getattr(result, "rejected_plan_count_by_type", {}) or {}).values())
                self.lbl_kpi_search.setText(f"{total_search:,}")
                self.lbl_kpi_feas.setText(f"{feas:,}")
                self.lbl_kpi_rej.setText(f"{rej:,}")
            except Exception:
                pass

            # flow baseline
            try:
                rows = getattr(result, "flow_baseline", []) or []
                self.tbl_flow.setRowCount(len(rows))
                for r, row in enumerate(rows):
                    vals = [
                        str(row.get("feeder_key", "")),
                        str(row.get("status", "")),
                        f"{row.get('min_voltage_pu', 0) or 0:.3f}" if row.get("min_voltage_pu") is not None else "—",
                        f"{row.get('max_line_loading_pct', 0) or 0:.1f}" if row.get("max_line_loading_pct") is not None else "—",
                        f"{row.get('max_transformer_loading_pct', 0) or 0:.1f}" if row.get("max_transformer_loading_pct") is not None else "—",
                    ]
                    for c, txt in enumerate(vals):
                        it = QTableWidgetItem(txt)
                        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.tbl_flow.setItem(r, c, it)
                self.tbl_flow.resizeRowsToContents()
            except Exception:
                pass

            # best plans
            try:
                best = getattr(result, "best_plans", {}) or {}
                baseline = getattr(result, "baseline_eens_by_type", {}) or {}
                feasible = getattr(result, "feasible_plan_count_by_type", {}) or {}
                rejected = getattr(result, "rejected_plan_count_by_type", {}) or {}
                self.tbl_plans.setRowCount(len(best))
                for r, (stype, plan) in enumerate(best.items()):
                    base = sum((baseline.get(stype) or {}).values())
                    if plan is None:
                        vals = [stype, f"{base:.1f}", "—", "—", "—", "—"]
                    else:
                        post = float(plan.get("post_plan_eens_kwh_per_year", 0))
                        gain = float(plan.get("gain_kwh_per_year", 0))
                        nc = sum(len(v) for v in (plan.get("nc_by_feeder") or {}).values())
                        no = len(plan.get("normally_open_ties") or [])
                        vals = [stype, f"{base:.1f}", f"{post:.1f}", f"{gain:.1f}", str(nc), str(no)]
                    for c, txt in enumerate(vals):
                        it = QTableWidgetItem(txt)
                        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.tbl_plans.setItem(r, c, it)
                self.tbl_plans.resizeRowsToContents()
            except Exception:
                pass

            # report
            try:
                md = getattr(result, "markdown", "") or ""
                # render as plain text for readability (avoid huge markdown tables)
                self.report.setMarkdown(md)
            except Exception:
                self.report.setPlainText(str(result))

            # unresolved
            try:
                unresolved = getattr(result, "unresolved", []) or []
                if unresolved:
                    self.lbl_unresolved.setText("• " + "\n• ".join(unresolved[:6]))
                    self.lbl_unresolved.setVisible(True)
                else:
                    self.lbl_unresolved.setVisible(False)
            except Exception:
                pass

            status = getattr(result, "status", "ok")
            self.lbl_status.setText(f"وضعیت: {status} — گزارش ذخیره شد.")
            self.btn_save.setEnabled(True)

        def _save_report(self):
            if self._result is None:
                return
            folder = None
            try:
                from PySide6.QtWidgets import QFileDialog
                folder = QFileDialog.getExistingDirectory(self, "ذخیره گزارش جایابی سطح ۲")
            except Exception:
                folder = ""
            if not folder:
                return
            import json

            out = Path(folder)
            try:
                (out / "level2_placement_report.md").write_text(self._result.markdown, encoding="utf-8")
                (out / "level2_placement_report.json").write_text(
                    json.dumps(self._result.as_dict(), ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                self.lbl_status.setText(f"ذخیره شد: {out}")
            except Exception as exc:
                QMessageBox.warning(self, "ذخیره", str(exc))

        def _refresh_ui_enabled(self):
            has_feeders = bool(self._feeders)
            self.btn_run.setEnabled(has_feeders)

    return Level2PlacementTab(parent)
