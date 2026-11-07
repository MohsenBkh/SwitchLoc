# -*- coding: utf-8 -*-
"""لایه‌های نقشه روی دادهٔ واقعی کوثر: خاموشی‌های دارای مختصات و
سکشنالایزرهای پیشنهادی (بدون Qt، فقط‌خواندنی)."""
from pathlib import Path
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")

import pytest

from switchloc.application.outage_review import (build_zone_geometries,
                                                 default_gazetteer_path,
                                                 outage_label_groups,
                                                 outage_map_points,
                                                 suggest_event_places)
from switchloc.application.topology_service import (TopologyService,
                                                   TopologySettings)
from switchloc.geography.places import PlaceGazetteer
from switchloc.persistence.store import ProjectStore
from switchloc.reliability.load_model import LoadModelSettings, build_node_loads
from switchloc.reliability.sectionalizer import (SectionalizerEngine,
                                                 SectionalizerSettings)
from switchloc.ui.map_renderer import NetworkMapRenderer
from switchloc.ui.map_style import MapStyle

DB = Path(__file__).resolve().parents[2] / "Kosar GIS.sqlite"

pytestmark = pytest.mark.skipif(
    not DB.is_file(), reason="پروژهٔ واقعی کوثر (Kosar GIS.sqlite) موجود نیست")


@pytest.fixture(scope="module")
def kosar():
    store = ProjectStore(str(DB))
    try:
        runs = store.runs()
        net, issues = store.load_network(runs[-1]["id"])
        events = store.load_outages()["events"]
        rates = {r["feeder_key"]: float(r["lambda_per_year"])
                 for r in store.load_outages()["lambda_r"]
                 if r.get("lambda_per_year") is not None}
    finally:
        store.close()
    crs = next((f"EPSG:{int(cd.epsg)}" for cd in (net.crs_definitions or [])
                if getattr(cd, "epsg", None)), None)
    topo = TopologyService(TopologySettings(persist=False)).run(net, issues=issues)
    records = [SimpleNamespace(**e) for e in events]
    return {"net": net, "topo": topo, "records": records, "rates": rates,
            "crs": crs,
            "geoms": build_zone_geometries(topo.graph, topo.zones)}


def _transform(crs):
    from switchloc.gis.crs import transform_wgs84_to_project
    return lambda lat, lon: transform_wgs84_to_project(lat, lon, crs)


def _renderer(kosar, style=None):
    net = kosar["net"]
    topo = kosar["topo"]
    return NetworkMapRenderer(topo.graph, traces=topo.traces, zones=topo.zones,
                              switches={s.id: s for s in net.switches},
                              style=style)


def test_outage_points_come_from_real_coordinates(kosar):
    if not kosar["crs"]:
        pytest.skip("CRS پروژه ثبت نشده است")
    gaz_path = default_gazetteer_path()
    if gaz_path is None:
        pytest.skip("بانک آفلاین مکان‌ها موجود نیست")
    gaz = PlaceGazetteer(gaz_path)
    suggestions = {s.event_id: s
                   for s in suggest_event_places(kosar["records"], gaz)}
    points = outage_map_points(kosar["records"], geometries=kosar["geoms"],
                               suggestions=suggestions,
                               transform=_transform(kosar["crs"]))
    assert points, "هیچ خاموشی‌ای مختصات پروژه نگرفت"
    ids = {p["id"] for p in points}
    assert len(ids) == len(points)                     # بدون تکرار
    for p in points:
        assert p["x"] and p["y"]
        assert p["status"] in {"confirmed", "rejected", "pending"}
        if p["zone_id"]:
            assert kosar["geoms"][p["zone_id"]].feeder == p["feeder"]
            assert p["zone_x"] is not None and p["zone_y"] is not None


