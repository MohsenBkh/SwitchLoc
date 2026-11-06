# -*- coding: utf-8 -*-
"""Tiny catalog-based translation for the application chrome.

Scope (honest): the navigation chrome — menus, toolbar, sidebar, status
bar, main buttons, tab titles, workflow stepper and the new dialogs — is
available in English and Persian.  Long engineering panels keep their
existing bilingual wording.  The language is stored in ``QSettings`` and
applied at the next start (``apply_layout_direction`` flips RTL for fa).

Qt-free: ``t()`` is a plain dict lookup, unit-testable.
"""
from __future__ import annotations

LANGS = {"en": "English", "fa": "فارسی"}
_STATE = {"lang": "en"}

FA: dict[str, str] = {
    # tabs / navigation
    "Data Import": "ورود داده",
    "Topology": "توپولوژی",
    "Placement": "جایابی",
    "Dashboard": "داشبورد",
    "Map": "نقشه",
    # workflow stepper
    "Import": "ورود",
    "Exports": "خروجی‌ها",
    # menus
    "&File": "&پرونده",
    "&Study": "&مطالعه",
    "&View": "&نمایش",
    "&Help": "&راهنما",
    "Recent projects": "پروژه‌های اخیر",
    "(none)": "(خالی)",
    "Clear list": "پاک‌کردن فهرست",
    "Exit": "خروج",
    "Language": "زبان",
    "Appearance": "ظاهر",
    "Light theme": "تم روشن",
    "Dark theme": "تم تاریک",
    "Toggle theme": "تغییر تم",
    "Open log folder": "باز کردن پوشهٔ گزارش خطا",
    "Help — study workflow": "راهنما — گردش کار مطالعه",
    "About SwitchLoc": "دربارهٔ SwitchLoc",
    "Restart required": "نیاز به راه‌اندازی مجدد",
    "The language change applies the next time SwitchLoc starts.":
        "تغییر زبان در اجرای بعدی برنامه اعمال می‌شود.",
    # actions / buttons
    "New project…": "پروژه جدید…",
    "Open project…": "بازکردن پروژه…",
    "Save project": "ذخیره پروژه",
    "Save project as…": "ذخیره پروژه با نام جدید…",
    "Import GIS data…": "ورود داده GIS…",
    "Import outage list…": "ورود فهرست خاموشی…",
    "Per-feeder outages": "خاموشی هر فیدر",
    "Run topology": "اجرای توپولوژی",
    "Run placement": "اجرای جایابی",
    "Settings": "تنظیمات",
    "Exports…": "خروجی‌ها…",
    "Approve plan": "تأیید طرح",
    "Map style…": "استایل نقشه…",
    "Help": "راهنما",
    "Choose folder & import GIS data…": "انتخاب پوشه و ورود داده GIS…",
    "Open project (.sqlite)…": "بازکردن پروژه (.sqlite)…",
    "Import outage list (single workbook)…":
        "ورود فهرست خاموشی (یک کتاب‌کار)…",
    "Process per-feeder outage files": "پردازش فایل‌های خاموشی هر فیدر",
    "Run topology on current project": "اجرای توپولوژی روی پروژه جاری",
    "Show on map": "نمایش روی نقشه",
    "Show proposals on map": "نمایش پیشنهادها روی نقشه",
    "Exports (choose formats)…": "خروجی‌ها (انتخاب قالب)…",
    "Engineering settings…": "تنظیمات مهندسی…",
    "Approve selected plan": "تأیید طرح انتخاب‌شده",
    "Run placement & ranking": "اجرای جایابی و رتبه‌بندی",
    "Import GIS data": "ورود داده GIS",
    "Per-feeder outage files": "فایل‌های خاموشی هر فیدر",
    # status bar
    "Ready": "آماده",
    "No project": "بدون پروژه",
    "Project": "پروژه",
    "Feeders": "فیدرها",
    "CRS": "سامانه مختصات",
    "Working…": "در حال انجام…",
    "Done": "انجام شد",
    "Drop a .sqlite project here to open it":
        "برای باز کردن، فایل پروژه (.sqlite) را اینجا رها کنید",
    "Another operation is still running — please wait for it to finish.":
        "عملیات دیگری در حال اجراست — لطفاً منتظر پایان آن بمانید.",
}


def set_language(lang: str) -> None:
    _STATE["lang"] = lang if lang in LANGS else "en"


def get_language() -> str:
    return _STATE["lang"]


def is_rtl() -> bool:
    return _STATE["lang"] == "fa"


def t(text: str) -> str:
    """Translate a chrome string (identity for English / unknown keys)."""
    if _STATE["lang"] == "fa":
        return FA.get(text, text)
    return text
