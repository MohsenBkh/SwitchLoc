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
}

_BRACE_RE = re.compile(r"\{([^}]+)\}")


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
    # Keep order: braces first (sorted), then others
    ordered = sorted(brace_keys) + sorted(v for v in vars_set if v not in brace_keys)
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
            return str(vars_dict.get(key, m.group(0)))
        return _BRACE_RE.sub(repl, text)

    def _replace_red_fragments_in_para(p) -> bool:
        """Replace red/brace variables inside paragraph; returns True if paragraph was image placeholder."""
        txt_stripped = p.text.strip()
        # Image placeholder handling
        if txt_stripped in _IMAGE_PLACEHOLDERS or txt_stripped.startswith("محل تصویر"):
            # decide image path
            img_path = None
            # count occurrences for sequential same-text placeholders
            cnt = _img_counters.get(txt_stripped, 0)
            _img_counters[txt_stripped] = cnt + 1
            # try sequential extra image first (e.g. second occurrence)
            seq_key = f"{txt_stripped}#{cnt+1}" if cnt > 0 else txt_stripped
            seq_key2 = f"{txt_stripped}#2" if cnt == 1 else None
            if txt_stripped == "feeder_indices.png" and charts_png and Path(charts_png).exists():
                img_path = charts_png
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
                    _run_set_font(r, _font_for_para(p), size_pt=10, color=RGBColor(0, 0, 0))
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
            # avoid replacing parts of braces already handled
            if "{" + key + "}" in original_text:
                continue
            # only replace if key appears as standalone substring (often whole paragraph)
            # To avoid over-replacing common words, require exact or with boundaries
            if key in new_text and key not in ("", " "):
                # For table placeholders like "توسط کاربر تکمیل می شود" etc., whole cell will be checked elsewhere
                # For para, check
                if new_text.strip() == key.strip():
                    new_text = str(val)
                elif key in new_text and len(key) > 3:
                    # cautious: only replace if key length >3 to avoid single-char
                    new_text = new_text.replace(key, str(val))

        if new_text != original_text:
            # Rebuild paragraph runs with single run preserving style but applying correct font
            # Keep original alignment
            align = p.alignment
            p.clear()
            _p_bidi(p)
            p.alignment = align
            # decide font and size: try to infer from original first run size
            # default 11
            size_pt = 11
            is_title = _is_title_para(p)
            font_name = FONT_TITLE if is_title else FONT_BODY
            # bold if original was heading
            bold = is_title
            r = p.add_run(new_text)
            _run_set_font(r, font_name, size_pt=size_pt, bold=bold, color=RGBColor(0, 0, 0))
            return False
        else:
            # No brace change, but recolor red runs to black and enforce fonts
            for r in p.runs:
                if _is_red(r):
                    _run_set_font(r, _font_for_para(p), color=RGBColor(0, 0, 0))
                else:
                    # ensure correct font even for non-red (task 5)
                    # Preserve size if exists
                    sz = r.font.size.pt if r.font.size else None
                    _run_set_font(r, _font_for_para(p), size_pt=sz, color=None)
            _p_bidi(p)
            return False

    # Process all top-level paragraphs
    for p in list(doc.paragraphs):
        _replace_red_fragments_in_para(p)

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
                        # table cells are body font
                        sz = 9 if ri == 0 else 9
                        bold = (ri == 0)
                        _run_set_font(r, FONT_BODY, size_pt=sz, bold=bold, color=RGBColor(0, 0, 0))
                    else:
                        # just enforce fonts and recolor red
                        for r in p.runs:
                            if _is_red(r):
                                _run_set_font(r, FONT_BODY, size_pt=9, bold=(ri == 0), color=RGBColor(0, 0, 0))
                            else:
                                sz = r.font.size.pt if r.font.size else 9
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

    # Post-process: if template has tables that should be auto-filled with real data,
    # do it now (overwrite placeholder red rows).
    if study_model is not None:
        try:
            _fill_tables_from_model(doc, study_model)
        except Exception as e:
            # not fatal
            from ...logging_setup import get_logger
            get_logger("reporting.docx_template").warning("fill tables failed: %s", e)

    # Enforce document default Normal style fonts
    try:
        st = doc.styles["Normal"]
        st.font.name = FONT_BODY
        st.font.size = Pt(11)
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
            for sname in ("Heading 1", "Heading 2", "Heading 3", "Heading 4", "Heading 5"):
                try:
                    hs = doc.styles[sname]
                    hs.font.name = FONT_TITLE
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
    """Populate common template vars from StudyModel if missing."""
    try:
        # feeder name: primary selected feeder or first trace
        feeders = [t.feeder_key for t in getattr(m.topo, "traces", [])]
        primary = feeders[0] if feeders else "نامشخص"
        # if placement has ranking, use top ranked feeder
        try:
            rank_rows = getattr(m.placement.ranking, "rows", [])
            if rank_rows:
                # first ranked is most critical?
                # use feeder with max score?
                top = sorted(rank_rows, key=lambda r: getattr(r, "rank", 0) or 999)[0]
                primary = getattr(top, "feeder_key", primary) or primary
        except Exception:
            pass
        # EENS values: from economics
        econ = getattr(m.placement, "economics", None)
        ens_before = getattr(econ, "ens_before_kwh", {}) if econ else {}
        ens_after_map = getattr(econ, "ens_after_kwh", {}) if econ else {}
        # pick primary's EENS
        def _find(mapping, key):
            if not mapping:
                return None
            if key in mapping:
                return mapping[key]
            from ..topology.tracing import same_feeder
            for k, v in mapping.items():
                if same_feeder(k, key):
                    return v
            return None
        eb = _find(ens_before, primary)
        # ens_after is dict scheme_id -> dict feeder->value
        ea = None
        if ens_after_map:
            for sid, d in ens_after_map.items():
                v = _find(d, primary)
                if v is not None:
                    ea = v
                    break
            if ea is None:
                # fallback first value
                for d in ens_after_map.values():
                    if d:
                        ea = next(iter(d.values()))
                        break
        pct = None
        if eb and ea and eb != 0:
            pct = (eb - ea) / eb * 100.0

        # fill brace keys if not present
        if "نام فیدر" not in vars_dict:
            vars_dict["نام فیدر"] = str(primary)
        if "موقعیت نصب" not in vars_dict and "موقعیت" not in vars_dict:
            # for sectionalizer, موقعیت نصب may be coordinates of proposed switch
            try:
                props = m.build_proposed()
                if props:
                    # use first proposed node's coord
                    ps = props[0]
                    coord_txt = f"{ps.x:.0f}, {ps.y:.0f}" if ps.x and ps.y else ps.node
                    vars_dict["موقعیت نصب"] = coord_txt
                    vars_dict["موقعیت"] = coord_txt
            except Exception:
                pass
        if "نام پست" not in vars_dict:
            # try to infer from graph? Use first part of feeder key?
            # feeder_key like "F6 - سلوط" -> post is "سلوط"
            if " - " in primary:
                vars_dict["نام پست"] = primary.split(" - ", 1)[1].strip()
            else:
                vars_dict["نام پست"] = "نامشخص"
        if "نام شهرستان" not in vars_dict and "نام امور" not in vars_dict:
            vars_dict["نام شهرستان"] = vars_dict.get("نام پست", "نامشخص")
            vars_dict["نام امور"] = vars_dict.get("نام پست", "نامشخص")
        if "جریان فیدر" not in vars_dict:
            # try from load: topo traces load? Use branch? fallback 100
            vars_dict["جریان فیدر"] = "—"
        if "مقدار EENS پایه" not in vars_dict and eb is not None:
            vars_dict["مقدار EENS پایه"] = f"{eb:,.1f}"
        if "مقدار EENS نهایی" not in vars_dict and ea is not None:
            vars_dict["مقدار EENS نهایی"] = f"{ea:,.1f}"
        if "درصد کاهش" not in vars_dict and pct is not None:
            vars_dict["درصد کاهش"] = f"{pct:.1f}"
        if "نام پرعارضه ترین فیدر" not in vars_dict:
            # most λ
            try:
                rows = m.feeder_table()
                if rows:
                    # sort by lambda_per_year descending
                    worst = max(rows, key=lambda r: float(r.get("lambda_per_year") or 0))
                    vars_dict["نام پرعارضه ترین فیدر"] = str(worst.get("feeder_key") or primary)
                    best = min(rows, key=lambda r: float(r.get("lambda_per_year") or 0))
                    vars_dict["نام کم عارضه ترین فیدر"] = str(best.get("feeder_key") or primary)
            except Exception:
                pass
        # date
        if "آبان 1405" not in vars_dict:
            # use current Persian date? Keep template default if not overridden
            pass
    except Exception:
        pass


