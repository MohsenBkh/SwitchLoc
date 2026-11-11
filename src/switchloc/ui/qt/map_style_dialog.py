# -*- coding: utf-8 -*-
"""Map style dialog — تنظیمات نمایشی نقشه (درخواست کاربر).

Features (per the user's two requests):

  1. the feeder colour table opens pre-filled with the EXACT colours the
     renderer assigns automatically (per-feeder palette — no shared
     default code); every colour/thickness/marker is then editable;
  2. MULTIPLE NAMED STYLES: the dialog keeps a book
     ``{name: MapStyle}`` — «ثبت تغییرات» overwrites the active name,
     «ذخیره با نام جدید…» creates one, «حذف استایل» removes one — and
     the caller persists the book inside the project (project_kv →
     ``map_styles``) so closing/reopening the project restores the
     exact settings.

Discipline: the pure helpers (`feeder_rows`, `collect_style`) are
Qt-free and unit-tested; only `make_map_style_dialog` touches Qt.
"""
from __future__ import annotations

from ..map_style import MARKER_CHOICES, MapStyle


def feeder_rows(style: MapStyle, feeders: list) -> list:
    """(feeder, colour) rows for the colour table — every modelled
    feeder gets a row with the colour the renderer would use (style
    override first, then the automatic per-feeder palette)."""
    pal = style.palette_of(feeders=feeders or [])
    return [[k, pal.get(k, style.unknown_color)]
            for k in sorted(feeders or pal)]


def collect_style(editor: dict) -> MapStyle:
    """Editor state (dict of field→value) → MapStyle (validated)."""
    st = MapStyle()
    st.feeder_colors = {str(k): str(v) for k, v in
                        (editor.get("feeder_colors") or {}).items()}
    for key, val in editor.items():
        if key == "feeder_colors":
            continue
        if hasattr(st, key):
            cur = getattr(st, key)
            try:
                if isinstance(cur, bool):
                    setattr(st, key, str(val).strip().lower()
                            not in ("0", "false", "no", ""))
                else:
                    setattr(st, key, type(cur)(val))
            except (TypeError, ValueError):
                pass
    return st


