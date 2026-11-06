# -*- coding: utf-8 -*-
"""Phase-4 unit tests — golden rule (روابط ۹/۱۰) + schemes (جدول ۱۷) +
ENS/CE-CN economics (رابطه ۸ + جدول ۱۸)."""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from switchloc.domain.enums import NodeKind                        # noqa: E402
from switchloc.domain.entities import Transformer                  # noqa: E402
from switchloc.placement.economics import (                        # noqa: E402
    CostModel, SegTree, build_seg_tree, compare_schemes,
    ens_of_configuration)
from switchloc.placement.golden import (                           # noqa: E402
    GoldenSettings, build_feeder_tree, feeder_trunk, golden_section,
    segment_stats, up_deviation)
from switchloc.placement.schemes import (                          # noqa: E402
    PlacementSettings, generate_schemes)
from switchloc.topology.graph import GraphEdge, GraphNode, NetworkGraph  # noqa
from switchloc.topology.tracing import FeederTrace                 # noqa: E402

from tests.unit.test_n_minus_1 import make_tie                     # noqa: E402


def chain_feeder(n_edges=8, edge_len=100.0, load_at=None, key="FA",
                 load_value=100.0):
    """Trunk n0→n{n}; optional load (transformer) at given node ids."""
    g = NetworkGraph()
    for i in range(n_edges + 1):
        g.nodes[f"n{i}"] = GraphNode(id=f"n{i}", kind=NodeKind.JUNCTION,
                                     coord=(i * edge_len, 0.0),
                                     feeder_hint="")
    for i in range(n_edges):
        eid = f"e{i}"
        g.edges[eid] = GraphEdge(id=eid, branch_id="b", seq=i, a=f"n{i}",
                                 b=f"n{i + 1}", length_m=edge_len,
                                 kind="overhead", feeder_hint="")
        g.adj[f"n{i}"].append((f"n{i + 1}", eid))
        g.adj[f"n{i + 1}"].append((f"n{i}", eid))
    load_at = load_at or {f"n{i}": load_value for i in range(n_edges + 1)}
    transformers = []
    for nid, cap in load_at.items():
        tid = f"t_{nid}"
        transformers.append(Transformer(node_id=nid, capacity_kva=cap, id=tid))
        g.transformer_ids_at[nid].append(tid)
    net = type("N", (), {"transformers": transformers, "switches": [],
                         "loads": []})()
    trace = FeederTrace(feeder="F", feeder_key=key, source_node="n0",
                        nodes=set(g.nodes), edges=set(g.edges))
    return g, net, trace


# ---------------------------------------------------------------------------
# golden rule
# ---------------------------------------------------------------------------
def test_uniform_feeder_gets_equal_up_segments():
    """رابطه (۹): exactly divisible feeder → equal segments, deviation 0.

    Loads hang at the odd nodes n1/n3/n5 (100 kW each) so every 2-edge
    segment carries exactly 100 kW regardless of the boundary-node
    convention — the golden split is unique and exact.
    """
    loads = {f"n{i}": 0.0 for i in range(7)}
    loads.update({"n1": 100.0, "n3": 100.0, "n5": 100.0})
    g, net, trace = chain_feeder(n_edges=6, load_at=loads)
    gs = golden_section(g, trace, set(g.edges), loads,
                        lam_per_year=10.0, r_minutes=60.0,
                        existing_cut_nodes=set(),
                        settings=GoldenSettings(target_zones=3))
    assert gs is not None
    assert set(gs.cut_nodes) == {"n2", "n4"}
    assert gs.deviation < 1e-9
    lens = [round(s["length_m"], 6) for s in gs.segments]
    lds = [round(s["load_kw"], 6) for s in gs.segments]
    assert lens == [200.0, 200.0, 200.0]
    assert lds == [100.0, 100.0, 100.0]


def test_concentrated_load_is_optimal():
    """The chosen split achieves the minimum U×P deviation over ALL
    candidate combinations (property test), on a feeder with two load
    centres where the objective actually discriminates."""
    from itertools import combinations
    loads = {f"n{i}": 0.0 for i in range(9)}
    loads["n2"] = 300.0
    loads["n8"] = 600.0
    g, net, trace = chain_feeder(n_edges=8, load_at=loads)
    st = GoldenSettings(target_zones=3)
    gs = golden_section(g, trace, set(g.edges), loads,
                        lam_per_year=10.0, r_minutes=60.0,
                        existing_cut_nodes=set(), settings=st)
    assert gs is not None
    # brute-force the same candidate space and compare
    t = build_feeder_tree(g, trace, set(g.edges), loads)
    cands = [n for n in gs.trunk[1:-1]]
    best = min(up_deviation(segment_stats(t, [cands[i] for i in combo]))
               for combo in combinations(range(len(cands)), 2))
    assert gs.deviation == best
    assert best < up_deviation(segment_stats(t, ["n3", "n6"]))  # beats naive


