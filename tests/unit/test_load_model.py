# -*- coding: utf-8 -*-
"""Tests for the three-level load model (نیاز ۱۱) — levels, adjustable
factors and per-value traceable origins."""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest                                          # noqa: E402

from switchloc.reliability.load_model import (          # noqa: E402
    LEVEL_ESTIMATED, LEVEL_PRECISE, LEVEL_SUBSTITUTE, LoadModelSettings,
    build_node_loads)
from switchloc.topology.graph import GraphEdge, GraphNode, NetworkGraph  # noqa
from switchloc.validation.issues import IssueLog        # noqa: E402


def _tiny_network(load_p_kw=120.0):
    """Graph + net stub: n0 -- n1(load) -- n2(transformer 400 kVA)."""
    from switchloc.domain.entities import LoadPt, Transformer
    g = NetworkGraph()
    for i in range(3):
        g.nodes[f"n{i}"] = GraphNode(id=f"n{i}", kind="junction",
                                     coord=(i * 10.0, 0.0), feeder_hint="")
    for i in range(2):
        eid = f"e{i}"
        g.edges[eid] = GraphEdge(id=eid, branch_id="b", seq=i, a=f"n{i}",
                                 b=f"n{i + 1}", length_m=10.0,
                                 kind="overhead", feeder_hint="")
        g.adj[f"n{i}"].append((f"n{i + 1}", eid))
        g.adj[f"n{i + 1}"].append((f"n{i}", eid))
    tr = Transformer(node_id="n2", capacity_kva=400.0, id="T1")
    g.transformer_ids_at["n2"].append("T1")
    load = LoadPt(node_id="n1", p_kw=load_p_kw, id="L1",
                  data_source="measured")
    net = type("N", (), {"transformers": [tr], "switches": [],
                         "loads": [load]})()
    return g, net


def test_substitute_level_is_legacy_kva_kw():
    g, net = _tiny_network()
    res = build_node_loads(g, net, LoadModelSettings(level=LEVEL_SUBSTITUTE,
                                                     substitute_factor=1.0))
    assert res.node_kw["n2"] == pytest.approx(400.0)     # kVA≈kW (رفتار قبلی)
    assert "T1" in res.node_origin["n2"]
    assert res.level == LEVEL_SUBSTITUTE


def test_estimated_level_uses_adjustable_loading_factor():
    g, net = _tiny_network()
    res = build_node_loads(g, net, LoadModelSettings(level=LEVEL_ESTIMATED,
                                                     loading_factor=0.6))
    assert res.node_kw["n2"] == pytest.approx(400.0 * 0.6)
    assert "0.6" in res.node_origin["n2"]                # منشأ قابل ردیابی
    res2 = build_node_loads(g, net, LoadModelSettings(level=LEVEL_ESTIMATED,
                                                      loading_factor=0.8))
    assert res2.node_kw["n2"] == pytest.approx(400.0 * 0.8)


def test_precise_level_uses_only_real_loads_zero_else():
    g, net = _tiny_network()
    res = build_node_loads(g, net, LoadModelSettings(level=LEVEL_PRECISE))
    assert res.node_kw["n1"] == pytest.approx(120.0)     # کنتور واقعی
    assert res.node_kw["n2"] == 0.0                      # بدون داده → صفر (حدس ممنوع)
    assert res.coverage["nodes_with_real_load"] == 1
    assert "L1" in res.node_origin["n1"]


def test_invalid_settings_are_refused():
    with pytest.raises(ValueError):
        LoadModelSettings(level="magic")
    with pytest.raises(ValueError):
        LoadModelSettings(loading_factor=0.0)
    with pytest.raises(ValueError):
        LoadModelSettings(substitute_factor=99.0)


def test_issues_record_the_level():
    g, net = _tiny_network()
    issues = IssueLog()
    build_node_loads(g, net, LoadModelSettings(level=LEVEL_PRECISE),
                     issues=issues)
    codes = {i.code for i in issues.items()}
    assert "LOAD-MODEL-LEVEL" in codes


def test_per_feeder_totals_present():
    g, net = _tiny_network()
    res = build_node_loads(g, net, LoadModelSettings(level=LEVEL_ESTIMATED,
                                                     loading_factor=0.7))
    # بدون برچسب فیدر گره‌ها → کلید «(بدون فیدر)» ولی جمع مثبت
    assert any(v > 0 for v in res.per_feeder_kw.values())


# ---------------------------------------------------------------------------
# سطح چهارم — روش Load Scaling (درخواست کاربر: ورود بار هر فیدر P/Q)
# ---------------------------------------------------------------------------
def _two_feeder_network():
    """F1: ترانس 400+400 kVA روی n2 — F2: ترانس 100 kVA روی n3."""
    from switchloc.domain.entities import Transformer
    g = NetworkGraph()
    for i in range(4):
        g.nodes[f"n{i}"] = GraphNode(id=f"n{i}", kind="junction",
                                     coord=(i * 10.0, 0.0), feeder_hint="")
    for i in range(3):
        eid = f"e{i}"
        g.edges[eid] = GraphEdge(id=eid, branch_id="b", seq=i, a=f"n{i}",
                                 b=f"n{i + 1}", length_m=10.0,
                                 kind="overhead", feeder_hint="")
        g.adj[f"n{i}"].append((f"n{i + 1}", eid))
        g.adj[f"n{i + 1}"].append((f"n{i}", eid))
    t1 = Transformer(node_id="n2", capacity_kva=400.0, id="T1",
                     feeder_name="F1")
    t2 = Transformer(node_id="n2", capacity_kva=400.0, id="T2",
                     feeder_name="F1")
    t3 = Transformer(node_id="n3", capacity_kva=100.0, id="T3",
                     feeder_name="F2")
    g.transformer_ids_at["n2"] += ["T1", "T2"]
    g.transformer_ids_at["n3"].append("T3")
    net = type("N", (), {"transformers": [t1, t2, t3], "switches": [],
                         "loads": []})()
    return g, net


