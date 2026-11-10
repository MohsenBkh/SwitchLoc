# -*- coding: utf-8 -*-
"""content.py — the neutral Persian report content (فاز ۵).

`build_report(model)` walks the StudyModel once and produces a
`ReportDoc`: ordered sections, each with intro paragraphs and captioned
tables.  `docx_report` and `pdf_report` only RENDER this tree — they
never re-derive a number — so the Word and PDF outputs are identical
by construction and any future channel (HTML, …) reuses the same tree.

All Persian here is plain text; the DOCX/PDF writers are responsible
for RTL direction and shaping.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .. import APP_NAME, TAV_REFERENCE, __version__
from .model import StudyModel

#: خلاصه وزن‌های رسمی جدول ۱۶ — used in headers/notes (A-03)
WEIGHTS_FA = "۱،۲،۲،۳،۱،۱"

SCHEME_KIND_FA = {
    "sequential_nc": "قطعه‌بندی سری (کلیدهای واکنش‌گر جدید)",
    "one_half_switch": "طرح ۱٫۵ کلیدی (نرمال‌باز + دو واکنش‌گر)",
    "automation_upgrade": "ارتقای اتوماسیون",
}


@dataclass
class Table:
    caption: str
    headers: list
    rows: list                  # list[list[str]] — everything pre-formatted
    note: str = ""
    #: optional relative column widths (fractions summing ~1); when given,
    # both renderers (PDF and Word) honour them — no per-renderer guesswork
    widths: list | None = None


@dataclass
class Equation:
    """One display equation of the «محاسبات کامل» section.

    ``omml`` — the genuine Word-equation XML (docx renderer); ``text`` —
    the plain-text form (PDF renderer / copy-paste); both describe the
    SAME formula so the two outputs never diverge.
    """
    caption: str
    omml: str
    text: str
    note: str = ""


@dataclass
class Section:
    id: str
    title: str
    intro: list = field(default_factory=list)     # paragraphs before tables
    tables: list = field(default_factory=list)    # [Table]
    after: list = field(default_factory=list)     # paragraphs after tables
    equations: list = field(default_factory=list)  # [Equation] after intro


@dataclass
class ReportDoc:
    title: str
    subtitle: str
    meta: list                                   # [(k, v)] two-column meta
    kpis: list                                   # [(k, v)]
    sections: list                               # [Section]
    footer: str = ""


def _fmt(v, nd=1) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.{nd}f}"
    return str(v)


def _money(v) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}"


def build_report(m: StudyModel, map_note: str = "") -> ReportDoc:
    # ---- نوع مطالعه تعیین‌کنندهٔ محتوای گزارش است (درخواست کاربر v1.15):
    # اگر مطالعهٔ جایابی کلید/EENS انجام شده باشد، گزارش نهایی فقط همان
    # مطالعه را مستند می‌کند و بخش‌های فاز ۴ (n-1، رتبه‌بندی، جدول ۱۷،
    # اقتصاد) به گزارش اضافه نمی‌شوند.
    if m.active_study == "eens":
        return _build_eens_report(m, map_note)
    k = m.kpis()
    snap = m.placement.settings
    verdict_fa = "قبول (PASS)" if m.verdict() == "PASS" else "رد (FAIL)"
    costs = snap.get("cost_model", {})

    from ..reliability.load_model import LEVEL_FA
    active_load_level = (m.placement.load_model or {}).get("level", "")
    meta = [
        ("نام پروژه", m.name),
        ("تاریخ گزارش", datetime.now().strftime("%Y-%m-%d")),
        ("مرجع روش", TAV_REFERENCE),
        ("نرم‌افزار / نسخه", f"{APP_NAME} {__version__}"),
        ("نتیجه پذیرش", verdict_fa),
        ("شناسه اجرای جایابی", m.placement_run_id or "— (اجرای در حافظه)"),
        ("پایگاه داده پروژه", m.db_path or "—"),
        ("سیستم مختصات تحلیل", m.crs_label),
        ("مدل بار", LEVEL_FA.get(active_load_level, active_load_level or "نامشخص")),
    ]

    kpis = [
        ("تعداد فیدر مدل‌شده", _fmt(k["feeder_count"], 0)),
        ("تعداد زون‌ها", _fmt(k["zone_count"], 0)),
        ("شاخص کل بار شبکه (kW)", _fmt(_total_load(m), 0)),
        ("کلیدهای موجود", _fmt(k["switch_existing"], 0)),
        ("کلیدهای پیشنهادی فاز ۴", _fmt(k["switch_proposed"], 0)),
        ("انرژی خاموشی قبل (kWh/سال)", _fmt(k["ens_before_kwh"], 0)),
        ("انرژی خاموشی پس از طرح‌های اصلی (kWh/سال)", _fmt(k["ens_after_kwh"], 0)),
        ("صرفه‌جویی ENS (kWh/سال)", _fmt(k["ens_saved_kwh"], 0)),
        ("بهترین نسبت CE/CN", _fmt(k["best_ce_over_cn"], 4)),
        ("فیدر اولویت اول", k["top_feeder"] or "—"),
    ]

    # ---------------- ۱. خلاصه مدیریتی -----------------------------------
    sec_sum = Section(
        id="summary", title="۱. خلاصه مدیریتی",
        intro=[
            "این گزارش خروجی فاز ۴ نرم‌افزار SwitchLoc است: رتبه‌بندی "
            "فیدرها بر مبنای شش معیار فرمول (۱) و جدول ۱۶ دستورالعمل، "
            "تولید طرح‌های کلیدگذاری جدول ۱۷ با قاعده طلایی U×P پیوست ب، "
            "و انتخاب طرح اصلی هر فیدر با معیار بیشینهٔ CE/CN جدول ۱۸. "
            "همه اعداد این گزارش با کتاب کار Excel و خروجی GIS هم‌مبنا "
            "هستند و از یک اجرای واحد موتور جایابی تولید شده‌اند.",
            f"فیدر نخست اولویت ({k['top_feeder'] or '—'}) با امتیاز "
            f"{_fmt(m.placement.ranking.rows[0].score if m.placement.ranking.rows else None, 4)} "
            "در صدر قرار گرفته و مجموع "
            f"{k['switch_proposed']} کلید پیشنهادی برای طرح‌های اصلی "
            "به‌دست آمده است. در صورت اعمال طرح‌های اصلی، انرژی خاموشی "
            f"از {k['ens_before_kwh']:,.0f} به {k['ens_after_kwh']:,.0f} "
            "کیلووات‌ساعت در سال می‌رسد.",
        ],
        tables=[Table("شاخص‌های کلیدی", ["شاخص", "مقدار"],
                      [[a, b] for a, b in kpis])])

    # ---------------- ۲. روش و پارامترها ---------------------------------
    sec_method = Section(
        id="method", title="۲. روش، پارامترها و مراجع رسمی",
        intro=[
            "زنجیره محاسبات بند ۷-۷-۴ تا ۷-۷-۷ دستورالعمل اجرا شده است: "
            "گام‌های ۴-۵ (جداول ۱۳ تا ۱۵ تحلیل n-1)، گام ۶ (رتبه‌بندی "
            "فرمول ۱)، گام ۷ (طرح‌های جدول ۱۷ و قطعه‌بندی قاعده طلایی "
            "روابط ۹ و ۱۰) و گام ۸ (مقایسه اقتصادی جدول ۱۸ با روابط ۸ و "
            "۱۱ پیوست ب). پارامترهای این اجرا در جدول زیر ثبت شده است.",
        ],
        tables=[
            Table("پارامترهای اجرا", ["پارامتر", "مقدار"], _method_rows(m)),
            Table("مدل هزینه (سیاست شرکت — قابل تنظیم)",
                  ["پارامتر هزینه", "مقدار (ریال)"], [
                      ["هزینه کلید واکنش‌گر جدید (NC)",
                       _money(costs.get("nc_new_rials"))],
                      ["هزینه کلید نرمال‌باز جدید (NO)",
                       _money(costs.get("no_new_rials"))],
                      ["ارتقای اتوماسیون یک کلید موجود",
                       _money(costs.get("automation_upgrade_rials"))],
                      ["نرخ انرژی (ریال بر کیلووات‌ساعت)",
                       _money(costs.get("rial_per_kwh"))],
                      ["زمان مانور هر کلیدزنی (دقیقه)",
                       _fmt(costs.get("switching_minutes"), 0)],
                  ]),
        ])

    # ---------------- ۳. جداول ۱۳-۱۵ (n-1) -------------------------------
    con_rows = [[c.feeder_a, c.feeder_b, c.switch_id or "—",
                 "دارد" if c.automation_capable else "ندارد",
                 str(c.n_ties), str(c.m_automation)]
                for c in m.placement.n1.connections] or \
        [["—", "—", "—", "—", "—", "—"]]
    ep_rows = [[f.feeder_key,
                f"{f.ep.ep_percent:.1f}٪", f"{f.ep.tl_percent:.1f}٪",
                _worst_zone_label(m, f),
                _fmt(f.total_load_kw, 0), _fmt(f.zone_count, 0)]
               for f in m.placement.n1.eptl]
    t15_rows = [[r["feeder_key"], str(r["zone_no"]), r["zone"],
                 _fmt(r["shed_kw"], 1), _fmt(r["restorable_kw"], 1),
                 _fmt(r["feeder_load_kw"], 0)]
                for r in m.placement.n1.rows15] or [["—"] * 6]
    sec_n1 = Section(
        id="n1", title="۳. تحلیل n-1 — جداول ۱۳، ۱۴ و ۱۵ (گام‌های ۴-۵)",
        intro=[
            "جدول ۱۳ ارتباطات فیدر به فیدر از مسیر نقاط اتصال (Tie) را "
            "خلاصه می‌کند؛ جدول ۱۴ حداکثر بار خاموش‌شدنی (EP) و سهم "
            "قابل انتقال (TL) هر فیدر را نشان می‌دهد و جدول ۱۵ تفکیک "
            "زون‌به‌زون بار خاموش‌شده و بازپُل‌شدنی است. مبنای بار، شاخص "
            "ظرفیت ترانس‌ها است (تصمیم باز ۴ فاز ۳).",
        ],
        tables=[
            Table("جدول ۱۳ — ارتباطات فیدرها",
                  ["فیدر الف", "فیدر ب", "کلید", "اتوماسیون‌پذیر",
                   "N", "M"], con_rows,
                  note="N: تعداد نقاط اتصال زوج — M: زیرمجموعه اتوماسیون‌پذیر "
                       "(تفسیر موقت A-13).",
                  widths=[0.10, 0.10, 0.40, 0.20, 0.10, 0.10]),
            Table("جدول ۱۴ — EP/TL فیدرها",
                  ["فیدر", "EP (بیشینه بار خاموش‌شده)", "TL (قابل انتقال)",
                   "بدترین زون", "بار فیدر (kW)", "تعداد زون"], ep_rows),
            Table("جدول ۱۵ — تفکیک زون‌به‌زون خاموشی",
                  ["فیدر", "شماره زون", "شناسه زون", "بار خاموش‌شده (kW)",
                   "بازپُل‌شدنی با مانور (kW)", "بار فیدر (kW)"], t15_rows,
                  widths=[0.09, 0.10, 0.31, 0.18, 0.20, 0.12]),
        ])

    # ---------------- پیوست تفصیلی زون‌ها -------------------------------
    zone_rows = m.zone_rows()
    zone_table_rows = [[r["feeder_key"], str(r["zone_no"]), r["zone_id"],
                        r["kind"], r["length_label"], _fmt(r["load_kw"], 1),
                        str(r["transformers"]), str(r["loads"]),
                        str(r["nodes"]), str(r["edges"])]
                       for r in zone_rows] or [["—"] * 10]
    sec_zones = Section(
        id="zones", title="۴. شناسنامه زون‌ها و توزیع بار",
        intro=[
            "این جدول از درخت زون‌بندی همان اجرای n-1 استخراج شده است؛ "
            "بار هر زون دقیقاً از تخصیص ترانس‌ها در مدل بار اجرا می‌آید و "
            "جمع بار زون‌های هر فیدر باید با بار کل همان فیدر تطبیق کند. "
            "طول‌های کمتر از یک کیلومتر برحسب متر و طول‌های بزرگ‌تر یا "
            "مساوی یک کیلومتر برحسب کیلومتر نمایش داده شده‌اند."
        ],
        tables=[Table("شناسنامه زون‌ها",
                      ["فیدر", "زون", "شناسه", "نوع", "طول",
                       "بار (kW)", "ترانس", "بارها", "گره", "یال"],
                      zone_table_rows,
                      note="منبع: درخت زون n-1 و مدل بار همین اجرای جایابی.")])

    # ---------------- ۴. رتبه‌بندی (گام ۶) -------------------------------
    rank_rows = []
    for r in m.placement.ranking.rows:
        rank_rows.append(
            [str(r.rank), r.feeder_key, f"{r.score:.4f}",
             _fmt(r.raw[0], 0), f"{r.raw[1]:.1f}٪", f"{r.raw[2]:.1f}٪",
             _fmt(r.raw[3], 0), f"{r.raw[4]:.2f}", f"{r.raw[5]:.1f}"])
    sec_rank = Section(
        id="ranking", title=f"۵. رتبه‌بندی فیدرها — فرمول (۱) و جدول ۱۶ (گام ۶)",
        intro=[
            "شش معیار رسمی با وزن‌های جدول ۱۶ (" + WEIGHTS_FA +
            ") محاسبه و با فرمول (۱) ترکیب شده‌اند: معیار ۱ معکوس "
            "تعداد ارتباطات (با سیاست رسمی «صفر ← ۱۰»، لنگر V-01)، "
            "معیارهای ۲ و ۳ از EP/TL جدول ۱۴، معیار ۴ مجموع اولویت بارها "
            "(جدول ۱۲) و معیارهای ۵ و ۶ از ماتریس λ/r فاز ۳. ماتریس کامل "
            "مقادیر خام، نرمال‌شده و وزن‌دار در کتاب کار Excel آمده است.",
        ],
        tables=[
            Table("جدول ۱۶ — امتیاز و رتبه فیدرها (مقادیر خام معیارها)",
                  ["رتبه", "فیدر", "امتیاز کل", "معیار ۱: ارتباطات",
                   "معیار ۲: EP", "معیار ۳: TL", "معیار ۴: اولویت بار",
                   "معیار ۵: λ (بر سال)", "معیار ۶: r (دقیقه)"], rank_rows,
                  note=f"وزن‌ها: {WEIGHTS_FA} — فرمول (۱) بند ۷-۷-۵، صفحه ۳۳."),
        ])

    # ---------------- ۵. طرح‌ها (گام ۷) -----------------------------------
    sch_rows = []
    for s in m.placement.schemes:
        sws = "؛ ".join(f"{sw.node} ({sw.kind})" for sw in s.switches)
        sch_rows.append([s.id[:14] + "…", SCHEME_KIND_FA.get(s.kind, s.kind),
                         ", ".join(s.feeders), str(len(s.switches)),
                         sws or "—"])
    sec_schemes = Section(
        id="schemes", title="۶. طرح‌های کلیدگذاری — جدول ۱۷ و پیوست ب (گام ۷)",
        intro=[
            "برای هر فیدر پُراولویت، قطعه‌بندی تنه اصلی با قاعده طلایی "
            "U×P (روابط ۹ و ۱۰) و برای جفت‌فیدرهای دارای ظرفیت انتقال، "
            "طرح ۱٫۵ کلیدی (رابطه ۱۱) تولید شده است. شناسه‌های گره، "
            "همان شناسه‌های لایه GIS هستند و مختصات دقیق مکان‌ها در "
            "پیوست الف و خروجی GIS آمده است.",
        ],
        tables=[
            Table("جدول ۱۷ — طرح‌های کاندید",
                  ["شناسه طرح", "نوع", "فیدرها", "تعداد کلید",
                   "مکان/نوع کلیدها (شناسه گره)"], sch_rows,
                  widths=[0.15, 0.17, 0.10, 0.08, 0.50]),
        ])

    # ---------------- ۶. مقایسه اقتصادی (گام ۸) -------------------------
    comp_rows = []
    for c in m.placement.economics.comparisons:
        ratio = "—" if c.ce_over_cn in (None, float("-inf")) \
            else f"{c.ce_over_cn:.4g}"
        comp_rows.append([
            SCHEME_KIND_FA.get(c.kind, c.kind), ", ".join(c.feeders),
            str(c.n_switches), _fmt(c.e2_before_kwh, 0),
            _fmt(c.e1_after_kwh, 0), _money(c.ce_rials), _money(c.cn_rials),
            ratio, "★ طرح اصلی" if c.selected else ""])
    sec_comp = Section(
        id="economics", title="۷. مقایسه اقتصادی طرح‌ها — جدول ۱۸ (گام ۸)",
        intro=[
            "CE صرفه‌ی ناشی از کاهش انرژی خاموشی (رابطه ۸) و CN هزینه "
            "سالانه‌شده طرح است؛ معیار انتخاب طبق بند ۷-۷-۷ بیشینهٔ "
            "CE/CN است. ستون «طرح اصلی» انتخاب نهایی هر اولویت را نشان "
            "می‌دهد. طرح‌های با CE صفر (بدون کاهش خاموشی) از انتخاب "
            "خارج‌اند و صرفاً برای شفافیت گزارش شده‌اند.",
        ],
        tables=[
            Table("جدول ۱۸ — مقایسه CE/CN",
                  ["نوع طرح", "فیدرها", "N", "E₂ قبل (kWh)",
                   "E₁ بعد (kWh)", "CE (ریال)", "CN (ریال)", "CE/CN",
                   "انتخاب"], comp_rows),
        ])

    # ---------------- ۷. طرح اصلی هر اولویت ------------------------------
    rec_rows = []
    for row in m.placement.recommendation:
        sws = "؛ ".join(f"{sw['node']} ({sw['kind']})"
                        for sw in row.get("switches", []))
        rec_rows.append([
            str(row["rank"]), row["feeder_key"],
            SCHEME_KIND_FA.get(row.get("scheme_kind") or "", "—")
            if row.get("scheme_kind") else "— (صرفه صفر)",
            str(row.get("n_switches") or 0), sws or "—"])
    sec_rec = Section(
        id="recommendation", title="۸. طرح اصلی برای هر اولویت",
        intro=[
            "جدول زیر جمع‌بندی اجرایی مطالعه است: برای هر فیدر به "
            "ترتیب اولویت، طرح منتخب (بیشینه CE/CN) و مکان کلیدها. "
            "این فهرست مبنای پیوست الف، خروجی GIS و ستاره‌های نقشه است.",
        ],
        tables=[
            Table("طرح منتخب هر فیدر",
                  ["رتبه", "فیدر", "طرح منتخب", "تعداد کلید",
                   "مکان/نوع کلیدها"], rec_rows),
        ],
        after=[map_note] if map_note else [])

    # ---------------- ۸. محدودیت‌ها و تصمیم‌ها ---------------------------
    issue_rows = [[c, {"Error": "خطا", "Warning": "هشدار",
                       "Information": "اطلاع"}.get(s, s), msg]
                  for c, s, msg in m.issues_all()] or \
        [["—", "—", "—"]]
    sec_issues = Section(
        id="issues", title="۹. محدودیت‌ها، تصمیم‌های باز و ثبت‌های بند ۱۹",
        intro=[
            "طبق بند ۱۹ هیچ شکاف مدلی بی‌صدا رد نمی‌شود: همه محدودیت‌های "
            "این اجرا با کد صریح ثبت شده‌اند. تصمیم‌های باز اصلی: λ از "
            "نرخ تصادفی کل (تصمیم ۱ فاز ۳)، منشأ و سطح مدل بار ثبت‌شده، "
            "و مقادیر ظرفیت نامی پیش‌فرض ۷۰۰۰ kW که باید توسط مهندس "
            "تأیید یا اصلاح شوند؛ بار پیک و ظرفیت اضطراری نیز مستقل از "
            "ظرفیت نامی نیازمند ورود/تأیید هستند.",
        ],
        tables=[Table("ثبت‌های این اجرا", ["کد", "شدت", "شرح"], issue_rows)])

    sections = [sec_sum, sec_method, sec_n1, sec_zones, sec_rank, sec_schemes,
                sec_comp, sec_rec, sec_issues]
    # شاخص‌های ارزیابی همهٔ فیدرها (λ، SAIDI/SAIFI، ENS…) بلافاصله پس از
    # خلاصهٔ مدیریتی — درخواست کاربر: همهٔ شاخص‌ها در گزارش بیاید.
    _ind_sec = _feeder_indices_section(m)
    if _ind_sec is not None:
        sections.insert(1, _ind_sec)

    # ---------------- پیوست الف: کاربرگ کلیدهای پیشنهادی -----------------
    prop = m.build_proposed()
    if prop:
        app_rows = []
        for p in prop:
            app_rows.append([
                p.feeder, p.node, p.kind_fa, str(p.order_in_scheme),
                str(p.zone_no) if p.zone_no is not None else "مرز",
                _fmt(p.x, 1), _fmt(p.y, 1),
                _fmt(p.lon, 6) if p.lon is not None else "—",
                _fmt(p.lat, 6) if p.lat is not None else "—",
            ])
        sec_appendix = Section(
            id="appendix", title="پیوست الف — کاربرگ اجرایی کلیدهای پیشنهادی",
            intro=[
                "مختصات X/Y در سیستم مختصات تحلیل (" + m.crs_label +
                ") و طول/عرض جغرافیایی تبدیل‌شده به WGS84 است تا هم "
                "عملیات میدانی و هم نرم‌افزارهای GIS بدون تبدیل اضافه "
                "بتوانند استفاده کنند. همین فهرست در قالب CSV و GeoJSON "
                "نیز کنار این گزارش خروجی گرفته می‌شود. کلیدهای نرمال‌باز "
                "طرح ۱٫۵ کلیدی روی مرز دو فیدر قرار دارند و ستون زون "
                "آن‌ها «مرز» ثبت می‌شود (خارج از هسته قطعی زون‌بندی n-1).",
            ],
            tables=[Table(
                "فهرست کلیدهای پیشنهادی (طرح‌های اصلی)",
                ["فیدر", "شناسه گره", "نوع کلید", "ترتیب در طرح",
                 "زون", "X (متر)", "Y (متر)", "طول جغرافیایی",
                 "عرض جغرافیایی"], app_rows,
                widths=[0.07, 0.26, 0.15, 0.06, 0.05, 0.11, 0.11, 0.095,
                        0.095])])
        sections.append(sec_appendix)

    # ---------------- ۱۰. محاسبات کامل (درخواست کاربر) -------------------
    # همه فرمول‌ها به‌صورت equation بومی Word (OMML) + مثال عددی واقعی
    # همین اجرا، تا «نحوه رسیدن به تمام داده‌های خروجی» در خود گزارش باشد.
    sec_calc = _build_calculations_section(m)
    sections.append(sec_calc)

    # ---------------- ۱۱. جایابی دستی (درخواست کاربر — مورد ۶) -----------
    # نتایج ارزیابی کلیدهای دستی مهندس (قبل/بعد روش سطح اول) در گزارش
    # نهایی می‌آید؛ مکان‌ها همان علامت‌های آبی نقشه گزارش‌اند.
    if m.manual_evals:
        sections.append(_build_manual_section(m))

    return ReportDoc(
        title="گزارش مطالعه جایابی کلید و برنامه‌ریزی اتوماسیون شبکه توزیع",
        subtitle="روش سطح اول دستورالعمل TAV122-02/00 توانیر — فاز ۴ "
                 "(گام‌های ۴ تا ۸)",
        meta=meta, kpis=kpis, sections=sections,
        footer=f"{APP_NAME} {__version__} — تولید خودکار؛ اعداد این گزارش "
               "با شناسه اجرای جایابی بالای گزارش بازتولیدپذیر است.")


#: ستون‌های جدول «شاخص‌های ارزیابی فیدرها» — (کلید، سرستون، تعداد اعشار)
FEEDER_INDEX_COLUMNS = (
    ("km", "طول (km)", 2),
    ("transformers", "ترانس", 0),
    ("lambda_per_year", "λ (۱/سال)", 2),
    ("lambda_reducible", "λ قابل کاهش", 2),
    ("r_minutes", "r (دقیقه)", 1),
    ("u_hours", "U=λr/60 (ساعت/سال)", 2),
    ("saidi", "SAIDI (دقیقه/سال)", 1),
    ("saifi", "SAIFI (قطع/سال)", 2),
    ("caidi", "CAIDI (دقیقه)", 1),
    ("asai", "ASAI (٪)", 4),
    ("ens_per_year_kwh", "ENS (kWh/سال)", 0),
    ("ens_before_kwh", "EENS پایه (kWh/سال)", 0),
    ("score", "امتیاز (فرمول ۱)", 4),
)


def _fmt_cell(value, nd: int) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "بله" if value else "خیر"
    if isinstance(value, (int, float)):
        return f"{value:,.{nd}f}"
    return str(value)


def feeder_index_rows(m: StudyModel) -> tuple[list, list]:
    """(سرستون‌ها، ردیف‌ها) برای جدول همهٔ شاخص‌های ارزیابی فیدرها."""
    headers = ["فیدر"] + [c[1] for c in FEEDER_INDEX_COLUMNS]
    rows = []
    for r in m.feeder_table():
        line = [r["feeder_key"]]
        for key, _label, nd in FEEDER_INDEX_COLUMNS:
            value = r.get(key)
            if key == "asai" and value is not None:
                value = float(value) * 100.0
            line.append(_fmt_cell(value, nd))
        rows.append(line)
    return headers, rows


def _feeder_indices_section(m: StudyModel) -> Section | None:
    """بخش «شاخص‌های ارزیابی فیدرها» — وقتی داده‌ای وجود دارد."""
    feeder_table = getattr(m, "feeder_table", None)   # مدل‌های سبک/قدیمی
    if feeder_table is None:
        return None
    rows = feeder_table()
    if not rows:
        return None
    headers, table_rows = feeder_index_rows(m)
    ind = m.feeder_indices or {}
    intro = [
        "این جدول همهٔ شاخص‌های ارزیابی‌شدهٔ هر فیدر را از همان اجراهای "
        "ثبت‌شدهٔ پروژه گرد می‌آورد: ردیابی (طول/ترانس)، ماتریس λ/r فاز ۳ "
        "(λ، r، U)، شاخص‌های پیوستگی SAIDI/SAIFI/CAIDI/ASAI و انرژی "
        "توزیع‌نشده (ENS) و EENS پایه. علامت «—» یعنی برای آن فیدر دادهٔ "
        "واقعی موجود نیست (صفر گزارش نمی‌شود).",
    ]
    if ind.get("has_result"):
        intro.append(
            f"شاخص‌های پیوستگی سامانه: SAIFI = {_fmt(ind.get('saifi'), 2)} "
            f"قطع/مشکل در سال، SAIDI = {_fmt(ind.get('saidi'), 1)} دقیقه در "
            f"سال، CAIDI = {_fmt(ind.get('caidi'), 1)} دقیقه و ASAI = "
            f"{_fmt((ind.get('asai') or 0) * 100, 4)}٪ "
            f"(جمع {('وزنی بر بار فیدرها' if ind.get('aggregation') == 'load-weighted' else 'میانگین سادهٔ فیدرها')}، "
            f"مبنای سهم مشترکین: {ind.get('load_basis') or '—'}، واحد انرژی: "
            f"{str(ind.get('energy_unit') or '—').upper()}).")
    tables = [Table("شاخص‌های ارزیابی فیدرها", headers, table_rows)]
    energy_rows = [f for f in ind.get("feeders", []) if f.get("energy_records")]
    if energy_rows:
        unit = str(ind.get("energy_unit") or "—").upper()
        intro.append("مجموع انرژی ثبت‌شده با ENS سالانه متفاوت است: ENS برابر مجموع انرژی تبدیل‌شده به kWh تقسیم بر سال مواجهه است. واحد خودکار صرفاً تخمین است و باید با منبع کنترل شود.")
        tables.append(Table("تطبیق انرژی خام با ENS سالانه", ["فیدر", "مجموع خام", "واحد فرض‌شده", "مواجهه (سال)", "ENS (kWh/سال)"],
                            [[f.get("feeder_key"), _fmt(f.get("energy_raw_total"), 4), unit, _fmt(f.get("exposure_years"), 4), _fmt(f.get("ens_kwh_per_year"), 2)] for f in energy_rows]))
    after = []
    notes = [str(n) for n in (ind.get("notes") or [])]
    if notes:
        after.append("محدودیت‌های محاسبهٔ شاخص‌های پیوستگی:")
        after.extend(f"• {n}" for n in notes)
    return Section(id="feeder_indices",
                   title="۱-ب. شاخص‌های ارزیابی فیدرها (λ، SAIDI/SAIFI، ENS)",
                   intro=intro, tables=tables, after=after)


def _total_load(m: StudyModel) -> float:
    """Σ شاخص بار فیدرهای مدل‌شده (جدول ۱۴) — kW."""
    return float(sum(f.total_load_kw for f in m.placement.n1.eptl))


def _build_manual_section(m: StudyModel) -> Section:
    """بخش جایابی دستی — نتایج ارزیابی کلیدهای دستی مهندس (مورد ۶)."""
    rows = []
    app_rows = []
    for ev in m.manual_evals:
        ratio = ev.get("ce_cn", {}).get("ce_over_cn")
        d = ev.get("delta", {})
        b = ev.get("before", {})
        a = ev.get("after", {})
        nodes = ", ".join(ev.get("switch_nodes") or []) or "—"
        rows.append([
            ev.get("feeder_key", ""), nodes,
            _fmt(b.get("ens_kwh"), 1), _fmt(a.get("ens_kwh"), 1),
            f"{d.get('ens_kwh', 0):+,.1f}",
            f"{d.get('ens_percent', 0):+.2f}٪",
            f"{b.get('ep_percent', 0):.1f} ← {a.get('ep_percent', 0):.1f}",
            f"{b.get('tl_percent', 0):.1f} ← {a.get('tl_percent', 0):.1f}",
            (f"{ratio:.4g}" if ratio not in (None, float("-inf")) else "—"),
            ev.get("verdict_fa", "")])
        # مختصات گره‌های دستی برای کاربرگ اجرایی
        for n in (ev.get("switch_nodes") or []):
            coord = m.node_coord(n)
            lon, lat = (None, None)
            if coord:
                ll = m.to_wgs84(coord[0], coord[1])
                if ll:
                    lon, lat = ll
            app_rows.append([
                ev.get("feeder_key", ""), n,
                _fmt(coord[0], 1) if coord else "—",
                _fmt(coord[1], 1) if coord else "—",
                _fmt(lon, 6) if lon is not None else "—",
                _fmt(lat, 6) if lat is not None else "—"])
    return Section(
        id="manual", title="۱۱. جایابی دستی کلید — ارزیابی مهندس (قبل/بعد)",
        intro=[
            "مهندس مکان‌هایی را به‌صورت دستی (کلیک روی نقشه یا مختصات "
            "UTM) برای کلید جدید پیشنهاد داده است. جدول زیر شاخص‌های "
            "روش سطح اول را قبل و بعد از نصب همین کلیدها مقایسه می‌کند؛ "
            "مکان‌ها با علامت آبی «Manual switch (evaluated)» روی نقشه "
            "گزارش مشخص شده‌اند. حکم هر ردیف، بهبود یا بدترشدن صریح "
            "است و هیچ اجباری برای پذیرش مکان دستی وجود ندارد.",
        ],
        tables=[
            Table("ارزیابی جایابی دستی — شاخص‌های قبل/بعد",
                  ["فیدر", "گره(های) کلید", "ENS قبل (kWh/سال)",
                   "ENS بعد (kWh/سال)", "ΔENS (kWh/سال)", "Δ٪",
                   "EP قبل ← بعد", "TL قبل ← بعد", "CE/CN", "حکم"],
                  rows or [["—"] * 10],
                  widths=[0.07, 0.16, 0.10, 0.10, 0.10, 0.07, 0.09,
                          0.09, 0.07, 0.15]),
            Table("مختصات کلیدهای دستی (کاربرگ اجرایی)",
                  ["فیدر", "شناسه گره", "X (متر)", "Y (متر)",
                   "طول جغرافیایی", "عرض جغرافیایی"],
                  app_rows or [["—"] * 6],
                  widths=[0.12, 0.30, 0.15, 0.15, 0.14, 0.14]),
        ],
        after=["این ارزیابی با همان موتور جایابی خودکار (درخت قطعات + "
               "رابطه ۸ + انتقال Tie) انجام شده است؛ بنابراین اعداد "
               "جایابی دستی مستقیماً با طرح‌های بخش ۷ قابل مقایسه‌اند."])


def _worst_zone_label(m: StudyModel, f) -> str:
    """بدترین زون به شماره زون (نه شناسه خام) — از درخت‌های strict فاز ۴."""
    wz = getattr(f.ep, "worst_zone", None)
    if wz is None:
        return "—"
    for tree in m.placement.n1.trees.values():
        for z in tree.zones:
            if z.id == wz:
                return f"زون {z.zone_no}"
    return "مرز"


def _method_rows(m: StudyModel) -> list:
    snap = m.placement.settings
    n1s = snap.get("n1", {})
    pls = snap.get("placement", {})
    rks = snap.get("ranking", {})
    from ..reliability.load_model import LEVEL_FA
    load_level = (m.placement.load_model or {}).get("level", "")
    return [
        ["مدل ناحیه تحلیل (area_mode)",
         "هسته قطعی فیدرها (کلید نامشخص = باز)" if snap.get("area_mode") == "strict"
         else "ردیابی عادی فیدرها"],
        ["مدل بار فعال", LEVEL_FA.get(load_level, load_level or "نامشخص")],
        ["پروکسی بار قدیمی n-1",
         {"transformer_capacity": "ظرفیت ترانس (legacy)",
          }.get(n1s.get("load_proxy"), n1s.get("load_proxy"))],
        ["انتقال فقط با اتوماسیون",
         "بله" if n1s.get("automation_only_transfer") else "خیر"],
        ["ظرفیت نامی فیدرها (kW)",
         str(n1s.get("feeder_rated_kw") or "تنظیم‌نشده (A-10)")],
        ["وزن‌های جدول ۱۶", "، ".join(str(w) for w in rks.get("weights", []))],
        ["مبنای λ", "نرخ تصادفی کل (تصمیم باز ۱ فاز ۳)"
         if rks.get("lambda_source") == "total_random" else "λ کاهش‌پذیر"],
        ["مبنا معیار ۴", "مجموع اولویت بار وزن‌شده با بار (A-14)"
         if rks.get("criterion4_mode") == "load_weighted"
         else "مجموع ساده اولویت‌ها"],
        ["بیشینه فیدرهای ورودی گام ۷", _fmt(pls.get("max_feeders"), 0)],
        ["زون‌های هدف قطعه‌بندی قاعده طلایی",
         _fmt(pls.get("target_zones"), 0)],
        ["بیشینه طرح‌های ۱٫۵ کلیدی", _fmt(pls.get("max_tie_schemes"), 0)],
    ]


# ---------------------------------------------------------------------------
# بخش ۹ — محاسبات کامل (درخواست کاربر: «محاسبات به همراه تمام فرمول‌بندی
# و نحوه رسیدن به تمام داده‌های خروجی در گزارش ارائه شود»)
# ---------------------------------------------------------------------------
def _build_calculations_section(m: StudyModel) -> Section:
    """فرمول‌ها (equation بومی ورد) + مثال عددی واقعی همین اجرا."""
    from .equations import ALL_EQUATIONS
    eqs = [Equation(caption=c, omml=om, text=tx, note=n)
           for c, om, tx, n in ALL_EQUATIONS]

    intro = [
        "این بخش «نحوه رسیدن» به همه خروجی‌های مطالعه را مستند می‌کند: "
        "ابتدا فرمول هر شاخص به‌صورت معادله بومی Word (قابل ویرایش در "
        "خود Word با دابل‌کلیک) و سپس مثال عددی واقعی همین اجرا. زنجیره "
        "داده: GIS (ظرفیت ترانس/طول خط) → مدل بار → ماتریس λ/r فاز ۳ → "
        "تحلیل n-1 (جداول ۱۳-۱۵) → رتبه‌بندی فرمول (۱) → طرح‌های جدول "
        "۱۷ → مقایسه اقتصادی جدول ۱۸.",
    ]

    # --- مثال عددی ۱: مدل بار ------------------------------------------------
    lm = getattr(m.placement, "load_model", {}) or {}
    load_rows = []
    plan = lm.get("scaling_plan") or {}
    if lm.get("level") == "scaled" and plan:
        for fk, pf in sorted(plan.items()):
            load_rows.append([
                fk, _fmt(pf.get("p_kw"), 0), _fmt(pf.get("q_kvar"), 0),
                _fmt(pf.get("s_load_kva"), 1), _fmt(pf.get("sum_s_rated_kva"), 0),
                f"{pf.get('cos_phi', 0.0):.4f}", f"{pf.get('k_scale', 0.0):.5f}",
                str(pf.get("n_transformers", 0))])
        load_note = ("S_load و cosφ و K برای هر فیدر مستقیماً از ورودی‌های "
                     "P/Q کاربر و جمع ظرفیت نامی ترانس‌های همان فیدر "
                     "(برچسب GIS) محاسبه شده است.")
    else:
        cov = lm.get("coverage") or {}
        load_rows = [[lm.get("level", "—"), _fmt(cov.get("factor"), 2),
                      _fmt(cov.get("nodes_total"), 0), "—", "—", "—", "—",
                      "—"]]
        load_note = ("سطح فعال مدل بار در این اجرا Load Scaling نبوده است؛ "
                     "برای فعال‌سازی، سطح «مقیاس‌شده» را در تنظیمات "
                     "مهندسی انتخاب و P/Q هر فیدر را وارد کنید.")
    tbl_load = Table("محاسبات مدل بار (به تفکیک فیدر)",
                     ["فیدر", "P (kW)", "Q (kVAr)", "S_load (kVA)",
                      "ΣS_rated (kVA)", "cos φ", "K", "تعداد ترانس"],
                     load_rows or [["—"] * 8], note=load_note)

    # --- مثال عددی ۲: λ/r و U ------------------------------------------------
    lam_rows = []
    for r in m.placement.ranking.rows:
        lam = float(r.raw[4]) if len(r.raw) > 4 else 0.0
        rmin = float(r.raw[5]) if len(r.raw) > 5 else 0.0
        u = lam * rmin / 60.0
        lam_rows.append([r.feeder_key, f"{lam:.2f}", f"{rmin:.1f}",
                         f"{u:.3f}"])
    tbl_lam = Table("محاسبات λ/r و نرخ خاموشی سالانه (U = λ×r/60)",
                    ["فیدر", "λ (فالت/سال)", "r (دقیقه)",
                     "U (ساعت/سال)"], lam_rows or [["—"] * 4],
                    note="λ و r از ماتریس فاز ۳ (خاموشی‌های واقعی با پوشش "
                         "داده واقعی) می‌آیند؛ U ورودی رابطه (۸) است.")

    # --- مثال عددی ۳: EP/TL بدترین فیدر --------------------------------------
    ep_rows = []
    for f in m.placement.n1.eptl:
        load = f.total_load_kw
        shed = load * f.ep.ep_percent / 100.0
        rest = load * f.ep.tl_percent / 100.0
        ep_rows.append([f.feeder_key, _fmt(load, 0), _fmt(shed, 1),
                        _fmt(rest, 1), f"{f.ep.ep_percent:.1f}٪",
                        f"{f.ep.tl_percent:.1f}٪"])
    tbl_eptl = Table(
        "محاسبات EP/TL (بدترین خطای تک‌زونه — جدول ۱۴)",
        ["فیدر", "ΣP (kW)", "بیشینه بار خاموش‌شده (kW)",
         "بیشینه بازپل‌شدنی (kW)", "EP", "TL"], ep_rows or [["—"] * 6],
        note="EP = 100×بیشینه خاموش‌شده/ΣP و TL = 100×بیشینه بازپل‌شدنی/ΣP "
             "(مقسوم‌علیه همان بار فیدر است).")

    # --- مثال عددی ۴: ENS هر فیدر قبل/بعد + جدول ۱۸ --------------------------
    ens_rows = []
    rec_by = {r["feeder_key"]: r for r in m.placement.recommendation}
    for fk, before in sorted(m.placement.economics.ens_before_kwh.items()):
        rec = rec_by.get(fk) or {}
        sid = rec.get("scheme_id")
        after = (m.placement.economics.ens_after_kwh.get(sid, {}) or {}).get(
            fk, before) if sid else before
        d = before - after
        pct = (100.0 * d / before) if before > 0 else 0.0
        ens_rows.append([fk, _fmt(before, 1), _fmt(after, 1),
                         _fmt(d, 1), f"{pct:.2f}٪"])
    tbl_ens = Table(
        "انرژی توزیع‌نشده هر فیدر — قبل و بعد از طرح اصلی (درخواست کاربر)",
        ["فیدر", "ENS قبل (kWh/سال)", "ENS بعد (kWh/سال)",
         "کاهش (kWh/سال)", "درصد کاهش"], ens_rows or [["—"] * 5],
        note="ENS از رابطه (۸) روی درخت قطعات فیدر محاسبه می‌شود؛ «بعد» "
             "طرح اصلی همان فیدر (بیشینه CE/CN) است و برای فیدر بدون طرح، "
             "بعد = قبل.")
    return Section(
        id="calculations",
        title="۱۰. محاسبات کامل — فرمول‌ها و مثال عددی همین اجرا",
        intro=intro, equations=eqs,
        tables=[tbl_load, tbl_lam, tbl_eptl, tbl_ens],
        after=[
            "تمام اعداد جدول‌های بالا از همان مقادیری محاسبه شده‌اند که "
            "در بخش‌های ۳ تا ۷ گزارش آمده‌اند؛ برای بازتولید دستی هر "
            "عدد، فرمول متناظر را روی ستون‌های همان بخش اعمال کنید. "
            "فرمول‌ها در Word با دابل‌کلیک قابل ویرایش‌اند (Insert ▸ "
            "Equation) و به همین شکل در قالب PDF نیز به‌صورت متن "
            "استاندارد آمده‌اند.",
        ])


# ---------------------------------------------------------------------------
# گزارش نهایی مطالعهٔ EENS — فقط همان مطالعه (بدون آیتم اضافی)
# ---------------------------------------------------------------------------
def _build_eens_report(m: StudyModel, map_note: str = "") -> ReportDoc:
    """گزارش Word/PDF بر اساس مطالعهٔ جایابی کلید ذخیره‌شده در پروژه."""
    from .eens_report import build_eens_sections

    prof, sections = build_eens_sections(m.eens_study, map_note=map_note)
    from ..reliability.load_model import LEVEL_FA
    meta = [
        ("نام پروژه", m.name),
        ("تاریخ گزارش", datetime.now().strftime("%Y-%m-%d")),
        ("نوع مطالعه", prof["scope_fa"]),
        ("نوع محاسبهٔ EENS", prof["method_fa"]),
        ("نوع کلید", prof["switch_type_fa"]),
        ("مدل بار", LEVEL_FA.get(str(prof["level"]), prof["level_fa"])),
        ("فیدرهای مطالعه", "، ".join(prof["studied_feeders"]) or "—"),
        ("نرم‌افزار / نسخه", f"{APP_NAME} {__version__}"),
        ("پایگاه داده پروژه", m.db_path or "—"),
        ("سیستم مختصات تحلیل", m.crs_label),
    ]
    kpis = [
        ("تعداد فیدر مطالعه‌شده", str(len(prof["studied_feeders"]))),
        ("EENS پایه (MWh/سال)", f"{prof['baseline_mwh']:,.3f}"),
        ("EENS پس از جایابی (MWh/سال)", f"{prof['best_mwh']:,.3f}"),
        ("کاهش EENS (٪)", f"{prof['improvement']:.2f}"),
        ("کلیدهای پیشنهادی", str(prof["switches"])),
    ]
    summary = Section(
        id="eens_summary", title="۱. خلاصهٔ مدیریتی",
        intro=[
            f"این گزارش یک مطالعهٔ **{prof['scope_fa']}** از «جایابی "
            f"بهینهٔ کلید و کاهش EENS» با روش **{prof['method_fa']}** و "
            f"نوع کلید **{prof['switch_type_fa']}** است.",
            f"EENS سالانه از {prof['baseline_mwh']:,.3f} به "
            f"{prof['best_mwh']:,.3f} مگاوات‌ساعت کاهش می‌یابد "
            f"(**{prof['improvement']:.2f}٪**) و برای این کاهش "
            f"{prof['switches']} کلید پیشنهاد می‌شود. اعداد این گزارش "
            "همان خروجی ذخیره‌شدهٔ موتور است و بازمحاسبه نشده‌اند.",
        ],
        tables=[Table("شاخص‌های کلیدی", ["شاخص", "مقدار"],
                      [[a, b] for a, b in kpis])])
    return ReportDoc(
        title="گزارش مطالعهٔ جایابی بهینهٔ کلید و کاهش EENS",
        subtitle=f"روش سطح اول TAV122-02/00 — نوع مطالعه: {prof['scope_fa']} · "
                 f"EENS: {prof['method_fa']} · کلید: {prof['switch_type_fa']}",
        meta=meta, kpis=kpis,
        sections=[summary] + ([_ind_sec] if (_ind_sec := _feeder_indices_section(m)) else [])
        + sections,
        footer=f"{APP_NAME} {__version__} — گزارش خودکار از خروجی موتور "
               "جایابی کلید (بازتولیدپذیر با شناسهٔ اجرا).")
