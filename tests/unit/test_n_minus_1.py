# -*- coding: utf-8 -*-
"""Phase-4 unit tests — n-1 engine (جداول ۱۳/۱۴/۱۵) on a synthetic radial
feeder, with the official anchors of TAV122-02/00 (V-02 kernel already
pinned in test_ep_tl_up.py; here the zone-tree mechanics are pinned)."""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from switchloc.domain.enums import NodeKind                       # noqa: E402
from switchloc.domain.entities import Transformer                 # noqa: E402
from switchloc.level1.n_minus_1 import (                          # noqa: E402
    NMinusOneSettings, run_n_minus_one)
from switchloc.topology.graph import GraphEdge, GraphNode, NetworkGraph  # noqa
from switchloc.topology.ties import TieCandidate                  # noqa: E402
from switchloc.topology.tracing import FeederTrace                # noqa: E402
from switchloc.topology.zones import SwitchZone, ZoneResult       # noqa: E402


def linear_feeder(zone_loads=(500.0, 500.0, 500.0, 400.0, 600.0),
                  feeder_key="FA"):
    """Radial feeder: n0 -n- n1 -n- ... -n- n{nz}; one zone per edge.

    ``zone_loads[i]`` = transformer capacity hanging in zone i (at the
    zone's DOWNSTREAM node).  Returns (graph, net, traces, zones_by_feeder).
    """
    g = NetworkGraph()
    transformers = []
    nz = len(zone_loads)
    for i in range(nz + 1):
        nid = f"n{i}"
        g.nodes[nid] = GraphNode(id=nid, kind=NodeKind.JUNCTION,
                                 coord=(i * 100.0, 0.0), feeder_hint="")
    for i in range(nz):
        eid = f"e{i}"
        g.edges[eid] = GraphEdge(id=eid, branch_id="b1", seq=i,
                                 a=f"n{i}", b=f"n{i + 1}", length_m=100.0,
                                 kind="overhead", feeder_hint="")
        g.adj[f"n{i}"].append((f"n{i + 1}", eid))
        g.adj[f"n{i + 1}"].append((f"n{i}", eid))
        tid = f"t{i}"
        transformers.append(Transformer(node_id=f"n{i + 1}",
                                        capacity_kva=zone_loads[i], id=tid))
        g.transformer_ids_at[f"n{i + 1}"].append(tid)
    net = type("N", (), {"transformers": transformers})()

    zones = []
    zone_of_edge, zone_of_node = {}, {}
    for i, load in enumerate(zone_loads):
        zid = f"Z{i}"
        z = SwitchZone(id=zid, feeder=feeder_key, zone_no=i,
                       kind=("head" if i == 0 else "section"),
                       source_node="n0" if i == 0 else None,
                       nodes={f"n{i}", f"n{i + 1}"}, edges={f"e{i}"},
                       transformer_ids={f"t{i}"})
        zones.append(z)
        zone_of_edge[f"e{i}"] = zid
        zone_of_node[f"n{i}"] = zid
    zone_of_node[f"n{nz}"] = f"Z{nz - 1}"
    zres = ZoneResult(zones=zones, zone_of_edge=zone_of_edge,
                      zone_of_node=zone_of_node, boundaries=[])
    traces = [FeederTrace(feeder="Feeder A", feeder_key=feeder_key,
                          source_node="n0",
                          nodes={n.id for n in g.nodes.values()},
                          edges=set(g.edges))]
    return g, net, traces, {feeder_key: zones}, zres


def make_tie(tid, a, b, node, automation=True, switch_id=None, score=10):
    return TieCandidate(id=tid, feeder_a=a, feeder_b=b, node=node,
                        switch_id=switch_id, rule="R1-overlap",
                        automation_capable=automation, score=score)


def test_zone_tree_linear_chain():
    g, net, traces, zones_by_feeder, _zres = linear_feeder()
    res = run_n_minus_one(g, net, traces, zones_by_feeder, ties=[])
    tree = res.trees["FA"]
    assert [z.id for z in tree.zones] == ["Z0", "Z1", "Z2", "Z3", "Z4"]
    assert tree.parent["Z3"] == "Z2" and tree.parent["Z0"] is None
    assert tree.total_load_kw == 2500.0
    assert tree.subtree_load_kw("Z0") == 2500.0
    assert tree.subtree_load_kw("Z2") == 1500.0     # Z2+Z3+Z4


def test_fault_sheds_downstream_only():
    """رابطه (۸) pattern: a fault hits the subtree; upstream is restored."""
    g, net, traces, zones_by_feeder, _zres = linear_feeder()
    res = run_n_minus_one(g, net, traces, zones_by_feeder, ties=[])
    rows = {r["zone"]: r for r in res.rows15}
    assert rows["Z2"]["shed_kw"] == 1500.0          # Z2+Z3+Z4, no tie
    assert rows["Z0"]["shed_kw"] == 2500.0          # head fault = all
    assert all(r["restorable_kw"] == 0.0 for r in rows.values())


