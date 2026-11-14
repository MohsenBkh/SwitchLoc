# -*- coding: utf-8 -*-
"""workbook.py — کتاب کار Excel خروجی مطالعه (فاز ۵، openpyxl).

One RTL workbook, one sheet per official artefact — the numbers are
REBUILT FROM THE SAME StudyModel as the Word/PDF report, never copied:

  خلاصه        — KPIs + run identity + cross-check verdict
  جدول ۱۳-۱۵   — connections, EP/TL, per-zone n-1 rows
  رتبه‌بندی     — full audit matrix: raw / normalized / weighted / score
  طرح‌ها        — جدول ۱۷ schemes with switch lists
  جدول ۱۸      — CE/CN comparison
  کلیدها       — actionable proposed-switch schedule (with coordinates)
  λ/r          — the reliability matrix backing criteria 5/6

Sheets are rightToLeft so the workbook reads naturally in Excel; header
styling is uniform; numbers stay numbers (no text-formatted numerics).
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .content import SCHEME_KIND_FA, WEIGHTS_FA
from .model import StudyModel

_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
_HEADER_FONT = Font(name="Vazirmatn", bold=True, color="FFFFFF", size=11)
_BODY_FONT = Font(name="Vazirmatn", size=10)
_TITLE_FONT = Font(name="Vazirmatn", bold=True, size=13, color="1F4E79")
_THIN = Side(style="thin", color="B0B0B0")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _sheet(wb: Workbook, title: str) -> object:
    ws = wb.create_sheet(title[:31])
    ws.sheet_view.rightToLeft = True
    return ws


def _put_title(ws, row: int, text: str) -> int:
    c = ws.cell(row=row, column=1, value=text)
    c.font = _TITLE_FONT
    return row + 1


def _put_table(ws, row: int, headers: list, rows: list) -> int:
    for j, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=j, value=h)
        c.font = _HEADER_FONT
        c.fill = _HEADER_FILL
        c.border = _BORDER
        c.alignment = Alignment(horizontal="center", vertical="center",
                                wrap_text=True)
    ws.row_dimensions[row].height = 22
    for i, r in enumerate(rows, start=1):
        for j, v in enumerate(r, start=1):
            c = ws.cell(row=row + i, column=j,
                        value=v if v is not None else "—")
            c.font = _BODY_FONT
            c.border = _BORDER
            c.alignment = Alignment(horizontal="right" if j == 1
                                    else "center", vertical="center",
                                    wrap_text=False)
    return row + len(rows) + 2


def _auto_width(ws, widths: list | None = None) -> None:
    if widths:
        for j, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(j)].width = w
        return
    for j, col in enumerate(ws.iter_cols(), start=1):
        best = 10
        for c in col:
            v = "" if c.value is None else str(c.value)
            best = max(best, min(60, len(v) + 4))
        ws.column_dimensions[get_column_letter(j)].width = best


def write_feeder_indices_sheet(wb, m: StudyModel) -> object:
    """برگهٔ «شاخص‌های فیدرها» + نمودارهای بومی Excel (درخواست کاربر).

    ستون‌ها از همان `FEEDER_INDEX_COLUMNS` گزارش می‌آیند تا Word/PDF و
    Excel یک عدد نشان دهند. هیچ عددی ساخته نمی‌شود؛ مقدار نامعلوم خالی
    می‌ماند («—») تا با صفر اشتباه نشود.
    """
    from .content import FEEDER_INDEX_COLUMNS

    metrics = m.feeder_table()
    ws = _sheet(wb, "شاخص‌های فیدرها")
    row = _put_title(ws, 1, "شاخص‌های ارزیابی فیدرها — λ/r، SAIDI/SAIFI/"
                           "CAIDI/ASAI، ENS/EENS، ردیابی و رتبه‌بندی")
    ind = m.feeder_indices or {}
    if ind.get("has_result"):
        row = _put_table(ws, row, ["شاخص سامانه", "مقدار", "مبنا"], [
            ["SAIFI (قطع/سال)", round(float(ind.get("saifi") or 0), 3),
             ind.get("aggregation") or "—"],
            ["SAIDI (دقیقه/سال)", round(float(ind.get("saidi") or 0), 2),
             ind.get("aggregation") or "—"],
            ["CAIDI (دقیقه)", round(float(ind.get("caidi") or 0), 2), "—"],
            ["ASAI (٪)", round(100 * float(ind.get("asai") or 0), 4), "—"],
            ["مبنای سهم مشترکین", ind.get("load_basis") or "—", "—"],
            ["واحد انرژی توزیع‌نشده",
             str(ind.get("energy_unit") or "—").upper(),
             ind.get("energy_unit_source") or "—"],
        ])
    headers = ["فیدر"] + [c[1] for c in FEEDER_INDEX_COLUMNS]
    body = []
    for r in metrics:
        line = [r["feeder_key"]]
        for key, _label, nd in FEEDER_INDEX_COLUMNS:
            v = r.get(key)
            if key == "asai" and v is not None:
                v = round(float(v) * 100.0, 4)
            elif isinstance(v, float):
                v = round(v, nd)
            line.append(v)
        body.append(line)
    header_row = row
    row = _put_table(ws, row, headers, body)
    _auto_width(ws, [22] + [14] * (len(headers) - 1))

    energy_rows = [f for f in ind.get("feeders", []) if f.get("energy_records")]
    if energy_rows:
        audit = _sheet(wb, "تطبیق انرژی")
        ar = _put_title(audit, 1, "تطبیق انرژی ثبت‌شده با ENS سالانه")
        _put_table(audit, ar, ["فیدر", "مجموع خام", "تعداد مقادیر", "واحد فرض‌شده", "مبنای واحد", "مواجهه (سال)", "ENS (kWh/سال)"],
                   [[f.get("feeder_key"), f.get("energy_raw_total"), f.get("energy_records"),
                     str(ind.get("energy_unit") or "—").upper(), ind.get("energy_unit_source") or "—",
                     f.get("exposure_years"), f.get("ens_kwh_per_year")] for f in energy_rows])
        _auto_width(audit, [25, 18, 18, 18, 18, 18, 22])

    # نمودارهای Excel-native (قابل ویرایش در خود Excel)
    try:
        from openpyxl.chart import BarChart, Reference
        col_of = {c[0]: i + 2 for i, c in enumerate(FEEDER_INDEX_COLUMNS)}
        wanted = [k for k in ("lambda_per_year", "r_minutes", "u_hours",
                              "saidi", "saifi", "caidi", "ens_per_year_kwh",
                              "ens_before_kwh") if k in col_of]
        anchor_row = header_row
        for key in wanted:
            if not body:
                break
            col = col_of[key]
            chart = BarChart()
            chart.type = "bar"
            chart.style = 10
            label = next(c[1] for c in FEEDER_INDEX_COLUMNS if c[0] == key)
            chart.title = label
            chart.y_axis.title = "مقدار"
            chart.x_axis.title = "فیدر"
            data = Reference(ws, min_col=col, min_row=header_row,
                             max_row=header_row + len(body))
            cats = Reference(ws, min_col=1, min_row=header_row + 1,
                             max_row=header_row + len(body))
            chart.add_data(data, titles_from_data=True)
            chart.set_categories(cats)
            chart.height = 7.5
            chart.width = 15
            ws.add_chart(chart, f"B{anchor_row + 20}")
            anchor_row += 17
    except Exception:                               # noqa: BLE001  pragma: no cover
        pass
    return ws


def export_workbook(m: StudyModel, path: str) -> str:
    """Write the Phase-5 XLSX and return the path."""
    wb = Workbook()
    wb.remove(wb.active)

    # ---------------- خلاصه ----------------------------------------------
    ws = _sheet(wb, "خلاصه")
    row = _put_title(ws, 1, f"خلاصه مطالعه — {m.name}")
    row = _put_table(ws, row, ["مشخصه", "مقدار"], [
        ["مرجع روش", "TAV122-02/00 (توانیر) — روش سطح اول، گام‌های ۴-۸"],
        ["شناسه اجرای جایابی", m.placement_run_id or "—"],
        ["نتیجه پذیرش", m.verdict()],
        ["سیستم مختصات تحلیل", m.crs_label],
        ["نتیجه تطبیق با اجرای ذخیره‌شده",
         m.crosscheck.get("status_fa", "—")],
    ])
    k = m.kpis()
    row = _put_table(ws, row, ["شاخص", "مقدار"], [
        ["تعداد فیدر مدل‌شده", k["feeder_count"]],
        ["تعداد زون‌ها", k["zone_count"]],
        ["کلیدهای موجود", k["switch_existing"]],
        ["کلیدهای پیشنهادی", k["switch_proposed"]],
        ["انرژی خاموشی قبل (kWh/سال)", round(k["ens_before_kwh"], 1)],
        ["انرژی خاموشی پس از طرح اصلی (kWh/سال)", round(k["ens_after_kwh"], 1)],
        ["صرفه‌جویی ENS (kWh/سال)", round(k["ens_saved_kwh"], 1)],
        ["بهترین نسبت CE/CN",
         None if k["best_ce_over_cn"] is None else round(k["best_ce_over_cn"], 4)],
        ["فیدر اولویت اول", k["top_feeder"]],
    ])
    _auto_width(ws, [46, 34])

    # ---------------- جداول ۱۳-۱۵ ----------------------------------------
    ws = _sheet(wb, "جداول ۱۳-۱۵")
    row = _put_title(ws, 1, "تحلیل n-1 — بند ۷-۷-۴ (گام‌های ۴-۵)")
    row = _put_table(ws, row, ["جدول ۱۳: فیدر الف", "فیدر ب", "کلید",
                               "اتوماسیون‌پذیر", "N", "M"],
                     [[c.feeder_a, c.feeder_b, c.switch_id or "—",
                       "دارد" if c.automation_capable else "ندارد",
                       c.n_ties, c.m_automation]
                      for c in m.placement.n1.connections])
    row = _put_table(ws, row, ["جدول ۱۴: فیدر", "EP (٪)", "TL (٪)",
                               "بدترین زون", "بار فیدر (kW)", "تعداد زون"],
                     [[f.feeder_key, round(f.ep.ep_percent, 2),
                       round(f.ep.tl_percent, 2),
                       f.ep.worst_zone if f.ep.worst_zone is not None else "—",
                       round(f.total_load_kw, 1), f.zone_count]
                      for f in m.placement.n1.eptl])
    row = _put_table(ws, row, ["جدول ۱۵: فیدر", "شماره زون", "شناسه زون",
                               "بار خاموش‌شده (kW)",
                               "بازپُل‌شدنی (kW)", "بار فیدر (kW)"],
                     [[r["feeder_key"], r["zone_no"], r["zone"],
                       r["shed_kw"], r["restorable_kw"], r["feeder_load_kw"]]
                      for r in m.placement.n1.rows15])
    _auto_width(ws, [20, 14, 26, 20, 18, 14])

    # ---------------- رتبه‌بندی (full audit matrix) -----------------------
    ws = _sheet(wb, "رتبه‌بندی")
    row = _put_title(ws, 1, f"گام ۶ — فرمول (۱) + جدول ۱۶؛ وزن‌های {WEIGHTS_FA}")
    crit = ["معیار ۱ ارتباطات (معکوس)", "معیار ۲ EP", "معیار ۳ TL (معکوس)",
            "معیار ۴ اولویت بار", "معیار ۵ λ", "معیار ۶ r"]
    heads = (["رتبه", "فیدر", "امتیاز"]
             + [f"خام {c}" for c in crit]
             + [f"نرمال {c}" for c in crit]
             + [f"وزن‌دار {c}" for c in crit])
    rows = []
    for r in m.placement.ranking.rows:
        rows.append([r.rank, r.feeder_key, round(r.score, 6)]
                    + [round(v, 4) for v in r.raw]
                    + [round(v, 6) for v in r.norm]
                    + [round(v, 6) for v in r.weighted])
    row = _put_table(ws, row, heads, rows)
    _auto_width(ws, [7, 10, 10] + [15] * 18)

    # ---------------- طرح‌ها (جدول ۱۷) ------------------------------------
    ws = _sheet(wb, "طرح‌ها")
    row = _put_title(ws, 1, "گام ۷ — طرح‌های کلیدگذاری (جدول ۱۷ + پیوست ب)")
    sch_rows = []
    for s in m.placement.schemes:
        for i, sw in enumerate(s.switches, start=1):
            sch_rows.append([s.id, SCHEME_KIND_FA.get(s.kind, s.kind),
                             ", ".join(s.feeders), i, sw.node, sw.kind,
                             sw.note or ""])
    row = _put_table(ws, row, ["شناسه طرح", "نوع طرح", "فیدرها",
                               "ترتیب کلید", "شناسه گره", "نوع کلید",
                               "شرح"], sch_rows or [["—"] * 7])
    _auto_width(ws, [36, 30, 14, 10, 34, 16, 44])

    # ---------------- جدول ۱۸ ---------------------------------------------
    ws = _sheet(wb, "جدول ۱۸")
    row = _put_title(ws, 1, "گام ۸ — مقایسه اقتصادی (بیشینه CE/CN)")
    comp_rows = []
    for c in m.placement.economics.comparisons:
        comp_rows.append([
            c.scheme_id, SCHEME_KIND_FA.get(c.kind, c.kind),
            ", ".join(c.feeders), c.n_switches,
            round(c.e2_before_kwh, 1), round(c.e1_after_kwh, 1),
            round(c.ce_rials, 0), round(c.cn_rials, 0),
            None if c.ce_over_cn in (None, float("-inf"))
            else round(c.ce_over_cn, 6),
            "★" if c.selected else ""])
    row = _put_table(ws, row, ["شناسه طرح", "نوع طرح", "فیدرها", "N",
                               "E₂ قبل (kWh)", "E₁ بعد (kWh)",
                               "CE (ریال)", "CN (ریال)", "CE/CN", "انتخاب"],
                     comp_rows)
    _auto_width(ws, [36, 30, 14, 6, 14, 14, 16, 16, 12, 8])

    # ---------------- شناسنامه زون‌ها ------------------------------------
    ws = _sheet(wb, "زون‌ها")
    row = _put_title(ws, 1, "شناسنامه زون‌ها — تخصیص بار از درخت n-1")
    zone_rows = [[z["feeder_key"], z["zone_no"], z["zone_id"], z["kind"],
                  z["length_m"], z["length_label"], z["load_kw"],
                  z["transformers"], z["loads"], z["nodes"], z["edges"]]
                 for z in m.zone_rows()]
    row = _put_table(ws, row, ["فیدر", "شماره زون", "شناسه زون", "نوع",
                               "طول (m)", "نمایش طول", "بار (kW)",
                               "ترانس", "بار", "گره", "یال"], zone_rows)
    _auto_width(ws, [14, 12, 36, 12, 14, 16, 16, 10, 10, 10, 10])

    # ---------------- کلیدهای پیشنهادی ------------------------------------
    ws = _sheet(wb, "کلیدهای پیشنهادی")
    row = _put_title(ws, 1, "کاربرگ اجرایی کلیدهای پیشنهادی (طرح‌های اصلی)")
    prop_rows = []
    for p in m.build_proposed():
        prop_rows.append([p.feeder, p.node, p.kind_fa, p.order_in_scheme,
                          p.zone_no, round(p.x, 2) if p.x is not None else None,
                          round(p.y, 2) if p.y is not None else None,
                          round(p.lon, 6) if p.lon is not None else None,
                          round(p.lat, 6) if p.lat is not None else None,
                          p.scheme_id])
    row = _put_table(ws, row, ["فیدر", "شناسه گره", "نوع کلید",
                               "ترتیب در طرح", "زون", "X (متر)", "Y (متر)",
                               "طول جغرافیایی", "عرض جغرافیایی",
                               "شناسه طرح"], prop_rows)
    row = _put_title(ws, row, "مختصات: سیستم مختصات تحلیل = " + m.crs_label)
    _auto_width(ws, [14, 34, 30, 12, 8, 12, 12, 14, 14, 36])

    # ---------------- ماتریس λ/r ------------------------------------------
    lam_rows = []
    for r in m.placement.ranking.rows:
        lam_rows.append([r.feeder_key, round(r.lambda_per_year, 3),
                         round(r.lambda_reducible, 3), round(r.r_minutes, 2),
                         round(r.lambda_per_year * r.r_minutes / 60.0, 2),
                         round(r.load_priority_sum, 1)])
    write_feeder_indices_sheet(wb, m)

    ws = _sheet(wb, "ماتریس λ-r")
    row = _put_title(ws, 1, "ماتریس λ/r فاز ۳ — مبنای معیارهای ۵ و ۶")
    row = _put_table(ws, row, ["فیدر", "λ تصادفی (بر سال)",
                               "λ کاهش‌پذیر (بر سال)", "r (دقیقه)",
                               "U=λr/60 (ساعت/سال)", "مجموع اولویت بار"],
                     lam_rows)
    _auto_width(ws, [12, 18, 20, 12, 18, 18])

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return str(out)


def export_dashboard_feeder_indices(dashboard: dict, path: str) -> str:
    """Export the displayed feeder metrics even when placement has not run."""
    from types import SimpleNamespace
    rows = []
    for source in dashboard.get("feeders") or []:
        row = dict(source)
        row["ens_before_kwh"] = source.get("ens_kwh")
        rows.append(row)
    indices = (dashboard.get("outage") or {}).get("service_indices") or {}
    model = SimpleNamespace(feeder_table=lambda: rows, feeder_indices=indices)
    wb = Workbook()
    wb.remove(wb.active)
    write_feeder_indices_sheet(wb, model)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return str(path)
