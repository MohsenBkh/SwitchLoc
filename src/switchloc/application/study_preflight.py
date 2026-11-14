# -*- coding: utf-8 -*-
"""study_preflight.py — بازبینی کامل ورودی‌ها **قبل از** اجرای جایابی EENS.

درخواست کاربر (v1.15): «قبل از اجرای جایابی بهینهٔ EENS پنجرهٔ ری‌چک کامل
ورودی‌ها باز شود؛ در حالت فعلی با دادهٔ بار پیش‌فرض کار می‌کند.»

این ماژول Qt-free است: از ورودی‌های مؤثرِ همان اجرا یک «چک‌لیست» می‌سازد
و برای هر ردیف یکی از سه وضعیت را می‌دهد:

* ``ok``     — مقدار صریح و کامل است؛
* ``warn``   — مقدار پیش‌فرض/تخمینی است؛ اجرا مجاز است ولی نتیجه باید با
               همین برچسب خوانده شود؛
* ``error``  — ورودی ناقص/ناسازگار است؛ اجرا نباید شروع شود.

هیچ عددی در این ماژول ساخته نمی‌شود؛ فقط وضعیت ورودی‌های واقعی گزارش
می‌شود تا کاربر بداند با چه داده‌ای اجرا می‌کند.
"""
from __future__ import annotations

from dataclasses import dataclass, field

STATUS_FA = {"ok": "درست", "warn": "هشدار", "error": "خطا"}

METHOD_FA = {
    "directional": "دایرکشنال (λ و r واقعی خاموشی)",
    "uniform": "یکنواخت (λ و r واقعی خاموشی)",
    "manual": "دستی (ورودی کاربر)",
}
SWITCH_FA = {"recloser": "ریکلوزر", "sectionalizer": "سکشنالایزر",
             "disconnector": "سکسیونر"}
LOAD_LEVEL_FA = {
    "actual": "واقعی (ورودی مهندس)",
    "scaled": "مقیاس‌شده با Load Scaling",
    "estimated": "تخمینی (ظرفیت ترانس × ضریب) — پیش‌فرض",
    "": "تعیین‌نشده — پیش‌فرض تخمینی",
}


@dataclass
class PreflightRow:
    group: str
    item: str
    value: str
    status: str = "ok"
    note: str = ""


@dataclass
class PreflightReport:
    rows: list = field(default_factory=list)      # [PreflightRow]
    method: str = ""
    switch_type: str = ""

    @property
    def errors(self) -> list:
        return [r for r in self.rows if r.status == "error"]

    @property
    def warnings(self) -> list:
        return [r for r in self.rows if r.status == "warn"]

    @property
    def blocking(self) -> bool:
        """آیا اجرا باید متوقف شود؟ (فقط خطاها مانع‌اند)"""
        return bool(self.errors)

    @property
    def counts(self) -> dict:
        return {s: sum(1 for r in self.rows if r.status == s)
                for s in ("ok", "warn", "error")}

    def summary_fa(self) -> str:
        c = self.counts
        return (f"{c['ok']} ورودی درست · {c['warn']} هشدار · "
                f"{c['error']} خطا")


def _fmt(v, nd=2) -> str:
    try:
        return f"{float(v):,.{nd}f}"
    except (TypeError, ValueError):
        return "—" if v in (None, "") else str(v)


