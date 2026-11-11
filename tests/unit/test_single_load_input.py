# -*- coding: utf-8 -*-
"""تک‌مبنایی‌بودن ورودی بار (درخواست کاربر): یک ورودی بار برای هر فیدر
(تب Load Model) و همهٔ محاسبات وابسته به بار — ENS/زون، رزرو ظرفیت،
رابطه (۱۱)، معیار ۴ و مبنای رتبه‌بندی — از همان مقدار می‌خوانند.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest                                          # noqa: E402

from switchloc.placement.capacity import (             # noqa: E402
    CAP_NEEDS_CONFIRMATION, CAP_OK, CAP_VIOLATED, FeederCapacity,
    check_scheme_capacity)
from switchloc.placement.service import _spare_map    # noqa: E402
from switchloc.level1.ranking import (                # noqa: E402
    feeder_criterion4, RankingSettings)
from switchloc.reliability.load_model import (        # noqa: E402
    LEVEL_SCALED, LoadModelSettings, build_node_loads)
from switchloc.topology.graph import GraphEdge, GraphNode, NetworkGraph  # noqa


# ---------------------------------------------------------------------------
# ۱) جمع بار هر فیدر (per_feeder_kw) طبق کلید فیدرِ خود ترانس است —
#    همان مبنای Load Scaling — نه برچسب خالی فیدرِ گره‌ها
# ---------------------------------------------------------------------------
def _two_feeder_scaled():
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
    net = SimpleNamespace(transformers=[t1, t2, t3], switches=[], loads=[])
    st = LoadModelSettings(
        level=LEVEL_SCALED,
        feeder_pq={"F1": {"p_kw": 1200.0, "q_kvar": 0.0},
                   "F2": {"p_kw": 1260.0, "q_kvar": 0.0}})
    return g, net, st


def test_scaled_per_feeder_kw_uses_transformer_feeder_key():
    g, net, st = _two_feeder_scaled()
    res = build_node_loads(g, net, st)
    assert res.per_feeder_kw == pytest.approx({"F1": 1200.0, "F2": 1260.0},
                                              abs=1e-6)
    assert "" not in res.per_feeder_kw
    assert res.coverage["feeders_total"] == 2
    assert res.coverage["sum_p_kw"] == pytest.approx(2460.0)


# ---------------------------------------------------------------------------
# ۲) رزرو ظرفیت: نامی − پیک، که پیک آن از همان ورودی واحد مدل بار است
# ---------------------------------------------------------------------------
def _n1(**kw):
    trees = {k: SimpleNamespace(total_load_kw=v) for k, v in kw.items()}
    return SimpleNamespace(trees=trees)


def test_spare_prefers_verified_nominal_minus_load_model_peak():
    caps = {"F1": FeederCapacity("F1", nominal_kw=5000.0, peak_kw=999.0,
                                 nominal_source="user", peak_source="unknown")}
    out = _spare_map(_n1(F1=1234.0), None, caps,
                     peak_kw_of_feeder={"F1": 1200.0})
    # پیک ذخیره‌شدهٔ ظرفیت (999) نادیده گرفته می‌شود؛ پیک مدل بار حاکم است
    assert out == {"F1": 3800.0}


def test_spare_ignores_default_software_nominal():
    caps = {"F1": FeederCapacity("F1", nominal_kw=7000.0, peak_kw=None,
                                 nominal_source="default")}
    out = _spare_map(_n1(F1=500.0), {"F1": 2000.0}, caps,
                     peak_kw_of_feeder={"F1": 1200.0})
    # نامی پیش‌فرض پذیرفته نمی‌شود → ظرفیت نامی قدیمی − پیک مدل بار
    assert out == {"F1": 800.0}


def test_spare_falls_back_to_lm_peak_not_zone_total():
    # بدون تب ظرفیت و بدون A-10: بار زون‌ها (total_load_kw) صرفاً
    # fallback آخر است؛ ورودی مدل بار همیشه اول است
    out = _spare_map(_n1(F1=111.0), {"F1": 2000.0}, None,
                     peak_kw_of_feeder={"F1": 1200.0})
    assert out == {"F1": 800.0}
    out2 = _spare_map(_n1(F1=111.0), {"F1": 2000.0}, None,
                      peak_kw_of_feeder={})
    assert out2 == {"F1": 1889.0}


# ---------------------------------------------------------------------------
# ۳) رابطه (۱۱): بار مصرفی = ورودی مدل بار — نه پیکِ ذخیره‌شدهٔ ظرفیت
# ---------------------------------------------------------------------------
class _Switch:
    def __init__(self, node, feeder, kind):
        self.node, self.feeder, self.kind = node, feeder, kind


class _Scheme:
    def __init__(self, switches, feeders):
        self.id = "s1"
        self.switches = switches
        self.feeders = feeders
        self.kind = "sequential_nc"


def _caps(**kw):
    return {k: FeederCapacity(k, **v) for k, v in kw.items()}


def test_relation11_uses_the_single_load_input_not_stored_peak():
    scheme = _Scheme([_Switch("a", "F1", "NO"), _Switch("b", "F2", "NO")],
                     ["F1", "F2"])
    caps = _caps(F1=dict(nominal_kw=7000.0, emergency_kw=900.0,
                         peak_kw=100.0, nominal_source="user",
                         peak_source="load_model"),
                 F2=dict(nominal_kw=7000.0, emergency_kw=900.0,
                         peak_kw=100.0, nominal_source="user",
                         peak_source="load_model"))
    # پیک ذخیره‌شده (100) بی‌خطر است اما ورودی مدل بار (1200) > ⅔×900=600
    chk = check_scheme_capacity(scheme, caps,
                                {"F1": 1200.0, "F2": 1200.0})
    assert chk.status == CAP_VIOLATED
    # و اگر بار ورودی مدل بار پایین باشد، همان‌قدر صریح تأیید می‌کند
    chk2 = check_scheme_capacity(scheme, caps,
                                 {"F1": 500.0, "F2": 500.0})
    assert chk2.status == CAP_OK


def test_default_nominal_never_confirms_even_if_peak_matches():
    scheme = _Scheme([_Switch("a", "F1", "NC")], ["F1"])
    caps = _caps(F1=dict(nominal_kw=7000.0, peak_kw=1200.0,
                         nominal_source="default",
                         peak_source="load_model"))
    chk = check_scheme_capacity(scheme, caps, {"F1": 1200.0})
    assert chk.status == CAP_NEEDS_CONFIRMATION


# ---------------------------------------------------------------------------
# ۴) معیار ۴ رتبه‌بندی: Σ (اولویت × بار مدل بار) — همان مبنای ENS
# ---------------------------------------------------------------------------
def _fake_n1(zone_tr_ids):
    zones = [SimpleNamespace(transformer_ids=list(zone_tr_ids))]
    tree = SimpleNamespace(zones=zones)
    return SimpleNamespace(trees={"F1": tree})


def _fake_net(tr_kva):
    return SimpleNamespace(transformers=[
        SimpleNamespace(id=tid, capacity_kva=kva) for tid, kva in tr_kva.items()])


def test_criterion4_load_weighted_uses_load_model_kw():
    st = RankingSettings(criterion4_mode="load_weighted")
    n1 = _fake_n1(["T1", "T2"])
    net = _fake_net({"T1": 400.0, "T2": 100.0})
    prio = {"T1": 2.0, "T2": 5.0}
    # مبنای مدل بار: 3 kW و 700 kW — ظرفیت kVA نادیده گرفته می‌شود
    got = feeder_criterion4(net, n1, "F1", prio, st,
                            load_kw_of_transformer={"T1": 3.0, "T2": 700.0})
    assert got == pytest.approx(2.0 * 3.0 + 5.0 * 700.0)
    # بدون نگاشت بار: رفتار سابق (ظرفیت ترانس) حفظ می‌شود
    got_cap = feeder_criterion4(net, n1, "F1", prio, st)
    assert got_cap == pytest.approx(2.0 * 400.0 + 5.0 * 100.0)


# ---------------------------------------------------------------------------
# ۵) جدول ظرفیت (UI parse): پیک از «ورودی واحد» ساخته می‌شود
# ---------------------------------------------------------------------------
def test_parse_capacity_rows_carries_peak_source():
    from switchloc.ui.qt.settings_dialog import (default_capacity_rows,
                                                 parse_capacity_rows)
    rows = default_capacity_rows(["F1"])
    parsed = parse_capacity_rows(rows)
    assert parsed[0]["peak_kw"] is None
    assert parsed[0]["peak_source"] == "unknown"
    assert parsed[0]["nominal_source"] == "user"
    # ردیف کامل‌شده توسط apply() (پیک = ورودی مدل بار)
    parsed2 = parse_capacity_rows([
        {"feeder_key": "F1", "nominal_kw": "5000", "peak_kw": "1200.0",
         "peak_source": "load_model", "emergency_kw": "", "note": ""}])
    assert parsed2[0]["peak_kw"] == 1200.0
    assert parsed2[0]["peak_source"] == "load_model"
    assert parsed2[0]["nominal_source"] == "user"
