# -*- coding: utf-8 -*-
"""Dashboard tab — the management view (Phase 3/4 results at a glance).

Layout (top → bottom):
  1. KPI cards        — feeders / zones / switches / Σλ / worst feeder /
                        proposed switches / selected schemes / issues
  2. charts           — per-feeder λ, ranking score, EP% (one Figure,
                        matplotlib only — the data+chart code is Qt-free
                        and Agg-testable; only the wrapper touches Qt)
  3. feeder matrix    — one merged row per feeder (trace + λ/r + EP/TL +
                        rank + selected scheme)
  4. table 18         — CE/CN comparison of the switching schemes
  5. notes            — λ source, outage summary, issues (Persian text
                        from the results, rendered by Qt — RTL is fine
                        in widgets; only Matplotlib cannot shape RTL)

`draw_charts(fig, dash)` and the pure assembly live outside the Qt
classes so tests run them on a plain Agg figure (see map_canvas.py).
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

from ..map_renderer import FEEDER_COLORS           # noqa: E402


# ---------------------------------------------------------------------------
# Qt-free chart builder (Agg-testable)
# ---------------------------------------------------------------------------
def draw_charts(fig, dash: dict) -> None:
    """λ / score / EP per feeder as three bar panels on ``fig``."""
    rows = dash.get("feeders") or []
    fig.clf()
    if not rows:
        ax = fig.add_subplot(111)
        ax.text(0.5, 0.5, "no feeder data yet", ha="center", va="center",
                fontsize=11, color="#777777")
        ax.set_axis_off()
        return
    keys = [r["feeder_key"] for r in rows]
    colors = [FEEDER_COLORS[i % len(FEEDER_COLORS)] for i in range(len(keys))]

    axs = fig.subplots(1, 3)

    lam = [r["lambda_per_year"] for r in rows]
    axs[0].bar(keys, lam, color=colors)
    axs[0].set_title("λ per feeder (1/yr)", fontsize=9)
    axs[0].tick_params(labelsize=7)

    scores = [r["score"] if r.get("score") is not None else 0.0
              for r in rows]
    axs[1].bar(keys, scores, color=colors)
    axs[1].set_title("Ranking score (formula 1)", fontsize=9)
    axs[1].tick_params(labelsize=7)

    eps = [r["ep_percent"] if r.get("ep_percent") is not None else 0.0
           for r in rows]
    axs[2].bar(keys, eps, color=colors)
    axs[2].set_title("EP % (n-1, table 14)", fontsize=9)
    axs[2].tick_params(labelsize=7)
    for ax in axs:
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=0.25)
    fig.subplots_adjust(left=0.05, right=0.99, top=0.88, bottom=0.10,
                        wspace=0.25)


def _build_chart_section():
    """بخش نمودارها → (ویجت، {key: نمودار})؛ ایمپورت Qt تنبل است."""
    from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget
    from .charts import BarChartWidget, CHART_METRICS

    def build() -> tuple:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        head = QLabel("<b>نمودار شاخص‌های ارزیابی فیدرها</b> — SAIDI، SAIFI، "
                      "CAIDI، ASAI، ENS/EENS، λ، r، U، بار، ظرفیت، طول و "
                      "امتیاز رتبه‌بندی (هر میله یک فیدر)")
        head.setWordWrap(True)
        v.addWidget(head)
        grid_holder = QWidget()
        grid = QGridLayout(grid_holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)
        charts = {}
        for i, (key, title, unit, _scale) in enumerate(CHART_METRICS):
            ch = BarChartWidget(title=title, unit=unit)
            charts[key] = ch
            grid.addWidget(ch, i // 2, i % 2)
        v.addWidget(grid_holder)
        return box, charts

    return build


def _fmt(v, spec: str = ":g") -> str:
    if v is None:
        return "—"
    try:
        return format(v, spec.replace(":", "", 1) if spec.startswith(":")
                      else spec)
    except (TypeError, ValueError):
        return str(v)


# ---------------------------------------------------------------------------
# Qt wrapper (import-safe without Qt — everything Qt lives in the factory)
# ---------------------------------------------------------------------------
def make_dashboard_tab(parent=None):
    """Return the dashboard widget exposing ``show_dashboard(dash)``."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (QAbstractItemView, QGridLayout,
                                   QHBoxLayout, QLabel, QScrollArea,
                                   QTableWidget, QTableWidgetItem,
                                   QTabWidget, QVBoxLayout, QWidget)
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure

    mono = QFont("Consolas")
    mono.setStyleHint(QFont.StyleHint.Monospace)

    TABLE_HEADER_QSS = (
        "QHeaderView::section { background-color:#1f4e79; color:white;"
        " font-weight:bold; padding:4px 6px; border:1px solid #16385a; }")
    # colours come from the application theme (light/dark) — only the item
    # padding is local; the header keeps its navy identity in both themes
    TABLE_QSS = "QTableWidget::item { padding:3px; }"

    def _style_table(t: "QTableWidget") -> None:
        """شکیل‌سازی جدول داشبورد (بازخورد کاربر): هدر رنگی سرمه‌ای با
        متن سفید، وسط‌چین، ردیف‌های یک‌درمیان رنگی، بدون ویرایش."""
        from PySide6.QtCore import Qt
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        t.setAlternatingRowColors(True)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setCornerButtonEnabled(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.horizontalHeader().setStyleSheet(TABLE_HEADER_QSS)
        t.setStyleSheet(TABLE_QSS)
        t.verticalHeader().setDefaultSectionSize(26)

    # ------------------------------------------------------------------
    class DashboardTab(QWidget):
        """KPI cards + charts + feeder matrix + reconciliation + table 18."""

        def __init__(self, parent_=None):
            super().__init__(parent_)
            self.fig = Figure(figsize=(11, 2.8))
            self.canvas = FigureCanvasQTAgg(self.fig)
            self.canvas.setMinimumHeight(190)

            self.cards: dict[str, QLabel] = {}
            grid = QGridLayout()
            grid.setContentsMargins(8, 6, 8, 0)
            grid.setSpacing(6)
            for i, key in enumerate(("feeders", "zones", "switches",
                                     "total_lambda", "worst_feeder",
                                     "proposed_switches", "plans_accepted",
                                     "plans_not_justified")):
                val = QLabel("—")
                val.setAlignment(Qt.AlignmentFlag.AlignCenter)
                f = val.font()
                f.setPointSize(f.pointSize() + 5)
                f.setBold(True)
                val.setFont(f)
                cap = QLabel({
                    "feeders": "Feeders", "zones": "Zones",
                    "switches": "Switches (GIS)",
                    "total_lambda": "Σ λ (1/yr)",
                    "worst_feeder": "Priority 1",
                    "proposed_switches": "Proposed switches",
                    "plans_accepted": "Plans accepted",
                    "plans_not_justified": "Not justified (no key)",
                }[key])
                cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
                box = QVBoxLayout()
                box.setContentsMargins(10, 8, 10, 8)
                box.addWidget(val)
                box.addWidget(cap)
                holder = QWidget()
                holder.setLayout(box)
                holder.setObjectName("KpiCard")
                holder.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,
                                    True)
                holder.setStyleSheet(
                    "QWidget#KpiCard { background: palette(alternate-base);"
                    " border: 1px solid palette(mid); border-radius: 6px; }")
                self.cards[key] = val
                grid.addWidget(holder, i // 4, i % 4)

            self.feeder_table = QTableWidget()
            _style_table(self.feeder_table)

            self.zone_table = QTableWidget()
            _style_table(self.zone_table)
            self.zone_table.setMinimumHeight(150)

            self.recon_table = QTableWidget()
            _style_table(self.recon_table)
            self.recon_table.setMaximumHeight(150)

            self.econ_table = QTableWidget()
            _style_table(self.econ_table)

            self.notes = QLabel("")
            self.notes.setWordWrap(True)
            self.notes.setTextFormat(Qt.TextFormat.RichText)
            self.notes.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.notes.setFont(mono)

            from ..qt.widgets import make_explain_label
            inner = QWidget()
            lay = QVBoxLayout(inner)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)
            lay.addLayout(grid)
            lay.addWidget(self.canvas)
            self.chart_box, self.charts = _build_chart_section()()
            lay.addWidget(self.chart_box)
            lay.addWidget(QLabel("<b>Feeder matrix — trace, λ/r, EP/TL, "
                                 "ENS, rank, selected scheme</b>"))
            lay.addWidget(self.feeder_table, 2)
            lay.addWidget(make_explain_label(
                "جدول آشتی ترانس‌ها (ریشه‌یابی اختلاف تعداد): ستون «TR "
                "(GIS)» تعداد ترانس‌ها بر اساس برچسب فیدر در داده GIS "
                "(ترکیب رسمی فیدر) است و ستون «TR (مسیر تغذیه)» تعداد "
                "رهیابی‌شده از منبع با وضعیت کلیدها. اختلاف یعنی ایراد "
                "داده GIS (مثال خلخال: ترانس‌های F6 با برچسب F5/خالی) یا "
                "قطعه پشت کلید باز — برای اصلاح، برچسب T_FeederNa را در "
                "GIS بازبینی کنید."))
            lay.addWidget(self.recon_table)
            lay.addWidget(QLabel("<b>Zone register — طول، بار و تعداد تجهیزات هر زون</b>"))
            lay.addWidget(self.zone_table, 1)
            lay.addWidget(QLabel("<b>Table 18 — CE/CN comparison "
                                 "(★ = selected)</b>"))
            lay.addWidget(self.econ_table, 1)
            lay.addWidget(self.notes)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(inner)
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(scroll)

        # -- public ------------------------------------------------------
        def show_dashboard(self, dash: dict) -> None:
            """Render one `build_dashboard()` payload."""
            k = dash.get("kpis", {})
            self.cards["feeders"].setText(str(k.get("feeders", 0)))
            self.cards["zones"].setText(str(k.get("zones", 0)))
            self.cards["switches"].setText(str(k.get("switches", 0)))
            self.cards["total_lambda"].setText(f"{k.get('total_lambda', 0):g}")
            self.cards["worst_feeder"].setText(k.get("worst_feeder") or "—")
            self.cards["proposed_switches"].setText(
                str(k.get("proposed_switches", 0)))
            self.cards["plans_accepted"].setText(
                str(k.get("plans_accepted", 0)))
            self.cards["plans_not_justified"].setText(
                str(k.get("plans_not_justified", 0)))

            draw_charts(self.fig, dash)
            self.canvas.draw_idle()

            self._fill_charts(dash)
            self._fill_feeder_table(dash.get("feeders") or [])
            self._fill_recon_table(dash.get("reconciliation") or [])
            self._fill_zone_table(dash.get("zones") or [])
            self._fill_econ_table(dash.get("economics") or [])
            self._fill_notes(dash)

        # -- internals -----------------------------------------------------
        def _fill_charts(self, dash: dict) -> None:
            """همهٔ شاخص‌های ارزیابی فیدرها به‌صورت نمودار ستونی."""
            charts = getattr(self, "charts", None)
            if not charts:
                return
            from .charts import chart_items
            rows = dash.get("feeders") or []
            for key, chart in charts.items():
                chart.set_data(chart_items(rows, key))

        def _fill_feeder_table(self, rows: list) -> None:
            from ..qt.widgets import fill_table
            headers = ["Feeder", "Nodes", "Edges", "km", "TR (مسیر تغذیه)",
                       "TR (GIS)", "ΣS_rated kVA", "ΔTR", "ENS kWh/yr",
                       "Loads", "λ 1/yr", "r min", "U h/yr", "EP %", "TL %",
                       "Load kW", "Load Δ kW", "Load source", "Rank", "Score", "Ties",
                       "Capacity (nom/peak/res kW)", "Cap status",
                       "Plan status", "SW"]
            data = []
            for r in rows:
                nom = r.get("cap_nominal_kw")
                pk = r.get("cap_peak_kw")
                res = r.get("cap_reserve_kw")
                cap_txt = ("—" if nom is None and pk is None else
                           f"{nom if nom is not None else '—'} / "
                           f"{pk if pk is not None else '—'} / "
                           f"{res if res is not None else '—'}")
                plan_txt = r.get("plan_status_fa") or \
                    r.get("plan_status") or "—"
                if r.get("plan_approved"):
                    plan_txt = "✔ تأیید نهایی مهندسی"
                data.append([
                    r["feeder_key"], r["nodes"], r["edges"], r["km"],
                    r["transformers"],
                    r.get("transformers_gis") if r.get("transformers_gis")
                    is not None else "—",
                    _fmt(r.get("s_rated_kva_gis"), ",.0f"),
                    r.get("tr_diff") if r.get("tr_diff") is not None
                    else "—",
                    _fmt(r.get("ens_kwh"), ",.1f"),
                    r["loads"],
                    f"{r['lambda_per_year']:.2f}",
                    f"{r['r_minutes']:.1f}",
                    f"{r['u_hours']:.2f}" if r["u_hours"] else "—",
                    _fmt(r.get("ep_percent"), ".1f"),
                    _fmt(r.get("tl_percent"), ".1f"),
                    _fmt(r.get("total_load_kw"), ".0f"),
                    _fmt(r.get("load_delta_kw"), ".1f"),
                    r.get("load_source") or "—",
                    r.get("rank") or "—",
                    _fmt(r.get("score"), ".4f"),
                    r.get("ties_count", "—"),
                    cap_txt,
                    {"ok": "✔ مشخص",
                     "needs_capacity_confirmation": "نیازمند تأیید ظرفیت",
                     None: "—"}.get(r.get("cap_status"),
                                     r.get("cap_status") or "—"),
                    plan_txt,
                    r.get("n_switches") or 0,
                ])
            fill_table(self.feeder_table, headers, data)
            self.feeder_table.resizeColumnsToContents()

        def _fill_recon_table(self, rows: list) -> None:
            """جدول آشتی ترانس‌ها — برچسب GIS در برابر مسیر تغذیه."""
            from ..qt.widgets import fill_table
            headers = ["Feeder", "TR (GIS)", "ΣS_rated (kVA)",
                       "TR (مسیر تغذیه)", "اختلاف", "بدون برچسب",
                       "بدون ظرفیت"]
            data = [[r.get("feeder_key", "—"), r.get("qty_gis", 0),
                     _fmt(r.get("s_rated_kva"), ",.0f"),
                     r.get("qty_traced", 0), r.get("diff", 0),
                     r.get("blank_label", 0), r.get("no_capacity", 0)]
                    for r in rows]
            fill_table(self.recon_table, headers, data)
            self.recon_table.resizeColumnsToContents()

        def _fill_zone_table(self, rows: list) -> None:
            """نمایش مستقیم شناسنامه زون‌ها؛ منبع بار همان موتور n-1 است."""
            from ..qt.widgets import fill_table
            headers = ["Feeder", "Zone", "Zone ID", "Kind", "Length",
                       "Load kW", "Transformers", "Loads", "Nodes", "Edges"]
            data = [[r.get("feeder_key"), r.get("zone_no"), r.get("zone_id"),
                     r.get("kind"), r.get("length_label"),
                     _fmt(r.get("load_kw"), ",.1f"), r.get("transformers"),
                     r.get("loads"), r.get("nodes"), r.get("edges")]
                    for r in rows]
            fill_table(self.zone_table, headers, data)
            self.zone_table.resizeColumnsToContents()

        def _fill_econ_table(self, comps: list) -> None:
            from ..qt.widgets import fill_table
            headers = ["★", "Kind", "Feeders", "N", "E2 kWh", "E1 kWh",
                       "CE (rials)", "CN (rials)", "CE/CN"]
            data = []
            for c in comps:
                ratio = "—" if c.get("ce_over_cn") is None else \
                    format(c["ce_over_cn"], ".4g")
                data.append([
                    "★" if c.get("selected") else "",
                    c.get("kind"), ", ".join(c.get("feeders") or []),
                    c.get("n_switches"),
                    f"{c.get('e2_before_kwh', 0):,.0f}",
                    f"{c.get('e1_after_kwh', 0):,.0f}",
                    f"{c.get('ce_rials', 0):.3e}",
                    f"{c.get('cn_rials', 0):.3e}", ratio])
            fill_table(self.econ_table, headers, data)
            self.econ_table.resizeColumnsToContents()

        def _fill_notes(self, dash: dict) -> None:
            o = dash.get("outage") or {}
            lines = [f"λ/r source: <b>{dash.get('lambda_source', '—')}</b>"
                     f" &nbsp;|&nbsp; Study scope: <b>"
                     f"{(dash.get('kpis') or {}).get('scope', '—')}</b>"]
            cov = dash.get("coverage") or {}
            if cov.get("start"):
                miss = cov.get("missing_months") or []
                lines.append(
                    "Data coverage (نیاز ۸): window "
                    f"{cov['start'][0]}/{cov['start'][1]:02d} .. "
                    f"{cov['end'][0]}/{cov['end'][1]:02d} — "
                    f"{len(cov.get('effective_months') or [])} months with "
                    f"data, <b>{cov.get('exposure_days')} days = "
                    f"{cov.get('exposure_years'):.4f} yr</b> exposure"
                    + (f" — <span style='color:#b26a00'>missing months "
                       f"(excluded): {', '.join(miss)}</span>" if miss else ""))
            k = dash.get("kpis") or {}
            lines.append(
                f"Zone register: {k.get('zones', 0)} zones; "
                f"{k.get('zones_with_load', 0)} with assigned load; "
                f"total zone length {k.get('zone_total_length_m', 0):,.0f} m. "
                "Feeder load is reconciled from the n-1 zone allocation.")
            lines.append(
                f"Capacities (نیاز ۹): {k.get('capacities_known', 0)} known / "
                f"{k.get('capacities_missing', 0)} missing — "
                f"plans: {k.get('plans_accepted', 0)} accepted, "
                f"{k.get('plans_need_capacity', 0)} need capacity, "
                f"{k.get('plans_not_justified', 0)} not justified (نیاز ۱۰)")
            if o.get("available"):
                cls = ", ".join(f"{k2}: {v}" for k2, v in
                                sorted((o.get("class_summary") or {}).items(),
                                       key=lambda kv: -kv[1]))
                record_count = o.get("records")
                empty_count = o.get("rows_empty_skipped")
                record_text = (f"{record_count:,}" if isinstance(record_count, (int, float))
                               else "نامشخص (خلاصه ذخیره‌شده فاقد جزئیات فیدر است)")
                empty_text = (f"{empty_count:,}" if isinstance(empty_count, (int, float))
                              else "—")
                lines.append(
                    f"Outage data: {record_text} records, "
                    f"{empty_text} empty rows skipped, "
                    f"years {', '.join(map(str, o.get('years') or []))}.")
                if cls:
                    lines.append(f"Classes — {cls}")
                si = o.get("service_indices") or {}
                if si.get("has_result"):
                    per = "، ".join(
                        f"{f['feeder_key']}: SAIFI {f['saifi']:.2f} / "
                        f"SAIDI {f['saidi']:,.0f} دقیقه"
                        for f in (si.get("feeders") or [])
                        if f.get("events_counted"))
                    lines.append(
                        "<b>SAIDI/SAIFI (شاخص پیوستگی):</b> "
                        f"نظام SAIFI <b>{si.get('saifi', 0):.2f}</b> قطع/سال · "
                        f"SAIDI <b>{si.get('saidi', 0):,.0f}</b> دقیقه/سال · "
                        f"CAIDI {si.get('caidi', 0):,.0f} دقیقه · "
                        f"ASAI {100 * si.get('asai', 1):.4f}%"
                        + (f"<br/>&nbsp;&nbsp;{per}" if per else "")
                        + f" <span style='color:#666'>({si.get('aggregation')}"
                        f"، مبنا {si.get('load_basis')}، انرژی "
                        f"{str(si.get('energy_unit', '')).upper()})</span>")
            else:
                lines.append("Outage data: not imported yet — import the "
                             "outage list or the per-feeder files (Data "
                             "Import tab) so λ/r come from the real records.")
            issues = dash.get("issues") or []
            if issues:
                lines.append("<b>Latest placement issues:</b>")
                for i in issues[:6]:
                    lines.append(f"• [{i['severity']}] {i['code']} — "
                                 f"{i['message_fa']}")
                if len(issues) > 6:
                    lines.append(f"• … {len(issues) - 6} more")
            self.notes.setText("<br>".join(lines))

    return DashboardTab(parent)