def test_saved_review_coordinates_win_over_suggestions(kosar):
    rec = kosar["records"][0]
    saved = {rec.id: {"coord_x": 700000.0, "coord_y": 4160000.0,
                      "zone_id": "", "status": "rejected"}}
    points = outage_map_points([rec], geometries=kosar["geoms"],
                               saved=saved, transform=None)
    assert len(points) == 1
    assert (points[0]["x"], points[0]["y"]) == (700000.0, 4160000.0)
    assert points[0]["status"] == "rejected"


def test_map_renders_both_layers(tmp_path, kosar):
    if not kosar["crs"]:
        pytest.skip("CRS پروژه ثبت نشده است")
    gaz_path = default_gazetteer_path()
    suggestions = ({s.event_id: s for s in
                    suggest_event_places(kosar["records"], PlaceGazetteer(gaz_path))}
                   if gaz_path else {})
    points = outage_map_points(kosar["records"], geometries=kosar["geoms"],
                               suggestions=suggestions,
                               transform=_transform(kosar["crs"]))
    node_kw = dict(build_node_loads(kosar["topo"].graph, kosar["net"],
                                    LoadModelSettings(level="estimated")).node_kw)
    study = SectionalizerEngine(SectionalizerSettings(max_sectionalizers=1)) \
        .run(kosar["topo"].graph, kosar["topo"].traces, node_kw,
             net=kosar["net"], failure_rates=kosar["rates"],
             failure_rate_source="outage")
    sec_nodes = [{"id": c.node, "x": float(c.coord[0]), "y": float(c.coord[1]),
                  "label": c.label}
                 for f in study.feeders if f.best for c in f.best.selected
                 if c.coord is not None]
    assert points and sec_nodes

    r = _renderer(kosar)
    out = r.render(str(tmp_path / "kosar_layers.png"), dpi=60,
                   outage_points=points, sectionalizer_nodes=sec_nodes)
    assert Path(out).stat().st_size > 5000
    assert "outage" in r._drawn
    assert "opt_sectionalizer" in r._drawn

    # پنهان‌کردن همهٔ رخدادها در سبک → لایه رسم نمی‌شود
    style = MapStyle.default_for(feeders=["F3"])
    style.hidden_outage_ids = [p["id"] for p in points]
    r2 = _renderer(kosar, style=style)
    r2.render(str(tmp_path / "kosar_hidden.png"), dpi=60,
              outage_points=points, sectionalizer_nodes=sec_nodes)
    assert "outage" not in r2._drawn
    assert "opt_sectionalizer" in r2._drawn

    # خاموش‌کردن کل لایه
    style.show_outages = False
    r3 = _renderer(kosar, style=style)
    r3.render(str(tmp_path / "kosar_off.png"), dpi=60,
              outage_points=points, sectionalizer_nodes=sec_nodes)
    assert "outage" not in r3._drawn


def test_real_labels_are_aggregated_by_place(kosar):
    """روی دادهٔ واقعی: برچسب‌ها «نام (تعداد)» و مجموع تعدادها = تعداد نقاط."""
    if not kosar["crs"]:
        pytest.skip("CRS پروژه ثبت نشده است")
    gaz_path = default_gazetteer_path()
    if gaz_path is None:
        pytest.skip("بانک آفلاین مکان‌ها موجود نیست")
    suggestions = {s.event_id: s for s in
                   suggest_event_places(kosar["records"],
                                        PlaceGazetteer(gaz_path))}
    points = outage_map_points(kosar["records"], geometries=kosar["geoms"],
                               suggestions=suggestions,
                               transform=_transform(kosar["crs"]))
    groups = outage_label_groups(points)
    assert 0 < len(groups) < len(points)          # چند رخداد در یک مکان ادغام شد
    assert sum(g["count"] for g in groups) == len(points)
    for g in groups:
        assert g["text"].endswith(f"({g['count']})")
        assert g["name"] in g["text"]
    # بیشترین تعداد یک مکان باید > ۱ باشد (سناریوی «کرندق (۴)»)
    assert max(g["count"] for g in groups) >= 2
