# -*- coding: utf-8 -*-
"""TopologyService — orchestration of the Phase-2 engine (ARCHITECTURE §۵).

Pipeline:
  CanonicalNetwork (in-memory or loaded from SQLite) → NetworkGraph →
  normal-state tracing → tie/NO candidates (A-09) → زون‌بندی → base
  scenario + connectivity → QC issues → persistence + Persian report.

The service never mutates the canonical model; the only auditable
mutations are the engineer's tie confirmations (switch.normally_state).
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from datetime import datetime

from .. import APP_NAME, TAV_REFERENCE, __version__
from ..domain.entities import CanonicalNetwork
from ..persistence.store import ProjectStore
from ..scenarios.base import (ConnectivityResult, SwitchScenario, base_state,
                              evaluate)
from ..topology.graph import (DEFAULT_MATCH_TOL_M,
                              DEFAULT_SOURCE_ATTACH_TOL_M, NetworkGraph)
from ..topology.ties import TieDetectionService
from ..topology.tracing import TracingEngine, TracingPolicy
from ..topology.zones import ZoneBuilder, ZonePolicy, ZoneResult
from ..validation.issues import (IssueLog, ValidationIssue, SEVERITY_ERROR,
                                 SEVERITY_INFO, SEVERITY_WARNING)
from ..validation.qc import QcReport, run_qc


@dataclass
class TopologySettings:
    user: str = "unknown"
    match_tol_m: float = DEFAULT_MATCH_TOL_M
    source_attach_tol_m: float = DEFAULT_SOURCE_ATTACH_TOL_M
    unknown_switch_pass: bool = True            # TOPO-POL-01
    out_of_service_blocks: bool = True
    include_fuse_cutout_as_boundary: bool = False   # TOPO-POL-03
    #: TOPO-POL-05 — GIS feeder labels gate the traversal (no NO/NC flags
    #: in the export → without the gate feeders flood into each other)
    hint_gated_tracing: bool = True
    persist: bool = True


@dataclass
class TopologyResult:
    graph: NetworkGraph
    traces: list
    ties: list
    zones: ZoneResult
    scenario: SwitchScenario
    connectivity: ConnectivityResult
    issues: IssueLog
    report: QcReport
    settings: dict
    topo_run_id: str | None = None
    traces_strict: list = dc_field(default_factory=list)   # diagnostic core

    @property
    def verdict(self) -> str:
        return self.report.verdict


class TopologyService:
    def __init__(self, settings: TopologySettings | None = None):
        self.settings = settings or TopologySettings()

    # ------------------------------------------------------------------
    def run(self, net: CanonicalNetwork, issues: IssueLog | None = None,
            source_run_id: str = "", out_db: str | None = None,
            zone_of_edge_hint: dict | None = None) -> TopologyResult:
        st = self.settings
        topo_issues = issues if issues is not None else IssueLog()

        # 1) graph -------------------------------------------------------
        graph = NetworkGraph.from_network(
            net, issues=topo_issues,
            match_tol_m=st.match_tol_m,
            source_attach_tol_m=st.source_attach_tol_m)

        # 2) normal-state tracing ----------------------------------------
        policy = TracingPolicy(unknown_switch_pass=st.unknown_switch_pass,
                               out_of_service_blocks=st.out_of_service_blocks,
                               hint_gated=st.hint_gated_tracing)
        tracing = TracingEngine(graph, net, policy)
        traces = tracing.trace_all(topo_issues)

        # 2b) strict-core diagnostic (unknown switches = open) — a second
        # look that shows the *guaranteed* core of each feeder while the
        # NO points of A-09 are unconfirmed; never pollutes QC issues.
        strict_scratch = IssueLog()
        traces_strict = TracingEngine(graph, net, TracingPolicy(
            unknown_switch_pass=False,
            out_of_service_blocks=st.out_of_service_blocks)).trace_all(
            strict_scratch, quiet=True)
        topo_issues.add(ValidationIssue(
            code="TOPO-STRICT-CORE", severity=SEVERITY_INFO,
            message_fa="هسته قطعی فیدرها (با فرض باز بودن کلیدهای با وضعیت "
                       "نامشخص) نیز محاسبه شد — سنجه کمکی برای تصمیم A-09.",
            impact_fa="جزئیات در گزارش فاز ۲؛ در پذیرش لحاظ نشده است.",
            meta={t.feeder_key: {"nodes": len(t.nodes),
                                 "length_m": round(t.length_m, 1)}
                  for t in traces_strict}))

        # 3) A-09 tie/NO candidates --------------------------------------
        ties_svc = TieDetectionService(graph, net, traces, tracing)
        ties = ties_svc.detect(topo_issues)

        # 4) زون‌بندی ------------------------------------------------------
        zbuilder = ZoneBuilder(graph, net, traces, ZonePolicy(
            include_fuse_cutout=st.include_fuse_cutout_as_boundary))
        zones = zbuilder.build(topo_issues)

        # 5) base scenario + connectivity ---------------------------------
        scenario = SwitchScenario(
            name="وضعیت عادی (از GIS)", base=base_state(net, policy),
            note="پایه فاز ۲ — وضعیت‌ها از T__outserv + تأییدهای NO کاربر")
        conn = evaluate(graph, net, scenario,
                        zone_of_edge=zones.zone_of_edge, issues=topo_issues)

        # 6) QC ------------------------------------------------------------
        summary = net.summary()
        summary["topology"] = {
            "graph": graph.stats,
            "traces": {t.feeder_key: t.as_dict() for t in traces},
            "traces_strict": {t.feeder_key: t.as_dict() for t in traces_strict},
            "zones": zones.as_dict(),
            "ties": len(ties),
            "connectivity": conn.summary(),
        }
        rep = run_qc(summary, topo_issues,
                     net.project_name or "topology", None)

        result = TopologyResult(
            graph=graph, traces=traces, ties=ties, zones=zones,
            scenario=scenario, connectivity=conn, issues=topo_issues,
            report=rep, settings=self._settings_snapshot(st),
            traces_strict=traces_strict)

        # 7) persistence -----------------------------------------------------
        if st.persist and out_db:
            store = ProjectStore(out_db)
            topo_run_id = store.save_topology(
                source_run_id=source_run_id,
                zones=zones.zones, zone_of_edge=zones.zone_of_edge,
                zone_of_node=zones.zone_of_node,
                boundaries=zones.boundaries, traces=traces,
                ties=ties_svc.to_tie_entities(),
                settings=result.settings, user=st.user,
                algo_version=f"{APP_NAME} {__version__}",
                summary=summary, verdict=rep.verdict,
                scenarios=[{
                    "name": scenario.name, "note": scenario.note,
                    "actions": [a.as_dict() for a in scenario.actions],
                    "summary": conn.summary(),
                }])
            result.topo_run_id = topo_run_id
            store.close()
        return result

    # ------------------------------------------------------------------
    @staticmethod
    def _settings_snapshot(st: TopologySettings) -> dict:
        return {
            "match_tol_m": st.match_tol_m,
            "source_attach_tol_m": st.source_attach_tol_m,
            "unknown_switch_pass": st.unknown_switch_pass,
            "out_of_service_blocks": st.out_of_service_blocks,
            "include_fuse_cutout_as_boundary": st.include_fuse_cutout_as_boundary,
            "hint_gated_tracing": st.hint_gated_tracing,
            "policies": {
                "TOPO-POL-01": "کلید با وضعیت نامشخص در وضعیت عادی عبور "
                               "می‌کند و صریحاً Issue دارد (قابل تغییر).",
                "TOPO-POL-02": "گره منبع (ELWFWT) به نزدیک‌ترین گره خطی "
                               "در شعاع اتصال متصل و فاصله آن ثبت می‌شود.",
                "TOPO-POL-03": "کات اوت فیوز به‌صورت پیش‌فرض مرز زون نیست.",
                "TOPO-POL-04": "سمت کلید در گره چندخطی از داده قابل "
                               "استنتاج نیست؛ مرز ثبت و برچسب می‌خورد.",
                "TOPO-POL-05": "دروازه برچسب فیدر — قطعه‌ای که GIS آن را به "
                               "فیدر دیگری منسوب کرده عبور نمی‌کند؛ بدون "
                               "این دروازه با نبود NO/NC در داده (A-09)، "
                               "فیدرها در هم غرق می‌شوند (فیکس تفکیک فیدر).",
                "TOPO-POL-06": "کلید/فیوز موجود روی ترمینال مستقیم ترانس توزیع "
                               "در مدل و نقشه حفظ می‌شود، اما مرز زون یا Tie "
                               "و کاندید ارتقای سکسیونینگ فیدر محسوب نمی‌شود؛ "
                               "تشخیص اتصال واقعی باید با GIS/نقشه تک‌خطی کنترل شود.",
            },
            "tav_revision": TAV_REFERENCE,
            # NOTE: no wall-clock timestamp here — the settings snapshot is
            # part of the deterministic topo_run_id (reproducibility, بند ۱۹).
            # The execution time is stored separately in topo_run.created_at.
        }
