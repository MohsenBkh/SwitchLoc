# -*- coding: utf-8 -*-
"""Six-class outage classifier (بند ۱۰ پرامپت مادر) on the four official
review levels of شکل ۵ (A-11 — resolved in Phase 1).

Six mandatory classes (domain.enums.OUTAGE_CLASSES):
  ۱. قابل کاهش با کلیدگذاری      — random line faults cleared from an
     upstream device (breaker/recloser): sectionalizing + automation
     reduces the affected zone / restoration time.
  ۲. نیازمند تعمیر یا تعویض تجهیز — a named piece of equipment failed
     (transformer, insulator, conductor, …); the remedy is the repair
     program, not switching (گام ۲: «حذف خاموشی‌هایی که با سرویس/تعویض
     شبکه فرسوده جبران می‌شوند»).
  ۳. ناشی از هماهنگی حفاظتی      — a downstream protective device (fuse
     cutout / rural miniature fuse) cleared the fault: the isolation
     already worked locally (protective coordination event).
  ۴. برنامه‌ریزی‌شده             — planned outage.  NO planned/unplanned
     column exists in the 1405 list (A-08) → detected only via a narrow
     audited pattern list (OUT-POL-02); everything else stays random.
  ۵. خارج از دامنه               — consumer-internal wiring, customer
     metering, theft: outside the switch-placement study scope.
  ۶. داده ناکافی                 — cause/feeder/date/duration missing
     (A-08); the event can not be judged.

Rule order is fixed and auditable; every event records the rule id that
fired (`rule_id`) plus the raw strings, so an engineer can re-review any
classification (review_status: auto → confirmed/rejected).
"""
from __future__ import annotations

from ..domain.enums import OUTAGE_CLASSES

CLASS_REDUCIBLE_BY_SWITCHING = OUTAGE_CLASSES[0]
CLASS_NEEDS_REPAIR = OUTAGE_CLASSES[1]
CLASS_PROTECTION_COORD = OUTAGE_CLASSES[2]
CLASS_PLANNED = OUTAGE_CLASSES[3]
CLASS_OUT_OF_SCOPE = OUTAGE_CLASSES[4]
CLASS_INSUFFICIENT = OUTAGE_CLASSES[5]

# --- کلاس ۴ (برنامه‌ریزی‌شده) — OUT-POL-02: الگوی باریک و ممیزی‌شده -------
# Profiling of the 1405 list showed that words like «تعویض/اصلاح» appear
# in crew *repair* notes («تعویض فیوز …») of clearly unplanned events;
# only explicit planned-outage phrasing is accepted here.
PLANNED_PATTERNS = (
    "خاموشی برنامه", "برنامه‌ای", "برنامه اتصال", "قطع برنامه",
    "سرویس دوره", "نگهداری دوره", "قطع از راه دور مشترک",
    "قطع اضطراری",                       # اقدام عمدی بهره‌برداری، نه خطای تصادفی
)

# --- کلاس ۵ (خارج از دامنه) — علل بیرون از هدف مطالعه کلیدگذاری -----------
OUT_OF_DOMAIN_PATTERNS = (
    "سرقت",                        # سرقت کابل/تجهیزات/ترانسفورماتور
    "شبکه داخلی مشترکان",
    "لوازم اندازه گیری",
    "شبکه فشار ضعیف",              # کلیدگذاری فشار متوسط بر LV اثر ندارد
)

# --- کلاس ۲ (نیازمند تعمیر/تعویض تجهیز) — خرابی تجهیز مشخص ---------------
# NOTE: «کات اوت فیوز» deliberately NOT here — its dominant reading is a
# protective operation (class 3); thefuse-equipment failure reading is
# kept inside class 3 with the rule id recorded for engineer review.
EQUIPMENT_REPAIR_PATTERNS = (
    "ترانسفورماتور", "مقره", "برقگیر", "جمپر", "پایه", "کابل", "کابلشو",
    "سرکابل", "سیم پارگی", "در رفتگی سیم", "تابلو", "بوشینگ", "استرچر",
    "پستها", "پست ها", "اتوبوستر", "قطع کننده",
)

# --- کلاس ۳ (هماهنگی حفاظتی) — قطع توسط حفاظت پایین‌دست -------------------
DOWNSTREAM_PROTECTIVE_PATTERNS = ("کات اوت", "فیوز")

