# -*- coding: utf-8 -*-
"""Phase 2 — persistence tests (segments roundtrip, topology tables)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from switchloc.domain.entities import StudyRunMeta
from switchloc.persistence.store import ProjectStore
from switchloc.validation.issues import IssueLog

from conftest import NetBuilder


def _save(tmp_path, b):
    db = tmp_path / "p2.sqlite"
    store = ProjectStore(db)
    run = StudyRunMeta(project_name="p2-test", started_at="2026-10-31T10:00:00",
                       user="tester", algo_version="switchloc 1.2.0")
    run_id = store.save_network(b.net, IssueLog(), run)
    store.close()
    return db, run_id


def test_branch_segments_survive_roundtrip(tmp_path):
    """The Phase-2 graph NEEDS segments from the DB (edge splitting)."""
    b = NetBuilder()
    b.line([(0, 0), (40, 0), (40, 30), (80, 30)], feeder="F1")
    db, run_id = _save(tmp_path, b)
    store = ProjectStore(db)
    net, _ = store.load_network(run_id)
    store.close()
    assert sum(len(br.segments) for br in net.branches) == 3
    seg = net.branches[0].segments[0]
    assert seg.a == (0.0, 0.0) and seg.b == (40.0, 0.0)


def test_topology_save_load_roundtrip(tmp_path):
    from switchloc.application.topology_service import (TopologyService,
                                                        TopologySettings)
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    b.switch(50, 0)
    db, run_id = _save(tmp_path, b)
    res = TopologyService(TopologySettings(user="tester")).run(
        b.net, source_run_id=run_id, out_db=str(db))
    assert res.topo_run_id

    store = ProjectStore(db)
    runs = store.list_topo_runs()
    assert len(runs) == 1 and runs[0]["verdict"] == "PASS"
    loaded = store.load_topology(res.topo_run_id)
    store.close()
    assert loaded["topo_run_id"] == res.topo_run_id
    assert loaded["summary"]["topology"]["zones"]["zone_count"] == \
        len(res.zones.zones)
    assert len(loaded["zones"]) == len(res.zones.zones)
    assert len(loaded["boundaries"]) == len(res.zones.boundaries)
    zone_rows = {z["feeder"] + str(z["zone_no"]) for z in loaded["zones"]}
    assert "F10" in zone_rows


def test_topology_persistence_is_deterministic(tmp_path):
    from switchloc.application.topology_service import (TopologyService,
                                                        TopologySettings)
    def build_and_run(db):
        b = NetBuilder()
        b.source(0, 0, "F1")
        b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
        b.switch(50, 0)
        store = ProjectStore(db)
        run = StudyRunMeta(project_name="det", started_at="2026-10-31T10:00:00",
                           user="tester", algo_version="switchloc 1.2.0")
        run_id = store.save_network(b.net, IssueLog(), run)
        store.close()
        res = TopologyService(TopologySettings(user="tester")).run(
            b.net, source_run_id=run_id, out_db=str(db))
        return res.topo_run_id

    id1 = build_and_run(tmp_path / "a.sqlite")
    id2 = build_and_run(tmp_path / "b.sqlite")
    assert id1 == id2                     # identical inputs → identical id
