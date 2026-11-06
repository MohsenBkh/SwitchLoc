# -*- coding: utf-8 -*-
"""Scenario model — وضعیت کلیدها، مانور و اثر آن بر برق‌داری (فاز ۲).

State semantics (documented, no hidden assumptions):
* a switch is OPEN when: confirmed NO, or OUT_OF_SERVICE
  (TOPO-POL-01: physically out of service), or an explicit scenario
  action opened it;
* a switch is CLOSED when: IN_SERVICE (and not NO) — or UNKNOWN while
  `unknown_switch_pass` holds (the same policy as tracing, so the base
  scenario is *consistent* with the normal-state map);
* a scenario action may only reference a switch that exists; actions are
  applied in order and recorded verbatim.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field as dc_field
from datetime import datetime

from ..domain.entities import CanonicalNetwork
from ..domain.enums import SwitchState
from ..validation.issues import IssueLog, ValidationIssue, SEVERITY_WARNING
from ..topology.graph import NetworkGraph
from ..topology.tracing import TracingPolicy, feeder_key


@dataclass
class ScenarioAction:
    switch_id: str
    action: str                      # "open" | "close"
    reason_fa: str = ""
    user: str = ""
    at: str = ""

    def as_dict(self) -> dict:
        return {"switch_id": self.switch_id, "action": self.action,
                "reason_fa": self.reason_fa, "user": self.user, "at": self.at}


class ScenarioState:
    """Effective open/closed decision per switch id."""

    def __init__(self, open_switches: set[str]):
        self.open_switches = set(open_switches)

    def is_open(self, switch_id: str) -> bool:
        return switch_id in self.open_switches

    def is_closed(self, switch_id: str) -> bool:
        return switch_id not in self.open_switches

    def as_dict(self) -> dict:
        return {"open_switches": sorted(self.open_switches)}


def base_state(net: CanonicalNetwork,
               policy: TracingPolicy | None = None) -> ScenarioState:
    """Normal configuration straight from the canonical model (بند ۷-۷-۵)."""
    p = policy or TracingPolicy()
    opened: set[str] = set()
    for sw in net.switches:
        if (sw.normally_state or "").strip().upper() == "NO":
            opened.add(sw.id)
        elif sw.current_state == SwitchState.OUT_OF_SERVICE:
            if p.out_of_service_blocks:
                opened.add(sw.id)
        elif sw.current_state == SwitchState.UNKNOWN:
            if not p.unknown_switch_pass:
                opened.add(sw.id)
    return ScenarioState(opened)


class SwitchScenario:
    """One named switching configuration (base + ordered actions)."""

    def __init__(self, name: str, base: ScenarioState,
                 actions: list[ScenarioAction] | None = None,
                 note: str = ""):
        self.name = name
        self.base = base
        self.actions = list(actions or [])
        self.note = note
        self._effective: ScenarioState | None = None

    # ------------------------------------------------------------------
    def add_action(self, switch_id: str, action: str, reason_fa: str = "",
                   user: str = "") -> ScenarioAction:
        if action not in ("open", "close"):
            raise ValueError("عملیات مجاز: open | close")
        act = ScenarioAction(switch_id=switch_id, action=action,
                             reason_fa=reason_fa, user=user,
                             at=datetime.now().isoformat(timespec="seconds"))
        self.actions.append(act)
        self._effective = None                      # invalidate cache
        return act

    def effective_state(self) -> ScenarioState:
        """Base state with actions applied in order (deterministic)."""
        if self._effective is None:
            opened = set(self.base.open_switches)
            for act in self.actions:
                if act.action == "open":
                    opened.add(act.switch_id)
                else:
                    opened.discard(act.switch_id)
            self._effective = ScenarioState(opened)
        return self._effective

    def as_dict(self) -> dict:
        return {
            "name": self.name, "note": self.note,
            "base": self.base.as_dict(),
            "actions": [a.as_dict() for a in self.actions],
            "effective": self.effective_state().as_dict(),
        }


@dataclass
class ConnectivityResult:
    """Outcome of evaluating one scenario against the graph."""
    scenario: str
    energized_by_feeder: dict = dc_field(default_factory=dict)  # key → set(nodes)
    energized_nodes: set = dc_field(default_factory=set)
    energized_edges: set = dc_field(default_factory=set)
    deenergized_nodes: set = dc_field(default_factory=set)
    deenergized_edges: set = dc_field(default_factory=set)
    isolated_zone_ids: set = dc_field(default_factory=set)      # fully dead zones

    def summary(self) -> dict:
        return {
            "scenario": self.scenario,
            "energized_nodes": len(self.energized_nodes),
            "energized_edges": len(self.energized_edges),
            "deenergized_nodes": len(self.deenergized_nodes),
            "deenergized_edges": len(self.deenergized_edges),
            "by_feeder": {k: len(v) for k, v in
                          sorted(self.energized_by_feeder.items())},
            "isolated_zones": len(self.isolated_zone_ids),
        }


def evaluate(graph: NetworkGraph, net: CanonicalNetwork,
             scenario: SwitchScenario,
             zone_of_edge: dict | None = None,
             issues: IssueLog | None = None) -> ConnectivityResult:
    """Energized/de-energized computation for one scenario (deterministic).

    Traversal rule mirrors `topology.tracing` with the scenario's
    effective states substituted for the GIS states, so the normal map
    and any what-if stay consistent by construction.
    """
    if issues is not None:
        known = {s.id for s in net.switches}
        for act in scenario.actions:
            if act.switch_id not in known:
                issues.add(ValidationIssue(
                    code="SCEN-ACTION-UNKNOWN-SWITCH", severity=SEVERITY_WARNING,
                    message_fa="عملیات سناریو به کلید ناموجود اشاره دارد.",
                    record_id=act.switch_id, current_value=act.action,
                    impact_fa="عملیات نادیده گرفته شد."))

    state = scenario.effective_state()
    res = ConnectivityResult(scenario=scenario.name)

    def passable(node: str) -> bool:
        for sid in graph.switch_ids_at.get(node, ()):
            if state.is_open(sid):
                return False
        return True

    seeds = sorted((n, feeder_key(f))
                   for n, f in graph.source_of.items())
    visited_edges: set[str] = set()
    for start, fkey in seeds:
        if start in res.energized_nodes:
            continue
        res.energized_nodes.add(start)
        res.energized_by_feeder.setdefault(fkey, set()).add(start)
        queue = deque([start]) if passable(start) else deque()
        while queue:
            node = queue.popleft()
            for nbr, eid in graph.neighbors(node):
                if eid in visited_edges:
                    continue
                visited_edges.add(eid)
                res.energized_edges.add(eid)
                res.energized_nodes.add(nbr)
                res.energized_by_feeder.setdefault(fkey, set()).add(nbr)
                if passable(nbr):
                    queue.append(nbr)

    res.deenergized_edges = set(graph.edges) - res.energized_edges
    res.deenergized_nodes = ({n for n in graph.nodes
                              if graph.adj.get(n) or graph.is_source(n)}
                             - res.energized_nodes)
    if zone_of_edge:
        dead_edges = [zone_of_edge[e] for e in res.deenergized_edges
                      if e in zone_of_edge]
        live_edges = [zone_of_edge[e] for e in res.energized_edges
                      if e in zone_of_edge]
        dead = set(dead_edges) - set(live_edges)
        res.isolated_zone_ids = dead
    return res


def isolation_scenario(graph: NetworkGraph, net: CanonicalNetwork,
                       zone_id: str, zone_of_edge: dict,
                       boundary_of_switch: dict, name: str,
                       user: str = "") -> SwitchScenario:
    """Fault-isolation switching for one zone (جدول ۱۵ base operation).

    Proposes opening every CLOSED boundary switch of the zone — the
    classic «باز کردن کلیدهای دو طرف زون معیوب».  Returned as a scenario
    the engineer reviews; nothing is auto-applied to the GIS.
    """
    base = base_state(net)
    scen = SwitchScenario(name=name, base=base,
                          note=f"جداسازی زون {zone_id[:8]}… برای شبیه‌سازی "
                               f"خطای داخل زون (جدول ۱۵)")
    zone_edges = {e for e, z in zone_of_edge.items() if z == zone_id}
    touched: set[str] = set()
    for eid in sorted(zone_edges):
        e = graph.edges[eid]
        for n in (e.a, e.b):
            for sid in graph.switch_ids_at.get(n, ()):
                br = boundary_of_switch.get(sid)
                if br is None or zone_id not in br.zones:
                    continue
                if sid in touched:
                    continue
                if base.is_closed(sid):
                    scen.add_action(sid, "open",
                                    reason_fa="مرز زون معیوب — جداسازی",
                                    user=user)
                touched.add(sid)
    return scen
