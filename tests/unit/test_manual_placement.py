# -*- coding: utf-8 -*-
"""Tests for the manual switch placement evaluator (روش جایابی دستی).

Covers: UTM point snapping (`nearest_node`), the before/after level-1
indicators (ENS via رابطه ۸ accounting, EP/TL per segment), the
improvement verdict, the refusal of foreign nodes and the no-effect
case for nodes that are already zone cuts.
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest                                          # noqa: E402

from switchloc.domain.entities import Transformer       # noqa: E402
from switchloc.domain.enums import NodeKind             # noqa: E402
from switchloc.level1.formulas import ce_cn             # noqa: E402
from switchloc.manual_placement import (                # noqa: E402
    evaluate_manual_placement, nearest_node)
from switchloc.reliability.lambdar import FeederLambdaR  # noqa: E402
from switchloc.reliability.load_model import (           # noqa: E402
    LoadModelSettings, LEVEL_SUBSTITUTE)
from switchloc.topology.graph import GraphEdge, GraphNode, NetworkGraph  # noqa
from switchloc.topology.tracing import FeederTrace       # noqa: E402
from switchloc.topology.zones import SwitchZone, ZoneResult  # noqa: E402


def _one_zone_feeder(n_edges=5, edge_len=100.0, load=500.0):
    """Chain n0→n{n}; ONE head zone (no existing cuts); loads at n1..n{n}."""
    g = NetworkGraph()
    for i in range(n_edges + 1):
        g.nodes[f"n{i}"] = GraphNode(id=f"n{i}", kind=NodeKind.JUNCTION,
                                     coord=(i * edge_len, 0.0),
                                     feeder_hint="")
    transformers = []
    edges = set()
    for i in range(n_edges):
        eid = f"e{i}"
        edges.add(eid)
        g.edges[eid] = GraphEdge(id=eid, branch_id="b", seq=i, a=f"n{i}",
                                 b=f"n{i + 1}", length_m=edge_len,
                                 kind="overhead", feeder_hint="")
        g.adj[f"n{i}"].append((f"n{i + 1}", eid))
        g.adj[f"n{i + 1}"].append((f"n{i}", eid))
        tid = f"t{i}"
        transformers.append(Transformer(node_id=f"n{i + 1}",
                                        capacity_kva=load, id=tid))
        g.transformer_ids_at[f"n{i + 1}"].append(tid)
    net = type("N", (), {"transformers": transformers, "switches": [],
                         "loads": []})()
    all_nodes = {f"n{i}" for i in range(n_edges + 1)}
    trace = FeederTrace(feeder="Feeder A", feeder_key="FA",
                        source_node="n0", nodes=set(all_nodes), edges=edges)
    zone = SwitchZone(id="Z0", feeder="FA", zone_no=0, kind="head",
                      source_node="n0", nodes=set(all_nodes), edges=edges,
                      transformer_ids={t.id for t in transformers})
    zres = ZoneResult(zones=[zone], zone_of_edge={e: "Z0" for e in edges},
                      zone_of_node={n: "Z0" for n in all_nodes},
                      boundaries=[])
    lam = [FeederLambdaR(feeder_key="FA", lambda_per_year=2.0,
                         r_minutes=60.0)]
    return g, net, trace, zres, lam


def test_nearest_node_snaps_and_restricts():
    g, _net, _trace, _zres, _lam = _one_zone_feeder()
    # click exactly at 210 m on the line → n2 (x=200) is 10 m away
    nid, d = nearest_node(g, 210.0, 0.0)
    assert nid == "n2" and d == pytest.approx(10.0)
    nid, d = nearest_node(g, 210.0, 0.0, restrict_to={"n0", "n4"})
    assert nid == "n4"
    nid, d = nearest_node(g, 210.0, 5.0, max_dist_m=5.0)
    assert nid is None and d == float("inf")


def test_manual_switch_mid_feeder_reduces_ens():
    """A new NC switch at n3 splits the trunk: faults beyond it shed only
    the downstream load → ENS must drop (رابطه ۸ accounting)."""
    g, net, trace, zres, lam = _one_zone_feeder()
    # n3 is a junction on the feeder conductor, not a transformer terminal.
    g.transformer_ids_at.pop("n3", None)
    from switchloc.placement.service import EngineSettings
    from switchloc.reliability.load_model import LoadModelSettings, LEVEL_SUBSTITUTE
    ev = evaluate_manual_placement(
        g, net, [trace], zres, ties=[], feeder_key="FA",
        switch_nodes=["n3"], lam_matrix=lam,
        settings=EngineSettings(load_model=LoadModelSettings(level=LEVEL_SUBSTITUTE)))
    # Hand-computed with n3 a true line junction (not a transformer terminal):
    # λ=2/yr, r=60min, L=500m, load=2000kW; switch at n3 splits
    # 300m/1000kW + 200m/1000kW. Faults in the upstream segment
    # still interrupt downstream load; the split lowers ENS 4000 -> 3200.
    assert ev.before["ens_kwh"] == pytest.approx(4000.0, abs=0.5)
    assert ev.after["ens_kwh"] == pytest.approx(3200.0, abs=0.5)
    assert ev.delta["ens_kwh"] == pytest.approx(800.0, abs=0.5)
    assert ev.better is True
    assert "بهبود" in ev.verdict_fa
    assert ev.after["segments"] == ev.before["segments"] + 1
    assert ev.after_zones is not None
    assert len(ev.after_zones.zones_of_feeder("FA")) == 2
    # جدول ۱۸ algebra for the manual switches (cost = 1 × NC default)
    cc = ce_cn(e1_kwh=ev.before["ens_kwh"], e2_kwh=ev.after["ens_kwh"],
               cost_rials=2_000_000_000.0)
    assert ev.ce_cn["ce_rials"] == pytest.approx(cc["ce_rials"])
    assert ev.ce_cn["ce_over_cn"] > 0


def test_manual_switch_on_already_cut_node_has_no_effect():
    """A node that is already a zone cut changes nothing — explicit
    warning, ΔENS = 0, verdict «بدون تغییر»."""
    g, net, trace, zres, lam = _one_zone_feeder()
    # split into two zones sharing node n3 → n3 is an existing cut
    edges = set(zres.zones[0].edges)
    z1 = SwitchZone(id="Z1", feeder="FA", zone_no=0, kind="head",
                    source_node="n0", nodes={"n0", "n1", "n2", "n3"},
                    edges={"e0", "e1", "e2"}, transformer_ids=set())
    z2 = SwitchZone(id="Z2", feeder="FA", zone_no=1, kind="section",
                    source_node=None, nodes={"n3", "n4", "n5"},
                    edges={"e3", "e4"},
                    transformer_ids={f"t{i}" for i in (3, 4)})
    zres2 = ZoneResult(zones=[z1, z2],
                       zone_of_edge={"e0": "Z1", "e1": "Z1", "e2": "Z1",
                                     "e3": "Z2", "e4": "Z2"},
                       zone_of_node={f"n{i}": ("Z1" if i <= 3 else "Z2")
                                     for i in range(6)},
                       boundaries=[])
    ev = evaluate_manual_placement(g, net, [trace], zres2, ties=[],
                                   feeder_key="FA", switch_nodes=["n3"],
                                   lam_matrix=lam)
    codes = {i[0] for i in ev.issues}
    assert "MANUAL-NODE-ALREADY-CUT" in codes
    assert ev.delta["ens_kwh"] == 0.0
    assert ev.better is False
    assert "بدون تغییر" in ev.verdict_fa


def test_manual_switch_on_foreign_node_is_refused():
    g, net, trace, zres, lam = _one_zone_feeder()
    ev = evaluate_manual_placement(g, net, [trace], zres, ties=[],
                                   feeder_key="FA",
                                   switch_nodes=["nx"], lam_matrix=lam)
    codes = {i[0] for i in ev.issues}
    assert "MANUAL-NODE-NOT-ON-FEEDER" in codes
    assert ev.before == {} and ev.after == {}


def test_manual_empty_selection_and_unknown_feeder():
    g, net, trace, zres, lam = _one_zone_feeder()
    ev = evaluate_manual_placement(g, net, [trace], zres, ties=[],
                                   feeder_key="FA", switch_nodes=[],
                                   lam_matrix=lam)
    assert "MANUAL-NO-NODE" in {i[0] for i in ev.issues}
    ev = evaluate_manual_placement(g, net, [trace], zres, ties=[],
                                   feeder_key="NOPE", switch_nodes=["n1"],
                                   lam_matrix=lam)
    assert "MANUAL-FEEDER-UNKNOWN" in {i[0] for i in ev.issues}


def test_as_dict_is_json_safe():
    import json
    g, net, trace, zres, lam = _one_zone_feeder()
    g.transformer_ids_at.pop("n3", None)
    from switchloc.placement.service import EngineSettings
    from switchloc.reliability.load_model import LoadModelSettings, LEVEL_SUBSTITUTE
    ev = evaluate_manual_placement(g, net, [trace], zres, ties=[],
                                   feeder_key="FA", switch_nodes=["n3"],
                                   lam_matrix=lam,
                                   settings=EngineSettings(load_model=LoadModelSettings(level=LEVEL_SUBSTITUTE)))
    d = ev.as_dict()
    json.dumps(d, ensure_ascii=False, allow_nan=False)   # must not raise
    assert d["feeder_key"] == "FA" and d["better"] is True


def test_manual_placement_refuses_transformer_terminal_and_missing_inputs():
    g, net, trace, zres, lam = _one_zone_feeder()
    # n3 still hosts a transformer terminal in this fixture.
    ev = evaluate_manual_placement(g, net, [trace], zres, ties=[],
                                   feeder_key="FA", switch_nodes=["n3"],
                                   lam_matrix=lam)
    assert ev.before == {} and ev.after == {}
    assert "MANUAL-TRANSFORMER-TERMINAL-DEVICE" in {i[0] for i in ev.issues}

    g.transformer_ids_at.pop("n3", None)
    ev2 = evaluate_manual_placement(g, net, [trace], zres, ties=[],
                                    feeder_key="FA", switch_nodes=["n3"],
                                    lam_matrix=[])
    assert ev2.before == {} and ev2.after == {}
    assert "MANUAL-RELIABILITY-INPUT-MISSING" in {i[0] for i in ev2.issues}

    from switchloc.reliability.load_model import LoadModelSettings, LEVEL_SCALED
    from switchloc.placement.service import EngineSettings
    ev3 = evaluate_manual_placement(
        g, net, [trace], zres, ties=[], feeder_key="FA", switch_nodes=["n3"],
        lam_matrix=lam,
        settings=EngineSettings(load_model=LoadModelSettings(level=LEVEL_SCALED)))
    assert ev3.before == {} and ev3.after == {}
    assert "MANUAL-LOAD-MISSING" in {i[0] for i in ev3.issues}


def test_manual_two_point_interfeeder_tie_requires_capacity_and_rebuilds_both_feeders():
    from copy import deepcopy
    from switchloc.manual_placement import evaluate_manual_interfeeder_tie
    from switchloc.domain.entities import Transformer
    from switchloc.placement.capacity import FeederCapacity
    from switchloc.placement.service import EngineSettings

    g, net, ta, za, la = _one_zone_feeder()
    # Endpoints must be line junctions, not direct transformer terminals.
    g.transformer_ids_at.pop("n3", None)
    for i in range(6):
        old, new = f"n{i}", f"b{i}"
        nd = deepcopy(g.nodes[old]); nd.id = new
        nd.coord = (nd.coord[0], nd.coord[1] + 1000.0)
        g.nodes[new] = nd
    for i in range(5):
        old, new = f"e{i}", f"be{i}"
        edge = deepcopy(g.edges[old]); edge.id = new
        edge.a, edge.b = f"b{i}", f"b{i+1}"
        g.edges[new] = edge
        g.adj[f"b{i}"].append((f"b{i+1}", new))
        g.adj[f"b{i+1}"].append((f"b{i}", new))
    for i in range(6):
        if f"n{i}" in g.transformer_ids_at:
            g.transformer_ids_at[f"b{i}"] = [x + "b" for x in g.transformer_ids_at[f"n{i}"]]
    for t in list(net.transformers):
        if t.node_id != "n3":
            net.transformers.append(Transformer(node_id="b" + t.node_id[1:],
                                                capacity_kva=t.capacity_kva,
                                                feeder_name="FB", id=t.id + "b"))
    tb = FeederTrace(feeder="Feeder B", feeder_key="FB", source_node="b0",
                     nodes={f"b{i}" for i in range(6)},
                     edges={f"be{i}" for i in range(5)})
    zb = SwitchZone(id="ZB", feeder="FB", zone_no=0, kind="head",
                    source_node="b0", nodes={f"b{i}" for i in range(6)},
                    edges={f"be{i}" for i in range(5)})
    zones = ZoneResult(zones=list(za.zones) + [zb],
                       zone_of_edge={**za.zone_of_edge,
                                     **{f"be{i}": "ZB" for i in range(5)}},
                       zone_of_node={**za.zone_of_node,
                                     **{f"b{i}": "ZB" for i in range(6)}})
    traces = [ta, tb]
    lam = la + [FeederLambdaR(feeder_key="FB", lambda_per_year=2.0,
                              r_minutes=60.0)]
    settings = __import__("switchloc.placement.service", fromlist=["EngineSettings"]).EngineSettings(
        load_model=LoadModelSettings(level=LEVEL_SUBSTITUTE))
    no_cap, issues = evaluate_manual_interfeeder_tie(
        g, net, traces, zones, [], "FA", "n3", "FB", "b3",
        lam_matrix=lam, settings=settings, automation_capable=True)
    assert no_cap == {}
    assert "MANUAL-TIE-CAPACITY-MISSING" in {i[0] for i in issues}

    capacities = {k: FeederCapacity(feeder_key=k, nominal_kw=10000,
                                    peak_kw=1000) for k in ("FA", "FB")}
    results, issues = evaluate_manual_interfeeder_tie(
        g, net, traces, zones, [], "FA", "n3", "FB", "b3",
        lam_matrix=lam, settings=settings, cap_map=capacities,
        automation_capable=True)
    assert set(results) == {"FA", "FB"}
    assert all(v.after_zones is not None and
               len(v.after_zones.zones_of_feeder(v.feeder_key)) == 2
               for v in results.values())
    assert all(v.after["ens_kwh"] < v.before["ens_kwh"]
               for v in results.values())