def build_preflight(*, method: str, switch_type: str,
                    engine: dict | None = None,
                    load_model: dict | None = None,
                    load_total_kw: float | None = None,
                    feeders: list | None = None,
                    all_feeders: list | None = None,
                    outage_rates: dict | None = None,
                    repair_times: dict | None = None,
                    explicit_rates: dict | None = None,
                    backup_kw: dict | None = None,
                    s_rated_kva: dict | None = None,
                    outage_available: bool = True) -> PreflightReport:
    """چک‌لیست ورودی‌های اجرای جایابی EENS (بدون Qt)."""
    eng = dict(engine or {})
    lm = dict(load_model or {})
    feeders = [str(k) for k in (feeders or [])]
    all_feeders = [str(k) for k in (all_feeders or [])]
    rates = {str(k): float(v) for k, v in (outage_rates or {}).items()
             if v is not None}
    reps = {str(k): float(v) for k, v in (repair_times or {}).items()
            if v is not None}
    explicit = {str(k): float(v) for k, v in (explicit_rates or {}).items()
                if v is not None}
    rows: list[PreflightRow] = []

    def add(group, item, value, status="ok", note=""):
        rows.append(PreflightRow(group=group, item=item, value=value,
                                 status=status, note=note))

    # ---- ۱. نوع مطالعه ------------------------------------------------
    auto = method in ("directional", "uniform")
    add("نوع مطالعه", "روش محاسبهٔ EENS", METHOD_FA.get(method, method))
    add("نوع مطالعه", "نوع کلید", SWITCH_FA.get(switch_type, switch_type))
    add("نوع مطالعه", "دامنه (فیدرهای انتخاب‌شده)",
        "، ".join(feeders) if feeders else "هیچ فیدری انتخاب نشده",
        "ok" if feeders else "error",
        f"از {len(all_feeders)} فیدر مدل‌شده" if all_feeders else "")
    add("نوع مطالعه", "منبع λ/r",
        "ماتریس λ/r خاموشی واقعی" if auto else "ورودی دستی کاربر",
        "ok" if (auto and outage_available) else ("ok" if not auto else "warn"),
        "" if outage_available else
        "هیچ تحلیل خاموشی ذخیره‌شده‌ای در پروژه نیست؛ λ پیش‌فرض استفاده می‌شود.")

    # ---- ۲. مدل بار ---------------------------------------------------
    level = str(lm.get("level") or "")
    load_status = "ok" if level in ("actual", "scaled") else "warn"
    load_note = ("" if load_status == "ok" else
                 "بار از مدل بار ورودی نیامده است؛ نتیجه با بار تخمینی است "
                 "و برای گزارش رسمی باید سطح «واقعی» یا «مقیاس‌شده» انتخاب شود.")
    add("مدل بار", "سطح مدل بار", LOAD_LEVEL_FA.get(level, level),
        load_status, load_note)
    add("مدل بار", "مجموع بار شبکه (kW)",
        _fmt(load_total_kw, 1) if load_total_kw is not None else "—",
        "ok" if (load_total_kw or 0) > 0 else "error",
        "" if (load_total_kw or 0) > 0 else
        "بار صفر است؛ EENS صفر می‌شود و نتیجه بی‌معناست.")
    if level == "scaled":
        # بررسی روی همان چیزی که ذخیره می‌شود: load_model.feeder_pq
        # (کلید: شناسهٔ فیدر). قبلاً وجود کلیدهای «feeders»/«scaling_plan»
        # آزموده می‌شد که این‌جا هرگز پر نمی‌شوند و خطای «P/Q خالی» حتی با
        # ورودی کامل هم نشان داده می‌شد.
        from ..ui.inputs_model import missing_load_scaling_inputs
        pq_all = dict(lm.get("feeder_pq") or {})
        scoped = list(feeders) or sorted(pq_all)
        missing = missing_load_scaling_inputs(scoped, pq_all)
        has = [k for k in scoped if k not in missing]
        if not pq_all:
            add("مدل بار", "P/Q ورودی فیدرها", "خالی", "error",
                "سطح «مقیاس‌شده» انتخاب شده ولی برای هیچ فیدری P_load و "
                "Q_load وارد نشده است (تنظیمات مهندسی ← تب Load model).")
        elif missing:
            add("مدل بار", "P/Q ورودی فیدرها",
                f"{len(has)} از {len(scoped)} فیدر دامنه", "error",
                "برای این فیدرها P و Q (هر دو، بزرگ‌تر از صفر) وارد نشده "
                "است: " + "، ".join(missing) +
                " — با سطح «مقیاس‌شده» بار این فیدرها صفر می‌شود و EENS "
                "بی‌معنا خواهد بود.")
        else:
            detail = "، ".join(
                f"{k}: P={_fmt((pq_all.get(k) or {}).get('p_kw'), 1)} kW / "
                f"Q={_fmt((pq_all.get(k) or {}).get('q_kvar'), 1)} kVAr"
                for k in has[:6])
            add("مدل بار", "P/Q ورودی فیدرها",
                f"{len(has)} فیدر کامل", "ok",
                detail + (" …" if len(has) > 6 else ""))

    s_rated = {str(k): float(v) for k, v in (s_rated_kva or {}).items()
               if v}
    if level == "scaled" and s_rated and feeders:
        import math
        for k in feeders:
            row = dict((lm.get("feeder_pq") or {}).get(k) or {})
            try:
                p_kw = float(row.get("p_kw") or 0.0)
                q_kvar = float(row.get("q_kvar") or 0.0)
            except (TypeError, ValueError):
                continue
            if p_kw <= 0 and q_kvar <= 0:
                continue
            s_load = math.hypot(p_kw, q_kvar)
            cos_phi = (p_kw / s_load) if s_load else 0.0
            cap = float(s_rated.get(k) or 0.0)
            text = (f"S_load = {_fmt(s_load, 1)} kVA · "
                    f"cos φ = {_fmt(cos_phi, 4)}" +
                    (f" · K = {_fmt(s_load / cap, 5)}" if cap > 0 else
                     " · K = — (ΣS_rated نامعلوم)"))
            add("مدل بار", f"مقیاس فیدر «{k}»", text,
                "ok" if cap > 0 else "warn",
                "" if cap > 0 else
                "Σ ظرفیت نامی ترانس‌های این فیدر از GIS خوانده نشد؛ "
                "K محاسبه نمی‌شود.")

    # ---- ۳. λ و r هر فیدر --------------------------------------------
    missing_rates = [k for k in feeders if k not in rates]
    if auto:
        add("λ و r", "فیدرهای دارای λ واقعی",
            "، ".join(sorted(rates)) if rates else "—",
            "ok" if rates and not missing_rates else "warn",
            ("برای " + "، ".join(missing_rates) +
             f" مقدار پیش‌فرض {_fmt(eng.get('total_failure_rate_per_year'), 1)}"
             " خرابی/سال استفاده می‌شود.") if missing_rates else "")
        add("λ و r", "فیدرهای دارای r واقعی",
            "، ".join(sorted(reps)) if reps else "—",
            "ok" if reps else "warn",
            "" if reps else
            f"زمان تعمیر پیش‌فرض {_fmt(eng.get('repair_time_min'), 1)} دقیقه "
            "برای همهٔ فیدرها استفاده می‌شود.")
    else:
        add("λ و r", "λ ورودی کاربر",
            "، ".join(f"{k}={_fmt(v)}" for k, v in sorted(explicit.items()))
            or f"پیش‌فرض {_fmt(eng.get('total_failure_rate_per_year'), 1)}",
            "ok" if explicit else "warn",
            "" if explicit else "λ دستی وارد نشده است؛ مقدار پیش‌فرض "
                                "تنظیمات به‌کار می‌رود.")

    # ---- ۴. زمان‌ها ----------------------------------------------------
    rep = eng.get("repair_time_min")
    res_time = eng.get("restoration_time_min")
    manual_res = eng.get("manual_restoration_time_min")
    rest_eff = (manual_res if switch_type == "disconnector" else res_time)
    try:
        rest_eff_v = float(rest_eff)
        rep_v = float(rep)
        if rest_eff_v > rep_v:
            add("زمان‌ها", "زمان بازیابی بار سالم",
                f"{_fmt(rest_eff_v, 1)} دقیقه", "warn",
                "از زمان تعمیر بیشتر است؛ مدل آن را به زمان تعمیر محدود "
                "می‌کند (نصب کلید سودی در EENS نخواهد داشت).")
        else:
            add("زمان‌ها", "زمان بازیابی بار سالم",
                f"{_fmt(rest_eff_v, 1)} دقیقه")
    except (TypeError, ValueError):
        add("زمان‌ها", "زمان بازیابی بار سالم", "—", "error",
            "مقدار معتبر نیست.")
    add("زمان‌ها", "زمان تعمیر", f"{_fmt(rep, 1)} دقیقه",
        "ok" if (rep or 0) > 0 else "error")
    if switch_type == "recloser":
        p = eng.get("reclose_success_probability")
        tr_max = eng.get("transient_max_duration_min")
        t_rec = eng.get("reclose_time_min")
        ok_p = p is not None and 0.0 <= float(p) <= 1.0
        add("خطای گذرا", "احتمال موفقیت وصل مجدد",
            f"{_fmt(100.0 * float(p), 0)}٪" if p is not None else "—",
            "ok" if ok_p else "error",
            "" if ok_p else "باید بین ۰ و ۱ باشد.")
        add("خطای گذرا", "زمان وصل مجدد", f"{_fmt(t_rec, 2)} دقیقه",
            "ok" if (t_rec or 0) >= 0 else "error")
        add("خطای گذرا", "آستانهٔ خطای گذرا", f"{_fmt(tr_max, 2)} دقیقه",
            "ok" if (tr_max or 0) > 0 else "warn",
            "صفر یعنی هیچ خطایی گذرا شمرده نمی‌شود.")

    # ---- ۵. پارامترهای جست‌وجو ----------------------------------------
    max_sw = eng.get("max_sectionalizers")
    add("جست‌وجو", "سقف کلید هر فیدر", str(max_sw),
        "ok" if (max_sw or 0) > 0 else "error")
    add("جست‌وجو", "حداقل عمق کاندید", str(eng.get("min_candidate_depth")))
    ratio = eng.get("max_downstream_load_ratio")
    add("جست‌وجو", "حداکثر سهم بار پایین‌دست",
        f"{_fmt(100.0 * float(ratio), 0)}٪" if ratio is not None else "—",
        "ok" if ratio is not None and 0 < float(ratio) <= 1 else "warn")
    add("جست‌وجو", "کلیدهای موجود در حالت پایه",
        "بله" if eng.get("use_existing_switches") else "خیر")
    add("جست‌وجو", "ظرفیت پشتیبان",
        "، ".join(f"{k}={_fmt(v, 0)} kW" for k, v in (backup_kw or {}).items())
        if backup_kw else "نامحدود (فرض کد مرجع)",
        "ok" if backup_kw else "warn",
        "" if backup_kw else
        "بدون ظرفیت پشتیبان، مدل خوش‌بینانه‌ترین حالت را می‌گیرد؛ برای "
        "نتیجهٔ محافظه‌کارانه ظرفیت پشتیبان فیدرها را وارد کنید.")

    return PreflightReport(rows=rows, method=method, switch_type=switch_type)


