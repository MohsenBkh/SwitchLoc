# -*- coding: utf-8 -*-
"""Balanced three-phase radial power flow (positive-sequence MVP).

This is an engineering calculation, not an impedance estimator.  Every line
must resolve to an explicit R/X and ampacity record supplied by the engineer.
Loads are balanced three-phase constant-P/Q loads.  The solver uses a backward-
forward sweep and reports normal-state voltage, current, losses, and operating
limit violations.  It deliberately refuses meshed/disconnected trees instead
of silently solving a spanning-tree approximation.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Mapping

from ..topology.graph import NetworkGraph


@dataclass(frozen=True)
class LineElectricalData:
    """Per-kilometre balanced line data; ampacity is a three-phase line limit."""

    r_ohm_per_km: float
    x_ohm_per_km: float
    max_current_a: float

    def validate(self) -> None:
        vals = (self.r_ohm_per_km, self.x_ohm_per_km, self.max_current_a)
        if not all(math.isfinite(float(v)) for v in vals):
            raise ValueError("پارامترهای R/X/جریان خط باید عدد متناهی باشند.")
        if self.r_ohm_per_km < 0 or self.x_ohm_per_km < 0:
            raise ValueError("R و X خط نمی‌توانند منفی باشند.")
        if self.max_current_a <= 0:
            raise ValueError("حد جریان خط باید بزرگ‌تر از صفر باشد.")


@dataclass
class PowerFlowSettings:
    """Explicit assumptions and line-impedance catalog for a radial feeder.

    ``line_catalog`` keys are ``CONDUCTOR|SECTION_MM2|INSTALLATION``.  The
    wildcard ``*`` is accepted for section and/or installation, but conductor
    must always match exactly.  A per-edge override may be keyed by graph edge
    id or by canonical branch id and has the same data fields.
    """

    base_voltage_kv: float
    source_voltage_pu: float = 1.0
    voltage_min_pu: float = 0.95
    voltage_max_pu: float = 1.05
    transformer_loading_limit_pct: float = 100.0
    tolerance_pu: float = 1e-8
    max_iterations: int = 100
    assumed_power_factor: float = 1.0
    line_catalog: dict = field(default_factory=dict)
    edge_overrides: dict = field(default_factory=dict)
    # Workbook types do not provide an independently verified ampacity unit.
    # Require explicit engineer-confirmed current ratings by selected type.
    type_ampacity_a: dict = field(default_factory=dict)

    def validate(self) -> None:
        if not math.isfinite(float(self.base_voltage_kv)) or self.base_voltage_kv <= 0:
            raise ValueError("ولتاژ مبنا باید بر حسب kV و بزرگ‌تر از صفر باشد.")
        if not math.isfinite(float(self.source_voltage_pu)) or self.source_voltage_pu <= 0:
            raise ValueError("ولتاژ منبع pu باید بزرگ‌تر از صفر باشد.")
        if not (0 < self.voltage_min_pu <= self.voltage_max_pu):
            raise ValueError("حدود ولتاژ pu نامعتبر است.")
        if self.transformer_loading_limit_pct <= 0:
            raise ValueError("حد بارگیری ترانس باید مثبت باشد.")
        if self.tolerance_pu <= 0 or self.max_iterations < 1:
            raise ValueError("تنظیمات همگرایی نامعتبر است.")
        if not (0 < self.assumed_power_factor <= 1):
            raise ValueError("ضریب توان فرضی باید در بازهٔ (۰،۱] باشد.")
        for raw in (self.line_catalog or {}).values():
            LineElectricalData(**raw).validate()
        for raw in (self.edge_overrides or {}).values():
            LineElectricalData(**raw).validate()
        for type_name, rating in (self.type_ampacity_a or {}).items():
            if not math.isfinite(float(rating)) or float(rating) <= 0:
                raise ValueError(f"حد جریان تایپ {type_name!r} باید آمپر مثبت باشد.")

    @classmethod
    def from_dict(cls, data: dict | None) -> "PowerFlowSettings":
        known = {k: v for k, v in dict(data or {}).items()
                 if k in cls.__dataclass_fields__}
        obj = cls(**known)
        obj.validate()
        return obj

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class PowerFlowResult:
    feeder_key: str
    converged: bool
    feasible: bool
    constraints_complete: bool
    iterations: int
    min_voltage_pu: float | None
    max_voltage_pu: float | None
    max_line_loading_pct: float | None
    max_transformer_loading_pct: float | None
    total_load_kw: float
    total_load_kvar: float
    losses_kw: float
    source_p_kw: float
    source_q_kvar: float
    voltages_pu: dict[str, float]
    branch_currents_a: dict[str, float]
    branch_loading_pct: dict[str, float]
    transformer_loading_pct: dict[str, float]
    missing_line_limits: list[str]
    missing_transformer_limits: list[str]
    violations: list[dict]
    assumptions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def line_catalog_key(conductor: str, section_mm2: float | None,
                     installation: str = "") -> str:
    """Canonical key shared by config files and edge lookup."""
    c = " ".join(str(conductor or "").strip().upper().split())
    inst = " ".join(str(installation or "").strip().upper().split()) or "*"
    section = "*" if section_mm2 is None else _fmt_section(section_mm2)
    return f"{c}|{section}|{inst}"


def _fmt_section(value: float) -> str:
    return f"{float(value):g}"


def _line_data(graph: NetworkGraph, edge_id: str,
               settings: PowerFlowSettings) -> LineElectricalData | None:
    edge = graph.edges[edge_id]
    branch_id = str(getattr(edge, "branch_id", "") or "")
    overrides = settings.edge_overrides or {}
    raw = overrides.get(edge_id) or overrides.get(branch_id)
    if raw is not None:
        item = LineElectricalData(**raw)
        item.validate()
        return item

    conductor = str(getattr(edge, "conductor", "") or "").strip().upper()
    section = getattr(edge, "section_mm2", None)
    installation = str(getattr(edge, "installation", "") or "").strip().upper()
    if not conductor:
        return None
    sec = _fmt_section(section) if section is not None else "*"
    inst = installation or "*"
    keys = [f"{conductor}|{sec}|{inst}", f"{conductor}|{sec}|*",
            f"{conductor}|*|{inst}", f"{conductor}|*|*"]
    catalog = settings.line_catalog or {}
    for key in keys:
        if key in catalog:
            item = LineElectricalData(**catalog[key])
            item.validate()
            return item
    return None


def solve_radial_power_flow(
    graph: NetworkGraph,
    tree,
    *,
    feeder_key: str,
    loads_kw: Mapping[str, float],
    loads_kvar: Mapping[str, float] | None = None,
    transformer_kva_by_node: Mapping[str, float] | None = None,
    settings: PowerFlowSettings,
) -> PowerFlowResult:
    """Solve one balanced radial feeder with a backward-forward sweep.

    ``tree`` is a :class:`RadialTree` from ``switch_placement``.  Loads are
    total three-phase kW/kvar at buses.  Transformer ratings at a bus are
    summed; the reported loading is based on the apparent load at that bus.
    No transformer impedance, shunt capacitance, phase unbalance, or generator
    model is implied.
    """
    settings.validate()
    root = str(getattr(tree, "root", "") or "")
    order = list(getattr(tree, "order", ()) or ())
    if not root or not order or order[0] != root:
        raise ValueError("درخت فیدر ریشه/ترتیب معتبر ندارد.")
    if getattr(tree, "extra_edge_ids", ()) or getattr(tree, "unreachable_edge_ids", ()):
        raise ValueError("پخش بار نسخهٔ اول فقط برای فیدر شعاعیِ بدون یال حلقه‌ای است.")
    if len(order) != len(set(order)):
        raise ValueError("گره تکراری در درخت فیدر پیدا شد.")

    nodes = set(order)
    p_kw = {n: _finite_load((loads_kw or {}).get(n, 0.0), n, "kW")
            for n in order}
    q_kvar = {n: _finite_load((loads_kvar or {}).get(n, 0.0), n, "kvar")
              for n in order}
    child_nodes: dict[str, list[str]] = {n: [] for n in order}
    edge_for_node: dict[str, str] = {}
    for n in order[1:]:
        parent = getattr(tree, "parent", {}).get(n)
        edge_id = getattr(tree, "parent_edge", {}).get(n)
        if parent not in nodes or not edge_id or edge_id not in graph.edges:
            raise ValueError(f"درخت برای گرهٔ {n} یال والد معتبر ندارد.")
        edge = graph.edges[edge_id]
        if {edge.a, edge.b} != {parent, n}:
            raise ValueError(f"یال {edge_id} با رابطهٔ والد/فرزند سازگار نیست.")
        child_nodes[parent].append(n)
        edge_for_node[n] = edge_id

    lengths_z: dict[str, complex] = {}
    ampacity: dict[str, float] = {}
    missing_lines = []
    for node, edge_id in edge_for_node.items():
        edge = graph.edges[edge_id]
        data = _line_data(graph, edge_id, settings)
        if data is None:
            missing_lines.append(edge_id)
            continue
        length_km = float(edge.length_m or 0.0) / 1000.0
        if not math.isfinite(length_km) or length_km < 0:
            raise ValueError(f"طول یال {edge_id} نامعتبر است.")
        lengths_z[node] = complex(data.r_ohm_per_km, data.x_ohm_per_km) * length_km
        ampacity[edge_id] = float(data.max_current_a)
    if missing_lines:
        raise ValueError("امپدانس/حد جریان برای همهٔ یال‌ها لازم است؛ فاقد داده: "
                         + ", ".join(missing_lines[:12])
                         + (" …" if len(missing_lines) > 12 else ""))

    # Per-phase volts and VA; catalog impedances are per phase.
    v_base_phase_v = float(settings.base_voltage_kv) * 1000.0 / math.sqrt(3.0)
    v_source = v_base_phase_v * float(settings.source_voltage_pu) + 0j
    voltages = {n: v_source for n in order}
    branch_current: dict[str, complex] = {}
    converged = False
    iterations = 0
    for iteration in range(1, int(settings.max_iterations) + 1):
        iterations = iteration
        downstream: dict[str, complex] = {}
        for node in reversed(order):
            v = voltages[node]
            if abs(v) < 1e-6:
                raise ValueError(f"ولتاژ گرهٔ {node} به صفر نزدیک شد؛ حل ناپایدار است.")
            s_phase_va = complex(p_kw[node], q_kvar[node]) * (1000.0 / 3.0)
            local_i = (s_phase_va / v).conjugate()
            downstream[node] = local_i + sum(downstream[c] for c in child_nodes[node])
            if node != root:
                branch_current[edge_for_node[node]] = downstream[node]

        updated = {root: v_source}
        for node in order[1:]:
            parent = tree.parent[node]
            updated[node] = updated[parent] - branch_current[edge_for_node[node]] * lengths_z[node]
        max_delta_pu = max(abs(updated[n] - voltages[n]) / v_base_phase_v
                           for n in order)
        voltages = updated
        if max_delta_pu <= settings.tolerance_pu:
            converged = True
            break
    if not converged:
        raise RuntimeError(f"پخش بار پس از {settings.max_iterations} تکرار همگرا نشد.")

    node_pu = {n: abs(v) / v_base_phase_v for n, v in voltages.items()}
    edge_current_a = {eid: abs(i) for eid, i in branch_current.items()}
    branch_loading = {eid: edge_current_a[eid] / ampacity[eid] * 100.0
                      for eid in edge_current_a}
    trafo_loading: dict[str, float] = {}
    missing_transformers = []
    for node, raw_rating in (transformer_kva_by_node or {}).items():
        if node not in nodes:
            continue
        rating = float(raw_rating or 0.0)
        apparent = math.hypot(p_kw[node], q_kvar[node])
        key = str(node)
        if rating <= 0:
            if apparent > 1e-9:
                missing_transformers.append(key)
            continue
        trafo_loading[key] = apparent / rating * 100.0
    for node in order:
        if math.hypot(p_kw[node], q_kvar[node]) > 1e-9 \
                and node not in (transformer_kva_by_node or {}):
            missing_transformers.append(node)

    violations: list[dict] = []
    for node, pu in node_pu.items():
        if pu < settings.voltage_min_pu - 1e-9:
            violations.append({"kind": "undervoltage", "element": node,
                               "value": pu, "limit": settings.voltage_min_pu})
        if pu > settings.voltage_max_pu + 1e-9:
            violations.append({"kind": "overvoltage", "element": node,
                               "value": pu, "limit": settings.voltage_max_pu})
    for eid, pct in branch_loading.items():
        if pct > 100.0 + 1e-9:
            violations.append({"kind": "line_overload", "element": eid,
                               "value": pct, "limit": 100.0})
    for node, pct in trafo_loading.items():
        if pct > settings.transformer_loading_limit_pct + 1e-9:
            violations.append({"kind": "transformer_overload", "element": node,
                               "value": pct, "limit": settings.transformer_loading_limit_pct})

    losses_kw = sum(3.0 * abs(branch_current[eid]) ** 2
                    * lengths_z[node].real / 1000.0
                    for node, eid in edge_for_node.items())
    # Slack complex power includes root load and all feeder currents at source.
    source_i = downstream[root]
    source_s_kva = 3.0 * v_source * source_i.conjugate() / 1000.0
    max_voltage = max(node_pu.values()) if node_pu else None
    min_voltage = min(node_pu.values()) if node_pu else None
    max_line = max(branch_loading.values()) if branch_loading else None
    max_trafo = max(trafo_loading.values()) if trafo_loading else None
    complete = not missing_transformers
    feasible = converged and not violations and complete
    assumptions = [
        "مدل سه‌فاز متعادل/توالی مثبت با بار ثابت P/Q و پخش رفت‌وبرگشتی اجرا شد.",
        "امپدانس ترانس، شنت خط، عدم‌تعادل فاز، تولید پراکنده و کنترل تپ در این MVP مدل نشده‌اند.",
    ]
    if missing_transformers:
        assumptions.append("ظرفیت ترانس برای گره(های) باردار ثبت نشده؛ امکان تأیید حد بارگیری کامل نیست.")
    return PowerFlowResult(
        feeder_key=str(feeder_key), converged=converged, feasible=feasible,
        constraints_complete=complete, iterations=iterations,
        min_voltage_pu=min_voltage, max_voltage_pu=max_voltage,
        max_line_loading_pct=max_line, max_transformer_loading_pct=max_trafo,
        total_load_kw=sum(p_kw.values()), total_load_kvar=sum(q_kvar.values()),
        losses_kw=float(losses_kw), source_p_kw=float(source_s_kva.real),
        source_q_kvar=float(source_s_kva.imag), voltages_pu=node_pu,
        branch_currents_a=edge_current_a, branch_loading_pct=branch_loading,
        transformer_loading_pct=trafo_loading,
        missing_line_limits=[], missing_transformer_limits=sorted(set(missing_transformers)),
        violations=violations, assumptions=assumptions)


def _finite_load(value, node: str, unit: str) -> float:
    result = float(value or 0.0)
    if not math.isfinite(result):
        raise ValueError(f"بار {unit} گرهٔ {node} باید متناهی باشد.")
    return result
