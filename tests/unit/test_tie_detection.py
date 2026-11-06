# -*- coding: utf-8 -*-
"""Phase 2 — A-09 NO/Tie detection tests (rules R1/R2 + confirmation)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from switchloc.domain.enums import YesNoUnknown
from switchloc.topology.graph import NetworkGraph
from switchloc.topology.ties import (TieDetectionPolicy, TieDetectionService)
from switchloc.topology.tracing import TracingEngine, TracingPolicy
from switchloc.validation.issues import IssueLog

from conftest import NetBuilder


def _detect(b, policy=None):
    issues = IssueLog()
    g = NetworkGraph.from_network(b.net, IssueLog())
    eng = TracingEngine(g, b.net, TracingPolicy())
    traces = eng.trace_all(issues)
    svc = TieDetectionService(g, b.net, traces, eng, policy)
    cands = svc.detect(issues)
    return svc, cands, issues, g


def test_r1_candidate_at_switch_between_two_feeders():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.source(200, 0, "F2")
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.line([(100, 0), (200, 0)], feeder="F2")
    b.switch(100, 0, remote=YesNoUnknown.YES)
    svc, cands, issues, g = _detect(b)
    r1 = [c for c in cands if c.rule == "R1-overlap"]
    assert len(r1) == 1
    assert r1[0].feeder_a == "F1" and r1[0].feeder_b == "F2"
    assert r1[0].automation_capable is True
    assert issues.by_code("TOPO-TIE-CANDIDATES")


def test_r1_without_switch_is_not_proposed():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.source(200, 0, "F2")
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.line([(100, 0), (200, 0)], feeder="F2")     # no switch at the meeting node
    svc, cands, issues, g = _detect(b)
    assert [c for c in cands if c.rule == "R1-overlap"] == []


def test_ranking_prefers_clean_boundary_and_cap():
    """Many overlapping nodes → only the best max_candidates are proposed;
    the rest stays in aggregate statistics.

    TOPO-POL-05 note: the middle corridor is UNLABELLED, so both feeders
    legitimately traverse it (a labelled corridor would be gated to its
    owner and the feeders would never overlap there)."""
    policy = TieDetectionPolicy(max_candidates=2)
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.source(300, 0, "F2")
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.line([(100, 0), (200, 0)])                  # unlabeled shared corridor
    b.line([(200, 0), (300, 0)], feeder="F2")
    b.switch(100, 0)
    b.switch(150, 0)
    b.switch(200, 0)
    svc, cands, issues, g = _detect(b, policy)
    assert len([c for c in cands if c.rule == "R1-overlap"]) == 2
    assert svc.overlap_stats["overlap_nodes"] > 0
    assert issues.by_code("TOPO-FEEDER-INTERCONNECTED")


def test_confirm_sets_no_and_resolves_overlap():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.source(200, 0, "F2")
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.line([(100, 0), (200, 0)], feeder="F2")
    b.switch(100, 0)
    svc, cands, issues, g = _detect(b)
    cand = cands[0]
    assert svc.confirm(cand.id, user="engineer-1", issues=issues) is True
    sw = next(s for s in b.net.switches if s.id == cand.switch_id)
    assert sw.normally_state == "NO"
    assert cand.status == "confirmed"
    assert svc.verified_after_confirmation() is True
    assert issues.by_code("TOPO-TIE-CONFIRMED")


def test_reject_keeps_switch_untouched():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.source(200, 0, "F2")
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.line([(100, 0), (200, 0)], feeder="F2")
    b.switch(100, 0)
    svc, cands, issues, g = _detect(b)
    cand = cands[0]
    assert svc.reject(cand.id, user="engineer-1", issues=issues) is True
    sw = next(s for s in b.net.switches if s.id == cand.switch_id)
    assert sw.normally_state == ""                # untouched
    assert cand.status == "rejected"
    assert issues.by_code("TOPO-TIE-REJECTED")


def test_r2_label_mismatch_off_overlap_nodes():
    """A switch labelled with another feeder, sitting on a line vertex of
    a cleanly traced area (no overlap) → R2 candidate."""
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")   # vertex at the switch
    b.switch(50, 0, feeder="F5")                  # label disagrees, no overlap
    svc, cands, issues, g = _detect(b)
    r2 = [c for c in cands if c.rule == "R2-label"]
    assert len(r2) == 1
    assert {r2[0].feeder_a, r2[0].feeder_b} == {"F1", "F5"}


def test_r2_suppressed_on_overlap_nodes():
    """On an overlap node R1 already speaks; R2 must stay silent."""
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.source(200, 0, "F2")
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.line([(100, 0), (200, 0)], feeder="F2")
    b.switch(100, 0, feeder="F2")
    svc, cands, issues, g = _detect(b)
    assert not [c for c in cands if c.rule == "R2-label"]


def test_tie_entities_carry_status():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.source(200, 0, "F2")
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.line([(100, 0), (200, 0)], feeder="F2")
    b.switch(100, 0)
    svc, cands, issues, g = _detect(b)
    entities = svc.to_tie_entities()
    assert len(entities) == len(cands)
    assert entities[0].status == "candidate"
    assert entities[0].automation_capable in (True, False)
