# -*- coding: utf-8 -*-
"""Phase 2 — زون‌بندی tests (تعریف ۵-۲۱، جدول ۱۵ numbering, policies)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from switchloc.domain.enums import SwitchFamily, SwitchState
from switchloc.topology.graph import NetworkGraph
from switchloc.topology.tracing import TracingEngine, TracingPolicy
from switchloc.topology.zones import ZoneBuilder, ZonePolicy
from switchloc.validation.issues import IssueLog

from conftest import NetBuilder


def _zones(b, policy: ZonePolicy | None = None):
    issues = IssueLog()
    g = NetworkGraph.from_network(b.net, IssueLog())
    traces = TracingEngine(g, b.net, TracingPolicy()).trace_all(
        IssueLog())
    zb = ZoneBuilder(g, b.net, traces, policy)
    return zb.build(issues), g, traces, issues


def test_two_zones_bounded_by_one_switch():
    """source — line — switch — line  ⇒  Zone0 + Zone1 (تعریف ۵-۲۱)."""
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    b.switch(50, 0)
    res, g, traces, issues = _zones(b)
    zf = res.zones_of_feeder("F1")
    assert len(zf) == 2
    assert zf[0].zone_no == 0 and zf[0].kind == "head"
    assert zf[0].source_node is not None
    assert zf[1].zone_no == 1
    # boundary switch separates both zones
    br = res.boundary_of_switch[  # the only boundary device
        list(res.boundary_of_switch)[0]]
    assert len(br.zones) == 2
    assert {z.zone_no for z in zf} == {0, 1}


def test_zone_stats_carry_length_and_transformers():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    b.switch(50, 0)
    b.transformer(100, 0, 630)
    res, g, traces, issues = _zones(b)
    zf = res.zones_of_feeder("F1")
    assert abs(zf[0].length_m - 50.0) < 1e-6
    assert len(zf[1].transformer_ids) == 1
    assert len(zf[1].load_ids) == 1


def test_no_switch_separates_feeders_zones():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.source(200, 0, "F2")
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.line([(100, 0), (200, 0)], feeder="F2")
    b.switch(100, 0, normally="NO")               # confirmed NO
    res, g, traces, issues = _zones(b)
    f1 = res.zones_of_feeder("F1")
    f2 = res.zones_of_feeder("F2")
    assert all(len(z.edges) == 1 for z in f1 + f2)
    # the NO boundary is recorded as open
    assert any(br.open_normal for br in res.boundaries)


def test_fuse_policy_toggle():
    def build():
        b = NetBuilder()
        b.source(0, 0, "F1")
        b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
        b.switch(50, 0, family=SwitchFamily.FUSE_CUTOUT)
        return b

    # TOPO-POL-03 default: fuse does NOT bound zones
    res, *_ = _zones(build(), ZonePolicy())
    assert len(res.zones_of_feeder("F1")) == 1
    # explicit toggle: fuse bounds zones
    res, *_ = _zones(build(), ZonePolicy(include_fuse_cutout=True))
    assert len(res.zones_of_feeder("F1")) == 2


def test_untraced_area_becomes_island():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0)], feeder="F1")
    b.line([(500, 500), (600, 500)], feeder="F9")   # disconnected island
    res, g, traces, issues = _zones(b)
    islands = [z for z in res.zones if z.kind == "island"]
    assert len(islands) == 1
    assert islands[0].feeder == ""


def test_branchy_boundary_flagged():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0)], feeder="F1")
    b.line([(50, 0), (100, 0)], feeder="F1")
    b.line([(50, 0), (50, 100)], feeder="F1")       # third line end at switch
    b.switch(50, 0)
    res, g, traces, issues = _zones(b)
    assert any(br.branchy for br in res.boundaries)
    assert issues.by_code("TOPO-SWITCH-NODE-BRANCHY")


def test_zone_ids_deterministic():
    def build():
        b = NetBuilder()
        b.source(0, 0, "F1")
        b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
        b.switch(50, 0)
        return b

    r1, *_ = _zones(build())
    r2, *_ = _zones(build())
    assert [z.id for z in r1.zones] == [z.id for z in r2.zones]
    assert [z.zone_no for z in r1.zones_of_feeder("F1")] == [0, 1]


def test_out_of_service_boundary_is_open():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    b.switch(50, 0, state=SwitchState.OUT_OF_SERVICE)
    res, g, traces, issues = _zones(b)
    assert res.as_dict()["open_boundaries"] == 1
