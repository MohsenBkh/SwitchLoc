# -*- coding: utf-8 -*-
"""دیالوگ بازبینی محل/زون خاموشی‌ها (جدول اکسل‌مانند).

سه رفتار خواسته‌شده در همین دیالوگ پیاده شده است:

  ۱. **زون خودکار** — هر ردیف بر اساس فیدر رخداد و مختصات «مکان
     پیشنهادی» زون می‌گیرد (`application.outage_review.pick_zone`)؛
     مبنای انتخاب در ستون «مبنای زون» ثبت می‌شود (بند ۱۹). با تغییر
     «مکان پیشنهادی» یا تغییر دستی زون، مبنا هم به‌روز می‌شود.
  ۲. **مکان پیشنهادی اول فهرست** — بهترین تطبیق بانک آفلاین اولین گزینه
     و انتخاب پیش‌فرض است (`place_options`).
  ۳. **وضعیت پیش‌فرض «تأیید مهندسی»** برای همهٔ ردیف‌هایی که زون دارند؛
     ردیف بدون زون «در انتظار بررسی» می‌ماند و صریح علامت می‌خورد، چون
     تأیید بدون زون یعنی انتساب حدسی.

منطق تصمیم‌گیری (plans) بیرون از Qt ساخته می‌شود و آزمون دارد؛ این فایل
فقط نمایش و تعامل است.
"""
from __future__ import annotations

from ...application.outage_review import (DEFAULT_MAX_ZONE_DISTANCE_M,
                                          ZONE_BASIS_FA, pick_zone,
                                          zone_options)


