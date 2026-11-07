# -*- coding: utf-8 -*-
"""Qt offscreen: جدول بازبینی خاموشی — پیش‌فرض‌های درخواست کاربر."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest                                        # noqa: E402

try:
    from PySide6 import QtWidgets                    # noqa: E402
    HAS_QT = True
except ImportError:                                  # pragma: no cover
    HAS_QT = False

pytestmark = pytest.mark.skipif(
    not HAS_QT, reason="PySide6.QtWidgets is not importable")


@pytest.fixture()
def app():
    if QtWidgets.QApplication.instance() is None:
        QtWidgets.QApplication([])
    yield


from types import SimpleNamespace                    # noqa: E402

from switchloc.application.outage_review import (ZoneGeometry,     # noqa: E402
                                                 OutagePlaceSuggestion,
                                                 plan_review_rows)
from switchloc.geography.places import Place, PlaceMatch              # noqa: E402
from switchloc.ui.qt.outage_review_dialog import (                    # noqa: E402
    make_outage_review_dialog)

Z1 = ZoneGeometry("z1", "F1", 1, ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0)))
Z2 = ZoneGeometry("z2", "F1", 2, ((5000.0, 0.0), (5100.0, 0.0)))
GEOMS = {"z1": Z1, "z2": Z2}


def _transform(lat, lon):
    return ((lon - 48.0) * 1000.0, (lat - 38.0) * 1000.0)


def _rec(eid, substation="زرج آباد"):
    return SimpleNamespace(id=eid, feeder_key="F1", feeder_raw="F1",
                           event_no=eid, substation=substation,
                           date_j="1404/02/02", notes="", cause_raw="",
                           device_raw="")


def _suggestion(name="زرج آباد"):
    m = PlaceMatch(place=Place("p1", name, 38.05, 48.06), confidence="بالا",
                   matched_text=name, score=1.0)
    m2 = PlaceMatch(place=Place("p2", "عباس آباد", 38.5, 48.5),
                    confidence="متوسط", matched_text="عباس آباد", score=0.7)
    return OutagePlaceSuggestion("e1", name, (m, m2))


def _dialog(records=None, geoms=None):
    records = records or [_rec("e1")]
    plans = plan_review_rows(records, suggestions={"e1": _suggestion()},
                             geometries=GEOMS if geoms is None else geoms,
                             project_crs="EPSG:32639", transform=_transform)
    dlg = make_outage_review_dialog(None, records=records, plans=plans,
                                    geometries=GEOMS if geoms is None else geoms,
                                    transform=_transform)
    table = dlg.findChildren(QtWidgets.QTableWidget)[0]
    return dlg, table, plans


def test_suggested_place_is_first_and_selected(app):
    dlg, table, _plans = _dialog()
    place = table.cellWidget(0, 5)
    assert place.currentIndex() == 0
    assert place.itemText(0).startswith("★")
    assert place.currentData() == "p1"
    assert place.itemData(place.count() - 1) == ""     # خالی، آخر فهرست


def test_status_defaults_to_engineering_confirmation(app):
    dlg, table, _plans = _dialog()
    status = table.cellWidget(0, 8)
    assert status.currentData() == "confirmed"
    assert status.currentText() == "تأیید مهندسی"


def test_zone_is_auto_selected_from_feeder_and_coordinates(app):
    dlg, table, plans = _dialog()
    assert plans[0].zone_id == "z1"
    zone = table.cellWidget(0, 6)
    assert zone.currentData() == "z1"
    assert "مختصات پیشنهادی" in table.item(0, 7).text()
    rows, skipped, no_zone = dlg.decisions()
    assert (skipped, no_zone) == (0, 0)
    assert rows[0]["zone_id"] == "z1"
    assert rows[0]["status"] == "confirmed"


def test_clearing_the_place_clears_the_auto_zone(app):
    dlg, table, _plans = _dialog()
    place = table.cellWidget(0, 5)
    place.setCurrentIndex(place.count() - 1)
    zone = table.cellWidget(0, 6)
    assert zone.currentData() == ""
    assert "یافتنشد" in table.item(0, 7).text() or "انتخاب دستی" in \
        table.item(0, 7).text()
    _rows, _skipped, no_zone = dlg.decisions()
    assert no_zone == 1                      # بدون زون: تأیید خودکار نمی‌شود


def test_manual_zone_choice_survives_place_changes(app):
    dlg, table, _plans = _dialog()
    zone = table.cellWidget(0, 6)
    zone.setCurrentIndex(zone.findData("z2"))
    assert "انتخاب دستی" in table.item(0, 7).text()
    place = table.cellWidget(0, 5)
    place.setCurrentIndex(0)                 # تغییر مکان نباید زون دستی را بشوید
    assert table.cellWidget(0, 6).currentData() == "z2"


def test_row_without_zone_is_pending_not_confirmed(app):
    dlg, table, _plans = _dialog(records=[_rec("e1", substation="")],
                                 geoms={"z1": Z1})
    # مکان پیشنهادی هست → مختصات → تنها زون فیدر: انتخاب خودکار و تأیید
    assert table.cellWidget(0, 6).currentData() == "z1"
    assert table.cellWidget(0, 8).currentData() == "confirmed"

    records = [_rec("e1", substation=""), _rec("e2")]
    plans = plan_review_rows(records, suggestions={}, geometries=GEOMS,
                             project_crs="EPSG:32639", transform=_transform)
    dlg2 = make_outage_review_dialog(None, records=records, plans=plans,
                                     geometries=GEOMS, transform=_transform)
    table2 = dlg2.findChildren(QtWidgets.QTableWidget)[0]
    # بدون مکان و بدون مختصات + فیدر دو‌زونی → زون حدس زده نمی‌شود
    assert plans[0].zone_id == "" and plans[1].zone_id == ""
    assert table2.cellWidget(0, 6).currentData() == ""
    assert table2.cellWidget(0, 8).currentData() == "pending"
    rows, skipped, no_zone = dlg2.decisions()
    # «در انتظار بررسی» → نه ذخیره می‌شود، نه به‌عنوان تأییدِ بی‌زون شمرده می‌شود
    assert rows == [] and skipped == 2 and no_zone == 0


def test_confirming_without_zone_is_reported_not_saved(app):
    records = [_rec("e1", substation="")]
    plans = plan_review_rows(records, suggestions={}, geometries=GEOMS,
                             project_crs="EPSG:32639", transform=_transform)
    dlg = make_outage_review_dialog(None, records=records, plans=plans,
                                    geometries=GEOMS, transform=_transform)
    table = dlg.findChildren(QtWidgets.QTableWidget)[0]
    status = table.cellWidget(0, 8)
    status.setCurrentIndex(status.findData("confirmed"))   # تأیید دستی بی‌زون
    rows, skipped, no_zone = dlg.decisions()
    assert rows == [] and skipped == 1 and no_zone == 1


def test_persian_help_text_documents_the_defaults(app):
    dlg, _table, _plans = _dialog()
    texts = " ".join(w.text() for w in dlg.findChildren(QtWidgets.QLabel))
    assert "تأیید مهندسی" in texts
    assert "اولین گزینهٔ فهرست" in texts
