# -*- coding: utf-8 -*-
"""Tests for the data-coverage / exposure model (نیاز ۸) and the
λ/r integration — exposure must come from REAL data coverage, not
calendar years, and months without records must be detectable."""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from switchloc.reliability.coverage import (  # noqa: E402
    CoverageResult, compute_coverage, enumerate_months, infer_window,
    is_jalali_leap, jalali_month_days, month_index, parse_year_month)


class Rec:
    """Minimal outage-record stand-in."""
    def __init__(self, year, month):
        self.year = year
        self.month = month


# ---------------------------------------------------------------------------
def test_jalali_month_lengths():
    # ۶ ماه اول ۳۱ روزه، ۵ ماه بعد ۳۰ روزه
    assert jalali_month_days(1404, 1) == 31
    assert jalali_month_days(1404, 6) == 31
    assert jalali_month_days(1404, 7) == 30
    assert jalali_month_days(1404, 11) == 30
    # اسفند کبیسه/غیرکبیسه (۱۴۰۳ کبیسه، ۱۴۰۴ غیرکبیسه)
    assert jalali_month_days(1403, 12) == 30
    assert jalali_month_days(1404, 12) == 29
    assert is_jalali_leap(1403) and not is_jalali_leap(1404)


def test_parse_year_month_and_enumerate():
    assert parse_year_month("1404/07") == (1404, 7)
    assert parse_year_month("1404-7") == (1404, 7)
    assert parse_year_month("بد") is None
    months = enumerate_months((1404, 11), (1405, 2))
    assert months == [(1404, 11), (1404, 12), (1405, 1), (1405, 2)]
    assert month_index(1404, 12) + 1 == month_index(1405, 1)


def test_auto_window_and_missing_months():
    recs = [Rec(1404, 3), Rec(1404, 4), Rec(1404, 5),
            Rec(1404, 6), Rec(1404, 7), Rec(1404, 9)]
    cov = compute_coverage(recs)
    assert cov.start == (1404, 3) and cov.end == (1404, 9)
    d = cov.as_dict()
    assert d["covered_months"] == ["1404/03", "1404/04", "1404/05",
                                   "1404/06", "1404/07", "1404/09"]
    # ماه بدون رکورد شناسایی می‌شود و از مواجهه حذف است
    assert d["missing_months"] == ["1404/08"]
    assert d["effective_months"] == d["covered_months"]
    # روزهای واقعی: ماه ۳،۴،۵،۶ (۳۱×۴) + ماه ۷،۹ (۳۰×۲) = ۱۸۴ روز
    # (ماه ۸ فاقد رکورد حذف است)
    assert cov.exposure_days == 184
    assert cov.exposure_years == pytest_approx(184 / 365.0)
    assert cov.method == "auto"


def pytest_approx(v):
    import pytest
    return pytest.approx(v)


def test_explicit_window_forced_and_excluded_months():
    # پنجره صریح یک‌ساله؛ مهندس ماه بدون رکورد را «دارای پوشش» اعلام می‌کند
    cov = compute_coverage([], start="1404/01", end="1404/12",
                           force_cover=("1404/08",))
    assert cov.method == "explicit"
    assert cov.as_dict()["effective_months"] == ["1404/08"]
    assert cov.exposure_days == 30 and cov.exposure_years > 0
    # ماه دارای رکورد که ناقص ثبت شده → حذف صریح از مواجهه
    recs = [Rec(1404, m) for m in (3, 4, 5, 6, 7, 9)]
    cov2 = compute_coverage(recs, force_exclude=("1404/05",))
    assert cov2.as_dict()["excluded_months"] == ["1404/05"]
    # ۱۸۴ روز کامل منهای ماه ۵ (۳۱ روز) = ۱۵۳ روز
    assert cov2.exposure_days == 184 - 31


def test_no_dated_records_gives_empty_coverage():
    cov = compute_coverage([])
    assert cov.start is None and not cov.has_coverage
    assert cov.exposure_days == 0


def test_infer_window_undated_count():
    recs = [Rec(1404, 2), Rec(1404, 5), Rec(None, None)]
    s, e, undated = infer_window(recs)
    assert (s, e) == ((1404, 2), (1404, 5))
    assert undated == 1


# ---------------------------------------------------------------------------
# λ/r integration
# ---------------------------------------------------------------------------
def _mk_record(feeder, year, month, duration=30.0, cls=""):
    """OutageRecord-like object for feeder_lambda_r."""
    from switchloc.reliability.outages import OutageRecord
    r = OutageRecord(sheet="پست تست", row_ref=1)
    r.feeder_key = feeder
    r.in_model = True
    r.year, r.month = year, month
    r.duration_min = duration
    r.outage_class = cls or "قابل کاهش با کلیدگذاری"
    return r


def test_lambda_uses_real_exposure_not_calendar_years():
    from switchloc.reliability.lambdar import feeder_lambda_r
    # ۲ رخداد تصادفی F1 در فروردین و خرداد ۱۴۰۴؛ تیر و مرداد بدون رکورد
    recs = [_mk_record("F1", 1404, 1), _mk_record("F1", 1404, 3)]
    cov = compute_coverage(recs)          # window 1..3, month2 missing
    lam = feeder_lambda_r(recs, {"F1"}, coverage=cov)
    row = lam[0]
    # مواجهه: فروردین + خرداد = ۳۱ + ۳۱ = ۶۲ روز = ۶۲/۳۶۵ سال
    assert row.exposure_days == 62
    assert row.lambda_per_year == pytest_approx(2 / (62 / 365.0))
    assert row.covered_months == 2 and row.missing_months == 1
    assert "exposure" in row.exposure_basis


def test_lambda_legacy_fallback_without_coverage():
    from switchloc.reliability.lambdar import feeder_lambda_r
    recs = [_mk_record("F1", 1403, 5), _mk_record("F1", 1404, 5)]
    lam = feeder_lambda_r(recs, {"F1"})
    assert lam[0].lambda_per_year == pytest_approx(1.0)   # 2 events / 2 years
    assert "legacy" in lam[0].exposure_basis


def test_u_hours_binding_with_exposure():
    """U = λ × r / 60 با مخرج مواجهه واقعی (لنگر V-03 با فرمول سازگار)."""
    from switchloc.reliability.lambdar import feeder_lambda_r
    recs = [_mk_record("F1", 1404, 4, duration=60.0)]
    cov = compute_coverage(recs)          # فروردین: ۳۱ روز
    row = feeder_lambda_r(recs, {"F1"}, coverage=cov)[0]
    assert row.u_hours == pytest_approx(row.lambda_per_year * 60.0 / 60.0)
