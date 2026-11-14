# -*- coding: utf-8 -*-
"""eens_report.py — بخش‌های گزارش نهایی برای «مطالعهٔ جایابی کلید / EENS».

گزارش نهایی نرم‌افزار باید **دقیقاً** با نوع مطالعه‌ای که انجام شده بخواند
(درخواست کاربر v1.15). این ماژول همان مطالعهٔ ذخیره‌شده در پروژه
(``project_kv['sectionalizer_study']``) را به بخش‌های آماده‌برای رندر
تبدیل می‌کند: نوع مطالعه (تک‌فیدره / چندفیدره / کلی)، نوع EENS
(دایرکشنال / یکنواخت / دستی)، سطح مدل بار، λ و r مؤثر هر فیدر با منبع
هر عدد، نتیجهٔ فیدرها، کلیدهای پیشنهادی، گام‌های بهینه‌سازی و
**فرمول‌بندی کامل موتور**.

هیچ بخشی که در این مطالعه وجود ندارد ساخته نمی‌شود (بدون آیتم اضافی) و
هیچ عددی بازمحاسبه نمی‌شود؛ همه از خروجی موتور می‌آید.
"""
from __future__ import annotations

from .content import Equation, Section, Table
from .equations import EENS_EQUATIONS

#: نام فارسی روش‌ها/نوع‌ها (هم‌ارز ماژول موتور — بدون import چرخشی)
SCOPE_FA = {
    "single": "تک‌فیدره",
    "multi": "چندفیدره",
    "all": "کلی (همهٔ فیدرهای مدل‌شده)",
    "none": "بدون فیدر",
}
METHOD_FA = {
    "directional": "دایرکشنال (جهت‌دار) — λ و r واقعی خاموشی",
    "uniform": "یکنواخت (هم‌ارز کد مرجع) — λ و r واقعی خاموشی",
    "manual": "دستی — λ و r ورودی کاربر",
}
SWITCH_FA = {
    "recloser": "ریکلوزر",
    "sectionalizer": "سکشنالایزر",
    "disconnector": "سکسیونر",
}
LEVEL_FA = {
    "actual": "واقعی (Actual) — ورودی مهندس",
    "scaled": "مقیاس‌شده با Load Scaling (سطح ۱)",
    "estimated": "تخمینی (ظرفیت ترانس × ضریب بارگذاری)",
    "": "نامشخص",
}


def _num(v, nd=1) -> str:
    try:
        if v is None:
            return "—"
        return f"{float(v):,.{nd}f}"
    except (TypeError, ValueError):
        return "—"


def eens_profile(study: dict | None) -> dict:
    """خلاصهٔ «نوع مطالعه» از payload ذخیره‌شدهٔ موتور."""
    payload = dict(study or {})
    st = dict(payload.get("study") or payload or {})
    settings = dict(st.get("settings") or {})
    feeders = list(st.get("feeders") or [])
    studied = list(settings.get("studied_feeders")
                   or [f.get("feeder_key") for f in feeders if f.get("feeder_key")])
    all_keys = list(settings.get("all_feeders") or [])
    if not studied:
        scope = "none"
    elif len(studied) <= 1:
        scope = "single"
    elif all_keys and set(studied) >= set(all_keys):
        scope = "all"
    else:
        scope = "multi"
    method = (settings.get("method") or settings.get("restoration_model")
              or "uniform")
    return {
        "scope": scope,
        "scope_fa": SCOPE_FA.get(scope, scope),
        "method": method,
        "method_fa": METHOD_FA.get(method, method),
        "switch_type": settings.get("switch_type", "sectionalizer"),
        "switch_type_fa": SWITCH_FA.get(settings.get("switch_type", ""),
                                        settings.get("switch_type_fa", "")),
        "level": settings.get("load_model_level", ""),
        "level_fa": LEVEL_FA.get(str(settings.get("load_model_level", "")),
                                 str(settings.get("load_model_level", "—"))),
        "studied_feeders": studied,
        "all_feeders": all_keys,
        "feeders": feeders,
        "settings": settings,
        "assumptions": list(st.get("assumptions") or []),
        "notes": list(st.get("notes") or []),
        "baseline_mwh": float(st.get("total_baseline_eens_kwh_per_year")
                              or 0.0) / 1000.0,
        "best_mwh": float(st.get("total_best_eens_kwh_per_year")
                          or 0.0) / 1000.0,
        "improvement": float(st.get("total_improvement_percent") or 0.0),
        "switches": int(st.get("total_selected_switches") or 0),
        "algo_version": str(payload.get("algo_version") or ""),
    }