_COLOR_ATTRS = (
    ("switch_color", "رنگ کلید عمومی"),
    ("fct_color", "رنگ FCT — فیوز کات‌اوت"),
    ("dcs_color", "رنگ DCS — دیسکانکتور"),
    ("cbr_color", "رنگ CBR — دژنکتور"),
    ("rec_color", "رنگ REC — ریکلوزر"),
    ("sec_color", "رنگ SEC — سکشنالایزر"),
    ("unknown_device_color", "رنگ کلید نامشخص"),
    ("no_tie_color", "رنگ open point / NO"),
    ("source_color", "رنگ سورس"),
    ("transformer_color", "رنگ ترانسفورماتور"),
    ("proposed_color", "رنگ کلید پیشنهادی"),
    ("manual_color", "رنگ کلید دستی"),
    ("zone_label_color", "رنگ متن لیبل زون"),
    ("zone_label_background_color", "رنگ زمینه لیبل زون"),
    ("zone_selected_color", "رنگ محدوده زون انتخاب‌شده"),
    # --- لایهٔ خاموشی‌های دارای مختصات (تب جدید) ---
    ("outage_color", "رنگ خاموشی بدون وضعیت"),
    ("outage_confirmed_color", "رنگ خاموشی تأیید مهندسی"),
    ("outage_pending_color", "رنگ خاموشی در انتظار بررسی"),
    ("outage_rejected_color", "رنگ خاموشی رد‌شده"),
    ("outage_label_color", "رنگ متن برچسب خاموشی"),
    ("outage_link_color", "رنگ خط اتصال خاموشی → زون"),
    ("opt_sec_color", "رنگ سکشنالایزر پیشنهادی (EENS)"),
)
_SIZE_ATTRS = (
    ("switch_size", "سایز کلید عمومی", 1.0, 120.0, 1.0),
    ("fct_size", "سایز FCT — فیوز کات‌اوت", 1.0, 120.0, 1.0),
    ("dcs_size", "سایز DCS — دیسکانکتور", 1.0, 120.0, 1.0),
    ("cbr_size", "سایز CBR — دژنکتور", 1.0, 120.0, 1.0),
    ("rec_size", "سایز REC — ریکلوزر", 1.0, 120.0, 1.0),
    ("sec_size", "سایز SEC — سکشنالایزر", 1.0, 120.0, 1.0),
    ("unknown_device_size", "سایز کلید با نوع نامشخص", 1.0, 120.0, 1.0),
    ("no_tie_size", "سایز open point / NO / Tie", 4.0, 160.0, 1.0),
    ("source_size", "سایز سورس (سر فیدر)", 4.0, 300.0, 1.0),
    ("transformer_size", "سایز ترانسفورماتور", 0.5, 60.0, 0.5),
    ("proposed_size", "سایز کلید پیشنهادی (ستاره)", 5.0, 400.0, 1.0),
    ("manual_size", "سایز کلید دستی ارزیابی‌شده", 5.0, 400.0, 1.0),
    ("zone_label_size", "سایز متن برچسب زون", 2.0, 20.0, 0.5),
    ("zone_label_alpha", "شفافیت متن زون", 0.1, 1.0, 0.05),
    ("zone_label_background_alpha", "شفافیت زمینه لیبل", 0.0, 1.0, 0.05),
    ("zone_selected_width", "ضخامت خطوط زون انتخاب‌شده", 1.0, 14.0, 0.5),
    ("zone_selected_alpha", "شفافیت محدوده انتخاب‌شده", 0.1, 1.0, 0.05),
    # --- لایهٔ خاموشی ---
    ("outage_size", "سایز نماد خاموشی", 5.0, 400.0, 1.0),
    ("outage_alpha", "شفافیت نماد خاموشی", 0.1, 1.0, 0.05),
    ("outage_label_size", "سایز متن برچسب خاموشی", 2.0, 20.0, 0.5),
    ("outage_label_alpha", "شفافیت متن خاموشی", 0.1, 1.0, 0.05),
    ("outage_link_width", "ضخامت خط اتصال خاموشی → زون", 0.2, 6.0, 0.1),
    ("outage_link_alpha", "شفافیت خط اتصال خاموشی", 0.1, 1.0, 0.05),
    ("opt_sec_size", "سایز سکشنالایزر پیشنهادی (EENS)", 10.0, 500.0, 5.0),
)
_MARKER_ATTRS = (
    ("switch_marker", "نماد کلید عمومی"),
    ("fct_marker", "نماد FCT — فیوز کات‌اوت"),
    ("dcs_marker", "نماد DCS — دیسکانکتور"),
    ("cbr_marker", "نماد CBR — دژنکتور"),
    ("rec_marker", "نماد REC — ریکلوزر"),
    ("sec_marker", "نماد SEC — سکشنالایزر"),
    ("unknown_device_marker", "نماد کلید نامشخص"),
    ("no_tie_marker", "نماد open point / NO"),
    ("source_marker", "نماد سورس"),
    ("transformer_marker", "نماد ترانسفورماتور"),
    ("proposed_marker", "نماد کلید پیشنهادی"),
    ("manual_marker", "نماد کلید دستی"),
    ("outage_marker", "نماد خاموشی"),
    ("opt_sec_marker", "نماد سکشنالایزر پیشنهادی (EENS)"),
)
_MARKER_FA = {"o": "دایره (o)", "s": "مربع (s)", "D": "لوزی (D)",
              "d": "لوزی باریک (d)", "^": "مثلث بالا (^)",
              "v": "مثلث پایین (v)", "<": "مثلث چپ (<)",
              ">": "مثلث راست (>)", "P": "به‌علاوه پر (P)",
              "X": "ضربدر پر (X)", "*": "ستاره (*)", "p": "پنج‌ضلعی (p)",
              "h": "شش‌ضلعی (h)", "H": "شش‌ضلعی۲ (H)",
              "8": "هشت‌ضلعی (8)", ".": "نقطه (.)"}


