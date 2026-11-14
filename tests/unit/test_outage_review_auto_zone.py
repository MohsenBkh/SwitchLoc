# -*- coding: utf-8 -*-
"""انتساب خودکار زون + پیش‌فرض‌های جدول بازبینی خاموشی (بدون Qt).

سه نیاز کاربر:
۱. زون هر رخداد از «فیدر + مختصات مکان پیشنهادی» خودکار انتخاب شود.
۲. مکان پیشنهادی اولین گزینهٔ فهرست و انتخاب پیش‌فرض باشد.
۳. وضعیت پیش‌فرض «تأیید مهندسی» باشد (جز ردیف بدون زون که حدس زده نمی‌شود).
"""
from types import SimpleNamespace

import pytest

from switchloc.application.outage_review import (DEFAULT_MAX_ZONE_DISTANCE_M,
                                                 OutagePlaceSuggestion,
                                                 ZoneGeometry, pick_zone,
                                                 place_options, plan_review_rows,
                                                 zone_options)
from switchloc.geography.places import Place, PlaceMatch

F1_Z1 = ZoneGeometry(zone_id="z1", feeder="F1", zone_no=1,
                     points=((0.0, 0.0), (100.0, 0.0), (100.0, 100.0),
                             (0.0, 100.0)))
F1_Z2 = ZoneGeometry(zone_id="z2", feeder="F1", zone_no=2,
                     points=((5000.0, 0.0), (5100.0, 0.0), (5100.0, 100.0)))
F2_Z1 = ZoneGeometry(zone_id="w1", feeder="F2", zone_no=1,
                     points=((2000.0, 2000.0), (2050.0, 2000.0)))
GEOMS = {g.zone_id: g for g in (F1_Z1, F1_Z2, F2_Z1)}


def _rec(eid="e1", feeder="F1", **kw):
    base = dict(id=eid, feeder_key=feeder, feeder_raw=feeder, event_no=eid,
                substation="", date_j="1404/01/01", notes="", cause_raw="",
                device_raw="")
    base.update(kw)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------- pick_zone
def test_point_inside_zone_is_picked_with_point_basis():
    pick = pick_zone(GEOMS, feeder="F1", point=(120.0, 20.0))
    assert pick.zone_id == "z1"
    assert pick.basis == "point"
    assert pick.basis_fa == "مختصات پیشنهادی"
    # فاصله تا نزدیک‌ترین گرهٔ زون (۱۰۰,۰) — نه تا مرکز یا ضلع
    assert pick.distance_m == pytest.approx(((120 - 100) ** 2 + 20 ** 2) ** 0.5)


def test_point_outside_tolerance_but_single_zone_feeder_falls_back():
    geoms = {"only": ZoneGeometry(zone_id="only", feeder="F3", zone_no=1,
                                  points=((0.0, 0.0), (10.0, 0.0)))}
    pick = pick_zone(geoms, feeder="F3", point=(9000.0, 9000.0))
    assert pick.zone_id == "only"
    assert pick.basis == "single-zone-of-feeder"
    assert pick.nearest_distance_m > DEFAULT_MAX_ZONE_DISTANCE_M


def test_far_point_on_multi_zone_feeder_is_never_guessed():
    pick = pick_zone(GEOMS, feeder="F1", point=(20000.0, 20000.0))
    assert pick.zone_id == ""
    assert pick.basis == "unmatched"
    assert pick.nearest_zone_id in {"z1", "z2"}
    assert pick.nearest_distance_m is not None


def test_feeder_isolation_ignores_other_feeders():
    # نقطه به زون F2 نزدیک است ولی رخداد F1 است → از فیدر F2 برداشته نمی‌شود
    pick = pick_zone(GEOMS, feeder="F1", point=(2010.0, 2000.0))
    assert pick.zone_id in {"", "z1", "z2"}
    assert pick.zone_id != "w1"
    pick2 = pick_zone(GEOMS, feeder="F2", point=(2010.0, 2000.0))
    assert pick2.zone_id == "w1"


def test_no_coordinates_uses_single_zone_rule_only():
    pick = pick_zone(GEOMS, feeder="F1")
    assert pick.zone_id == ""
    assert pick.basis == "unmatched"
    pick_single = pick_zone({"w1": F2_Z1}, feeder="F2")
    assert pick_single.zone_id == "w1"
    assert pick_single.basis == "single-zone-of-feeder"


def test_unknown_crs_never_guesses():
    pick = pick_zone(GEOMS, feeder="F1", point=(10.0, 10.0), reason="no-crs")
    assert pick.zone_id == ""
    assert pick.basis == "no-crs"


def test_zone_options_are_ordered_by_distance():
    opts = zone_options(GEOMS, "F1", point=(120.0, 20.0))
    assert [o["zone_id"] for o in opts] == ["z1", "z2"]
    assert opts[0]["distance_m"] <= opts[1]["distance_m"]


# ------------------------------------------------------------- place_options
def _suggestion(*names):
    matches = []
    for i, name in enumerate(names):
        matches.append(PlaceMatch(place=Place(f"p{i}", name, 38.0 + i / 100,
                                               48.0 + i / 100),
                                  confidence=("بالا" if i == 0 else "متوسط"),
                                  matched_text=name, score=1.0 - i / 10))
    return OutagePlaceSuggestion(event_id="e1", text="x", matches=tuple(matches))


