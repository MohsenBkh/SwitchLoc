# -*- coding: utf-8 -*-
"""PlacementEngine — orchestration of the Phase-4 pipeline (گام‌های ۴-۸).

Pipeline (pure computation, no I/O — the application layer persists):

  n-1 engine (جداول ۱۳/۱۴/۱۵)  →  feeder ranking (فرمول ۱ + جدول ۱۶)
  →  scheme generation (جدول ۱۷ + پیوست ب)  →  ENS before/after
  (رابطه ۸ + transfer of رابطه ۱۱)  →  جدول ۱۸ CE/CN  →  recommendation
  (طرح اصلی برای هر اولویت = max CE/CN).

Area model (default ``strict``): the n-1/zoning analysis runs on each
feeder's GUARANTEED core (Phase-2 ``traces_strict`` — unknown-state
switches treated as open, so feeders are disjoint).  The flooded
normal-state trace covers the whole interconnection island for every
feeder (A-09 flood-through) and would double-count everything; the
full extent is restored per feeder once the NO points are engineer-
confirmed (A-09) — registered as explicit issues, never silent.

Every number is anchored to the official text; every modelling gap
(no rated capacity, unassigned load categories, missing λ/r) surfaces
as a registered issue — nothing is silent (بند ۱۹).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.entities import CanonicalNetwork
from ..level1.transfer import barrier_cut_nodes
from ..level1.n_minus_1 import (NMinusOneResult, NMinusOneSettings,
                                run_n_minus_one)
from ..level1.ranking import RankingResult, RankingSettings, rank_feeders
from ..reliability.lambdar import FeederLambdaR
from ..reliability.load_model import LoadModelSettings, build_node_loads
from ..topology.graph import NetworkGraph
from .acceptance import (AcceptanceCriteria, SchemeDecision,
                         evaluate_scheme, select_plans)
from .capacity import CapacityCheck, FeederCapacity, check_scheme_capacity
from .economics import (CostModel, EconomicsResult, SegTree,
                        build_seg_tree, compare_schemes,
                        ens_of_configuration, existing_cut_nodes)
from .golden import GoldenSectioning, build_feeder_tree, owned_edges
from .schemes import PlacementSettings, SwitchScheme, generate_schemes


@dataclass
class EngineSettings:
    n1: NMinusOneSettings = field(default_factory=NMinusOneSettings)
    ranking: RankingSettings = field(default_factory=RankingSettings)
    placement: PlacementSettings = field(default_factory=PlacementSettings)
    cost: CostModel = field(default_factory=CostModel)
    #: نیاز ۱۱ — مدل بار سه‌سطحی (سطح/ضرایب قابل تنظیم از GUI)
    load_model: LoadModelSettings = field(default_factory=LoadModelSettings)
    #: نیاز ۱۰ — معیارهای پذیرش طرح (آستانه‌ها قابل تنظیم از GUI)
    criteria: AcceptanceCriteria = field(default_factory=AcceptanceCriteria)


@dataclass
class PlacementResult:
    n1: NMinusOneResult
    ranking: RankingResult
    schemes: list                          # [SwitchScheme]
    golden: dict                           # feeder → GoldenSectioning
    economics: EconomicsResult
    recommendation: list                   # per-feeder plan decision
    issues: list
    settings: dict
    decisions: dict = field(default_factory=dict)   # scheme_id → decision dict
    capacity_checks: dict = field(default_factory=dict)  # scheme_id → dict
    capacity_map: dict = field(default_factory=dict)     # feeder → dict
    load_model: dict = field(default_factory=dict)       # مدل بار + پوشش

    def to_dict(self) -> dict:
        """JSON-safe snapshot for reports and persistence."""
        return {
            "table13_connections": [
                {"feeder_a": c.feeder_a, "feeder_b": c.feeder_b,
                 "switch_id": c.switch_id,
                 "automation_capable": c.automation_capable,
                 "n_ties": c.n_ties, "m_automation": c.m_automation}
                for c in self.n1.connections],
            "table14_eptl": [
                {"feeder_key": f.feeder_key,
                 "ep_percent": round(f.ep.ep_percent, 2),
                 "tl_percent": round(f.ep.tl_percent, 2),
                 "worst_zone": f.ep.worst_zone,
                 "total_load_kw": round(f.total_load_kw, 1),
                 "zone_count": f.zone_count}
                for f in self.n1.eptl],
            "table15_rows": self.n1.rows15,
            "zone_register": [
                {"feeder_key": fk, "zone_id": z.id, "zone_no": z.zone_no,
                 "kind": z.kind, "length_m": round(float(z.length_m or 0.0), 1),
                 "load_kw": round(float(tree.load_kw.get(z.id, 0.0) or 0.0), 2),
                 "nodes": len(z.nodes), "edges": len(z.edges),
                 "transformers": len(z.transformer_ids), "loads": len(z.load_ids)}
                for fk, tree in sorted(self.n1.trees.items())
                for z in sorted(tree.zones, key=lambda x: (x.zone_no, x.id))
            ],
            "ranking": [
                {"feeder_key": r.feeder_key, "rank": r.rank,
                 "score": round(r.score, 6),
                 "raw": [round(v, 4) for v in r.raw],
                 "norm": [round(v, 6) for v in r.norm],
                 "weighted": [round(v, 6) for v in r.weighted],
                 "ties_count": r.ties_count,
                 "ep_percent": round(r.ep_percent, 2),
                 "tl_percent": round(r.tl_percent, 2),
                 "load_priority_sum": round(r.load_priority_sum, 1),
                 "lambda_per_year": round(r.lambda_per_year, 4),
                 "lambda_reducible": round(r.lambda_reducible, 4),
                 "r_minutes": round(r.r_minutes, 2)}
                for r in self.ranking.rows],
            "schemes": [
                {"id": s.id, "kind": s.kind, "feeders": s.feeders,
                 "relations": s.relations, "note": s.note,
                 "switches": [{"node": sw.node, "feeder": sw.feeder,
                               "kind": sw.kind, "note": sw.note}
                              for sw in s.switches],
                 "extra": s.extra}
                for s in self.schemes],
            "ens_before_kwh": {k: round(v, 2)
                               for k, v in self.economics.ens_before_kwh.items()},
            "table18_comparison": [
                {"scheme_id": c.scheme_id, "kind": c.kind,
                 "feeders": c.feeders, "n_switches": c.n_switches,
                 "e2_before_kwh": c.e2_before_kwh,
                 "e1_after_kwh": c.e1_after_kwh,
                 "ce_rials": c.ce_rials, "cn_rials": c.cn_rials,
                 "ce_over_cn": (c.ce_over_cn if c.ce_over_cn !=
                                float("-inf") else None),
                 "selected": c.selected}
                for c in self.economics.comparisons],
            "recommendation": self.recommendation,
            "decisions": {k: {"status": d["status"],
                              "reasons": d["reasons"],
                              "checks": d["checks"]}
                          for k, d in self.decisions.items()},
            "capacity_checks": {k: v for k, v in self.capacity_checks.items()},
            "capacity_map": {k: v for k, v in self.capacity_map.items()},
            "load_model": self.load_model,
            "issues": [{"code": c, "severity": s, "message_fa": m}
                       for c, s, m in self.issues],
            "settings": self.settings,
        }


def node_load_map(graph: NetworkGraph, net: CanonicalNetwork) -> dict[str, float]:
    """node → Σ transformer capacity_kva (legacy proxy — kept for the
    report path; the engine itself uses the three-level load model of
    نیاز ۱۱ through ``build_node_loads``)."""
    cap = {t.id: (t.capacity_kva or 0.0) for t in net.transformers}
    out: dict[str, float] = {}
    for node, ids in graph.transformer_ids_at.items():
        out[node] = sum(cap.get(t, 0.0) for t in ids)
    return out


def _spare_map(result_n1: NMinusOneResult,
               rated_kw: dict | None,
               capacity_map: dict[str, FeederCapacity] | None = None,
               ) -> dict[str, float]:
    """ظرفیت پشتیبان هر فیدر برای انتقال (kW).

    اولویت: رزرو قابل استفاده مدل ظرفیت (نامی − پیک — نیاز ۹)؛ در نبود
    آن، ظرفیت نامی قدیمی (A-10). اگر هیچ‌کدام موجود نباشد، ظرفیت انتقال
    صفر منظور می‌شود (سیاست محافظه‌کارانهٔ v1.9.1 — انتقال تأییدنشده
    هرگز فرض بی‌نهایت نمی‌شود) و هشدار صریح ثبت می‌شود.
    """
    if capacity_map:
        out = {}
        for k, tree in result_n1.trees.items():
            cap = capacity_map.get(k)
            if cap is not None and cap.usable_reserve_kw is not None:
                out[k] = cap.usable_reserve_kw
            elif rated_kw and k in rated_kw:
                out[k] = max(0.0, float(rated_kw[k]) - tree.total_load_kw)
        return out
    if not rated_kw:
        return {}
    return {k: max(0.0, float(rated_kw[k]) - tree.total_load_kw)
            for k, tree in result_n1.trees.items() if k in rated_kw}


class PlacementEngine:
    """Runs گام‌های ۴-۸ of the first-level method on a traced network."""

    def __init__(self, settings: EngineSettings | None = None):
        self.settings = settings or EngineSettings()

    def run(self, graph: NetworkGraph, net: CanonicalNetwork,
            traces, zones, ties,
            lam_matrix: list[FeederLambdaR] | None = None,
            traces_strict=None,
            feeder_capacity: dict[str, FeederCapacity] | None = None,
            scope_feeder: str | None = None,
            scope_feeders=None) -> PlacementResult:
        """اجرای گام‌های ۴-۸.

        ``feeder_capacity``: مدل ظرفیت فیدرها (نیاز ۹) — رزرو/اضطراری.
        ``scope_feeder``: مطالعه تک‌فیدر (نیاز ۱۲) — رتبه‌بندی روی کل شبکه
        عیب‌ج می‌شود (نرمال‌سازی ثابت می‌ماند) و سپس فقط طرح‌ها/نتیجه‌های
        همان فیدر گزارش می‌شوند.
        """
        st = self.settings
        issues: list = []
        cap_map = dict(feeder_capacity or {})
        if not cap_map and st.placement.feeder_capacity:
            cap_map = dict(st.placement.feeder_capacity)

        # ---- نیاز ۱۱: مدل بار سه‌سطحی با منشأ ردیابی‌پذیر -----------------
        lm = build_node_loads(graph, net, st.load_model)
        node_load = lm.node_kw
        issues.extend((i.code, i.severity, i.message_fa)
                      for i in lm.issues)
        issues.append(("PLAC-LOAD-MODEL-SOURCE", "Information",
                       f"بار گره‌ها از مدل بار سطح «{lm.level}» با منشأ "
                       "ردیابی‌پذیر (node_origin) گرفته شد — بار کل هر فیدر "
                       "در داشبورد قابل مشاهده است."))

        # ---- area model (strict core vs flooded trace) ---------------------
        area_traces, area_zones = list(traces), zones
        zone_src = "traced"
        if st.placement.area_mode == "strict":
            if traces_strict:
                from ..topology.zones import ZoneBuilder, ZonePolicy
                from ..validation.issues import IssueLog
                strict_zres = ZoneBuilder(
                    graph, net, traces_strict,
                    ZonePolicy(include_fuse_cutout=
                               st.placement.include_fuse_cutout_as_boundary),
                ).build(IssueLog())
                area_traces, area_zones = traces_strict, strict_zres
                zone_src = "strict"
                edges_n = sum(len(z.edges) for z in strict_zres.zones)
                issues.append((
                    "PLAC-AREA-STRICT", "Information",
                    f"تحلیل n-1 روی هسته قطعی فیدرها انجام شد (کلیدهای با "
                    f"وضعیت نامشخص = باز): {len(strict_zres.zones)} زون و "
                    f"{edges_n} یال. گستره کامل هر فیدر پس از تأیید "
                    "نقاط NO (A-09) جایگزین و محاسبه تکرار می‌شود."))
            else:
                issues.append((
                    "PLAC-AREA-FALLBACK", "Warning",
                    "traces_strict در دسترس نیست؛ تحلیل روی ردیابی عادی "
                    "اجرا شد که برای فیدرهای به‌هم‌پیوسته (سرریز A-09) "
                    "بارها را چندبار می‌شمارد."))
        elif st.placement.area_mode != "traced":
            raise ValueError(f"area_mode نامعتبر: {st.placement.area_mode}")

        # A restricted study is genuinely restricted through N-1, scheme
        # generation and economics, not only at the final recommendation
        # table. The complete graph remains available to find connectivity,
        # but only selected feeder traces/zones and interconnections enter
        # this run.
        selected_scope = ({str(k).strip().upper() for k in scope_feeders
                           if str(k).strip()} if scope_feeders else
                          ({str(scope_feeder).strip().upper()}
                           if scope_feeder else set()))
        study_ties = list(ties)
        if selected_scope:
            area_traces = [t for t in area_traces
                           if str(t.feeder_key).strip().upper() in selected_scope]
            study_ties = [t for t in study_ties
                          if str(t.feeder_a).strip().upper() in selected_scope
                          and str(t.feeder_b).strip().upper() in selected_scope]

        keys = {t.feeder_key for t in area_traces}
        zones_by_feeder = {k: [z for z in area_zones.zones if z.feeder == k]
                           for k in keys}
        edge_set_of = {k: owned_edges(zones_by_feeder.get(k, []))
                       for k in keys}

        # ---- گام‌های ۴-۵: جداول ۱۳/۱۴/۱۵ ----------------------------------
        # Convert the selected node-load model to transformer allocations
        # so N-1 zone aggregation uses the same kW basis as ENS/ranking.
        transformer_load_kw: dict[str, float] = {}
        transformers_by_id = {t.id: t for t in net.transformers}
        for node, transformer_ids in graph.transformer_ids_at.items():
            ids = [tid for tid in transformer_ids if tid in transformers_by_id]
            if not ids:
                continue
            node_kw = max(0.0, float(node_load.get(node, 0.0) or 0.0))
            weights = {tid: max(0.0, float(transformers_by_id[tid].capacity_kva or 0.0))
                       for tid in ids}
            total_weight = sum(weights.values())
            if total_weight <= 0:
                weights = {tid: 1.0 for tid in ids}
                total_weight = float(len(ids))
            for tid in ids:
                transformer_load_kw[tid] = node_kw * weights[tid] / total_weight

        # Reconcile graph-assigned transformer load against actual zone
        # membership. A transformer can be present in the graph yet remain
        # outside every materialized zone (e.g. an isolated terminal/node).
        # Such load must be reported, never silently disappear from the
        # zone totals or be spread over the other zones.
        zone_transformer_ids = {
            tid for feeder_zones in zones_by_feeder.values()
            for zone in feeder_zones for tid in zone.transformer_ids
        }
        unzoned_transformer_ids = sorted(
            set(transformer_load_kw) - zone_transformer_ids)
        unzoned_transformer_kw = sum(
            transformer_load_kw.get(tid, 0.0)
            for tid in unzoned_transformer_ids)
        if unzoned_transformer_ids:
            issues.append((
                "LOAD-SCALING-TRANSFORMER-UNZONED", "Warning",
                f"{len(unzoned_transformer_ids)} ترانس در گراف وجود دارند اما "
                f"عضو هیچ‌یک از زون‌های مطالعه نیستند؛ بار متناظر "
                f"{unzoned_transformer_kw:,.1f} kW از جمع بار زون‌ها خارج "
                "مانده است. این مقدار به زون دیگری منتقل یا پنهان نشده است."))
        n1 = run_n_minus_one(graph, net, area_traces, zones_by_feeder,
                             study_ties, settings=st.n1,
                             transformer_load_kw=transformer_load_kw)
        issues.extend(n1.issues)

        # ---- گام ۶: رتبه‌بندی (فرمول ۱ + جدول ۱۶) --------------------------
        ranking = rank_feeders(n1, net, lam_matrix, settings=st.ranking,
                                scope_feeder=scope_feeder,
                                scope_feeders=scope_feeders)
        issues.extend(ranking.issues)
        if scope_feeder:
            issues.append((
                "PLAC-SINGLE-FEEDER-RANKING", "Information",
                "رتبه‌بندی فقط برای فیدر انتخابی نرمال‌سازی شده و رتبه ۱ از ۱ "
                "است؛ این امتیاز برای مقایسه با فیدرهای خارج از دامنه قابل "
                "استفاده نیست. برای اولویت‌بندی بین فیدرها، مطالعه کل شبکه اجرا شود."))
        elif scope_feeders:
            issues.append((
                "PLAC-MULTI-FEEDER-RANKING", "Information",
                "رتبه‌بندی فقط بین فیدرهای انتخاب‌شده انجام شد؛ امتیازها و رتبه‌ها "
                "برای مقایسه با فیدرهای خارج از دامنه معتبر نیستند."))

        # ENS benefit is credited only to outages classified as reducible by
        # switching; total λ remains available to ranking/reporting.
        lam_of = {m.feeder_key: getattr(m, "lambda_reducible_per_year", 0.0)
                  for m in (lam_matrix or [])}
        r_of = {m.feeder_key: getattr(m, "r_reducible_minutes", 0.0)
                for m in (lam_matrix or [])}

        # zone_no per (feeder, node) for the head-tie rule (جدول ۱۷-ج)
        zone_no_of: dict[tuple, int] = {}
        for key, tree in n1.trees.items():
            for z in tree.zones:
                for n in z.nodes:
                    cur = zone_no_of.get((key, n))
                    if cur is None or z.zone_no < cur:
                        zone_no_of[(key, n)] = z.zone_no

        cut_nodes_of = {t.feeder_key: existing_cut_nodes(
            zones_by_feeder.get(t.feeder_key, [])) for t in area_traces}

        # ---- گام ۷: طرح‌های کلیدگذاری (جدول ۱۷ + پیوست ب) ------------------
        # ظرفیت اضطراری/نامی به تولید طرح ۱٫۵ کلیدی (رابطه ۱۱) تزریق می‌شود
        if cap_map:
            st.placement.feeder_capacity = dict(cap_map)
        schemes, golden_of, sch_issues = generate_schemes(
            graph, net, area_traces, n1.trees, ranking.rows, study_ties,
            zone_no_of, node_load, lam_of, r_of, cut_nodes_of, edge_set_of,
            settings=st.placement)
        issues.extend(sch_issues)

        # ---- گام ۸: ENS قبل/بعد + جدول ۱۸ ----------------------------------
        eco = self._economics(graph, net, area_traces, n1, study_ties, schemes,
                              node_load, lam_of, r_of, cut_nodes_of,
                              edge_set_of, cap_map)
        issues.extend(eco.issues)

        # ---- نیاز ۹ + ۱۰: کنترل ظرفیت، ارزیابی پذیرش و انتخاب بدون اجبار --
        load_kw_of = {k: tree.total_load_kw for k, tree in n1.trees.items()}
        capacity_checks: dict[str, CapacityCheck] = {}
        decisions: dict[str, SchemeDecision] = {}
        for sc in schemes:
            chk = check_scheme_capacity(sc, cap_map, load_kw_of)
            capacity_checks[sc.id] = chk
            comp = next((c for c in eco.comparisons
                         if c.scheme_id == sc.id), None)
            decisions[sc.id] = evaluate_scheme(comp, chk, st.criteria)
        recommendation = select_plans(eco.comparisons, decisions,
                                      ranking.rows, schemes)
        n_no_just = sum(1 for r in recommendation
                        if r["status"] == "no_justification")
        n_need_cap = sum(1 for r in recommendation
                         if r["status"] == "needs_capacity_confirmation")
        issues.append(("PLAC-ACCEPTANCE-SUMMARY", "Information",
                       f"پذیرش طرح (نیاز ۱۰): "
                       f"{sum(1 for r in recommendation if r['status'] == 'accepted')} "
                       f"فیدر طرح اصلی دارند، {n_need_cap} فیدر «نیازمند تأیید "
                       f"ظرفیت» و {n_no_just} فیدر «عدم توجیه نصب کلید» — "
                       "هیچ طرحی به اجبار معرفی نمی‌شود."))
        if not cap_map:
            issues.append(("PLAC-CAPACITY-MISSING", "Warning",
                           "ظرفیت هیچ فیدری وارد نشده (نیاز ۹): هر طرحی که "
                           "انتقال داشته باشد در وضعیت «نیازمند تأیید ظرفیت» "
                           "می‌ماند و تأیید نهایی مهندسی نمی‌گیرد — ظرفیت "
                           "نامی/پیک/اضطراری را از تنظیمات وارد و اجرا را "
                           "تکرار کنید."))
        issues.append((
            "PLAC-LOAD-PROXY-NOTE", "Information",
            "بار زون‌ها از مدل بار سه‌سطحی (نیاز ۱۱) گرفته شد؛ سطح فعال و "
            "ضرایب در تنظیمات اجرا ثبت است."))

        # ---- مطالعه تک‌فیدر (نیاز ۱۲): فیلتر خروجی روی یک فیدر -------------
        if selected_scope:
            recommendation = [r for r in recommendation
                              if str(r.get("feeder_key", "")).strip().upper()
                              in selected_scope]
            if not recommendation:
                issues.append(("PLAC-SCOPE-EMPTY", "Warning",
                               "هیچ‌یک از فیدرهای انتخاب‌شده در نتایج رتبه‌بندی "
                               "وجود ندارد؛ دامنه مطالعه خالی ماند."))

        settings_snapshot = {
            "area_mode": zone_src,
            "scope_feeder": scope_feeder,
            "scope_feeders": sorted(selected_scope) if selected_scope else [],
            "n1": n1.settings,
            "ranking": ranking.settings,
            "load_model": st.load_model.as_dict(),
            "criteria": st.criteria.as_dict(),
            "placement": {
                "max_feeders": st.placement.max_feeders,
                "max_tie_schemes": st.placement.max_tie_schemes,
                "target_zones": st.placement.golden.target_zones,
                "candidate_mode": st.placement.golden.candidate_mode,
                "feeder_rated_kw": st.placement.feeder_rated_kw,
            },
            "cost_model": {
                "nc_new_rials": st.cost.nc_new_rials,
                "no_new_rials": st.cost.no_new_rials,
                "automation_upgrade_rials": st.cost.automation_upgrade_rials,
                "rial_per_kwh": st.cost.rial_per_kwh,
                "switching_minutes": st.cost.switching_minutes,
            },
            "anchors": {
                "tables_13_14_15": "TAV122-02/00 بند ۷-۷-۴ (گام‌های ۴-۵)",
                "formula_1_table_16": "بند ۷-۷-۵ (گام ۶)، صفحه ۳۳",
                "table_17": "بند ۷-۷-۶ (گام ۷) + پیوست ب",
                "table_18": "بند ۷-۷-۷ (گام ۸)، صفحه ۳۵ — بیشینه CE/CN",
                "relations": "پیوست ب، روابط (۸) تا (۱۳)",
                "acceptance": "نیاز ۱۰ — پنج معیار پذیرش + عدم توجیه صریح",
            },
        }

        return PlacementResult(
            n1=n1, ranking=ranking, schemes=schemes, golden=golden_of,
            economics=eco, recommendation=recommendation, issues=issues,
            settings=settings_snapshot,
            decisions={k: {"status": d.status, "reasons": d.reasons,
                           "checks": d.checks}
                       for k, d in decisions.items()},
            capacity_checks={k: v.as_dict()
                             for k, v in capacity_checks.items()},
            capacity_map={k: v.as_dict() for k, v in cap_map.items()},
            load_model={"level": lm.level,
                        "coverage": lm.coverage,
                        "scaling_plan": getattr(lm, "scaling_plan", {}) or {},
                        "per_feeder_kw": {
                            k: round(v, 1) for k, v in
                            lm.per_feeder_kw.items()}})

    # ------------------------------------------------------------------
    def _economics(self, graph, net, traces, n1: NMinusOneResult,
                   ties, schemes: list[SwitchScheme], node_load,
                   lam_of: dict, r_of: dict, cut_nodes_of: dict,
                   edge_set_of: dict,
                   cap_map: dict[str, FeederCapacity] | None = None
                   ) -> EconomicsResult:
        st = self.settings
        eco = EconomicsResult(cost_model={
            "nc_new_rials": st.cost.nc_new_rials,
            "no_new_rials": st.cost.no_new_rials,
            "automation_upgrade_rials": st.cost.automation_upgrade_rials,
            "rial_per_kwh": st.cost.rial_per_kwh,
            "switching_minutes": st.cost.switching_minutes,
        })
        barriers = barrier_cut_nodes(graph, net, ties)
        spare = _spare_map(n1, st.placement.feeder_rated_kw, cap_map)
        if not spare:
            eco.issues.append((
                "PLAC-CAP-UNKNOWN", "Information",
                "ظرفیت رزرو فیدرها تنظیم نشده؛ ظرفیت انتقال پشتیبان صفر "
                "منظور شد (سیاست محافظه‌کارانهٔ v1.9.1 — انتقال تأییدنشده "
                "هرگز فرض نمی‌شود). طرح‌های انتقالی تا ورود ظرفیت‌ها "
                "«نیازمند تأیید ظرفیت» می‌مانند (نیاز ۹)."))
        trace_of = {t.feeder_key: t for t in traces}
        node_trees = {k: build_feeder_tree(graph, trace_of[k],
                                           edge_set_of.get(k, set()), node_load)
                      for k in trace_of}

        def transfers_for(feeder_key: str, segs: SegTree) -> dict[str, float]:
            out: dict[str, float] = {}
            auto = [t for t in ties if t.automation_capable
                    and feeder_key in (t.feeder_a, t.feeder_b)]
            for tie in auto:
                other = (tie.feeder_b if tie.feeder_a == feeder_key
                         else tie.feeder_a)
                seg = segs.node_seg_below.get(tie.node) \
                    or segs.node_seg.get(tie.node)
                if seg is None:
                    continue
                cap = spare.get(other, 0.0)
                prev = out.get(seg, 0.0)
                out[seg] = prev + cap
            return out

        # ---- before state --------------------------------------------------
        ens_before: dict[str, float] = {}
        for tr in traces:
            key = tr.feeder_key
            tree = node_trees[key]
            segs = build_seg_tree(graph, tr, tree,
                                  cut_nodes_of.get(key, set()), node_load,
                                  edge_set_of.get(key, set()))
            cap, _ = ens_of_configuration(
                segs, lam_of.get(key, 0.0), r_of.get(key, 0.0),
                st.cost.switching_minutes,
                transfers_for(key, segs),
                total_length_m=tree.sub_len.get(tree.order[0]),
                barrier_nodes=barriers)
            ens_before[key] = cap
        eco.ens_before_kwh = ens_before

        # ---- after state per scheme -----------------------------------------
        for sc in schemes:
            after: dict[str, float] = {}
            for key in sc.feeders:
                tr = trace_of.get(key)
                tree = node_trees.get(key)
                if tr is None or tree is None:
                    continue
                cuts = set(cut_nodes_of.get(key, set()))
                cuts |= {sw.node for sw in sc.switches
                         if sw.kind in ("NC", "automation_upgrade")}
                extra_ties = [sw for sw in sc.switches if sw.kind == "NO"]
                segs = build_seg_tree(graph, tr, tree, cuts, node_load,
                                      edge_set_of.get(key, set()))
                tmap = transfers_for(key, segs)
                # NO switches added by THIS scheme act as new ties at
                # their own node — map them onto the new segment tree
                for sw in extra_ties:
                    other = next((f for f in sc.feeders if f != key), key)
                    seg = segs.node_seg_below.get(sw.node) \
                        or segs.node_seg.get(sw.node)
                    if seg is None:
                        continue
                    cap = spare.get(other, 0.0)
                    prev = tmap.get(seg, 0.0)
                    tmap[seg] = prev + cap
                val, _ = ens_of_configuration(
                    segs, lam_of.get(key, 0.0), r_of.get(key, 0.0),
                    st.cost.switching_minutes, tmap,
                    total_length_m=tree.sub_len.get(tree.order[0]),
                    barrier_nodes=barriers)
                after[key] = val
            eco.ens_after_kwh[sc.id] = after
        eco.comparisons = compare_schemes(schemes, ens_before,
                                          eco.ens_after_kwh, st.cost)
        return eco
