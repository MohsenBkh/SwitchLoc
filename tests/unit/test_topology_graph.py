# -*- coding: utf-8 -*-
"""Phase 2 — NetworkGraph tests (edge splitting at device vertices, TG-03)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from switchloc.domain.enums import NodeKind, SwitchFamily, SwitchState
from switchloc.topology.graph import NetworkGraph
from switchloc.validation.issues import IssueLog

from conftest import NetBuilder


def test_graph_splits_line_at_mid_device_vertex():
    """A switch on a mid-line vertex cuts the branch into two edges —
    the GeoGrid splice behaviour, re-implemented (TG-03)."""
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (100, 0), (200, 0)], feeder="F1")
    b.switch(100, 0)                              # mid-vertex switch
    issues = IssueLog()
    g = NetworkGraph.from_network(b.net, issues)
    assert g.stats["edges"] == 2
    mid = [n for n, nd in g.nodes.items() if nd.coord == (100.0, 0.0)][0]
    assert g.has_switch(mid)
    # both edges touch the mid node
    assert {eid for _, eid in g.adj[mid]} and len(g.adj[mid]) == 2


def test_graph_parallel_edges_kept():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (10, 0)], feeder="F1")
    b.line([(0, 0), (10, 0)], feeder="F1")        # parallel duplicate
    g = NetworkGraph.from_network(b.net, IssueLog())
    assert g.stats["edges"] == 2
    a = [n for n, nd in g.nodes.items()
         if nd.coord == (0.0, 0.0) and nd.kind == NodeKind.JUNCTION][0]
    assert len(g.adj[a]) == 2


def test_graph_skips_excluded_branches_and_counts():
    b = NetBuilder()
    b.source(0, 0, "F1")
    br = b.line([(0, 0), (50, 0)], feeder="F1")
    br.excluded_with_issue = True
    b.line([(50, 0), (100, 0)], feeder="F1")
    g = NetworkGraph.from_network(b.net, IssueLog())
    assert g.stats["branches_skipped_excluded"] == 1
    assert g.stats["edges"] == 1


def test_source_attachment_records_distance():
    b = NetBuilder()
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.source(0.5, 0, "F1")                        # 0.5 m off the junction
    issues = IssueLog()
    g = NetworkGraph.from_network(b.net, issues)
    assert g.stats["sources"] == 1
    attached = list(g.source_of.values())
    assert attached == ["F1"]
    dist = list(g.source_attach.values())[0][1]
    assert 0 < dist <= 0.6
    assert len(issues.by_code("TOPO-SOURCE-ATTACHED")) == 1


def test_isolated_source_flagged_as_warning():
    b = NetBuilder()
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.source(5000, 5000, "F1")                    # far away → no attachment
    issues = IssueLog()
    g = NetworkGraph.from_network(b.net, issues)
    assert g.stats["sources"] == 0
    assert len(issues.by_code("TOPO-SOURCE-ISOLATED")) == 1


def test_devices_and_transformers_attached_to_nodes():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (100, 0)], feeder="F1")
    b.transformer(100, 0, 400)
    g = NetworkGraph.from_network(b.net, IssueLog())
    end = [n for n, nd in g.nodes.items() if nd.coord == (100.0, 0.0)][0]
    assert len(g.transformer_ids_at[end]) == 1
    assert len(g.load_ids_at[end]) == 1


def test_graph_build_is_deterministic():
    def build():
        b = NetBuilder()
        b.source(0, 0, "F1")
        b.line([(0, 0), (30, 0), (60, 10)], feeder="F1")
        b.line([(60, 10), (90, 10)], feeder="F1")
        b.switch(30, 0)
        return NetworkGraph.from_network(b.net, IssueLog())

    g1, g2 = build(), build()
    assert g1.stats == g2.stats
    assert sorted(g1.edges) == sorted(g2.edges)
    assert [e.length_m for e in g1.edges.values()] == \
           [e.length_m for e in g2.edges.values()]


def test_length_preserved_after_split():
    """Σ edge lengths == Σ segment lengths (GG-03 companion)."""
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (40, 0), (40, 30), (80, 30)], feeder="F1", registered=100.0)
    g = NetworkGraph.from_network(b.net, IssueLog())
    assert sum(e.length_m for e in g.edges.values()) == 100.0


def test_source_node_kind_present_in_graph():
    b = NetBuilder()
    b.source(0, 0, "F1")
    g = NetworkGraph.from_network(b.net, IssueLog())
    assert any(nd.kind == NodeKind.SOURCE for nd in g.nodes.values())
