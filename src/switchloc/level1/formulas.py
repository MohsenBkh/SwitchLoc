# -*- coding: utf-8 -*-
"""Audited Level-1 formula kernels of TAV122-02/00 (Phase 0→1).

Every function below carries its directive anchor (بند/جدول/رابطه) and is
covered by unit tests anchored to the directive's own numerical examples
(tests/unit/test_normalization.py, test_ep_tl_up.py, test_official_anchors.py).

Phase 1 (official PDF verification): the zero-inversion policy of بند ۷-۷-۵
(گام ششم، صفحه ۳۳) is now CONFIRMED verbatim by the official TAV122-02/00
PDF: «معکوس مقادیر صفر برابر با مقدار 10 در نظر گرفته شود».  The default
policy is therefore 'confirmed'; the 'pending' lock remains available as an
explicit argument for future re-verification rounds (main prompt §12).
"""
from __future__ import annotations

from dataclasses import dataclass


#: Official-PDF confirmation registry (updated only from verified sources).
OFFICIAL_CONFIRMATIONS = {
    "inverse_zero": {
        "status": "confirmed",
        "anchor": "TAV122-02/00 بند ۷-۷-۵ (گام ششم)، صفحه ۳۳",
        "quote_fa": "معکوس مقادیر صفر برابر با مقدار 10 در نظر گرفته شود",
        "source": "upload/0006 - (TAV122-0200) دستورالعمل رسمی (صفحات منطقی ۱-۳۵)",
        "verified": "۱۴۰۵/۰۹ — Phase 1 (پس از آپلود PDF رسمی توسط کاربر)",
    },
    "table16_weights": {
        "status": "confirmed",
        "anchor": "TAV122-02/00 جدول ۱۶، صفحه ۳۳",
        "weights": [1, 2, 2, 3, 1, 1],
    },
    "table12_priorities": {
        "status": "confirmed",
        "anchor": "TAV122-02/00 جدول ۱۲، صفحه ۳۱",
        "values_fa": {"شهری": 2, "روستایی": 1, "کشاورزی": 1.5, "صنعتی": 1.5, "بار خاص": 4},
        "note_fa": "اعداد پیشنهادی است و هر شرکت توزیع می‌تواند وزندهی متفاوتی داشته باشد.",
    },
    "table18_ce_cn": {
        "status": "confirmed",
        "anchor": "TAV122-02/00 جدول ۱۸، صفحه ۳۵",
        "definition_fa": (
            "N تعداد کلیدهای مورد نیاز؛ E2 و E1 به‌ترتیب مقدار انرژی توزیع‌نشده "
            "برحسب کیلووات‌ساعت قبل و بعد از کلیدگذاری؛ CE برابر با مقدار "
            "1000 × (E2 − E1) و CN هزینه خرید کلیدهای جدید و جابجایی کلیدهای "
            "موجود در هر طرح کلیدگذاری برحسب ریال می‌باشد. بعد از تکمیل جدول ۱۸ "
            "طرح‌هایی که مقدار CE/CN بیشتری دارند به‌عنوان طرح اصلی برای هر "
            "اولویت انتخاب می‌شوند."
        ),
        # ⚠ CE/CN is a BENEFIT/COST ratio to MAXIMIZE — this REVERSES the
        # Phase-0 reading of the HTML راهنمای اجرایی (CE=هزینه, CN=تعداد).
        "selection": "maximize CE/CN",
        # قاعده «به ترتیب» در متن رسمی: E2=قبل، E1=بعد ← جمع‌جبری رسمی
        # CE = 1000×(E2−E1) = 1000×(قبل−بعد) > 0 برای طرح بهبوددهنده.
        "letter_map": "E2=انرژی قبل، E1=انرژی بعد (قاعده «به ترتیب»)",
        "algebra": "CE = 1000×(E2−E1) = 1000×(قبل − بعد)",
    },
}


