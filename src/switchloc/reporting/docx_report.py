# -*- coding: utf-8 -*-
"""docx_report.py — گزارش Word فارسی/RTL (فاز ۵، python-docx).

Renders the neutral `ReportDoc` tree into a right-to-left engineering
report: A4 title page, RTL headings/paragraphs (`w:bidi`), RTL tables
(`w:bidiVisual` — first logical column shows on the right), complex-
script font (Vazirmatn `w:cs`) and the network map with the proposed
switches embedded as a figure.

Word shapes Persian text natively — no reshaping here; the text written
into the XML stays logical-order Unicode (searchable, copyable).
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .content import ReportDoc

FONT = "Vazirmatn"          # falls back gracefully when not installed
_NAVY = RGBColor(0x1F, 0x4E, 0x79)


# ---------------------------------------------------------------------------
# low-level RTL helpers (python-docx has no RTL API — oxml it is)
# ---------------------------------------------------------------------------
def _p_bidi(p) -> None:
    pPr = p._p.get_or_add_pPr()
    if pPr.find(qn("w:bidi")) is None:
        el = OxmlElement("w:bidi")
        el.set(qn("w:val"), "1")
        pPr.append(el)


def _run_fa(run, size: float = 11, bold: bool = False,
            color: RGBColor | None = None) -> None:
    """Persian run: complex-script font + size + rtl."""
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), FONT)
    rFonts.set(qn("w:hAnsi"), FONT)
    rFonts.set(qn("w:cs"), FONT)
    szCs = rPr.find(qn("w:szCs"))
    if szCs is None:
        szCs = OxmlElement("w:szCs")
        rPr.append(szCs)
    szCs.set(qn("w:val"), str(int(size * 2)))
    if bold:
        bCs = rPr.find(qn("w:bCs"))
        if bCs is None:
            bCs = OxmlElement("w:bCs")
            rPr.append(bCs)
    rtl = rPr.find(qn("w:rtl"))
    if rtl is None:
        rtl = OxmlElement("w:rtl")
        rPr.append(rtl)


def _fa_para(doc, text: str, size: float = 11, bold: bool = False,
             align=WD_ALIGN_PARAGRAPH.JUSTIFY, color=None,
             space_after: float = 6) -> object:
    p = doc.add_paragraph()
    _p_bidi(p)
    p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    _run_fa(p.add_run(text), size=size, bold=bold, color=color)
    return p


def _tbl_bidi(table) -> None:
    tblPr = table._tbl.tblPr
    if tblPr.find(qn("w:bidiVisual")) is None:
        tblPr.append(OxmlElement("w:bidiVisual"))


def append_equation(doc, omml_xml: str, caption: str = "",
                    note: str = "") -> None:
    """Inject a genuine Word equation (OMML) — «از قابلیت equation ورد
    استفاده کن» (درخواست کاربر).  The paragraph holds the caption run
    followed by the `<m:oMathPara>` element itself, so the formula is a
    REAL Word equation: double-click in Word opens the equation editor;
    it is neither an image nor plain text."""
    from docx.oxml import parse_xml
    p = doc.add_paragraph()
    _p_bidi(p)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if caption:
        _run_fa(p.add_run(caption + "  —  "), size=10, bold=True,
                color=_NAVY)
    p._p.append(parse_xml(omml_xml))
    p.paragraph_format.space_after = Pt(2)
    if note:
        _fa_para(doc, note, size=9, align=WD_ALIGN_PARAGRAPH.RIGHT,
                 color=RGBColor(0x40, 0x40, 0x40), space_after=8)


def _cell_fa(cell, text: str, bold: bool = False, size: float = 9) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    _p_bidi(p)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run_fa(p.add_run(text), size=size, bold=bold)


# ---------------------------------------------------------------------------
def export_docx(doc_content: ReportDoc, path: str,
                map_png: str | None = None) -> str:
    """Write the Word report and return the path."""
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)     # A4 portrait
    for attr in ("left_margin", "right_margin"):
        setattr(sec, attr, Cm(2.0))
    sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.0)

    # normal style → Persian default
    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(11)

    # ---------------- title page -----------------------------------------
    for _ in range(4):
        doc.add_paragraph()
    _fa_para(doc, doc_content.title, size=20, bold=True,
             align=WD_ALIGN_PARAGRAPH.CENTER, color=_NAVY, space_after=10)
    _fa_para(doc, doc_content.subtitle, size=13,
             align=WD_ALIGN_PARAGRAPH.CENTER, space_after=18)
    t = doc.add_table(rows=len(doc_content.meta), cols=2)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _tbl_bidi(t)
    for i, (kk, vv) in enumerate(doc_content.meta):
        _cell_fa(t.rows[i].cells[0], str(kk), bold=True)
        _cell_fa(t.rows[i].cells[1], str(vv))
        t.rows[i].cells[0].width = Cm(6.5)
        t.rows[i].cells[1].width = Cm(10.0)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ---------------- body ------------------------------------------------
    for s in doc_content.sections:
        _fa_para(doc, s.title, size=15, bold=True,
                 align=WD_ALIGN_PARAGRAPH.RIGHT, color=_NAVY,
                 space_after=8)
        for para in s.intro:
            _fa_para(doc, para)
        for eq in getattr(s, "equations", None) or []:
            append_equation(doc, eq.omml, caption=eq.caption, note=eq.note)
        for tb in s.tables:
            _fa_para(doc, tb.caption, size=11, bold=True,
                     align=WD_ALIGN_PARAGRAPH.RIGHT, space_after=3)
            if not tb.rows:
                _fa_para(doc, "(بدون ردیف)", size=10)
                continue
            n_cols = len(tb.headers)
            t = doc.add_table(rows=1 + len(tb.rows), cols=n_cols)
            t.style = "Table Grid"
            _tbl_bidi(t)
            t.autofit = False
            if tb.widths and len(tb.widths) == n_cols:
                col_cm = [17.0 * w / sum(tb.widths) for w in tb.widths]
            else:
                col_cm = [17.0 / n_cols] * n_cols
            for j, h in enumerate(tb.headers):
                _cell_fa(t.rows[0].cells[j], str(h), bold=True, size=9)
            for i, row in enumerate(tb.rows, start=1):
                for j in range(n_cols):
                    _cell_fa(t.rows[i].cells[j],
                             str(row[j]) if j < len(row) else "",
                             size=9)
            for j, w in enumerate(col_cm):       # fixed column widths
                for r in t.rows:
                    r.cells[j].width = Cm(w)
            if tb.note:
                _fa_para(doc, "یادداشت: " + tb.note, size=9,
                         align=WD_ALIGN_PARAGRAPH.RIGHT, space_after=10)
            else:
                doc.add_paragraph().paragraph_format.space_after = Pt(4)
        for para in s.after:
            _fa_para(doc, para)

    # ---------------- map figure ------------------------------------------
    if map_png and Path(map_png).exists():
        _fa_para(doc, "نقشه شبکه و مکان کلیدهای پیشنهادی", size=15,
                 bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT, color=_NAVY)
        _fa_para(doc, "ستاره‌های سبز مکان کلیدهای پیشنهادی فاز ۴ هستند؛ "
                      "خطوط به رنگ فیدر تفکیک شده‌اند. این تصویر با همان "
                      "موتور ترسیم نقشه نرم‌افزار تولید شده است.", size=10)
        pic_sec = doc.add_section(WD_SECTION.NEW_PAGE)
        pic_sec.orientation = WD_ORIENT.LANDSCAPE
        pic_sec.page_width, pic_sec.page_height = Cm(29.7), Cm(21.0)
        pic_sec.left_margin = pic_sec.right_margin = Cm(1.2)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(map_png, width=Cm(26.5))

    # ---------------- footer note -----------------------------------------
    _fa_para(doc, doc_content.footer, size=9,
             align=WD_ALIGN_PARAGRAPH.CENTER, color=RGBColor(0x60, 0x60, 0x60))

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    return str(out)
