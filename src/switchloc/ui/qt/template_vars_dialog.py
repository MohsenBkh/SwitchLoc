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


def _find_templates() -> dict[str, Path]:
    import sys
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
                candidates_roots.append(Path(meipass).resolve())
                # _MEIPASS parent may contain templates when datas copied to root
                try:
                    candidates_roots.append(Path(meipass).resolve().parent)
                except Exception:
                    pass
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
    extra_subdirs = ["", "data", "build_assets", "assets", "templates", "resources"]
    out: dict[str, Path] = {}
    for name in (TEMPLATE_RECL, TEMPLATE_SEC):
        found: Path | None = None
        for root in uniq_roots:
            for sub in extra_subdirs:
                base = root / sub if sub else root
                p = base / name
                if p.is_file():
                    found = p
                    break
            if found:
                break
        if found:
            out[name] = found
    # final direct check and rglob fallback
    for name in (TEMPLATE_RECL, TEMPLATE_SEC):
        if name not in out:
            p = Path(name)
            if p.is_file():
                out[name] = p.resolve()
            else:
                try:
                    for cand in Path.cwd().rglob(name):
                        if cand.is_file():
                            out[name] = cand
                            break
                except Exception:
                    pass
                if name not in out:
                    # also search via importlib.resources
                    try:
                        import importlib.resources as _ir
                        # try package data
                        for pkg in ("switchloc", "switchloc.data", "build_assets"):
                            try:
                                if _ir.files(pkg).joinpath(name).is_file():  # type: ignore[attr-defined]
                                    # extract to temp is complex; skip
                                    pass
                            except Exception:
                                pass
                    except Exception:
                        pass
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
        if study_model is not None and getattr(study_model, "topo", None) is not None:
            _feeder_choices = [str(x.feeder_key) for x in (getattr(study_model.topo, "traces", []) or []) if getattr(x, "feeder_key", None)]
        if not _feeder_choices and defaults.get("selected_feeders"):
            _feeder_choices = [str(x) for x in defaults.get("selected_feeders", [])]
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
    _current_main = str(defaults.get("نام فیدر") or "").strip() if defaults.get("نام فیدر") else ""
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
    rb_recl.setEnabled(has_recl)
    rb_sec.setEnabled(has_sec)
    if not has_recl and not has_sec:
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
                if "سکسیونر" in low or "sectionalizer" in low or low == TEMPLATE_SEC.lower():
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
    elif selected_template == "sectionalizer" and has_sec:
        rb_sec.setChecked(True)
    else:
        # auto: if study has EENS -> sectionalizer else recloser
        try:
            is_eens = bool(study_model and getattr(study_model, "has_eens_study", False))
        except Exception:
            is_eens = False
        if is_eens and has_sec:
            rb_sec.setChecked(True)
        elif has_recl:
            rb_recl.setChecked(True)
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

    # Main feeder picker — only shown when multi-feeder
    feeder_combo: QComboBox | None = None
    if len(_feeder_choices) > 1:
        fg = QGroupBox("فیدر اصلی برای متغیر {نام فیدر} — پارامترهای گزارش بر اساس همین فیدر پر می‌شود")
        fl = QHBoxLayout(fg)
        feeder_combo = QComboBox()
        for fk in _feeder_choices:
            feeder_combo.addItem(fk)
        # select current
        if _current_main in _feeder_choices:
            feeder_combo.setCurrentText(_current_main)
        feeder_combo.setMinimumWidth(320)
        hint = QLabel("فیدر اصلی را انتخاب کنید — جریان، EENS و مختصات فقط برای این فیدر محاسبه می‌شود.")
        hint.setWordWrap(True)
        fl.addWidget(QLabel("نام فیدر اصلی :"))
        fl.addWidget(feeder_combo, 1)
        # also add hint below? keep compact
        lay.addWidget(fg)
        # tooltip
        feeder_combo.setToolTip("در صورت چندفیدری بودن پروژه، دفترچه فقط برای یک فیدر اصلی تهیه می‌شود — پارامترهای محاسباتی بر همان فیدر اعمال می‌گردد.")
    elif _feeder_choices:
        # single feeder — no picker, show label
        pass

    # Resolve current template path for preview variables
    def _current_template_path():
        if rb_recl.isChecked() and has_recl:
            return templates[TEMPLATE_RECL]
        if rb_sec.isChecked() and has_sec:
            return templates[TEMPLATE_SEC]
        if has_recl:
            return templates[TEMPLATE_RECL]
        if has_sec:
            return templates[TEMPLATE_SEC]
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

    # Build form rows
    # Use Persian labels directly as var names
    for key in var_names:
        le = QLineEdit()
        le.setText(str(defaults.get(key, "")))
        le.setPlaceholderText(f"مقدار {key}")
        # For date/number fields, keep simple
        edits[key] = le
        lbl = QLabel(key + " :")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        form_lay.addRow(lbl, le)

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

    # When template choice changes, rebuild var form? Simple: reload variables on accept
    # But also update on radio toggle
    def _rebuild_vars():
        nonlocal var_names
        new_path = _current_template_path()
        if not new_path or not new_path.is_file():
            return
        try:
            new_vars = extract_variables(str(new_path))
        except Exception:
            return
        if set(new_vars) == set(var_names):
            return
        # Clear form
        while form_lay.rowCount() > 0:
            form_lay.removeRow(0)
        edits.clear()
        var_names = new_vars
        for key in var_names:
            le = QLineEdit()
            le.setText(str(defaults.get(key, "")))
            le.setPlaceholderText(f"مقدار {key}")
            edits[key] = le
            lbl = QLabel(key + " :")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            form_lay.addRow(lbl, le)

    rb_recl.toggled.connect(lambda checked: _rebuild_vars() if checked else None)
    rb_sec.toggled.connect(lambda checked: _rebuild_vars() if checked else None)
    rb_auto.toggled.connect(lambda checked: _rebuild_vars() if checked else None)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    final_path = _current_template_path()
    if not final_path:
        QMessageBox.warning(parent, "خطا", "تمپلیت انتخاب نشده است.")
        return None

    vars_dict = {k: e.text().strip() for k, e in edits.items()}
    vars_dict = {k: v for k, v in vars_dict.items() if v != ""}
    # main feeder override (requirement 12)
    if feeder_combo is not None:
        sel = feeder_combo.currentText().strip() if feeder_combo.currentText() else ""
        if sel:
            vars_dict["نام فیدر"] = sel
    # Ensure dedup synonyms are unified already via _canonical filter in extract_variables,
    # but if dialog returned canonical, we also ensure synonyms are not duplicated separately.
    # _auto_fill will expand, so leaving canonical is fine.

    extra_images: dict[str, str] = {}
    # Map friendly placeholders to actual placeholder texts expected by template engine
    # The engine expects keys like "منحنی توسط کاربر بارگذاری می شود" (single) but we have two
    # We'll map first to that key, second to same with disambiguation via extra_images dict
    # Simpler: if user picked image for either curve, use it for generic placeholder;
    # the second curve will overwrite if needed — we handle sequential placeholders differently.
    # For now, collect any picked images and let engine try to match by order.
    picked = []
    for placeholder, le in extra_edits.items():
        p = le.text().strip()
        if p:
            picked.append(p)
    # Map to generic keys in order of appearance in document:
    # For recloser: two "منحنی توسط کاربر بارگذاری می شود" placeholders (Fig3, Fig4)
    # For sectionalizer: two "تصویر توسط کاربر بارگذاری می شود" (Fig3,4)
    # We'll pass list via extra_images with special keys
    if picked:
        # Use ordered mapping: first picked -> first generic placeholder, etc.
        # Engine will attempt to use extra_images["منحنی توسط کاربر بارگذاری می شود"] etc.
        # For disambiguation, assign by index
        generic_keys = ["منحنی توسط کاربر بارگذاری می شود", "تصویر توسط کاربر بارگذاری می شود"]
        # Assign both curves to same generic but engine will use first; to support two images we need index
        # We'll store extra_images with suffix _1, _2 and engine will be updated to handle
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