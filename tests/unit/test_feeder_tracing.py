# -*- coding: utf-8 -*-
"""Phase 2 — normal-state feeder tracing tests (TOPO-POL-01/02)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from switchloc.domain.enums import SwitchFamily, SwitchState, YesNoUnknown
from switchloc.topology.graph import NetworkGraph
from switchloc.topology.tracing import (TracingEngine, TracingPolicy,
                                        feeder_key)
from switchloc.validation.issues import IssueLog

from conftest import NetBuilder


def _graph(b):
    return NetworkGraph.from_network(b.net, IssueLog())


def test_feeder_key_normalization():
    assert feeder_key("F1 - KHALKHAL") == "F1"
    assert feeder_key("f5") == "F5"
    assert feeder_key("") == ""
    assert feeder_key("F5 - KOLOOR") == "F5"


def test_single_feeder_traces_whole_line():
    b = NetBuilder()
    b.source(0, 0, "F1 - KHALKHAL")
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.transformer(100, 0)
    g = _graph(b)
    eng = TracingEngine(g, b.net, TracingPolicy())
    traces = eng.trace_all(IssueLog())
    assert len(traces) == 1
    tr = traces[0]
    assert tr.feeder_key == "F1 - KHALKHAL"
    assert len(tr.edges) == 1
    assert len(tr.transformer_ids) == 1
    assert abs(tr.length_m - 100.0) < 1e-6


def test_no_switch_passes_and_no_switch_blocks():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    b.switch(50, 0, normally="NO")                # confirmed normally-open
    issues = IssueLog()
    traces = TracingEngine(_graph(b), b.net,
                           TracingPolicy()).trace_all(issues)
    assert len(traces[0].edges) == 1              # only up to the NO switch
    assert issues.count("Warning") >= 1           # TOPO-UNTRACED-AREA


def test_out_of_service_switch_blocks_by_policy():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    b.switch(50, 0, state=SwitchState.OUT_OF_SERVICE)
    traces = TracingEngine(_graph(b), b.net,
                           TracingPolicy()).trace_all(IssueLog())
    assert len(traces[0].edges) == 1


def test_unknown_state_policy_is_explicit():
    def build():
        b = NetBuilder()
        b.source(0, 0, "F1")
        b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
        b.switch(50, 0, state=SwitchState.UNKNOWN)
        return b

    # TOPO-POL-01 default: pass (with the phase-1 issue already recorded)
    b = build()
    traces = TracingEngine(_graph(b), b.net, TracingPolicy()).trace_all(
        IssueLog())
    assert len(traces[0].edges) == 2
    # strict variant: unknown = open
    b = build()
    traces = TracingEngine(_graph(b), b.net, TracingPolicy(
        unknown_switch_pass=False)).trace_all(IssueLog())
    assert len(traces[0].edges) == 1


def test_two_feeders_meeting_produce_overlap():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.source(200, 0, "F2")
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.line([(100, 0), (200, 0)], feeder="F2")
    traces = TracingEngine(_graph(b), b.net,
                           TracingPolicy()).trace_all(IssueLog())
    by_key = {t.feeder_key: t for t in traces}
    assert set(by_key) == {"F1", "F2"}
    assert by_key["F1"].overlaps and by_key["F2"].overlaps


def test_gis_label_mismatch_reported():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (100, 0)], feeder="F9")       # wrong label in GIS
    issues = IssueLog()
    TracingEngine(_graph(b), b.net, TracingPolicy()).trace_all(issues)
    mism = issues.by_code("TOPO-FEEDER-MISMATCH")
    assert len(mism) == 1
    assert "F9" in mism[0].message_fa


def test_fallback_seeds_from_breakers():
    b = NetBuilder()
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.switch(0, 0, family=SwitchFamily.BREAKER, feeder="F1",
             layer="ELWCBR")
    issues = IssueLog()
    traces = TracingEngine(_graph(b), b.net,
                           TracingPolicy()).trace_all(issues)
    # این سناریو نام خام «F1» دارد (بدون پسوند) → شناسه همان «F1» است
    assert traces and traces[0].feeder_key == "F1"
    assert issues.by_code("TOPO-FALLBACK-SEEDS")


def test_no_source_at_all_is_an_error():
    b = NetBuilder()
    b.line([(0, 0), (100, 0)], feeder="F1")
    issues = IssueLog()
    traces = TracingEngine(_graph(b), b.net,
                           TracingPolicy()).trace_all(issues)
    assert traces == []
    assert issues.by_code("TOPO-NO-SOURCE")
    assert issues.has_errors()


def test_remote_flag_carried_for_tie_automation():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (100, 0)], feeder="F1")
    sw = b.switch(100, 0, remote=YesNoUnknown.YES)
    assert sw.remote_controlled == YesNoUnknown.YES


def test_feeder_key_normalizes_hyphenated_suffixes():
    assert feeder_key("F4- KOSAR") == "F4"
    assert feeder_key("F4-KOSAR") == "F4"
    assert feeder_key("F4 - KOSAR") == "F4"
