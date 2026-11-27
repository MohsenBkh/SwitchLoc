# -*- coding: utf-8 -*-
"""Dialog to collect variable values for template-based report."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QRadioButton, QScrollArea, QVBoxLayout, QWidget,
)

from ...reporting.docx_template import extract_variables

TEMPLATE_RECL = "نمونه دفترچه مطالعات ریکلوزر.docx"
TEMPLATE_SEC = "نمونه دفترچه مطالعات سکسیونر.docx"
TEMPLATE_SECT = "نمونه دفترچه مطالعات سکشنالایزر.docx"  # optional: dedicated sectionalizer template; fallback to SEC


def _find_templates() -> dict[str, Path]:
    import sys
    import unicodedata
    _PERSIAN_FIX = str.maketrans({"ي": "ی", "ك": "ک"})
    def _norm_name(s: str) -> str:
        s = s.translate(_PERSIAN_FIX)
        s = unicodedata.normalize("NFC", s)
        return s
    substrings = {
        "ریکلوزر": TEMPLATE_RECL,
        "سکسیونر": TEMPLATE_SEC,
        "سکشنالایزر": TEMPLATE_SECT,
        "recloser": TEMPLATE_RECL,
        "sectionalizer": TEMPLATE_SECT,
        "disconnector": TEMPLATE_SEC,
        "سکسیونر": TEMPLATE_SEC,
    }
    norm_expected = { _norm_name(TEMPLATE_RECL): TEMPLATE_RECL, _norm_name(TEMPLATE_SEC): TEMPLATE_SEC, _norm_name(TEMPLATE_SECT): TEMPLATE_SECT }
    candidates_roots: list[Path] = []
    # cwd and ancestors
    try:
        cur = Path.cwd().resolve()
        for _ in range(8):
            candidates_roots.append(cur)
            if cur.parent == cur:
                break
            cur = cur.parent
    except Exception:
        pass
    # exe / frozen
    try:
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            cur = exe_dir
            for _ in range(8):
                candidates_roots.append(cur)
                if cur.parent == cur:
                    break
                cur = cur.parent
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                try:
                    mp_path = Path(meipass).resolve()
                    candidates_roots.append(mp_path)
                    candidates_roots.append(mp_path.parent)
                    candidates_roots.append(mp_path / "_internal")
                except Exception:
                    candidates_roots.append(Path(meipass))
    except Exception:
        pass
    # __file__ ancestors
    try:
        cur = Path(__file__).resolve()
        for _ in range(8):
            cur = cur.parent
            candidates_roots.append(cur)
    except Exception:
        pass
    # switchloc package
    try:
        import switchloc
        candidates_roots.append(Path(switchloc.__file__).resolve().parents[1])
        candidates_roots.append(Path(switchloc.__file__).resolve().parents[2])
        candidates_roots.append(Path(switchloc.__file__).resolve().parent)
    except Exception:
        pass
    # argv 0
    try:
        candidates_roots.append(Path(sys.argv[0]).resolve().parent)
        candidates_roots.append(Path(sys.argv[0]).resolve().parent.parent)
    except Exception:
        pass
    # deduplicate
    seen: set[Path] = set()
    uniq_roots: list[Path] = []
    for r in candidates_roots:
        try:
            rp = r.resolve()
        except Exception:
            rp = r
        if rp not in seen:
            seen.add(rp)
            uniq_roots.append(r)
    extra_subdirs = ["", "data", "build_assets", "assets", "templates", "resources", "_internal", "report_templates"]
    out: dict[str, Path] = {}
    # 1) Direct and normalized listing
    for name in (TEMPLATE_RECL, TEMPLATE_SEC, TEMPLATE_SECT):
        norm_exp = _norm_name(name)
        found: Path | None = None
        for root in uniq_roots:
            for sub in extra_subdirs:
                base = root / sub if sub else root
                try:
                    if not base.is_dir():
                        continue
                    p = base / name
                    if p.is_file():
                        found = p
                        break
                    # normalized listing
                    try:
                        for entry in base.iterdir():
                            if entry.is_file() and entry.suffix.lower() == ".docx":
                                norm_entry = _norm_name(entry.name)
                                if norm_entry == norm_exp:
                                    found = entry
                                    break
                                for sub_key, target in substrings.items():
                                    if sub_key in norm_entry and target == name:
                                        found = entry
                                        break
                            if found:
                                break
                    except Exception:
                        pass
                except Exception:
                    continue
            if found:
                break
        if found:
            out[name] = found
    # 2) Recursive rglob
    for name in (TEMPLATE_RECL, TEMPLATE_SEC, TEMPLATE_SECT):
        if name in out:
            continue
        norm_exp = _norm_name(name)
        for root in uniq_roots:
            try:
                if not root.is_dir():
                    continue
                for cand in root.rglob("*.docx"):
                    try:
                        norm_cand = _norm_name(cand.name)
                        if norm_cand == norm_exp:
                            out[name] = cand
                            break
                        for sub_key, target in substrings.items():
                            if sub_key in norm_cand and target == name:
                                out[name] = cand
                                break
                    except Exception:
                        continue
                    if name in out:
                        break
            except Exception:
                continue
            if name in out:
                break
    # 3) importlib.resources fallback
    for name in (TEMPLATE_RECL, TEMPLATE_SEC, TEMPLATE_SECT):
        if name in out:
            continue
        try:
            import importlib.resources as _ir
            for pkg in ("switchloc", "switchloc.reporting", "switchloc.data", "build_assets"):
                try:
                    files = _ir.files(pkg)  # type: ignore
                    cand = files.joinpath(name)
                    if cand.is_file():
                        try:
                            with _ir.as_file(cand) as _p:
                                if _p.is_file():
                                    out[name] = Path(_p)
                                    break
                        except Exception:
                            pass
                    # rglob via resources
                    try:
                        for res in files.rglob("*.docx"):
                            if _norm_name(res.name) == _norm_name(name):
                                try:
                                    with _ir.as_file(res) as _p2:
                                        out[name] = Path(_p2)
                                        break
                                except Exception:
                                    continue
                    except Exception:
                        pass
                except Exception:
                    continue
                if name in out:
                    break
        except Exception:
            pass
    # final direct check
    for name in (TEMPLATE_RECL, TEMPLATE_SEC, TEMPLATE_SECT):
        if name not in out:
            try:
                p = Path(name)
                if p.is_file():
                    out[name] = p.resolve()
            except Exception:
                pass
    # Fallback: if dedicated sectionalizer template not found but disconnector exists, alias it (they share template historically)
    if TEMPLATE_SECT not in out and TEMPLATE_SEC in out:
        out[TEMPLATE_SECT] = out[TEMPLATE_SEC]
    return out


def get_template_vars(parent, study_model=None, selected_template: str | None = None,
                      defaults: dict[str, str] | None = None):
    """Show dialog to edit template variables.

    Returns ``(template_path, vars_dict, extra_images)`` or ``None`` if cancelled.
    """
    defaults = dict(defaults or {})
    templates = _find_templates()
    # Auto-fill defaults from model if study_model provided
    if study_model is not None:
        try:
            from ...reporting.docx_template import _auto_fill_vars_from_model
            auto = {}
            _auto_fill_vars_from_model(auto, study_model)
            for k, v in auto.items():
                defaults.setdefault(k, str(v))
        except Exception:
            pass

    # --- main feeder picker (requirement 12): if multi-feeder, ask user to choose the main {نام فیدر} ---
    # We pre-collect feeder list from study_model (topo.traces or selected_feeders)
    _feeder_choices: list[str] = []
    try:
        # A scoped feeder study should default to (and offer) its own feeders,
        # not the first feeder in the full network topology.
        if defaults.get("selected_feeders"):
            _feeder_choices = [str(x) for x in defaults.get("selected_feeders", [])]
        if not _feeder_choices and study_model is not None and getattr(study_model, "topo", None) is not None:
            _feeder_choices = [str(x.feeder_key) for x in (getattr(study_model.topo, "traces", []) or []) if getattr(x, "feeder_key", None)]
    except Exception:
        pass
    _feeder_choices = [f for f in _feeder_choices if f and f.strip()]
    # deduplicate preserving order
    _seen = set()
    _uniq_feeders: list[str] = []
    for f in _feeder_choices:
        if f not in _seen:
            _seen.add(f)
            _uniq_feeders.append(f)
    _feeder_choices = _uniq_feeders
    # Current main feeder (already in defaults or first)
    _current_main = str(defaults.get("__main_feeder_key") or "").strip()
    if not _current_main and _feeder_choices:
        _current_main = _feeder_choices[0]

    dlg = QDialog(parent)
    dlg.setWindowTitle("اطلاعات متغیر گزارش — تکمیل دفترچه")
    dlg.resize(620, 700)
    lay = QVBoxLayout(dlg)

    # Template choice
    tmpl_group = QGroupBox("انتخاب تمپلیت")
    tg_lay = QHBoxLayout(tmpl_group)
    rb_auto = QRadioButton("خودکار")
    rb_recl = QRadioButton("ریکلووزر")
    rb_sec = QRadioButton("سکسیونر")
    # enable only where file exists
    has_recl = TEMPLATE_RECL in templates
    has_sec = TEMPLATE_SEC in templates
    has_sect = TEMPLATE_SECT in templates
    # sectionalizer shares disconnector template if dedicated not present (alias added in _find_templates)
    # So has_sec counts for sectionalizer; keep both enabled separately for UI clarity
    # If only has_sect alias, then has_sec is True anyway
    rb_recl.setEnabled(has_recl)
    rb_sec.setEnabled(has_sec or has_sect)
    # helper: robust switch_type detection from StudyModel
    def _sw_type_from_model(m):
        if m is None:
            return ""
        try:
            eens = getattr(m, "eens_study", None) or {}
            if not isinstance(eens, dict):
                return ""
            # candidates: top-level eens, eens["study"], settings, engine, feeders
            candidates = []
            # 1) eens itself and eens["study"]
            for d in (eens, eens.get("study") if isinstance(eens.get("study"), dict) else None):
                if isinstance(d, dict):
                    candidates.append(d)
                    # nested settings
                    st = d.get("settings")
                    if isinstance(st, dict):
                        candidates.append(st)
                        # engine inside settings
                        eng = st.get("engine")
                        if isinstance(eng, dict):
                            candidates.append(eng)
                        # also settings may have switch_type directly
            # 2) also explicitly check study.settings.engine
            try:
                sd = eens.get("study", {}) if isinstance(eens.get("study"), dict) else {}
                st2 = sd.get("settings", {}) if isinstance(sd, dict) else {}
                if isinstance(st2, dict):
                    candidates.append(st2)
                    eng2 = st2.get("engine")
                    if isinstance(eng2, dict):
                        candidates.append(eng2)
            except Exception:
                pass
            # 3) check feeders[0].switch_type in study
            try:
                sd2 = eens.get("study", {}) if isinstance(eens.get("study"), dict) else eens
                if isinstance(sd2, dict):
                    for f in (sd2.get("feeders") or []):
                        if isinstance(f, dict) and f.get("switch_type"):
                            candidates.append(f)
            except Exception:
                pass
            for d in candidates:
                if not isinstance(d, dict):
                    continue
                v = d.get("switch_type")
                if isinstance(v, str) and v.strip().lower() in ("recloser", "sectionalizer", "disconnector"):
                    return v.strip().lower()
                # also check switchType camel?
                v = d.get("switchType")
                if isinstance(v, str) and v.strip().lower() in ("recloser", "sectionalizer", "disconnector"):
                    return v.strip().lower()
        except Exception:
            pass
        return ""
    def _has_eens(m):
        try:
            return bool(m and getattr(m, "has_eens_study", False))
        except Exception:
            try:
                eens = getattr(m, "eens_study", None) or {}
                if not isinstance(eens, dict):
                    return False
                st = eens.get("study") if isinstance(eens, dict) else None
                return bool(st and (st.get("feeders") or st.get("settings")))
            except Exception:
                return False

    if not has_recl and not has_sec and not has_sect:
        resp = QMessageBox.question(
            parent, "تمپلیت یافت نشد",
            "فایل‌های تمپلیت در ریشه پروژه یافت نشدند:\n"
            f"{TEMPLATE_RECL}\n{TEMPLATE_SEC}\n\n"
            "آیا می‌خواهید فایل تمپلیت را دستی انتخاب کنید؟\n"
            "در صورت انتخاب «No»، گزارش عمومی (بدون تمپلیت) ساخته می‌شود.\n"
            "«Cancel» انصراف کامل گزارش‌گیری است.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
        )
        if resp == QMessageBox.StandardButton.Cancel:
            return None
        if resp == QMessageBox.StandardButton.Yes:
            path, _ = QFileDialog.getOpenFileName(
                parent, "انتخاب فایل تمپلیت Word", str(Path.cwd()),
                "Word (*.docx);;All (*.*)")
            if path and Path(path).is_file():
                low = Path(path).name.lower()
                if "سکسیونر" in low or "سکشنالایزر" in low or "sectionalizer" in low or "disconnector" in low or low == TEMPLATE_SEC.lower():
                    templates[TEMPLATE_SEC] = Path(path)
                    has_sec = True
                elif "ریکلووزر" in low or "recloser" in low or low == TEMPLATE_RECL.lower():
                    templates[TEMPLATE_RECL] = Path(path)
                    has_recl = True
                else:
                    templates[TEMPLATE_RECL] = Path(path)
                    has_recl = True
            else:
                return (None, {}, {})
        else:  # No -> generic report
            return (None, {}, {})
        rb_recl.setChecked(True)
    elif selected_template == "sectionalizer" and (has_sec or has_sect):
        rb_sec.setChecked(True)
    elif selected_template == "disconnector" and has_sec:
        rb_sec.setChecked(True)
    elif selected_template == "recloser" and has_recl:
        rb_recl.setChecked(True)
    else:
        # auto: choose template based on actual switch_type of EENS study, not just existence
        try:
            sw_type = _sw_type_from_model(study_model)
            is_eens = _has_eens(study_model)
        except Exception:
            sw_type = ""
            is_eens = False
        if sw_type == "recloser" and has_recl:
            rb_recl.setChecked(True)
        elif sw_type in ("sectionalizer", "disconnector") and (has_sec or has_sect):
            rb_sec.setChecked(True)
        elif is_eens and (has_sec or has_sect):
            # fallback for old payloads without switch_type -> sectionalizer/disconnector template
            rb_sec.setChecked(True)
        elif has_recl:
            rb_recl.setChecked(True)
        elif has_sec or has_sect:
            rb_sec.setChecked(True)
        else:
            rb_auto.setChecked(True)
            rb_auto.setEnabled(False)
        rb_auto.setChecked(False)  # prefer concrete
        if not rb_recl.isChecked() and not rb_sec.isChecked():
            rb_auto.setChecked(True)
    tg_lay.addWidget(rb_auto)
    tg_lay.addWidget(rb_recl)
    tg_lay.addWidget(rb_sec)
    tg_lay.addStretch(1)
    lay.addWidget(tmpl_group)

    # Main feeder picker — for technical lookup (English key), separate from display name (Persian)
    # Display name (نمایش) is from QLineEdit "نام فیدر" (Persian typed by user); lookup key is from this combo.
    feeder_combo: QComboBox | None = None
    if len(_feeder_choices) > 1:
        fg = QGroupBox("فیدر اصلی برای پارامترهای فنی — انتخاب کلید فنی (انگلیسی)؛ نام نمایشی از فیلد «نام فیدر» برداشته می‌شود")
        fl = QHBoxLayout(fg)
        feeder_combo = QComboBox()
        for fk in _feeder_choices:
            feeder_combo.addItem(fk)
        if _current_main in _feeder_choices:
            feeder_combo.setCurrentText(_current_main)
        feeder_combo.setMinimumWidth(320)
        fl.addWidget(QLabel("فیدر مرجع فنی :"))
        fl.addWidget(feeder_combo, 1)
        lay.addWidget(fg)
        feeder_combo.setToolTip("این انتخاب فقط برای استخراج پارامترهای فنی (جریان، EENS، طول، λ، r) استفاده می‌شود؛ نام نمایشی در دفترچه از فیلد «نام فیدر» (فارسی) برداشته می‌شود.")
    elif _feeder_choices:
        # single feeder — still need lookup key but no picker UI
        feeder_combo = QComboBox()
        for fk in _feeder_choices:
            feeder_combo.addItem(fk)
        feeder_combo.setCurrentText(_feeder_choices[0])
        # keep hidden; no widget added
        pass

    # Resolve current template path for preview variables — switch_type-aware for Auto
    def _current_template_path():
        if rb_recl.isChecked() and has_recl:
            return templates[TEMPLATE_RECL]
        if rb_sec.isChecked() and (has_sec or has_sect):
            # prefer dedicated sectionalizer if exists else disconnector
            if has_sect and TEMPLATE_SECT in templates:
                # if model says disconnector, use disconnector file; else use sectionalizer
                sw = _sw_type_from_model(study_model)
                if sw == "disconnector" and has_sec:
                    return templates[TEMPLATE_SEC]
                return templates[TEMPLATE_SECT]
            if has_sec:
                return templates[TEMPLATE_SEC]
            if has_sect:
                return templates[TEMPLATE_SECT]
        if rb_auto.isChecked():
            sw = _sw_type_from_model(study_model)
            is_eens = _has_eens(study_model)
            if sw == "recloser" and has_recl:
                return templates[TEMPLATE_RECL]
            if sw in ("sectionalizer", "disconnector") and (has_sec or has_sect):
                if has_sect and TEMPLATE_SECT in templates and sw == "sectionalizer":
                    return templates[TEMPLATE_SECT]
                return templates.get(TEMPLATE_SEC) or templates.get(TEMPLATE_SECT)
            if is_eens and (has_sec or has_sect):
                if has_sect:
                    return templates[TEMPLATE_SECT]
                return templates[TEMPLATE_SEC]
            if has_recl:
                return templates[TEMPLATE_RECL]
            if has_sec:
                return templates[TEMPLATE_SEC]
            if has_sect:
                return templates[TEMPLATE_SECT]
        if has_recl:
            return templates[TEMPLATE_RECL]
        if has_sec:
            return templates[TEMPLATE_SEC]
        if has_sect:
            return templates[TEMPLATE_SECT]
        return None

    # Variables form inside scroll
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    form_host = QWidget()
    form_lay = QFormLayout(form_host)
    form_lay.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    form_lay.setFormAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
    scroll.setWidget(form_host)
    lay.addWidget(scroll, 1)

    edits: dict[str, QLineEdit] = {}
    extra_edits: dict[str, QLineEdit] = {}
    extra_buttons: dict[str, QPushButton] = {}

    # Each template owns its own edits. In particular, recloser values must
    # survive a switch to sectionalizer and back without alias-based mixing.
    def _template_cache_key() -> str:
        if rb_recl.isChecked():
            return "recloser"
        sw = _sw_type_from_model(study_model)
        if rb_sec.isChecked():
            if selected_template in ("sectionalizer", "disconnector"):
                return selected_template
            return "disconnector" if sw == "disconnector" else "sectionalizer"
        if sw == "recloser":
            return "recloser"
        return "disconnector" if sw == "disconnector" else "sectionalizer"

    template_caches: dict[str, dict[str, str]] = {}
    active_cache = dict(defaults)
    active_cache_key = _template_cache_key()
    template_caches[active_cache_key] = active_cache

    # Pre-collect variables for current template
    cur_path = _current_template_path()
    var_names: list[str] = []
    if cur_path and cur_path.is_file():
        try:
            var_names = extract_variables(str(cur_path))
        except Exception as e:
            var_names = []
    # Fallback if auto template unknown
    if not var_names:
        var_names = sorted(set(defaults.keys()))

    # Values are looked up by the exact placeholder name. Cross-template
    # canonical/synonym fallback used to make unrelated template fields share
    # a single value (and overwrite one another on round trips).
    def _value_for_key(key: str) -> str:
        if key in active_cache:
            return str(active_cache[key])
        return str(defaults.get(key, ""))

    # Build form rows
    # Use Persian labels directly as var names
    for key in var_names:
        le = QLineEdit()
        le.setText(_value_for_key(key))
        le.setPlaceholderText(f"مقدار {key}")
        edits[key] = le
        lbl = QLabel(key + " :")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        form_lay.addRow(lbl, le)
    # Seed this template's own cache from the values initially shown.
    for k, le in edits.items():
        active_cache.setdefault(k, le.text())

    # Extra images pickers
    img_group = QGroupBox("تصاویر اختیاری — منحنی‌های حفاظتی (TCC)")
    img_lay = QFormLayout(img_group)
    for placeholder in ("منحنی توسط کاربر بارگذاری می شود (فاز)", "منحنی توسط کاربر بارگذاری می شود (زمین)",
                        "تصویر توسط کاربر بارگذاری می شود (ایرانسل)", "تصویر توسط کاربر بارگذاری می شود (همراه اول)"):
        le = QLineEdit()
        le.setPlaceholderText("مسیر تصویر (اختیاری)")
        le.setReadOnly(True)
        btn = QPushButton("انتخاب…")
        btn.setMinimumWidth(80)
        h = QHBoxLayout()
        h.addWidget(le, 1)
        h.addWidget(btn)
        w = QWidget()
        w.setLayout(h)
        h.setContentsMargins(0, 0, 0, 0)
        img_lay.addRow(QLabel(placeholder + " :"), w)
        extra_edits[placeholder] = le
        extra_buttons[placeholder] = btn
        # connect picker
        def _make_picker(target_le: QLineEdit):
            def pick():
                path, _ = QFileDialog.getOpenFileName(dlg, "انتخاب تصویر", "",
                                                      "Images (*.png *.jpg *.jpeg *.bmp *.tif);;All (*)")
                if path:
                    target_le.setText(path)
            return pick
        btn.clicked.connect(_make_picker(le))

    lay.addWidget(img_group)

    # Buttons
    bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    bbox.accepted.connect(dlg.accept)
    bbox.rejected.connect(dlg.reject)
    lay.addWidget(bbox)

    # When template choice changes, save/restore a separate variable set for
    # each template family. This also works when the templates have identical
    # placeholder names.
    def _rebuild_vars():
        nonlocal var_names, active_cache, active_cache_key
        new_path = _current_template_path()
        if not new_path or not new_path.is_file():
            return
        try:
            new_vars = extract_variables(str(new_path))
        except Exception:
            return
        for k, le in edits.items():
            active_cache[k] = le.text()
        next_key = _template_cache_key()
        if next_key != active_cache_key:
            active_cache_key = next_key
            active_cache = template_caches.setdefault(next_key, dict(defaults))
        while form_lay.rowCount() > 0:
            form_lay.removeRow(0)
        edits.clear()
        var_names = new_vars
        for key in var_names:
            le = QLineEdit()
            le.setText(_value_for_key(key))
            le.setPlaceholderText(f"مقدار {key}")
            edits[key] = le
            lbl = QLabel(key + " :")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            form_lay.addRow(lbl, le)
            active_cache.setdefault(key, le.text())

    rb_recl.toggled.connect(lambda checked: _rebuild_vars() if checked else None)
    rb_sec.toggled.connect(lambda checked: _rebuild_vars() if checked else None)
    rb_auto.toggled.connect(lambda checked: _rebuild_vars() if checked else None)

    # Feeder-specific values must follow the selected technical lookup key.
    # These are generated values (not user-entered display labels), so a new
    # feeder selection deliberately replaces the previous feeder's numbers.
    from ...reporting.template_values import (
        FEEDER_VALUE_KEYS, refresh_feeder_template_caches,
    )

    def _refresh_feeder_values(*_args):
        if study_model is None or feeder_combo is None:
            return
        feeder_key = feeder_combo.currentText().strip()
        if not feeder_key:
            return
        try:
            from ...reporting.docx_template import _auto_fill_vars_from_model
            generated = {"__main_feeder_key": feeder_key}
            _auto_fill_vars_from_model(generated, study_model)
            refreshed = refresh_feeder_template_caches(
                generated, defaults, template_caches, FEEDER_VALUE_KEYS)
            for key, value in refreshed.items():
                if key in edits:
                    edits[key].setText(value)
        except Exception:
            pass

    if feeder_combo is not None:
        feeder_combo.currentTextChanged.connect(_refresh_feeder_values)
        _refresh_feeder_values()

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    final_path = _current_template_path()
    if not final_path:
        QMessageBox.warning(parent, "خطا", "تمپلیت انتخاب نشده است.")
        return None

    vars_dict = {k: e.text().strip() for k, e in edits.items()}
    vars_dict = {k: v for k, v in vars_dict.items() if v != ""}
    # Only variables for the selected template are returned.
    # Store technical lookup key separately (English), keep display name as typed (Persian)
    if feeder_combo is not None:
        sel = feeder_combo.currentText().strip() if feeder_combo.currentText() else ""
        if sel:
            vars_dict["__main_feeder_key"] = sel
            vars_dict["_main_feeder_key"] = sel

    extra_images: dict[str, str] = {}
    picked = []
    for placeholder, le in extra_edits.items():
        p = le.text().strip()
        if p:
            picked.append(p)
    if picked:
        generic_keys = ["منحنی توسط کاربر بارگذاری می شود", "تصویر توسط کاربر بارگذاری می شود"]
        for idx, path in enumerate(picked):
            if idx == 0:
                extra_images["منحنی توسط کاربر بارگذاری می شود"] = path
                extra_images["تصویر توسط کاربر بارگذاری می شود"] = path
            elif idx == 1:
                extra_images["منحنی توسط کاربر بارگذاری می شود#2"] = path
                extra_images["تصویر توسط کاربر بارگذاری می شود#2"] = path
            else:
                extra_images[f"extra_{idx}"] = path

    return (str(final_path), vars_dict, extra_images)
