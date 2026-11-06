# -*- coding: utf-8 -*-
"""Data-coverage / exposure-time model (نیاز ۸ — Exposure Time واقعی).

مفهوم رسمی: نرخ خرابی λ = تعداد رخدادهای تصادفی ÷ زمان مواجهه (Exposure
Time) برحسب سال.  زمان مواجهه باید بر اساس «واقعیت پوشش داده» محاسبه
شود، نه تعداد سال‌های تقویمی و نه صرفاً سال‌هایی که رخداد داشته‌اند:

  * «نبود رکورد» لزوماً به معنی «نبود خاموشی» نیست → ماه‌های داخل پنجره
    پوشش که هیچ رکوردی ندارند به‌عنوان «ماه فاقد داده» شناسایی و به‌صورت
    پیش‌فرض از زمان مواجهه حذف می‌شوند (مهندس می‌تواند صریحاً پوشش بدهد).
  * دوره پوشش داده (شروع/پایان) قابل تعریف صریح است؛ اگر داده نشود از
    خود رکوردها استنتاج می‌شود (اولین/آخرین ماه دارای رکورد).
  * زمان مواجهه بر حسب «روز واقعی» جمع می‌شود (طول واقعی ماه‌های شمسی:
    ۶ ماه اول ۳۱ روزه، ۵ ماه بعد ۳۰ روزه، اسفند ۲۹ یا ۳۰ روزه در سال
    کبیسه) و سپس به سال تبدیل می‌شود: exposure_years = days / 365.

هر نتیجه به‌صورت JSON-safe گزارش می‌شود تا در گزارش‌ها و داشبورد، منشأ
مخرج λ کاملاً قابل ردیابی باشد (بند ۱۹ — هیچ عدد پنهانی نیست).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

#: روزهای ماه‌های شمسی (فارسی/جلالی): ۱-۶ → ۳۱، ۷-۱۱ → ۳۰، ۱۲ → ۲۹/۳۰
_JALALI_LEAP_REMAINDERS = frozenset({1, 5, 9, 13, 17, 22, 26, 30})
#: مبنای تبدیل روز به سال (سال ۳۶۵ روزه — قرارداد گزارش‌گیری مطالعات)
DAYS_PER_YEAR = 365.0


def is_jalali_leap(year: int) -> bool:
    """کبیسه‌بودن سال شمسی با الگوی ۳۳ ساله (الگوریتم متداول بیرجندی)."""
    return (year % 33) in _JALALI_LEAP_REMAINDERS


def jalali_month_days(year: int, month: int) -> int:
    """طول واقعی یک ماه شمسی برحسب روز."""
    if not 1 <= month <= 12:
        raise ValueError(f"month out of range: {month}")
    if month <= 6:
        return 31
    if month <= 11:
        return 30
    return 30 if is_jalali_leap(year) else 29


def month_index(year: int, month: int) -> int:
    """کلید مرتب‌پذیر یک ماه: year*12 + (month-1)."""
    return year * 12 + (month - 1)


def parse_year_month(text: str) -> tuple[int, int] | None:
    """«1404/07» یا «1404-7» یا «1404» → (1404, 7)؛ نامعتبر → None.

    «1404» تنها به‌معنای کل سال (ماه ۱ تا ۱۲) تفسیر نمی‌شود؛ پنجره پوشش
    باید صریح باشد، در غیر این صورت از داده استنتاج می‌شود.
    """
    s = (text or "").strip().replace("-", "/").replace(".", "/")
    if not s:
        return None
    parts = [p for p in s.split("/") if p != ""]
    try:
        if len(parts) == 2:
            y, m = int(parts[0]), int(parts[1])
        elif len(parts) == 1:
            y, m = int(parts[0]), 1          # «1404» → فروردین همان سال
        else:
            return None
    except ValueError:
        return None
    if not (1 <= m <= 12) or not (1200 <= y <= 1600):
        return None
    return y, m


def enumerate_months(start: tuple[int, int],
                     end: tuple[int, int]) -> list[tuple[int, int]]:
    """همه ماه‌های (year, month) از start تا end شامل دو سر."""
    if month_index(*start) > month_index(*end):
        return []
    out = []
    y, m = start
    while month_index(y, m) <= month_index(*end):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


@dataclass
class CoverageResult:
    """نتیجه تحلیل پوشش داده — منشأ مخرج λ (قابل ردیابی و JSON-safe)."""
    start: tuple[int, int] | None = None          # (year, month) شمسسی
    end: tuple[int, int] | None = None
    window_months: list = field(default_factory=list)   # کل پنجره
    covered_months: list = field(default_factory=list)  # ≥۱ رکورد
    missing_months: list = field(default_factory=list)  # پنجره منهای پوشش
    forced_months: list = field(default_factory=list)   # تأیید صریح مهندس
    excluded_months: list = field(default_factory=list)  # حذف صریح مهندس
    effective_months: list = field(default_factory=list)  # مبنای مواجهه
    exposure_days: int = 0
    exposure_years: float = 0.0
    method: str = "auto"                # auto | explicit
    records_total: int = 0
    records_undated: int = 0

    @property
    def has_coverage(self) -> bool:
        return bool(self.effective_months) and self.exposure_days > 0

    def as_dict(self) -> dict:
        d = asdict(self)
        d["start"] = list(self.start) if self.start else None
        d["end"] = list(self.end) if self.end else None
        fmt = lambda ms: [f"{y}/{m:02d}" for y, m in sorted(ms)]  # noqa: E731
        for key in ("window_months", "covered_months", "missing_months",
                    "forced_months", "excluded_months", "effective_months"):
            d[key] = fmt(d[key])
        d["exposure_years"] = round(self.exposure_years, 6)
        d["days_per_year_basis"] = DAYS_PER_YEAR
        return d


def infer_window(records) -> tuple[tuple[int, int] | None,
                                   tuple[int, int] | None, int]:
    """استنتاج پنجره پوشش از خود رکوردها (اولین/آخرین ماه دارای رکورد)."""
    dated = [(r.year, r.month) for r in records
             if getattr(r, "year", None) and getattr(r, "month", None)]
    undated = sum(1 for r in records
                  if not (getattr(r, "year", None)
                          and getattr(r, "month", None)))
    if not dated:
        return None, None, undated
    idx = [month_index(*m) for m in dated]
    lo, hi = min(idx), max(idx)
    return ((lo // 12, lo % 12 + 1), (hi // 12, hi % 12 + 1), undated)


def compute_coverage(records,
                     start: tuple[int, int] | str | None = None,
                     end: tuple[int, int] | str | None = None,
                     force_cover=(), force_exclude=()) -> CoverageResult:
    """پوشش داده و زمان مواجهه واقعی را از رکوردها محاسبه می‌کند.

    * ``start``/``end``: دوره پوشش صریح («1404/07») — بدون آن‌ها پنجره از
      اولین/آخرین رکورد استنتاج می‌شود.
    * ``force_cover``: ماه‌های فاقد رکورد که مهندس صریحاً دارای پوشش
      اعلام می‌کند (مثلاً «پرونده آن ماه در بایگانی است»).
    * ``force_exclude``: ماه‌های دارای رکورد که باید حذف شوند
      (مثلاً ثبت ناقص).
    """
    def as_pair(v):
        if v is None:
            return None
        if isinstance(v, str):
            return parse_year_month(v)
        return (int(v[0]), int(v[1]))

    s_exp, e_exp = as_pair(start), as_pair(end)
    s_inf, e_inf, undated = infer_window(records)
    method = "explicit" if (s_exp or e_exp) else "auto"
    s = s_exp or s_inf
    e = e_exp or e_inf
    res = CoverageResult(start=s, end=e, method=method,
                         records_total=len(records),
                         records_undated=undated)
    if s is None or e is None or month_index(*s) > month_index(*e):
        return res                       # هیچ داده تاریخی معتبری نیست

    res.window_months = enumerate_months(s, e)
    seen = {month_index(y, m) for y, m in
            ((r.year, r.month) for r in records
             if getattr(r, "year", None) and getattr(r, "month", None))}
    window_idx = {month_index(*m): m for m in res.window_months}
    res.covered_months = [m for m in res.window_months
                          if month_index(*m) in seen]
    res.missing_months = [m for m in res.window_months
                          if month_index(*m) not in seen]

    forced_idx = [month_index(*as_pair(v)) for v in force_cover
                  if as_pair(v) is not None
                  and month_index(*as_pair(v)) in window_idx]
    excluded_idx = {month_index(*as_pair(v)) for v in force_exclude
                    if as_pair(v) is not None
                    and month_index(*as_pair(v)) in window_idx}
    res.forced_months = [window_idx[i] for i in sorted(forced_idx)]
    res.excluded_months = [window_idx[i] for i in sorted(excluded_idx)]

    effective_idx = {month_index(*m) for m in res.covered_months}
    effective_idx |= set(forced_idx)
    effective_idx -= excluded_idx
    res.effective_months = [window_idx[i] for i in sorted(effective_idx)]
    res.exposure_days = sum(jalali_month_days(y, m)
                            for y, m in res.effective_months)
    res.exposure_years = res.exposure_days / DAYS_PER_YEAR
    return res
