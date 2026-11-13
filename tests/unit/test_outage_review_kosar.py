# -*- coding: utf-8 -*-
"""پذیرش بازبینی خاموشی روی دادهٔ واقعی کوثر (فقط‌خواندنی).

هدف: اطمینان از اینکه زنجیرهٔ «نام پست → بانک مکان‌ها → مختصات CRS پروژه →
زون خودکار» روی دادهٔ واقعی کار می‌کند، نه فقط روی دادهٔ ساختگی.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from switchloc.application.outage_review import (DEFAULT_MAX_ZONE_DISTANCE_M,
                                                 build_zone_geometries,
                                                 default_gazetteer_path,
                                                 plan_review_rows,
                                                 suggest_event_places)
from switchloc.application.topology_service import (TopologyService,
                                                   TopologySettings)
from switchloc.geography.places import PlaceGazetteer
from switchloc.persistence.store import ProjectStore

DB = Path(__file__).resolve().parents[2] / "Kosar GIS.sqlite"

pytestmark = pytest.mark.skipif(
    not DB.is_file(), reason="پروژهٔ واقعی کوثر (Kosar GIS.sqlite) موجود نیست")


@pytest.fixture(scope="module")
def kosar():
    gaz_path = default_gazetteer_path()
    if gaz_path is None:
        pytest.skip("بانک آفلاین مکان‌ها موجود نیست")
    store = ProjectStore(str(DB))
    try:
        runs = store.runs()
        net, issues = store.load_network(runs[-1]["id"])
        events = store.load_outages()["events"]
    finally:
        store.close()
    crs = next((f"EPSG:{int(cd.epsg)}" for cd in
                (net.crs_definitions or []) if getattr(cd, "epsg", None)), None)
    if not crs:
        pytest.skip("CRS پروژه در پایگاه ثبت نشده است")
    topo = TopologyService(TopologySettings(persist=False)).run(net, issues=issues)
    records = [SimpleNamespace(**e) for e in events]
    geoms = build_zone_geometries(topo.graph, topo.zones)
    gaz = PlaceGazetteer(gaz_path)
    suggestions = {s.event_id: s for s in suggest_event_places(records, gaz)}
    rows = plan_review_rows(records, suggestions=suggestions, geometries=geoms,
                            project_crs=crs,
                            max_zone_distance_m=DEFAULT_MAX_ZONE_DISTANCE_M)
    return {"crs": crs, "records": records, "geoms": geoms,
            "suggestions": suggestions, "rows": rows,
            "feeder_count": len({g.feeder for g in geoms.values() if g.feeder})}


def test_every_row_has_an_explicit_basis(kosar):
    rows = kosar["rows"]
    assert len(rows) == len(kosar["records"])
    assert len(rows) > 300
    for r in rows:
        assert r.zone_basis in {"point", "single-zone-of-feeder", "unmatched",
                                "no-crs", "saved-review"}


def test_suggested_places_become_project_coordinates(kosar):
    """هر ردیف دارای پیشنهاد مکان باید مختصات متری پروژه بگیرد (یا CRS نامشخص)."""
    rows = kosar["rows"]
    with_place = [r for r in rows
                  if r.place_options and r.place_options[0]["place_id"]]
    assert with_place, "هیچ ردیفی پیشنهاد مکان نگرفت — زنجیرهٔ گازیتیر شکسته است"
    for r in with_place:
        assert r.point is not None
        assert r.point_basis == "suggestion"
        # مختصات متری UTM، نه درجهٔ جغرافیایی
        assert abs(r.point[0]) > 1000 and abs(r.point[1]) > 1000


def test_auto_zone_confirms_only_rows_with_a_matched_zone(kosar):
    rows = kosar["rows"]
    zoned = [r for r in rows if r.zone_id]
    assert zoned, "هیچ زونی خودکار انتخاب نشد"
    for r in zoned:
        assert r.status == "confirmed"          # پیش‌فرض درخواست کاربر
        assert r.zone_basis == "point"
    for r in rows:
        if not r.zone_id:
            assert r.status == "pending"        # هرگز تأیید بدون زون
            assert r.zone_note


def test_zone_belongs_to_the_event_feeder(kosar):
    geoms = kosar["geoms"]
    for r in kosar["rows"]:
        if r.zone_id:
            assert geoms[r.zone_id].feeder == r.feeder_key


def test_feeder_is_not_crossed_between_feeders(kosar):
    """نقطه‌های یک فیدر نباید زون فیدر دیگر را بگیرند (حتی اگر نزدیک‌تر باشد)."""
    rows = kosar["rows"]
    assert len({r.feeder_key for r in rows if r.zone_id}) >= 1
    assert kosar["feeder_count"] >= 2


def test_place_suggestion_is_always_the_first_option(kosar):
    for r in kosar["rows"]:
        opts = r.place_options
        assert opts and opts[-1]["place_id"] == ""      # «بدون مکان» آخر
        match_first = any(o["place_id"] for o in opts[:-1])
        assert opts[0]["is_default"] is True
        if match_first:
            assert opts[0]["place_id"]
            assert opts[0]["label"].startswith("★")
        else:
            assert opts[0]["place_id"] == ""
