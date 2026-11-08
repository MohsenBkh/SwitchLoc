# -*- coding: utf-8 -*-
"""Engineering settings dialog (نیاز ۱۲ — تنظیمات مهندسی در GUI).

One dialog, five pages — every page edits a plain dict; the caller
applies the dict to the engine settings (the dialog itself holds no
engineering logic, same split as dashboard_tab):

  * Load model (نیاز ۱۱)   — level + loading/substitute factors
  * Feeder capacity (نیاز ۹) — nominal / peak / emergency per feeder
  * Costs                    — NC / NO / automation / rial-per-kWh /
    switching minutes (company policy, logged)
  * Acceptance criteria (نیاز ۱۰) — ΔENS thresholds, caps, budget
  * Data coverage (نیاز ۸)   — explicit coverage window + forced /
    excluded months (the «missing months ≠ no outage» control)

The dialog is created by `make_settings_dialog` so the module imports
safely without Qt (the Qt-free `CAPACITY_COLUMNS` / defaults stay
testable).
"""
from __future__ import annotations

from ...reliability.load_model import (DEFAULT_LOADING_FACTOR,
                                       DEFAULT_SUBSTITUTE_FACTOR, LEVELS,
                                       LEVEL_FA, LEVEL_SCALED)
from .main_window import _fmt_exc, _write_log

CAPACITY_COLUMNS = ("Feeder", "Nominal kW", "Peak kW (خودکار از مدل بار)",
                    "Emergency kW", "Note")


def default_capacity_rows(feeder_keys) -> list[dict]:
    """New feeder rows: همهٔ ظرفیت‌ها نامعلوم می‌مانند تا مهندس وارد کند.

    مقدار پیش‌فرضِ ساختگی (۷۰۰۰ kW) عمداً حذف شد — هیچ مقدار پیش‌فرضی به‌عنوان
    ظرفیت تأییدشدهٔ مهندس به‌کار نمی‌رود.
    """
    return [{"feeder_key": k, "nominal_kw": None,
             "peak_kw": None, "peak_source": "unknown",
             "emergency_kw": None, "note": ""}
            for k in feeder_keys]


def _lookup_by_feeder(mapping: dict, key: str):
    """مقدار ذخیره‌شدهٔ فیدر با هر نگارشی («F3»/«F3 - KOSAR»)."""
    from ...topology.tracing import same_feeder
    if not mapping:
        return None
    if key in mapping:
        return mapping[key]
    hits = [k for k in mapping if same_feeder(k, key)]
    return mapping[hits[0]] if len(hits) == 1 else None


def parse_capacity_rows(table_rows) -> list[dict]:
    """Raw GUI rows → clean dicts (None for unknown, no silent zero)."""
    out = []
    for r in table_rows:
        def _f(v):
            if v is None:
                return None
            s = str(v).strip().replace(",", "")
            if s == "":
                return None
            try:
                return float(s)
            except ValueError:
                return None
        nominal = _f(r.get("nominal_kw"))
        peak = _f(r.get("peak_kw"))
        peak_src = str(r.get("peak_source", "unknown") or "unknown")
        if peak is None:
            peak_src = "unknown"
        out.append({"feeder_key": str(r.get("feeder_key", "")).strip().upper(),
                    "nominal_kw": nominal,
                    "nominal_source": "user" if nominal is not None else "unknown",
                    "peak_kw": peak,
                    "peak_source": peak_src,
                    "emergency_kw": _f(r.get("emergency_kw")),
                    "note": str(r.get("note", ""))})
    return out


