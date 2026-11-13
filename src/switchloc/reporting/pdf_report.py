# -*- coding: utf-8 -*-
"""pdf_report.py — گزارش PDF فارسی (فاز ۵، ReportLab).

Same `ReportDoc` tree as the Word report, rendered offline to PDF with
true Persian shaping: arabic_reshaper (contextual forms) + python-bidi
(visual reordering) + the bundled Vazirmatn TTF.  Shaping is applied at
the *paragraph* level; tables keep Western digits so numeric columns
stay machine-readable.

Dependencies are optional at runtime (`switchloc[report-pdf]`): when
arabic_reshaper / python-bidi / reportlab / the font are missing the
exporter raises `PdfUnavailableError` with a clear Persian message and
the caller falls back to DOCX (Word prints to PDF natively).

Fonts are looked up in (1) a PyInstaller bundle (`sys._MEIPASS`/
build_assets/fonts), (2) the repo's build_assets/fonts — so BUILD.bat
bundles them with `--add-data build_assets`.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .content import ReportDoc


class PdfUnavailableError(RuntimeError):
    """PDF extras missing (reportlab / arabic_reshaper / bidi / font)."""


def _candidate_font_dirs() -> list[Path]:
    out: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        out.append(Path(meipass) / "build_assets" / "fonts")
        out.append(Path(meipass) / "fonts")
    out.append(Path(__file__).resolve().parents[3] / "build_assets" / "fonts")
    out.append(Path.cwd() / "build_assets" / "fonts")
    return out


def find_font(bold: bool = False) -> Path | None:
    name = f"Vazirmatn-{'Bold' if bold else 'Regular'}.ttf"
    for d in _candidate_font_dirs():
        p = d / name
        if p.exists() and p.stat().st_size > 10_000:
            return p
    return None


def export_pdf(doc_content: ReportDoc, path: str,
               map_png: str | None = None,
               charts_png: str | None = None) -> str:
    """Write the Persian PDF and return the path (raises PdfUnavailableError
    when the optional extras are not installed)."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (BaseDocTemplate, Frame, Image,
                                        NextPageTemplate, PageBreak,
                                        PageTemplate, Paragraph, Spacer, Table,
                                        TableStyle)
    except ImportError as exc:                       # pragma: no cover
        raise PdfUnavailableError(
            "برای خروجی PDF بسته‌های اختیاری لازم است: "
            "pip install -r requirements-report.txt "
            f"(جزئیات: {exc})") from exc

    reg, bold = find_font(False), find_font(True)
    if reg is None or bold is None:
        raise PdfUnavailableError(
            "فونت Vazirmatn یافت نشد (build_assets/fonts). PDF فارسی بدون "
            "این فونت ممکن نیست؛ خروجی Word در دسترس است.")

    pdfmetrics.registerFont(TTFont("Vazir", str(reg)))
    pdfmetrics.registerFont(TTFont("Vazir-Bold", str(bold)))

    reshaper = arabic_reshaper.ArabicReshaper(
        configuration={"delete_harakat": False, "support_ligatures": True})

    #: نویسه‌هایی که فونت وزیرمتن ندارد (یونانی/فلش/نمادها) — جایگزین خوانا
    fallback = {"λ": "لامبدا", "Λ": "لامبدا", "Σ": "سیگما", "Δ": "دلتا",
                "φ": "فی", "Φ": "فی",
                "→": "->", "←": "<-", "↔": "<->", "▸": ">", "★": "*",
                "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
                "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9"}
    #: نویسه‌های نامرئی که نباید جایگزین شوند (ZWNJ و جهت‌دهنده‌ها)
    invisible = {"\u200c", "\u200d", "\u200e", "\u200f", "\ufeff"}
    vazir = pdfmetrics.getFont("Vazir")
    glyphs = getattr(getattr(vazir, "face", None), "charToGlyph", {}) or {}

    def _missing(ch: str) -> bool:
        """آیا فونت این نویسه را دارد؟ (وگرنه مربع خالی در PDF)"""
        if ch in invisible or ch.isspace() or not glyphs:
            return False
        return ord(ch) not in glyphs

    def fa(text: str) -> str:
        """Logical Persian → shaped visual order for ReportLab."""
        if not text:
            return text
        out = str(text)
        if glyphs and any(_missing(ch) for ch in out):
            out = "".join(fallback.get(ch, ch) if _missing(ch) else ch
                          for ch in out)
        return get_display(reshaper.reshape(out))

    S_TITLE = ParagraphStyle("t", fontName="Vazir-Bold", fontSize=17,
                             leading=26, alignment=TA_CENTER,
                             textColor=colors.HexColor("#1F4E79"))
    S_SUB = ParagraphStyle("s", fontName="Vazir", fontSize=12, leading=19,
                           alignment=TA_CENTER,
                           textColor=colors.HexColor("#404040"))
    S_H1 = ParagraphStyle("h1", fontName="Vazir-Bold", fontSize=13,
                          leading=20, alignment=TA_RIGHT,
                          textColor=colors.HexColor("#1F4E79"),
                          spaceBefore=10, spaceAfter=4)
    S_BODY = ParagraphStyle("b", fontName="Vazir", fontSize=10, leading=17,
                            alignment=TA_RIGHT, spaceAfter=5)
    S_EQ = ParagraphStyle("eq", fontName="Vazir-Bold", fontSize=10,
                          leading=16, alignment=TA_CENTER,
                          textColor=colors.HexColor("#0d47a1"),
                          spaceBefore=3, spaceAfter=1)
    S_CAP = ParagraphStyle("c", fontName="Vazir-Bold", fontSize=10,
                           leading=16, alignment=TA_RIGHT, spaceAfter=2)
    S_NOTE = ParagraphStyle("n", fontName="Vazir", fontSize=8, leading=13,
                            alignment=TA_RIGHT,
                            textColor=colors.HexColor("#606060"))
    S_TH = ParagraphStyle("th", fontName="Vazir-Bold", fontSize=8,
                          leading=12, alignment=TA_CENTER,
                          textColor=colors.white)
    S_TD = ParagraphStyle("td", fontName="Vazir", fontSize=8, leading=12,
                          alignment=TA_CENTER)
    # جدول‌های پهن (شاخص‌های فیدرها: ۱۴ ستون) — فونت ریزتر روی صفحهٔ افقی
    S_TH_W = ParagraphStyle("thw", fontName="Vazir-Bold", fontSize=6.5,
                            leading=9.5, alignment=TA_CENTER,
                            textColor=colors.white)
    S_TD_W = ParagraphStyle("tdw", fontName="Vazir", fontSize=6.5, leading=9.5,
                            alignment=TA_CENTER)

    NAVY = colors.HexColor("#1F4E79")
    HEAD_BG = colors.HexColor("#1F4E79")
    GRID = colors.HexColor("#B0B0B0")

    story: list = []

    # ---------------- title page -----------------------------------------
    story += [Spacer(1, 90),
              Paragraph(fa(doc_content.title), S_TITLE),
              Spacer(1, 8),
              Paragraph(fa(doc_content.subtitle), S_SUB),
              Spacer(1, 26)]
    t = Table([[Paragraph(fa(k), S_TD), Paragraph(fa(str(v)), S_TD)]
               for k, v in doc_content.meta],
              colWidths=[150, 315])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF0F7")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [t, PageBreak()]

    # ---------------- sections --------------------------------------------
    for s in doc_content.sections:
        story.append(Paragraph(fa(s.title), S_H1))
        for para in s.intro:
            story.append(Paragraph(fa(para), S_BODY))
        for eq in getattr(s, "equations", None) or []:
            # PDF has no Word-equation object — the same formula is
            # rendered as its standard text form (the docx keeps the
            # genuine OMML equation; the two outputs never diverge)
            story.append(Paragraph(
                fa(f"{eq.caption} — {eq.text}"), S_EQ))
            if eq.note:
                story.append(Paragraph(fa(eq.note), S_NOTE))
        for tb in s.tables:
            story.append(Paragraph(fa(tb.caption), S_CAP))
            if not tb.rows:
                story.append(Paragraph(fa("(بدون ردیف)"), S_BODY))
                continue
            n = len(tb.headers)
            wide = _is_wide_table(n)   # ۱۴ ستون شاخص‌ها در A4 عمودی جا نمی‌شود
            th, td = (S_TH_W, S_TD_W) if wide else (S_TH, S_TD)
            if wide:
                story += [NextPageTemplate("landscape"), PageBreak()]
            data = [[Paragraph(fa(h), th) for h in tb.headers]]
            for row in tb.rows:
                data.append([Paragraph(
                    fa(str(row[j]) if j < len(row) else ""), td)
                    for j in range(n)])
            # first logical column (rightmost visually) a bit wider
            usable = (A4[1] - 72) if wide else (A4[0] - 72)
            widths = _col_widths(n, tb.headers, tb.widths, usable)
            t = Table(data, colWidths=widths, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#F4F7FB")]),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story += [t]
            if wide:
                story += [NextPageTemplate("portrait"), PageBreak()]
            if tb.note:
                story.append(Paragraph(fa("یادداشت: " + tb.note), S_NOTE))
            story.append(Spacer(1, 6))
        for para in s.after:
            story.append(Paragraph(fa(para), S_BODY))

    # ---------------- index charts ------------------------------------------
    if charts_png and Path(charts_png).exists():
        story += [Paragraph(fa("نمودار شاخص‌های ارزیابی فیدرها"), S_H1),
                  Image(charts_png, width=17 * 28.35, height=9.6 * 28.35,
                        kind="proportional")]

    # ---------------- map ---------------------------------------------------
    if map_png and Path(map_png).exists():
        story += [PageBreak(),
                  Paragraph(fa("نقشه شبکه و مکان کلیدهای پیشنهادی"), S_H1),
                  Image(map_png, width=26 * 28.35, height=22 * 28.35,
                        kind="proportional")]

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    def _footer(canv, _doc) -> None:
        canv.saveState()
        canv.setFont("Vazir", 7)
        canv.setFillColor(colors.HexColor("#808080"))
        width = canv._pagesize[0]                      # noqa: SLF001
        canv.drawCentredString(width / 2, 1.1 * 28.35,
                               fa(doc_content.footer))
        canv.restoreState()

    # دو قالب صفحه: عمودی برای متن و جدول‌های باریک، افقی برای جدول‌های
    # پهن (۱۴ ستون شاخص‌های فیدرها) تا سرستون‌ها در هم نریزند.
    pw, ph = A4
    lw, lh = landscape(A4)
    tpl = BaseDocTemplate(str(out), pagesize=A4,
                          title=doc_content.title, author="SwitchLoc")
    tpl.addPageTemplates([
        PageTemplate(id="portrait", pagesize=A4,
                     frames=[Frame(36, 44, pw - 72, ph - 86, id="p")],
                     onPage=_footer),
        PageTemplate(id="landscape", pagesize=landscape(A4),
                     frames=[Frame(36, 34, lw - 72, lh - 74, id="l")],
                     onPage=_footer),
    ])
    tpl.build(story)
    return str(out)


def _is_wide_table(n_columns: int) -> bool:
    """جدول‌های پهن (۹ ستون و بیشتر) باید روی صفحهٔ افقی بروند."""
    return n_columns >= 9


def _col_widths(n: int, headers: list, fractions: list | None = None,
                usable: float = 523.0) -> list:
    """Usable width (523pt portrait / 770pt landscape) — explicit fractions
    when given, else distribute by header length with sane caps."""
    usable = float(usable)
    if fractions and len(fractions) == n:
        k = usable / sum(fractions)
        return [f * k for f in fractions]
    if n == 2:
        return [190, usable - 190]
    if n >= 9:
        # ستون «فیدر» پهن‌تر (نام کامل فیدر) و بقیه بر اساس طول سرستون؛
        # کمینهٔ ۴۰pt تا اعداد (۴۱۸.۳۷) دو خطی نشوند.
        first = usable * 0.145
        rest = usable - first
        weights = [max(len(str(h)), 4) for h in headers[1:]]
        total = sum(weights)
        floor = 40.0            # جای عدد ۵ رقمی مثل «418.37» در فونت ۶.۵
        if floor * len(weights) >= rest:            # خیلی پهن — بی‌کف
            return [first] + [rest * w / total for w in weights]
        extra = rest - floor * len(weights)
        return [first] + [floor + extra * w / total for w in weights]
    weights = [max(len(str(h)), 3) for h in headers]
    total = sum(weights)
    raw = [usable * w / total for w in weights]
    lo = min(34.0, usable / n * 0.55)
    hi = usable * 0.42
    raw = [min(max(v, lo), hi) for v in raw]
    k = usable / sum(raw)
    return [v * k for v in raw]
