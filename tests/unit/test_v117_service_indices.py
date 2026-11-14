# -*- coding: utf-8 -*-
"""v1.17 — شاخص‌های پیوستگی SAIDI / SAIFI / CAIDI / ASAI از دادهٔ خاموشی.

مبنا: دادهٔ خاموشی ستون «تعداد مشترکین» ندارد (A-08)؛ سهم مشترکینِ متأثر
از «انرژی توزیع‌نشده ÷ (بار فیدر × مدت قطع)» استنتاج می‌شود. این آزمون‌ها
هم عددِ دقیق (با دادهٔ ساختگی) و هم رفتار در نبود داده را قفل می‌کنند.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from switchloc.reliability.indices import (compute_service_indices,
                                           infer_energy_unit)


class Rec:
    """حداقلِ یک رکورد خاموشی برای آزمون (همان فیلدهای OutageRecord)."""

    def __init__(self, feeder="F1", duration=60.0, energy=1.0, device="",
                 cls="قابل کاهش با کلیدگذاری", in_model=True):
        self.feeder_key = feeder
        self.duration_min = duration
        self.energy_kwh = energy
        self.device_raw = device
        self.outage_class = cls
        self.in_model = in_model

    @property
    def is_random(self):
        return self.outage_class in ("قابل کاهش با کلیدگذاری",
                                     "نیازمند تعمیر یا تعویض تجهیز",
                                     "ناشی از هماهنگی حفاظتی")


LAM_1Y = [{"feeder_key": "F1", "exposure_years": 1.0, "years_covered": 1}]


# ---------------------------------------------------------------------------
# ۱) عدد دقیق: E=1000 kWh، T=60 دقیقه، P=1000 kW → f=1
# ---------------------------------------------------------------------------
def test_exact_saidi_saifi_for_known_inputs():
    recs = [Rec(duration=60.0, energy=1.0)]          # 1 MWh
    ind = compute_service_indices(
        recs, model_feeders=["F1"], feeder_load_kw={"F1": 1000.0},
        lam=LAM_1Y, energy_unit="mwh")
    f = ind.feeders[0]
    assert f.events_counted == 1 and f.events_total == 1
    assert f.saifi == pytest.approx(1.0, rel=1e-9)      # یک قطع/سال
    assert f.saidi == pytest.approx(60.0, rel=1e-9)     # ۶۰ دقیقه/سال
    assert f.caidi == pytest.approx(60.0, rel=1e-9)
    assert f.asai == pytest.approx(1 - 60 / 525600, rel=1e-9)
    assert f.basis_counts == {"energy": 1}


def test_partial_fraction_and_multi_event_aggregation():
    # 500 kWh در ۶۰ دقیقه با بار ۱۰۰۰ kW → f = 0.5 ؛ دو رخداد
    recs = [Rec(duration=60.0, energy=0.5), Rec(duration=30.0, energy=0.25)]
    ind = compute_service_indices(recs, model_feeders=["F1"],
                                  feeder_load_kw={"F1": 1000.0},
                                  lam=LAM_1Y, energy_unit="mwh")
    f = ind.feeders[0]
    assert f.saifi == pytest.approx(0.5 + 0.5, rel=1e-9)
    assert f.saidi == pytest.approx(0.5 * 60 + 0.5 * 30, rel=1e-9)
    assert f.caidi == pytest.approx(f.saidi / f.saifi, rel=1e-9)


def test_exposure_years_is_the_denominator():
    recs = [Rec(duration=60.0, energy=1.0)]
    lam = [{"feeder_key": "F1", "exposure_years": 5.0}]
    f = compute_service_indices(recs, model_feeders=["F1"],
                                feeder_load_kw={"F1": 1000.0},
                                lam=lam, energy_unit="mwh").feeders[0]
    assert f.exposure_years == pytest.approx(5.0)
    assert f.saifi == pytest.approx(1 / 5.0, rel=1e-9)
    assert f.saidi == pytest.approx(60 / 5.0, rel=1e-9)


# ---------------------------------------------------------------------------
# ۲) نبود انرژی / نبود بار
# ---------------------------------------------------------------------------
def test_whole_feeder_device_counts_as_fraction_one_without_energy():
    recs = [Rec(duration=45.0, energy=None, device="بریکر پست فوق توزیع")]
    ind = compute_service_indices(recs, model_feeders=["F1"], lam=LAM_1Y)
    f = ind.feeders[0]
    assert f.basis_counts == {"device-whole": 1}
    assert f.saifi == pytest.approx(1.0)
    assert f.saidi == pytest.approx(45.0)
    assert ind.load_basis == "device-only"
    assert any("کف واقعی" in n for n in ind.notes)


def test_partial_device_without_energy_is_skipped_not_guessed():
    recs = [Rec(duration=45.0, energy=None, device="کات اوت سرخط")]
    ind = compute_service_indices(recs, model_feeders=["F1"],
                                  feeder_load_kw={"F1": 1000.0},
                                  lam=LAM_1Y)
    f = ind.feeders[0]
    assert f.events_counted == 0 and f.events_skipped == 1
    assert f.basis_counts == {"partial-without-energy": 1}
    assert f.saifi == 0.0 and f.saidi == 0.0
    assert not ind.has_result


def test_missing_duration_is_never_counted():
    recs = [Rec(duration=None, energy=1.0)]
    f = compute_service_indices(recs, model_feeders=["F1"],
                                feeder_load_kw={"F1": 1000.0},
                                lam=LAM_1Y, energy_unit="mwh").feeders[0]
    assert f.basis_counts == {"no-duration": 1}
    assert f.events_counted == 0


def test_fraction_clamped_and_reported():
    # انرژی بزرگ‌تر از بار×مدت → سهم > ۱ → روی ۱ بسته می‌شود
    recs = [Rec(duration=60.0, energy=10.0)]
    ind = compute_service_indices(recs, model_feeders=["F1"],
                                  feeder_load_kw={"F1": 100.0},
                                  lam=LAM_1Y, energy_unit="mwh")
    f = ind.feeders[0]
    assert f.basis_counts == {"energy-clamped": 1}
    assert f.saidi == pytest.approx(60.0)
    assert any("روی ۱ بسته شد" in n for n in f.notes)


# ---------------------------------------------------------------------------
# ۳) واحد انرژی، فیدر بدون داده، مشترکین
# ---------------------------------------------------------------------------
def test_energy_unit_inference():
    recs = [Rec(duration=60.0, energy=0.5), Rec(duration=60.0, energy=0.3)]
    assert infer_energy_unit(recs, {"F1": 1000.0}) == "mwh"
    kwh = [Rec(duration=60.0, energy=500.0), Rec(duration=60.0, energy=300.0)]
    assert infer_energy_unit(kwh, {"F1": 1000.0}) == "kwh"
    ind = compute_service_indices(recs, model_feeders=["F1"],
                                  feeder_load_kw={"F1": 1000.0}, lam=LAM_1Y)
    assert ind.energy_unit == "mwh" and ind.energy_unit_source == "inferred"
    assert any("A-08" in n for n in ind.notes)


def test_feeder_without_records_is_not_zero():
    recs = [Rec(feeder="F1", duration=60.0, energy=1.0)]
    ind = compute_service_indices(recs, model_feeders=["F1", "F2"],
                                  feeder_load_kw={"F1": 1000.0},
                                  lam=LAM_1Y + [{"feeder_key": "F2",
                                                 "exposure_years": 1.0}],
                                  energy_unit="mwh")
    rows = {f.feeder_key: f for f in ind.feeders}
    assert rows["F2"].has_data is False and rows["F2"].as_dict()["has_data"] is False
    md = ind.to_markdown()
    assert "| F2 | — | — | — | بدون داده |" in md


def test_customers_only_add_customer_minutes():
    recs = [Rec(duration=60.0, energy=0.5)]
    ind = compute_service_indices(recs, model_feeders=["F1"],
                                  feeder_load_kw={"F1": 1000.0},
                                  lam=LAM_1Y, energy_unit="mwh",
                                  customers={"F1": 2000})
    f = ind.feeders[0]
    assert f.saidi == pytest.approx(30.0)           # ۰٫۵ × ۶۰ دقیقه
    assert f.customer_minutes == pytest.approx(30.0 * 2000)
    assert f.customer_interruptions == pytest.approx(0.5 * 2000)


def test_system_total_is_load_weighted():
    recs = [Rec(feeder="F1", duration=60.0, energy=1.0),        # f=1 با ۱۰۰۰ kW
            Rec(feeder="F2", duration=60.0, energy=0.5)]        # f=0.5 با ۱۰۰۰ kW
    lam = [{"feeder_key": "F1", "exposure_years": 1.0},
           {"feeder_key": "F2", "exposure_years": 1.0}]
    ind = compute_service_indices(recs, model_feeders=["F1", "F2"],
                                  feeder_load_kw={"F1": 1000.0, "F2": 1000.0},
                                  lam=lam, energy_unit="mwh")
    assert ind.aggregation == "load-weighted"
    assert ind.saifi == pytest.approx(0.75)
    assert ind.saidi == pytest.approx(45.0)


def test_markdown_table_contains_totals():
    recs = [Rec(duration=60.0, energy=1.0)]
    ind = compute_service_indices(recs, model_feeders=["F1"],
                                  feeder_load_kw={"F1": 1000.0},
                                  lam=LAM_1Y, energy_unit="mwh")
    md = ind.to_markdown()
    assert "SAIFI" in md and "SAIDI" in md and "سامانه" in md
    assert "| F1 | 1.00 | 60.0 | 60.0 |" in md


# ---------------------------------------------------------------------------
# ۴) دادهٔ واقعی مخزن (فیدر ۱ و ۲ مشگین‌شهر)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fa,fb", [("1.xlsx", "2.xlsx")])
def test_real_meshkinshahr_outage_files(fa, fb):
    if not (ROOT / fa).is_file() or not (ROOT / fb).is_file():
        pytest.skip("فایل‌های خاموشی در مخزن نیستند")
    from switchloc.application.outage_service import (OutageService,
                                                      OutageSettings)
    res = OutageService(OutageSettings(
        per_feeder_files={"F1 - MESHKIN": str(ROOT / fa),
                          "F2 - MESHKIN": str(ROOT / fb)},
        model_feeders=("F1 - MESHKIN", "F2 - MESHKIN"),
        feeder_load_kw={"F1 - MESHKIN": 9000.0, "F2 - MESHKIN": 12000.0},
        persist=False)).run(project_name="test")
    ind = res.indices
    assert ind is not None and ind.has_result
    assert ind.energy_unit == "mwh" and ind.load_basis == "feeder-load"
    rows = {f.feeder_key: f for f in ind.feeders}
    f1, f2 = rows["F1 - MESHKIN"], rows["F2 - MESHKIN"]
    # اعداد با بار واردشده؛ بازه‌ها پهن‌اند تا تغییر جزئی داده/بار نشکند
    assert 5.0 < f1.saifi < 15.0 and 200 < f1.saidi < 700
    assert 1.5 < f2.saifi < 8.0 and 80 < f2.saidi < 400
    assert 0.99 < f1.asai < 1.0
    # مخرج همان زمان مواجههٔ λ است
    lam = {r.feeder_key: r for r in res.lambda_r}
    assert f1.exposure_years == pytest.approx(lam["F1 - MESHKIN"].exposure_years,
                                              rel=1e-6)
    # گزارش و payload شامل شاخص‌ها هستند
    assert "service_indices" in res.levels
    assert res.report.summary["service_indices"]["has_result"] is True