# --- کلاس ۱ (قابل کاهش با کلیدگذاری) — قطع از بالادست / خطای تصادفی خط ---
UPSTREAM_CLEARING_PATTERNS = (
    "بریکر", "ریکلوزر", "ژنکتور",           # دیژنکتور/دژنکتور (both spellings)
    "کلید فیدر", "کلید اصلی", "سکسیونر",
)
RANDOM_LINE_CAUSE_PATTERNS = (
    "عیب گذرا", "عیب نامشخص", "پرند", "حیوانات", "رعد", "باد", "طوفان",
    "بارندگی", "برف", "تگرگ", "مه", "درخت", "اشیای خارجی", "فشار متوسط",
    "سایر اشکالات", "یخ", "گالوپینگ",
)

#: Every cause string the classifier knows.  A cause matching NONE of
#: these is «نگاشت‌نشده» → R-UNK-99 (Error in the service): an unknown
#: future cause can never silently enter a class (الزام بند ۱۰).
KNOWN_CAUSE_PATTERNS = (OUT_OF_DOMAIN_PATTERNS + EQUIPMENT_REPAIR_PATTERNS
                        + DOWNSTREAM_PROTECTIVE_PATTERNS
                        + UPSTREAM_CLEARING_PATTERNS
                        + RANDOM_LINE_CAUSE_PATTERNS)

# --- سطح دوم شکل ۵ — گروه «نوع اشکال» (mapping of the raw causes) --------
# Ordered: first matching group wins (e.g. «سرقت ترانسفورماتور» → انسانی/
# خارجی, NOT تجهیز پست).  A cause matching no group surfaces as
# «نگاشت‌نشده» + an OUT-CAUSE-UNMAPPED Error in the service.
FAULT_TYPE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("گذرا", ("عیب گذرا",)),
    ("جانداران", ("پرند", "حیوانات", "جوندگان", "مار")),
    ("شرایط جوی", ("رعد", "باد", "طوفان", "بارندگی", "برف", "تگرگ", "مه",
                   "رطوبت", "یخ", "گالوپینگ")),
    ("درختان", ("درخت",)),
    ("انسانی/خارجی", ("سرقت", "اشیای خارجی", "برخورد خودرو", "ضربه")),
    ("بهره‌برداری/مدیریت بار", ("قطع اضطراری",)),
    ("تجهیز خط هوایی", ("مقره", "جمپر", "سیم پارگی", "در رفتگی سیم", "پایه",
                        "برقگیر", "استرچر", "سیم اصلی", "اتوبوستر")),
    ("حفاظت و کلید", ("کات اوت", "فیوز", "دژنکتور", "ریکلوزر", "بریکر",
                      "سکسیونر", "کلید", "قطع کننده")),
    ("ترانس و پست", ("ترانسفورماتور", "کابل", "کابلشو", "سرکابل", "تابلو",
                     "بوشینگ", "باس بار", "شینه", "پستها", "پست ها")),
    ("مشترک/اندازه‌گیری", ("شبکه داخلی", "لوازم اندازه گیری", "کنتور")),
    ("شبکه فشار ضعیف", ("شبکه فشار ضعیف",)),
    ("شبکه فشار متوسط (نامشخص)", ("فشار متوسط", "عیب نامشخص",
                                  "سایر اشکالات")),
)

RULES_DOC = {
    "R-NAK-01": "فیلد علت/فیدر/تاریخ/مدت مفقود → داده ناکافی (A-08)",
    "R-PLAN-01": "الگوی صریح خاموشی برنامه‌ای در توضیحات (OUT-POL-02)",
    "R-DOM-01": "علت بیرون از دامنه مطالعه (سرقت/شبکه داخلی/اندازه‌گیری)",
    "R-REP-01": "خرابی تجهیز مشخص → برنامه تعمیر و تعویض",
    "R-COORD-01": "قطع توسط حفاظت پایین‌دست (کات اوت/فیوز) → هماهنگی حفاظتی",
    "R-SWITCH-01": "قطع از بالادست (بریکر/ریکلوزر/…) یا خطای تصادفی خط → "
                   "اثرپذیر با کلیدگذاری",
    "R-UNK-99": "علت/کلید خارج از نگاشت شناخته‌شده → داده ناکافی + Issue "
                "(OUT-CAUSE-UNMAPPED در سرویس)",
}


def _matches(text: str, patterns) -> str:
    """First matching pattern (substring) or ''."""
    for p in patterns:
        if p in text:
            return p
    return ""