def preflight_from_settings(*, settings: dict, load_model: dict | None,
                            load_total_kw: float | None,
                            feeders: list | None, all_feeders: list | None,
                            persisted_outages: dict | None = None,
                            backup_kw: dict | None = None,
                            s_rated_kva: dict | None = None) -> PreflightReport:
    """پل میان تنظیمات تب و :func:`build_preflight` (شکل داده یکسان)."""
    s = dict(settings or {})
    outages = dict(persisted_outages or {})
    rates, reps = {}, {}
    for row in (outages.get("lambda_r") or []):
        key = str(row.get("feeder_key") or "").strip().upper()
        if not key:
            continue
        val = row.get("lambda_per_year")
        if val is not None:
            rates[key] = float(val)
        rv = row.get("r_minutes")
        if rv is not None and float(rv) > 0:
            reps[key] = float(rv)
    explicit = dict(s.get("failure_rates") or {})
    return build_preflight(
        method=str(s.get("method", "uniform")),
        switch_type=str(s.get("switch_type", "sectionalizer")),
        engine=s, load_model=load_model, load_total_kw=load_total_kw,
        feeders=list(feeders or []), all_feeders=list(all_feeders or []),
        outage_rates=rates, repair_times=reps, explicit_rates=explicit,
        backup_kw=dict(backup_kw or {}),
        s_rated_kva=dict(s_rated_kva or {}),
        outage_available=bool(outages.get("lambda_r")))