def test_segment_stats_subtraction():
    g, _net, trace = chain_feeder(n_edges=4, load_value=0.0)
    t = build_feeder_tree(g, trace, set(g.edges), {n: 0.0 for n in g.nodes})
    segs = segment_stats(t, ["n2"])
    assert segs[0]["length_m"] == 200.0 and segs[1]["length_m"] == 200.0
    assert up_deviation(segs) == 0.0


def test_trunk_is_longest_path():
    g, _net, trace = chain_feeder(n_edges=6)
    assert feeder_trunk(g, trace, set(g.edges))[0] == "n0"
    assert feeder_trunk(g, trace, set(g.edges))[-1] == "n6"


# ---------------------------------------------------------------------------
# ENS accounting (رابطه ۸ + transfer)
# ---------------------------------------------------------------------------
def _two_seg_tree(load1=500.0, load2=500.0, len1=100.0, len2=100.0):
    segs = SegTree(
        seg_load={"S1": load1, "S2": load2},
        seg_len={"S1": len1, "S2": len2},
        parent={"S1": None, "S2": "S1"},
        children={"S1": ["S2"], "S2": []},
        root="S1", node_seg={}, node_seg_below={})
    return segs


def test_ens_no_transfer_matches_hand_calculation():
    """λ=10/yr split by length, r=60 min → ENS = Σ λ_i × r/60 × shed."""
    segs = _two_seg_tree()
    ens, rows = ens_of_configuration(segs, lam_per_year=10.0, r_minutes=60.0,
                                     switching_minutes=10.0,
                                     transfer_cap_by_seg={})
    # fault S1: λ=5, shed 1000 → 5×(60/60)×1000 = 5000
    # fault S2: λ=5, shed  500 → 5×(60/60)× 500 = 2500  → total 7500
    assert ens == 7500.0
    assert len(rows) == 2


def test_ens_with_tie_transfer_improves():
    segs = _two_seg_tree()
    ens0, _ = ens_of_configuration(segs, 10.0, 60.0, 10.0, {})
    ens1, _ = ens_of_configuration(segs, 10.0, 60.0, 10.0,
                                   {"S2": float("inf")})
    # fault S1 restores S2 (500 kW) after 10 min switching:
    # 5×(60×500 + 10×500)/60 = 2916.67; fault S2 unchanged → 2500
    assert ens1 == 2916.6666666666665 + 2500.0
    assert ens1 < ens0


def test_ens_capacity_capped_transfer():
    segs = _two_seg_tree()
    ens, _ = ens_of_configuration(segs, 10.0, 60.0, 10.0, {"S2": 200.0})
    # fault S1: restored 200 → shed 800 → 5×(60×800 + 10×200)/60 = 4166.67
    assert ens == 4166.666666666666 + 2500.0


# ---------------------------------------------------------------------------
# schemes (جدول ۱۷) + جدول ۱۸ comparison
# ---------------------------------------------------------------------------
def _two_feeders_with_tie(rated=None):
    from switchloc.level1.n_minus_1 import ZoneTree
    g1, net1, tr1 = chain_feeder(n_edges=6, key="FA")
    g = g1
    for i in range(7):                    # second feeder nodes/edges
        g.nodes[f"m{i}"] = GraphNode(id=f"m{i}", kind=NodeKind.JUNCTION,
                                     coord=(i * 100.0, 1000.0),
                                     feeder_hint="")
    for i in range(6):
        eid = f"f{i}"
        g.edges[eid] = GraphEdge(id=eid, branch_id="fb", seq=i, a=f"m{i}",
                                 b=f"m{i + 1}", length_m=100.0,
                                 kind="overhead", feeder_hint="")
        g.adj[f"m{i}"].append((f"m{i + 1}", eid))
        g.adj[f"m{i + 1}"].append((f"m{i}", eid))
    tr2 = FeederTrace(feeder="FB", feeder_key="FB", source_node="m0",
                      nodes={f"m{i}" for i in range(7)},
                      edges={f"f{i}" for i in range(6)})
    net = type("N", (), {"transformers": [
        Transformer(node_id="n6", capacity_kva=900.0, id="ta"),
        Transformer(node_id="m6", capacity_kva=900.0, id="tb")],
        "switches": [], "loads": []})()
    g.transformer_ids_at["n6"].append("ta")
    g.transformer_ids_at["m6"].append("tb")
    ties = [make_tie("T1", "FA", "FB", "n3", automation=True)]
    traces = [tr1, tr2]

    def _zone(zid, feeder, nodes, edges, trafos):
        return SwitchZoneStub(zid, feeder, nodes, edges, trafos, 900.0)

    zfa = _zone("FAZ0", "FA", {"n0"}, {"e0"}, ("ta",))
    zfb = _zone("FBZ0", "FB", {"m0"}, {"f0"}, ("tb",))
    trees = {
        "FA": ZoneTree(feeder_key="FA", zones=[zfa],
                       load_kw={"FAZ0": 900.0}, parent={"FAZ0": None},
                       children={"FAZ0": []}, head_zone="FAZ0",
                       total_load_kw=900.0),
        "FB": ZoneTree(feeder_key="FB", zones=[zfb],
                       load_kw={"FBZ0": 900.0}, parent={"FBZ0": None},
                       children={"FBZ0": []}, head_zone="FBZ0",
                       total_load_kw=900.0),
    }
    zones_by_feeder = {"FA": [zfa], "FB": [zfb]}
    edge_set_of = {"FA": set(g1.edges),
                   "FB": {f"f{i}" for i in range(6)}}
    return g, net, traces, trees, zones_by_feeder, edge_set_of, ties


