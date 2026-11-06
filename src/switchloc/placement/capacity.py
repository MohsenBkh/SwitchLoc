# -*- coding: utf-8 -*-
"""Feeder capacity model (نیاز ۹ — ظرفیت نامی / پیک / رزرو / اضطراری).

چهار کمیت به‌ازای هر فیدر:

  * ``nominal_kw``   — ظرفیت نامی فیدر (ورودی کاربر/پرونده شبکه)
  * ``peak_kw``      — بار پیک موجود فیدر (ورودی کاربر/اندازه‌گیری)
  * ``reserve_kw``   — ظرفیت رزرو = نامی − پیک (محاسبه‌شده؛ می‌تواند منفی
    باشد = اضافه‌بارداری، که صراحتاً گزارش می‌شود و پنهان نمی‌شود)
  * ``emergency_kw`` — ظرفیت اضطراری (کوتاه‌مدت، مبنای رابطه ۱۱ پیوست ب) —
    از ظرفیت عادی «تفکیک‌شده» است؛ حدس زده نمی‌شود (بند ۱۹).

وضعیت کنترل ظرفیت هر فیدر و هر طرح:

  * ``ok``                       — داده کافی و قیود برقرار
  * ``needs_capacity_confirmation`` — ظرفیت نامشخص؛ طرح «نیازمند تأیید
    ظرفیت» است و «تأیید نهایی مهندسی» نمی‌گیرد (سخت‌گیرانه و بدون استثنا)
  * ``violated``                 — داده موجود است ولی قید ظرفیت نقض شده

منشأ هر مقدار (``*_source``) قابل ردیابی است: user / measured / gis /
unknown — همان انضباط ردیابی مدل بار (نیاز ۱۱).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field

#: وضعیت کنترل ظرفیت
CAP_OK = "ok"
CAP_NEEDS_CONFIRMATION = "needs_capacity_confirmation"
CAP_VIOLATED = "violated"

#: علامت‌های منشأ مقدار
SOURCE_USER = "user"            # ورود دستی مهندس
SOURCE_MEASURED = "measured"    # اندازه‌گیری/کنتور
SOURCE_GIS = "gis"              # از فیلدهای GIS
SOURCE_UNKNOWN = "unknown"
SOURCE_DEFAULT = "default"       # UI-provided starting assumption, not a measurement


@dataclass
class FeederCapacity:
    """ظرفیت‌های یک فیدر + منشأ هر مقدار (ردیابی‌پذیر)."""
    feeder_key: str
    nominal_kw: float | None = None       # ظرفیت نامی
    peak_kw: float | None = None          # بار پیک موجود
    emergency_kw: float | None = None     # ظرفیت اضطراری (کوتاه‌مدت)
    nominal_source: str = SOURCE_UNKNOWN
    peak_source: str = SOURCE_UNKNOWN
    emergency_source: str = SOURCE_UNKNOWN
    note: str = ""

    # -- محاسبات ---------------------------------------------------------
    @property
    def reserve_kw(self) -> float | None:
        """ظرفیت رزرو = نامی − پیک (خام؛ منفی = اضافه‌بارداری)."""
        if self.nominal_kw is None or self.peak_kw is None:
            return None
        return self.nominal_kw - self.peak_kw

    @property
    def usable_reserve_kw(self) -> float | None:
        """ظرفیت رزرو قابل استفاده برای انتقال (منفی → صفر)."""
        r = self.reserve_kw
        return None if r is None else max(0.0, r)

    @property
    def overloaded(self) -> bool:
        r = self.reserve_kw
        return r is not None and r < 0

    @property
    def has_basic_data(self) -> bool:
        """نامی و پیک هر دو مشخص باشند = کنترل ظرفیت پایه ممکن است."""
        return self.nominal_kw is not None and self.peak_kw is not None

    @property
    def status(self) -> str:
        """وضعیت فیدر: ok یا needs_capacity_confirmation."""
        return CAP_OK if self.has_basic_data else CAP_NEEDS_CONFIRMATION

    def emergency_or_none(self) -> float | None:
        """ظرفیت اضطراری — بدون حدس؛ None یعنی کنترل رابطه ۱۱ ممکن نیست."""
        return self.emergency_kw

    def as_dict(self) -> dict:
        d = asdict(self)
        d["reserve_kw"] = self.reserve_kw
        d["usable_reserve_kw"] = self.usable_reserve_kw
        d["overloaded"] = self.overloaded
        d["status"] = self.status
        return d

    @staticmethod
    def from_row(row: dict) -> "FeederCapacity":
        def _f(v):
            if v is None or v == "":
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        return FeederCapacity(
            feeder_key=str(row.get("feeder_key", "")).strip().upper(),
            nominal_kw=_f(row.get("nominal_kw")),
            peak_kw=_f(row.get("peak_kw")),
            emergency_kw=_f(row.get("emergency_kw")),
            nominal_source=row.get("nominal_source") or SOURCE_USER,
            peak_source=row.get("peak_source") or SOURCE_USER,
            emergency_source=row.get("emergency_source") or SOURCE_USER,
            note=row.get("note", ""))


# ---------------------------------------------------------------------------
# کنترل ظرفیت یک طرح کلیدگذاری (جدول ۱۷) — ورودی معیار ۳ پذیرش طرح (نیاز ۱۰)
# ---------------------------------------------------------------------------
@dataclass
class CapacityCheck:
    """نتیجه کنترل ظرفیت یک طرح (قابل درج در جدول ۱۸ و گزارش)."""
    status: str = CAP_NEEDS_CONFIRMATION
    reasons: list = field(default_factory=list)     # فارسی — auditable
    checked_feeders: list = field(default_factory=list)

    @property
    def is_blocking(self) -> bool:
        """کنترل‌نشده یا نقض‌شده = مجوز تأیید نهایی مهندسی ندارد."""
        return self.status != CAP_OK

    def as_dict(self) -> dict:
        return {"status": self.status, "reasons": list(self.reasons),
                "checked_feeders": list(self.checked_feeders)}


def check_scheme_capacity(scheme, cap_of: dict[str, FeederCapacity],
                          load_kw_of: dict[str, float] | None = None,
                          ) -> CapacityCheck:
    """کنترل ظرفیت انتقال یک طرح کلیدگذاری.

    قواعد (پیوست ب + نیاز ۹):
      * طرح فقط-NC (قطعه‌بندی داخل فیدر، بدون انتقال) → ظرفیت انتقال
        لازم ندارد؛ اما اگر پیک > نامی باشد «نیازمند تأیید ظرفیت» می‌شود
        (اضافه‌بارداری موجود باید صریح دیده شود).
      * طرح دارای NO (انتقال/پشتیبانی دوسویه) → ظرفیت اضطراری هر دو فیدر
        باید مشخص باشد؛ نامشخص = needs_capacity_confirmation (بدون حدس).
      * بار پیک هر دو فیدرِ طرح ۱٫۵ کلیدی باید ≤ ⅔ ظرفیت اضطراری باشد
        (رابطه ۱۱)؛ نقض = violated.
    """
    check = CapacityCheck(checked_feeders=sorted(
        {sw.feeder for sw in scheme.switches} | set(scheme.feeders)))
    load_of = load_kw_of or {}

    involved = list(check.checked_feeders)
    missing = [f for f in involved
               if f not in cap_of or not cap_of[f].has_basic_data]
    if missing:
        check.reasons.append(
            "ظرفیت نامی/بار پیک فیدر " + "، ".join(missing) +
            " نامشخص است (نیاز ۹) — طرح «نیازمند تأیید ظرفیت» است.")

    overloads = [f for f in involved
                 if f in cap_of and cap_of[f].overloaded]
    for f in overloads:
        cap = cap_of[f]
        check.reasons.append(
            f"فیدر {f}: بار پیک {cap.peak_kw:.0f} kW از ظرفیت نامی "
            f"{cap.nominal_kw:.0f} kW بیشتر است (رزرو منفی).")

    has_transfer = any(sw.kind == "NO" for sw in scheme.switches)
    if has_transfer:
        no_cap = [f for f in involved
                  if f not in cap_of or cap_of[f].emergency_or_none() is None]
        if no_cap:
            check.status = CAP_NEEDS_CONFIRMATION
            check.reasons.append(
                "ظرفیت اضطراری فیدر " + "، ".join(sorted(set(no_cap))) +
                " اعلام نشده — قید ۲/۳ رابطه (۱۱) کنترل شدنی نیست و "
                "طرح بدون کنترل ظرفیت تأیید نهایی نمی‌گیرد.")
            return check

        # رابطه ۱۱: بار هر دو فیدر ≤ ⅔ ظرفیت اضطراری
        for f in involved:
            cap = cap_of.get(f)
            if cap is None:
                continue
            em = cap.emergency_or_none()
            load = load_of.get(f, cap.peak_kw or 0.0)
            if em is not None and load > (2.0 / 3.0) * em:
                check.status = CAP_VIOLATED
                check.reasons.append(
                    f"فیدر {f}: بار {load:.0f} kW از ۲/۳ ظرفیت اضطراری "
                    f"({(2.0 / 3.0) * em:.0f} kW) بیشتر است — رابطه (۱۱) "
                    "نقض شده.")
        if check.status == CAP_VIOLATED:
            return check

    if missing or overloads:
        check.status = CAP_NEEDS_CONFIRMATION
        return check

    check.status = CAP_OK
    if not check.reasons:
        check.reasons.append("قیدهای ظرفیت برقرارند (نامی/پیک مشخص؛ "
                             + ("ظرفیت اضطراری و رابطه (۱۱) کنترل شد."
                                if has_transfer else
                                "طرح انتقالی نیست و ظرفیت اضافه نمی‌خواهد."))
    return check