def is_eens_study(study: dict | None) -> bool:
    """آیا این payload یک مطالعهٔ EENS معتبر است؟"""
    if not study:
        return False
    st = study.get("study") if isinstance(study, dict) else None
    return bool(st and (st.get("feeders") or st.get("settings")))


# ---------------------------------------------------------------------------
def _rate_rows(prof: dict) -> list[list[str]]:
    rows = []
    for f in prof["feeders"]:
        rows.append([
            str(f.get("feeder_key", "")),
            _num(f.get("failure_rate_per_year"), 2),
            str(f.get("failure_rate_source", "")),
            _num(f.get("repair_time_min"), 1),
            _num(f.get("transient_rate_per_year"), 2),
        ])
    return rows


def _result_rows(prof: dict) -> list[list[str]]:
    rows = []
    for f in prof["feeders"]:
        sel = (f.get("best") or {}).get("selected") or []
        labels = "؛ ".join(str(c.get("label", "")) for c in sel) or "—"
        rows.append([
            str(f.get("feeder_key", "")),
            _num(f.get("line_length_km"), 2),
            _num(f.get("total_load_kw"), 1),
            str(f.get("existing_section_count", 0)),
            str(f.get("candidate_count", 0)),
            _num(f.get("baseline_eens_mwh_per_year"), 4),
            str(len(sel)),
            _num(f.get("best_eens_mwh_per_year"), 4),
            _num(f.get("improvement_percent"), 2),
            labels,
        ])
    return rows


def _switch_rows(prof: dict) -> list[list[str]]:
    rows = []
    for f in prof["feeders"]:
        for c in ((f.get("best") or {}).get("selected") or []):
            coord = c.get("coord") or (None, None)
            rows.append([
                str(f.get("feeder_key", "")),
                str(c.get("label", "")),
                str(c.get("node", "")),
                str(c.get("depth", "")),
                _num(c.get("downstream_load_kw"), 1),
                _num(c.get("downstream_length_km"), 3),
                str(c.get("zone_id", "") or "—"),
                _num(coord[0], 1) if coord and coord[0] is not None else "—",
                _num(coord[1], 1) if len(coord) > 1 and coord[1] is not None
                else "—",
            ])
    return rows


def _step_rows(prof: dict) -> list[list[str]]:
    rows = []
    for f in prof["feeders"]:
        for st in (f.get("steps") or []):
            sel = st.get("selected") or []
            rows.append([
                str(f.get("feeder_key", "")),
                str(st.get("count", "")),
                _num(st.get("eens_kwh_per_year"), 1),
                _num(st.get("improvement_percent"), 2),
                str(sel[-1].get("label", "")) if sel else "—",
            ])
    return rows


