# -*- coding: utf-8 -*-
"""نمودارهای ستونی سبک برای داشبورد (بدون وابستگی تازه).

چرا QPainter و نه Matplotlib؟ برچسب‌ها فارسی‌اند و Qt شکل‌دهی (shaping) و
چیدمان راست‌به‌چپ فارسی را درست انجام می‌دهد؛ در Matplotlib متن فارسی
بدون reshaper/‌bidi به‌صورت حروف جدا و برعکس رسم می‌شود. این ویجت فقط
می‌خواند و هیچ‌چیز را در مدل تغییر نمی‌دهد.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..map_renderer import FEEDER_COLORS


def _fmt_value(v: float) -> str:
    """نمایش عدد: هزار جداکننده، بدون صفرهای اضافی."""
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1000:
        return f"{v:,.0f}"
    if a >= 10:
        return f"{v:,.1f}"
    if a >= 1:
        return f"{v:,.2f}"
    if a == 0:
        return "0"
    return f"{v:.3f}"


class BarChartWidget(QWidget):
    """یک نمودار ستونی افقی: عنوان، واحد و یک میله برای هر فیدر.

    ``items``: فهرست ``(label, value, color)``؛ مقدار ``None`` یعنی «بدون
    داده» و با «—» نشان داده می‌شود (صفر نمایش داده نمی‌شود تا «نداشتن
    داده» با «صفر بودن» اشتباه نشود).
    """

    def __init__(self, title: str = "", unit: str = "", parent=None):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.items: list[tuple[str, float | None, str]] = []
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Minimum)
        self.setToolTip(title)

    # ------------------------------------------------------------------
    def set_data(self, items, title: str | None = None,
                 unit: str | None = None) -> None:
        self.items = [(str(k), (None if v is None else float(v)), c)
                      for k, v, c in (items or [])]
        if title is not None:
            self.title = title
        if unit is not None:
            self.unit = unit
        self.setMinimumHeight(40 + 18 * max(1, len(self.items)))
        self.setToolTip("\n".join(
            f"{k}: {_fmt_value(v)} {self.unit}".strip()
            for k, v, _c in self.items) or self.title)
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:      # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#ffffff"))

        head = QFont(self.font())
        head.setBold(True)
        head.setPointSizeF(max(8.5, self.font().pointSizeF()))
        p.setFont(head)
        p.setPen(QPen(QColor("#1f2d3d")))
        title = self.title + (f"  ({self.unit})" if self.unit else "")
        p.drawText(QRectF(6, 2, w - 12, 22),
                   int(Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter), title)
        p.setPen(QPen(QColor("#c8ced6")))
        p.drawLine(6, 25, w - 6, 25)

        if not self.items:
            p.setPen(QPen(QColor("#8a939e")))
            p.drawText(QRectF(6, 26, w - 12, h - 30),
                       int(Qt.AlignmentFlag.AlignCenter), "داده‌ای برای نمایش نیست")
            p.end()
            return

        values = [abs(v) for _k, v, _c in self.items if v is not None]
        vmax = max(values) if values else 0.0
        # چیدمان راست‌به‌چپ: برچسب فیدر سمت راست، میله از همان‌جا به چپ
        label_w = int(min(200, max(96, w * 0.34)))
        label_x = w - label_w - 6
        bar_left = 6.0
        bar_right = label_x - 10.0
        bar_w_max = max(20.0, bar_right - bar_left)
        row_h = max(14.0, (h - 30) / max(1, len(self.items)))

        small = QFont(self.font())
        small.setPointSizeF(max(7.5, self.font().pointSizeF() - 0.5))
        p.setFont(small)
        for i, (label, value, color) in enumerate(self.items):
            y = 30 + i * row_h
            p.setPen(QPen(QColor("#31424f")))
            p.drawText(QRectF(label_x, y, label_w, row_h),
                       int(Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter),
                       str(label))
            if value is None:
                p.setPen(QPen(QColor("#9aa3ad")))
                p.drawText(QRectF(bar_left, y, bar_w_max, row_h),
                           int(Qt.AlignmentFlag.AlignRight
                               | Qt.AlignmentFlag.AlignVCenter), "—")
                continue
            frac = (abs(value) / vmax) if vmax else 0.0
            width = max(2.0, bar_w_max * frac)
            x0 = bar_right - width            # میله از راست به چپ رشد می‌کند
            bar = QRectF(x0, y + row_h * 0.18, width, row_h * 0.64)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color or FEEDER_COLORS[0]))
            p.drawRoundedRect(bar, 2.0, 2.0)
            if width >= 62:
                # میلهٔ بلند: عدد داخل میله (سفید) تا با برچسب قاطی نشود
                p.setPen(QPen(QColor("#ffffff")))
                p.drawText(QRectF(x0 + 4, y, 60, row_h),
                           int(Qt.AlignmentFlag.AlignLeft
                               | Qt.AlignmentFlag.AlignVCenter),
                           _fmt_value(value))
            else:
                p.setPen(QPen(QColor("#22303c")))
                p.drawText(QRectF(max(bar_left, x0 - 72), y, 68, row_h),
                           int(Qt.AlignmentFlag.AlignRight
                               | Qt.AlignmentFlag.AlignVCenter),
                           _fmt_value(value))
        p.end()


#: شاخص‌هایی که در داشبورد به‌صورت نمودار می‌آیند
#: (key در ردیف فیدر، عنوان فارسی، واحد، مقیاس نمایش، تعداد اعشار)
CHART_METRICS = (
    ("saidi", "SAIDI — مدت متوسط قطع", "دقیقه/سال", 1.0),
    ("saifi", "SAIFI — تعداد متوسط قطع", "قطع/سال", 1.0),
    ("caidi", "CAIDI — مدت هر قطع", "دقیقه", 1.0),
    ("asai_pct", "ASAI — دسترس‌پذیری", "٪", 1.0),
    ("ens_per_year_kwh", "انرژی توزیع‌نشده (ENS)", "kWh/سال", 1.0),
    ("ens_kwh", "EENS پایه (بدون کلیدگذاری)", "kWh/سال", 1.0),
    ("ens_after_kwh", "EENS پس از طرح", "kWh/سال", 1.0),
    ("lambda_per_year", "λ — نرخ خرابی تصادفی", "خرابی/سال", 1.0),
    ("lambda_reducible", "λ قابل کاهش با کلیدگذاری", "خرابی/سال", 1.0),
    ("r_minutes", "r — مدت تعمیر", "دقیقه", 1.0),
    ("u_hours", "U = λr/60", "ساعت/سال", 1.0),
    ("km", "طول شبکهٔ فیدر", "کیلومتر", 1.0),
    ("transformers", "تعداد ترانس", "دستگاه", 1.0),
    ("total_load_kw", "بار فیدر", "kW", 1.0),
    ("s_rated_kva_gis", "ظرفیت نامی ترانس‌ها", "kVA", 1.0),
    ("score", "امتیاز رتبه‌بندی (فرمول ۱)", "امتیاز", 1.0),
    ("ep_percent", "EP — احتمال وقوع (n-1)", "٪", 1.0),
)


def chart_items(rows: list, key: str) -> list[tuple[str, float | None, str]]:
    """دادهٔ یک شاخص از ردیف‌های فیدر داشبورد → آیتم‌های نمودار."""
    items = []
    for i, r in enumerate(rows or []):
        color = FEEDER_COLORS[i % len(FEEDER_COLORS)]
        if key == "asai_pct":
            raw = r.get("asai")
            value = None if raw is None else float(raw) * 100.0
        else:
            raw = r.get(key)
            value = None if raw is None else float(raw)
        items.append((str(r.get("feeder_key") or "?"), value, color))
    return items
