# -*- coding: utf-8 -*-
"""Dashboard data-layer tests (Qt-free — build_dashboard + draw_charts).

The dashboard must merge, per feeder: trace stats + outage λ/r + n-1
EP/TL + formula-(1) rank + selected scheme — and never invent numbers
when a part is missing (zeros / "—" instead).
"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure                     # noqa: E402

import pytest                                            # noqa: E402

from switchloc.ui.dashboard_data import (build_dashboard,  # noqa: E402
                                         feeder_rows, summarize_outage)
from switchloc.ui.qt.dashboard_tab import draw_charts    # noqa: E402
from switchloc.validation.issues import IssueLog         # noqa: E402

from conftest import NetBuilder                          # noqa: E402


@pytest.fixture()
def topo_two_feeders():
    """Tiny 2-feeder network through the real TopologyService."""
    from switchloc.application.topology_service import (TopologyService,
                                                        TopologySettings)
    b = NetBuilder()
    b.source(0, 0, "F1 - KHALKHAL")
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.transformer(100, 0)
    b.source(500, 0, "F2 - KHALKHAL")
    b.line([(500, 0), (600, 0)], feeder="F2")
    b.transformer(600, 0)
    net = b.net
    topo = TopologyService(TopologySettings(user="t", persist=False)).run(net)
    return net, topo


def test_build_dashboard_network_only(topo_two_feeders):
    net, topo = topo_two_feeders
    dash = build_dashboard(net=net, topo=topo)
    k = dash["kpis"]
    assert k["feeders"] == 2
    assert k["nodes"] == net.summary()["nodes"]
    assert k["zones"] == len(topo.zones.zones)
    assert k["total_lambda"] == 0.0
    assert k["proposed_switches"] == 0
    assert dash["has_topology"] and not dash["has_placement"]
    assert dash["lambda_source"] == "no outage data (λ = 0)"
    rows = dash["feeders"]
    # v1.16: شناسهٔ فیدر، نام کامل GIS است (نه توکن کوتاه)
    assert [r["feeder_key"] for r in rows] == ["F1 - KHALKHAL", "F2 - KHALKHAL"]
    assert rows[0]["edges"] == 1 and rows[0]["transformers"] == 1
    assert rows[0]["rank"] is None and rows[0]["scheme_kind"] is None


def test_feeder_rows_merge_outage_ranking_and_scheme(topo_two_feeders):
    _net, topo = topo_two_feeders
    outage = NS(lambda_r=[NS(as_dict=lambda: {
                    "feeder_key": "F1", "lambda_per_year": 3.25,
                    "lambda_reducible_per_year": 1.0, "r_minutes": 45.0,
                    "u_hours": 2.44})], records=[], reader_stats={},
                levels={"class_summary": {}})
    snap = {
        "table14_eptl": [{"feeder_key": "F1", "ep_percent": 62.5,
                          "tl_percent": 40.0, "total_load_kw": 800.0,
                          "zone_count": 3}],
        "ranking": [{"feeder_key": "F1", "rank": 1, "score": 0.5123,
                     "ties_count": 2, "lambda_per_year": 3.25,
                     "r_minutes": 45.0},
                    {"feeder_key": "F2", "rank": 2, "score": 0.1,
                     "ties_count": 0, "lambda_per_year": 0.0,
                     "r_minutes": 0.0}],
        "recommendation": [{"feeder_key": "F1", "rank": 1,
                            "scheme_kind": "sequential_nc",
                            "n_switches": 2,
                            "switches": [{"node": "n1", "kind": "NC"}]}],
        "table18_comparison": [{"kind": "sequential_nc", "feeders": ["F1"],
                                "n_switches": 2, "e2_before_kwh": 100.0,
                                "e1_after_kwh": 40.0, "ce_rials": 6e10,
                                "cn_rials": 5e9, "ce_over_cn": 12.0,
                                "selected": True}],
        "issues": [{"code": "X", "severity": "Warning", "message_fa": "م"}],
    }
    rows = feeder_rows(topo.traces,
                       summarize_outage(outage)["lambda_r"], snap)
    f1 = {r["feeder_key"]: r for r in rows}["F1 - KHALKHAL"]
    assert f1["lambda_per_year"] == 3.25 and f1["r_minutes"] == 45.0
    assert f1["u_hours"] == 2.44
    assert f1["ep_percent"] == 62.5 and f1["total_load_kw"] == 800.0
    assert f1["rank"] == 1 and f1["score"] == 0.5123
    assert f1["scheme_kind"] == "sequential_nc" and f1["n_switches"] == 2
    # F2 has no outage row → falls back to the ranking λ (0.0), no invention
    f2 = {r["feeder_key"]: r for r in rows}["F2 - KHALKHAL"]
    assert f2["lambda_per_year"] == 0.0 and f2["scheme_kind"] is None


def test_build_dashboard_with_placement_and_outage(topo_two_feeders):
    net, topo = topo_two_feeders
    outage = NS(lambda_r=[], records=[], reader_stats={},
                levels={"class_summary": {"برنامه‌ریزی‌شده": 4}})
    placement = NS(to_dict=lambda: {
        "table14_eptl": [], "ranking": [], "recommendation": [],
        "table18_comparison": [{"kind": "k", "feeders": ["F1"],
                                "n_switches": 1, "e2_before_kwh": 1.0,
                                "e1_after_kwh": 0.5, "ce_rials": 1.0,
                                "cn_rials": 1.0, "ce_over_cn": 1.0,
                                "selected": True}],
        "schemes": [], "issues": [],
        "settings": {"area_mode": "strict"}})
    dash = build_dashboard(net=net, topo=topo, outage=outage,
                           placement=placement, lambda_source="test")
    assert dash["has_placement"]
    assert dash["kpis"]["selected_schemes"] == 1
    assert dash["outage"]["class_summary"] == {"برنامه‌ریزی‌شده": 4}
    assert dash["lambda_source"] == "test"


def test_summarize_outage_persisted_store_payload():
    payload = {"outage_run_id": "run-1", "lambda_r": [
        {"feeder_key": "F1", "lambda_per_year": 6.33, "r_minutes": 36.63}],
        "summary": {"records": 1783, "rows_empty_skipped": 895,
                    "class_summary": {"a": 1}, "years": [1404]}}
    s = summarize_outage(payload)
    assert s["available"] and s["source"] == "run-1"
    assert s["records"] == 1783 and s["years"] == [1404]
    assert s["lambda_r"][0]["lambda_per_year"] == 6.33


def test_draw_charts_three_panels_and_empty(topo_two_feeders):
    _net, topo = topo_two_feeders
    dash = build_dashboard(net=None, topo=topo)
    fig = Figure(figsize=(8, 3))
    draw_charts(fig, dash)
    assert len(fig.get_axes()) == 3
    assert all(len(ax.patches) or len(ax.lines) or ax.containers
               for ax in fig.get_axes())
    empty = build_dashboard(net=None, topo=None)
    fig2 = Figure(figsize=(8, 3))
    draw_charts(fig2, empty)
    assert len(fig2.get_axes()) == 1          # placeholder panel


def test_build_dashboard_everything_missing_is_safe():
    dash = build_dashboard()
    assert dash["kpis"]["feeders"] == 0
    assert dash["feeders"] == []
    assert dash["lambda_source"].startswith("no outage data")


def test_dashboard_selected_feeders_filters_every_network_kpi(topo_two_feeders):
    net, topo = topo_two_feeders
    dash = build_dashboard(net=net, topo=topo, scope=["F2"])
    assert [r["feeder_key"] for r in dash["feeders"]] == ["F2 - KHALKHAL"]
    assert dash["kpis"]["feeders"] == 1
    assert dash["kpis"]["length_km"] == dash["feeders"][0]["km"]
    assert dash["kpis"]["transformers"] == 1
    assert dash["kpis"]["zones"] == len(topo.zones.zones_of_feeder("F2"))
    assert dash["kpis"]["scope"] == "F2"


def test_dashboard_empty_selected_scope_is_not_whole_network(topo_two_feeders):
    net, topo = topo_two_feeders
    dash = build_dashboard(net=net, topo=topo, scope=[])
    assert dash["feeders"] == []
    assert dash["kpis"]["feeders"] == 0
    assert dash["kpis"]["scope"] == "no feeders selected"


def test_summarize_outage_filters_live_records_to_selected_feeders():
    from switchloc.ui.dashboard_data import summarize_outage
    records = [
        NS(feeder_key="F1", year=1404, outage_class="قابل کاهش با کلیدگذاری"),
        NS(feeder_key="F2", year=1405, outage_class="نیازمند تعمیر یا تعویض تجهیز"),
    ]
    outage = NS(lambda_r=[
        NS(as_dict=lambda: {"feeder_key": "F1", "lambda_per_year": 2.0}),
        NS(as_dict=lambda: {"feeder_key": "F2", "lambda_per_year": 3.0}),
    ], records=records, reader_stats={"rows_empty_skipped": 7},
        levels={"class_summary": {"global": 99}}, outage_run_id="r")
    result = summarize_outage(outage, {"F2"})
    assert result["records"] == 1
    assert result["years"] == [1405]
    assert result["class_summary"] == {"نیازمند تعمیر یا تعویض تجهیز": 1}
    assert [r["feeder_key"] for r in result["lambda_r"]] == ["F2"]
    assert result["rows_empty_skipped"] is None


def test_zone_load_map_flattens_authoritative_n_minus_one_zone_loads():
    from switchloc.ui.dashboard_data import zone_load_map
    placement = NS(n1=NS(zone_load_kw={
        "F1": {"F1-Z0": 125.5, "F1-Z1": 80.0},
        "F2": {"F2-Z0": 42.25},
    }))
    result = zone_load_map(NS(), NS(), placement=placement)
    assert result == {"F1-Z0": 125.5, "F1-Z1": 80.0, "F2-Z0": 42.25}


def test_persisted_outage_scope_does_not_reuse_global_aggregate_counts():
    from switchloc.ui.dashboard_data import summarize_outage
    payload = {
        "outage_run_id": "persisted",
        "lambda_r": [{"feeder_key": "F1", "lambda_per_year": 1.0}],
        "summary": {"records": 100, "rows_empty_skipped": 20,
                    "class_summary": {"global": 100}, "years": [1404]},
    }
    scoped = summarize_outage(payload, {"F1"})
    assert scoped["lambda_r"][0]["feeder_key"] == "F1"
    assert scoped["records"] is None
    assert scoped["rows_empty_skipped"] is None
    assert scoped["class_summary"] == {}
    assert scoped["years"] == []


def test_map_zone_labels_include_load_and_remain_pickable(topo_two_feeders):
    from matplotlib.figure import Figure
    from switchloc.ui.map_renderer import NetworkMapRenderer
    from switchloc.ui.map_style import MapStyle
    net, topo = topo_two_feeders
    renderer = NetworkMapRenderer(
        topo.graph, traces=topo.traces, zones=topo.zones,
        switches={s.id: s for s in net.switches}, style=MapStyle())
    zone = topo.zones.zones[0]
    fig = Figure(figsize=(5, 4))
    renderer.render_into(fig, zone_labels=True,
                         zone_load_kw={zone.id: 123.4})
    labels = [artist for ax in fig.axes for artist in ax.texts
              if str(artist.get_gid() or "").startswith("zone:")]
    assert labels
    assert any("123 kW" in artist.get_text() for artist in labels)
    assert labels[0].get_picker() == 5


def test_map_explicit_zone_label_off_overrides_saved_style(topo_two_feeders):
    from matplotlib.figure import Figure
    from switchloc.ui.map_renderer import NetworkMapRenderer
    from switchloc.ui.map_style import MapStyle
    net, topo = topo_two_feeders
    renderer = NetworkMapRenderer(
        topo.graph, traces=topo.traces, zones=topo.zones,
        switches={s.id: s for s in net.switches},
        style=MapStyle(show_zone_labels=True))
    fig = Figure(figsize=(5, 4))
    renderer.render_into(fig, zone_labels=False)
    labels = [artist for ax in fig.axes for artist in ax.texts
              if str(artist.get_gid() or "").startswith("zone:")]
    assert labels == []


def test_dashboard_recomputes_live_coverage_for_selected_feeder(topo_two_feeders):
    net, topo = topo_two_feeders
    records = [
        NS(feeder_key="F1", year=1404, month=1,
           outage_class="قابل کاهش با کلیدگذاری"),
        NS(feeder_key="F2", year=1404, month=4,
           outage_class="قابل کاهش با کلیدگذاری"),
    ]
    outage = NS(lambda_r=[], records=records, reader_stats={},
                levels={"class_summary": {}}, settings={"coverage": {}})
    dash = build_dashboard(net=net, topo=topo, outage=outage, scope="F1")
    assert dash["coverage"]["start"] == [1404, 1]
    assert dash["coverage"]["end"] == [1404, 1]


def test_dashboard_exposes_zone_register_and_formats_lengths(topo_two_feeders):
    net, topo = topo_two_feeders
    dash = build_dashboard(net=net, topo=topo)
    assert len(dash["zones"]) == len(topo.zones.zones)
    assert dash["kpis"]["zones"] == len(dash["zones"])
    assert all("length_label" in z and "load_kw" in z for z in dash["zones"])
    assert all(z["load_kw"] is None for z in dash["zones"])  # no load run yet
    # The tiny fixture has a short feeder zone; the user-facing unit is metres.
    assert all(z["length_label"].endswith("m") for z in dash["zones"])


def test_placement_snapshot_and_dashboard_share_n1_zone_loads(topo_two_feeders):
    from switchloc.placement.service import EngineSettings, PlacementEngine
    from switchloc.reliability.load_model import LoadModelSettings, LEVEL_SUBSTITUTE
    net, topo = topo_two_feeders
    engine = PlacementEngine(EngineSettings(
        load_model=LoadModelSettings(level=LEVEL_SUBSTITUTE)))
    result = engine.run(topo.graph, net, topo.traces, topo.zones, topo.ties,
                        traces_strict=topo.traces_strict)
    snap = result.to_dict()
    assert snap["zone_register"]
    assert sum(z["load_kw"] for z in snap["zone_register"]) == pytest.approx(
        sum(t.total_load_kw for t in result.n1.trees.values()))
    dash = build_dashboard(net=net, topo=topo, placement=result)
    assert len(dash["zones"]) == len(snap["zone_register"])
    for feeder in dash["feeders"]:
        if feeder["feeder_key"] in result.n1.trees:
            assert feeder["total_load_kw"] == pytest.approx(
                result.n1.trees[feeder["feeder_key"]].total_load_kw)
            assert abs(feeder["load_delta_kw"]) <= 0.1


def test_zone_register_survives_placement_store_roundtrip(topo_two_feeders, tmp_path):
    from switchloc.placement.service import EngineSettings, PlacementEngine
    from switchloc.reliability.load_model import LoadModelSettings, LEVEL_SUBSTITUTE
    from switchloc.persistence.store import ProjectStore
    from switchloc.reporting.service import ReportService
    net, topo = topo_two_feeders
    result = PlacementEngine(EngineSettings(
        load_model=LoadModelSettings(level=LEVEL_SUBSTITUTE))).run(
            topo.graph, net, topo.traces, topo.zones, topo.ties,
            traces_strict=topo.traces_strict)
    db = tmp_path / "zone-register.sqlite"
    store = ProjectStore(str(db))
    run_id = store.save_placement(result.to_dict(), result.settings,
                                  user="test", algo_version="1.10.0")
    saved = store.load_placement(run_id)
    store.close()
    assert saved["summary"]["zone_register"] == result.to_dict()["zone_register"]
    check = ReportService._crosscheck(str(db), result)
    assert check["status"] == "match"
    assert check["checks"]["feeder_loads"] is True
    assert check["checks"]["zone_counts"] is True
    assert check["checks"]["zone_register"] is True



def test_report_zone_section_uses_real_n1_zone_tree():
    from switchloc.reporting.model import StudyModel
    from switchloc.reporting.content import build_report
    from switchloc.application.topology_service import TopologyService, TopologySettings
    from switchloc.placement.service import PlacementEngine, EngineSettings
    from switchloc.reliability.load_model import LoadModelSettings, LEVEL_SUBSTITUTE
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (500, 0), (1000, 0)], feeder="F1")
    b.transformer(1000, 0)
    net = b.net
    topo = TopologyService(TopologySettings(user="report-test", persist=False)).run(net)
    placement = PlacementEngine(EngineSettings(
        load_model=LoadModelSettings(level=LEVEL_SUBSTITUTE))).run(
            topo.graph, net, topo.traces, topo.zones, topo.ties,
            traces_strict=topo.traces_strict)
    model = StudyModel(net=net, topo=topo, placement=placement)
    report = build_report(model)
    section = next(s for s in report.sections if s.id == "zones")
    assert section.tables and section.tables[0].rows
    assert section.tables[0].rows[0][4].endswith("m")
    assert sum(z["load_kw"] for z in model.zone_rows()) == pytest.approx(
        sum(t.total_load_kw for t in placement.n1.trees.values()))



def test_zone_length_display_switches_at_one_kilometre():
    from switchloc.ui.dashboard_data import _length_label
    assert _length_label(999.9).endswith("m")
    assert _length_label(1000.0).endswith("km")