def make_outage_review_dialog(parent, *, records, plans, geometries=None,
                              max_zone_distance_m: float = DEFAULT_MAX_ZONE_DISTANCE_M,
                              bank_line: str = "", info_extra: str = "",
                              transform=None):  # pragma: no cover (Qt)
    """دیالوگ بازبینی؛ پس از ``exec()`` مقدار ``dlg.decisions()`` خوانده می‌شود."""
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel
    from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                   QHBoxLayout, QLabel, QMessageBox,
                                   QPushButton, QTableWidget, QTableWidgetItem,
                                   QVBoxLayout, QLineEdit)

    from .widgets import make_excel_like, make_table_item

    records = list(records)
    plans = list(plans)
    geometries = geometries or {}
    plan_by_event = {p.event_id: p for p in plans}

    dlg = QDialog(parent)
    dlg.setWindowTitle("بازبینی محل و زون رخدادهای خاموشی")
    dlg.resize(1480, 800)
    dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint |
                       Qt.WindowType.WindowMinimizeButtonHint)
    layout = QVBoxLayout(dlg)

    base_info = (
        bank_line +
        "زون هر ردیف به‌صورت خودکار از «فیدر + مختصات مکان پیشنهادی» "
        f"انتخاب می‌شود (تحمل {max_zone_distance_m:,.0f} متر) و مبنای آن در "
        "ستون «مبنای زون» ثبت می‌گردد؛ هیچ زونی حدس زده نمی‌شود. "
        "اگر مکان پیشنهادی پیدا شده باشد، اولین گزینهٔ فهرست همان پیشنهاد "
        "است و به‌صورت پیش‌فرض انتخاب می‌شود. وضعیت پیش‌فرض همهٔ ردیف‌ها "
        "«تأیید مهندسی» است؛ در صورت مغایرت تغییرش دهید. ردیف‌هایی که زون "
        "ندارند «در انتظار بررسی» می‌مانند (تأیید بدون زون مجاز نیست). "
        "جدول اکسل‌مانند است: کلیک روی هدر/شمارهٔ ردیف کل سطر/ستون را "
        "انتخاب می‌کند؛ Ctrl+C کپی TSV و Ctrl+V جایگذاری است.")
    info = QLabel(base_info + ((" " + info_extra) if info_extra else ""))
    info.setWordWrap(True)
    layout.addWidget(info)

    headers = ["رخداد", "نام پست", "فیدر", "تاریخ", "توضیحات",
               "مکان پیشنهادی", "زون متأثر (تأیید مهندس)", "مبنای زون",
               "وضعیت"]
    incremental = len(records) > 500
    table = QTableWidget(0 if incremental else len(records), len(headers), dlg)
    table.setHorizontalHeaderLabels(headers)
    table.setWordWrap(True)
    table.setAlternatingRowColors(True)
    for col, width in ((0, 80), (1, 140), (2, 70), (3, 90), (4, 260),
                       (5, 240), (6, 260), (7, 150), (8, 130)):
        table.setColumnWidth(col, width)

    #: ردیف‌هایی که کاربر زونشان را دستی تغییر داده است (انتخاب خودکار
    #: دیگر روی آن‌ها اعمال نمی‌شود)
    manual_rows: set[int] = set()
    #: گزینه‌های مکان هر ردیف (برای تبدیل مختصات به CRS پروژه)
    row_places: dict[int, list] = {}
    #: مختصات هر گزینهٔ مکان در CRS پروژه: (row, index) → (x, y) | None
    point_cache: dict[tuple[str, int], tuple[float, float] | None] = {}
    # Share immutable option models: thousands of identical QComboBox models
    # otherwise replicate hundreds of zone entries per event.
    option_models = {}

    def option_model(items):
        key = tuple((str(label), str(data)) for label, data in items)
        if key not in option_models:
            model = QStandardItemModel(dlg)
            for label, data in items:
                item = QStandardItem(str(label))
                item.setData(data, Qt.ItemDataRole.UserRole)
                model.appendRow(item)
            option_models[key] = model
        return option_models[key]

    def _point_for(i: int, index: int):
        """مختصات گزینهٔ مکان انتخاب‌شده در CRS پروژه (کش‌شده)."""
        event_id = table.item(i, 0).data(Qt.ItemDataRole.UserRole)
        key = (event_id, index)
        if key in point_cache:
            return point_cache[key]
        opts = row_places.get(event_id) or []
        point = None
        if 0 <= index < len(opts):
            o = opts[index]
            if o.get("lat") is not None and o.get("lon") is not None \
                    and transform is not None:
                try:
                    point = tuple(transform(float(o["lat"]), float(o["lon"])))
                except Exception:                   # noqa: BLE001
                    point = None
        point_cache[key] = point
        return point

    def _set_basis(i: int, text: str, note: str = "",
                   warn: bool = False) -> None:
        item = table.item(i, 7)
        if item is None:
            item = QTableWidgetItem()
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(i, 7, item)
        item.setText(text)
        item.setToolTip(note or text)
        if warn:
            item.setBackground(QBrush(QColor("#ffe0b2")))
        else:
            item.setBackground(QBrush(QColor("#e8f5e9")))

    def _row_zone_options(i: int, feeder: str, point):
        box = table.cellWidget(i, 6)
        current = box.currentData()
        opts = zone_options(geometries, feeder, point=point)
        box.blockSignals(True)
        # Detach from the shared immutable option model before changing it.
        box.setModel(QStandardItemModel(box))
        box.addItem("— انتخاب زون —", "")
        for o in opts:
            suffix = (f" · {o['distance_m']:,.0f} m"
                      if o.get("distance_m") is not None else "")
            box.addItem(f"{o['label']}{suffix}", o["zone_id"])
        ix = box.findData(current)
        box.setCurrentIndex(ix if ix >= 0 else 0)
        box.blockSignals(False)
        table.item(i, 6).setText(box.currentText())

    def _apply_auto_zone(i: int) -> None:
        """زون را از فیدر + مختصات مکان انتخاب‌شده به‌روز می‌کند."""
        plan = plan_by_event.get(str(table.item(i, 0).data(Qt.ItemDataRole.UserRole)))
        if plan is None:
            return
        place_box = table.cellWidget(i, 5)
        zone_box = table.cellWidget(i, 6)
        point = _point_for(i, place_box.currentIndex())
        _row_zone_options(i, plan.feeder_key, point)
        pick = pick_zone(geometries, feeder=plan.feeder_key, point=point,
                         max_distance_m=max_zone_distance_m)
        if pick.zone_id:
            ix = zone_box.findData(pick.zone_id)
            if ix >= 0:
                zone_box.setCurrentIndex(ix)
            _set_basis(i, pick.basis_fa,
                       ("فاصله تا هندسهٔ زون: "
                        f"{pick.distance_m:,.1f} متر" if pick.distance_m is not None
                        else ""))
        else:
            zone_box.setCurrentIndex(0)
            note = ("نزدیک‌ترین زون "
                    f"{pick.nearest_distance_m:,.0f} متر دورتر از مختصات است؛ "
                    "انتخاب دستی لازم است."
                    if pick.nearest_distance_m is not None
                    else "زون متناظر از فیدر/مختصات تعیین نشد؛ انتخاب دستی لازم است.")
            _set_basis(i, pick.basis_fa, note, warn=True)

    def _populate_row(i, rec):
            plan = plan_by_event.get(str(rec.id))
            anchor = make_table_item(str(rec.event_no or rec.id))
            anchor.setData(Qt.ItemDataRole.UserRole, str(rec.id))
            table.setItem(i, 0, anchor)
            table.setItem(i, 1, make_table_item(str(rec.substation or "—")))
            table.setItem(i, 2, make_table_item(
                str(rec.feeder_key or rec.feeder_raw or "—")))
            table.setItem(i, 3, make_table_item(str(rec.date_j or "")))
            table.setItem(i, 4, make_table_item(str(rec.notes or rec.cause_raw or "")))

            # --- مکان پیشنهادی (پیشنهاد اول، انتخاب پیش‌فرض) -----------------
            place_box = QComboBox()
            opts = list(plan.place_options) if plan else [
                {"place_id": "", "label": "بدون مکان تأییدشده", "lat": None,
                 "lon": None, "is_default": True}]
            place_box.setModel(option_model([(o["label"], o["place_id"]) for o in opts]))
            default_ix = next((k for k, o in enumerate(opts) if o.get("is_default")), 0)
            place_box.setCurrentIndex(default_ix)
            table.setItem(i, 5, make_table_item(place_box.currentText()))
            table.setCellWidget(i, 5, place_box)

            # --- زون متأثر ----------------------------------------------------
            zone_box = QComboBox()
            zone_box.setModel(option_model(
                [("— انتخاب زون —", "")] +
                [(o["label"], o["zone_id"]) for o in (plan.zone_options if plan else [])]))
            target = plan.zone_id if plan else ""
            ix = zone_box.findData(target) if target else 0
            zone_box.setCurrentIndex(ix if ix >= 0 else 0)
            table.setItem(i, 6, make_table_item(zone_box.currentText()))
            table.setCellWidget(i, 6, zone_box)
            _set_basis(i, plan.zone_basis_fa if plan else ZONE_BASIS_FA["unmatched"],
                       plan.zone_note if plan else "",
                       warn=not target)

            # --- وضعیت (پیش‌فرض: تأیید مهندسی) ------------------------------
            status_box = QComboBox()
            status_box.setModel(option_model([("تأیید مهندسی", "confirmed"),
                                              ("رد رخداد", "rejected"),
                                              ("در انتظار بررسی", "pending")]))
            default_status = plan.status if plan else "pending"
            s_ix = status_box.findData(default_status)
            status_box.setCurrentIndex(s_ix if s_ix >= 0 else 2)
            table.setItem(i, 8, make_table_item(status_box.currentText()))
            table.setCellWidget(i, 8, status_box)

            # --- گزینه‌های مکان این ردیف (تبدیل مختصات به‌صورت تنبل) --------
            event_id = str(rec.id)
            row_places[event_id] = opts
            if plan is not None and plan.point is not None:
                point_cache[(event_id, default_ix)] = tuple(plan.point)

            def _on_place(_idx, _anchor=anchor) -> None:
                _i = table.row(_anchor)
                if _i < 0:
                    return
                table.item(_i, 5).setText(table.cellWidget(_i, 5).currentText())
                if _anchor.data(Qt.ItemDataRole.UserRole) in manual_rows:
                    return                      # زون دستی کاربر محفوظ می‌ماند
                _apply_auto_zone(_i)
            place_box.currentIndexChanged.connect(_on_place)

            def _on_zone(_idx, _anchor=anchor) -> None:
                _i = table.row(_anchor)
                if _i < 0:
                    return
                manual_rows.add(_anchor.data(Qt.ItemDataRole.UserRole))
                zone_box = table.cellWidget(_i, 6)
                table.item(_i, 6).setText(zone_box.currentText())
                if zone_box.currentData():
                    _set_basis(_i, ZONE_BASIS_FA["manual"], "انتخاب دستی مهندس")
                else:
                    _set_basis(_i, ZONE_BASIS_FA["unmatched"],
                               "هیچ زونی انتخاب نشده است", warn=True)
            zone_box.currentIndexChanged.connect(_on_zone)

            def _on_status(_idx, _anchor=anchor) -> None:
                _i = table.row(_anchor)
                if _i < 0:
                    return
                table.item(_i, 8).setText(table.cellWidget(_i, 8).currentText())
                status = table.cellWidget(_i, 8).currentData()
                zone = table.cellWidget(_i, 6).currentData()
                if status == "confirmed" and not zone:
                    _set_basis(_i, table.item(_i, 7).text(),
                               "برای تأیید، ابتدا زون را انتخاب کنید.", warn=True)
            status_box.currentIndexChanged.connect(_on_status)
            table.setRowHeight(i, 44)

    if not incremental:
        for i, rec in enumerate(records):
            _populate_row(i, rec)

    def _paste_note(pasted, skipped):
        info.setText(base_info +
                     f" — نتیجهٔ آخرین جایگذاری: {pasted} سلول نوشته شد، "
                     f"{skipped} سلول رد شد (سلول‌های فقط‌خواندنی و "
                     "کمبوباکس‌های بدون گزینهٔ منطبق رد می‌شوند).")

    make_excel_like(table, paste=True, on_paste=_paste_note)
    # Column filters keep the underlying row order and its decision widgets intact.
    filters = QHBoxLayout()
    filter_boxes = []
    timer = QTimer(dlg)
    timer.setSingleShot(True)
    timer.setInterval(250)
    for header in headers:
        edit = QLineEdit()
        edit.setPlaceholderText(header)
        edit.setToolTip("فیلتر ستون " + header)
        edit.textChanged.connect(lambda _text: timer.start())
        filters.addWidget(edit)
        filter_boxes.append(edit)
    def apply_filters():
        from .widgets import _cell_text
        terms = [edit.text().strip().casefold() for edit in filter_boxes]
        for row in range(table.rowCount()):
            table.setRowHidden(row, any(term and term not in _cell_text(table, row, col).casefold()
                                        for col, term in enumerate(terms)))
    timer.timeout.connect(apply_filters)
    layout.addLayout(filters)
    sorting = QHBoxLayout()
    sorting.addWidget(QLabel("مرتب‌سازی ستون:"))
    sort_column = QComboBox()
    sort_column.addItems(headers)
    sorting.addWidget(sort_column)
    sort_buttons = []
    for text, order in (("صعودی", Qt.SortOrder.AscendingOrder),
                        ("نزولی", Qt.SortOrder.DescendingOrder)):
        button = QPushButton(text)
        button.clicked.connect(lambda _checked=False, order=order:
                               table.sortItems(sort_column.currentIndex(), order))
        sorting.addWidget(button)
        sort_buttons.append(button)
    sorting.addStretch(1)
    layout.addLayout(sorting)
    layout.addWidget(table, 1)

    bulk = QHBoxLayout()
    btn_all_confirm = QPushButton("همه: تأیید مهندسی")
    btn_all_pending = QPushButton("همه: در انتظار بررسی")

    def _bulk(status: str) -> None:
        for i in range(table.rowCount()):
            box = table.cellWidget(i, 8)
            ix = box.findData(status)
            if ix >= 0:
                box.blockSignals(True)
                box.setCurrentIndex(ix)
                box.blockSignals(False)
                table.item(i, 8).setText(box.currentText())
    btn_all_confirm.clicked.connect(lambda: _bulk("confirmed"))
    btn_all_pending.clicked.connect(lambda: _bulk("pending"))
    bulk.addWidget(btn_all_confirm)
    bulk.addWidget(btn_all_pending)
    bulk.addStretch(1)
    layout.addLayout(bulk)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                               QDialogButtonBox.StandardButton.Cancel)
    layout.addWidget(buttons)
    buttons.rejected.connect(dlg.reject)

    def decisions() -> tuple[list[dict], int, int]:
        """(تصمیم‌ها، تعداد نادیده‌گرفته‌شده، تعداد تأییدنشده بدون زون)."""
        out, skipped, no_zone = [], 0, 0
        for i in range(table.rowCount()):
            event_id = str(table.item(i, 0).data(Qt.ItemDataRole.UserRole))
            zone_box = table.cellWidget(i, 6)
            status_box = table.cellWidget(i, 8)
            place_box = table.cellWidget(i, 5)
            zone_id = zone_box.currentData()
            status = status_box.currentData()
            if status == "pending":
                skipped += 1
                continue
            if status == "confirmed" and not zone_id:
                no_zone += 1
                skipped += 1
                continue
            place_id = place_box.currentData() or ""
            place_name = ""
            if place_id:
                meta = next((o for o in row_places.get(event_id, [])
                             if o.get("place_id") == place_id), None)
                place_name = (meta.get("name") if meta else "") or ""
            place_name = place_name or (place_box.currentText() if place_id else "")
            point = _point_for(i, place_box.currentIndex())
            if status == "rejected":
                point = None
            out.append({
                "event_id": event_id, "zone_id": str(zone_id or ""),
                "place_id": place_id, "place_name": place_name,
                "status": status,
                "zone_basis": (table.item(i, 7).text()
                               if table.item(i, 7) is not None else ""),
                "coord_x": (point[0] if point else None),
                "coord_y": (point[1] if point else None),
            })
        return out, skipped, no_zone

    def on_save() -> None:
        out, skipped, no_zone = decisions()
        message = f"{len(out)} ردیف ذخیره می‌شود"
        if skipped:
            message += (f"؛ {skipped} ردیف بدون تغییر باقی می‌ماند "
                        f"({no_zone} ردیف تأییدشده بدون زون بود — تأیید "
                        "بدون زون مجاز نیست)")
        dlg.setProperty("save_message", message)
        dlg.accept()

    buttons.accepted.connect(on_save)
    dlg.decisions = decisions                     # type: ignore[attr-defined]
    if incremental:
        from PySide6.QtWidgets import QDialogButtonBox as _DBB
        save_button = buttons.button(_DBB.StandardButton.Save)
        controls = filter_boxes + sort_buttons + [sort_column, btn_all_confirm, btn_all_pending, save_button]
        for control in controls:
            control.setEnabled(False)
        progress = QLabel(f"در حال آماده‌سازی جدول: ۰ از {len(records):,}")
        layout.insertWidget(1, progress)
        loader = QTimer(dlg)
        loader.setInterval(0)
        loaded = [0]
        # Paint once at the end; repainting thousands of widget cells per
        # batch dominates the work. The progress label remains responsive.
        table.setUpdatesEnabled(False)
        def load_batch():
            start = loaded[0]
            end = min(start + 300, len(records))
            table.setRowCount(end)
            for i in range(start, end):
                _populate_row(i, records[i])
            loaded[0] = end
            progress.setText(f"در حال آماده‌سازی جدول: {end:,} از {len(records):,}")
            if end == len(records):
                loader.stop()
                table.setUpdatesEnabled(True)
                progress.setText(f"آماده: {end:,} رخداد")
                for control in controls:
                    control.setEnabled(True)
        loader.timeout.connect(load_batch)
        dlg.finished.connect(lambda *_: loader.stop())
        loader.start()
        dlg._review_loader = loader
    return dlg