def test_suggested_place_is_first_and_default():
    opts = place_options(_suggestion("زرج آباد", "عباس آباد"))
    assert [o["place_id"] for o in opts] == ["p0", "p1", ""]
    assert opts[0]["is_default"] is True
    assert opts[0]["label"].startswith("★")
    assert all(o["is_default"] is False for o in opts[1:])
    # «بدون مکان تأییدشده» آخر می‌ماند (انتخاب اشتباه نشود)
    assert opts[-1]["place_id"] == ""


def test_saved_place_wins_over_best_match():
    opts = place_options(_suggestion("زرج آباد", "عباس آباد"), saved_place_id="p1")
    assert opts[1]["is_default"] is True
    assert opts[0]["is_default"] is False


def test_without_matches_only_the_empty_option_is_default():
    opts = place_options(None)
    assert len(opts) == 1
    assert opts[0]["place_id"] == "" and opts[0]["is_default"] is True


# ----------------------------------------------------------- plan_review_rows
def _transform(lat, lon):
    """CRS جعلی: درجهٔ ۳۸/۴۸ → مختصات پروژه در همان محدودهٔ زون z1."""
    return ((lon - 48.0) * 1000.0, (lat - 38.0) * 1000.0)


def test_plan_auto_confirms_when_zone_is_found():
    rec = _rec(substation="زرج آباد")
    rows = plan_review_rows([rec], suggestions={"e1": _suggestion("زرج آباد")},
                            geometries=GEOMS, project_crs="EPSG:32639",
                            transform=_transform)
    row = rows[0]
    assert row.feeder_key == "F1"
    assert row.place_options[0]["is_default"] is True
    assert row.point is not None and row.point_basis == "suggestion"
    assert row.zone_id == "z1"
    assert row.zone_basis == "point"
    assert row.status == "confirmed"          # پیش‌فرض درخواست کاربر


def test_project_crs_alone_builds_the_default_transform():
    """بدون ``transform`` صریح، تبدیل باید از CRS پروژه استفاده کند.

    باگ واقعی: امضای ``transform_wgs84_to_project(lat, lon, crs)`` سه‌آرگومانی
    است؛ پاس‌دادن خودِ تابع باعث می‌شد همهٔ مختصات بی‌صدا ``None`` شوند و
    ردیف‌ها بدون هیچ هشداری «یافتنشد» بمانند.
    """
    from switchloc.gis.crs import transform_wgs84_to_project

    rec = _rec(substation="زرج آباد")
    sug = {"e1": _suggestion("زرج آباد")}
    rows = plan_review_rows([rec], suggestions=sug, geometries=GEOMS,
                            project_crs="EPSG:32638")
    p0 = sug["e1"].matches[0].place
    expected = transform_wgs84_to_project(p0.lat, p0.lon, "EPSG:32638")
    assert rows[0].point == pytest.approx(expected)
    assert rows[0].point_basis == "suggestion"
    # زون این هندسه‌های جعلی دور است → هیچ زونی حدس زده نمی‌شود
    assert rows[0].status == "pending"


def test_plan_keeps_pending_when_no_zone_is_matched():
    rec = _rec(substation="جای نامعلوم")
    rows = plan_review_rows([rec], suggestions={"e1": _suggestion("جای نامعلوم")},
                            geometries={}, project_crs="EPSG:32639",
                            transform=_transform)
    assert rows[0].zone_id == ""
    assert rows[0].status == "pending"        # بدون زون، تأیید خودکار ممنوع
    assert rows[0].zone_note


def test_plan_is_pending_when_project_crs_is_unknown():
    rec = _rec(substation="زرج آباد")
    rows = plan_review_rows([rec], suggestions={"e1": _suggestion("زرج آباد")},
                            geometries=GEOMS, project_crs="", transform=None)
    assert rows[0].zone_basis == "no-crs"
    assert rows[0].point is None
    assert rows[0].status == "pending"


def test_saved_review_is_not_overwritten_by_automation():
    rec = _rec(substation="زرج آباد")
    saved = {"e1": {"zone_id": "z2", "status": "confirmed", "place_id": "p0",
                    "coord_x": 5000.0, "coord_y": 50.0}}
    rows = plan_review_rows([rec], suggestions={"e1": _suggestion("زرج آباد")},
                            geometries=GEOMS, project_crs="EPSG:32639",
                            transform=_transform, saved=saved)
    row = rows[0]
    assert row.zone_id == "z2"
    assert row.zone_basis == "saved-review"
    assert row.point == (5000.0, 50.0)
    assert row.point_basis == "saved"
    assert row.status == "confirmed"


def test_saved_coordinates_drive_the_zone_when_place_has_no_latlon():
    rec = _rec(substation="")
    rows = plan_review_rows([rec], geometries=GEOMS, project_crs="EPSG:32639",
                            transform=_transform,
                            saved={"e1": {"coord_x": 30.0, "coord_y": 30.0}})
    assert rows[0].zone_id == "z1"
    assert rows[0].zone_basis == "point"
    assert rows[0].point_basis == "saved"