def fault_type_group(cause_raw: str) -> str:
    """سطح دوم شکل ۵ — نوع اشکال (grouped). Unmapped → ''."""
    for group, patterns in FAULT_TYPE_GROUPS:
        if _matches(cause_raw, patterns):
            return group
    return ""


def classify_event(rec) -> tuple[str, str]:
    """Return (outage_class, rule_id) for one OutageRecord.

    Pure function — no mutation; the service assigns the result onto the
    record.  Rule order is fixed (see module docstring).
    """
    cause, device, notes = rec.cause_raw, rec.device_raw, rec.notes
    combined = f"{cause} {notes}"

    # R-NAK-01 — داده ناکافی (A-08): بدون علت/فیدر/تاریخ/مدت قضاوت ممکن نیست
    if (not cause or not rec.feeder_raw or rec.date_j == ""
            or rec.duration_min is None):
        return CLASS_INSUFFICIENT, "R-NAK-01"

    # R-PLAN-01 — برنامه‌ریزی‌شده (الگوی باریک، OUT-POL-02)
    if _matches(combined, PLANNED_PATTERNS):
        return CLASS_PLANNED, "R-PLAN-01"

    # R-UNK-99 — علت نگاشت‌نشده هرگز بی‌صدا طبقه‌بندی نمی‌شود (الزام بند ۱۰)
    if not _matches(cause, KNOWN_CAUSE_PATTERNS):
        return CLASS_INSUFFICIENT, "R-UNK-99"

    # R-DOM-01 — خارج از دامنه
    if _matches(cause, OUT_OF_DOMAIN_PATTERNS):
        return CLASS_OUT_OF_SCOPE, "R-DOM-01"

    # R-REP-01 — خرابی تجهیز مشخص
    if _matches(cause, EQUIPMENT_REPAIR_PATTERNS):
        return CLASS_NEEDS_REPAIR, "R-REP-01"

    # A head-of-feeder cutout is not a downstream protective device.
    # Do not classify it as coordination solely from the words cutout/fuse.
    head_device = _matches(f"{cause} {device} {notes}",
                           ("سرخط", "ابتدای فیدر", "کلید اصلی فیدر"))
    if head_device and (_matches(cause, DOWNSTREAM_PROTECTIVE_PATTERNS)
                        or _matches(device, DOWNSTREAM_PROTECTIVE_PATTERNS)):
        return CLASS_INSUFFICIENT, "R-NAK-01"  # مهندس باید نقش تجهیز را تأیید کند
    if (_matches(cause, DOWNSTREAM_PROTECTIVE_PATTERNS)
            or _matches(device, DOWNSTREAM_PROTECTIVE_PATTERNS)):
        return CLASS_PROTECTION_COORD, "R-COORD-01"

    # R-SWITCH-01 — قابل کاهش با کلیدگذاری
    if (_matches(device, UPSTREAM_CLEARING_PATTERNS)
            or _matches(cause, RANDOM_LINE_CAUSE_PATTERNS)):
        return CLASS_REDUCIBLE_BY_SWITCHING, "R-SWITCH-01"

    # علت شناخته‌شده ولی خارج از قواعد بالا (مثلاً علت کلید بالادست بدون
    # رکورد قطع‌کننده) → مانند بقیه خطاهای تصادفی خط، قابل کاهش با کلیدگذاری
    return CLASS_REDUCIBLE_BY_SWITCHING, "R-SWITCH-01"


def classify_all(records) -> dict:
    """Classify records in place; return rule/class counters.

    ``records[i].outage_class / .rule_id / .cause_group`` are filled.
    Unmapped-cause events (R-UNK-99) keep the «داده ناکافی» class and are
    reported by the service as Error issues (OUT-CAUSE-UNMAPPED) so an
    unknown future cause string can never silently pass (الزام بند ۱۰).
    """
    rule_counts: dict[str, int] = {}
    for rec in records:
        cls, rule = classify_event(rec)
        rec.outage_class = cls
        rec.rule_id = rule
        # گروه «نوع اشکال» ویژگی مستقل علت است — حتی برای رکوردهای
        # داده ناکافی (R-NAK) محاسبه می‌شود تا جداول سطح دوم کامل بمانند.
        rec.cause_group = fault_type_group(rec.cause_raw) if rec.cause_raw else ""
        rule_counts[rule] = rule_counts.get(rule, 0) + 1
    return {"rule_counts": rule_counts}


def cause_known(rec) -> bool:
    return bool(rec.cause_raw) and rec.rule_id not in ("R-NAK-01", "R-UNK-99")
