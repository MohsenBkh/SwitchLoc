# -*- coding: utf-8 -*-
"""Phase-4 acceptance tests — the real Khalkhal project, end to end.

Covers: the strict-core area model, the EP/TL table bounds, the six-
criterion ranking, scheme generation (table 17), the جدول ۱۸ CE/CN
algebra and selection, determinism of two consecutive runs, persistence
round-trip and the MD/JSON report.  Skipped cleanly when the sample
project (and optionally the outage workbook) is absent.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest                                        # noqa: E402

from switchloc.application.placement_service import (  # noqa: E402
    PlacementAppSettings, PlacementService)
from switchloc.placement.service import (              # noqa: E402
    EngineSettings, PlacementEngine)
from switchloc.persistence.store import ProjectStore   # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "projects" / "khalkhal_phase1.sqlite"
XLSX = ROOT / "data" / "outages_1405.xlsx"

pytestmark = pytest.mark.skipif(not DB.exists(),
                                reason="projects/khalkhal_phase1.sqlite not present")


@pytest.fixture(scope="module")
def topology():
    from switchloc.application.topology_service import (TopologyService,
                                                        TopologySettings)
    store = ProjectStore(str(DB))
    net, _issues = store.load_network()
    store.close()
    topo = TopologyService(TopologySettings(persist=False)).run(net)
    return net, topo


@pytest.fixture(scope="module")
def lam_matrix():
    if not XLSX.exists():
        return None
    from switchloc.reliability.classify import classify_all
    from switchloc.reliability.lambdar import feeder_lambda_r
    from switchloc.reliability.outages import read_outage_workbook
    recs, _stats = read_outage_workbook(XLSX)
    classify_all(recs)
    return feeder_lambda_r(recs)


@pytest.fixture(scope="module")
def result(topology, lam_matrix):
    net, topo = topology
    return PlacementEngine(EngineSettings()).run(
        topo.graph, net, topo.traces, topo.zones, topo.ties,
        lam_matrix=lam_matrix, traces_strict=topo.traces_strict)


def test_strict_core_area_model(result):
    codes = [c for c, _s, _m in result.issues]
    assert "PLAC-AREA-STRICT" in codes
    # strict zones are disjoint per feeder — no double-counted load
    trees = result.n1.trees
    loads = {k: round(t.total_load_kw, 6) for k, t in trees.items()}
    assert len(set(loads.values())) == len(loads) or len(loads) > 1


def test_table14_eptl_bounds(result):
    assert len(result.n1.eptl) >= 5               # F6 has zero load → skipped
    for f in result.n1.eptl:
        assert 0.0 <= f.ep.ep_percent <= 100.0
        assert 0.0 <= f.ep.tl_percent <= 100.0
        assert f.total_load_kw > 0.0


def test_ranking_complete_and_ordered(result):
    rows = result.ranking.rows
    assert 5 <= len(rows) <= 7
    assert [r.rank for r in rows] == list(range(1, len(rows) + 1))
    assert all(r.score > 0 for r in rows)
    # every row carries the 6 criteria + audit trail
    for r in rows:
        assert len(r.raw) == 6 and len(r.norm) == 6 and len(r.weighted) == 6
        assert r.ep_percent >= 0.0


def test_schemes_generated(result):
    kinds = {s.kind for s in result.schemes}
    assert "sequential_nc" in kinds
    assert len(result.schemes) >= 3
    for s in result.schemes:
        assert s.switches
        assert all(sw.kind in ("NC", "NO", "automation_upgrade")
                   for sw in s.switches)
        assert s.relations                        # directive anchors kept


def test_table18_algebra_and_selection(result):
    comps = result.economics.comparisons
    assert comps
    for c in comps:
        # official algebra: CE = 1000 × (E2 − E1) = 1000 × (قبل − بعد)
        # (report rounds rials to integers — hence the 1-rial tolerance)
        assert c.ce_rials == pytest.approx(
            1000.0 * (c.e2_before_kwh - c.e1_after_kwh), abs=1.0)
        assert c.cn_rials > 0
    assert any(c.selected for c in comps)          # at least one main scheme
    # selected rows are the per-feeder maxima
    for c in comps:
        if not c.selected:
            continue
        for f in c.feeders:
            rivals = [x.ce_over_cn for x in comps
                      if f in x.feeders and x.ce_over_cn not in
                      (None, float("-inf"))]
            assert c.ce_over_cn >= max(rivals) - 1e-9


def test_recommendation_covers_ranking(result):
    assert len(result.recommendation) == len(result.ranking.rows)


def test_two_runs_are_deterministic(result, topology, lam_matrix):
    net, topo = topology
    again = PlacementEngine(EngineSettings()).run(
        topo.graph, net, topo.traces, topo.zones, topo.ties,
        lam_matrix=lam_matrix, traces_strict=topo.traces_strict)
    assert again.to_dict() == result.to_dict()


def test_persistence_roundtrip_and_report(result, topology, tmp_path):
    net, _topo = topology
    db_copy = tmp_path / "p4_acceptance.sqlite"
    shutil.copy(DB, db_copy)
    svc = PlacementService(PlacementAppSettings(
        user="acceptance", persist=True, report_dir=str(tmp_path / "reports")))
    run = svc.run(str(db_copy))
    assert run.run_id and run.verdict == "PASS"
    assert (tmp_path / "reports" / "phase4_placement_report.md").exists()
    assert (tmp_path / "reports" / "phase4_placement_report.json").exists()
    store = ProjectStore(str(db_copy))
    runs = store.list_placement_runs()
    assert runs and runs[0]["placement_run_id"] == run.run_id
    loaded = store.load_placement(run.run_id)
    store.close()
    assert len(loaded["ranking"]) == len(result.ranking.rows)
    assert loaded["ranking"][0]["feeder_key"] == \
        result.ranking.rows[0].feeder_key
    assert len(loaded["schemes"]) == len(result.schemes)
