# -*- coding: utf-8 -*-
"""Phase-4 unit tests — feeder ranking (گام ۶: فرمول ۱ + جدول ۱۶).

The V-01 zero-inversion policy and the جدول ۱۶ weights are already
pinned by tests/unit/test_official_anchors.py and test_normalization.py;
here the assembly of the six criteria columns on real structures is
pinned (nothing guessed, defaults registered)."""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from switchloc.domain.entities import Transformer                  # noqa: E402
from switchloc.level1.n_minus_1 import (                           # noqa: E402
    FeederEPTL, NMinusOneResult, ZoneTree)
from switchloc.level1.ranking import (                             # noqa: E402
    RankingSettings, rank_feeders)
from switchloc.reliability.lambdar import FeederLambdaR            # noqa: E402
from switchloc.topology.zones import SwitchZone                    # noqa: E402


def _tree(feeder="FA", trafos=("t1",), caps=(1000.0,)):
    zones = [SwitchZone(id=f"{feeder}Z0", feeder=feeder, zone_no=0,
                        kind="head", source_node="n0",
                        nodes={"n0"}, edges={"e0"},
                        transformer_ids=set(trafos))]
    return ZoneTree(feeder_key=feeder, zones=zones,
                    load_kw={zones[0].id: sum(caps)},
                    parent={zones[0].id: None},
                    children={zones[0].id: []},
                    head_zone=zones[0].id, total_load_kw=sum(caps))


def _n1_result(ties_of=None, ep_tl=None, trees=None):
    return NMinusOneResult(
        rows15=[], eptl=ep_tl or [], connections=[],
        ties_of_feeder=ties_of or {},
        zone_load_kw={}, trees=trees or {}, issues=[],
        settings={})


def _eptl(feeder, ep, tl, load):
    from switchloc.level1.formulas import EPTLResult
    return FeederEPTL(feeder_key=feeder,
                      ep=EPTLResult(ep_percent=ep, tl_percent=tl,
                                    worst_zone="z", total_load_kw=load),
                      total_load_kw=load, zone_count=1)


def _net(caps_by_id):
    return type("N", (), {"transformers": [
        Transformer(node_id="n0", capacity_kva=c, id=t)
        for t, c in caps_by_id.items()],
        "loads": []})()


def test_six_columns_and_rank_order():
    n1 = _n1_result(
        ties_of={"FA": [], "FB": [{"tie_id": "T"}, {"tie_id": "T2"}]},
        ep_tl=[_eptl("FA", 76.0, 24.0, 2500.0),
               _eptl("FB", 30.0, 60.0, 2500.0)],
        trees={"FA": _tree("FA"), "FB": _tree("FB")})
    net = _net({"t1": 1000.0})
    lam = [FeederLambdaR(feeder_key="FA", lambda_per_year=5.0, r_minutes=60.0),
           FeederLambdaR(feeder_key="FB", lambda_per_year=1.0, r_minutes=30.0)]
    res = rank_feeders(n1, net, lam, settings=RankingSettings())
    keys_ranked = [r.feeder_key for r in res.rows]
    assert set(keys_ranked) == {"FA", "FB"}
    # normalised columns sum to 1 (non-zero criteria)
    for j in (1, 3, 4, 5):                        # EP, prio, λ, r
        assert sum(r.norm[j] for r in res.rows) == 1.0 or \
            all(r.norm[j] == 0.0 for r in res.rows)
    # FB has 2 ties → smaller inverse-tie share than FA's 0→10
    fa = next(r for r in res.rows if r.feeder_key == "FA")
    fb = next(r for r in res.rows if r.feeder_key == "FB")
    assert fa.norm[0] > fb.norm[0]                # 10/(10+0.5) > 0.5/(10.5)
    assert fa.raw[0] == 0.0 and fb.raw[0] == 2.0
    assert abs(fa.norm[0] - 10.0 / 10.5) < 1e-9   # V-01 zero→10 policy


def test_zero_ties_get_inverse_ten_policy():
    """V-01: معکوس مقادیر صفر = 10 — applied to criterion 1 only."""
    n1 = _n1_result(
        ties_of={"FA": [], "FB": []},
        ep_tl=[_eptl("FA", 50.0, 10.0, 1000.0),
               _eptl("FB", 50.0, 10.0, 1000.0)],
        trees={"FA": _tree("FA"), "FB": _tree("FB")})
    net = _net({"t1": 1000.0})
    res = rank_feeders(n1, net, None, settings=RankingSettings())
    assert all(r.norm[0] == 0.5 for r in res.rows)   # 10/(10+10)
    assert any(c == "PLAC-TIES-ZERO" for c, _s, _m in res.issues)


def test_missing_lambda_matrix_is_registered_not_invented():
    n1 = _n1_result(
        ep_tl=[_eptl("FA", 50.0, 10.0, 1000.0)],
        trees={"FA": _tree("FA")})
    net = _net({"t1": 1000.0})
    res = rank_feeders(n1, net, None, settings=RankingSettings())
    row = res.rows[0]
    assert row.raw[4] == 0.0 and row.raw[5] == 0.0
    assert any(c == "PLAC-LAMBDA-MISSING" for c, _s, _m in res.issues)
    assert any(c == "PLAC-LOAD-CAT-DEFAULT" for c, _s, _m in res.issues)


def test_weights_of_table16():
    st = RankingSettings()
    assert st.weights == [1, 2, 2, 3, 1, 1]          # A-03 configurable
