# -*- coding: utf-8 -*-
"""Regression tests — انتقال بار (ties) در تحلیل n-1 و ENS (v1.10.2).

قبل از v1.10.2، برای خطای زون i فقط «زیرمجموعهٔ پشت کلید Tie» قابل
بازپُل فرض می‌شد. رابطه (۸) و رابطه (۱۱) پیوست ب صراحت می‌گویند که با
جداسازی زون معیوب، تمام بار پایین‌دستِ مرز جداسازی (شاخهٔ حاوی Tie و
تمام انشعاب‌های آن تا مرز زون معیوب) قابل برقداری از سمت فیدر پشتیبان است —
نه صرفاً بارِ «پشتِ» نقطهٔ Tie. این فایل معناشناسی صحیح را پین می‌کند.

مدل جزایر (v1.10.2 — سطح اول): اعضای پایین‌دستِ عضو معیوب که گره‌های
مشترک (رسانا) دارند یک جزیره می‌سازند؛ هر جزیره مستقل تا min(بار
جزیره، Σ ظرفیت Tieهای همان جزیره) بازپُل می‌شود. گرهٔ مانع (هیچ تجهیزی
توان رد نمی‌کند — همه NO غیراتوماسیون/از مدار خارج) جزیره‌ها را جدا
می‌کند. تعمد ثبت‌شده: دو Tie از یک فیدر پشتیبانِ واحد در یک جزیره جمع
ظرفیت‌شان شمرده می‌شود؛ سقف واقعی، رزرو همان فیدر است.
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from switchloc.domain.entities import Transformer                # noqa: E402
from switchloc.domain.enums import NodeKind                      # noqa: E402
from switchloc.level1.n_minus_1 import (                         # noqa: E402
    NMinusOneSettings, build_zone_tree, run_n_minus_one,
    zone_fault_rows)
from switchloc.manual_placement import _ep_tl_of_segments         # noqa: E402
from switchloc.placement.economics import (                        # noqa: E402
    SegTree, ens_of_configuration)
from switchloc.topology.graph import GraphEdge, GraphNode, NetworkGraph  # noqa
from switchloc.topology.tracing import FeederTrace                 # noqa: E402
from switchloc.topology.zones import SwitchZone                    # noqa: E402
from switchloc.topology.ties import TieCandidate                   # noqa: E402


def linear_feeder(zone_loads=(500.0, 500.0, 500.0, 400.0, 600.0),
                  feeder_key="FA"):
    """رادیکال: n0 … n{nz}؛ یک زون به‌ازای هر یال؛ بار در گرهٔ پایین‌دست."""
    g = NetworkGraph()
    transformers = []
    nz = len(zone_loads)
    for i in range(nz + 1):
        g.nodes[f"n{i}"] = GraphNode(id=f"n{i}", kind=NodeKind.JUNCTION,
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
    for i, load in enumerate(zone_loads):
        zones.append(SwitchZone(id=f"Z{i}", feeder=feeder_key, zone_no=i,
                                kind=("head" if i == 0 else "section"),
                                source_node="n0" if i == 0 else None,
                                nodes={f"n{i}", f"n{i + 1}"}, edges={f"e{i}"},
                                transformer_ids={f"t{i}"}))
    trace = FeederTrace(feeder="Feeder A", feeder_key=feeder_key,
                        source_node="n0",
                        nodes={n.id for n in g.nodes.values()},
                        edges=set(g.edges))
    return g, net, [trace], {feeder_key: zones}


def make_tie(tid, a, b, node, automation=True):
    return TieCandidate(id=tid, feeder_a=a, feeder_b=b, node=node,
                        switch_id=None, rule="R1-overlap",
                        automation_capable=automation, score=10)


def _second_feeder(g, zones_by_feeder, key="FC", load=300.0):
    g.nodes["m0"] = GraphNode(id="m0", kind=NodeKind.JUNCTION,
                              coord=(0.0, 500.0), feeder_hint="")
    g.nodes["m1"] = GraphNode(id="m1", kind=NodeKind.JUNCTION,
                              coord=(100.0, 500.0), feeder_hint="")
    g.edges["f0"] = GraphEdge(id="f0", branch_id="fb", seq=0, a="m0", b="m1",
                              length_m=100.0, kind="overhead", feeder_hint="")
    g.adj["m0"].append(("m1", "f0"))
    g.adj["m1"].append(("m0", "f0"))
    tr = Transformer(node_id="m1", capacity_kva=load, id="ft0")
    g.transformer_ids_at["m1"] = ["ft0"]
    zones_by_feeder[key] = [SwitchZone(
        id=f"{key}0", feeder=key, zone_no=0, kind="head", source_node="m0",
        nodes={"m0", "m1"}, edges={"f0"}, transformer_ids={"ft0"})]
    return tr


def _tree(g, net, traces, zones_by_feeder, feeder="FA"):
    transf_kw = {t.id: t.capacity_kva for t in net.transformers}
    tree = build_zone_tree(g, traces[0], zones_by_feeder[feeder],
                           transf_kw, [])
    assert tree is not None
    return tree


def test_end_tie_restores_everything_between_fault_and_tie():
    """خطای زون‌سر با Tie انتهایی: تمام پایین‌دستِ جداسازی برقدار می‌شود."""
    g, net, traces, zones_by_feeder = linear_feeder()
    tree = _tree(g, net, traces, zones_by_feeder)
    # پشتیبان ۲۰۰۰ kW رزرو دارد → همه ۲۰۰۰ kW پایین‌دست زون معیوب بازپُل می‌شود
    rows = zone_fault_rows(tree, {"Z4": 2000.0})
    by_zone = {r.zone: r for r in rows}
    assert by_zone["Z0"].restorable_kw == 2000.0
    assert by_zone["Z0"].shed_kw == 500.0
    # خطا در Z1 → پایین‌دست Z1 (Z1 معیوب است) = Z2..Z4 = 1500 kW
    assert by_zone["Z1"].restorable_kw == 1500.0
    assert by_zone["Z1"].shed_kw == 500.0      # فقط خود Z1 خاموش می‌ماند
    # خطا در Z3 → پایین‌دست = فقط Z4 = 600 kW
    assert by_zone["Z3"].restorable_kw == 600.0
    assert by_zone["Z3"].shed_kw == 400.0
    # خطای خود زون Tie: زون معیوب هرگز برقدار نمی‌شود
    assert by_zone["Z4"].restorable_kw == 0.0
    assert by_zone["Z4"].shed_kw == 600.0


def test_tie_restores_side_branches_along_the_path():
    """انشعاب‌های جانبی مسیر بین خطا و Tie نیز برقدار می‌شوند."""
    g = NetworkGraph()
    for i in range(3):
        g.nodes[f"n{i}"] = GraphNode(id=f"n{i}", kind=NodeKind.JUNCTION,
                                     coord=(i * 100.0, 0.0), feeder_hint="")
    # انشعاب جانبی از n1 به n1s (بار 300 kW)
    g.nodes["n1s"] = GraphNode(id="n1s", kind=NodeKind.JUNCTION,
                               coord=(100.0, 80.0), feeder_hint="")
    g.edges["e0"] = GraphEdge(id="e0", branch_id="b", seq=0, a="n0", b="n1",
                              length_m=100.0, kind="overhead", feeder_hint="")
    g.edges["e1"] = GraphEdge(id="e1", branch_id="b", seq=1, a="n1", b="n2",
                              length_m=100.0, kind="overhead", feeder_hint="")
    g.edges["s1"] = GraphEdge(id="s1", branch_id="s", seq=0, a="n1", b="n1s",
                              length_m=80.0, kind="overhead", feeder_hint="")
    adj = {"n0": [("n1", "e0")], "n1": [("n0", "e0"), ("n2", "e1"), ("n1s", "s1")],
           "n2": [("n1", "e1")], "n1s": [("n1", "s1")]}
    for a, nbrs in adj.items():
        g.adj[a].extend(nbrs)
    net = type("N", (), {"transformers": [
        Transformer(node_id="n1", capacity_kva=400.0, id="t0"),
        Transformer(node_id="n2", capacity_kva=400.0, id="t1"),
        Transformer(node_id="n1s", capacity_kva=300.0, id="t2"),
    ]})()
    g.transformer_ids_at["n1"] = ["t0"]
    g.transformer_ids_at["n2"] = ["t1"]
    g.transformer_ids_at["n1s"] = ["t2"]
    trafos = {"Z0": {"t0"}, "Z1": {"t1"}, "Z2": {"t2"}}
    zones = [SwitchZone(id="Z0", feeder="FA", zone_no=0, kind="head",
                        source_node="n0", nodes={"n0", "n1"}, edges={"e0"},
                        transformer_ids=trafos["Z0"]),
             SwitchZone(id="Z1", feeder="FA", zone_no=1, kind="section",
                        source_node=None, nodes={"n1", "n2"}, edges={"e1"},
                        transformer_ids=trafos["Z1"]),
             SwitchZone(id="Z2", feeder="FA", zone_no=2, kind="section",
                        source_node=None, nodes={"n1", "n1s"}, edges={"s1"},
                        transformer_ids=trafos["Z2"])]
    trace = FeederTrace(feeder="A", feeder_key="FA", source_node="n0",
                        nodes=set(g.nodes), edges=set(g.edges))
    transf_kw = {t.id: t.capacity_kva for t in net.transformers}
    tree = build_zone_tree(g, trace, zones, transf_kw, [])
    assert tree is not None
    # Tie در انتهای Z1: خطای Z0 باید Z1 و انشعاب Z2 (400+300=700 kW) را بازپُل کند
    rows = zone_fault_rows(tree, {"Z1": 10_000.0})
    by_zone = {r.zone: r for r in rows}
    assert by_zone["Z0"].restorable_kw == 400.0 + 300.0
    assert by_zone["Z0"].shed_kw == 400.0      # فقط بار خود Z0 (400) قطع می‌ماند


def test_two_ties_same_branch_pool_capacity_in_one_island():
    """دو Tie در یک شاخه: ظرفیت هر دو Tie در یک جزیره تجمیع می‌شود."""
    segs = SegTree(
        seg_load={"S1": 100.0, "S2": 100.0, "S3": 500.0},
        seg_len={"S1": 100.0, "S2": 100.0, "S3": 100.0},
        parent={"S1": None, "S2": "S1", "S3": "S2"},
        children={"S1": ["S2"], "S2": ["S3"], "S3": []},
        root="S1",
        node_seg={"c1": "S1", "c2": "S2"},
        node_seg_below={"c1": "S2", "c2": "S3"})
    _ens, rows = ens_of_configuration(segs, lam_per_year=9.0,
                                      r_minutes=60.0,
                                      switching_minutes=10.0,
                                      transfer_cap_by_seg={"S2": 300.0,
                                                           "S3": 100.0},
                                      total_length_m=300.0)
    r1 = next(r for r in rows if r["seg"] == "S1")
    # خطای S1 → جزیرهٔ {S2,S3} با مجموع بار ۶۰۰ و مجموع Tieها ۴۰۰ → ۴۰۰ بازپُل
    assert r1["restored_kw"] == 400.0
    assert r1["shed_kw"] == 300.0


def test_ties_in_separate_branches_get_independent_pools():
    """دروازه‌های خروج جدا (دو گرهٔ مرزی متفاوت) → دو جزیرهٔ مستقل با سقف مستقل."""
    segs = SegTree(
        seg_load={"S0": 50.0, "SA": 100.0, "SB": 200.0},
        seg_len={"S0": 100.0, "SA": 100.0, "SB": 100.0},
        parent={"S0": None, "SA": "S0", "SB": "S0"},
        children={"S0": ["SA", "SB"], "SA": [], "SB": []},
        root="S0",
        node_seg={"xA": "S0", "xB": "S0"},
        node_seg_below={"xA": "SA", "xB": "SB"})
    _ens, rows = ens_of_configuration(
        segs, lam_per_year=9.0, r_minutes=60.0, switching_minutes=10.0,
        transfer_cap_by_seg={"SA": 150.0, "SB": 50.0},
        total_length_m=300.0)
    r0 = next(r for r in rows if r["seg"] == "S0")
    # جزیرهٔ A: min(100,150)=100؛ جزیرهٔ B: min(200,50)=50 → 150 (نه 200)
    assert r0["restored_kw"] == 150.0
    # outage = 50+100+200 = 350؛ shed = 350 − 150 = 200
    assert r0["shed_kw"] == 200.0


def test_tie_in_sibling_branch_restores_shared_tee_island():
    """Tie در شاخهٔ A هنگامی که هر دو شاخه زیر یک مرز جداسازی (یک کلید tee)
    هستند، کل جزیرهٔ tee را بازپُل می‌کند.

    توجه فیزیکی (بند ۱۹ — ثبت برای بازبینی مهندس): اگر در گرهٔ انشعاب
    برای هر شاخه کلید مستقل نصب باشد، با بازکردن هر دو، دو جزیرهٔ جدا
    می‌شوند و Tie شاخهٔ A فقط شاخهٔ خود را بازپُل می‌کند؛ دادهٔ zone این
    تمایز را نشان نمی‌دهد (TOPO-POL-04 branchy boundary) و سطح اول آن را
    یک جزیره می‌بیند — سازگار با درخت قطعه‌های build_seg_tree (هر دو شاخهٔ
    زیر همان کلید در یک قطعه‌اند و ENS همین را می‌شمارد).
    """
    g = NetworkGraph()
    for nid, x in (("n0", 0.0), ("n1", 100.0), ("a1", 200.0), ("b1", 200.0)):
        g.nodes[nid] = GraphNode(id=nid, kind=NodeKind.JUNCTION,
                                 coord=(x, 100.0 if nid.startswith("b") else 0.0),
                                 feeder_hint="")
    g.edges["e0"] = GraphEdge(id="e0", branch_id="b", seq=0, a="n0", b="n1",
                              length_m=100.0, kind="overhead", feeder_hint="")
    g.edges["ea"] = GraphEdge(id="ea", branch_id="b", seq=1, a="n1", b="a1",
                              length_m=100.0, kind="overhead", feeder_hint="")
    g.edges["eb"] = GraphEdge(id="eb", branch_id="b2", seq=0, a="n1", b="b1",
                              length_m=100.0, kind="overhead", feeder_hint="")
    for a, nbrs in {"n0": [("n1", "e0")],
                    "n1": [("n0", "e0"), ("a1", "ea"), ("b1", "eb")],
                    "a1": [("n1", "ea")], "b1": [("n1", "eb")]}.items():
        g.adj[a].extend(nbrs)
    net = type("N", (), {"transformers": [
        Transformer(node_id="a1", capacity_kva=700.0, id="ta"),
        Transformer(node_id="b1", capacity_kva=900.0, id="tb"),
    ]})()
    g.transformer_ids_at["a1"] = ["ta"]
    g.transformer_ids_at["b1"] = ["tb"]
    zones = [SwitchZone(id="Z0", feeder="FA", zone_no=0, kind="head",
                        source_node="n0", nodes={"n0", "n1"}, edges={"e0"},
                        transformer_ids=set()),
             SwitchZone(id="Z1", feeder="FA", zone_no=1, kind="section",
                        source_node=None, nodes={"n1", "a1"}, edges={"ea"},
                        transformer_ids={"ta"}),
             SwitchZone(id="Z2", feeder="FA", zone_no=2, kind="section",
                        source_node=None, nodes={"n1", "b1"}, edges={"eb"},
                        transformer_ids={"tb"})]
    trace = FeederTrace(feeder="A", feeder_key="FA", source_node="n0",
                        nodes=set(g.nodes), edges=set(g.edges))
    transf_kw = {t.id: t.capacity_kva for t in net.transformers}
    tree = build_zone_tree(g, trace, zones, transf_kw, [])
    assert tree is not None
    # خطای Z0؛ Tie فقط در شاخهٔ A، اما دو شاخه زیر یک مرز مشترک‌اند →
    # یک جزیره: min(700+900, 10000) = 1600 بازپُل می‌شود
    rows = zone_fault_rows(tree, {"Z1": 10_000.0})
    by_zone = {r.zone: r for r in rows}
    assert by_zone["Z0"].restorable_kw == 1600.0
    assert by_zone["Z0"].shed_kw == 0.0
    # خطای Z1 → اعضای پایین‌دست فقط Z2؛ بدون Tie = ۰ بازپُل
    assert by_zone["Z1"].restorable_kw == 0.0


def test_tie_restores_only_within_backup_spare():
    """ظرفیت پشتیبان سقف بازپُل است (A-10)."""
    g, net, traces, zones_by_feeder = linear_feeder()
    ft = _second_feeder(g, zones_by_feeder)
    net.transformers.append(ft)
    # فیدر پشتیبان FC هم trace دارد تا رزرو مدل‌شده‌اش (800−300=500) شناخته شود
    traces_fc = list(traces) + [
        FeederTrace(feeder="Feeder C", feeder_key="FC", source_node="m0",
                    nodes={"m0", "m1"}, edges={"f0"})]
    tie = make_tie("T1", "FA", "FC", "n5", automation=True)
    st = NMinusOneSettings(feeder_rated_kw={"FC": 800.0})   # رزرو ۵۰۰
    res = run_n_minus_one(g, net, traces_fc, zones_by_feeder, ties=[tie],
                          settings=st)
    rows = {r["zone"]: r for r in res.rows15}
    assert rows["Z0"]["restorable_kw"] == 500.0     # min(2000, 500)
    assert rows["Z1"]["restorable_kw"] == 500.0     # min(1500, 500)
    assert rows["Z2"]["restorable_kw"] == 500.0     # min(1000, 500)


def test_barrier_node_splits_the_island():
    """گره مانع (فقط کلید NO غیراتوماسیون) → شاخه‌های tee دو جزیرهٔ مستقل‌اند."""
    g = NetworkGraph()
    for nid, x in (("n0", 0.0), ("n1", 100.0), ("a1", 200.0), ("b1", 200.0)):
        g.nodes[nid] = GraphNode(id=nid, kind=NodeKind.JUNCTION,
                                 coord=(x, 100.0 if nid.startswith("b") else 0.0),
                                 feeder_hint="")
    g.edges["e0"] = GraphEdge(id="e0", branch_id="b", seq=0, a="n0", b="n1",
                              length_m=100.0, kind="overhead", feeder_hint="")
    g.edges["ea"] = GraphEdge(id="ea", branch_id="b", seq=1, a="n1", b="a1",
                              length_m=100.0, kind="overhead", feeder_hint="")
    g.edges["eb"] = GraphEdge(id="eb", branch_id="b2", seq=0, a="n1", b="b1",
                              length_m=100.0, kind="overhead", feeder_hint="")
    for a, nbrs in {"n0": [("n1", "e0")],
                    "n1": [("n0", "e0"), ("a1", "ea"), ("b1", "eb")],
                    "a1": [("n1", "ea")], "b1": [("n1", "eb")]}.items():
        g.adj[a].extend(nbrs)
    # کلید دستیِ NO در گرهٔ انشعاب (غیراتوماسیون) → مانع
    from switchloc.domain.entities import SwitchDev
    from switchloc.domain.enums import SwitchFamily, SwitchState
    manual = SwitchDev(family=SwitchFamily.SECTIONALIZER, node_id="n1",
                       normally_state="NO",
                       current_state=SwitchState.IN_SERVICE, id="sw_manual")
    net = type("N", (), {"transformers": [
        Transformer(node_id="a1", capacity_kva=700.0, id="ta"),
        Transformer(node_id="b1", capacity_kva=900.0, id="tb"),
    ], "switches": [manual]})()
    g.switch_ids_at["n1"] = ["sw_manual"]
    g.transformer_ids_at["a1"] = ["ta"]
    g.transformer_ids_at["b1"] = ["tb"]
    zones = [SwitchZone(id="Z0", feeder="FA", zone_no=0, kind="head",
                        source_node="n0", nodes={"n0", "n1"}, edges={"e0"},
                        transformer_ids=set()),
             SwitchZone(id="Z1", feeder="FA", zone_no=1, kind="section",
                        source_node=None, nodes={"n1", "a1"}, edges={"ea"},
                        transformer_ids={"ta"}),
             SwitchZone(id="Z2", feeder="FA", zone_no=2, kind="section",
                        source_node=None, nodes={"n1", "b1"}, edges={"eb"},
                        transformer_ids={"tb"})]
    trace = FeederTrace(feeder="A", feeder_key="FA", source_node="n0",
                        nodes=set(g.nodes), edges=set(g.edges))
    transf_kw = {t.id: t.capacity_kva for t in net.transformers}
    tree = build_zone_tree(g, trace, zones, transf_kw, [])
    assert tree is not None
    from switchloc.level1.transfer import barrier_cut_nodes
    barriers = barrier_cut_nodes(g, net, [])
    assert "n1" in barriers
    rows = zone_fault_rows(tree, {"Z1": 10_000.0}, barriers)
    by_zone = {r.zone: r for r in rows}
    # خطای Z0؛ Tie در A پشت مانع n1 → فقط Z1 بازپُل می‌شود
    assert by_zone["Z0"].restorable_kw == 700.0
    assert by_zone["Z0"].shed_kw == 900.0


def test_separate_exit_nodes_get_independent_islands():
    """دو دروازهٔ خروج جدا → دو جزیرهٔ مستقل؛ ظرفیت Tie هر جزیره سقف خودش است."""
    g = NetworkGraph()
    coords = {"n0": (0.0, 0.0), "nA": (100.0, 0.0), "nB": (200.0, 0.0),
              "a1": (100.0, 80.0), "b1": (300.0, 0.0)}
    for nid, c in coords.items():
        g.nodes[nid] = GraphNode(id=nid, kind=NodeKind.JUNCTION,
                                 coord=c, feeder_hint="")
    g.edges["ep"] = GraphEdge(id="ep", branch_id="b", seq=0, a="n0", b="nA",
                              length_m=100.0, kind="overhead", feeder_hint="")
    g.edges["ep2"] = GraphEdge(id="ep2", branch_id="b", seq=1, a="nA", b="nB",
                               length_m=100.0, kind="overhead", feeder_hint="")
    g.edges["ea"] = GraphEdge(id="ea", branch_id="b", seq=2, a="nA", b="a1",
                              length_m=100.0, kind="overhead", feeder_hint="")
    g.edges["eb"] = GraphEdge(id="eb", branch_id="b", seq=3, a="nB", b="b1",
                              length_m=100.0, kind="overhead", feeder_hint="")
    for a, nbrs in {"n0": [("nA", "ep")],
                    "nA": [("n0", "ep"), ("nB", "ep2"), ("a1", "ea")],
                    "nB": [("nA", "ep2"), ("b1", "eb")],
                    "a1": [("nA", "ea")], "b1": [("nB", "eb")]}.items():
        g.adj[a].extend(nbrs)
    net = type("N", (), {"transformers": [
        Transformer(node_id="a1", capacity_kva=100.0, id="ta"),
        Transformer(node_id="b1", capacity_kva=200.0, id="tb"),
    ]})()
    g.transformer_ids_at["a1"] = ["ta"]
    g.transformer_ids_at["b1"] = ["tb"]
    # زون سر: n0..nA است؛ nB در زون سر نیست — ZB خروج دوم را در خود دارد
    zones = [SwitchZone(id="Z0", feeder="FA", zone_no=0, kind="head",
                        source_node="n0", nodes={"n0", "nA"},
                        edges={"ep"}, transformer_ids=set()),
             SwitchZone(id="ZB", feeder="FA", zone_no=1, kind="section",
                        source_node=None, nodes={"nA", "nB"}, edges={"ep2"},
                        transformer_ids=set()),
             SwitchZone(id="ZA", feeder="FA", zone_no=2, kind="section",
                        source_node=None, nodes={"nA", "a1"}, edges={"ea"},
                        transformer_ids={"ta"}),
             SwitchZone(id="ZC", feeder="FA", zone_no=3, kind="section",
                        source_node=None, nodes={"nB", "b1"}, edges={"eb"},
                        transformer_ids={"tb"})]
    trace = FeederTrace(feeder="A", feeder_key="FA", source_node="n0",
                        nodes=set(g.nodes), edges=set(g.edges))
    transf_kw = {t.id: t.capacity_kva for t in net.transformers}
    tree = build_zone_tree(g, trace, zones, transf_kw, [])
    assert tree is not None
    # خطای Z0؛ اعضای پایین‌دست: ZB (تنه)، ZA (خروجی اول، Tie=۱۵۰)، ZC (خروجی دوم، Tie=۵۰)
    # همبندی: ZB با ZA در nA و با ZC در nB مشترک است → یک جزیره در غیاب مانع؛
    # مجموع Tieها ۲۰۰، بار کل ۳۰۰ → بازپُل ۲۰۰.
    # اما با مانع در nB، جزیرهٔ ZC جدا می‌شود و سقف خودش (۵۰) اعمال می‌شود.
    rows = zone_fault_rows(tree, {"ZA": 150.0, "ZC": 50.0})
    by_zone = {r.zone: r for r in rows}
    assert by_zone["Z0"].restorable_kw == 200.0
    # خطای ZB (میانهٔ تنه): درخت زون ZA و ZB را هم‌سطح (هر دو فرزند مستقیم Z0)
    # می‌سازد؛ عضو پایین‌دستِ ZB فقط ZC است → جزیرهٔ مستقل: min(200, 50) = 50
    assert by_zone["ZB"].restorable_kw == 50.0
    assert by_zone["ZB"].shed_kw == 150.0
    # با مانع در nA: خطای Z0 → ZA از جزیرهٔ تنه جدا می‌شود → 100 + min(0+200,50) = 150
    from switchloc.level1.transfer import barrier_cut_nodes
    barriers = barrier_cut_nodes(g, net, [])  # هیچ تجهیزی تعریف نشده → خالی
    assert "nA" not in barriers               # مانع فقط با تجهیز واقعی ساخته می‌شود
    rows2 = zone_fault_rows(tree, {"ZA": 150.0, "ZC": 50.0}, {"nA"})
    by_zone2 = {r.zone: r for r in rows2}
    assert by_zone2["Z0"].restorable_kw == 150.0


def test_fault_nested_inside_branch_islands_below_only():
    """خطا در میانهٔ شاخه: تنها پایین‌دست بازپُل می‌شود."""
    g, net, traces, zones_by_feeder = linear_feeder((500.0, 500.0, 400.0))
    tree = _tree(g, net, traces, zones_by_feeder)
    rows = zone_fault_rows(tree, {"Z2": 10_000.0})
    by_zone = {r.zone: r for r in rows}
    # خطای Z1: اعضای پایین‌دست {Z2} با Tie بی‌نهایت → ۴۰۰
    assert by_zone["Z1"].restorable_kw == 400.0
    # خطای Z2: عضو دیگری نیست → ۰
    assert by_zone["Z2"].restorable_kw == 0.0


def test_manual_ep_tl_matches_island_model_and_kernel():
    """_ep_tl_of_segments: جزیره‌های بازپُل + TL حداکثر مستقل
    (هم‌روا با کرنل compute_ep_tl)."""
    segs = SegTree(
        seg_load={"S1": 500.0, "S2": 500.0, "S3": 500.0},
        seg_len={"S1": 100.0, "S2": 100.0, "S3": 100.0},
        parent={"S1": None, "S2": "S1", "S3": "S2"},
        children={"S1": ["S2"], "S2": ["S3"], "S3": []},
        root="S1",
        node_seg={"c1": "S1", "c2": "S2"},
        node_seg_below={"c1": "S2", "c2": "S3"})
    # Tie در S2 و S3 با ظرفیت ۱۰۰ هر کدام؛ خطای S1 → جزیرهٔ {S2,S3} → ۲۰۰ kW
    ep, tl, worst = _ep_tl_of_segments(segs, 1500.0,
                                       {"S2": 100.0, "S3": 100.0})
    assert worst == "S1"
    assert ep == 100.0 * (1500.0 - 200.0) / 1500.0
    assert tl == 100.0 * 200.0 / 1500.0
