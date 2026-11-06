# -*- coding: utf-8 -*-
"""Load/priority model — جدول ۱۲ (گام ۳-۵، فصل ۶ / مدل بار).

Official table 12 priorities (verbatim, Phase-1 verified):
    شهری ۲ · روستایی ۱ · کشاورزی ۱.۵ · صنعتی ۱.۵ · بار خاص ۴
with the official footnote: «اعداد پیشنهادی است و هر شرکت توزیع می‌تواند
وزندهی متفاوتی داشته باشد» → configurable + every override is logged via
settings_log (ابهام A-03 / بند ۹ پرامپت مادر).

«بار خاص» per جدول ۸: مراکز درمانی، بیمارستان‌ها، … (A-05: same category).
The GIS sample carries no load-category field — the model therefore
ships (a) the audited table, (b) alias resolution for common spellings,
(c) explicit assignment + sum per feeder, and (d) a recorded limitation
issue instead of inventing categories (الزام بند ۱۹).
"""
from __future__ import annotations

from ..domain.entities import CanonicalNetwork
from ..validation.issues import (IssueLog, SEVERITY_INFO, SEVERITY_WARNING,
                                 ValidationIssue)

#: جدول ۱۲ — official defaults (configurable; changes are logged).
TABLE12_PRIORITIES: dict[str, float] = {
    "شهری": 2.0,
    "روستایی": 1.0,
    "کشاورزی": 1.5,
    "صنعتی": 1.5,
    "بار خاص": 4.0,
}

#: common spellings → canonical جدول ۱۲ category (جدول ۸: بار خاص حساس).
CATEGORY_ALIASES: dict[str, str] = {
    "urban": "شهری", "شهری": "شهری",
    "rural": "روستایی", "روستایی": "روستایی", "روستا": "روستایی",
    "agriculture": "کشاورزی", "کشاورزی": "کشاورزی", "زراعی": "کشاورزی",
    "industrial": "صنعتی", "صنعتی": "صنعتی", "کارخانه": "صنعتی",
    "special": "بار خاص", "بار خاص": "بار خاص", "حساس": "بار خاص",
    "درمانی": "بار خاص", "بیمارستان": "بار خاص", "درمان": "بار خاص",
    "hospital": "بار خاص",
}


def resolve_category(raw: str) -> str:
    """Map a raw category string to a جدول ۱۲ category; '' if unknown."""
    key = (raw or "").strip().lower()
    return CATEGORY_ALIASES.get(key, CATEGORY_ALIASES.get(raw.strip(), ""))


def assign_priorities(net: CanonicalNetwork, issues: IssueLog | None = None,
                      category_overrides: dict[str, str] | None = None,
                      priorities: dict[str, float] | None = None,
                      ) -> dict:
    """Fill ``load_pt.priority_weight`` per جدول ۱۲ (or per override).

    Loads whose category is unknown are left untouched
    (``data_source='unassigned'``) and counted — never guessed.
    Returns a summary dict; issues (Information/Warning) describe what
    was assigned and what remains unassigned.
    """
    issues = issues if issues is not None else IssueLog()
    prio = dict(TABLE12_PRIORITIES)
    if priorities:
        prio.update(priorities)
    node_of = {n.id: n for n in net.nodes}

    assigned = unknown = 0
    weighted_kw = 0.0
    for ld in net.loads:
        raw_cat = ld.category or ""
        cat = resolve_category(raw_cat)
        if category_overrides and ld.id in category_overrides:
            cat = resolve_category(category_overrides[ld.id])
        if cat and cat in prio:
            ld.priority_weight = prio[cat]
            ld.data_source = "table12"
            assigned += 1
            if ld.p_kw:
                weighted_kw += prio[cat] * ld.p_kw
        else:
            unknown += 1

    if assigned:
        issues.add(ValidationIssue(
            code="LOAD-PRI-ASSIGNED", severity=SEVERITY_INFO,
            message_fa=f"اولویت جدول ۱۲ برای {assigned} بار تخصیص یافت "
                       f"(Σ وزنی بار شناخته‌شده = {weighted_kw:,.1f} kW).",
            field="priority_weight", current_value="—",
            suggestion_fa="تغییر وزن‌ها توسط شرکت از مسیر "
                          "settings_log ثبت می‌شود (A-03).",
            impact_fa="ورودی معیار ۴ جدول ۱۶ (مجموع اولویت بارهای فیدر).",
            meta={"assigned": assigned, "weighted_kw": weighted_kw}))
    if unknown:
        issues.add(ValidationIssue(
            code="LOAD-PRI-UNASSIGNED", severity=SEVERITY_WARNING,
            message_fa=f"{unknown} بار بدون دسته جدول ۱۲ باقی ماند — GIS "
                       "نمونه فیلد دسته‌بندی بار ندارد؛ حدس زده نمی‌شود.",
            field="category", current_value="",
            suggestion_fa="ورود دسته‌بندی توسط کاربر (شهری/روستایی/…"
                          "/بار خاص) یا فایل نگاشت دسته‌ها.",
            impact_fa="بارهای بدون اولویت در معیار ۴ جدول ۱۶ لحاظ نمی‌شوند.",
            meta={"unassigned": unknown}))

    return {
        "table12": prio,
        "assigned": assigned,
        "unassigned": unknown,
        "weighted_kw": weighted_kw,
        "categories_seen": sorted({ld.category for ld in net.loads if ld.category}),
    }


def feeder_priority_sums(net: CanonicalNetwork) -> dict[str, dict]:
    """Per-feeder load/priority sums (input of criterion 4, جدول ۱۶).

    transformer-only nodes without p_kw contribute their transformer
    capacity as the *proxy* load?  — NO (الزام بند ۱۹: no invented data):
    only loads with a known p_kw count; the gap is visible in
    ``loads_without_kw``.
    """
    transformer_of = {t.id: t for t in net.transformers}
    feeder_of_node = {n.id: n.feeder_name for n in net.nodes}
    out: dict[str, dict] = {}
    for ld in net.loads:
        feeder = feeder_of_node.get(ld.node_id, "")
        # feeder of the load = feeder of its transformer when known
        if not feeder and ld.transformer_id in transformer_of:
            feeder = transformer_of[ld.transformer_id].feeder_name or ""
        key = feeder or "(بدون فیدر)"
        s = out.setdefault(key, {
            "loads": 0, "with_kw": 0, "without_kw": 0,
            "p_kw": 0.0, "priority_weighted_kw": 0.0})
        s["loads"] += 1
        if ld.p_kw:
            s["with_kw"] += 1
            s["p_kw"] += ld.p_kw
            if ld.priority_weight:
                s["priority_weighted_kw"] += ld.priority_weight * ld.p_kw
        else:
            s["without_kw"] += 1
    return out
