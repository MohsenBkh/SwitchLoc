# -*- coding: utf-8 -*-
"""Template-based Word report (دفترچه مطالعات).

Two supplied templates at repo root:
  * نمونه دفترچه مطالعات ریکلوزر.docx
  * نمونه دفترچه مطالعات سکسیونر.docx

Red runs (font.color.rgb == FF0000) and ``{…}`` placeholders are
variables; everything else is copied verbatim.  Body font enforced to
``B Nazanin``, headings to ``B Titr`` (task 5).  Images for
``feeder_indices.png`` / ``report_map.png`` / user-picked TCC curves are
inserted where the templates contain the placeholder paragraphs
``منحنی توسط کاربر بارگذاری می شود`` / ``تصویر توسط کاربر بارگذاری می شود``
/ ``محل تصویر بارگذاری توسط کاربر`` / ``feeder_indices.png``.
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT, WD_SECTION

FONT_BODY = "B Nazanin"
FONT_TITLE = "B Titr"
_NAVY = RGBColor(0x1F, 0x4E, 0x79)

# placeholder paragraphs that should become images
_IMAGE_PLACEHOLDERS = {
    "منحنی توسط کاربر بارگذاری می شود",
    "تصویر توسط کاربر بارگذاری می شود",
    "محل تصویر بارگذاری توسط کاربر",
    "feeder_indices.png",
    "محل تصویر بارگذاری توسط کاربر ",  # with trailing
    "تصویر فیدر تحت مطالعه از بخش مپ نرم افزار SwitchLoc",
    "نقشه مپ فیدر با فعال سازی برچسب خاموشی ها و توزیع رنگی خاموشی ها مربوط به نرم افزار SwitchLoc",
    "نقشه مپ مربوط به فیدر یا فیدرهای تحت مطالعه استخراجی از SwitchLoc",
}

_BRACE_RE = re.compile(r"\{([^}]+)\}")

_SYNONYM_MAP = {
    "امور مربوطه": "نام امور",
    "نام شهرستان": "نام امور",
    "موقعیت": "موقعیت نصب",
}
_AUTO_VARS = {
    "جریان فیدر", "جریان بار",
    "P_load (kW)/1000", "Q_load (kW)/1000", "Q_load (kW)", "P_load (kW)", "Q_load (kW)/1000",
    "طول فیدر",
    "سایر فیدر1", "سایر فیدر2", "سایر فیدر3", "سایر فیدر4",
    "سایر فیدر1 ", "سایر فیدر2 ", "سایر فیدر3 ", "سایر فیدر4 ",
    "رتبه فیدر از نظرعارضه بندی",
    "مقدار EENS پایه", "مقدار EENS نهایی", "درصد کاهش",
    "EENS پایه", "EENS نهایی", "درصد کاهش EENS",
    "عدد نرخ خرابی", "زمان تعمیر",
    "تعداد کلید", "مختصات کلیدی پیشنهادی",
    "توسط کاربر تکمیل می شود",
}


def _canonical(key: str) -> str:
    k = key.strip()
    return _SYNONYM_MAP.get(k, k)


def _is_red(run) -> bool:
    try:
        c = run.font.color.rgb
        return c is not None and str(c).upper() == "FF0000"
    except Exception:
        return False


def _p_bidi(p) -> None:
    pPr = p._p.get_or_add_pPr()
    if pPr.find(qn("w:bidi")) is None:
        el = OxmlElement("w:bidi")
        el.set(qn("w:val"), "1")
        pPr.append(el)


def _run_set_font(run, font_name: str, size_pt: float | None = None,
                  bold: bool | None = None, color: RGBColor | None = None) -> None:
    run.font.name = font_name
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    else:
        # ensure red becomes black
        try:
            if run.font.color.rgb is not None and str(run.font.color.rgb).upper() == "FF0000":
                run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
        except Exception:
            pass
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), font_name)
    rFonts.set(qn("w:hAnsi"), font_name)
    rFonts.set(qn("w:cs"), font_name)
    if size_pt is not None:
        sz = rPr.find(qn("w:sz"))
        if sz is None:
            sz = OxmlElement("w:sz")
            rPr.append(sz)
        sz.set(qn("w:val"), str(int(size_pt * 2)))
        szCs = rPr.find(qn("w:szCs"))
        if szCs is None:
            szCs = OxmlElement("w:szCs")
            rPr.append(szCs)
        szCs.set(qn("w:val"), str(int(size_pt * 2)))
    rtl = rPr.find(qn("w:rtl"))
    if rtl is None:
        rtl = OxmlElement("w:rtl")
        rPr.append(rtl)


def _is_title_para(p) -> bool:
    try:
        name = (p.style.name or "").lower()
        return "heading" in name or "title" in name
    except Exception:
        return False


def _font_for_para(p) -> str:
    # Heading or caption bold? Use Titr for titles, Nazanin for body
    if _is_title_para(p):
        return FONT_TITLE
    # also captions that are bold titles -> Titr
    try:
        if p.alignment == WD_ALIGN_PARAGRAPH.CENTER and any(r.bold for r in p.runs):
            return FONT_TITLE
    except Exception:
        pass
    return FONT_BODY


def extract_variables(template_path: str) -> list[str]:
    """Return distinct variable keys from red runs + {braces}.

    Only meaningful placeholders are returned (brace inners + dates,
    report numbers and user-image placeholders). Pure numeric table data
    (sample numbers) are excluded — they are auto-filled from StudyModel.
    """
    doc = Document(str(template_path))
    brace_keys: set[str] = set()
    for p in doc.paragraphs:
        for m in _BRACE_RE.finditer(p.text):
            brace_keys.add(m.group(1).strip())
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for m in _BRACE_RE.finditer(cell.text):
                    brace_keys.add(m.group(1).strip())
    vars_set: set[str] = set(brace_keys)
    # Helpful non-brace placeholders: whole-paragraph red texts that are not numeric
    # e.g. "آبان 1405", "PD-21-001", "توسط کاربر تکمیل می شود", image placeholders
    import re as _re
    _num_re = _re.compile(r"^[\d\.\,\s\u06F0-\u06F9\u0660-\u0669]+$")
    for p in doc.paragraphs:
        txt = p.text.strip()
        if not txt:
            continue
        # consider paragraph if it is predominantly red
        red_runs = [r for r in p.runs if _is_red(r) and r.text.strip()]
        if not red_runs:
            continue
        # whole paragraph red? or contains brace? Skip numeric-only paras (table sample numbers are in tables, not paras)
        # For paras, include date/number/report and image placeholders
        # Heuristics: keep if contains Persian letters or is date/image marker
        if txt in brace_keys or ("{" + txt + "}") in p.text:
            continue
        # Table data numbers are not in paras; paras red are usually headers like "آبان 1405"
        # Keep if not purely numeric and length > 2
        if _num_re.match(txt):
            continue
        # Split case: paragraph "مقدار EENS پایه" fragmented across runs — already covered by brace
        # But paragraphs like "آبان 1405" single run => keep
        # Paragraphs like "منحنی توسط کاربر بارگذاری می شود" => keep as image placeholder hint (but not prompted as editable var)
        # We expose only date/number + a few image hints; image placeholders are handled via file pickers, not text edit
        # So we keep only short meaningful texts: date and report number
        if txt in ("آبان 1405", "آبان", "1405", "PD-21-001", "PD-15-003") or txt.startswith("PD-") or "PD-" in txt:
            # extract PD number substring
            import re as _re2
            m = _re2.search(r"PD-[\d\-]+", txt)
            if m:
                vars_set.add(m.group(0))
            else:
                vars_set.add(txt)
        elif "توسط کاربر" in txt or "بارگذاری توسط کاربر" in txt or txt == "feeder_indices.png":
            # image placeholders — not editable text, skip from var prompt (they are file pickers)
            continue
        elif len(txt) < 30 and any("\u0600" <= c <= "\u06FF" for c in txt):
            # short Persian red para not part of braces (e.g. maybe a header) — keep if not numeric
            # but avoid fragments like "EENS", "PD-"
            if txt not in ("EENS", "PD-", "سلوط") and not _num_re.match(txt):
                # Only keep if paragraph is exactly the red fragment (not a sentence with braces)
                # Sentences with braces already handled; pure red sentences like "آبان 1405" kept above
                # So for safety, don't add other sentence fragments
                pass
    # Tables: only "توسط کاربر تکمیل می شود" is user-editable table placeholder
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                ctext = cell.text.strip()
                if ctext == "توسط کاربر تکمیل می شود":
                    vars_set.add(ctext)
    # Canonicalize and unify synonyms (requirement 9) and filter auto-calculated vars (requirements 4,5,6,10)
    # Filter out image placeholders (they are file pickers, not text vars)
    def _is_image_key(k: str) -> bool:
        kk = k.strip()
        # without braces inner
        if kk in _IMAGE_PLACEHOLDERS:
            return True
        # with braces? inner may have the same
        # heuristics for long map/chart placeholders
        if "نقشه مپ" in kk or "SwitchLoc" in kk and "مپ" in kk:
            return True
        if kk in ("تصویر فیدر تحت مطالعه از بخش مپ نرم افزار SwitchLoc",):
            return True
        return False
    canon_brace = {_canonical(k) for k in brace_keys if not _is_image_key(k) and k not in _IMAGE_PLACEHOLDERS}
    canon_all = {_canonical(k) for k in vars_set if not _is_image_key(k)}
    filtered_brace = sorted(k for k in canon_brace if k not in _AUTO_VARS)
    other_keys = sorted(k for k in canon_all if k not in canon_brace and k not in _AUTO_VARS)
    ordered = filtered_brace + other_keys
    return ordered


def apply_template(template_path: str, output_path: str,
                   vars_dict: dict[str, str] | None = None,
                   map_png: str | None = None,
                   charts_png: str | None = None,
                   extra_images: dict[str, str] | None = None,
                   study_model=None) -> str:
    """Fill template red/{…} placeholders with vars_dict and save.

    * vars_dict: mapping from variable name (brace inner or red fragment) to
      replacement text.  Missing keys keep original.
    * map_png / charts_png: if given, inserted where image placeholders live.
    * extra_images: mapping placeholder text -> image path (user-picked TCC etc.)
    * study_model: optional StudyModel to auto-fill tables where red values are
      data-driven (feeder specs, indices, EENS).
    """
    vars_dict = dict(vars_dict or {})
    extra_images = dict(extra_images or {})
    # expand vars_dict to include canonical and synonym variants so template placeholders with synonyms match
    # Ensure canonical keys map to provided values and vice versa
    _expanded = {}
    for k, v in list(vars_dict.items()):
        ck = _canonical(k)
        _expanded[k] = v
        _expanded[ck] = v
        # also propagate to all synonyms that share same canonical
        for syn, can in _SYNONYM_MAP.items():
            if can == ck and syn not in _expanded:
                _expanded[syn] = v
            if syn == k and can not in _expanded:
                _expanded[can] = v
    vars_dict = _expanded
    template_path = str(template_path)
    output_path = str(output_path)
    doc = Document(template_path)

    # Auto-derive some vars from study_model when not supplied
    if study_model is not None:
        try:
            _auto_fill_vars_from_model(vars_dict, study_model)
        except Exception:
            pass

    # Determine which image goes to which placeholder
    # Order: first image placeholder -> charts, second -> map, rest -> extra or map again
    # But templates have specific order: recloser has feeder_indices.png then 2x curve placeholders
    # sectionalizer has محل تصویر ... (Fig1) then 2x تصویر ...
    # We map intelligently: "feeder_indices.png" -> charts_png, "محل تصویر..." -> map_png, others -> extra or map
    _img_counters: dict[str, int] = {}

    # Helper to replace braces in text
    def _replace_braces(text: str) -> str:
        def repl(m):
            key = m.group(1).strip()
            # try direct, then canonical
            if key in vars_dict:
                return str(vars_dict[key])
            ck = _canonical(key)
            if ck in vars_dict:
                return str(vars_dict[ck])
            return m.group(0)
        return _BRACE_RE.sub(repl, text)

    def _replace_red_fragments_in_para(p) -> bool:
        """Replace red/brace variables inside paragraph; returns True if paragraph was image placeholder."""
        txt_stripped = p.text.strip()
        # Normalize brace-wrapped image placeholders like {نقشه مپ ...}
        _norm = txt_stripped.strip().strip("{} ").strip()
        _is_img = (txt_stripped in _IMAGE_PLACEHOLDERS or _norm in _IMAGE_PLACEHOLDERS
                   or txt_stripped.startswith("محل تصویر") or _norm.startswith("محل تصویر")
                   or "نقشه مپ فیدر با فعال سازی" in txt_stripped or "نقشه مپ فیدر با فعال سازی" in _norm
                   or txt_stripped == "تصویر فیدر تحت مطالعه از بخش مپ نرم افزار SwitchLoc"
                   or _norm == "تصویر فیدر تحت مطالعه از بخش مپ نرم افزار SwitchLoc")
        # Image placeholder handling
        if _is_img:
            # decide image path
            img_path = None
            # count occurrences for sequential same-text placeholders
            cnt = _img_counters.get(txt_stripped, 0)
            _img_counters[txt_stripped] = cnt + 1
            # try sequential extra image first (e.g. second occurrence)
            seq_key = f"{txt_stripped}#{cnt+1}" if cnt > 0 else txt_stripped
            seq_key2 = f"{txt_stripped}#2" if cnt == 1 else None
            # also handle brace-wrapped and long Persian placeholders
            _norm_for_img = _norm
            if txt_stripped == "feeder_indices.png" and charts_png and Path(charts_png).exists():
                img_path = charts_png
            elif _norm_for_img == "نقشه مپ فیدر با فعال سازی برچسب خاموشی ها و توزیع رنگی خاموشی ها مربوط به نرم افزار SwitchLoc" and charts_png and Path(charts_png).exists():
                img_path = charts_png
            elif txt_stripped in ("محل تصویر بارگذاری توسط کاربر", "محل تصویر بارگذاری توسط کاربر ", "تصویر فیدر تحت مطالعه از بخش مپ نرم افزار SwitchLoc", "{تصویر فیدر تحت مطالعه از بخش مپ نرم افزار SwitchLoc}", "{نقشه مپ فیدر با فعال سازی برچسب خاموشی ها و توزیع رنگی خاموشی ها مربوط به نرم افزار SwitchLoc}") and map_png and Path(map_png).exists():
                img_path = map_png
            elif _norm_for_img in ("محل تصویر بارگذاری توسط کاربر", "تصویر فیدر تحت مطالعه از بخش مپ نرم افزار SwitchLoc", "نقشه مپ فیدر با فعال سازی برچسب خاموشی ها و توزیع رنگی خاموشی ها مربوط به نرم افزار SwitchLoc") and map_png and Path(map_png).exists():
                img_path = map_png
            elif txt_stripped in ("محل تصویر بارگذاری توسط کاربر", "محل تصویر بارگذاری توسط کاربر ") and map_png and Path(map_png).exists():
                img_path = map_png
            elif seq_key in extra_images and extra_images[seq_key] and Path(extra_images[seq_key]).exists():
                img_path = extra_images[seq_key]
            elif seq_key2 and seq_key2 in extra_images and Path(extra_images[seq_key2]).exists():
                img_path = extra_images[seq_key2]
            elif txt_stripped in extra_images and extra_images[txt_stripped] and Path(extra_images[txt_stripped]).exists():
                # For first occurrence, use base key; for second occurrence with same text but only base provided,
                # still use base (will duplicate) — but prefer extra cover
                img_path = extra_images[txt_stripped]
            elif charts_png and Path(charts_png).exists() and "feeder_indices" not in txt_stripped:
                # fallback: for generic تصویر placeholders, prefer map then charts
                # sectionalizer Fig3/4 are coverage maps (user images) — if no extra, keep placeholder text
                if map_png and Path(map_png).exists() and txt_stripped == "تصویر توسط کاربر بارگذاری می شود":
                    # First generic image after Fig2 will be map? But for sectionalizer Fig3/4 are coverage — leave if no user image
                    # Only auto-fill if study has no extra; otherwise leave text
                    pass
                img_path = None
            if img_path:
                # Replace paragraph content with image
                # Clear paragraph
                p.clear()
                _p_bidi(p)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run()
                # preserve font for caption? not needed for image
                try:
                    run.add_picture(img_path, width=Cm(15.5))
                except Exception:
                    # fallback width
                    run.add_picture(img_path, width=Cm(12))
                # enforce fonts on this paragraph (no text)
                return True
            # no image available: just replace red fragments with vars if any, keep text but make black
            if txt_stripped in vars_dict:
                new_txt = str(vars_dict[txt_stripped])
                if p.text != new_txt:
                    # rebuild
                    p.clear()
                    _p_bidi(p)
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    r = p.add_run(new_txt)
                    _run_set_font(r, _font_for_para(p), size_pt=13, color=RGBColor(0, 0, 0))
                else:
                    # just recolor
                    for r in p.runs:
                        _run_set_font(r, _font_for_para(p), color=RGBColor(0, 0, 0))
                return False
        # General brace + red replacement for paragraph
        original_text = p.text
        if not original_text.strip():
            return False
        # If paragraph contains braces, do brace substitution
        new_text = _replace_braces(original_text)
        # Also handle direct red fragment replacement where whole red run equals key
        # For each red run text that is a key in vars_dict, replace that substring
        # Since runs are split, easiest to do on full paragraph text: replace occurrences of red keys
        for key, val in vars_dict.items():
            if "{" + key + "}" in original_text:
                continue
            # Only replace when the whole paragraph exactly equals the key (for red non-brace vars like "آبان 1405", "PD-...")
            # Do not do substring replacement to avoid corrupting normal text containing words like "موقعیت"
            if new_text.strip() == key.strip():
                new_text = str(val)

        if new_text != original_text:
            # Rebuild paragraph runs — enforce 18 for titles, 13 for body (requirements 2,3)
            align = p.alignment
            # capture title state BEFORE clear (style + bold/center heuristics)
            try:
                pre_font = _font_for_para(p)
                is_title_before = (pre_font == FONT_TITLE) or _is_title_para(p)
            except Exception:
                is_title_before = _is_title_para(p)
            p.clear()
            _p_bidi(p)
            p.alignment = align
            size_pt = 18 if is_title_before else 13
            font_name = FONT_TITLE if is_title_before else FONT_BODY
            bold = True if is_title_before else False
            r = p.add_run(new_text)
            _run_set_font(r, font_name, size_pt=size_pt, bold=bold, color=RGBColor(0, 0, 0))
            return False
        else:
            # No brace change, but recolor red runs to black and enforce fonts to 13/18 (requirements 2,3)
            try:
                tgt_font = _font_for_para(p)
                is_t = (tgt_font == FONT_TITLE)
            except Exception:
                is_t = _is_title_para(p)
                tgt_font = FONT_TITLE if is_t else FONT_BODY
            tgt_sz = 18 if is_t else 13
            for r in p.runs:
                if _is_red(r):
                    _run_set_font(r, tgt_font, size_pt=tgt_sz, bold=is_t, color=RGBColor(0, 0, 0))
                else:
                    _run_set_font(r, tgt_font, size_pt=tgt_sz, bold=(r.bold if not is_t else True), color=None)
            _p_bidi(p)
            return False

    # Process all top-level paragraphs
    for p in list(doc.paragraphs):
        _replace_red_fragments_in_para(p)

    # Per new spec: enforce specific paragraph sizes/spacings
    for p in doc.paragraphs:
        txt = p.text.strip()
        if not txt:
            continue
        # Fixed cover title always 20 B Titr
        if txt == "دفترچه مطالعات جایابی تجهیزات و هماهنگی حفاظتی" or "دفترچه مطالعات جایابی تجهیزات و هماهنگی حفاظتی" in txt and len(txt) < 80 and p.alignment == WD_ALIGN_PARAGRAPH.CENTER:
            for r in p.runs:
                _run_set_font(r, FONT_TITLE, size_pt=20, bold=True, color=_NAVY)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            # keep original space_after (30) as is
        # Month-year (e.g., آبان 1405, آذر 1405) -> 12 and space_after 18 (was 60)
        _months = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")
        is_month = (txt in ("آبان 1405", "آذر 1405", "دی 1405") or any(m in txt for m in _months) and any(y in txt for y in ("1404", "1405", "1406", "1403", "1407")) and len(txt) < 30)
        if txt == "آبان 1405" or is_month or (len(txt) < 20 and ("1405" in txt or "1406" in txt) and any(m in txt for m in _months)):
            for r in p.runs:
                _run_set_font(r, FONT_BODY, size_pt=12, bold=True, color=RGBColor(0, 0, 0))
            p.paragraph_format.space_after = Pt(18)
            p.paragraph_format.space_before = Pt(0)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            # also ensure if txt is like "آذر 1405" we still catch it
        # Fallback generic: any short centered paragraph containing year
        elif len(txt) < 25 and ("1405" in txt or "1406" in txt) and p.alignment == WD_ALIGN_PARAGRAPH.CENTER:
            for r in p.runs:
                _run_set_font(r, FONT_BODY, size_pt=12, bold=True, color=RGBColor(0, 0, 0))
            p.paragraph_format.space_after = Pt(18)
        # Also handle any red "آبان" fragmented? The paragraph may be "آبان 1405" split across runs but text is that
        # Doc number PD-... -> 12
        if "PD-" in txt and ("شماره گزارش" in txt or txt.startswith("PD-")):
            for r in p.runs:
                # doc number is red, make black 12
                sz = 12
                # preserve bold
                _run_set_font(r, FONT_BODY, size_pt=sz, bold=r.bold if r.bold is not None else True, color=RGBColor(0, 0, 0) if _is_red(r) else None)
            p.paragraph_format.space_after = Pt(4)  # keep small
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        # Headings that must be B Titr 12 per spec — exact subheadings only (not the main Heading 1 "3- تحلیل ...")
        _is_param_heading = txt.strip() in ("پارامترهای مؤثر فیدر (نرخ خرابی و زمان تعمیر)", "پارامترهای موثر فیدر (نرخ خرابی و زمان تعمیر)", "پارامترهای موثر فیدر") or txt.strip().startswith("پارامترهای مؤثر فیدر") and not txt.strip().startswith("پارامترهای تأثیرگذار")
        _is_spec_heading = txt.strip() == "مشخصات فنی و نتایج بهینه‌سازی فیدر"
        _is_indices_heading = txt.strip() in ("شاخص‌های قابلیت اطمینان:", "شاخص\u200cهای قابلیت اطمینان:")
        if txt.strip() in ("پارامترهای مؤثر فیدر (نرخ خرابی و زمان تعمیر)", "پارامترهای موثر فیدر (نرخ خرابی و زمان تعمیر)", "پارامترهای موثر فیدر", "مشخصات فنی و نتایج بهینه‌سازی فیدر", "شاخص‌های قابلیت اطمینان:", "شاخص\u200cهای قابلیت اطمینان:") or _is_param_heading or _is_spec_heading or _is_indices_heading:
            for r in p.runs:
                _run_set_font(r, FONT_TITLE, size_pt=12, bold=True, color=RGBColor(0, 0, 0))
            # keep original alignment but ensure right for these headings (they are Heading 4 left? but spec says right)
            # Our templates have them as Heading 4 with no explicit alignment; keep as is but ensure not centered
            if p.alignment == WD_ALIGN_PARAGRAPH.CENTER:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            # also override style size if needed
            try:
                p.style.font.size = Pt(12)
            except Exception:
                pass

    # Process tables: replace brace placeholders and red cell values
    for t in doc.tables:
        # detect header row (first row) — keep as is but enforce fonts
        for ri, row in enumerate(t.rows):
            for ci, cell in enumerate(row.cells):
                for p in list(cell.paragraphs):
                    original = p.text
                    # check if cell is image placeholder (unlikely in table)
                    # brace replacement
                    new_text = _replace_braces(original)
                    # direct var mapping for whole cell
                    stripped = original.strip()
                    if stripped in vars_dict:
                        new_text = str(vars_dict[stripped])
                    elif stripped and stripped in _IMAGE_PLACEHOLDERS:
                        # leave
                        pass
                    else:
                        # check red fragments inside cell
                        for key, val in vars_dict.items():
                            if key in new_text and len(key) > 2 and "{" + key + "}" not in original:
                                if new_text.strip() == key.strip():
                                    new_text = str(val)
                                # don't over-replace inside table numbers
                    if new_text != original:
                        # rebuild cell paragraph
                        align = p.alignment
                        p.clear()
                        _p_bidi(p)
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        r = p.add_run(new_text)
                        # table cells are body font — requirement 8: header 12 bold, body 12
                        sz = 12
                        bold = (ri == 0)
                        _run_set_font(r, FONT_BODY, size_pt=sz, bold=bold, color=RGBColor(0, 0, 0))
                    else:
                        # just enforce fonts and recolor red — requirement 8
                        for r in p.runs:
                            if _is_red(r):
                                _run_set_font(r, FONT_BODY, size_pt=12, bold=(ri == 0), color=RGBColor(0, 0, 0))
                            else:
                                sz = r.font.size.pt if r.font.size else 12
                                # ensure at least 12 for body, unless heading
                                if sz is not None and sz < 12:
                                    sz = 12
                                _run_set_font(r, FONT_BODY, size_pt=sz, bold=(ri == 0) if ri == 0 else r.bold, color=None)
                        _p_bidi(p)
        # enforce bidiVisual
        try:
            from docx.oxml.ns import qn as _qn
            tblPr = t._tbl.tblPr
            if tblPr.find(_qn("w:bidiVisual")) is None:
                tblPr.append(OxmlElement("w:bidiVisual"))
        except Exception:
            pass

    # Post-process: fill tables with main feeder data (use hidden lookup key for technical, display for name)
    if study_model is not None:
        try:
            # derive primary lookup and display for tables
            _tbl_primary = None
            _tbl_display = None
            for hk in ("__main_feeder_key", "_main_feeder_key", "__selected_feeder_key"):
                if hk in vars_dict and str(vars_dict[hk]).strip():
                    _tbl_primary = str(vars_dict[hk]).strip()
                    break
            _tbl_display = str(vars_dict.get("نام فیدر") or "").strip() or _tbl_primary
            # fallback to first feeder if still none
            if not _tbl_primary:
                try:
                    _tbl_primary = [t.feeder_key for t in getattr(study_model.topo, "traces", [])][:1][0]
                except Exception:
                    _tbl_primary = _tbl_display
            _fill_tables_from_model(doc, study_model, primary_key=_tbl_primary, display_name=_tbl_display)
        except Exception as e:
            # not fatal
            from ...logging_setup import get_logger
            get_logger("reporting.docx_template").warning("fill tables failed: %s", e)

    # Enforce document default Normal style fonts
    try:
        st = doc.styles["Normal"]
        st.font.name = FONT_BODY
        st.font.size = Pt(13)
        # set rFonts for Normal
        rPr = st.element.find(qn("w:rPr"))
        if rPr is not None:
            rFonts = rPr.find(qn("w:rFonts"))
            if rFonts is None:
                rFonts = OxmlElement("w:rFonts")
                rPr.append(rFonts)
            rFonts.set(qn("w:ascii"), FONT_BODY)
            rFonts.set(qn("w:hAnsi"), FONT_BODY)
            rFonts.set(qn("w:cs"), FONT_BODY)
            # also Heading styles to Titr
            for sname in ("Heading 1", "Heading 2", "Heading 3", "Heading 4", "Heading 5", "Title"):
                try:
                    hs = doc.styles[sname]
                    hs.font.name = FONT_TITLE
                    # enforce size 18 for titles (requirement 2)
                    hs.font.size = Pt(18)
                    hrPr = hs.element.find(qn("w:rPr"))
                    if hrPr is not None:
                        hr = hrPr.find(qn("w:rFonts"))
                        if hr is None:
                            hr = OxmlElement("w:rFonts")
                            hrPr.append(hr)
                        hr.set(qn("w:ascii"), FONT_TITLE)
                        hr.set(qn("w:hAnsi"), FONT_TITLE)
                        hr.set(qn("w:cs"), FONT_TITLE)
                except Exception:
                    pass
    except Exception:
        pass

    # Also enforce bidi on all paragraphs
    for p in doc.paragraphs:
        _p_bidi(p)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    return str(output_path)


def _auto_fill_vars_from_model(vars_dict: dict, m) -> None:
    """Populate common template vars from StudyModel if missing — auto-calculated.

    Per requirements:
    4 - جریان فیدر/بار from P/Q (S/(√3·20kV))
    5 - EENS base/final + reduction auto (not prompted)
    9 - نام امور / امور مربوطه / نام شهرستان unify
    9 - موقعیت / موقعیت نصب unify
    10+11 - sectionalizer EENS also auto, based on selected switch type/results
    12 - if multi-feeder, main feeder name should be asked (handled in dialog) — here we respect existing value
    """
    try:
        import math
        # --- primary feeder: separate display (Persian) vs technical lookup (English) ---
        feeders = [t.feeder_key for t in getattr(m.topo, "traces", [])] if getattr(m, "topo", None) else []
        # Lookup key (English feeder_key) for all technical params — from hidden __main_feeder_key
        # Display name (Persian) for {نام فیدر} is vars_dict["نام فیدر"] as typed by user
        display_name = str(vars_dict.get("نام فیدر") or "").strip()
        lookup_key = ""
        for hk in ("__main_feeder_key", "_main_feeder_key", "__selected_feeder_key", "_selected_feeder_key"):
            if hk in vars_dict and str(vars_dict[hk]).strip():
                lookup_key = str(vars_dict[hk]).strip()
                break
        # Also try selected_feeders from model if no hidden key
        if not lookup_key:
            # try to infer from display_name if it looks like English key and matches a feeder
            if display_name:
                # exact match or same_feeder
                for fk in feeders:
                    if display_name == fk:
                        lookup_key = fk
                        break
                    try:
                        from ..topology.tracing import same_feeder
                        if same_feeder(display_name, fk):
                            lookup_key = fk
                            break
                    except Exception:
                        pass
                # if display_name is Persian (no match), keep lookup empty to fallback to first/feeders or ranking
        if not lookup_key:
            if feeders:
                # if multi-feeder but no hidden key, use first as fallback but this is now considered bug case — should be hidden
                # Prefer ranking top if single? Keep first
                lookup_key = feeders[0]
            else:
                lookup_key = display_name or "نامشخص"
            try:
                rank_rows = getattr(m.placement.ranking, "rows", [])
                if rank_rows and len(feeders) == 1:
                    top = sorted(rank_rows, key=lambda r: getattr(r, "rank", 0) or 999)[0]
                    lookup_key = getattr(top, "feeder_key", lookup_key) or lookup_key
            except Exception:
                pass
        # primary for technical lookups
        primary = lookup_key
        # keep display_name for UI: if no display, fallback to lookup
        if not display_name:
            display_name = primary

        # --- EENS values: try placement economics first, then sectionalizer study, then fallback ---
        eb = ea = pct = None
        try:
            econ = getattr(m.placement, "economics", None)
            ens_before = getattr(econ, "ens_before_kwh", {}) if econ else {}
            ens_after_map = getattr(econ, "ens_after_kwh", {}) if econ else {}
            def _find(mapping, key):
                if not mapping:
                    return None
                if key in mapping:
                    return mapping[key]
                # Try normalized and same_feeder and feeder_key matching
                try:
                    from ..topology.tracing import same_feeder, feeder_key
                except Exception:
                    same_feeder = None
                    feeder_key = lambda x: x
                # 1) same_feeder (handles short vs full)
                if same_feeder is not None:
                    for k, v in mapping.items():
                        try:
                            if same_feeder(k, key):
                                return v
                        except Exception:
                            pass
                # 2) feeder_key short token match
                try:
                    kkey = feeder_key(key) if callable(feeder_key) else None
                    if kkey:
                        for k, v in mapping.items():
                            if feeder_key(k) == kkey:
                                return v
                except Exception:
                    pass
                # 3) case-insensitive normalized (upper, dash)
                try:
                    import re
                    def _norm(s):
                        s = (s or "").strip().upper()
                        s = re.sub(r"\s+", " ", s)
                        s = re.sub(r"\s*-\s*", " - ", s)
                        return s
                    nk = _norm(key)
                    for k, v in mapping.items():
                        if _norm(k) == nk:
                            return v
                except Exception:
                    pass
                return None
            eb = _find(ens_before, primary)
            # No unconditional fallback to first — keep None to try other sources (feeder_table, eens_study)
            # Only fallback if mapping has single entry and primary was not specified (i.e., primary is fallback itself)
            # So do not fallback here.
            if ens_after_map:
                for sid, d in ens_after_map.items():
                    v = _find(d, primary)
                    if v is not None:
                        ea = v
                        break
                # Do not fallback to first when primary specified — keep None
        except Exception:
            pass
        # fallback to sectionalizer/EENS study if placement EENS missing (requirement 10-11)
        if eb is None or ea is None:
            try:
                eens_study = getattr(m, "eens_study", None) or {}
                # newest: study is dict with "study" -> feeders -> before/best
                study_data = eens_study.get("study") if isinstance(eens_study, dict) else None
                if study_data and isinstance(study_data, dict):
                    feeders_eens = study_data.get("feeders") or []
                    # try robust match for primary
                    def _match_feeder(a,b):
                        if not a or not b:
                            return False
                        if str(a).strip() == str(b).strip():
                            return True
                        try:
                            from ..topology.tracing import same_feeder, feeder_key
                            if same_feeder(str(a), str(b)):
                                return True
                            if feeder_key(str(a)) == feeder_key(str(b)):
                                return True
                        except Exception:
                            pass
                        import re
                        def _n(s): return re.sub(r"\s*-\s*", " - ", re.sub(r"\s+", " ", str(s).strip().upper()))
                        return _n(a) == _n(b)
                    for f in feeders_eens:
                        if _match_feeder(f.get("feeder_key"), primary):
                            eb = f.get("baseline_eens_kwh")
                            # best may be under f["best"] or f["best_eens_kwh"]
                            best = f.get("best") or {}
                            if isinstance(best, dict):
                                ea = best.get("eens_kwh") if "eens_kwh" in best else best.get("best_eens_kwh")
                            if ea is None:
                                ea = f.get("best_eens_kwh")
                            break
                    # Do not fallback to first feeder when primary not found — keep None to avoid mixing
                    # (previous code incorrectly used first feeder's data for wrong feeder)
                    pass
                # also try top-level baseline/best
                if eb is None and isinstance(eens_study, dict):
                    # study might be directly at top level? Check m.eens_study["study"]["baseline_eens_kwh"]
                    try:
                        sd = eens_study.get("study") or eens_study
                        if "baseline_eens_kwh" in sd:
                            eb = sd.get("baseline_eens_kwh")
                            ea = sd.get("best_eens_kwh") if "best_eens_kwh" in sd else sd.get("best", {}).get("eens_kwh")
                    except Exception:
                        pass
            except Exception:
                pass
        # also try feeder_table fallback for EENS (indices)
        if eb is None or ea is None or (eb is not None and eb == 0):
            try:
                rows_ft = m.feeder_table()
                def _match(a,b):
                    if str(a).strip() == str(b).strip():
                        return True
                    try:
                        from ..topology.tracing import same_feeder, feeder_key
                        if same_feeder(str(a), str(b)):
                            return True
                        if feeder_key(str(a)) == feeder_key(str(b)):
                            return True
                    except Exception:
                        pass
                    import re
                    def _n(s): return re.sub(r"\s*-\s*", " - ", re.sub(r"\s+", " ", str(s).strip().upper()))
                    return _n(a) == _n(b)
                for r in rows_ft:
                    if _match(r.get("feeder_key"), primary):
                        # Try economics first, then outage indices ens
                        if r.get("ens_before_kwh") is not None and (eb is None or eb == 0):
                            # Only use if non-zero or if no other source
                            if r.get("ens_before_kwh") not in (None, 0) or eb is None:
                                eb = r.get("ens_before_kwh")
                        # Fallback to outage indices ens_per_year_kwh (in kWh) if still missing/zero
                        if (eb is None or eb == 0) and r.get("ens_per_year_kwh") not in (None, 0):
                            eb = r.get("ens_per_year_kwh")
                        # No after value in feeder_table, so keep ea as is (will show dash)
                        break
            except Exception:
                pass
        if eb is not None and ea is not None and eb != 0:
            try:
                pct = (eb - ea) / eb * 100.0
            except Exception:
                pct = None

        # --- helper to get feeder P/Q and compute current ---
        def _load_pq_for_feeder(feeder_key: str):
            p_kw = q_kvar = None
            # try m.load_model if exists
            try:
                lm = getattr(m, "load_model", None)
                if lm and isinstance(lm, dict):
                    pq = (lm.get("feeder_pq") or {}).get(feeder_key)
                    if pq:
                        p_kw = float(pq.get("p_kw") or 0) if pq.get("p_kw") is not None else None
                        q_kvar = float(pq.get("q_kvar") or 0) if pq.get("q_kvar") is not None else None
            except Exception:
                pass
            # try ProjectStore if db_path available
            if p_kw is None or q_kvar is None:
                try:
                    dbp = getattr(m, "db_path", None)
                    if dbp:
                        from ..persistence.store import ProjectStore
                        store = ProjectStore(str(dbp))
                        try:
                            from ..persistence.engineering_load import load_load_model
                            lm2 = load_load_model(str(dbp))
                            pq2 = (lm2.get("feeder_pq") or {}).get(feeder_key)
                            if pq2:
                                if p_kw is None and pq2.get("p_kw") is not None:
                                    p_kw = float(pq2.get("p_kw"))
                                if q_kvar is None and pq2.get("q_kvar") is not None:
                                    q_kvar = float(pq2.get("q_kvar"))
                        finally:
                            store.close()
                except Exception:
                    pass
            # fallback to placement load_model?
            if p_kw is None:
                try:
                    lm3 = getattr(getattr(m.placement, "settings", None), "load_model", None)  # not likely
                    pass
                except Exception:
                    pass
            return p_kw, q_kvar

        p_kw, q_kvar = _load_pq_for_feeder(primary)
        # also get km and other feeder_table metrics
        km_val = None
        lambda_val = r_val = None
        try:
            rows = m.feeder_table()
            def _km_match(a,b):
                if str(a).strip() == str(b).strip():
                    return True
                try:
                    from ..topology.tracing import same_feeder, feeder_key
                    if same_feeder(str(a), str(b)):
                        return True
                    if feeder_key(str(a)) == feeder_key(str(b)):
                        return True
                except Exception:
                    pass
                import re
                def _n(s): return re.sub(r"\s*-\s*", " - ", re.sub(r"\s+", " ", str(s).strip().upper()))
                return _n(a) == _n(b)
            for r in rows:
                if _km_match(r.get("feeder_key"), primary):
                    km_val = r.get("km")
                    lambda_val = r.get("lambda_per_year")
                    r_val = r.get("r_minutes")
                    break
        except Exception:
            pass

        # --- current calculation (requirement 4) ---
        current_a = None
        if p_kw is not None and q_kvar is not None:
            try:
                s_kva = math.hypot(float(p_kw), float(q_kvar))
                # 20 kV base per template: I = S/(√3·V)
                current_a = s_kva / (math.sqrt(3) * 20.0)
            except Exception:
                current_a = None
        # if P/Q not available, try to estimate from feeder_table's km? fallback
        current_str = f"{current_a:.2f}" if current_a is not None else "—"

        # --- fill brace keys if not present (auto) ---

        # Display name: only if not already typed by user, fallback to lookup key
        if "نام فیدر" not in vars_dict or not str(vars_dict["نام فیدر"]).strip():
            # if user typed Persian display, keep it; else use lookup key or display_name
            vars_dict["نام فیدر"] = str(display_name or primary)

        # موقعیت / موقعیت نصب unify (requirement 9)
        if "موقعیت نصب" not in vars_dict and "موقعیت" not in vars_dict:
            try:
                props = m.build_proposed()
                # also consider sectionalizer nodes if placement empty
                if not props:
                    # try sectionalizer study nodes
                    try:
                        eens = getattr(m, "eens_study", {}) or {}
                        study = eens.get("study") if isinstance(eens, dict) else None
                        if study:
                            for f in (study.get("feeders") or []):
                                cands = (f.get("best") or {}).get("selected") or []
                                if cands:
                                    c = cands[0]
                                    coord = c.get("coord")
                                    if coord and len(coord)==2:
                                        coord_txt = f"{float(coord[0]):.0f}, {float(coord[1]):.0f}"
                                        vars_dict["موقعیت نصب"] = coord_txt
                                        vars_dict["موقعیت"] = coord_txt
                                        break
                    except Exception:
                        pass
                if props:
                    ps = props[0]
                    coord_txt = f"{ps.x:.0f}, {ps.y:.0f}" if ps.x and ps.y else ps.node
                    vars_dict["موقعیت نصب"] = coord_txt
                    vars_dict["موقعیت"] = coord_txt
                elif "موقعیت" not in vars_dict and "موقعیت نصب" not in vars_dict:
                    # fallback to feeder name only if not already set from eens_study
                    vars_dict["موقعیت نصب"] = str(primary)
                    vars_dict["موقعیت"] = str(primary)
            except Exception:
                pass
        # ensure synonym consistency: if one exists, copy to other
        if "موقعیت نصب" in vars_dict and "موقعیت" not in vars_dict:
            vars_dict["موقعیت"] = vars_dict["موقعیت نصب"]
        if "موقعیت" in vars_dict and "موقعیت نصب" not in vars_dict:
            vars_dict["موقعیت نصب"] = vars_dict["موقعیت"]

        if "نام پست" not in vars_dict:
            if " - " in primary:
                vars_dict["نام پست"] = primary.split(" - ", 1)[1].strip()
            else:
                # try to infer from net?
                try:
                    # feeder_key may be like "F1 - MESHKIN" -> post MESHKIN
                    # Already handled
                    vars_dict["نام پست"] = "نامشخص"
                except Exception:
                    vars_dict["نام پست"] = "نامشخص"

        # نام امور / امور مربوطه / نام شهرستان unify (requirement 9)
        # canonical is "نام امور"
        post_name = vars_dict.get("نام پست", "نامشخص")
        if "نام امور" not in vars_dict and "امور مربوطه" not in vars_dict and "نام شهرستان" not in vars_dict:
            vars_dict["نام امور"] = post_name
            vars_dict["امور مربوطه"] = post_name
            vars_dict["نام شهرستان"] = post_name
        else:
            # propagate to synonyms
            canonical = vars_dict.get("نام امور") or vars_dict.get("امور مربوطه") or vars_dict.get("نام شهرستان") or post_name
            vars_dict["نام امور"] = canonical
            vars_dict["امور مربوطه"] = canonical
            vars_dict["نام شهرستان"] = canonical

        # جریان (unify)
        for key in ("جریان فیدر", "جریان بار"):
            if key not in vars_dict:
                vars_dict[key] = current_str

        # P/Q auto (for table placeholders like P_load, Q_load)
        # These are in MW/Mvar in template as /1000
        if p_kw is not None:
            # p_kw in kW
            vars_dict.setdefault("P_load (kW)/1000", f"{p_kw/1000.0:.2f}")
            vars_dict.setdefault("P_load (kW)", f"{p_kw:.2f}")
            # also handle without space variant? Already trimmed brace inner strips, so key exactly as above
        else:
            vars_dict.setdefault("P_load (kW)/1000", "—")
            vars_dict.setdefault("P_load (kW)", "—")
        if q_kvar is not None:
            vars_dict.setdefault("Q_load (kW)/1000", f"{q_kvar/1000.0:.2f}")
            vars_dict.setdefault("Q_load (kW)/1000", f"{q_kvar/1000.0:.2f}")
            vars_dict.setdefault("Q_load (kW)", f"{q_kvar:.2f}")
        else:
            vars_dict.setdefault("Q_load (kW)/1000", "—")
            vars_dict.setdefault("Q_load (kW)", "—")

        if km_val is not None:
            vars_dict.setdefault("طول فیدر", f"{km_val:.2f}")
        else:
            # try from feeder_table already? fallback
            vars_dict.setdefault("طول فیدر", "—")

        # EENS auto - handle both naming variants, formatted to 2 decimals (requirement 6 + 5 +10)
        # Always ensure brace vars are filled (with dash if missing) to avoid leftover { } in docx
        try:
            eb_mwh = None
            ea_mwh = None
            pct_val = None
            if eb is not None:
                eb_mwh = eb/1000.0 if eb > 500 else eb
                pct_val = pct
            if ea is not None:
                ea_mwh = ea/1000.0 if ea > 500 else ea
            # If eb present, set پایه; else set dash if not already provided
            for k in ("مقدار EENS پایه", "EENS پایه"):
                if k not in vars_dict:
                    if eb_mwh is not None:
                        vars_dict[k] = f"{eb_mwh:.2f}"
                    else:
                        vars_dict[k] = "—"
            for k in ("مقدار EENS نهایی", "EENS نهایی"):
                if k not in vars_dict:
                    if ea_mwh is not None:
                        vars_dict[k] = f"{ea_mwh:.2f}"
                    else:
                        vars_dict[k] = "—"
            for k in ("درصد کاهش", "درصد کاهش EENS"):
                if k not in vars_dict:
                    if pct_val is not None and eb_mwh is not None and ea_mwh is not None:
                        vars_dict[k] = f"{pct_val:.2f}"
                    elif eb_mwh is not None and ea_mwh is not None:
                        # fallback compute
                        try:
                            _pct = (eb - ea)/eb*100.0 if eb else 0
                            vars_dict[k] = f"{_pct:.2f}"
                        except Exception:
                            vars_dict[k] = "—"
                    else:
                        vars_dict[k] = "—"
        except Exception:
            pass
        # also handle mixed: if only one of each pair missing
        if "EENS پایه" not in vars_dict and "مقدار EENS پایه" in vars_dict:
            vars_dict["EENS پایه"] = vars_dict["مقدار EENS پایه"]
        if "مقدار EENS پایه" not in vars_dict and "EENS پایه" in vars_dict:
            vars_dict["مقدار EENS پایه"] = vars_dict["EENS پایه"]
        if "EENS نهایی" not in vars_dict and "مقدار EENS نهایی" in vars_dict:
            vars_dict["EENS نهایی"] = vars_dict["مقدار EENS نهایی"]
        if "مقدار EENS نهایی" not in vars_dict and "EENS نهایی" in vars_dict:
            vars_dict["مقدار EENS نهایی"] = vars_dict["EENS نهایی"]
        if "درصد کاهش EENS" not in vars_dict and "درصد کاهش" in vars_dict:
            vars_dict["درصد کاهش EENS"] = vars_dict["درصد کاهش"]
        if "درصد کاهش" not in vars_dict and "درصد کاهش EENS" in vars_dict:
            vars_dict["درصد کاهش"] = vars_dict["درصد کاهش EENS"]

        # other auto vars
        # lambda and repair
        if lambda_val is not None:
            vars_dict.setdefault("عدد نرخ خرابی", f"{lambda_val:.2f}")
        else:
            # try from lambda matrix directly?
            vars_dict.setdefault("عدد نرخ خرابی", "—")
        if r_val is not None:
            vars_dict.setdefault("زمان تعمیر", f"{r_val:.2f}")
        else:
            vars_dict.setdefault("زمان تعمیر", "—")

        # تعداد کلید and مختصات
        try:
            props = m.build_proposed()
            cnt = len(props) if props else 0
            # also check sectionalizer count if placement empty
            if cnt == 0:
                try:
                    eens = getattr(m, "eens_study", {}) or {}
                    study = eens.get("study") if isinstance(eens, dict) else None
                    if study:
                        for f in (study.get("feeders") or []):
                            cands = (f.get("best") or {}).get("selected") or []
                            cnt += len(cands)
                except Exception:
                    pass
            vars_dict.setdefault("تعداد کلید", str(cnt) if cnt else "—")
            # مختصات
            coord_txt = vars_dict.get("موقعیت نصب") or vars_dict.get("موقعیت") or ""
            if "مختصات کلیدی پیشنهادی" not in vars_dict:
                if props:
                    # join all coords
                    coords = []
                    for ps in props:
                        if ps.x and ps.y:
                            coords.append(f"{ps.x:.0f}, {ps.y:.0f}")
                        else:
                            coords.append(ps.node)
                    vars_dict["مختصات کلیدی پیشنهادی"] = " | ".join(coords) if coords else coord_txt
                else:
                    # try sectionalizer coords
                    try:
                        eens = getattr(m, "eens_study", {}) or {}
                        study = eens.get("study") if isinstance(eens, dict) else None
                        if study:
                            ccs=[]
                            for f in (study.get("feeders") or []):
                                for c in ((f.get("best") or {}).get("selected") or []):
                                    coord = c.get("coord")
                                    if coord and len(coord)==2:
                                        ccs.append(f"{float(coord[0]):.0f}, {float(coord[1]):.0f}")
                            if ccs:
                                vars_dict["مختصات کلیدی پیشنهادی"] = " | ".join(ccs)
                            else:
                                vars_dict.setdefault("مختصات کلیدی پیشنهادی", coord_txt or "—")
                        else:
                            vars_dict.setdefault("مختصات کلیدی پیشنهادی", coord_txt or "—")
                    except Exception:
                        vars_dict.setdefault("مختصات کلیدی پیشنهادی", coord_txt or "—")
        except Exception:
            pass

        # پرعارضه etc
        if "نام پرعارضه ترین فیدر" not in vars_dict or "نام کم عارضه ترین فیدر" not in vars_dict or "رتبه فیدر از نظرعارضه بندی" not in vars_dict:
            try:
                rows = m.feeder_table()
                if rows:
                    worst = max(rows, key=lambda r: float(r.get("lambda_per_year") or 0))
                    best = min(rows, key=lambda r: float(r.get("lambda_per_year") or 0))
                    if "نام پرعارضه ترین فیدر" not in vars_dict:
                        vars_dict["نام پرعارضه ترین فیدر"] = str(worst.get("feeder_key") or primary)
                    if "نام کم عارضه ترین فیدر" not in vars_dict:
                        vars_dict["نام کم عارضه ترین فیدر"] = str(best.get("feeder_key") or primary)
                    # رتبه
                    if "رتبه فیدر از نظرعارضه بندی" not in vars_dict:
                        # rank by lambda descending: 1 is worst
                        sorted_rows = sorted(rows, key=lambda r: float(r.get("lambda_per_year") or 0), reverse=True)
                        rank = next((i+1 for i, r in enumerate(sorted_rows) if str(r.get("feeder_key") or "") == primary), 1)
                        vars_dict["رتبه فیدر از نظرعارضه بندی"] = str(rank)
                        # also simple "رتبه فیدر"? Not in template but keep
                # سایر فیدر1..4
                others = [r.get("feeder_key") for r in rows if str(r.get("feeder_key") or "") != primary] if rows else []
                for idx in range(1,5):
                    key = f"سایر فیدر{idx}"
                    # template has trailing space like "سایر فیدر1 " - we handle via stripped, but also ensure that exact key with space is covered?
                    # Our brace inner is stripped, so "سایر فیدر1" matches. Provide.
                    if key not in vars_dict:
                        if idx-1 < len(others):
                            vars_dict[key] = str(others[idx-1])
                        else:
                            vars_dict[key] = "—"
                    # also handle variant with space
                    if f"سایر فیدر{idx} " not in vars_dict and key in vars_dict:
                        vars_dict[f"سایر فیدر{idx} "] = vars_dict[key]
            except Exception:
                pass

        # ensure synonyms after all
        if "موقعیت نصب" in vars_dict and "موقعیت" not in vars_dict:
            vars_dict["موقعیت"] = vars_dict["موقعیت نصب"]
        if "موقعیت" in vars_dict and "موقعیت نصب" not in vars_dict:
            vars_dict["موقعیت نصب"] = vars_dict["موقعیت"]
        for canonical, synonyms in [("نام امور", ["امور مربوطه", "نام شهرستان"]), ("موقعیت نصب", ["موقعیت"])]:
            if canonical in vars_dict:
                for syn in synonyms:
                    if syn not in vars_dict:
                        vars_dict[syn] = vars_dict[canonical]

    except Exception:
        pass


def _fill_tables_from_model(doc, m, primary_key: str | None = None, display_name: str | None = None) -> None:
    """If template contains data tables with red placeholder values, replace with real numbers.
    Requirement 6: all table values to two decimals.
    Requirement 8: header 12 bold, body 12 (handled via font patch).
    """
    try:
        rows_table = m.feeder_table()
        if not rows_table:
            return
        for t in doc.tables:
            if len(t.rows) < 2 or len(t.columns) < 4:
                continue
            headers = [cell.text.strip() for cell in t.rows[0].cells]
            header_joined = " | ".join(headers)
            # Table with indices (λ, SAIDI etc.) — recloser Table1
            if "SAIDI" in header_joined and "SAIFI" in header_joined:
                # rebuild to match rows_table exactly (per selected feeders)
                tbl = t._tbl
                trs = tbl.findall(qn("w:tr"))
                for tr in trs[1:]:
                    tbl.remove(tr)
                for r in rows_table:
                    cells = t.add_row().cells
                    # ensure two decimals for all numeric columns (req 6)
                    def _fmt(v):
                        if v is None:
                            return "—"
                        try:
                            return f"{float(v):.2f}"
                        except Exception:
                            return str(v)
                    # SAIDI/SAIFI etc may be None -> "—" else two decimals
                    vals = [
                        str(r.get("feeder_key") or ""),
                        f"{float(r.get('km') or 0):.2f}",
                        f"{float(r.get('lambda_per_year') or 0):.2f}",
                        f"{float(r.get('r_minutes') or 0):.2f}",
                        _fmt(r.get("saidi")),
                        _fmt(r.get("saifi")),
                        _fmt(r.get("caidi")),
                        _fmt(r.get("ens_per_year_kwh")),
                    ]
                    for i, v in enumerate(vals[:len(cells)]):
                        p_ = cells[i].paragraphs[0]
                        p_.clear()
                        _p_bidi(p_)
                        p_.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        run = p_.add_run(str(v))
                        _run_set_font(run, FONT_BODY, size_pt=12, color=RGBColor(0, 0, 0))
                continue
            elif "EENS پایه" in header_joined and "EENS نهایی" in header_joined:
                # Use main feeder (lookup key) if provided, else first
                r = None
                if primary_key:
                    # robust match: exact -> same_feeder -> feeder_key -> normalized
                    try:
                        from ..topology.tracing import same_feeder, feeder_key
                    except Exception:
                        same_feeder = None
                        feeder_key = lambda x: x
                    import re
                    def _norm(s):
                        s = (s or "").strip().upper()
                        s = re.sub(r"\s+", " ", s)
                        s = re.sub(r"\s*-\s*", " - ", s)
                        return s
                    nk = _norm(primary_key)
                    for cand in rows_table:
                        ck = str(cand.get("feeder_key") or "")
                        if ck == primary_key:
                            r = cand
                            break
                        try:
                            if same_feeder is not None and same_feeder(ck, primary_key):
                                r = cand
                                break
                        except Exception:
                            pass
                        try:
                            if feeder_key is not None and feeder_key(ck) == feeder_key(primary_key):
                                # Only if one is short? But still prefer if same_feeder failed due to different suffix?
                                # Use short match only if one is short token?
                                # For safety, allow short match when normalized full not equal but short equal and one is short?
                                # We already have same_feeder handling short cases; keep short match as fallback for case like F4 vs F4 - South?
                                if _norm(ck) == nk:
                                    r = cand
                                    break
                                # Also check short token equality as last resort
                                if feeder_key(ck) == feeder_key(primary_key):
                                    # Ensure not mixing F2-MESHKIN vs F2-KOLOOR (different full): same_feeder would have rejected, but short token matches incorrectly
                                    # So only allow if one is exactly short token
                                    if _norm(ck) == feeder_key(primary_key) or nk == feeder_key(ck):
                                        r = cand
                                        break
                        except Exception:
                            pass
                        if _norm(ck) == nk:
                            r = cand
                            break
                if r is None:
                    # fallback to first only if single feeder or no primary
                    primary_rows = rows_table[:1]
                    if not primary_rows:
                        continue
                    r = primary_rows[0]
                # Try to get EENS before/after from economics or eens_study (consistent with _auto_fill)
                eb = ea = pct = None
                try:
                    econ = getattr(m.placement, "economics", None)
                    if econ:
                        eb_dict = getattr(econ, "ens_before_kwh", {}) or {}
                        ea_dict = getattr(econ, "ens_after_kwh", {}) or {}
                        from ..topology.tracing import same_feeder, feeder_key
                        import re
                        def _norm(s):
                            s = (s or "").strip().upper()
                            s = re.sub(r"\s+", " ", s)
                            s = re.sub(r"\s*-\s*", " - ", s)
                            return s
                        def _match(a,b):
                            if not a or not b:
                                return False
                            if str(a).strip() == str(b).strip():
                                return True
                            try:
                                if same_feeder(str(a), str(b)):
                                    return True
                                if feeder_key(str(a)) == feeder_key(str(b)):
                                    return True
                            except Exception:
                                pass
                            return _norm(a) == _norm(b)
                        for k, v in (eb_dict or {}).items():
                            if _match(k, str(r.get("feeder_key") or "")):
                                eb = v
                                break
                        # do not fallback to first when primary specified
                        for d in (ea_dict or {}).values():
                            if isinstance(d, dict):
                                for k2, v2 in d.items():
                                    if _match(k2, str(r.get("feeder_key") or "")):
                                        ea = v2
                                        break
                                if ea is not None:
                                    break
                        # no fallback to first
                    # fallback to eens_study with robust matching
                    if eb is None or ea is None:
                        eens = getattr(m, "eens_study", {}) or {}
                        study = eens.get("study") if isinstance(eens, dict) else None
                        if study:
                            import re
                            def _norm2(s):
                                s = (s or "").strip().upper()
                                s = re.sub(r"\s+", " ", s)
                                s = re.sub(r"\s*-\s*", " - ", s)
                                return s
                            def _match2(a,b):
                                if str(a).strip() == str(b).strip():
                                    return True
                                try:
                                    from ..topology.tracing import same_feeder, feeder_key
                                    if same_feeder(str(a), str(b)):
                                        return True
                                    if feeder_key(str(a)) == feeder_key(str(b)):
                                        return True
                                except Exception:
                                    pass
                                return _norm2(a) == _norm2(b)
                            for f in (study.get("feeders") or []):
                                if _match2(f.get("feeder_key"), str(r.get("feeder_key") or "")):
                                    eb = f.get("baseline_eens_kwh") if eb is None else eb
                                    best = f.get("best") or {}
                                    if isinstance(best, dict):
                                        ea = best.get("eens_kwh") if ea is None else ea
                                    break
                except Exception:
                    pass
                # Fallback to feeder_table's outage EENS if still missing or zero (for recloser where economics is 0)
                if (eb is None or eb == 0) and r.get("ens_per_year_kwh") not in (None, 0):
                    eb = r.get("ens_per_year_kwh")
                if (eb is None or eb == 0) and r.get("ens_before_kwh") not in (None, 0):
                    eb = r.get("ens_before_kwh")
                # If ea still None, keep dash (do not use total kpis as per-feeder)
                # compute pct and display conversion (always convert kWh->MWh when >500)
                if eb is not None and ea is not None:
                    try:
                        pct = (eb - ea) / eb * 100.0 if eb else 0
                        # convert to MWh for display if large (kWh -> MWh)
                        eb_disp = eb/1000.0 if eb > 500 else eb
                        ea_disp = ea/1000.0 if ea > 500 else ea
                    except Exception:
                        eb_disp, ea_disp, pct = eb, ea, 0
                else:
                    # keep dash for missing; still convert eb if present
                    try:
                        eb_disp = eb/1000.0 if eb is not None and eb > 500 else eb
                        ea_disp = ea/1000.0 if ea is not None and ea > 500 else ea
                    except Exception:
                        eb_disp, ea_disp = eb, ea
                    pct = None
                # Fill first data row
                row_cells = t.rows[1].cells
                vals = {}
                vals[0] = str(display_name or r.get("feeder_key") or "")
                if len(row_cells) >= 2:
                    vals[1] = f"{float(r.get('km') or 0):.2f}"
                if len(row_cells) >= 3:
                    try:
                        p_kw = None
                        try:
                            lm0 = getattr(m, "load_model", None)
                            if isinstance(lm0, dict):
                                pq0 = (lm0.get("feeder_pq") or {}).get(str(r.get("feeder_key") or "")) or {}
                                p_kw = pq0.get("p_kw")
                        except Exception:
                            pass
                        if p_kw is None:
                            try:
                                from ..persistence.store import ProjectStore
                                if getattr(m, "db_path", None):
                                    store = ProjectStore(str(m.db_path))
                                    try:
                                        from ..persistence.engineering_load import load_load_model
                                        lm = load_load_model(str(m.db_path))
                                        pq = (lm.get("feeder_pq") or {}).get(str(r.get("feeder_key") or "")) or {}
                                        p_kw = pq.get("p_kw")
                                    finally:
                                        store.close()
                            except Exception:
                                pass
                        if p_kw is not None:
                            vals[2] = f"{float(p_kw):.2f}"
                        else:
                            vals[2] = f"{float(r.get('loads') or 0):.2f}"  # fallback
                    except Exception:
                        vals[2] = f"{float(r.get('loads') or 0):.2f}"
                if len(row_cells) >= 4:
                    vals[3] = f"{eb_disp:.2f}" if eb_disp is not None else "—"
                if len(row_cells) >= 5:
                    vals[4] = f"{ea_disp:.2f}" if ea_disp is not None else "—"
                if len(row_cells) >= 6:
                    vals[5] = f"{pct:.2f}" if pct is not None else "—"
                # X,Y or مختصات
                try:
                    props = m.build_proposed()
                    # also check sectionalizer
                    if not props:
                        eens = getattr(m, "eens_study", {}) or {}
                        study = eens.get("study") if isinstance(eens, dict) else None
                        if study:
                            for f in (study.get("feeders") or []):
                                for c in ((f.get("best") or {}).get("selected") or []):
                                    coord = c.get("coord")
                                    if coord and len(coord)==2 and len(row_cells) >=7:
                                        vals[6] = f"{float(coord[0]):.0f}, {float(coord[1]):.0f}"
                                        break
                    else:
                        if props and len(row_cells) >= 8:
                            ps = props[0]
                            vals[6] = f"{ps.x:.0f}" if ps.x else ""
                            vals[7] = f"{ps.y:.0f}" if ps.y else ""
                        elif props and len(row_cells) == 7:
                            ps = props[0]
                            vals[6] = f"{ps.x:.0f},{ps.y:.0f}" if ps.x and ps.y else ps.node
                except Exception:
                    pass
                for ci, v in vals.items():
                    if ci < len(row_cells):
                        cell = row_cells[ci]
                        p_ = cell.paragraphs[0]
                        p_.clear()
                        _p_bidi(p_)
                        p_.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        run = p_.add_run(str(v))
                        _run_set_font(run, FONT_BODY, size_pt=12, color=RGBColor(0, 0, 0))
            elif "فیدر" in header_joined and "پست فوق توزیع" in header_joined:
                # Use main feeder for spec table (robust)
                if rows_table:
                    r = None
                    if primary_key:
                        try:
                            from ..topology.tracing import same_feeder, feeder_key
                        except Exception:
                            same_feeder = None
                            feeder_key = lambda x: x
                        import re
                        def _norm2(s):
                            s = (s or "").strip().upper()
                            s = re.sub(r"\s+", " ", s)
                            s = re.sub(r"\s*-\s*", " - ", s)
                            return s
                        nk2 = _norm2(primary_key)
                        for cand in rows_table:
                            ck2 = str(cand.get("feeder_key") or "")
                            if ck2 == primary_key:
                                r = cand
                                break
                            try:
                                if same_feeder is not None and same_feeder(ck2, primary_key):
                                    r = cand
                                    break
                            except Exception:
                                pass
                            if _norm2(ck2) == nk2:
                                r = cand
                                break
                            try:
                                if feeder_key is not None and feeder_key(ck2) == feeder_key(primary_key) and (_norm2(ck2) == feeder_key(primary_key) or nk2 == feeder_key(ck2)):
                                    r = cand
                                    break
                            except Exception:
                                pass
                    if r is None:
                        r = rows_table[0]
                    row_cells = t.rows[1].cells
                    # compute current/P/Q as in auto_fill — check model first then db (requirements 4,6)
                    try:
                        import math
                        p_kw = q_kvar = None
                        # try model.load_model dict first (live run)
                        try:
                            lm = getattr(m, "load_model", None)
                            if isinstance(lm, dict):
                                pq = (lm.get("feeder_pq") or {}).get(str(r.get("feeder_key") or "")) or {}
                                p_kw = pq.get("p_kw")
                                q_kvar = pq.get("q_kvar")
                        except Exception:
                            pass
                        # try db fallback if still missing
                        if p_kw is None or q_kvar is None:
                            try:
                                from ..persistence.store import ProjectStore
                                if getattr(m, "db_path", None):
                                    store = ProjectStore(str(m.db_path))
                                    try:
                                        from ..persistence.engineering_load import load_load_model
                                        lm2 = load_load_model(str(m.db_path))
                                        pq2 = (lm2.get("feeder_pq") or {}).get(str(r.get("feeder_key") or "")) or {}
                                        if p_kw is None:
                                            p_kw = pq2.get("p_kw")
                                        if q_kvar is None:
                                            q_kvar = pq2.get("q_kvar")
                                    finally:
                                        store.close()
                            except Exception:
                                pass
                        s_current = "—"
                        p_mw = q_mvar = "—"
                        if p_kw is not None and q_kvar is not None:
                            s_kva = math.hypot(float(p_kw), float(q_kvar))
                            cur = s_kva / (math.sqrt(3)*20.0)
                            s_current = f"{cur:.2f}"
                            p_mw = f"{float(p_kw)/1000.0:.2f}"
                            q_mvar = f"{float(q_kvar)/1000.0:.2f}"
                        # also keep raw kW for sectionalizer's P_load (kW) variant
                        _disp = str(display_name or r.get("feeder_key") or "")
                        vals = [
                            _disp,
                            (str(display_name or r.get("feeder_key") or "").split(" - ",1)[1] if " - " in str(display_name or r.get("feeder_key") or "") else (str(r.get("feeder_key") or "").split(" - ",1)[1] if " - " in str(r.get("feeder_key") or "") else "—")),
                            s_current,
                            p_mw,
                            q_mvar,
                            f"{float(r.get('km') or 0):.2f}",
                        ]
                    except Exception as e:
                        _disp = str(display_name or r.get("feeder_key") or "")
                        vals = [
                            _disp,
                            (str(display_name or r.get("feeder_key") or "").split(" - ",1)[1] if " - " in str(display_name or r.get("feeder_key") or "") else (str(r.get("feeder_key") or "").split(" - ",1)[1] if " - " in str(r.get("feeder_key") or "") else "—")),
                            "—",
                            "—",
                            "—",
                            f"{float(r.get('km') or 0):.2f}",
                        ]
                    for ci in range(min(len(row_cells), len(vals))):
                        if headers[ci] and "ولتاژ" in headers[ci]:
                            vals[ci] = "20.00"
                        cell = row_cells[ci]
                        p_ = cell.paragraphs[0]
                        p_.clear()
                        _p_bidi(p_)
                        p_.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        run = p_.add_run(str(vals[ci]))
                        _run_set_font(run, FONT_BODY, size_pt=12, color=RGBColor(0, 0, 0))
    except Exception as e:
        from ...logging_setup import get_logger
        get_logger("reporting.docx_template").warning("table fill error: %s", e)
