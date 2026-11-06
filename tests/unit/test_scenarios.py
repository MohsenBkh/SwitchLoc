# -*- coding: utf-8 -*-
"""Phase 2 — scenario model tests (base state, actions, connectivity)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from switchloc.domain.enums import SwitchState
from switchloc.scenarios.base import (SwitchScenario, base_state, evaluate,
                                      isolation_scenario)
from switchloc.topology.graph import NetworkGraph
from switchloc.topology.tracing import TracingEngine, TracingPolicy
from switchloc.topology.zones import ZoneBuilder
from switchloc.validation.issues import IssueLog

from conftest import NetBuilder


def _full(b):
    issues = IssueLog()
    g = NetworkGraph.from_network(b.net, IssueLog())
    traces = TracingEngine(g, b.net, TracingPolicy()).trace_all(IssueLog())
    zones = ZoneBuilder(g, b.net, traces).build(issues)
    return g, zones, issues


def test_base_state_from_gis_states():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    sw_out = b.switch(50, 0, state=SwitchState.OUT_OF_SERVICE)
    state = base_state(b.net)
    assert state.is_open(sw_out.id)


def test_normal_evaluation_energizes_all_with_unknown_pass():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    b.switch(50, 0, state=SwitchState.UNKNOWN)    # TOPO-POL-01: passes
    g, zones, issues = _full(b)
    scen = SwitchScenario("normal", base_state(b.net))
    conn = evaluate(g, b.net, scen, zone_of_edge=zones.zone_of_edge)
    assert conn.summary()["deenergized_edges"] == 0
    assert set(conn.energized_by_feeder) == {"F1"}


def test_open_action_isolates_downstream_zone():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    sw = b.switch(50, 0)
    b.transformer(100, 0)
    g, zones, issues = _full(b)
    scen = SwitchScenario("manoeuvre", base_state(b.net))
    scen.add_action(sw.id, "open", reason_fa="آزمایش جداسازی", user="t")
    conn = evaluate(g, b.net, scen, zone_of_edge=zones.zone_of_edge)
    s = conn.summary()
    assert s["deenergized_edges"] == 1            # the downstream edge
    assert s["isolated_zones"] == 1               # Zone1 fully dead


def test_close_action_restores():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    sw = b.switch(50, 0, normally="NO")           # NO → open in base
    g, zones, issues = _full(b)
    conn_dead = evaluate(g, b.net, SwitchScenario("normal", base_state(b.net)),
                         zone_of_edge=zones.zone_of_edge)
    assert conn_dead.summary()["deenergized_edges"] == 1
    scen = SwitchScenario("tie-closed", base_state(b.net))
    scen.add_action(sw.id, "close", reason_fa="بستن Tie برای انتقال بار",
                    user="t")
    conn_live = evaluate(g, b.net, scen, zone_of_edge=zones.zone_of_edge)
    assert conn_live.summary()["deenergized_edges"] == 0


def test_action_on_unknown_switch_is_flagged():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (100, 0)], feeder="F1")
    g, zones, issues = _full(b)
    scen = SwitchScenario("bad", base_state(b.net))
    scen.add_action("no-such-switch", "open", user="t")
    issues2 = IssueLog()
    evaluate(g, b.net, scen, zone_of_edge=zones.zone_of_edge, issues=issues2)
    assert issues2.by_code("SCEN-ACTION-UNKNOWN-SWITCH")


def test_isolation_scenario_opens_zone_boundaries():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    b.switch(50, 0)
    g, zones, issues = _full(b)
    zone1 = zones.zones_of_feeder("F1")[1]
    scen = isolation_scenario(g, b.net, zone1.id, zones.zone_of_edge,
                              zones.boundary_of_switch, "isolate-Z1",
                              user="t")
    opened = [a.switch_id for a in scen.actions if a.action == "open"]
    assert opened == [  # the zone's only boundary switch
        list(zones.boundary_of_switch)[0]]
    conn = evaluate(g, b.net, scen, zone_of_edge=zones.zone_of_edge)
    assert conn.summary()["isolated_zones"] == 1


def test_scenario_effective_state_is_ordered():
    b = NetBuilder()
    state = base_state(b.net)
    scen = SwitchScenario("seq", state)
    scen.add_action("s1", "open")
    scen.add_action("s1", "close")
    eff = scen.effective_state()
    assert eff.is_closed("s1")                    # last action wins
    scen.add_action("s1", "open")
    assert scen.effective_state().is_open("s1")