def make_settings_dialog(parent, feeder_keys, current: dict,
                         feeder_s_rated: dict | None = None):  # pragma: no cover
    """Return the dialog instance; exec() + apply() by the caller.

    ``feeder_s_rated``: feeder_key → Σ S_rated [kVA] (از ترانس‌های GIS)
    — برای پیش‌نمایش زندهٔ محاسبات Load Scaling (K و cosφ) روی همان صفحه.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                   QDoubleSpinBox, QFormLayout, QHBoxLayout,
                                   QHeaderView, QLabel, QLineEdit, QTableWidget,
                                   QTableWidgetItem, QTabWidget, QVBoxLayout,
                                   QWidget)
    from .widgets import (EXPLAIN_QSS, fill_table, make_explain_label,
                          make_required_label)

    dlg = QDialog(parent)
    dlg.setWindowTitle("SwitchLoc — Engineering settings")
    dlg.setMinimumWidth(620)
    tabs = QTabWidget(dlg)
    lay = QVBoxLayout(dlg)
    lay.addWidget(tabs)

    cur = current or {}

    # -- 1) load model (نیاز ۱۱) -------------------------------------------
    page1 = QWidget(); f1 = QFormLayout(page1)
    cmb_level = QComboBox()
    for lv in LEVELS:
        cmb_level.addItem(LEVEL_FA[lv], lv)
    cmb_level.setCurrentIndex(
        LEVELS.index(cur.get("load_model", {}).get("level", LEVEL_SCALED)))
    sp_lf = QDoubleSpinBox(); sp_lf.setRange(0.05, 1.5); sp_lf.setSingleStep(0.05)
    sp_lf.setValue(float(cur.get("load_model", {}).get(
        "loading_factor", DEFAULT_LOADING_FACTOR)))
    sp_sf = QDoubleSpinBox(); sp_sf.setRange(0.05, 2.0); sp_sf.setSingleStep(0.1)
    sp_sf.setValue(float(cur.get("load_model", {}).get(
        "substitute_factor", DEFAULT_SUBSTITUTE_FACTOR)))
    f1.addRow(make_required_label("Active load-model level:"), cmb_level)
    f1.addRow("Loading factor (estimated level):", sp_lf)
    f1.addRow("Substitute factor (kVA≈kW level):", sp_sf)
    note1 = make_explain_label(
        "منشأ هر مقدار بار در خروجی (node_origin) ردیابی‌پذیر است؛ سطح "
        "«دقیق» فقط از بار واقعی استفاده می‌کند. سطح «مقیاس‌شده» "
        "(Load Scaling) بار (P، Q) هر فیدر را به نسبت ظرفیت نامی بین "
        "ترانس‌های همان فیدر توزیع می‌کند: K = S_load/ΣS_rated و "
        "P_T,i = K·S_rated,i·cosφ — جدول ورودی P/Q در پایین همین صفحه.")
    f1.addRow(note1)

    # -- 1b) Load Scaling — ورودی P/Q هر فیدر (روش جدید کاربر) --------------
    pq_cur = dict((cur.get("load_model", {}) or {}).get("feeder_pq") or {})
    s_rated = dict(feeder_s_rated or {})
    pq_headers = ["Feeder", "P_load (kW)*", "Q_load (kVAr)*",
                  "ΣS_rated (kVA)", "S_load (kVA)", "cos φ", "K"]
    pq_table = QTableWidget(len(feeder_keys), len(pq_headers))
    pq_table.setHorizontalHeaderLabels(pq_headers)
    pq_table.verticalHeader().setVisible(False)
    pq_table.horizontalHeader().setStretchLastSection(True)

    busy = {"on": False}

    def _pq_calc_row(i: int) -> None:
        """پیش‌نمایش زندهٔ S_load / cosφ / K از ورودی‌های P و Q.

        هر سه ستون **همیشه** از P و Q محاسبه می‌شوند (K فقط وقتی ΣS_rated
        فیدر معلوم باشد)؛ قبلاً مقدار اولیهٔ سلول‌ها به‌هم‌ریخته بود و مقادیر
        ذخیره‌شده هنگام بازکردن پنجره دوباره محاسبه نمی‌شدند.
        """
        import math
        if busy["on"]:
            return
        def _f(item):
            if item is None:
                return 0.0
            try:
                return float(item.text().strip().replace(",", "") or 0.0)
            except ValueError:
                return 0.0
        p = _f(pq_table.item(i, 1))
        q = _f(pq_table.item(i, 2))
        s_load = math.hypot(p, q)
        cos_phi = (p / s_load) if s_load > 0 else 0.0
        s_r = float(s_rated.get(feeder_keys[i], 0.0) or 0.0)
        k_scale = (s_load / s_r) if s_r > 0 else 0.0
        busy["on"] = True
        try:
            for col, val in ((4, f"{s_load:,.1f}" if (p or q) else "—"),
                             (5, f"{cos_phi:.4f}" if s_load else "—"),
                             (6, f"{k_scale:.5f}" if (s_r and (p or q)) else "—")):
                it = pq_table.item(i, col)
                if it is not None:
                    it.setText(val)
        finally:
            busy["on"] = False

    for i, k in enumerate(feeder_keys):
        pq = dict(_lookup_by_feeder(pq_cur, k) or {})
        it0 = QTableWidgetItem(k)
        it0.setFlags(it0.flags() & ~Qt.ItemFlag.ItemIsEditable)
        pq_table.setItem(i, 0, it0)
        pq_table.setItem(i, 1, QTableWidgetItem(
            f"{pq['p_kw']:g}" if pq.get("p_kw") is not None else ""))
        pq_table.setItem(i, 2, QTableWidgetItem(
            f"{pq['q_kvar']:g}" if pq.get("q_kvar") is not None else ""))
        it3 = QTableWidgetItem(f"{s_rated.get(k, 0.0):,.0f}")
        it3.setFlags(it3.flags() & ~Qt.ItemFlag.ItemIsEditable)
        pq_table.setItem(i, 3, it3)
        for col in (4, 5, 6):
            it = QTableWidgetItem("—")
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            pq_table.setItem(i, col, it)
    # پس از ساخت همهٔ ردیف‌ها، مقادیر ذخیره‌شده یک‌بار محاسبه می‌شوند و
    # سپس فقط یک اتصال برای ویرایش‌های بعدی ثبت می‌گردد (بدون سیگنال تودرتو).
    for i in range(len(feeder_keys)):
        _pq_calc_row(i)
    pq_table.itemChanged.connect(
        lambda it: _pq_calc_row(pq_table.row(it)))
    pq_table.setFixedHeight(min(360, 34 * (len(feeder_keys) + 1) + 12))
    f1.addRow(make_explain_label(
        "روش Load Scaling (سطح «مقیاس‌شده»): بار هر فیدر را وارد کنید "
        "(مثلاً پیک تابستان). نرم‌افزار S_load = √(P²+Q²)، "
        "cos φ = P/S_load، K = S_load/ΣS_rated و سپس "
        "P هر ترانس = K × S_rated × cos φ را محاسبه می‌کند. ستون‌های "
        "ستاره‌دار الزامی‌اند؛ فیدر بدون ورودی صفر می‌گیرد و هشدار صریح "
        "می‌سازد."))
    f1.addRow(pq_table)
    tabs.addTab(page1, "Load model")

    # -- 2) feeder capacity (نیاز ۹) ----------------------------------------
    page2 = QWidget(); v2 = QVBoxLayout(page2)
    cap_rows = {r["feeder_key"]: dict(r)
                for r in cur.get("capacity_rows", [])}
    cap_headers = ["Feeder*", "Nominal kW*",
                   "Peak kW (خوانده از مدل بار)", "Emergency kW*",
                   "Note"]
    tbl = QTableWidget(len(feeder_keys), len(cap_headers))
    tbl.setHorizontalHeaderLabels(cap_headers)
    tbl.verticalHeader().setVisible(False)
    tbl.horizontalHeader().setStretchLastSection(True)
    lpq_rows = ((cur.get("load_model", {}) or {}).get("feeder_pq", {})
                or {})
    lpq_now = {str(fk).strip().upper():
               float((v or {}).get("p_kw") or 0.0)
               for fk, v in lpq_rows.items()}
    for i, k in enumerate(feeder_keys):
        row = dict(_lookup_by_feeder(cap_rows, k) or {})
        # پیک از ورودی واحد مدل بار خوانده می‌شود — یک منبع، بدون ورودی موازی
        row["peak_kw"] = lpq_now.get(k) or None
        if row["peak_kw"] is None:
            row["peak_kw"] = row.get("peak_kw")  # مقدار ذخیره‌شده قبلی
        row.setdefault("emergency_kw", None)
        row.setdefault("note", "")
        tbl.setItem(i, 0, QTableWidgetItem(k))
        for j, key in ((1, "nominal_kw"), (2, "peak_kw"),
                       (3, "emergency_kw"), (4, "note")):
            v = row.get(key)
            cell = QTableWidgetItem("" if v is None else str(v))
            if j == 2:  # پیک ستون READ-ONLY: همگام خودکار با تب Load Model
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                v_txt = (f"{v:.1f} (از مدل بار)"
                         if isinstance(v, (int, float)) else
                         ("پیک نامعلوم — P را در تب Load Model وارد کنید"
                          if v is None else str(v)))
                cell.setText(v_txt)
            tbl.setItem(i, j, cell)
    tbl.setFixedHeight(min(360, 40 * (len(feeder_keys) + 1) + 12))
    v2.addWidget(make_explain_label(
        "ظرفیت نامی/اضطراری هر فیدر را مهندس وارد می‌کند؛ هیچ مقدار "
        "پیش‌فرض ساختگی وجود ندارد و مقادیر از GIS حدس زده نمی‌شوند. "
        "ستون «Peak kW» فقط نمایش است و از همان ورودی تب «Load Model» "
        "(P فیدر) خوانده می‌شود — یک ورودی واحد برای همهٔ محاسبات بار. "
        "خالی = نامشخص → طرح‌های انتقالی «نیازمند تأیید ظرفیت» می‌شوند "
        "و تأیید نهایی مهندسی نمی‌گیرند."))
    v2.addWidget(tbl)
    tabs.addTab(page2, "Feeder capacity")

    # -- 3) costs -----------------------------------------------------------
    page3 = QWidget(); f3 = QFormLayout(page3)
    cm = cur.get("cost_model", {})
    sp_costs = {}
    for key, label, hi in (
            ("nc_new_rials", "New NC switch (rials)", 1e12),
            ("no_new_rials", "New NO switch (rials)", 1e12),
            ("automation_upgrade_rials", "Automation upgrade (rials)", 1e12),
            ("rial_per_kwh", "Rial per kWh (جدول ۱۸)", 1e7),
            ("switching_minutes", "Switching time (minutes)", 600.0)):
        sp = QDoubleSpinBox(); sp.setRange(0.0, hi); sp.setDecimals(0)
        sp.setValue(float(cm.get(key, 0.0)))
        sp_costs[key] = sp
        if key == "rial_per_kwh":
            f3.addRow(make_required_label(label + ":"), sp)
        else:
            f3.addRow(label + ":", sp)
    f3.addRow(make_explain_label(
        "نرخ انرژی (ریال بر kWh) ضریب رسمی جدول ۱۸ است (پیش‌فرض ۱۰۰۰) و "
        "برای مقایسه اقتصادی الزامی است؛ سایر هزینه‌ها سیاست شرکت‌اند."))
    tabs.addTab(page3, "Costs")

    # -- 4) acceptance criteria (نیاز ۱۰) -----------------------------------
    page4 = QWidget(); f4 = QFormLayout(page4)
    cr = cur.get("criteria", {})
    sp_min_kwh = QDoubleSpinBox(); sp_min_kwh.setRange(0.0, 1e6)
    sp_min_kwh.setValue(float(cr.get("min_ens_reduction_kwh", 1.0)))
    sp_min_pct = QDoubleSpinBox(); sp_min_pct.setRange(0.0, 100.0)
    sp_min_pct.setValue(float(cr.get("min_ens_reduction_percent", 1.0)))
    sp_max_sw = QDoubleSpinBox(); sp_max_sw.setRange(0.0, 50.0)
    sp_max_sw.setValue(float(cr.get("max_switches_per_scheme") or 0))
    sp_max_bud = QDoubleSpinBox(); sp_max_bud.setRange(0.0, 1e14)
    sp_max_bud.setDecimals(0)
    sp_max_bud.setValue(float(cr.get("max_budget_rials") or 0))
    f4.addRow("Min ΔENS (kWh/yr — مطلق):", sp_min_kwh)
    f4.addRow("Min ΔENS (٪ — نسبی):", sp_min_pct)
    f4.addRow("Max switches per scheme (0=بدون سقف):", sp_max_sw)
    f4.addRow("Max budget per scheme, rials (0=بدون سقف):", sp_max_bud)
    note4 = make_explain_label(
        "طرح بدون کاهش ENS معنادار یا منفعت مثبت رد می‌شود؛ بدون طرح "
        "قابل قبول، نتیجه صریح «عدم توجیه نصب کلید» است — نرم‌افزار به "
        "اجبار طرح معرفی نمی‌کند.")
    f4.addRow(note4)
    tabs.addTab(page4, "Acceptance")

    # -- 5) data coverage (نیاز ۸) ------------------------------------------
    page5 = QWidget(); f5 = QFormLayout(page5)
    cov = cur.get("coverage", {})
    ed_start = QLineEdit(str(cov.get("start") or ""))
    ed_start.setPlaceholderText("auto (از اولین رکورد) — مثل 1404/01")
    ed_end = QLineEdit(str(cov.get("end") or ""))
    ed_end.setPlaceholderText("auto (تا آخرین رکورد)")
    ed_force = QLineEdit(", ".join(cov.get("force_cover_months") or []))
    ed_force.setPlaceholderText("ماه‌های بدون رکورد اما دارای پوشش، مثل 1404/08, 1404/09")
    ed_excl = QLineEdit(", ".join(cov.get("force_exclude_months") or []))
    ed_excl.setPlaceholderText("ماه‌های حذف از مواجهه، مثل 1404/05")
    f5.addRow("Coverage start (YYYY/MM):", ed_start)
    f5.addRow("Coverage end (YYYY/MM):", ed_end)
    f5.addRow("Force-covered months:", ed_force)
    f5.addRow("Excluded months:", ed_excl)
    note5 = make_explain_label(
        "نبود رکورد الزاماً نبود خاموشی نیست: ماه‌های فاقد رکورد از مخرج "
        "λ حذف می‌شوند؛ اگر پوشش واقعی داشته‌اند، صریحاً اینجا اعلام "
        "کنید (همه تغییرات در گزارش ثبت می‌شود). فیلدهای این صفحه اختیاری "
        "هستند — پیش‌فرض، کل بازه داده است.")
    f5.addRow(note5)
    tabs.addTab(page5, "Data coverage")

    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                            | QDialogButtonBox.StandardButton.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)

    def apply() -> dict:
        """Collect every page → plain dict for the caller."""
        def months(text):
            return [p.strip() for p in (text or "").split(",")
                    if p.strip()]
        # Load Scaling P/Q — فقط ردیف‌هایی که ورودی دارند (عدد > 0)
        feeder_pq = {}
        for i, k in enumerate(feeder_keys):
            def _num(col, _i=i):
                it = pq_table.item(_i, col)
                if it is None or not it.text().strip():
                    return 0.0
                try:
                    return float(it.text().strip().replace(",", ""))
                except ValueError:
                    return 0.0
            p, q = _num(1), _num(2)
            if p > 0 or q > 0:
                feeder_pq[k] = {"p_kw": p, "q_kvar": q}
        cap = parse_capacity_rows(
            [{"feeder_key": (tbl.item(i, 0).text() if tbl.item(i, 0) else ""),
              "nominal_kw": tbl.item(i, 1).text() if tbl.item(i, 1) else None,
              # پیک از سلول خوانده نمی‌شود؛ از ورودی واحد مدل بار ساخته می‌شود
              "peak_kw": None,
              "emergency_kw": tbl.item(i, 3).text() if tbl.item(i, 3) else None,
              "note": tbl.item(i, 4).text() if tbl.item(i, 4) else ""}
             for i in range(tbl.rowCount())])
        for row in cap:
            p = feeder_pq.get(row["feeder_key"], {}).get("p_kw")
            row["peak_kw"] = float(p) if p else None
            row["peak_source"] = "load_model" if p else "unknown"
        return {
            "load_model": {"level": cmb_level.currentData(),
                           "loading_factor": sp_lf.value(),
                           "substitute_factor": sp_sf.value(),
                           "feeder_pq": feeder_pq},
            "capacity_rows": cap,
            "cost_model": {k: sp.value() for k, sp in sp_costs.items()},
            "criteria": {
                "min_ens_reduction_kwh": sp_min_kwh.value(),
                "min_ens_reduction_percent": sp_min_pct.value(),
                "max_switches_per_scheme":
                    int(sp_max_sw.value()) or None,
                "max_budget_rials": float(sp_max_bud.value()) or None,
            },
            "coverage": {"start": ed_start.text().strip() or None,
                         "end": ed_end.text().strip() or None,
                         "force_cover_months": months(ed_force.text()),
                         "force_exclude_months": months(ed_excl.text())},
        }

    dlg.apply = apply                    # type: ignore[attr-defined]
    return dlg


def make_exports_dialog(parent, formats=("xlsx", "docx", "pdf", "gis")):  # noqa
    """Output-format selection dialog (نیاز ۱۲ — انتخاب فرمت خروجی)."""
    from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                                   QHBoxLayout, QLabel, QVBoxLayout)

    dlg = QDialog(parent)
    dlg.setWindowTitle("SwitchLoc — Export formats")
    labels = {"xlsx": "Excel study workbook (.xlsx)",
              "docx": "Word report (.docx)",
              "pdf": "PDF report (.pdf — needs optional extras)",
              "gis": "GIS export (GeoJSON + CSV)"}
    boxes = {}
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel("خروجی‌های موردنیاز را انتخاب کنید:"))
    row = QHBoxLayout()
    for fmt in formats:
        cb = QCheckBox(labels.get(fmt, fmt))
        cb.setChecked(True)
        boxes[fmt] = cb
        row.addWidget(cb)
    lay.addLayout(row)
    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                            | QDialogButtonBox.StandardButton.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)

    def selected() -> tuple:
        return tuple(f for f, cb in boxes.items() if cb.isChecked())

    dlg.selected = selected              # type: ignore[attr-defined]
    return dlg
