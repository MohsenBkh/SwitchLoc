# -*- coding: utf-8 -*-
"""Project service for exhaustive Level-2 EENS + load-flow placement."""
from __future__ import annotations

import itertools
import json
import math
from copy import copy
from dataclasses import dataclass, replace
from pathlib import Path

from ..application.equipment_types import DEFAULT_TYPES_CATALOG, EquipmentTypeCatalog
from ..application.topology_service import TopologyService, TopologySettings
from ..domain.enums import SwitchFamily
from ..persistence.store import ProjectStore
from ..placement.level2 import (Level2Plan, Level2Settings, Level2StudyResult,
                                enumerate_location_plans, exact_plan_count)
from ..reliability.load_model import LoadModelSettings, build_node_loads
from ..reliability.power_flow import PowerFlowSettings, solve_radial_power_flow
from ..reliability.switch_placement import (
    SwitchPlacementEngine, SwitchPlacementSettings,
    build_radial_tree, build_sections, compute_eens_kwh,
    compute_transient_eens_kwh)
from ..topology.tracing import TracingEngine, same_feeder
from ..topology.zones import ZoneBuilder, ZonePolicy
from ..task_control import check_cancelled, report_progress
from ..validation.issues import IssueLog


@dataclass
class Level2AppSettings:
    level2: Level2Settings
    power_flow: PowerFlowSettings
    load_model: dict
    reliability: dict
    equipment_types_path: str = str(DEFAULT_TYPES_CATALOG)
    feeder_keys: tuple[str, ...] | None = None
    persist: bool = False
    user: str = "level2-placement"


