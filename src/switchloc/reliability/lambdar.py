# -*- coding: utf-8 -*-
"""λ/r aggregation + the four official review levels of شکل ۵ (گام ۲).

Outputs per TAV122-02/00:
  * per-feeder λ (random events / covered years) and r (mean outage
    duration, zeros included; a zero-duration momentary event is a real
    reclose) — the values feeding معیارهای ۵ و ۶ جدول ۱۶ in فاز ۴;
    U = λ × r / 60 [h/yr] binds the Phase-1 anchor V-03 (جدول ۲۶).
  * سطح اول — by علت اشکال: events / mean duration / energy.
  * سطح دوم — by نوع اشکال (grouped cause): same metrics.
  * سطح سوم — by زمان رخداد: year×month event matrix.
  * سطح چهارم — by محدوده: feeder × operating-device counts.

Only events mapped to modelled feeders (in_model, F1..F7) enter the λ/r
matrix; all real events (both sheets) appear in the level tables.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, asdict

from .classify import CLASS_PLANNED
from .coverage import CoverageResult, compute_coverage  # noqa: F401


@dataclass
class FeederLambdaR:
    """One row of the λ/r matrix (ماتریس λ/r فیدرها — فاز ۳)."""
    feeder_key: str
    feeder_raw: str = ""
    events_total: int = 0
    events_random: int = 0
    events_planned: int = 0
    events_reducible: int = 0        # طبقه «قابل کاهش با کلیدگذاری»
    years_covered: int = 0
    lambda_per_year: float = 0.0      # نرخ خرابی تصادفی (فالت/سال)
    lambda_reducible_per_year: float = 0.0   # سنجه کمکی فاز ۴ (فقط طبقه ۱)
    r_minutes: float = 0.0            # متوسط زمان خاموشی تصادفی معتبر (دقیقه)
    r_reducible_minutes: float = 0.0  # متوسط زمان رخدادهای قابل کاهش با کلیدگذاری
    r_minutes_nonzero: float | None = None   # حساسیت: بدون رخدادهای لحظه‌ای
    energy_kwh: float = 0.0           # Σ انرژی توزیع‌نشده (واحد undeclared — A-08)
    class_counts: dict = None         # type: ignore[assignment]
    # --- زمان مواجهه واقعی (پوشش داده — نیاز ۸) --------------------------
    exposure_days: int = 0            # روزهای واقعی دارای پوشش داده
    exposure_years: float = 0.0       # = exposure_days / 365
    covered_months: int = 0           # ماه‌های دارای رکورد در پنجره
    missing_months: int = 0           # ماه‌های فاقد داده (حذف از مخرج)
    exposure_basis: str = ""          # منشأ مخرج λ (قابل ردیابی)

    @property
    def u_hours(self) -> float:
        """U = λ × r / 60 [ساعت/سال] — anchor V-03 (جدول ۲۶)."""
        return self.lambda_per_year * self.r_minutes / 60.0

    def as_dict(self) -> dict:
        d = asdict(self)
        d["u_hours"] = round(self.u_hours, 4)
        return d


def _mean(values) -> float:
    return sum(values) / len(values) if values else 0.0


def feeder_lambda_r(records, model_feeders=None,
                    coverage: CoverageResult | None = None,
                    ) -> list[FeederLambdaR]:
    """λ/r for every modelled feeder.

    Feeders of ``model_feeders`` with *zero* recorded events still get a
    row (λ=0, r=0) so the matrix is complete for the جدول ۱۶ ranking of
    فاز ۴ (its zero-inversion policy — V-01 — then applies explicitly,
    nothing is hidden).

    مخرج λ — زمان مواجهه (نیاز ۸):
      * وقتی ``coverage`` (نتیجه compute_coverage) داده شود، λ بر مبنای
        «روزهای واقعی دارای پوشش داده» است:  λ = رخداد ÷ exposure_years
        (ماه‌های فاقد رکورد — که نبودشان به معنی نبود خاموشی نیست — از
        مخرج حذف شده‌اند).
      * بدون ``coverage`` رفتار قدیمی (تقسیم بر سال‌های دارای رخداد)
        حفظ می‌شود و صراحتاً در ``exposure_basis`` ثبت می‌گردد.
    """
    from .classify import CLASS_REDUCIBLE_BY_SWITCHING

    by_feeder: dict[str, list] = defaultdict(list)
    for r in records:
        if r.in_model and r.feeder_key:
            by_feeder[r.feeder_key].append(r)

    use_coverage = coverage is not None and coverage.has_coverage
    exp_years = coverage.exposure_years if use_coverage else 0.0
    exp_days = coverage.exposure_days if use_coverage else 0
    basis = (f"exposure {exp_days} d / {exp_years:.4f} yr "
             f"({len(coverage.effective_months)} months with data)"
             if use_coverage else "years-with-events (legacy fallback)")

    out: list[FeederLambdaR] = []
    for key in sorted(set(by_feeder) | set(model_feeders or (()))):
        evts = by_feeder.get(key, [])
        random = [r for r in evts if r.is_random]
        planned = [r for r in evts if r.outage_class == CLASS_PLANNED]
        reducible = [r for r in random
                     if r.outage_class == CLASS_REDUCIBLE_BY_SWITCHING]
        # Coverage is feeder-specific. Preserve an explicitly declared
        # study window/engineer overrides, but never borrow another feeder's
        # months with events as evidence of this feeder's exposure.
        feeder_coverage = coverage
        if coverage is not None:
            feeder_coverage = compute_coverage(
                evts, start=coverage.start, end=coverage.end,
                force_cover=coverage.forced_months,
                force_exclude=coverage.excluded_months)
        local_exp_years = (feeder_coverage.exposure_years
                           if feeder_coverage is not None else 0.0)
        local_exp_days = (feeder_coverage.exposure_days
                          if feeder_coverage is not None else 0)
        years = sorted({r.year for r in evts if r.year is not None})
        durs = [r.duration_min for r in random if r.duration_min is not None]
        nz = [d for d in durs if d > 0]
        denom = local_exp_years if use_coverage else (len(years) or 0.0)
        out.append(FeederLambdaR(
            feeder_key=key,
            feeder_raw="; ".join(sorted({r.feeder_raw for r in evts if r.feeder_raw})),
            events_total=len(evts), events_random=len(random),
            events_planned=len(planned), events_reducible=len(reducible),
            years_covered=len(years),
            lambda_per_year=(len(random) / denom) if denom else 0.0,
            lambda_reducible_per_year=(len(reducible) / denom) if denom else 0.0,
            r_minutes=round(_mean(durs), 3),
            r_reducible_minutes=round(_mean([
                r.duration_min for r in reducible
                if r.duration_min is not None]), 3),
            r_minutes_nonzero=(round(_mean(nz), 3) if nz else None),
            energy_kwh=round(sum(r.energy_kwh or 0.0 for r in evts), 4),
            class_counts=dict(Counter(r.outage_class for r in evts)),
            exposure_days=local_exp_days,
            exposure_years=round(local_exp_years, 6),
            covered_months=len(feeder_coverage.covered_months) if use_coverage else 0,
            missing_months=len(feeder_coverage.missing_months) if use_coverage else 0,
            exposure_basis=basis,
        ))
    return out


def level1_by_cause(records) -> list[dict]:
    """سطح اول شکل ۵ — بر اساس علت اشکال: رخداد/مدت متوسط/انرژی."""
    by: dict[str, list] = defaultdict(list)
    for r in records:
        if r.cause_raw:
            by[r.cause_raw].append(r)
    rows = []
    for cause, evts in by.items():
        durs = [r.duration_min for r in evts if r.duration_min is not None]
        rows.append({
            "cause": cause, "events": len(evts),
            "mean_duration_min": round(_mean(durs), 2),
            "energy_kwh": round(sum(r.energy_kwh or 0.0 for r in evts), 4),
            "dominant_class": Counter(r.outage_class for r in evts).most_common(1)[0][0],
        })
    rows.sort(key=lambda d: -d["events"])
    return rows


def level2_by_fault_group(records) -> list[dict]:
    """سطح دوم شکل ۵ — بر اساس نوع اشکال (گروه‌های نگاشت رسمی)."""
    by: dict[str, list] = defaultdict(list)
    unmapped = 0
    for r in records:
        if not r.cause_raw:
            continue
        if r.cause_group:
            by[r.cause_group].append(r)
        else:
            unmapped += 1
    rows = []
    for group, evts in by.items():
        durs = [r.duration_min for r in evts if r.duration_min is not None]
        rows.append({
            "fault_group": group, "events": len(evts),
            "mean_duration_min": round(_mean(durs), 2),
            "energy_kwh": round(sum(r.energy_kwh or 0.0 for r in evts), 4),
        })
    rows.sort(key=lambda d: -d["events"])
    if unmapped:
        rows.append({"fault_group": "نگاشت‌نشده", "events": unmapped,
                     "mean_duration_min": None, "energy_kwh": None})
    return rows


def level3_by_time(records) -> dict:
    """سطح سوم شکل ۵ — زمان رخداد: ماتریس سال×ماه + خلاصه سالانه."""
    year_month: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    year_summary: dict[int, dict] = {}
    for r in records:
        if r.year is None:
            continue
        year_month[r.year][r.month or 0] += 1
        s = year_summary.setdefault(
            r.year, {"events": 0, "mean_duration_min": 0.0, "energy_kwh": 0.0})
        s["events"] += 1
        s["energy_kwh"] += r.energy_kwh or 0.0
    for year, s in year_summary.items():
        durs = [r.duration_min for r in records
                if r.year == year and r.duration_min is not None]
        s["mean_duration_min"] = round(_mean(durs), 2)
        s["energy_kwh"] = round(s["energy_kwh"], 4)
    return {
        "year_month_counts": {str(y): {f"{m:02d}": c for m, c in sorted(months.items())}
                              for y, months in sorted(year_month.items())},
        "year_summary": {str(y): s for y, s in sorted(year_summary.items())},
    }


def level4_by_scope(records) -> dict:
    """سطح چهارم شکل ۵ — محدوده: فیدر × قطع‌کننده + توزیع طبقات فیدر."""
    feeder_device: Counter = Counter()
    feeder_classes: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        feeder = r.feeder_key or (r.feeder_raw or "(بدون فیدر)")
        feeder_device[(feeder, r.device_raw or "(نامشخص)")] += 1
        feeder_classes[feeder][r.outage_class] += 1
    return {
        "feeder_device_counts": [
            {"feeder": f, "device": d, "events": n}
            for (f, d), n in sorted(feeder_device.items(),
                                    key=lambda kv: (-kv[1], kv[0]))],
        "feeder_class_counts": {
            f: dict(c) for f, c in sorted(feeder_classes.items())},
    }


def classify_summary(records) -> dict:
    """Six-class distribution over all real events."""
    return dict(Counter(r.outage_class for r in records))


def as_dict(records, lam: list[FeederLambdaR],
            coverage: CoverageResult | None = None) -> dict:
    """Everything the Phase-3 JSON report needs."""
    out = {
        "lambda_r": [f.as_dict() for f in lam],
        "coverage": coverage.as_dict() if coverage is not None else None,
        "class_summary": classify_summary(records),
        "level1_by_cause": level1_by_cause(records),
        "level2_by_fault_group": level2_by_fault_group(records),
        "level3_by_time": level3_by_time(records),
        "level4_by_scope": level4_by_scope(records),
    }
    return out
