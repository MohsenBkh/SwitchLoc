# -*- coding: utf-8 -*-
"""Shared constants and enumerations (TAV122-02/00 definitions, بند ۵).

Every value here is traceable to the directive or the audited field
catalog — nothing is invented.
"""
from __future__ import annotations

from enum import Enum

#: معیار n-1 (تعریف ۵-۲۲): all loads restored in < 30 minutes.
#: Company-tunable per تعریف ۵-۲۳ (n-1 اصلاح‌شده) — kept as a named
#: constant so the tuning is explicit, never a magic number.
N1_RESTORE_LIMIT_MIN = 30

# --- گام ۲ (بند ۷-۷-۳) — چهار سطح رسمی بررسی خاموشی (شکل ۵، صفحه ۳۰) ------
# A-11 resolved in Phase 1: the official PDF's شکل ۵ «شناسایی و تفکیک
# خاموشی‌های شبکه» was read from the rendered page image (physical page 43 /
# logical page 30).  The four review axes and their reported metrics are
# transcribed below; the micro-wording of the figure boxes is a faithful
# reading, the axis names are certain.
OUTAGE_REVIEW_LEVELS = (
    ("سطح اول", "علت اشکال",
     "تعداد رخداد، مدت متوسط خاموشی، انرژی توزیع‌شده"),
    ("سطح دوم", "نوع اشکال",
     "تعداد رخداد، مدت متوسط خاموشی، انرژی توزیع‌شده"),
    ("سطح سوم", "زمان رخداد (سالانه/ماهانه)",
     "تمرکزات ماهانه و سالانه بر نوع خرابی و تأثیر بهبود وضعیت"),
    ("سطح چهارم", "محدوده",
     "بررسی نوع خطاها و نحوه عمل‌کرد تجهیزات"),
)

# --- بند ۱۰ پرامپت مادر — شش طبقه اجباری طبقه‌بندی خاموشی ------------------
# Implemented in `reliability/classify.py` (فاز ۳) per ARCHITECTURE.md §۵;
# the mapping of the four official levels above to these six classes is
# recorded in docs/TAV122_TRACEABILITY.md §۲-گام ۲ and docs/PHASE3_REPORT.md.
OUTAGE_CLASSES = (
    "قابل کاهش با کلیدگذاری",
    "نیازمند تعمیر یا تعویض تجهیز",
    "ناشی از هماهنگی حفاظتی",
    "برنامه‌ریزی‌شده",
    "خارج از دامنه",
    "داده ناکافی",
)


class NodeKind(str, Enum):
    JUNCTION = "junction"          # گره هندسی اتصال قطعات خط
    DEVICE_HV = "device_hv"        # تجهیز نقطه‌ای در شبکه فشار متوسط
    SOURCE = "source"              # پست/منبع تغذیه فیدر


class BranchKind(str, Enum):
    LINE_AERIAL = "line_aerial"    # خط هوایی
    LINE_UNDERGROUND = "line_underground"  # خط زمینی/کابل
    JUMPER = "jumper"              # جمپر
    LINE_MISC = "line_misc"        # سایر هادی‌ها


class SwitchFamily(str, Enum):
    DISCONNECTOR = "disconnector"      # سکسیونر/دیژنکتور/کلید جردن
    BREAKER = "breaker"                # بریکر/مدارشکن
    RECLOSER = "recloser"              # ریکلوزر
    SECTIONALIZER = "sectionalizer"    # سکشنلایزر
    FUSE_CUTOUT = "fuse_cutout"        # کات اوت فیوز
    UNKNOWN = "unknown"


class SwitchState(str, Enum):
    """وضعیت سرویس از فیلد T__outserv (تعریف ۵-۷ نقطه کار شبکه)."""
    IN_SERVICE = "in_service"
    OUT_OF_SERVICE = "out_of_service"
    UNKNOWN = "unknown"            # هیچ مقداری فرض پنهان نمی‌شود (الزام بند ۱۹)


class YesNoUnknown(str, Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"