# ---------------------------------------------------------------------------
# گام ۶ / بند ۷-۷-۵ / فرمول (۱) + جدول ۱۶
# ---------------------------------------------------------------------------
def normalize(values, inverse: bool = False,
              inverse_zero_policy: str = "confirmed",
              inverse_zero_value: float = 10.0):
    """Norm(Xi) = Xi / ΣXi  (TAV122-02/00 فرمول ۱، بند ۷-۷-۵).

    Parameters
    ----------
    values : list[float]
        Raw criterion values per feeder.
    inverse : bool
        Use 1/Xi before normalising (criteria 1 and 3 of جدول ۱۶).
    inverse_zero_policy : 'confirmed' | 'pending'
        * 'confirmed' (default since Phase 1): zero inverts to
          `inverse_zero_value` (10) — verified verbatim in the official
          PDF: «معکوس مقادیر صفر برابر با مقدار 10 در نظر گرفته شود"
          (بند ۷-۷-۵، صفحه ۳۳).  The value stays configurable so a company
          policy change is auditable, never hardcoded.
        * 'pending': a zero value raises ValueError — the Phase-0 lock,
          kept for explicit re-verification rounds; callers must record a
          CALC-POLICY-PENDING issue instead of computing.

    Worked example of the directive (V-01 anchor): inputs 1, 2, 0, 4 →
    inverses 1, 0.5, 10, 0.25 → normalized 0.085, 0.043, 0.851, 0.021.
    """
    if inverse:
        out = []
        for x in values:
            if x == 0:
                if inverse_zero_policy == "pending":
                    raise ValueError(
                        "صفر در معیار معکوس‌شده: سیاست جایگزین هنوز تأیید نشده "
                        "(A-02 / CALC-POLICY-PENDING)")
                out.append(float(inverse_zero_value))
            else:
                out.append(1.0 / x)
    else:
        out = [float(x) for x in values]
    total = sum(out)
    if total <= 0:
        raise ValueError("مجموع مقادیر معیار باید بزرگ‌تر از صفر باشد.")
    return [v / total for v in out]


FEEDER_RANKING_WEIGHTS = [1, 2, 2, 3, 1, 1]   # جدول ۱۶ (تأیید PDF رسمی — همچنان configurable، ابهام A-03)


def score_feeders(raw_values, weights=None):
    """Weighted ranking per جدول ۱۶.

    raw_values: list of 6-tuples (criterion 1..6 raw values per feeder).
    Returns per-feeder dict(raw, weighted_score) — normalisation of each
    criterion is the caller's responsibility (so raw/normalised values can
    both be displayed per main prompt §12-1).
    """
    weights = weights or FEEDER_RANKING_WEIGHTS
    if len(raw_values[0]) != len(weights):
        raise ValueError("تعداد معیارها با جدول ۱۶ هم‌خوان نیست.")
    scores = [sum(w * v for w, v in zip(weights, vals)) for vals in raw_values]
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    rank = [0] * len(scores)
    for pos, i in enumerate(order, start=1):
        rank[i] = pos
    return [{"score": s, "rank": r} for s, r in zip(scores, rank)]


# ---------------------------------------------------------------------------
# گام‌های ۴-۵ / جدول‌های ۱۴ و ۱۵  —  EP و TL طبق معیار n-1
# ---------------------------------------------------------------------------
@dataclass
class ZoneFaultRow:
    """One row of جدول ۱۵ (زون خطادیده، بار قطع‌شده، بار قابل بازیابی) kW."""
    zone: str
    shed_kw: float
    restorable_kw: float


@dataclass
class EPTLResult:
    ep_percent: float   # ماکزیمم درصد بار خاموش‌شده در صورت وقوع یک خطا
    tl_percent: float   # ماکزیمم درصد بار قابل انتقال
    worst_zone: str
    total_load_kw: float


def compute_ep_tl(zone_rows: list[ZoneFaultRow], total_load_kw: float) -> EPTLResult:
    """EP = max_zone(shed) / ΣP  ;  TL = max_zone(restorable) / ΣP.

    Provenance: جدول ۱۴ definitions + the directive's own worked example
    (شکل ۶-۷): shed 1800 kW of 2500 kW → EP = 72٪; restorable 700 kW →
    TL = 28٪.  Only automation-capable ties count as transfer paths — the
    caller must already have filtered TieConnections by automation_capable.
    """
    if total_load_kw <= 0:
        raise ValueError("کل بار فیدر باید مثبت باشد.")
    worst = max(zone_rows, key=lambda r: r.shed_kw)
    ep = 100.0 * worst.shed_kw / total_load_kw
    tl = 100.0 * worst.restorable_kw / total_load_kw
    return EPTLResult(ep_percent=ep, tl_percent=tl, worst_zone=worst.zone,
                      total_load_kw=total_load_kw)


# ---------------------------------------------------------------------------
# گام ۸ / جدول ۱۸ — مقایسه طرح‌های کلیدگذاری (تعریف رسمی CE و CN)
# ---------------------------------------------------------------------------
DEFAULT_RIAL_PER_KWH = 1000.0   # ضریب ثابت جدول ۱۸ متن رسمی؛ قابل تنظیم برای سیاست شرکت