class SwitchZoneStub:
    def __init__(self, zid, feeder, nodes, edges, trafos, load):
        self.id, self.feeder, self.nodes, self.edges = zid, feeder, nodes, edges
        self.transformer_ids = set(trafos)
        self.load = load
        self.zone_no = 0
        self.kind = "head"


def test_one_half_switch_scheme_generated():
    g, net, traces, trees, zones_by_feeder, edge_set_of, ties = \
        _two_feeders_with_tie()
    st = PlacementSettings(max_feeders=0, max_tie_schemes=5)
    schemes, golden_of, issues = generate_schemes(
        g, net, traces, trees, ranking_rows=[], ties=ties,
        zone_no_of={("FA", "n3"): 0, ("FB", "n3"): 0},
        load_kw_at={n: 0.0 for n in g.nodes},
        lam_of={}, r_of={},
        cut_nodes_of={"FA": set(), "FB": set()},
        edge_set_of=edge_set_of, settings=st)
    kinds = [s.kind for s in schemes]
    assert "one_half_switch" in kinds
    sch = next(s for s in schemes if s.kind == "one_half_switch")
    assert set(sch.feeders) == {"FA", "FB"}
    assert len(sch.switches) == 3                 # NO + 2 end NC
    assert sum(1 for s in sch.switches if s.kind == "NO") == 1


def test_one_half_rejected_when_two_thirds_rule_violated():
    """رابطه (۱۱): both feeders must be ≤ 2/3 emergency loading."""
    g, net, traces, trees, zones_by_feeder, edge_set_of, ties = \
        _two_feeders_with_tie(rated={"FA": 1000.0, "FB": 1000.0})
    st = PlacementSettings(max_feeders=0, max_tie_schemes=5,
                           feeder_rated_kw={"FA": 1000.0, "FB": 1000.0})
    schemes, _g, issues = generate_schemes(
        g, net, traces, trees, ranking_rows=[], ties=ties,
        zone_no_of={}, load_kw_at={n: 0.0 for n in g.nodes},
        lam_of={}, r_of={},
        cut_nodes_of={"FA": set(), "FB": set()},
        edge_set_of=edge_set_of, settings=st)
    assert not [s for s in schemes if s.kind == "one_half_switch"]
    assert any(c == "PLAC-15-CAPACITY" for c, _s, _m in issues)


def test_compare_selects_max_ce_over_cn():
    """A-01: the selection direction is MAXIMIZE CE/CN (official text)."""
    from switchloc.placement.schemes import ProposedSwitch, SwitchScheme
    s1 = SwitchScheme(id="A", kind="sequential_nc", feeders=["FA"],
                      switches=[ProposedSwitch("x", "FA", "NC")],
                      relations=[])
    s2 = SwitchScheme(id="B", kind="one_half_switch", feeders=["FA"],
                      switches=[ProposedSwitch("x", "FA", "NC"),
                                ProposedSwitch("y", "FA", "NC"),
                                ProposedSwitch("z", "FA", "NO")],
                      relations=[])
    ens_before = {"FA": 1000.0}
    # A saves 500 kWh, B saves 800 kWh; A has 1 NC, B has 3 switches
    after = {"A": {"FA": 500.0}, "B": {"FA": 200.0}}
    rows = compare_schemes([s1, s2], ens_before, after, CostModel())
    sel = [r.scheme_id for r in rows if r.selected]
    assert sel == ["A"]          # A: 500k/2e9 > B: 800k/6e9 → bigger ratio
    for r in rows:
        assert r.ce_rials > 0    # benefit positive for improving schemes