class Level2PlacementService:
    """Load a project, exhaustively search placements, and enforce load flow.

    New NC devices are normally closed; only explicitly enumerated existing
    tie-switch candidates are considered as new normally-open points. All
    normally-open states are evaluated against every feeder's steady-state
    load-flow constraints. Reliability scoring uses the project's declared
    restoration model/backup limits.
    """

    def __init__(self, settings: Level2AppSettings):
        settings.level2.validate()
        settings.power_flow.validate()
        self.settings = settings

    def run(self, db_path: str) -> Level2StudyResult:
        st = self.settings
        check_cancelled()
        report_progress(0, "شروع جست‌وجوی جایابی سطح ۲")
        store = ProjectStore(db_path)
        try:
            runs = store.runs()
            if not runs:
                raise ValueError("پروژه هیچ دادهٔ ورودی ندارد.")
            net, issues = store.load_network(runs[-1]["id"])
            topo = TopologyService(TopologySettings(persist=False)).run(net, issues=issues)
            all_traces = list(topo.traces)
            if st.feeder_keys is None:
                traces = all_traces
            else:
                requested = {str(key).strip() for key in st.feeder_keys if str(key).strip()}
                unknown = [key for key in requested
                           if not any(same_feeder(key, trace.feeder_key)
                                      for trace in all_traces)]
                if unknown:
                    raise ValueError("فیدرهای انتخاب‌شده در پروژه پیدا نشدند: "
                                     + ", ".join(sorted(unknown)))
                traces = [trace for trace in all_traces
                          if any(same_feeder(trace.feeder_key, key)
                                 for key in requested)]
                if not traces:
                    raise ValueError("برای جایابی سطح ۲ هیچ فیدری در دامنهٔ مطالعه انتخاب نشده است.")
            selected_nodes = {node for trace in traces for node in trace.nodes}
            load_data = dict(st.load_model or
                             store.get_kv("engineering_load_model_v1", {}) or {})
            if not load_data:
                raise ValueError("مدل بار وجود ندارد؛ P/Q را برای همهٔ فیدرها تکمیل کنید.")
            lm_settings = LoadModelSettings.from_dict(load_data)
            load_result = build_node_loads(topo.graph, net, lm_settings)
            node_kw = {n: float(v or 0.0) for n, v in load_result.node_kw.items()
                       if n in selected_nodes}
            node_kvar = {n: float(v or 0.0) for n, v in load_result.node_kvar.items()
                         if n in selected_nodes}
            if not any(abs(v) > 1e-9 for v in node_kw.values()):
                raise ValueError("مدل بار هیچ بار اکتیوی به گره‌ها تخصیص نداده است.")
            q_explicit = lm_settings.level == "scaled" or any(
                getattr(ld, "node_id", None) in selected_nodes
                and getattr(ld, "q_kvar", None) is not None
                for ld in (net.loads or []))
            if not q_explicit:
                pf = st.power_flow.assumed_power_factor
                tan_phi = math.tan(math.acos(pf))
                node_kvar = {n: abs(p) * tan_phi for n, p in node_kw.items()}

            rates, repairs, transients, rate_notes = _resolve_reliability_inputs(
                st.reliability, store, traces)
            flow_settings = PowerFlowSettings.from_dict(st.power_flow.as_dict())
            catalog = EquipmentTypeCatalog(st.equipment_types_path)
            _apply_catalog_lines(flow_settings, catalog, net.branches or [])
            transformer_kva = _transformer_kva_by_node(topo.graph, net)
            budget = _resolve_budgets(st.level2.nc_budget_by_feeder, traces)

            unresolved: list[str] = []
            ties, tie_ambiguities = _candidate_ties(topo.ties)
            selected_feeders = {str(trace.feeder_key) for trace in traces}
            ties = [tie for tie in ties
                    if any(same_feeder(tie.feeder_a, key) for key in selected_feeders)
                    and any(same_feeder(tie.feeder_b, key) for key in selected_feeders)]
            unresolved.extend(tie_ambiguities)
            if st.level2.no_budget > len(ties):
                raise ValueError(
                    f"بودجهٔ NO={st.level2.no_budget} ولی فقط {len(ties)} کاندید tie معتبر "
                    "در دامنهٔ فیدرهای انتخاب‌شده وجود دارد. فقط tie-switchهای موجود با شناسهٔ "
                    "یکتای GIS قابل ارزیابی‌اند؛ تعداد NO را کاهش دهید یا فیدر/توپولوژی را بررسی کنید. "
                    "جایابی کلید NO جدید در این نسخه پشتیبانی نمی‌شود.")
            no_state_count = math.comb(len(ties), st.level2.no_budget)
            if not no_state_count:
                raise ValueError("هیچ حالت NO قابل بررسی نیست.")
            no_states = itertools.combinations(ties, st.level2.no_budget)

            # Baseline: actual imported normally-open states, before this plan.
            base_contexts = self._build_contexts(
                topo.graph, net, traces, node_kw, rates, repairs, transients,
                st.reliability, budget, st.level2, topo.zones.zone_of_node)
            baseline_eens = {}
            for switch_type, contexts in base_contexts.items():
                baseline_eens[switch_type] = {}
                for key, ctx in contexts.items():
                    if ctx["study"].status != "ok":
                        raise ValueError(
                            f"EENS پایهٔ فیدر {key} قابل محاسبه نیست: "
                            + "; ".join(ctx["study"].notes))
                    baseline_eens[switch_type][key] = _score_feeder_eens(
                        ctx, (), switch_type, st.reliability)
            baseline_flow, _ = self._evaluate_flow_state(
                topo.graph, net, traces, node_kw, node_kvar,
                transformer_kva, flow_settings)

            # State count is summed across all allowed NO states and switch types.
            total_states = 0
            prepared = []
            for no_index, no_selection in enumerate(no_states):
                check_cancelled()
                if no_index % max(1, no_state_count // 25) == 0:
                    report_progress(5 + 22 * no_index / max(1, no_state_count),
                                    f"آماده‌سازی حالت NO: {no_index + 1}/{no_state_count}")
                state_net = _with_normally_open(net, no_selection)
                trace_engine = TracingEngine(topo.graph, state_net)
                state_traces = trace_engine.trace_all(IssueLog(), quiet=True)
                state_traces = [trace for trace in state_traces
                                if any(same_feeder(trace.feeder_key, key)
                                       for key in selected_feeders)]
                if not state_traces:
                    unresolved.append("حالت NO انتخاب‌شده فیدری برای ردیابی تولید نکرد.")
                    continue
                state_load_counts = _loaded_node_occurrences(state_traces, node_kw)
                duplicate_loads = [n for n, c in state_load_counts.items() if c > 1]
                all_load_nodes = {n for n, p in node_kw.items() if p > 1e-9}
                missing_loads = sorted(all_load_nodes - set(state_load_counts))
                if duplicate_loads or missing_loads:
                    if duplicate_loads:
                        unresolved.append(
                            "بار گره‌های مشترک بین چند فیدر، پس از تعیین NO نیز مبهم است: "
                            + ", ".join(duplicate_loads[:8]))
                    if missing_loads:
                        unresolved.append(
                            "بار بدون فیدر منبع پس از تعیین NO: "
                            + ", ".join(missing_loads[:8]))
                    continue
                zone_res = ZoneBuilder(
                    topo.graph, state_net, state_traces,
                    ZonePolicy(include_fuse_cutout=False)).build(IssueLog())
                flow_rows, flow_ok = self._evaluate_flow_state(
                    topo.graph, state_net, state_traces, node_kw, node_kvar,
                    transformer_kva, flow_settings)
                contexts = self._build_contexts(
                    topo.graph, state_net, state_traces, node_kw, rates, repairs,
                    transients, st.reliability, budget, st.level2,
                    zone_res.zone_of_node)
                expected_feeders = set(next(iter(base_contexts.values()), {}))
                actual_feeders = set(next(iter(contexts.values()), {}))
                if actual_feeders != expected_feeders:
                    unresolved.append(
                        "مجموعهٔ فیدرهای قابل تحلیل در این حالت NO با حالت پایه برابر نیست؛ "
                        "حالت برای جلوگیری از حذف/افزودن پنهان بار کنار گذاشته شد.")
                    continue
                candidate_lists = _candidate_lists(contexts, st.level2.candidate_mode,
                                                   topo.graph, node_kw)
                missing_budget = [f for f, n in budget.items()
                                  if n > len(candidate_lists.get(f, []))]
                if missing_budget:
                    unresolved.append(
                        "بودجهٔ NC در این حالت از کاندیدهای معتبر بیشتر است: "
                        + ", ".join(missing_budget))
                    continue
                state_count = exact_plan_count(candidate_lists, budget, 0, 0)
                total_states += state_count
                prepared.append((no_selection, state_net, state_traces, contexts,
                                 candidate_lists, flow_rows, flow_ok, state_count))

            expanded_count = total_states * len(st.level2.switch_types)
            report_progress(28, f"فضای جست‌وجو: {expanded_count:,} آرایش")
            if expanded_count > st.level2.max_search_states:
                raise ValueError(
                    f"فضای دقیق جست‌وجو {expanded_count:,} حالت است؛ سقف "
                    f"max_search_states={st.level2.max_search_states:,}. "
                    "کاندید/بودجه را صریح تغییر دهید؛ کاهش خودکار انجام نشد.")

            best: dict[str, Level2Plan | None] = {
                switch_type: None for switch_type in st.level2.switch_types}
            feasible_counts = {x: 0 for x in st.level2.switch_types}
            rejected_counts = {x: 0 for x in st.level2.switch_types}
            state_index = 0
            evaluated_states = 0
            progress_stride = max(1, expanded_count // 100)
            for no_selection, _state_net, _state_traces, contexts, candidate_lists, flow_rows, flow_ok, state_count in prepared:
                check_cancelled()
                if not flow_ok:
                    for switch_type in st.level2.switch_types:
                        rejected_counts[switch_type] += state_count
                    evaluated_states += state_count * len(st.level2.switch_types)
                    state_index += state_count
                    report_progress(
                        28 + 70 * evaluated_states / max(1, expanded_count),
                        f"رد آرایش‌های ناسازگار پخش بار: {evaluated_states:,}/{expanded_count:,}")
                    continue
                for nc_by_feeder, _unused in enumerate_location_plans(
                        candidate_lists, budget, (), 0,
                        max(1, st.level2.max_search_states)):
                    check_cancelled()
                    state_index += 1
                    for switch_type in st.level2.switch_types:
                        check_cancelled()
                        evaluated_states += 1
                        if evaluated_states % progress_stride == 0:
                            report_progress(
                                28 + 70 * evaluated_states / max(1, expanded_count),
                                f"ارزیابی آرایش‌ها: {evaluated_states:,}/{expanded_count:,}")
                        post_by_feeder = {}
                        try:
                            for feeder, ctx in contexts[switch_type].items():
                                selected = nc_by_feeder.get(feeder, [])
                                post_by_feeder[feeder] = _score_feeder_eens(
                                    ctx, selected, switch_type, st.reliability)
                        except (ValueError, RuntimeError) as exc:
                            rejected_counts[switch_type] += 1
                            if len(unresolved) < 20:
                                unresolved.append(
                                    f"یک آرایش {switch_type} به‌دلیل خطای محاسبه EENS رد شد: {exc}")
                            continue
                        plan = Level2Plan(
                            switch_type=switch_type,
                            nc_by_feeder={f: [c.as_dict() for c in cs]
                                          for f, cs in nc_by_feeder.items()},
                            normally_open_ties=[_tie_dict(x) for x in no_selection],
                            base_eens_kwh_per_year=sum(
                                baseline_eens.get(switch_type, {}).values()),
                            post_plan_eens_kwh_per_year=sum(post_by_feeder.values()),
                            gain_kwh_per_year=(sum(baseline_eens.get(switch_type, {}).values())
                                               - sum(post_by_feeder.values())),
                            flow_feasible=True,
                            base_eens_by_feeder=dict(baseline_eens.get(switch_type, {})),
                            post_plan_eens_by_feeder=post_by_feeder,
                            flow_scenarios=flow_rows,
                            state_index=state_index)
                        feasible_counts[switch_type] += 1
                        previous = best[switch_type]
                        tie_key = (plan.post_plan_eens_kwh_per_year,
                                   _plan_signature(plan))
                        prev_key = ((previous["post_plan_eens_kwh_per_year"],
                                     _plan_signature(previous)) if previous else None)
                        if prev_key is None or tie_key < prev_key:
                            best[switch_type] = plan.as_dict()

            feeders = sorted({str(t.feeder_key) for t in traces})
            assumptions = [
                f"دامنهٔ مطالعه فقط فیدرهای انتخاب‌شده است: {', '.join(feeders)}.",
                "هدف: کمینه‌سازی EENS سالانه با جست‌وجوی شمارشی کامل روی کاندیدهای تعریف‌شده.",
                "قیود پخش بار حالت ماندگار برای تمام فیدرهای ردیابی‌شده و هر حالت NO کاندید اعمال شد؛ طرح‌های ناقض ولتاژ، جریان، ظرفیت ترانس، شعاعی‌بودن یا دادهٔ ضروری رد شدند.",
                "کلیدهای NC جدید در حالت عادی بسته‌اند؛ بنابراین محل NC به‌تنهایی پخش بار عادی را تغییر نمی‌دهد. حالت‌های NO از کاندیدهای موجود topology ساخته می‌شوند.",
                "مدل EENS/بازیابی همان موتور قابلیت اطمینان پروژه با پارامترهای صریح است؛ توالی کلیدزنی پس از هر خطا به‌صورت خودکار از GIS استنتاج نمی‌شود.",
                "نتیجهٔ NO یک پیشنهاد جست‌وجویی است؛ پیش از تبدیل به تنظیم بهره‌برداری باید هویت کلید و مانور آن توسط شرکت تأیید شود.",
                "R/X از تایپ یکتای types_override.xlsx گرفته شد؛ Sline(r) با واحد kA و ضریب ۱۰۰۰ به آمپر تبدیل شد. Ithr حد جریان اتصال کوتاه است و در پخش بار استفاده نمی‌شود. مقادیر type_ampacity_a ورودی بر مقدار کاتالوگ اولویت دارند.",
            ]
            if st.level2.candidate_mode == "load_points":
                assumptions.append("فضای نصب NC به گره‌های دارای بار صریح (نقطه‌بار GIS/مدل بار) محدود شد.")
            if not st.reliability.get("backup_kw"):
                assumptions.append("ظرفیت پشتیبان در مدل EENS نامحدود است، مگر اینکه backup_kw صریح ارائه شود.")
            for feeder, source in (st.reliability.get("input_source_by_feeder", {}) or {}).items():
                assumptions.append(f"منشأ λ/r فیدر {feeder}: {source}.")
            if rate_notes:
                assumptions.extend(rate_notes)
            if not q_explicit:
                assumptions.append(
                    f"Q از pf={st.power_flow.assumed_power_factor:g} استنتاج شد؛ Q مستقل GIS/مدل بار موجود نبود.")
            status = "ok" if any(best.values()) else "no-feasible-plan"
            result = Level2StudyResult(
                settings={"feeder_keys": feeders,
                          "level2": st.level2.as_dict(),
                          "power_flow": flow_settings.as_dict(),
                          "reliability": dict(st.reliability),
                          "load_model_level": lm_settings.level,
                          "equipment_types_catalog": str(catalog.path)},
                feeder_keys=feeders,
                baseline_eens_by_type=baseline_eens,
                best_plans=best,
                feasible_plan_count_by_type=feasible_counts,
                rejected_plan_count_by_type=rejected_counts,
                search_state_count=evaluated_states,
                flow_baseline=baseline_flow,
                unresolved=unresolved,
                assumptions=assumptions,
                status=status)
            check_cancelled()
            if st.persist:
                report_progress(98, "ذخیرهٔ نتیجهٔ جایابی سطح ۲")
                store.set_kv("level2_placement_study", result.as_dict(), user=st.user)
            report_progress(100, "جست‌وجوی جایابی سطح ۲ کامل شد")
            return result
        finally:
            store.close()

    def _build_contexts(self, graph, net, traces, node_kw, rates, repairs,
                        transients, reliability, budget, level2, zone_of_node):
        contexts_by_type = {}
        for switch_type in level2.switch_types:
            check_cancelled()
            raw = dict(reliability.get("engine", {}) or {})
            raw["switch_type"] = switch_type
            raw["max_sectionalizers"] = 0
            # Counts are imposed by the exact search, not the legacy greedy cap.
            raw["max_candidates_per_feeder"] = 0
            default_rate = reliability.get("default_failure_rate_per_year")
            default_repair = reliability.get("default_repair_time_min")
            raw.setdefault("total_failure_rate_per_year",
                           0.0 if default_rate is None else float(default_rate))
            raw.setdefault("repair_time_min",
                           0.0 if default_repair is None else float(default_repair))
            engine_settings = SwitchPlacementSettings.from_dict(raw)
            study = SwitchPlacementEngine(engine_settings).run(
                graph, traces, node_kw, net=net,
                failure_rates=rates, repair_times=repairs,
                transient_rates=transients,
                failure_rate_source="level2-input-or-outage-records",
                backup_kw=dict(reliability.get("backup_kw", {}) or {}) or None,
                zone_of_node=zone_of_node)
            by_feeder = {f.feeder_key: f for f in study.feeders}
            trace_by_feeder = {str(t.feeder_key): t for t in traces}
            contexts = {}
            for feeder, feeder_study in by_feeder.items():
                check_cancelled()
                trace = trace_by_feeder.get(feeder)
                if trace is None:
                    hits = [t for t in traces if same_feeder(t.feeder_key, feeder)]
                    trace = hits[0] if len(hits) == 1 else None
                if trace is None:
                    continue
                tree = build_radial_tree(graph, trace, node_kw)
                contexts[feeder] = {
                    "study": feeder_study, "tree": tree, "trace": trace,
                    "engine_settings": engine_settings,
                    "node_kw": node_kw,
                    "existing_reclosers": _existing_reclosers(graph, net, tree),
                }
            contexts_by_type[switch_type] = contexts
        return contexts_by_type

    @staticmethod
    def _evaluate_flow_state(graph, net, traces, node_kw, node_kvar,
                             transformer_kva, settings):
        rows = []
        feasible = True
        from ..reliability.switch_placement import build_radial_tree
        for trace in sorted(traces, key=lambda t: t.feeder_key):
            row = {"feeder_key": trace.feeder_key}
            try:
                tree = build_radial_tree(graph, trace, node_kw)
                if tree.total_load_kw <= 0:
                    raise ValueError("بار مثبت به فیدر تخصیص نیافته است.")
                result = solve_radial_power_flow(
                    graph, tree, feeder_key=trace.feeder_key,
                    loads_kw=node_kw, loads_kvar=node_kvar,
                    transformer_kva_by_node=transformer_kva,
                    settings=settings)
                row.update({"status": "feasible" if result.feasible else "violated",
                            "min_voltage_pu": result.min_voltage_pu,
                            "max_voltage_pu": result.max_voltage_pu,
                            "max_line_loading_pct": result.max_line_loading_pct,
                            "max_transformer_loading_pct": result.max_transformer_loading_pct,
                            "losses_kw": result.losses_kw,
                            "violations": result.violations,
                            "missing_transformer_limits": result.missing_transformer_limits})
                feasible &= result.feasible
                if not result.feasible:
                    row["reason"] = "قیود بهره‌برداری یا دادهٔ ظرفیت ترانس کامل نیست."
            except (ValueError, RuntimeError) as exc:
                row.update({"status": "error", "reason": str(exc)})
                feasible = False
            rows.append(row)
        return rows, feasible


def load_level2_config(path: str | Path) -> Level2AppSettings:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return level2_settings_from_data(data)


def level2_settings_from_data(data: dict) -> Level2AppSettings:
    """Build service settings from JSON-loaded or directly-entered GUI data."""
    if not isinstance(data, dict):
        raise ValueError("پیکربندی سطح ۲ باید یک شیء تنظیمات باشد.")
    level2 = Level2Settings(**dict(data.get("level2", {})))
    pflow = PowerFlowSettings.from_dict(data.get("power_flow", {}))
    return Level2AppSettings(
        level2=level2, power_flow=pflow,
        load_model=dict(data.get("load_model", {}) or {}),
        reliability=dict(data.get("reliability", {}) or {}),
        equipment_types_path=str(data.get("equipment_types_catalog") or DEFAULT_TYPES_CATALOG),
        feeder_keys=(tuple(map(str, data["feeder_keys"]))
                     if data.get("feeder_keys") is not None else None),
        persist=bool(data.get("persist", False)),
        user=str(data.get("user") or "level2-placement"))


def _resolve_reliability_inputs(reliability, store, traces):
    data = {}
    notes = []
    try:
        data = store.load_outages()
    except ValueError:
        data = {}
    rows = data.get("lambda_r", []) or []
    events = data.get("events", []) or []
    rates, repairs, transients = {}, {}, {}
    for row in rows:
        key = str(row.get("feeder_key") or "")
        if not key:
            continue
        evidence = bool(row.get("events_random")) or float(row.get("exposure_years") or 0) > 0
        if evidence and row.get("lambda_per_year") is not None:
            rates[key] = float(row["lambda_per_year"])
        if evidence and row.get("r_minutes") is not None and float(row["r_minutes"]) > 0:
            repairs[key] = float(row["r_minutes"])
    rates.update({str(k): float(v) for k, v in (reliability.get("failure_rates", {}) or {}).items()})
    repairs.update({str(k): float(v) for k, v in (reliability.get("repair_times_min", {}) or {}).items()})
    transient_input = reliability.get("transient_rates", {}) or {}
    if transient_input:
        transients.update({str(k): float(v) for k, v in transient_input.items()})
    for label, values, minimum in (("λ", rates, 0.0),
                                   ("زمان تعمیر", repairs, 0.0),
                                   ("λ گذرا", transients, 0.0)):
        invalid = [k for k, v in values.items()
                   if not math.isfinite(float(v)) or float(v) < minimum]
        if invalid:
            raise ValueError(f"{label} نامعتبر برای: " + ", ".join(invalid))
    if not transient_input and events:
        random_classes = {"قابل کاهش با کلیدگذاری", "نیازمند تعمیر یا تعویض تجهیز",
                          "ناشی از هماهنگی حفاظتی"}
        max_duration = float(reliability.get("transient_max_duration_min", 3.0))
        counts = {}
        for event in events:
            if str(event.get("outage_class") or "") not in random_classes:
                continue
            key = str(event.get("feeder_key") or "")
            try:
                duration = float(event.get("duration_min"))
            except (TypeError, ValueError):
                continue
            slot = counts.setdefault(key, [0, 0])
            slot[1] += 1
            slot[0] += int(duration <= max_duration)
        for key, (short_n, total_n) in counts.items():
            rate = _lookup(rates, key)
            if rate is not None and total_n:
                transients[key] = rate * short_n / total_n
    default_rate = reliability.get("default_failure_rate_per_year")
    default_repair = reliability.get("default_repair_time_min")
    missing = []
    for trace in traces:
        key = str(trace.feeder_key)
        if _lookup(rates, key) is None:
            if default_rate is None:
                missing.append(f"λ برای {key}")
            else:
                rates[key] = float(default_rate)
        if _lookup(repairs, key) is None:
            if default_repair is None:
                missing.append(f"r برای {key}")
            else:
                repairs[key] = float(default_repair)
        if _lookup(transients, key) is None:
            transients[key] = 0.0
    if missing:
        raise ValueError("ورودی قابلیت اطمینان ناقص است؛ " + "، ".join(missing)
                         + ". مقادیر واقعی یا default صریح وارد کنید.")
    if not transient_input and not events:
        notes.append("دادهٔ خطاهای گذرای خاموشی وجود نداشت؛ نرخ گذرا برای ریکلوزر صفر است.")
    return rates, repairs, transients, notes


def _lookup(mapping, key):
    if key in mapping:
        return mapping[key]
    hits = [k for k in mapping if same_feeder(k, key)]
    return mapping[hits[0]] if len(hits) == 1 else None


def _resolve_budgets(raw, traces):
    budgets = {}
    known = [str(t.feeder_key) for t in traces]
    for feeder in known:
        value = _lookup(raw, feeder)
        budgets[feeder] = int(value or 0)
    unknown = [k for k in raw if not any(same_feeder(k, f) for f in known)]
    if unknown:
        raise ValueError("فیدرهای ناشناخته در nc_budget_by_feeder: " + ", ".join(unknown))
    return budgets


def _candidate_lists(contexts_by_type, mode, graph, node_kw):
    # Every reliability type uses the same feasible point set; take the first.
    contexts = next(iter(contexts_by_type.values()), {})
    loaded_nodes = {n for n, p in node_kw.items() if p > 1e-9}
    out = {}
    for feeder, ctx in contexts.items():
        candidates = list(ctx["study"].candidates)
        if mode == "load_points":
            candidates = [c for c in candidates if c.node in loaded_nodes]
        out[feeder] = candidates
    return out


def _score_feeder_eens(ctx, selected, switch_type, reliability):
    study = ctx["study"]
    tree = ctx["tree"]
    if not tree.order or tree.total_length_m <= 0:
        raise ValueError(f"درخت/طول فیدر {study.feeder_key} برای EENS معتبر نیست.")
    cuts = set(study.existing_cut_nodes) | {c.node for c in selected}
    sections = build_sections(tree, cuts)
    settings = ctx["engine_settings"]
    perm = compute_eens_kwh(
        sections,
        failure_rate=study.failure_rate_per_year,
        total_length_m=tree.total_length_m,
        total_load_kw=tree.total_load_kw,
        repair_time_min=study.repair_time_min,
        restoration_time_min=settings.effective_restoration_time_min,
        restoration_model=settings.restoration_model,
        backup_kw=study.backup_kw)
    transient = 0.0
    if switch_type == "recloser" and study.transient_rate_per_year > 0:
        selected_reclosers = set(ctx["existing_reclosers"]) | {c.node for c in selected}
        transient = compute_transient_eens_kwh(
            tree, sections,
            transient_rate=study.transient_rate_per_year,
            total_load_kw=tree.total_load_kw,
            transient_time_min=settings.transient_interruption_min,
            reclose_time_min=settings.reclose_time_min,
            reclose_success_probability=settings.reclose_success_probability,
            recloser_nodes=selected_reclosers)
    return float(perm + transient)


def _existing_reclosers(graph, net, tree):
    return {s.node_id for s in (net.switches or [])
            if s.family == SwitchFamily.RECLOSER and s.node_id in tree.parent}


def _candidate_ties(ties):
    by_switch = {}
    for tie in ties or []:
        if tie.switch_id:
            by_switch.setdefault(tie.switch_id, []).append(tie)
    selected, ambiguous = [], []
    for switch_id, rows in sorted(by_switch.items()):
        identities = {(row.node, row.feeder_a, row.feeder_b) for row in rows}
        if len(identities) != 1:
            ambiguous.append(
                f"کلید {switch_id} در چند اتصال توپولوژیک کاندید شده؛ "
                "برای تصمیم NO یکتا استفاده نشد.")
            continue
        selected.append(sorted(rows, key=lambda row: row.id)[0])
    return sorted(selected, key=lambda t: (t.feeder_a, t.feeder_b, t.node, t.id)), ambiguous


def _with_normally_open(net, ties):
    switch_ids = {t.switch_id for t in ties}
    cloned = copy(net)
    cloned.switches = [replace(sw, normally_state="NO") if sw.id in switch_ids else sw
                       for sw in (net.switches or [])]
    return cloned


def _tie_dict(tie):
    return {"id": tie.id, "switch_id": tie.switch_id, "node": tie.node,
            "feeder_a": tie.feeder_a, "feeder_b": tie.feeder_b,
            "rule": tie.rule, "status": tie.status,
            "automation_capable": tie.automation_capable}


def _loaded_node_occurrences(traces, node_kw):
    out = {}
    for trace in traces:
        for node in trace.nodes:
            if float(node_kw.get(node, 0.0) or 0.0) > 1e-9:
                out[node] = out.get(node, 0) + 1
    return out


def _transformer_kva_by_node(graph, net):
    by_id = {str(t.id): t for t in (net.transformers or [])}
    return {node: sum(float(by_id[sid].capacity_kva or 0.0)
                      for sid in ids if sid in by_id)
            for node, ids in graph.transformer_ids_at.items()}


def _apply_catalog_lines(flow_settings, catalog, branches):
    for branch in branches:
        resolved = catalog.resolve_branch(branch)
        if resolved.status != "matched":
            continue
        row = next(r for r in catalog.lines
                   if catalog._type_name(r) == resolved.selected_type)
        # An explicit project/form override wins; otherwise Sline is taken from
        # the type workbook (unit kA) and converted to A. Ithr is short-circuit current.
        ampacity = (flow_settings.type_ampacity_a or {}).get(resolved.selected_type)
        if ampacity is None:
            ampacity = catalog.line_ampacity_a(resolved.selected_type)
        if ampacity is None:
            continue
        flow_settings.edge_overrides[str(branch.id)] = {
            "r_ohm_per_km": float(row["rline(r)"]),
            "x_ohm_per_km": float(row["xline(r)"]),
            "max_current_a": float(ampacity),
        }


def _plan_signature(plan):
    data = plan.as_dict() if hasattr(plan, "as_dict") else plan
    return (tuple((f, tuple(d.get("node", "") for d in ds))
                  for f, ds in sorted(data.get("nc_by_feeder", {}).items())),
            tuple(d.get("id", "") for d in data.get("normally_open_ties", [])))
