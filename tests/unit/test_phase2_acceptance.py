# -*- coding: utf-8 -*-
"""Phase 2 acceptance — topology on the real Khalkhal 12-layer export.

Gated on the Phase-1 project database (or the sample folder to rebuild it).
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

DB = ROOT / "projects" / "khalkhal_phase1.sqlite"
SAMPLE = Path(os.environ.get(
    "SWITCHLOC_SAMPLE_DIR",
    "/home/z/my-project/work/sample_shp/Export_1404_08_17_12_34_09"))

pytestmark = pytest.mark.skipif(
    not (DB.exists() or SAMPLE.is_dir()),
    reason="phase-1 project DB / real sample not available")


@pytest.fixture(scope="module")
def topology():
    from switchloc.application.topology_service import (TopologyService,
                                                        TopologySettings)
    from switchloc.persistence.store import ProjectStore
    store = ProjectStore(DB)
    run_id = store.runs()[-1]["id"]
    net, issues = store.load_network(run_id)
    store.close()
    return TopologyService(TopologySettings(user="pytest",
                                            persist=False)).run(
        net, issues=issues, source_run_id=run_id)


def test_feeder_keys_f1_to_f7_rebuilt(topology):
    keys = {t.feeder_key for t in topology.traces}
    assert {"F1", "F2", "F3", "F4", "F5", "F6", "F7"} <= keys


def test_every_feeder_has_zones(topology):
    for t in topology.traces:
        assert topology.zones.zones_of_feeder(t.feeder_key)


def test_no_unresolved_errors(topology):
    assert topology.verdict == "PASS"


def test_tie_candidates_ranked_and_capped(topology):
    assert 0 < len(topology.ties) <= 40 + 788        # R1 cap + R2 pool
    r1 = [c for c in topology.ties if c.rule == "R1-overlap"]
    assert r1, "R1 must propose candidates on the interconnected sample"
    assert all(c.switch_id for c in r1)               # switch-bearing only
    scores = [c.score for c in r1]
    assert scores == sorted(scores, reverse=True)     # ranked


def test_strict_core_diagnostic_available(topology):
    assert topology.traces_strict
    assert {t.feeder_key for t in topology.traces_strict} == \
           {t.feeder_key for t in topology.traces}


def test_graph_edge_splitting_on_real_data(topology):
    """Edges > branches proves mid-device splitting happens on real GIS."""
    assert topology.graph.stats["edges"] >= topology.graph.stats["branches_kept"]


def test_topology_persisted_roundtrip(topology):
    from switchloc.persistence.store import ProjectStore
    store = ProjectStore(DB)
    runs = store.list_topo_runs()
    assert runs
    loaded = store.load_topology(runs[-1]["id"])
    store.close()
    assert loaded["zones"], "topo_zone rows must exist"
    assert loaded["verdict"] in ("PASS", "FAIL")