def fit_dialog_to_screen(dlg, *, margin: int = 48,
                         min_w: int = 560, min_h: int = 420):  # pragma: no cover
    """پنجره را داخل صفحهٔ نمایش جا می‌دهد و **وسط صفحه** می‌گذارد.

    درخواست کاربر: «قسمت پایین پنجره (دکمه OK) خارج از دید است، پنجره را
    نسبت به صفحه سنتر کن». بنابراین اندازه به ناحیهٔ قابل‌استفادهٔ صفحه
    محدود می‌شود (تا نوار عنوان و دکمه‌ها همیشه دیده شوند) و سپس مرکز
    همان ناحیه قرار می‌گیرد — نه مرکز پنجرهٔ والد.
    """
    from PySide6.QtCore import QPoint
    try:
        screen = dlg.screen()
        avail = screen.availableGeometry() if screen is not None else None
    except Exception:                                  # noqa: BLE001
        avail = None
    if avail is None or avail.isEmpty():
        return
    w = max(min_w, min(dlg.width(), avail.width() - margin))
    h = max(min_h, min(dlg.height(), avail.height() - margin))
    dlg.resize(min(w, avail.width()), min(h, avail.height()))
    dlg.move(QPoint(avail.center().x() - dlg.width() // 2,
                    avail.center().y() - dlg.height() // 2))


def make_map_style_dialog(parent, feeders: list, current: MapStyle,
                          book: dict | None = None,
                          active_name: str = ""):  # pragma: no cover
    """Return the dialog; caller does exec() then reads
    ``dlg.result_style() / dlg.result_book() / dlg.result_active()``."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox,
                                   QDialog, QDialogButtonBox,
                                   QDoubleSpinBox, QFormLayout,
                                   QGroupBox, QHBoxLayout, QHeaderView,
                                   QInputDialog, QSpinBox,
                                   QLabel, QMessageBox, QPushButton,
                                   QScrollArea, QSplitter, QTableWidget, QTableWidgetItem,
                                   QVBoxLayout, QWidget, QTabWidget, QGridLayout)

    dlg = QDialog(parent)
    dlg.setWindowTitle("SwitchLoc — Map style (تنظیمات نمایشی نقشه)")
    dlg.setMinimumSize(680, 470)
    dlg.resize(896, 656)
    dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint |
                       Qt.WindowType.WindowMinimizeButtonHint)

    work = MapStyle.from_dict(current.as_dict())
    names_book: dict[str, MapStyle] = {
        str(k): MapStyle.from_dict(v)
        for k, v in (book or {}).items() if isinstance(v, dict)}
    active = {"name": active_name if active_name in names_book else
              (next(iter(sorted(names_book)), ""))}

    lay = QVBoxLayout(dlg)

    # -- style book row -----------------------------------------------------
    top = QHBoxLayout()
    top.addWidget(QLabel("استایل:"))
    cmb = QComboBox()
    top.addWidget(cmb, 1)
    btn_save = QPushButton("ثبت تغییرات در این استایل")
    btn_save_as = QPushButton("ذخیره با نام جدید…")
    btn_del = QPushButton("حذف استایل")
    btn_reset = QPushButton("بازگشت به پیش‌فرض")
    for b in (btn_save, btn_save_as, btn_del, btn_reset):
        top.addWidget(b)
    lay.addLayout(top)

    tip = QLabel(
        "«ثبت تغییرات» همان استایل فعال را به‌روز می‌کند؛ «ذخیره با نام "
        "جدید» یک استایل مستقل می‌سازد. استایل‌ها داخل فایل پروژه ذخیره "
        "می‌شوند و پس از بستن/بازکردن پروژه همان تنظیمات برمی‌گردد.")
    tip.setWordWrap(True)
    lay.addWidget(tip)

    tabs = QTabWidget()
    tabs.setDocumentMode(True)
    lay.addWidget(tabs, 1)

    # (a) feeder colours + widths ------------------------------------------
    left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(2, 2, 2, 2)
    lv.addWidget(QLabel("<b>رنگ و ضخامت فیدرها</b>"))
    tbl = QTableWidget(0, 3)
    tbl.setHorizontalHeaderLabels(["Feeder", "نمایش", "Color"])
    tbl.horizontalHeader().setStretchLastSection(True)
    tbl.verticalHeader().setVisible(False)
    tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    lv.addWidget(tbl, 1)
    feeder_buttons = QHBoxLayout()
    for label, checked in (("انتخاب همهٔ فیدرها", True), ("حذف انتخاب همه", False)):
        button = QPushButton(label)
        def set_all(_checked=False, checked=checked):
            for row in range(tbl.rowCount()):
                item = tbl.item(row, 1)
                if item is not None:
                    item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        button.clicked.connect(set_all)
        feeder_buttons.addWidget(button)
    lv.addLayout(feeder_buttons)
    fw = QFormLayout()
    sp_w = QDoubleSpinBox(); sp_w.setRange(0.1, 8.0); sp_w.setSingleStep(0.1)
    sp_wf = QDoubleSpinBox(); sp_wf.setRange(0.1, 8.0); sp_wf.setSingleStep(0.1)
    fw.addRow("ضخامت خط فیدر (کل شبکه):", sp_w)
    fw.addRow("ضخامت خط در نمای تک‌فیدر:", sp_wf)
    btn_unk = QPushButton(); btn_unk.setFixedWidth(84)
    unk_swatch = QLabel(); unk_swatch.setFixedWidth(46)
    unk_swatch.setAlignment(Qt.AlignmentFlag.AlignCenter)
    unk_hold = QWidget()
    unk_lay = QHBoxLayout(unk_hold)
    unk_lay.setContentsMargins(0, 0, 0, 0)
    unk_lay.addWidget(btn_unk)
    unk_lay.addWidget(unk_swatch)
    fw.addRow("رنگ خطوط بدون برچسب:", unk_hold)
    lv.addLayout(fw)
    tabs.addTab(left, "فیدرها")

    # (b) devices -----------------------------------------------------------
    right = QWidget(); rv = QVBoxLayout(right); rv.setContentsMargins(2, 2, 2, 2)
    rv.addWidget(QLabel("<b>نماد کلیدها، سورس، open point و …</b>"))
    grp = QFormLayout()
    zone_grp = QFormLayout()
    outage_grp = QFormLayout()
    spins: dict[str, QDoubleSpinBox] = {}
    marks: dict[str, QComboBox] = {}
    cols: dict[str, QPushButton] = {}
    swatches: dict[str, QLabel] = {}

    def _add_color(key: str, label: str, form) -> None:
        b = QPushButton(); b.setFixedWidth(84)
        sw = QLabel(); sw.setFixedWidth(46)
        sw.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row = QHBoxLayout(); row.addWidget(b); row.addWidget(sw)
        hold = QWidget(); hold.setLayout(row)
        form.addRow(label, hold)
        cols[key] = b
        swatches[key] = sw

    def _add_size(key: str, label: str, lo, hi, step, form) -> None:
        sp = QDoubleSpinBox(); sp.setRange(lo, hi); sp.setSingleStep(step)
        form.addRow(label, sp)
        spins[key] = sp

    def _add_marker(key: str, label: str, form) -> None:
        cb = QComboBox()
        for m in MARKER_CHOICES:
            cb.addItem(_MARKER_FA.get(m, m), m)
        form.addRow(label, cb)
        marks[key] = cb

    zone_size_keys = {"zone_label_size", "zone_label_alpha", "zone_label_background_alpha", "zone_selected_width", "zone_selected_alpha"}
    zone_color_keys = {"zone_label_color", "zone_label_background_color", "zone_selected_color"}

    def _form_for(key: str, default):
        if key.startswith("outage_"):
            return outage_grp
        if key in zone_size_keys or key in zone_color_keys:
            return zone_grp
        return default

    for key, label, lo, hi, step in _SIZE_ATTRS:
        _add_size(key, label, lo, hi, step, _form_for(key, grp))
    for key, label in _MARKER_ATTRS:
        _add_marker(key, label, _form_for(key, grp))
    for key, label in _COLOR_ATTRS:
        _add_color(key, label, _form_for(key, grp))
    chk_fuse = QCheckBox("نمایش فیوز کات‌اوت‌ها (FCT) روی نقشه "
                         "— پیش‌فرض خاموش")
    chk_fuse.setToolTip(
        "درخواست کاربر: فیوزها به‌صورت پیش‌فرض نمایش داده نمی‌شوند؛ با "
        "تیک‌زدن این گزینه (یا تیک گروه FCT در فهرست کلیدهای تب نقشه) "
        "روشن می‌شوند.")
    grp_rows = QVBoxLayout(); grp_rows.addWidget(chk_fuse); grp_rows.addLayout(grp)
    hold1 = QWidget(); hold1.setLayout(grp_rows)
    controls_scroll = QScrollArea()
    controls_scroll.setWidgetResizable(True)
    controls_scroll.setWidget(hold1)
    rv.addWidget(controls_scroll, 1)
    tabs.addTab(right, "تجهیزات شبکه")

    zone_page = QWidget()
    zv = QVBoxLayout(zone_page)
    zone_form_widget = QWidget(); zone_form_widget.setLayout(zone_grp)
    zone_scroll = QScrollArea(); zone_scroll.setWidgetResizable(True)
    zone_scroll.setWidget(zone_form_widget)
    zv.addWidget(zone_scroll, 1)
    chk_legend = QCheckBox("نمایش لجند روی نقشه")
    chk_zones = QCheckBox("نمایش لیبل زون‌ها روی نقشه")
    zv.addWidget(chk_legend)
    zv.addWidget(chk_zones)
    tabs.addTab(zone_page, "زون‌ها و لجند")

    # (d) لایهٔ خاموشی‌های دارای مختصات — تب مستقل، دو باکس کنار هم
    #     (درخواست کاربر v1.15: چپ = نمادها و متن، راست = چیدمان برچسب و
    #      توزیع رنگی)
    outage_page = QWidget()
    ov = QVBoxLayout(outage_page)
    ov.addWidget(QLabel(
        "<b>نمایش خاموشی‌های دارای مختصات</b> — سمت چپ نمادها، رنگ‌ها و متن "
        "برچسب؛ سمت راست چیدمان برچسب‌ها و توزیع رنگی مسیر فیدرها. "
        "روشن/خاموش کردن تک‌تک رخدادها از پنل «لایهٔ خاموشی‌ها» در تب نقشه "
        "انجام می‌شود."))
    outage_split = QSplitter(Qt.Orientation.Horizontal)

    # --- باکس چپ: نمادها و متن خاموشی ---
    sym_box = QGroupBox("نمادهای خاموشی، رنگ وضعیت و متن برچسب")
    sym_lay = QVBoxLayout(sym_box)
    outage_form_widget = QWidget()
    outage_form_widget.setLayout(outage_grp)
    outage_scroll = QScrollArea()
    outage_scroll.setWidgetResizable(True)
    outage_scroll.setWidget(outage_form_widget)
    sym_lay.addWidget(outage_scroll, 1)
    chk_outages = QCheckBox("نمایش لایهٔ خاموشی‌ها روی نقشه")
    chk_outage_labels = QCheckBox("نمایش برچسب «نام مکان (تعداد خطا)» روی نقشه")
    chk_outage_links = QCheckBox("خط اتصال خاموشی به مرکز زون متأثر")
    for cb in (chk_outages, chk_outage_labels, chk_outage_links):
        sym_lay.addWidget(cb)
    outage_split.addWidget(sym_box)

    # --- باکس راست: چیدمان برچسب‌ها + توزیع رنگی ---
    layout_box = QGroupBox("چیدمان برچسب‌ها و توزیع رنگی مسیر")
    layout_lay = QVBoxLayout(layout_box)
    outage_split.addWidget(layout_box)
    outage_split.setStretchFactor(0, 3)
    outage_split.setStretchFactor(1, 4)
    ov.addWidget(outage_split, 1)

    # --- چیدمان برچسب‌ها: نزدیک نقطه + خط راهنما (اصلاح پراکندگی) --------
    layout_inner = QWidget()
    layout_inner_lay = QVBoxLayout(layout_inner)
    layout_inner_lay.setContentsMargins(0, 0, 0, 0)
    layout_scroll = QScrollArea()
    layout_scroll.setWidgetResizable(True)
    layout_scroll.setWidget(layout_inner)
    layout_lay.addWidget(layout_scroll, 1)

    lbl_box = QGroupBox("چیدمان برچسب‌ها (نزدیک نقطه، با خط راهنما)")
    lbl_form = QFormLayout(lbl_box)
    sp_lbl_levels = QSpinBox()
    sp_lbl_levels.setRange(0, 8)
    sp_lbl_levels.setValue(3)
    sp_lbl_levels.setToolTip(
        "حداکثر تعداد پله‌ای که برچسب برای فرار از هم‌پوشانی جابه‌جا می‌شود؛"
        " عدد بزرگ = پراکندگی زیاد برچسب‌ها (مشکل قبلی).")
    lbl_form.addRow("حداکثر پلهٔ جابه‌جایی:", sp_lbl_levels)
    sp_lbl_offset = QDoubleSpinBox()
    sp_lbl_offset.setRange(0.0, 40.0)
    sp_lbl_offset.setDecimals(1)
    sp_lbl_offset.setSingleStep(0.5)
    sp_lbl_offset.setValue(4.0)
    lbl_form.addRow("فاصلهٔ افقی از نقطه (point):", sp_lbl_offset)
    chk_lbl_leader = QCheckBox("خط راهنما از برچسب به نقطهٔ خاموشی")
    chk_lbl_leader.setChecked(True)
    lbl_form.addRow("", chk_lbl_leader)
    layout_inner_lay.addWidget(lbl_box)

    # --- توزیع رنگی مسیر بر اساس تکرار خاموشی (DIgSILENT-style) ---------
    heat_box = QGroupBox("توزیع رنگی مسیر فیدرها بر اساس تکرار خاموشی")
    heat_form = QFormLayout(heat_box)
    chk_heat = QCheckBox("توزیع رنگی فعال باشد")
    heat_form.addRow("", chk_heat)
    sp_heat_radius = QDoubleSpinBox()
    # بدون سقف (درخواست کاربر): فقط کف دارد؛ هر شعاع بزرگ‌تری پذیرفته می‌شود
    sp_heat_radius.setRange(1.0, 1.0e9)
    sp_heat_radius.setDecimals(0)
    sp_heat_radius.setSingleStep(100.0)
    sp_heat_radius.setValue(float(getattr(work, "outage_heat_radius_m", 5000.0)))
    sp_heat_radius.setToolTip(
        "هر خاموشی به یال‌هایی که در این شعاع آن هستند نسبت داده می‌شود "
        "(پیش‌فرض ۵۰۰۰ متر، بدون سقف).")
    heat_form.addRow("شعاع اثر هر خاموشی (m):", sp_heat_radius)
    sp_heat_width = QDoubleSpinBox()
    sp_heat_width.setRange(0.5, 12.0)
    sp_heat_width.setDecimals(1)
    sp_heat_width.setSingleStep(0.2)
    sp_heat_width.setValue(2.4)
    heat_form.addRow("ضخامت خط رنگی (point):", sp_heat_width)

    heat_table = QTableWidget(0, 2)
    heat_table.setHorizontalHeaderLabels(["حد بالا (تعداد)", "رنگ"])
    heat_table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.Stretch)
    heat_table.setMinimumHeight(96)
    heat_table.setToolTip(
        "خالی گذاشتن «حد بالا» یعنی آخرین سطح (بی‌نهایت). برای تغییر رنگ "
        "روی خانهٔ رنگ دوبار کلیک کنید.")
    heat_form.addRow("سطوح:", heat_table)
    heat_btns = QHBoxLayout()
    btn_add_level = QPushButton("افزودن سطح")
    btn_del_level = QPushButton("حذف سطح")
    heat_btns.addWidget(btn_add_level)
    heat_btns.addWidget(btn_del_level)
    heat_btns.addStretch(1)
    heat_form.addRow("", heat_btns)
    layout_inner_lay.addWidget(heat_box)
    layout_inner_lay.addStretch(1)

    tabs.addTab(outage_page, "خاموشی‌ها")

    # -- pull (style → widgets) / events ------------------------------------
    def _paint(lbl: QLabel, color: str) -> None:
        pm = QPixmap(40, 14)
        pm.fill(QColor(color if color else "#000000"))
        lbl.setPixmap(pm)

    def _load(st: MapStyle) -> None:
        rows = feeder_rows(st, list(feeders or []))
        tbl.setRowCount(len(rows))
        tbl.blockSignals(True)
        for i, (k, c) in enumerate(rows):
            it0 = tbl.item(i, 0)
            if it0 is None:
                it0 = QTableWidgetItem(str(k))
                it0.setFlags(it0.flags() & ~Qt.ItemFlag.ItemIsEditable)
                tbl.setItem(i, 0, it0)
            it0.setText(str(k))
            vis = QTableWidgetItem()
            vis.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            vis.setCheckState(Qt.CheckState.Checked if st.visible_feeders is None or
                              k in st.visible_feeders else Qt.CheckState.Unchecked)
            tbl.setItem(i, 1, vis)
            wrap = QWidget()
            h = QHBoxLayout(); h.setContentsMargins(2, 2, 2, 2)
            lbl = QLabel(); _paint(lbl, c)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            b = QPushButton("…"); b.setFixedWidth(40)

            def go(_=False, _k=str(k), _lbl=lbl) -> None:
                cur = work.feeder_colors.get(_k) or st.unknown_color
                cc = QColorDialog.getColor(QColor(cur), dlg, "انتخاب رنگ")
                if cc.isValid():
                    work.feeder_colors[_k] = cc.name()
                    _paint(_lbl, cc.name())
            b.clicked.connect(go)
            h.addWidget(lbl, 1)
            h.addWidget(b)
            wrap.setLayout(h)
            tbl.setCellWidget(i, 2, wrap)
        tbl.blockSignals(False)
        sp_w.setValue(float(st.feeder_width))
        sp_wf.setValue(float(st.feeder_width_filtered))
        btn_unk.setText(st.unknown_color)
        pm = QPixmap(40, 14); pm.fill(QColor(st.unknown_color))
        unk_swatch.setPixmap(pm)
        for key, _, _, _, _ in _SIZE_ATTRS:
            spins[key].setValue(float(getattr(st, key)))
        for key, _ in _MARKER_ATTRS:
            idx = marks[key].findData(getattr(st, key))
            marks[key].setCurrentIndex(max(0, idx))
        for key, _ in _COLOR_ATTRS:
            cols[key].setText(getattr(st, key))
            _paint(swatches[key], getattr(st, key))
        chk_fuse.setChecked(bool(getattr(st, "show_fuse_cutouts", False)))
        chk_legend.setChecked(bool(st.show_legend))
        chk_zones.setChecked(bool(st.show_zone_labels))
        chk_outages.setChecked(bool(st.show_outages))
        chk_outage_labels.setChecked(bool(st.show_outage_labels))
        chk_outage_links.setChecked(bool(st.show_outage_links))
        sp_lbl_levels.setValue(int(getattr(st, "outage_label_max_levels", 3)))
        sp_lbl_offset.setValue(float(getattr(st, "outage_label_offset_pt", 4.0)))
        chk_lbl_leader.setChecked(bool(getattr(st, "outage_label_leader", True)))
        chk_heat.setChecked(bool(getattr(st, "outage_heat_enabled", False)))
        sp_heat_radius.setValue(float(getattr(st, "outage_heat_radius_m", 5000.0)))
        sp_heat_width.setValue(float(getattr(st, "outage_heat_width", 2.4)))
        _fill_heat_table()

    def on_unk() -> None:
        cc = QColorDialog.getColor(QColor(btn_unk.text()), dlg, "انتخاب رنگ")
        if cc.isValid():
            work.unknown_color = cc.name()
            btn_unk.setText(cc.name())
            pm = QPixmap(40, 14); pm.fill(QColor(cc.name()))
            unk_swatch.setPixmap(pm)
    btn_unk.clicked.connect(on_unk)

    for key, _ in _COLOR_ATTRS:
        def go(_=False, _k=key) -> None:
            cur = getattr(work, _k)
            cc = QColorDialog.getColor(QColor(cur), dlg, "انتخاب رنگ")
            if cc.isValid():
                setattr(work, _k, cc.name())
                cols[_k].setText(cc.name())
                _paint(swatches[_k], cc.name())
        cols[key].clicked.connect(go)

    def _wire_spin(key: str) -> None:
        def on_val(v) -> None:
            setattr(work, key, float(v))
        spins[key].valueChanged.connect(on_val)
    for key, _, _, _, _ in _SIZE_ATTRS:
        _wire_spin(key)
    # ضخامت خط فیدرها هم باید در مدل کار بنشیند (وگرنه تغییرش هدر می‌رفت)
    sp_w.valueChanged.connect(
        lambda v: setattr(work, "feeder_width", float(v)))
    sp_wf.valueChanged.connect(
        lambda v: setattr(work, "feeder_width_filtered", float(v)))

    def _wire_marker(key: str) -> None:
        def on_idx(_i: int) -> None:
            setattr(work, key, marks[key].currentData())
        marks[key].currentIndexChanged.connect(on_idx)
    for key, _ in _MARKER_ATTRS:
        _wire_marker(key)
    chk_fuse.toggled.connect(
        lambda on: setattr(work, "show_fuse_cutouts", bool(on)))
    chk_legend.toggled.connect(lambda on: setattr(work, "show_legend", bool(on)))
    chk_zones.toggled.connect(lambda on: setattr(work, "show_zone_labels", bool(on)))
    chk_outages.toggled.connect(lambda on: setattr(work, "show_outages", bool(on)))
    chk_outage_labels.toggled.connect(
        lambda on: setattr(work, "show_outage_labels", bool(on)))
    chk_outage_links.toggled.connect(
        lambda on: setattr(work, "show_outage_links", bool(on)))
    sp_lbl_levels.valueChanged.connect(
        lambda v: setattr(work, "outage_label_max_levels", int(v)))
    sp_lbl_offset.valueChanged.connect(
        lambda v: setattr(work, "outage_label_offset_pt", float(v)))
    chk_lbl_leader.toggled.connect(
        lambda on: setattr(work, "outage_label_leader", bool(on)))
    chk_heat.toggled.connect(
        lambda on: setattr(work, "outage_heat_enabled", bool(on)))
    sp_heat_radius.valueChanged.connect(
        lambda v: setattr(work, "outage_heat_radius_m", float(v)))
    sp_heat_width.valueChanged.connect(
        lambda v: setattr(work, "outage_heat_width", float(v)))

    # ---- سطوح توزیع رنگی: جدول ویرایش‌پذیر ----
    def _heat_rows() -> list:
        levels = list(getattr(work, "outage_heat_levels", []) or [])
        heat_table.blockSignals(True)
        heat_table.setRowCount(len(levels))
        for row, lvl in enumerate(levels):
            top = lvl.get("max")
            item_top = QTableWidgetItem(
                "" if top is None else f"{float(top):g}")
            heat_table.setItem(row, 0, item_top)
            item_c = QTableWidgetItem(str(lvl.get("color") or "#c62828"))
            try:
                item_c.setBackground(QColor(str(lvl.get("color") or "#c62828")))
            except Exception:                     # noqa: BLE001
                pass
            heat_table.setItem(row, 1, item_c)
        heat_table.blockSignals(False)
        return levels

    def _commit_heat() -> None:
        levels = []
        for row in range(heat_table.rowCount()):
            top_item = heat_table.item(row, 0)
            color_item = heat_table.item(row, 1)
            raw = (top_item.text().strip() if top_item is not None else "")
            color = (color_item.text().strip() if color_item is not None
                     else "#c62828")
            try:
                top = None if raw in ("", "∞", "-") else float(raw)
            except ValueError:
                top = None
            label = ("بی‌نهایت" if top is None else f"≤ {top:g}")
            levels.append({"max": top, "color": color, "label": label})
        work.outage_heat_levels = levels

    _fill_heat_table = _heat_rows

    def _on_heat_edit(_item=None) -> None:
        _commit_heat()

    def _pick_heat_color(row: int, _col: int = 0) -> None:
        if row < 0 or row >= heat_table.rowCount():
            return
        item = heat_table.item(row, 1)
        cur = item.text() if item is not None else "#c62828"
        cc = QColorDialog.getColor(QColor(cur), dlg, "رنگ سطح")
        if cc.isValid():
            item.setText(cc.name())
            try:
                item.setBackground(QColor(cc.name()))
            except Exception:                     # noqa: BLE001
                pass
            _commit_heat()

    heat_table.itemChanged.connect(_on_heat_edit)
    heat_table.cellDoubleClicked.connect(_pick_heat_color)

    def _add_level() -> None:
        levels = _heat_rows()
        last_top = None
        for lvl in reversed(levels):
            if lvl.get("max") is not None:
                last_top = float(lvl["max"])
                break
        new_top = (last_top or 10.0) * 2.0
        levels.insert(max(0, len(levels) - 1),
                      {"max": new_top, "color": "#6a1b9a",
                       "label": f"≤ {new_top:g}"})
        work.outage_heat_levels = levels
        _heat_rows()

    def _del_level() -> None:
        row = heat_table.currentRow()
        levels = _heat_rows()
        if 0 <= row < len(levels) and len(levels) > 1:
            levels.pop(row)
            work.outage_heat_levels = levels
            _heat_rows()

    btn_add_level.clicked.connect(_add_level)
    btn_del_level.clicked.connect(_del_level)

    # -- book actions ---------------------------------------------------------
    def refresh_combo() -> None:
        cmb.blockSignals(True)
        cmb.clear()
        for name in sorted(names_book):
            cmb.addItem(name)
        if not names_book:
            cmb.addItem("(بدون استایل ذخیره‌شده)")
        if active["name"] in names_book:
            cmb.setCurrentText(active["name"])
        cmb.blockSignals(False)

    def on_combo(text: str) -> None:
        if text in names_book:
            active["name"] = text
            work.__dict__.update(MapStyle.from_dict(
                names_book[text].as_dict()).__dict__)
            _load(work)
    cmb.currentTextChanged.connect(on_combo)

    def on_save() -> None:
        name = active["name"] or "پیش‌فرض"
        names_book[name] = MapStyle.from_dict(work.as_dict())
        active["name"] = name
        refresh_combo()
        QMessageBox.information(dlg, "Map style",
                                f"تغییرات در استایل «{name}» ثبت شد.")

    def on_save_as() -> None:
        name, ok = QInputDialog.getText(
            dlg, "ذخیره با نام جدید", "نام استایل:",
            text=f"استایل {len(names_book) + 1}")
        name = (name or "").strip()
        if not ok or not name:
            return
        names_book[name] = MapStyle.from_dict(work.as_dict())
        active["name"] = name
        refresh_combo()

    def on_del() -> None:
        if not names_book:
            return
        name = active["name"] or next(iter(sorted(names_book)))
        if QMessageBox.question(dlg, "حذف استایل",
                                f"استایل «{name}» حذف شود؟") != \
                QMessageBox.StandardButton.Yes:
            return
        names_book.pop(name, None)
        active["name"] = next(iter(sorted(names_book)), "")
        refresh_combo()
        if names_book:
            work.__dict__.update(
                MapStyle.from_dict(names_book[active["name"]].as_dict()).__dict__)
        else:
            work.__dict__.update(
                MapStyle.default_for(feeders=list(feeders or [])).__dict__)
        _load(work)

    def on_reset() -> None:
        work.__dict__.update(
            MapStyle.default_for(feeders=list(feeders or [])).__dict__)
        _load(work)
    btn_save.clicked.connect(on_save)
    btn_save_as.clicked.connect(on_save_as)
    btn_del.clicked.connect(on_del)
    btn_reset.clicked.connect(on_reset)

    def _visibility_changed(_item) -> None:
        work.visible_feeders = [str(tbl.item(i, 0).text())
                                for i in range(tbl.rowCount())
                                if tbl.item(i, 1) is not None and
                                tbl.item(i, 1).checkState() == Qt.CheckState.Checked]
    tbl.itemChanged.connect(_visibility_changed)

    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                            QDialogButtonBox.StandardButton.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)

    # init
    refresh_combo()
    if names_book and active["name"] in names_book:
        work = MapStyle.from_dict(names_book[active["name"]].as_dict())
    _load(work)

    # جا دادن پنجره در صفحه و وسط‌چین کردن آن (دکمه OK همیشه دیده شود)
    from PySide6.QtCore import QTimer
    fit_dialog_to_screen(dlg)
    QTimer.singleShot(0, lambda: fit_dialog_to_screen(dlg))

    dlg.result_style = lambda: MapStyle.from_dict(work.as_dict())  # type: ignore
    dlg.result_book = lambda: {k: v.as_dict()
                               for k, v in names_book.items()}    # type: ignore
    dlg.result_active = lambda: active["name"]                     # type: ignore
    return dlg