def ce_cn(e1_kwh: float, e2_kwh: float, cost_rials: float,
          rial_per_kwh: float = DEFAULT_RIAL_PER_KWH) -> dict:
    """Benefit/cost pair of جدول ۱۸ per the OFFICIAL text (page 35).

    Official definition (verbatim, verified Phase 1):
      * N  = تعداد کلیدهای مورد نیاز
      * E2 و E1 **به ترتیب** = انرژی توزیع‌نشده **قبل و بعد** از کلیدگذاری
        [kWh]  ← قاعده «به ترتیب»: حرف رسمی E2 = قبل، حرف رسمی E1 = بعد
      * CE = 1000 × (E2 − E1)  [ریال] = 1000 × (قبل − بعد)
        ← ارزش ریالی انرژی صرفه‌جویی‌شده (مزیت؛ برای طرح بهبوددهنده مثبت)
      * CN = هزینه خرید کلیدهای جدید و جابجایی کلیدهای موجود [ریال] (هزینه)
      * انتخاب طرح: بیشینه‌سازی CE/CN («طرح‌هایی که مقدار CE/CN بیشتری
        دارند به‌عنوان طرح اصلی برای هر اولویت انتخاب می‌شوند»).

    Parameter naming (function convention — intuitive order):
      * `e1_kwh` = انرژی **قبل** از کلیدگذاری  (معادل حرف رسمی E2)
      * `e2_kwh` = انرژی **بعد** از کلیدگذاری   (معادل حرف رسمی E1)
    لذا جمع‌جبری رسمی CE = 1000×(E2−E1) در این تابع معادل
    1000×(`e1_kwh` − `e2_kwh`) است — همیشه همان علامت مزیت مثبت.

    ⚠ This REVERSES the Phase-0 HTML-guide reading (which had CE as the
    cost and CN as the switch count).  The official text governs (قاعده
    حاکم).  `rial_per_kwh` keeps the 1000 factor configurable for company
    policy; the ranking direction (maximize) never flips.
    """
    saved = e1_kwh - e2_kwh   # قبل − بعد = انرژی صرفه‌جویی‌شده؛ >0 یعنی بهبود
    ce = rial_per_kwh * saved                     # مزیت ریالی (E2−E1 رسمی)
    ratio = (ce / cost_rials) if cost_rials > 0 else float("-inf")
    return {
        "e1_kwh": e1_kwh, "e2_kwh": e2_kwh,
        "saved_kwh": saved,
        "ce_rials": ce, "cn_rials": cost_rials,
        "ce_over_cn": ratio,                    # جهت انتخاب: بیشینه
        "anchor": ("جدول ۱۸ صفحه ۳۵ — CE=1000×(E2−E1)=1000×(قبل−بعد)، "
                   "CN=هزینه خرید/جابجایی؛ انتخاب: بیشینه CE/CN"),
    }


# ---------------------------------------------------------------------------
# پیوست ب / روابط ۸-۱۰  —  زون‌بندی و قاعده U×P
# ---------------------------------------------------------------------------
@dataclass
class ZoneUP:
    zone: str
    lambda_per_year: float   # λ — نرخ خرابی زون (فالت/سال)
    r_minutes: float         # r — متوسط زمان تعمیر (دقیقه)
    load_mw: float           # P — مجموع بار زون (MW)

    @property
    def u_hours(self) -> float:
        """U = λ × r / 60  [ساعت/سال]."""
        return self.lambda_per_year * self.r_minutes / 60.0

    @property
    def ens_mwh(self) -> float:
        """ENS = U × P  [MWh] — رابطه (۸) term / جدول ۲۶ sample."""
        return self.u_hours * self.load_mw


def up_rule_deviation(zones: list[ZoneUP]) -> float:
    """Normalised RMS deviation of U_i×P_i from its mean (رابطه ۱۰).

    Ui×Pi = Uj×Pj is the directive's golden placement rule for zones of a
    feeder (پیوست ب، رابطه ۱۰).  Placement algorithms minimise this
    deviation; zero means the ideal equal-U×P split is achieved.
    """
    if not zones:
        raise ValueError("فهرست زون‌ها خالی است.")
    ups = [z.u_hours * z.load_mw for z in zones]
    mean = sum(ups) / len(ups)
    if mean <= 0:
        return 0.0
    rms = (sum((u - mean) ** 2 for u in ups) / len(ups)) ** 0.5
    return rms / mean


def ens_total(zones: list[ZoneUP]) -> float:
    """ENS = Σ Ui×Pi  [MWh] — رابطه (۸) aggregated over zones."""
    return sum(z.ens_mwh for z in zones)
