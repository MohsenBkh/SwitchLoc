# -*- coding: utf-8 -*-
"""Scheme acceptance / plan selection (نیاز ۱۰ — معیارهای انتخاب طرح).

انتخاب طرح حداقل با این پنج معیار انجام می‌شود:

  ۱. کاهش ENS مثبت و معنادار باشد  (ΔENS = E2 − E1 > 0 و ≥ آستانه)
  ۲. منفعت اقتصادی مثبت باشد        (CE − CN > 0)
  ۳. ظرفیت انتقال و محدودیت‌های فنی رعایت شده باشند (ظرفیت کنترل‌شده،
     رابطه ۱۱ برقرار — نتیجه check_scheme_capacity)
  ۴. تعداد کلیدها و بودجه از سقف تعیین‌شده تجاوز نکنند
  ۵. در صورت نبود طرح قابل قبول، نتیجه صریحاً «عدم توجیه نصب کلید» باشد

⚠ قاعده طلایی این نیاز: نرم‌افزار **به اجبار برای هر فیدر طرح معرفی
نمی‌کند**.  خروجی recommendation به‌ازای «هر» فیدر یک سطر دارد، اما وضعیت
آن سطر می‌تواند باشد:

  * ``accepted``                  — طرح اصلی (بیشینه CE/CN میان پذیرفته‌ها)
  * ``needs_capacity_confirmation`` — بهترین طرح از نظر عددی، اما کنترل
    ظرفیت ناقص → «نیازمند تأیید ظرفیت»؛ تأیید نهایی مهندسی نمی‌گیرد
  * ``no_justification``          — هیچ طرح قابل قبولی نیست → «عدم توجیه
    نصب کلید» (صریح، نه حذف سطر و نه حدس)

و گردش کار تأیید مهندسی: فقط طرح ``accepted`` می‌تواند ``approved`` شود؛
درخواست تأیید برای طرح کنترل‌ظرفیت‌نشده در لایه سرویس «رد» می‌شود
(``approve_plan`` — خطای صریح، نه سکوت).
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: وضعیت طرح برای هر فیدر
ST_ACCEPTED = "accepted"
ST_NEEDS_CAPACITY = "needs_capacity_confirmation"
ST_NO_JUSTIFICATION = "no_justification"

#: برچسب‌های فارسی وضعیت (گزارش/داشبورد)
STATUS_FA = {
    ST_ACCEPTED: "طرح اصلی — قابل تأیید مهندسی",
    ST_NEEDS_CAPACITY: "نیازمند تأیید ظرفیت",
    ST_NO_JUSTIFICATION: "عدم توجیه نصب کلید",
}

#: وقتی کنترل ظرفیت اصلاً انجام نشده باشد = مانند «نیازمند تأیید ظرفیت»
CAP_MISSING = ST_NEEDS_CAPACITY


@dataclass
class AcceptanceCriteria:
    """آستانه‌های پذیرش طرح — همه قابل تنظیم از GUI (نیاز ۱۲/تنظیمات)."""
    #: کاهش ENS باید حداقل این مقدار (kWh/yr) باشد (معناداری مطلق)
    min_ens_reduction_kwh: float = 1.0
    #: معناداری نسبی: ΔENS ≥ این درصد از E2 (٪) — کافی است یکی برقرار شود
    min_ens_reduction_percent: float = 1.0
    #: منفعت اقتصادی باید مثبت باشد (CE − CN > 0)
    require_positive_benefit: bool = True
    #: طرح انتقالی باید ظرفیت کنترل‌شده داشته باشد (نیاز ۹)
    require_capacity_check: bool = True
    #: سقف تعداد کلید هر طرح (None = بدون سقف)
    max_switches_per_scheme: int | None = None
    #: سقف بودجه هر طرح (ریال؛ None = بدون سقف)
    max_budget_rials: float | None = None

    def as_dict(self) -> dict:
        return {
            "min_ens_reduction_kwh": self.min_ens_reduction_kwh,
            "min_ens_reduction_percent": self.min_ens_reduction_percent,
            "require_positive_benefit": self.require_positive_benefit,
            "require_capacity_check": self.require_capacity_check,
            "max_switches_per_scheme": self.max_switches_per_scheme,
            "max_budget_rials": self.max_budget_rials,
        }


@dataclass
class SchemeDecision:
    """نتیجه ارزیابی یک طرح (یک سطر جدول ۱۸) علیه معیارهای پذیرش."""
    scheme_id: str
    status: str                          # accepted | needs_capacity_confirmation | rejected
    reasons: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)

    @property
    def acceptable(self) -> bool:
        return self.status == ST_ACCEPTED

    @property
    def pending_capacity(self) -> bool:
        return self.status == ST_NEEDS_CAPACITY


def evaluate_scheme(comp, capacity_check, criteria: AcceptanceCriteria,
                    ) -> SchemeDecision:
    """ارزیابی یک مقایسه جدول ۱۸ علیه معیارهای ۱ تا ۵ (نیاز ۱۰).

    ``comp``: SchemeComparison یا dict هم‌ساختار؛ ``capacity_check``:
    CapacityCheck خروجی check_scheme_capacity.
    """
    def g(key, default=None):
        return getattr(comp, key, None) if not isinstance(comp, dict) \
            else comp.get(key, default)

    sid = g("scheme_id", "")
    reasons: list = []
    e2 = float(g("e2_before_kwh") or 0.0)
    e1 = float(g("e1_after_kwh") or 0.0)
    ce = float(g("ce_rials") or 0.0)
    cn = float(g("cn_rials") or 0.0)
    n_sw = int(g("n_switches") or 0)
    d_ens = e2 - e1
    d_pct = (100.0 * d_ens / e2) if e2 > 0 else 0.0

    # -- معیار ۱: کاهش ENS مثبت و معنادار --------------------------------
    if d_ens <= 0:
        reasons.append(f"کاهش ENS مثبت نیست (ΔENS = {d_ens:.1f} kWh/yr) — "
                       "نصب کلید این طرح توجیه فنی ندارد.")
        return SchemeDecision(sid, "rejected", reasons,
                              {"ens_reduction_kwh": round(d_ens, 3),
                               "ens_reduction_percent": round(d_pct, 2)})
    sig_abs = d_ens >= max(criteria.min_ens_reduction_kwh, 0.0) \
        if criteria.min_ens_reduction_kwh > 0 else True
    sig_pct = d_pct >= criteria.min_ens_reduction_percent \
        if criteria.min_ens_reduction_percent > 0 else True
    if not (sig_abs or sig_pct):
        reasons.append(
            f"کاهش ENS معنادار نیست: ΔENS = {d_ens:.2f} kWh/yr "
            f"({d_pct:.2f}٪) — آستانه‌ها: "
            f"{criteria.min_ens_reduction_kwh:g} kWh یا "
            f"{criteria.min_ens_reduction_percent:g}٪.")
        return SchemeDecision(sid, "rejected", reasons,
                              {"ens_reduction_kwh": round(d_ens, 3),
                               "ens_reduction_percent": round(d_pct, 2)})

    # -- معیار ۲: منفعت اقتصادی مثبت -------------------------------------
    if criteria.require_positive_benefit and ce - cn <= 0:
        reasons.append(f"منفعت اقتصادی مثبت نیست: CE − CN = "
                       f"{(ce - cn):.3e} ریال (CE/CN = "
                       f"{(ce / cn) if cn else 0:.3f}).")
        return SchemeDecision(sid, "rejected", reasons,
                              {"ens_reduction_kwh": round(d_ens, 3),
                               "benefit_rials": round(ce - cn, 0)})

    # -- معیار ۳: ظرفیت انتقال و محدودیت‌های فنی --------------------------
    if capacity_check is None:
        cap_status = CAP_MISSING
        cap_reasons: list = ["کنترل ظرفیت انجام نشده است."]
    else:
        cap_status = getattr(capacity_check, "status", CAP_MISSING)
        cap_reasons = list(getattr(capacity_check, "reasons", []))
    if criteria.require_capacity_check and \
            cap_status == ST_NEEDS_CAPACITY:
        return SchemeDecision(
            sid, ST_NEEDS_CAPACITY,
            ["عددی‌ها مثبت‌اند اما کنترل ظرفیت کامل نیست: "
             + (" | ".join(cap_reasons) or "ظرفیت نامشخص.")],
            {"ens_reduction_kwh": round(d_ens, 3),
             "capacity_status": cap_status})
    if criteria.require_capacity_check and cap_status == "violated":
        reasons.append("محدودیت ظرفیت نقض شده است: "
                       + " | ".join(cap_reasons))
        return SchemeDecision(sid, "rejected", reasons,
                              {"ens_reduction_kwh": round(d_ens, 3),
                               "capacity_status": cap_status})

    # -- معیار ۴: سقف تعداد کلید و بودجه ---------------------------------
    max_sw = criteria.max_switches_per_scheme
    if max_sw is not None and n_sw > max_sw:
        reasons.append(f"تعداد کلید طرح ({n_sw}) از سقف مجاز ({max_sw}) "
                       "بیشتر است.")
        return SchemeDecision(sid, "rejected", reasons,
                              {"ens_reduction_kwh": round(d_ens, 3)})
    max_b = criteria.max_budget_rials
    if max_b is not None and cn > max_b:
        reasons.append(f"بودجه طرح ({cn:,.0f} ریال) از سقف مجاز "
                       f"({max_b:,.0f} ریال) بیشتر است.")
        return SchemeDecision(sid, "rejected", reasons,
                              {"ens_reduction_kwh": round(d_ens, 3)})

    # -- همه معیارها برقرار → accepted -----------------------------------
    reasons.append("هر پنج معیار پذیرش برقرار است: کاهش ENS مثبت و "
                   f"معنادار ({d_ens:.1f} kWh)، منفعت اقتصادی مثبت، "
                   "ظرفیت کنترل‌شده، سقف کلید/بودجه رعایت شده.")
    return SchemeDecision(sid, ST_ACCEPTED, reasons,
                          {"ens_reduction_kwh": round(d_ens, 3),
                           "ens_reduction_percent": round(d_pct, 2),
                           "benefit_rials": round(ce - cn, 0),
                           "capacity_status": cap_status})


def select_plans(comparisons, decisions: dict[str, SchemeDecision],
                 ranking_rows: list, schemes: list,
                 ) -> list[dict]:
    """طرح اصلی هر فیدر — «بدون اجبار» (قلب نیاز ۱۰).

    برای هر فیدر (به ترتیب رتبه):
      * میان طرح‌های پذیرفته‌شده آن فیدر، بیشینه CE/CN → ``accepted``
      * وگرنه میان طرح‌های «نیازمند تأیید ظرفیت»، بیشینه CE/CN →
        ``needs_capacity_confirmation`` (منتظر ورود ظرفیت/تأیید مهندس)
      * وگرنه → ``no_justification`` با پیام صریح «عدم توجیه نصب کلید»
    """
    scheme_of = {s.id: s for s in schemes}
    comps = []
    for c in comparisons:
        cid = getattr(c, "scheme_id", None) if not isinstance(c, dict) \
            else c.get("scheme_id")
        ratio = getattr(c, "ce_over_cn", None) if not isinstance(c, dict) \
            else c.get("ce_over_cn")
        comps.append((cid, float(ratio) if ratio not in (None, float("-inf"))
                      else float("-inf")))

    by_feeder: dict[str, list[str]] = {}
    for cid, _ratio in comps:
        sc = scheme_of.get(cid)
        if sc is None:
            continue
        for f in sc.feeders:
            by_feeder.setdefault(f, []).append(cid)

    comp_ratio = dict(comps)
    best: dict[str, tuple[float, str]] = {}
    for row in ranking_rows:
        f = row.feeder_key if hasattr(row, "feeder_key") \
            else row.get("feeder_key")
        cands = by_feeder.get(f, [])
        acc = [cid for cid in cands
               if decisions.get(cid) is not None and decisions[cid].acceptable]
        pend = [cid for cid in cands
                if decisions.get(cid) is not None
                and decisions[cid].pending_capacity]
        if acc:
            cid = max(acc, key=lambda c: comp_ratio.get(c, float("-inf")))
            best[f] = (comp_ratio.get(cid, float("-inf")), cid)
        elif pend:
            cid = max(pend, key=lambda c: comp_ratio.get(c, float("-inf")))
            best[f] = (comp_ratio.get(cid, float("-inf")), cid)

    out = []
    for row in ranking_rows:
        f = row.feeder_key if hasattr(row, "feeder_key") \
            else row.get("feeder_key")
        rank = row.rank if hasattr(row, "rank") else row.get("rank")
        hit = best.get(f)
        if hit is None:
            out.append({
                "feeder_key": f, "rank": rank,
                "status": ST_NO_JUSTIFICATION,
                "status_fa": STATUS_FA[ST_NO_JUSTIFICATION],
                "scheme_id": None, "scheme_kind": None,
                "n_switches": 0, "ce_over_cn": None,
                "decision_reasons": [
                    "هیچ طرحی از معیارهای پذیرش (کاهش ENS معنادار، منفعت "
                    "اقتصادی مثبت، ظرفیت، سقف کلید/بودجه) عبور نکرد — "
                    "نصب کلید برای این فیدر توجیه ندارد."],
                "switches": [],
                "approved": False,
            })
            continue
        ratio, sid = hit
        sc = scheme_of[sid]
        dec = decisions[sid]
        out.append({
            "feeder_key": f, "rank": rank, "status": dec.status,
            "status_fa": STATUS_FA.get(dec.status, dec.status),
            "scheme_id": sid, "scheme_kind": sc.kind,
            "n_switches": len(sc.switches),
            "ce_over_cn": (ratio if ratio != float("-inf") else None),
            "decision_reasons": dec.reasons,
            "switches": [{"node": sw.node, "kind": sw.kind, "feeder": sw.feeder,
                          "note": getattr(sw, "note", "")} for sw in sc.switches],
            "approved": False,      # تأیید نهایی فقط با گردش کار مهندسی
        })
    return out


class PlanApprovalError(Exception):
    """تأیید نهایی مهندسی برای طرح کنترل‌ظرفیت‌نشده مجاز نیست (نیاز ۹)."""


def approve_plan(plan_row: dict, capacity_map: dict | None = None,
                 ) -> dict:
    """گردش کار تأیید مهندسی — دروازه سخت (نیاز ۹ + ۱۰).

    قاعده: طرحی که ``status != accepted`` یا ``capacity_status`` کنترل
   ‌نشده دارد هرگز تأیید نهایی نمی‌گیرد؛ تلاش برای تأیید، خطای صریح
    ``PlanApprovalError`` می‌دهد (نه سکوت و نه تأیید خودکار).
    """
    if plan_row.get("status") != ST_ACCEPTED:
        raise PlanApprovalError(
            f"طرح فیدر {plan_row.get('feeder_key')} در وضعیت "
            f"«{plan_row.get('status_fa', plan_row.get('status'))}» است — "
            "تأیید نهایی مهندسی فقط برای طرح با هر پنج معیار پذیرش ممکن است.")
    for sw in plan_row.get("switches", []):
        f = sw.get("feeder")
        if f and capacity_map is not None:
            cap = capacity_map.get(f)
            if cap is not None and not cap.has_basic_data:
                raise PlanApprovalError(
                    f"ظرفیت فیدر {f} کنترل نشده است — تأیید نهایی مجاز "
                    "نیست (نیاز ۹).")
    approved = dict(plan_row)
    approved["approved"] = True
    return approved