def build_eens_sections(study: dict, map_note: str = "") -> tuple[dict, list]:
    """(پروفایل مطالعه، فهرست بخش‌های گزارش) — بدون بخش اضافی."""
    prof = eens_profile(study)
    settings = prof["settings"]
    sections: list[Section] = []

    # --- ۱. نوع مطالعه و ورودی‌ها ------------------------------------
    input_rows = [
        ["نوع مطالعه (دامنه)", prof["scope_fa"]],
        ["نوع محاسبهٔ EENS", prof["method_fa"]],
        ["نوع کلید جایابی‌شده", prof["switch_type_fa"]],
        ["سطح مدل بار", prof["level_fa"]],
        ["فیدرهای مطالعه", "، ".join(prof["studied_feeders"]) or "—"],
        ["تعداد فیدرهای مدل‌شده", str(len(prof["all_feeders"]))
         if prof["all_feeders"] else "—"],
        ["λ پیش‌فرض تنظیمات (خرابی/سال)",
         _num(settings.get("total_failure_rate_per_year"), 2)],
        ["زمان تعمیر پیش‌فرض (دقیقه)",
         _num(settings.get("repair_time_min"), 1)],
        ["زمان بازیابی بار سالم (دقیقه)",
         _num(settings.get("restoration_time_min"), 1)],
        ["سقف کلید هر فیدر", str(settings.get("max_sectionalizers", "—"))],
        ["حداقل عمق کاندید", str(settings.get("min_candidate_depth", "—"))],
        ["حداکثر سهم بار پایین‌دست",
         _num(100.0 * float(settings.get("max_downstream_load_ratio") or 0), 0)
         + "٪"],
        ["استفاده از کلیدهای موجود",
         "بله" if settings.get("use_existing_switches") else "خیر"],
    ]
    if settings.get("switch_type") == "recloser":
        input_rows += [
            ["آستانهٔ خطای گذرا (دقیقه)",
             _num(settings.get("transient_max_duration_min"), 2)],
            ["وقفهٔ گذرا (دقیقه)",
             _num(settings.get("transient_interruption_min"), 2)],
            ["زمان وصل مجدد (دقیقه)",
             _num(settings.get("reclose_time_min"), 2)],
            ["احتمال موفقیت وصل مجدد",
             _num(100.0 * float(settings.get("reclose_success_probability") or 0), 0)
             + "٪"],
        ]
    sections.append(Section(
        id="eens_inputs",
        title="۲. نوع مطالعه، ورودی‌ها و λ/r مؤثر هر فیدر",
        intro=[
            "این گزارش مطالعهٔ **جایابی بهینهٔ کلید و کاهش EENS** است؛ "
            "ساختار آن دقیقاً از نوع مطالعهٔ اجراشده پیروی می‌کند: همان "
            "دامنه (تک‌فیدره / چندفیدره / کلی)، همان روش EENS و همان "
            "فیدرهایی که محاسبه شده‌اند.",
            "λ و r هر فیدر از **ماتریس λ/r خاموشی‌های واقعی همان پروژه** "
            "خوانده می‌شود. مقدار پیش‌فرض تنظیمات فقط برای فیدرهایی به‌کار "
            "می‌رود که دادهٔ واقعی ندارند و در ستون «منبع» با "
            "`configured-default` علامت خورده است — هیچ عدد پیش‌فرضی "
            "بی‌برچسب استفاده نشده است.",
        ],
        tables=[
            Table("ورودی‌های اجرا", ["ورودی", "مقدار"], input_rows),
            Table("λ و r مؤثر هر فیدر (با منبع هر عدد)",
                  ["فیدر", "λ (خرابی/سال)", "منبع λ", "r (دقیقه)",
                   "λ گذرا (خرابی/سال)"],
                  _rate_rows(prof) or [["—"] * 5],
                  note="منبع `outage-lambda` یعنی مقدار واقعی از ماتریس "
                       "خاموشی؛ `configured-default` یعنی مقدار پیش‌فرض "
                       "تنظیمات."),
        ]))

    # --- ۲. نتیجهٔ فیدرها --------------------------------------------
    sections.append(Section(
        id="eens_results",
        title="۳. نتیجهٔ فیدرها — EENS پایه و پس از جایابی",
        intro=[
            "EENS پایه، وضعیت فعلی شبکه با کلیدهای موجود است و EENS نهایی "
            "پس از نصب کلیدهای پیشنهادی همان فیدر. جست‌وجو حریصانه و "
            "گام‌به‌گام است: در هر گام کاندیدی که بیشترین کاهش EENS را "
            "بدهد انتخاب می‌شود.",
        ],
        tables=[Table(
            "خلاصهٔ فیدرها",
            ["فیدر", "طول (km)", "بار (kW)", "قطعه موجود", "کاندید",
             "EENS پایه (MWh/سال)", "کلید پیشنهادی", "EENS نهایی (MWh/سال)",
             "کاهش (٪)", "کلیدهای پیشنهادی"],
            _result_rows(prof) or [["—"] * 10],
            widths=[0.07, 0.07, 0.08, 0.06, 0.06, 0.10, 0.07, 0.10, 0.07,
                    0.32])],
        after=[f"**جمع کل:** EENS پایه {prof['baseline_mwh']:,.3f} "
               f"MWh/سال → {prof['best_mwh']:,.3f} MWh/سال "
               f"(کاهش {prof['improvement']:.2f}٪ با {prof['switches']} "
               "کلید)." + (f" {map_note}" if map_note else "")]))

    # --- ۳. کلیدهای پیشنهادی ----------------------------------------
    switches = _switch_rows(prof)
    if switches:
        sections.append(Section(
            id="eens_switches",
            title="۴. کلیدهای پیشنهادی (مکان و مشخصات)",
            intro=[
                "مکان هر کلید با شناسهٔ گرهٔ شبکه و مختصات سیستم تحلیل "
                "(متر) آمده است؛ همین نقاط روی نقشهٔ گزارش با نشانگر "
                "«سکشنالایزر پیشنهادی» مشخص شده‌اند.",
            ],
            tables=[Table(
                "فهرست کلیدهای پیشنهادی",
                ["فیدر", "شناسه/برچسب", "گره", "عمق", "بار پایین‌دست (kW)",
                 "طول پایین‌دست (km)", "زون", "X (متر)", "Y (متر)"],
                switches,
                widths=[0.07, 0.24, 0.17, 0.05, 0.11, 0.11, 0.05, 0.10,
                        0.10])]))

    # --- ۴. گام‌های بهینه‌سازی ---------------------------------------
    steps = _step_rows(prof)
    if steps:
        sections.append(Section(
            id="eens_steps",
            title="۵. گام‌های بهینه‌سازی (حریصانه)",
            intro=["هر گام یک کلید اضافه می‌کند و EENS را بازمحاسبه "
                   "می‌کند؛ وقتی بهبود از آستانهٔ معنادار کمتر شد "
                   "جست‌وجو متوقف می‌شود."],
            tables=[Table("گام‌ها", ["فیدر", "گام", "EENS پس از گام "
                                     "(kWh/سال)", "کاهش تجمعی (٪)",
                                     "کلید افزوده"], steps)]))

    # --- ۵. محاسبات کامل — فرمول‌بندی موتور -------------------------
    equations = [Equation(caption=c, omml=om, text=tx, note=n)
                 for c, om, tx, n in EENS_EQUATIONS]
    sections.append(Section(
        id="eens_calculations",
        title="۶. محاسبات کامل — فرمول‌بندی موتور EENS",
        intro=[
            "همهٔ روابطی که موتور برای همین مطالعه اجرا کرده است، به‌صورت "
            "معادلهٔ بومی Word (قابل ویرایش با دابل‌کلیک) و متن ساده "
            "آمده است. اعداد جدول‌های قبلی دقیقاً از همین روابط "
            "به‌دست آمده‌اند.",
            f"روش اجراشده در این مطالعه: **{prof['method_fa']}** — "
            f"بنابراین رابطهٔ EENS متناظر همان روش، رابطهٔ حاکم است"
            + ("؛ رابطهٔ خطای گذرا نیز فعال بود (نوع کلید: ریکلوزر)."
               if prof["switch_type"] == "recloser" else "."),
        ],
        equations=equations))

    # --- ۶. فرض‌ها و هشدارها ----------------------------------------
    if prof["assumptions"] or prof["notes"]:
        rows = [["فرض", a] for a in prof["assumptions"]]
        rows += [["هشدار/یادداشت", n] for n in prof["notes"]]
        sections.append(Section(
            id="eens_notes",
            title="۷. فرض‌ها، محدودیت‌ها و هشدارها",
            intro=["طبق قاعدهٔ «هیچ شکاف مدلی بی‌صدا رد نمی‌شود»، همهٔ "
                   "فرض‌ها و هشدارهای همین اجرا ثبت شده‌اند."],
            tables=[Table("فرض‌ها و هشدارها", ["نوع", "شرح"], rows)]))
    return prof, sections
