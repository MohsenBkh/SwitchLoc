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
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QBrush, QColor
    from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                   QHBoxLayout, QLabel, QMessageBox,
                                   QPushButton, QTableWidget, QTableWidgetItem,
                                   QVBoxLayout)

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
    table = QTableWidget(len(records), len(headers), dlg)
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
    point_cache: dict[tuple[int, int], tuple[float, float] | None] = {}

    def _point_for(i: int, index: int):
        """مختصات گزینهٔ مکان انتخاب‌شده در CRS پروژه (کش‌شده)."""
        key = (i, index)
        if key in point_cache:
            return point_cache[key]
        opts = row_places.get(i) or []
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
        box.clear()
        box.addItem("— انتخاب زون —", "")
        for o in opts:
            suffix = (f" · {o['distance_m']:,.0f} m"
                      if o.get("distance_m") is not None else "")
            box.addItem(f"{o['label']}{suffix}", o["zone_id"])
        ix = box.findData(current)
        box.setCurrentIndex(ix if ix >= 0 else 0)
        box.blockSignals(False)

    def _apply_auto_zone(i: int) -> None:
        """زون را از فیدر + مختصات مکان انتخاب‌شده به‌روز می‌کند."""
        plan = plan_by_event.get(str(records[i].id))
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

    for i, rec in enumerate(records):
        plan = plan_by_event.get(str(rec.id))
        table.setItem(i, 0, make_table_item(str(rec.event_no or rec.id)))
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
        for o in opts:
            place_box.addItem(o["label"], o["place_id"])
        default_ix = next((k for k, o in enumerate(opts) if o.get("is_default")), 0)
        place_box.setCurrentIndex(default_ix)
        table.setCellWidget(i, 5, place_box)

        # --- زون متأثر ----------------------------------------------------
        zone_box = QComboBox()
        zone_box.addItem("— انتخاب زون —", "")
        for o in (plan.zone_options if plan else []):
            zone_box.addItem(o["label"], o["zone_id"])
        target = plan.zone_id if plan else ""
        ix = zone_box.findData(target) if target else 0
        zone_box.setCurrentIndex(ix if ix >= 0 else 0)
        table.setCellWidget(i, 6, zone_box)
        _set_basis(i, plan.zone_basis_fa if plan else ZONE_BASIS_FA["unmatched"],
                   plan.zone_note if plan else "",
                   warn=not target)

        # --- وضعیت (پیش‌فرض: تأیید مهندسی) ------------------------------
        status_box = QComboBox()
        status_box.addItem("تأیید مهندسی", "confirmed")
        status_box.addItem("رد رخداد", "rejected")
        status_box.addItem("در انتظار بررسی", "pending")
        default_status = plan.status if plan else "pending"
        s_ix = status_box.findData(default_status)
        status_box.setCurrentIndex(s_ix if s_ix >= 0 else 2)
        table.setCellWidget(i, 8, status_box)

        # --- گزینه‌های مکان این ردیف (تبدیل مختصات به‌صورت تنبل) --------
        row_places[i] = opts
        if plan is not None and plan.point is not None:
            point_cache[(i, default_ix)] = tuple(plan.point)

        def _on_place(_idx, _i=i) -> None:
            if _i in manual_rows:
                return                      # زون دستی کاربر محفوظ می‌ماند
            _apply_auto_zone(_i)
        place_box.currentIndexChanged.connect(_on_place)

        def _on_zone(_idx, _i=i) -> None:
            manual_rows.add(_i)
            zone_box = table.cellWidget(_i, 6)
            if zone_box.currentData():
                _set_basis(_i, ZONE_BASIS_FA["manual"], "انتخاب دستی مهندس")
            else:
                _set_basis(_i, ZONE_BASIS_FA["unmatched"],
                           "هیچ زونی انتخاب نشده است", warn=True)
        zone_box.currentIndexChanged.connect(_on_zone)

        def _on_status(_idx, _i=i) -> None:
            status = table.cellWidget(_i, 8).currentData()
            zone = table.cellWidget(_i, 6).currentData()
            if status == "confirmed" and not zone:
                _set_basis(_i, table.item(_i, 7).text(),
                           "برای تأیید، ابتدا زون را انتخاب کنید.", warn=True)
        status_box.currentIndexChanged.connect(_on_status)
        table.setRowHeight(i, 44)

    def _paste_note(pasted, skipped):
        info.setText(base_info +
                     f" — نتیجهٔ آخرین جایگذاری: {pasted} سلول نوشته شد، "
                     f"{skipped} سلول رد شد (سلول‌های فقط‌خواندنی و "
                     "کمبوباکس‌های بدون گزینهٔ منطبق رد می‌شوند).")

    make_excel_like(table, paste=True, on_paste=_paste_note)
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
        for i, rec in enumerate(records):
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
                meta = next((o for o in row_places.get(i, [])
                             if o.get("place_id") == place_id), None)
                place_name = (meta.get("name") if meta else "") or ""
            place_name = place_name or (place_box.currentText() if place_id else "")
            point = _point_for(i, place_box.currentIndex())
            if status == "rejected":
                point = None
            out.append({
                "event_id": str(rec.id), "zone_id": str(zone_id or ""),
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
    return dlg