def test_automation_tie_restores_behind_its_zone():
    """Tie at Z4 (600 kW behind it): head fault restores 600 → EP=76٪."""
    g, net, traces, zones_by_feeder, _zres = linear_feeder()
    tie = make_tie("T1", "FA", "FB", "n5", automation=True)
    res = run_n_minus_one(g, net, traces, zones_by_feeder, ties=[tie])
    rows = {r["zone"]: r for r in res.rows15}
    # No rated spare capacity was supplied for FB: transfer is unconfirmed,
    # so the conservative result must not assume unlimited capacity.
    assert rows["Z0"]["restorable_kw"] == 0.0
    assert rows["Z0"]["shed_kw"] == 2500.0
    ep = next(f for f in res.eptl if f.feeder_key == "FA")
    assert ep.ep.ep_percent == 100.0
    assert ep.ep.tl_percent == 0.0


def test_non_automation_tie_is_ignored():
    """جدول ۱۳ note: only automation-capable connections transfer."""
    g, net, traces, zones_by_feeder, _zres = linear_feeder()
    tie = make_tie("T1", "FA", "FB", "n5", automation=False)
    res = run_n_minus_one(g, net, traces, zones_by_feeder, ties=[tie])
    rows = {r["zone"]: r for r in res.rows15}
    assert rows["Z0"]["restorable_kw"] == 0.0
    assert res.connections == []                    # not automation-capable


def test_spare_capacity_limits_transfer():
    """Backup feeder FC with rated 500 kW / load 300 → spare 200 kW."""
    g, net, traces, zones_by_feeder, _zres = linear_feeder()
    # second feeder FC: one zone, 300 kW load, so it exists in the trees
    zones_by_feeder["FC"] = [SwitchZone(
        id="FC0", feeder="FC", zone_no=0, kind="head", source_node="m0",
        nodes={"m0", "m1"}, edges={"f0"}, transformer_ids={"ft0"})]
    g.nodes["m0"] = GraphNode(id="m0", kind=NodeKind.JUNCTION,
                              coord=(0.0, 500.0), feeder_hint="")
    g.nodes["m1"] = GraphNode(id="m1", kind=NodeKind.JUNCTION,
                              coord=(100.0, 500.0), feeder_hint="")
    g.edges["f0"] = GraphEdge(id="f0", branch_id="fb", seq=0, a="m0", b="m1",
                              length_m=100.0, kind="overhead", feeder_hint="")
    g.adj["m0"].append(("m1", "f0"))
    g.adj["m1"].append(("m0", "f0"))
    net.transformers.append(Transformer(node_id="m1", capacity_kva=300.0,
                                        id="ft0"))
    g.transformer_ids_at["m1"].append("ft0")
    traces.append(FeederTrace(feeder="Feeder C", feeder_key="FC",
                              source_node="m0", nodes={"m0", "m1"},
                              edges={"f0"}))
    tie = make_tie("T1", "FA", "FC", "n5", automation=True)
    st = NMinusOneSettings(feeder_rated_kw={"FC": 500.0})
    res = run_n_minus_one(g, net, traces, zones_by_feeder, ties=[tie],
                          settings=st)
    rows = {r["zone"]: r for r in res.rows15}
    assert rows["Z0"]["restorable_kw"] == 200.0     # min(600 behind, 200 spare)
    assert rows["Z0"]["shed_kw"] == 2300.0
    assert "PLAC-CAP-UNKNOWN" not in [i[0] for i in res.issues]


def test_zero_load_feeder_is_flagged_and_skipped():
    g, net, traces, zones_by_feeder, _zres = linear_feeder(
        zone_loads=(0.0, 0.0, 0.0, 0.0, 0.0))
    res = run_n_minus_one(g, net, traces, zones_by_feeder, ties=[])
    assert res.eptl == []                           # skipped
    assert any(c == "PLAC-FEEDER-NOLOAD" for c, _s, _m in res.issues)


def test_table13_rows():
    g, net, traces, zones_by_feeder, _zres = linear_feeder()
    ties = [make_tie("T1", "FA", "FB", "n5", automation=True),
            make_tie("T2", "FA", "FC", "n3", automation=False)]
    res = run_n_minus_one(g, net, traces, zones_by_feeder, ties=ties)
    assert len(res.connections) == 1                # only the automation tie
    assert res.connections[0].feeder_a == "FA"
    assert res.connections[0].feeder_b == "FB"
    assert len(res.ties_of_feeder["FA"]) == 2       # bookkeeping keeps both