def _fill_tables_from_model(doc, m) -> None:
    """If template contains data tables with red placeholder values, replace with real numbers."""
    try:
        rows_table = m.feeder_table()
        if not rows_table:
            return
        # For recloser templates, Table1 (6x8) and Table0 (2x6) and Table2 (2x8)
        # For sectionalizer, Table1 (2x7)
        # We will attempt to fill any table whose header matches known patterns
        for t in doc.tables:
            if len(t.rows) < 2 or len(t.columns) < 4:
                continue
            headers = [cell.text.strip() for cell in t.rows[0].cells]
            header_joined = " | ".join(headers)
            # Table with indices (λ, SAIDI etc.)
            if "SAIDI" in header_joined and "SAIFI" in header_joined:
                # This is the indices table (Table1 recloser)
                # Replace its data rows with rows_table filtered to selected?
                # Keep header, replace rows
                # Ensure rows count matches feeders; if mismatch, rebuild
                # Build mapping feeder_key -> row dict
                key_to_row = {str(r.get("feeder_key")): r for r in rows_table}
                # Determine which feeders currently in table (first col)
                existing_feeders = [row.cells[0].text.strip() for row in t.rows[1:]]
                # If existing feeders count differs from rows_table count, we replace with rows_table
                # Else fill in place
                if len(t.rows)-1 != len(rows_table):
                    # Rebuild table to match rows_table length (may be selected only)
                    # Remove extra rows / add rows as needed
                    # Simpler: fill first N rows and hide extras? But spec says only selected feeders should appear.
                    # So rebuild by removing all data rows and adding new ones
                    # Keep header row 0
                    # Remove rows 1..end
                    # Need to recreate rows
                    # docx table has no easy delete; we can clear and add
                    # Instead, fill sequentially and truncate/add
                    # For now, fill existing rows and if need more, add rows
                    # Remove all data rows after header
                    tbl = t._tbl
                    trs = tbl.findall(qn("w:tr"))
                    # keep first tr (header)
                    for tr in trs[1:]:
                        tbl.remove(tr)
                    # add new rows
                    for r in rows_table:
                        cells = t.add_row().cells
                        # fill cells in order matching header: فیدر, طول, λ, r, SAIDI, SAIFI, CAIDI, ENS
                        # header order assumed as in template
                        vals = [
                            str(r.get("feeder_key") or ""),
                            f"{r.get('km') or 0:.2f}",
                            f"{r.get('lambda_per_year') or 0:.2f}",
                            f"{r.get('r_minutes') or 0:.1f}",
                            f"{r.get('saidi') if r.get('saidi') is not None else '—':}",
                            f"{r.get('saifi') if r.get('saifi') is not None else '—':}",
                            f"{r.get('caidi') if r.get('caidi') is not None else '—':}",
                            f"{r.get('ens_per_year_kwh') if r.get('ens_per_year_kwh') is not None else '—':}",
                        ]
                        # header may have 8 cols, ensure vals length
                        for i, v in enumerate(vals[:len(cells)]):
                            p = cells[i].paragraphs[0]
                            p.clear()
                            _p_bidi(p)
                            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            run = p.add_run(str(v))
                            _run_set_font(run, FONT_BODY, size_pt=9, color=RGBColor(0, 0, 0))
                        # style remaining cells empty
                    continue
                else:
                    for i, row in enumerate(t.rows[1:]):
                        if i >= len(rows_table):
                            break
                        r = rows_table[i]
                        # map feeder key order as table order or rows_table order; use rows_table[i]
                        # fill in same order as header expects
                        # but ensure feeder column matches
                        # We'll fill by index i
                        vals = [
                            str(r.get("feeder_key") or ""),
                            f"{r.get('km') or 0:.2f}",
                            f"{r.get('lambda_per_year') or 0:.2f}",
                            f"{r.get('r_minutes') or 0:.1f}",
                            f"{r.get('saidi') if r.get('saidi') is not None else '—'}",
                            f"{r.get('saifi') if r.get('saifi') is not None else '—'}",
                            f"{r.get('caidi') if r.get('caidi') is not None else '—'}",
                            f"{r.get('ens_per_year_kwh') if r.get('ens_per_year_kwh') is not None else '—'}",
                        ]
                        for ci in range(min(len(row.cells), len(vals))):
                            cell = row.cells[ci]
                            p = cell.paragraphs[0]
                            p.clear()
                            _p_bidi(p)
                            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            run = p.add_run(str(vals[ci]))
                            _run_set_font(run, FONT_BODY, size_pt=9, color=RGBColor(0, 0, 0))
            elif "EENS پایه" in header_joined and "EENS نهایی" in header_joined:
                # Table2 recloser or Table1 sectionalizer with EENS summary
                # Fill with primary feeder's EENS
                primary_rows = rows_table[:1]
                if not primary_rows:
                    continue
                r = primary_rows[0]
                # Try to get EENS before/after from economics
                try:
                    econ = getattr(m.placement, "economics", None)
                    eb = None
                    ea = None
                    if econ:
                        eb_dict = getattr(econ, "ens_before_kwh", {})
                        ea_dict = getattr(econ, "ens_after_kwh", {})
                        # find matching feeder
                        from ..topology.tracing import same_feeder
                        for k, v in (eb_dict or {}).items():
                            if same_feeder(k, str(r.get("feeder_key") or "")):
                                eb = v
                                break
                        if not eb and eb_dict:
                            eb = next(iter(eb_dict.values()))
                        for d in (ea_dict or {}).values():
                            if isinstance(d, dict):
                                for k2, v2 in d.items():
                                    if same_feeder(k2, str(r.get("feeder_key") or "")):
                                        ea = v2
                                        break
                                if ea is not None:
                                    break
                        if ea is None and ea_dict:
                            for d in ea_dict.values():
                                if d:
                                    ea = next(iter(d.values()))
                                    break
                    if eb is None:
                        eb = r.get("ens_before_kwh")
                    if ea is None:
                        ea = r.get("ens_per_year_kwh")
                    if eb and ea:
                        pct = (eb - ea) / eb * 100 if eb else 0
                        # Fill table row 1 (first data row)
                        # Header: فیدر, طول پایین دست, بار, EENS پایه, EENS نهایی, کاهش, X, Y (or variations)
                        # For recloser: 8 cols, for sectionalizer: 7 cols
                        # Determine column count
                        row_cells = t.rows[1].cells
                        # feeder
                        vals = {}
                        vals[0] = str(r.get("feeder_key") or "")
                        if len(row_cells) >= 2:
                            vals[1] = f"{r.get('km') or 0:.2f}"
                        if len(row_cells) >= 3:
                            # load?
                            vals[2] = f"{r.get('loads') or ''}"
                        if len(row_cells) >= 4:
                            vals[3] = f"{eb:.2f}" if eb is not None else "—"
                        if len(row_cells) >= 5:
                            vals[4] = f"{ea:.2f}" if ea is not None else "—"
                        if len(row_cells) >= 6:
                            vals[5] = f"{pct:.1f}" if pct is not None else "—"
                        # X,Y from proposed
                        try:
                            props = m.build_proposed()
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
                                p = cell.paragraphs[0]
                                p.clear()
                                _p_bidi(p)
                                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                                run = p.add_run(str(v))
                                _run_set_font(run, FONT_BODY, size_pt=9, color=RGBColor(0, 0, 0))
                except Exception:
                    pass
            elif "فیدر" in header_joined and "پست فوق توزیع" in header_joined:
                # Table0 feeder spec
                if rows_table:
                    r = rows_table[0]
                    row_cells = t.rows[1].cells
                    vals = [
                        str(r.get("feeder_key") or ""),
                        # post name derived from feeder key
                        (str(r.get("feeder_key")).split(" - ",1)[1] if " - " in str(r.get("feeder_key")) else "—"),
                        "—",  # current
                        "—",  # P
                        "—",  # Q
                        f"{r.get('km') or 0:.2f}",
                    ]
                    # For sectionalizer variant with 6 cols but different header: includes ولتاژ (20)
                    # Adjust
                    for ci in range(min(len(row_cells), len(vals))):
                        # keep ولتاژ column as 20 if header contains ولتاژ
                        if headers[ci] and "ولتاژ" in headers[ci]:
                            vals[ci] = "20"
                        cell = row_cells[ci]
                        # don't overwrite if vars_dict already provided placeholder value
                        p = cell.paragraphs[0]
                        # if current text is not red placeholder? But we overwrite anyway with real km
                        p.clear()
                        _p_bidi(p)
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        run = p.add_run(str(vals[ci]))
                        _run_set_font(run, FONT_BODY, size_pt=9, color=RGBColor(0, 0, 0))
    except Exception as e:
        from ...logging_setup import get_logger
        get_logger("reporting.docx_template").warning("table fill error: %s", e)
