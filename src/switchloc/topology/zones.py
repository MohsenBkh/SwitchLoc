# -*- coding: utf-8 -*-
"""Zone building — زون‌بندی شبکه فشار متوسط (فاز ۲).

Official definition (TAV122-02/00, تعریف ۵-۲۱ — verified in Phase 1):
  «زون: آن قسمت شبکه فشار متوسط به‌همراه تمام تجهیزات و بارهای آن که
   محدود به یک یا چند کلید می‌شود.»

Algorithm — per-feeder split-node component labelling (deterministic):
  1. a node carrying a *boundary device* is declared a «cut node»;
  2. for EVERY feeder trace, the feeder's own traced edges are
     decomposed into connected components where traversal through cut
     nodes is forbidden — each component becomes one zone OF THAT
     FEEDER, numbered Zone0 (the component holding the source) upward
     by breadth-first walk across switch boundaries — the جدول ۱۵
     convention (Zone0..n per feeder);
  3. edges claimed by two feeders' traces (the A-09 flood-through: GIS
     has no NO/NC field) legitimately appear in both feeders' zones;
     the *global* edge→zone map prefers the alphabetically-first claim
     and the double-claiming is reported once as an aggregated
     TOPO-ZONE-SHARED-EDGE issue — never silently;
  4. untraced edge components become islands (kind="island") — the
     zone-level counterpart of TOPO-UNTRACED-AREA.

Policies (explicit, auditable):
  TOPO-POL-03 — FCT fuse cutouts are device types covered by TAV122, but
  are not assumed to be load-break sectionalizing boundaries by default;
  the utility may enable them where operating practice and device rating allow.
  This is an explicit engineering policy, not a verbatim TAV122 exclusion.
  TOPO-POL-06 — existing devices attached directly to a distribution-
  transformer terminal are retained in the model/map but do not split feeder
  zones; the GIS does not prove a separate feeder-section boundary there.
  TOPO-POL-04 — the side of each line end at a multi-line switch node is
  not in the data; the node is assigned to its earliest zone in the
  deterministic ordering, and the boundary record lists ALL zones it
  separates → flagged for engineer review.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field as dc_field

from ..domain.entities import CanonicalNetwork, SwitchDev
from ..domain.enums import SwitchFamily, SwitchState
from ..domain.ids import stable_id
from ..validation.issues import (IssueLog, ValidationIssue, SEVERITY_INFO,
                                 SEVERITY_WARNING)
from .graph import NetworkGraph
from .tracing import FeederTrace

DEFAULT_BOUND_FAMILIES = (SwitchFamily.DISCONNECTOR, SwitchFamily.BREAKER,
                          SwitchFamily.RECLOSER, SwitchFamily.SECTIONALIZER)


@dataclass
class ZonePolicy:
    bound_families: tuple = DEFAULT_BOUND_FAMILIES
    include_fuse_cutout: bool = False          # TOPO-POL-03
    no_as_boundary: bool = True                # confirmed NO separates zones
    out_of_service_as_boundary: bool = True
    exclude_transformer_terminal_devices: bool = True  # TOPO-POL-06


@dataclass
class SwitchZone:
    id: str
    feeder: str                                # feeder key ("" for islands)
    zone_no: int                               # 0 = head zone (جدول ۱۵)
    kind: str                                  # head | section | island
    source_node: str | None
    nodes: set = dc_field(default_factory=set)
    edges: set = dc_field(default_factory=set)
    branches: set = dc_field(default_factory=set)
    length_m: float = 0.0
    transformer_ids: set = dc_field(default_factory=set)
    load_ids: set = dc_field(default_factory=set)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "feeder": self.feeder, "zone_no": self.zone_no,
            "kind": self.kind, "source_node": self.source_node,
            "nodes": len(self.nodes), "edges": len(self.edges),
            "branches": len(self.branches),
            "length_m": round(self.length_m, 1),
            "transformers": len(self.transformer_ids),
            "loads": len(self.load_ids),
        }


@dataclass
class BoundaryRecord:
    switch_id: str
    node: str
    zones: set = dc_field(default_factory=set)     # zone ids it separates
    open_normal: bool = False                      # NO or out-of-service
    branchy: bool = False                          # TOPO-POL-04 flag


@dataclass
class ZoneResult:
    zones: list = dc_field(default_factory=list)             # [SwitchZone]
    zone_of_edge: dict = dc_field(default_factory=dict)      # edge_id → zone id
    zone_of_node: dict = dc_field(default_factory=dict)      # node_id → zone id
    boundaries: list = dc_field(default_factory=list)        # [BoundaryRecord]
    boundary_of_switch: dict = dc_field(default_factory=dict)

    def zones_of_feeder(self, feeder: str) -> list[SwitchZone]:
        from .tracing import same_feeder

        return sorted((z for z in self.zones if same_feeder(z.feeder, feeder)),
                      key=lambda z: z.zone_no)

    def zone_by_id(self, zone_id: str) -> SwitchZone | None:
        for z in self.zones:
            if z.id == zone_id:
                return z
        return None

    def as_dict(self) -> dict:
        by_feeder: dict[str, int] = defaultdict(int)
        for z in self.zones:
            by_feeder[z.feeder or "(island)"] += 1
        return {
            "zone_count": len(self.zones),
            "zones_per_feeder": dict(sorted(by_feeder.items())),
            "boundary_switches": len(self.boundaries),
            "open_boundaries": sum(1 for b in self.boundaries if b.open_normal),
            "branchy_boundaries": sum(1 for b in self.boundaries if b.branchy),
        }


class ZoneBuilder:
    """Per-feeder split-node labelling (deterministic, issue-annotated)."""

    def __init__(self, graph: NetworkGraph, net: CanonicalNetwork,
                 traces: list[FeederTrace],
                 policy: ZonePolicy | None = None):
        self.graph = graph
        self.net = net
        self.traces = sorted(traces, key=lambda t: t.feeder_key)
        self.policy = policy or ZonePolicy()
        self.switches: dict[str, SwitchDev] = {s.id: s for s in net.switches}

    # -- boundary device test -------------------------------------------
    def is_boundary_device(self, sw: SwitchDev) -> bool:
        if sw.family in self.policy.bound_families:
            return True
        if (self.policy.include_fuse_cutout
                and sw.family == SwitchFamily.FUSE_CUTOUT):
            return True
        if (self.policy.no_as_boundary
                and (sw.normally_state or "").strip().upper() == "NO"):
            return True
        if (self.policy.out_of_service_as_boundary
                and sw.current_state == SwitchState.OUT_OF_SERVICE):
            return True
        return False

    def node_is_cut(self, node: str) -> bool:
        # کلید/فیوز روی ترمینال ترانس توزیع، تجهیز حفاظتی/انشعابی آن بار است؛
        # مرز سکسیونینگ فیدر و مرز زون مستقل تلقی نمی‌شود (TOPO-POL-06).
        if (self.policy.exclude_transformer_terminal_devices
                and self.graph.transformer_ids_at.get(node)):
            return False
        for sid in self.graph.switch_ids_at.get(node, ()):
            sw = self.switches.get(sid)
            if sw is not None and self.is_boundary_device(sw):
                return True
        return False

    # ------------------------------------------------------------------
    # components of a sub-graph of edges (cut nodes separate)
    # ------------------------------------------------------------------
    def _components(self, edges: set[str]) -> list[list[str]]:
        comp_of_edge: dict[str, int] = {}
        comps: list[list[str]] = []
        for seed in sorted(edges):
            if seed in comp_of_edge:
                continue
            comp: list[str] = []
            comp_of_edge[seed] = len(comps)
            queue = deque([seed])
            while queue:
                eid = queue.popleft()
                comp.append(eid)
                e = self.graph.edges[eid]
                for n in (e.a, e.b):
                    if self.node_is_cut(n):
                        continue
                    for nbr, eid2 in self.graph.neighbors(n):
                        if eid2 in edges and eid2 not in comp_of_edge:
                            comp_of_edge[eid2] = len(comps)
                            queue.append(eid2)
            comps.append(comp)
        return comps

    @staticmethod
    def _materialize(graph: NetworkGraph, comp_edges: list[str],
                     feeder: str, zone_no: int, kind: str,
                     source_node: str | None) -> SwitchZone:
        zid = stable_id("zone", feeder, zone_no)
        znodes: set = set()
        branches: set = set()
        length = 0.0
        trafos: set = set()
        loads: set = set()
        for eid in comp_edges:
            e = graph.edges[eid]
            znodes.update((e.a, e.b))
            branches.add(e.branch_id)
            length += e.length_m
            trafos.update(graph.transformer_ids_at.get(e.a, ()))
            trafos.update(graph.transformer_ids_at.get(e.b, ()))
            loads.update(graph.load_ids_at.get(e.a, ()))
            loads.update(graph.load_ids_at.get(e.b, ()))
        return SwitchZone(id=zid, feeder=feeder, zone_no=zone_no, kind=kind,
                          source_node=source_node, nodes=znodes,
                          edges=set(comp_edges), branches=branches,
                          length_m=length, transformer_ids=trafos,
                          load_ids=loads)

    # ------------------------------------------------------------------
    # main
    # ------------------------------------------------------------------
    def build(self, issues: IssueLog) -> ZoneResult:
        res = ZoneResult()

        cut_nodes = {n for n in self.graph.switch_ids_at if self.node_is_cut(n)}

        zones: list[SwitchZone] = []
        claimed_by: dict[str, list[str]] = defaultdict(list)   # edge → feeders
        for tr in self.traces:
            comps = self._components(set(tr.edges))
            comp_of_edge_tr: dict[str, int] = {}
            for i, comp in enumerate(comps):
                for eid in comp:
                    comp_of_edge_tr[eid] = i

            # head component: the one hosting an edge incident to the source
            head_idx: int | None = None
            for nbr, eid in self.graph.neighbors(tr.source_node):
                if eid in comp_of_edge_tr:
                    head_idx = comp_of_edge_tr[eid]
                    break
            if head_idx is None and comps:
                issues.add(ValidationIssue(
                    code="TOPO-FEEDER-NO-HEAD", severity=SEVERITY_INFO,
                    message_fa=f"زون سر فیدر «{tr.feeder_key}» یافت نشد؛ "
                               "شماره‌گذاری از اولین مؤلفه شروع می‌شود.",
                    impact_fa="معمولاً به این معناست که منبع به قطعات ردیابی "
                              "شده متصل نیست.",
                    meta={"feeder": tr.feeder_key}))
                head_idx = 0

            # adjacency between comps of THIS feeder across cut nodes
            comp_adj: dict[int, set] = defaultdict(set)
            for node in cut_nodes:
                incident = sorted({comp_of_edge_tr[eid]
                                   for nbr, eid in self.graph.neighbors(node)
                                   if eid in comp_of_edge_tr})
                for a in range(len(incident)):
                    for b in range(a + 1, len(incident)):
                        comp_adj[incident[a]].add(incident[b])
                        comp_adj[incident[b]].add(incident[a])

            zone_of_comp: dict[int, int] = {}
            if comps:
                # sequential numbering in BFS discovery order (جدول ۱۵:
                # Zone0, Zone1, … per feeder — NOT BFS layer depth, which
                # would give parallel branches the same number)
                zone_of_comp[head_idx] = 0
                counter = 1
                queue = deque([head_idx])
                while queue:
                    ci = queue.popleft()
                    for cj in sorted(comp_adj.get(ci, ())):
                        if cj in zone_of_comp:
                            continue
                        zone_of_comp[cj] = counter
                        counter += 1
                        queue.append(cj)
                next_no = len(zone_of_comp)
                for ci in sorted(range(len(comps))):
                    if ci not in zone_of_comp:
                        zone_of_comp[ci] = next_no
                        next_no += 1
            for ci, comp in enumerate(comps):
                zno = zone_of_comp.get(ci, 0)
                kind = "head" if ci == head_idx else "section"
                z = self._materialize(self.graph, comp, tr.feeder_key, zno,
                                      kind, tr.source_node if kind == "head"
                                      else None)
                zones.append(z)
                for eid in comp:
                    claimed_by[eid].append(tr.feeder_key)

        # islands — components over untraced edges only
        traced_all = set(claimed_by)
        island_comps = self._components(set(self.graph.edges) - traced_all)
        for i, comp in enumerate(island_comps):
            zones.append(self._materialize(self.graph, comp, "", i, "island",
                                           None))

        res.zones = zones

        # -- membership maps (deterministic: zones are in build order) -----
        shared = 0
        for z in zones:
            for eid in z.edges:
                res.zone_of_edge.setdefault(eid, z.id)
            for n in z.nodes:
                res.zone_of_node.setdefault(n, z.id)
        for eid, fs in claimed_by.items():
            if len(fs) > 1:
                shared += 1
        if shared:
            issues.add(ValidationIssue(
                code="TOPO-ZONE-SHARED-EDGE", severity=SEVERITY_WARNING,
                message_fa=f"{shared} یال توسط بیش از یک فیدر زون‌بندی شد "
                           "(نقطه باز بین فیدرها در GIS ثبت نشده است — A-09).",
                suggestion_fa="کاندیدهای NO/Tie را تأیید کنید و توپولوژی را "
                              "مجدداً اجرا کنید تا مرز فیدرها قطعی شود.",
                impact_fa="نقشه سراسری یال را به اولین فیدر (ترتیب الفبایی) "
                          "تخصیص می‌دهد؛ زون هر فیدر بر داده خودش است.",
                meta={"shared_edges": shared}))

        # -- boundary records -----------------------------------------------
        for node in sorted(cut_nodes):
            sids = [s for s in self.graph.switch_ids_at[node]
                    if self.is_boundary_device(self.switches[s])]
            zids = {res.zone_of_edge[eid]
                    for nbr, eid in self.graph.neighbors(node)
                    if eid in res.zone_of_edge}
            for sid in sids:
                sw = self.switches[sid]
                br = BoundaryRecord(
                    switch_id=sid, node=node, zones=set(zids),
                    open_normal=((sw.normally_state or "").strip().upper() == "NO"
                                 or sw.current_state == SwitchState.OUT_OF_SERVICE),
                    branchy=len(zids) > 2 or len(sids) > 1)
                res.boundaries.append(br)
                res.boundary_of_switch[sid] = br
                if br.branchy:
                    issues.add(ValidationIssue(
                        code="TOPO-SWITCH-NODE-BRANCHY", severity=SEVERITY_INFO,
                        message_fa="گره کلید مرزی چند خط/چند کلید دارد؛ "
                                   "تفکیک سمت کلید از داده ممکن نیست "
                                   "(TOPO-POL-04).",
                        record_id=sid,
                        impact_fa="کلید مرز همه زون‌های مجاور ثبت شد؛ "
                                  "بازبینی مهندسی پیشنهاد می‌شود.",
                        meta={"node": node, "zone_count": len(zids)}))
        res.boundaries.sort(key=lambda b: b.switch_id)
        return res