def test_scaled_level_distributes_feeder_load_by_rated_capacity():
    from switchloc.reliability.load_model import LEVEL_SCALED
    g, net = _two_feeder_network()
    st = LoadModelSettings(
        level=LEVEL_SCALED,
        feeder_pq={"F1": {"p_kw": 200.0, "q_kvar": 0.0},
                   "F2": {"p_kw": 30.0, "q_kvar": 40.0}})
    res = build_node_loads(g, net, st)
    # F1: S_load=200، ΣS_rated=800 → K=0.25، cosφ=1 → هر ترانس 100 kW
    assert res.node_kw["n2"] == pytest.approx(200.0)     # 2 × 100
    # F2: S_load=√(30²+40²)=50، ΣS_rated=100 → K=0.5، cosφ=30/50=0.6
    #      P_T3 = 0.5 × 100 × 0.6 = 30 kW == P واردشده ✓
    assert res.node_kw["n3"] == pytest.approx(30.0)
    plan = res.scaling_plan
    assert plan["F1"]["k_scale"] == pytest.approx(200.0 / 800.0)
    assert plan["F2"]["cos_phi"] == pytest.approx(0.6)
    assert plan["F2"]["s_load_kva"] == pytest.approx(50.0)
    # منشأ ردیابی‌پذیر (بند ۱۹)
    assert "T1" in res.node_origin["n2"] and "cosφ" in res.node_origin["n2"]
    # جمع بار توزیع‌شده هر فیدر = P واردشده
    assert sum(res.node_kw[n] for n in ("n2",)) == pytest.approx(200.0)


def test_scaled_level_missing_feeder_input_is_zero_with_warning():
    from switchloc.reliability.load_model import LEVEL_SCALED
    g, net = _two_feeder_network()
    st = LoadModelSettings(level=LEVEL_SCALED,
                           feeder_pq={"F1": {"p_kw": 400.0, "q_kvar": 0.0}})
    res = build_node_loads(g, net, st)
    assert res.node_kw["n2"] == pytest.approx(400.0)
    assert res.node_kw["n3"] == 0.0                      # بدون ورودی → صفر
    codes = {i.code for i in res.issues}
    assert "LOAD-SCALING-FEEDER-NO-INPUT" in codes


def test_scaled_settings_reject_nonpositive_inputs_and_roundtrip():
    from switchloc.reliability.load_model import LEVEL_SCALED
    with pytest.raises(ValueError):
        LoadModelSettings(level=LEVEL_SCALED,
                          feeder_pq={"F1": {"p_kw": 0.0, "q_kvar": 0.0}})
    with pytest.raises(ValueError):
        LoadModelSettings(level=LEVEL_SCALED,
                          feeder_pq={"F1": {"p_kw": -5.0, "q_kvar": 0.0}})
    st = LoadModelSettings(level=LEVEL_SCALED,
                           feeder_pq={"F1": {"p_kw": 10.0, "q_kvar": 2.0}})
    d = st.as_dict()
    st2 = LoadModelSettings.from_dict(d)
    assert st2.feeder_pq["F1"] == {"p_kw": 10.0, "q_kvar": 2.0}
    assert st2.level == LEVEL_SCALED


def test_scaled_level_reports_transformer_load_missing_from_graph():
    from switchloc.reliability.load_model import LEVEL_SCALED
    g, net = _two_feeder_network()
    # T3 remains in the engineering inventory but its GIS node is not in graph.
    g.transformer_ids_at["n3"].remove("T3")
    st = LoadModelSettings(
        level=LEVEL_SCALED,
        feeder_pq={"F1": {"p_kw": 200.0, "q_kvar": 0.0},
                   "F2": {"p_kw": 30.0, "q_kvar": 40.0}})
    res = build_node_loads(g, net, st)
    assert res.node_kw["n2"] == pytest.approx(200.0)
    assert res.unassigned_transformer_ids == ["T3"]
    assert res.unassigned_kw_by_feeder["F2"] == pytest.approx(30.0)
    assert res.accounting["feeder_input_p_kw"] == pytest.approx(230.0)
    assert res.accounting["graph_assigned_transformer_kw"] == pytest.approx(200.0)
    assert res.accounting["graph_unassigned_transformer_kw"] == pytest.approx(30.0)
    assert res.accounting["reconciled"] is True
    assert any(i.code == "LOAD-SCALING-TRANSFORMER-RECONCILIATION"
               for i in res.issues)
