# -*- coding: utf-8 -*-
"""Project adapter for the balanced radial power-flow MVP.

The project GIS is topology/load data, not an impedance database.  The
engineer supplies an explicit line-impedance/ampacity catalog and source
voltage in a JSON config.  No line values are guessed from conductor labels.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field as dc_field
from pathlib import Path

from ..persistence.store import ProjectStore
from .equipment_types import (DEFAULT_TYPES_CATALOG, EquipmentTypeCatalog,
                              resolution_report)
from ..reliability.load_model import LoadModelSettings, build_node_loads
from ..reliability.power_flow import PowerFlowSettings, solve_radial_power_flow
from ..task_control import check_cancelled, report_progress
from ..reliability.switch_placement import build_radial_tree
from ..topology.tracing import same_feeder
from ..validation.issues import IssueLog


@dataclass
class PowerFlowAppSettings:
    power_flow: PowerFlowSettings
    load_model: dict = dc_field(default_factory=dict)
    feeder_keys: tuple = ()
    equipment_types_path: str = str(DEFAULT_TYPES_CATALOG)


@dataclass
class PowerFlowAppResult:
    results: list
    settings: dict
    load_model_level: str
    warnings: list[str] = dc_field(default_factory=list)
    errors: list[dict] = dc_field(default_factory=list)
    equipment_type_report: dict = dc_field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "settings": self.settings,
            "load_model_level": self.load_model_level,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "equipment_types": self.equipment_type_report,
            "feeders": [r.as_dict() for r in self.results],
        }

    @property
    def markdown(self) -> str:
        lines = ["# پخش بار شعاعی متعادل — گزارش فیدرها", "",
                 f"**ولتاژ مبنا:** {self.settings['base_voltage_kv']:g} kV LL · "
                 f"**مدل بار:** {self.load_model_level} · "
                 "**مدل:** سه‌فاز متعادل، بار ثابت P/Q، Backward/Forward Sweep", "",
                 "| فیدر | وضعیت | Vmin (pu) | Vmax (pu) | بیشینه بار خط (%) | "
                 "بیشینه بار ترانس (%) | تلفات (kW) | تکرار |",
                 "|---|---|---:|---:|---:|---:|---:|---:|"]
        for r in self.results:
            status = "مجاز" if r.feasible else (
                "نقض قید" if r.constraints_complete else "دادهٔ قید ناقص")
            lines.append(
                f"| {r.feeder_key} | {status} | {_fmt(r.min_voltage_pu)} | "
                f"{_fmt(r.max_voltage_pu)} | {_fmt(r.max_line_loading_pct)} | "
                f"{_fmt(r.max_transformer_loading_pct)} | {r.losses_kw:.3f} | "
                f"{r.iterations} |")
        totals = self.equipment_type_report.get("totals", {})
        if totals:
            lines += ["", "## تطبیق تایپ‌های تجهیزات GIS", "",
                      f"نتیجهٔ کاتالوگ: {totals.get('matched', 0)} تطبیق یکتا، "
                      f"{totals.get('ambiguous', 0)} مبهم، "
                      f"{totals.get('unmatched', 0)} بدون تطبیق، "
                      f"{totals.get('unsupported', 0)} پشتیبانی‌نشده و "
                      f"{totals.get('unusable', 0)} تایپ غیرقابل‌استفاده.",
                      "جزئیات تجهیز، ورودی GIS، تایپ انتخاب‌شده و کاندیدها "
                      "در `equipment_types` خروجی JSON ثبت شده است.",
                      "", "| فیدر | یکتا | مبهم | بدون تطبیق | پشتیبانی‌نشده | غیرقابل‌استفاده |",
                      "|---|---:|---:|---:|---:|---:|"]
            for feeder, details in sorted(self.equipment_type_report.get("feeders", {}).items()):
                counts = details.get("counts", {})
                lines.append(
                    f"| {feeder} | {counts.get('matched', 0)} | "
                    f"{counts.get('ambiguous', 0)} | {counts.get('unmatched', 0)} | "
                    f"{counts.get('unsupported', 0)} | {counts.get('unusable', 0)} |")
        lines += ["", "## فیدرهای حل‌نشده", ""]
        if self.errors:
            lines.extend(f"- {e['feeder_key']}: {e['error']}" for e in self.errors)
        else:
            lines.append("فیدر حل‌نشده‌ای ثبت نشد.")
        lines += ["", "## موارد نقض / دادهٔ ناقص", ""]
        any_detail = False
        for r in self.results:
            for v in r.violations:
                any_detail = True
                lines.append(f"- {r.feeder_key}: `{v['kind']}` روی `{v['element']}`؛ "
                             f"مقدار {v['value']:.5g}، حد {v['limit']:.5g}.")
            if r.missing_transformer_limits:
                any_detail = True
                lines.append(f"- {r.feeder_key}: بار بدون ظرفیت ترانسِ قابل ارزیابی: "
                             + ", ".join(r.missing_transformer_limits))
        if not any_detail:
            lines.append("موردی ثبت نشد.")
        if self.warnings:
            lines += ["", "## هشدارها", ""]
            lines.extend(f"- {w}" for w in self.warnings)
        lines += ["", "> نتیجه فقط برای حالت عادی شعاعی است؛ این گزارش به‌تنهایی "
                  "جایابی کلید/بازآرایی یا تحلیل نامتعادلی سه‌فاز نیست."]
        return "\n".join(lines)


class PowerFlowService:
    """Load a project, distribute configured P/Q, and solve each feeder."""

    def __init__(self, settings: PowerFlowAppSettings):
        settings.power_flow.validate()
        self.settings = settings

    def run(self, db_path: str) -> PowerFlowAppResult:
        check_cancelled()
        report_progress(0, "شروع پخش بار")
        store = ProjectStore(db_path)
        try:
            runs = store.runs()
            if not runs:
                raise ValueError("پروژه هیچ دادهٔ ورودی ندارد.")
            net, issues = store.load_network(runs[-1]["id"])
            catalog = EquipmentTypeCatalog(self.settings.equipment_types_path)
            type_resolutions = catalog.resolve_network(
                net, voltage_kv=self.settings.power_flow.base_voltage_kv)
            type_report = resolution_report(type_resolutions)
            flow_settings = PowerFlowSettings.from_dict(
                self.settings.power_flow.as_dict())
            # Workbook line R/X is selected from GIS identity. Ampacity remains
            # an explicit engineer input keyed by workbook type name because
            # the workbook's sline/Ithr units are not validated by this model.
            branch_resolutions = type_resolutions[:len(net.branches or [])]
            for branch, resolution in zip(net.branches or [], branch_resolutions, strict=True):
                if resolution.equipment != "line" or resolution.status != "matched":
                    continue
                type_name = resolution.selected_type
                branch_id = str(branch.id)
                if branch_id in (flow_settings.edge_overrides or {}):
                    continue  # an explicit branch override always wins
                max_current = (flow_settings.type_ampacity_a or {}).get(type_name)
                if max_current is None:
                    continue
                row = next(r for r in catalog.lines
                           if catalog._type_name(r) == type_name)
                flow_settings.edge_overrides[branch_id] = {
                    "r_ohm_per_km": float(row["rline(r)"]),
                    "x_ohm_per_km": float(row["xline(r)"]),
                    "max_current_a": float(max_current),
                }
            topo_kv = store.get_kv("engineering_load_model_v1", {}) or {}
            lm_data = dict(self.settings.load_model or topo_kv)
            if not lm_data:
                raise ValueError("مدل بار پروژه وجود ندارد؛ P/Q فیدرها را تکمیل کنید.")
            topo = _topology(net, issues)
            lm_settings = LoadModelSettings.from_dict(lm_data)
            warnings: list[str] = []
            totals = type_report["totals"]
            unresolved = totals["ambiguous"] + totals["unmatched"] + totals["unsupported"] + totals["unusable"]
            if unresolved:
                warnings.append(
                    f"تطبیق تایپ تجهیزات: {totals['matched']} یکتا، {unresolved} "
                    "مبهم/بدون تطبیق/پشتیبانی‌نشده؛ جزئیات در equipment_types گزارش JSON است.")
            selected_without_ampacity = sum(
                1 for item in type_report["feeders"].values()
                for detail in item["items"]
                if detail["equipment"] == "line" and detail["status"] == "matched"
                and detail["selected_type"] not in (flow_settings.type_ampacity_a or {}))
            if selected_without_ampacity:
                warnings.append(
                    f"برای {selected_without_ampacity} خطِ دارای تایپ یکتا، حد جریان آمپری "
                    "تأییدشده در type_ampacity_a تعریف نشده است؛ R/X تایپ اعمال نشد.")
            load_issues = IssueLog()
            load = build_node_loads(topo.graph, net, lm_settings,
                                    issues=load_issues)
            warnings.extend(i.message_fa for i in load_issues.items()
                            if i.severity != "Information")
            node_kw = {n: float(v or 0.0) for n, v in load.node_kw.items()}
            node_kvar = {n: float(v or 0.0) for n, v in load.node_kvar.items()}
            # Non-scaled load models often have no Q data.  Only then use the
            # explicit, reported power-factor assumption; scaled P/Q is exact.
            q_is_explicit = (lm_settings.level == "scaled" or any(
                ld.q_kvar is not None for ld in (getattr(net, "loads", None) or [])))
            if not q_is_explicit and any(abs(v) > 1e-9 for v in node_kw.values()):
                tan_phi = math.tan(math.acos(self.settings.power_flow.assumed_power_factor))
                node_kvar = {n: abs(p) * tan_phi for n, p in node_kw.items()}
                warnings.append(
                    "Q در دادهٔ بار موجود نبود؛ Q=P·tan(arccos(pf)) با "
                    f"pf={self.settings.power_flow.assumed_power_factor:g} فرض شد.")
            transformer_by_id = {str(t.id): t for t in (net.transformers or [])}
            transformer_kva_by_node = {}
            for node, ids in topo.graph.transformer_ids_at.items():
                transformer_kva_by_node[node] = sum(
                    float(transformer_by_id[sid].capacity_kva or 0.0)
                    for sid in ids if str(sid) in transformer_by_id)

            wanted = [str(k) for k in (self.settings.feeder_keys or ())]
            traces = [tr for tr in topo.traces if not wanted or any(
                same_feeder(tr.feeder_key, key) for key in wanted)]
            if wanted:
                missing = [k for k in wanted if not any(
                    same_feeder(tr.feeder_key, k) for tr in traces)]
                if missing:
                    warnings.append("فیدر(های) پیدا نشده: " + ", ".join(missing))
            results = []
            errors = []
            ordered_traces = sorted(traces, key=lambda x: x.feeder_key)
            for index, tr in enumerate(ordered_traces):
                check_cancelled()
                report_progress(10 + 85 * index / max(1, len(ordered_traces)),
                                f"حل پخش بار فیدر {tr.feeder_key}")
                try:
                    tree = build_radial_tree(topo.graph, tr, node_kw)
                    if tree.total_load_kw <= 1e-9:
                        errors.append({
                            "feeder_key": tr.feeder_key,
                            "error": ("بار مثبت به گراف فیدر تخصیص نیافته؛ "
                                      "پخش بار/قیود بارگیری قابل ارزیابی نیست.")})
                        continue
                    result = solve_radial_power_flow(
                        topo.graph, tree, feeder_key=tr.feeder_key,
                        loads_kw=node_kw, loads_kvar=node_kvar,
                        transformer_kva_by_node=transformer_kva_by_node,
                        settings=flow_settings)
                    results.append(result)
                except (ValueError, RuntimeError) as exc:
                    errors.append({"feeder_key": tr.feeder_key, "error": str(exc)})
            check_cancelled()
            report_progress(100, "پخش بار کامل شد")
            return PowerFlowAppResult(
                results=results,
                settings=flow_settings.as_dict(),
                load_model_level=lm_settings.level,
                warnings=warnings, errors=errors,
                equipment_type_report=type_report)
        finally:
            store.close()


def _topology(net, issues):
    from .topology_service import TopologyService, TopologySettings
    return TopologyService(TopologySettings(persist=False)).run(net, issues=issues)


def _fmt(value) -> str:
    return "—" if value is None else f"{value:.4f}"


def load_power_flow_config(path: str | Path) -> PowerFlowSettings:
    """Read an engineer-maintained JSON configuration file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("فایل تنظیمات پخش بار باید یک شیء JSON باشد.")
    return PowerFlowSettings.from_dict(data)
