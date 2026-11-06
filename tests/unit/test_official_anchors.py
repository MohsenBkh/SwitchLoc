# -*- coding: utf-8 -*-
"""Official-PDF anchors verified in Phase 1 (V-02, V-05, A-01 reversal).

Sources rendered/extracted from the uploaded official PDF
`0006 - (TAV122-0200) دستورالعمل مطالعات جایابی کلید در شبکه های توزیع`
(logical pages 1–35; annexes ب/ج are NOT part of this upload — see
docs/TAV122_TRACEABILITY.md §「صحت‌سنجی متن رسمی」).
"""
import pytest

from switchloc.level1 import formulas as F
from switchloc.level1.formulas import ZoneFaultRow, compute_ep_tl


# --- V-02: جدول ۱۵ worked example (official values, page 32) ---------------
def test_v02_ep_tl_official_zone_table():
    rows = [
        ZoneFaultRow("Zone0", 1800, 700),
        ZoneFaultRow("Zone1", 600, 400),
        ZoneFaultRow("Zone2", 300, 400),
        ZoneFaultRow("Zone3", 200, 200),
        ZoneFaultRow("Zone4", 200, 0),
    ]
    res = compute_ep_tl(rows, total_load_kw=2500)
    assert res.ep_percent == pytest.approx(72.0, abs=1e-9)
    assert res.tl_percent == pytest.approx(28.0, abs=1e-9)
    assert res.worst_zone == "Zone0"


# --- A-01 reversal: official CE/CN of جدول ۱۸ (page 35) --------------------
def test_a01_ce_is_benefit_cn_is_cost_maximize_ratio():
    # انرژی قبل = 16.2 MWh، انرژی بعد = 10.0 MWh، CN = 20e9 ریال
    # (قاعده «به ترتیب» متن رسمی: حرف E2=قبل، E1=بعد؛ پارامترهای تابع
    #  e1_kwh=قبل و e2_kwh=بعد هستند ← CE = 1000×(e1−e2) مثبت)
    out = F.ce_cn(e1_kwh=16200.0, e2_kwh=10000.0, cost_rials=20e9)
    assert out["saved_kwh"] == pytest.approx(6200.0)
    assert out["ce_rials"] == pytest.approx(1000.0 * 6200.0)   # CE = 1000×(E2−E1)
    assert out["cn_rials"] == pytest.approx(20e9)
    assert out["ce_over_cn"] == pytest.approx(6.2e6 / 20e9)
    # regression: the Phase-0 HTML reading (CE=cost/CN=count, minimize) is
    # superseded — direction of selection is MAXIMIZE (official page 35).
    assert F.OFFICIAL_CONFIRMATIONS["table18_ce_cn"]["selection"] == "maximize CE/CN"


def test_a01_worse_plan_must_rank_lower():
    """Plan A saves more energy per rial than plan B → higher CE/CN."""
    a = F.ce_cn(16200, 10000, cost_rials=10e9)["ce_over_cn"]
    b = F.ce_cn(16200, 14000, cost_rials=10e9)["ce_over_cn"]
    assert a > b


def test_a01_no_cost_is_not_a_rankable_plan():
    out = F.ce_cn(100, 50, cost_rials=0)
    assert out["ce_over_cn"] == float("-inf")


# --- V-05: n-1 criterion definition (تعریف ۵-۲۲، صفحه ۸) -------------------
def test_v05_n1_threshold_constant_documented():
    """30-minute restoration threshold (company-tunable per تعریف ۵-۲۳)."""
    from switchloc.domain.enums import N1_RESTORE_LIMIT_MIN
    assert N1_RESTORE_LIMIT_MIN == 30


# --- A-11: four official outage-review levels (شکل ۵، صفحه ۳۰) --------------
def test_a11_four_official_review_levels_and_six_classes():
    """شکل ۵ (PDF رسمی، صفحه منطقی ۳۰) → چهار سطح؛ بند ۱۰ پرامپت مادر → ۶ طبقه."""
    from switchloc.domain.enums import OUTAGE_REVIEW_LEVELS, OUTAGE_CLASSES
    assert len(OUTAGE_REVIEW_LEVELS) == 4
    axes = [axis for _, axis, _ in OUTAGE_REVIEW_LEVELS]
    # چهار محور رسمی: علت، نوع، زمان، محدوده
    assert axes == ["علت اشکال", "نوع اشکال",
                    "زمان رخداد (سالانه/ماهانه)", "محدوده"]
    # سه سطح نخست با همان سه سنجه گزارش می‌شوند
    for _, _, metrics in OUTAGE_REVIEW_LEVELS[:2]:
        assert "انرژی توزیع‌شده" in metrics and "مدت متوسط خاموشی" in metrics
    # شش طبقه اجباری پرامپت مادر
    assert len(OUTAGE_CLASSES) == 6
    assert "داده ناکافی" in OUTAGE_CLASSES and "خارج از دامنه" in OUTAGE_CLASSES
