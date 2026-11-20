# -*- coding: utf-8 -*-
"""Dialog to collect variable values for template-based report."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QRadioButton, QScrollArea, QVBoxLayout, QWidget,
)

from ...reporting.docx_template import extract_variables

TEMPLATE_RECL = "نمونه دفترچه مطالعات ریکلوزر.docx"
TEMPLATE_SEC = "نمونه دفترچه مطالعات سکسیونر.docx"


def _find_templates() -> dict[str, Path]:
    roots = [Path.cwd(), Path(__file__).resolve().parents[4]]
    # also try import
    try:
        import switchloc
        roots.append(Path(switchloc.__file__).resolve().parents[1])
    except Exception:
        pass
    out: dict[str, Path] = {}
    for name in (TEMPLATE_RECL, TEMPLATE_SEC):
        for r in roots:
            p = r / name
            if p.is_file():
                out[name] = p
                break
        # also direct root
        if name not in out:
            p = Path(name)
            if p.is_file():
                out[name] = p.resolve()
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
        QMessageBox.warning(parent, "تمپلیت یافت نشد",
                            "فایل‌های تمپلیت در ریشه پروژه یافت نشدند:\n"
                            f"{TEMPLATE_RECL}\n{TEMPLATE_SEC}")
        return None
    # default selection
    if selected_template == "recloser" and has_recl:
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
    # prune empty? keep as is; empty will keep original placeholder
    # remove empty entries to fallback to original/template? keep empty as original
    vars_dict = {k: v for k, v in vars_dict.items() if v != ""}

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
