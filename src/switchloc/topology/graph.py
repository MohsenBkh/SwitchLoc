# -*- coding: utf-8 -*-
"""NetworkGraph — CanonicalNetwork → traversable graph (Phase 2).

Why a graph pass is needed at all
---------------------------------
The Phase-1 canonical model stores each GIS polyline as ONE `Branch`
between its two endpoint nodes, with the interior vertices kept only as
`LineSegment` geometry.  A point device (switch/fuse/transformer) that
sits on a *mid-line vertex* therefore lives on a node that is not an
endpoint of any branch — exactly the situation GeoGrid solved with its
«splice» trick (equipment on a mid-vertex connects because the line is
conceptually cut at every vertex; audit §۷, test GG-05).

`NetworkGraph.from_network` performs that cut explicitly and
reproducibly:

  1. every branch is re-walked segment by segment;
  2. each segment endpoint is matched to the nearest existing canonical
     node within `match_tol_m` (grid index, deterministic tie-breaks) —
     the cluster centroid of Phase-1 snap is at most `snap_tol` away
     from any of its member points, so 1.5×snap_tol is safe by default;
  3. each consecutive node pair becomes one `GraphEdge` carrying the
     proportional share of the branch's registered length (already
     distributed by `gis.segmentation` — test GG-03 guarantee Σ = Σ);
  4. point devices are attached to their nodes as blocking/tap entries;
  5. SOURCE-kind nodes (ELWFWT feeder inlets) are attached to the
     nearest junction node within `source_attach_tol_m` (TOPO-POL-02 —
     the Phase-1 assembler creates them as standalone nodes, so the
     attachment happens here, with the distance recorded as an Issue).

Nothing is deleted silently: collapsed points, lost vertices and
isolated devices all surface as Issues.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field as dc_field

from ..domain.entities import CanonicalNetwork
from ..domain.enums import NodeKind
from ..validation.issues import (IssueLog, ValidationIssue, SEVERITY_INFO,
                                 SEVERITY_WARNING)

#: default vertex→node match tolerance (metres) — ≥ snap tolerance so a
#: cluster centroid can never miss its own member point.
DEFAULT_MATCH_TOL_M = 0.75
#: default attachment radius for SOURCE nodes (ELWFWT feeder inlets).
DEFAULT_SOURCE_ATTACH_TOL_M = 2.0


@dataclass
class GraphNode:
    id: str
    kind: NodeKind
    coord: tuple | None            # display coord (snapped preferred)
    feeder_hint: str
    cluster_key: str = ""


@dataclass
class GraphEdge:
    id: str                        # "{branch_id}#{seq}"
    branch_id: str
    seq: int
    a: str
    b: str
    length_m: float                # distributed registered length (GG-03)
    kind: str                      # BranchKind value
    feeder_hint: str
    conductor: str = ""
    section_mm2: float | None = None

    def other(self, node: str) -> str:
        return self.b if node == self.a else self.a


class _GridIndex:
    """Uniform-grid nearest-neighbour index (pure Python, O(1) lookup)."""

    def __init__(self, cell: float):
        self.cell = max(cell, 1e-9)
        self._cells: dict[tuple, list[str]] = defaultdict(list)
        self._pts: dict[str, tuple] = {}

    def add(self, node_id: str, pt: tuple) -> None:
        self._pts[node_id] = pt
        self._cells[(math.floor(pt[0] / self.cell),
                     math.floor(pt[1] / self.cell))].append(node_id)

    def nearest(self, pt: tuple, tol: float,
                kind_rank: dict | None = None) -> tuple | None:
        """(node_id, distance) of the nearest point within `tol`.

        Deterministic tie-break: smaller distance first, then LOWER
        kind rank (JUNCTION beats DEVICE_HV beats SOURCE — line vertices
        must attach to junction nodes when several canonical nodes share
        the same coordinates), then smaller node id.  Returns None when
        nothing lies within `tol`.
        """
        cx, cy = math.floor(pt[0] / self.cell), math.floor(pt[1] / self.cell)
        best = None
        best_key = None
        r = math.ceil(tol / self.cell)
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                for nid in self._cells.get((cx + dx, cy + dy), ()):
                    d = math.dist(pt, self._pts[nid])
                    if d > tol:
                        continue
                    rank = kind_rank.get(nid, 9) if kind_rank else 0
                    key = (round(d, 9), rank, nid)
                    if best is None or key < best_key:
                        best, best_key = (nid, d), key
        return best


@dataclass
class _NodeMeta:
    kind: NodeKind


# (reserved for future per-node caches; keeps dataclass import meaningful)


class NetworkGraph:
    """Adjacency multi-graph with device attachments (Phase 2 engine)."""

    def __init__(self):
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}
        self.adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.edges_of_branch: dict[str, list[str]] = defaultdict(list)
        self.switch_ids_at: dict[str, list[str]] = defaultdict(list)
        self.transformer_ids_at: dict[str, list[str]] = defaultdict(list)
        self.load_ids_at: dict[str, list[str]] = defaultdict(list)
        self.source_of: dict[str, str] = {}      # attached node → feeder name
        self.source_attach: dict[str, tuple] = {}  # src node → (junction, dist_m)
        self.stats: dict = {}

    # ------------------------------------------------------------------
    @classmethod
    def from_network(cls, net: CanonicalNetwork,
                     issues: IssueLog | None = None,
                     match_tol_m: float = DEFAULT_MATCH_TOL_M,
                     source_attach_tol_m: float = DEFAULT_SOURCE_ATTACH_TOL_M,
                     ) -> "NetworkGraph":
        issues = issues if issues is not None else IssueLog()
        g = cls()

        if match_tol_m <= 0 or source_attach_tol_m <= 0:
            raise ValueError("تلورانس‌های تطبیق باید مثبت باشند.")

        # -- 1) nodes ---------------------------------------------------
        for nd in net.nodes:
            coord = nd.coord_snapped or nd.coord_original
            g.nodes[nd.id] = GraphNode(
                id=nd.id, kind=nd.kind, coord=coord,
                feeder_hint=nd.feeder_name, cluster_key=nd.cluster_key)

        # attachment/vertex anchors are JUNCTION nodes only — devices and
        # sources never anchor a line vertex (a SOURCE node must never
        # match itself during attachment; orphans stay isolated by design).
        junction_index = _GridIndex(match_tol_m)
        kind_rank: dict[str, int] = {}
        for nid in sorted(g.nodes):
            kind_rank[nid] = {NodeKind.JUNCTION: 0,
                              NodeKind.DEVICE_HV: 1,
                              NodeKind.SOURCE: 2}.get(g.nodes[nid].kind, 9)
            if g.nodes[nid].coord is not None \
                    and g.nodes[nid].kind == NodeKind.JUNCTION:
                junction_index.add(nid, g.nodes[nid].coord)

        # -- 2) branches → edges ---------------------------------------
        n_edges = 0
        collapsed = 0
        kept = skipped = 0
        for br in sorted(net.branches, key=lambda b: b.id):
            if br.excluded_with_issue:
                skipped += 1
                continue
            if not br.segments:
                # DB-loaded branch without segments — cannot be split;
                # keep as a direct endpoint edge and flag.
                issues.add(ValidationIssue(
                    code="TOPO-SEGMENTS-MISSING", severity=SEVERITY_WARNING,
                    message_fa="شاخه بدون قطعات هندسی است؛ اتصال مستقیم دو سر "
                               "فرض شد (قطعه‌بندی داخلی ممکن نیست).",
                    layer=br.source.layer if br.source else "",
                    record_id=br.source.record_ref if br.source else "",
                    suggestion_fa="پروژه را با فاز ۱ مجدداً وارد کنید تا "
                                  "قطعات در دیتابیس ذخیره شوند.",
                    impact_fa="کلیدهای روی رأس میانی این شاخه در گراف برش "
                              "نمی‌خورند.",
                    meta={"branch_id": br.id}))
                if br.node_a and br.node_b:
                    g._add_edge(br, [(0, br.node_a), (1, br.node_b)])
                    n_edges += 1
                    kept += 1
                continue

            vertices = [seg.a for seg in br.segments] + [br.segments[-1].b]
            node_path: list[tuple[int, str]] = []
            for vi, pt in enumerate(vertices):
                hit = junction_index.nearest(pt, match_tol_m, kind_rank)
                if hit is None:
                    issues.add(ValidationIssue(
                        code="TOPO-VERTEX-NODE-LOST", severity=SEVERITY_WARNING,
                        message_fa="رأس قطعه خط به هیچ گره canonical "
                                   "نزدیک‌تر از تلورانس نبود.",
                        layer=br.source.layer if br.source else "",
                        record_id=br.source.record_ref if br.source else "",
                        current_value=f"({pt[0]:.2f}, {pt[1]:.2f})",
                        suggestion_fa="تلورانس تطبیق گراف یا تلورانس snap فاز ۱ "
                                      "بازبینی شود.",
                        impact_fa="شاخه در این نقطه ناتمام وارد گراف شد.",
                        meta={"branch_id": br.id, "vertex": vi}))
                    continue
                node_path.append((vi, hit[0]))
            # collapse consecutive duplicates (points snapped together)
            dedup: list[tuple[int, str]] = []
            for vi, nid in node_path:
                if dedup and dedup[-1][1] == nid:
                    collapsed += 1
                    continue
                dedup.append((vi, nid))
            if len(dedup) >= 2:
                g._add_edge(br, dedup)
                n_edges += 1
                kept += 1
            else:
                issues.add(ValidationIssue(
                    code="TOPO-BRANCH-DEGENERATE", severity=SEVERITY_INFO,
                    message_fa="شاخه پس از تطبیق گره‌ها تک‌گره شد؛ یال "
                               "تولید نشد.",
                    layer=br.source.layer if br.source else "",
                    record_id=br.source.record_ref if br.source else "",
                    impact_fa="شاخه صرفاً در آمار حفظ می‌شود.",
                    meta={"branch_id": br.id}))

        # -- 3) devices -------------------------------------------------
        for sw in sorted(net.switches, key=lambda s: s.id):
            if sw.node_id in g.nodes:
                g.switch_ids_at[sw.node_id].append(sw.id)
        for tr in sorted(net.transformers, key=lambda t: t.id):
            if tr.node_id in g.nodes:
                g.transformer_ids_at[tr.node_id].append(tr.id)
        for ld in sorted(net.loads, key=lambda l: l.id):
            if ld.node_id in g.nodes:
                g.load_ids_at[ld.node_id].append(ld.id)

        # -- 4) SOURCE attachment (TOPO-POL-02) -------------------------
        for nd in sorted((n for n in net.nodes if n.kind == NodeKind.SOURCE),
                         key=lambda n: n.id):
            coord = nd.coord_snapped or nd.coord_original
            if coord is None:
                issues.add(ValidationIssue(
                    code="TOPO-SOURCE-ISOLATED", severity=SEVERITY_WARNING,
                    message_fa="گره منبع فاقد مختصات است؛ فیدر از این منبع "
                               "ردیابی نمی‌شود.",
                    current_value=nd.feeder_name,
                    impact_fa="ظرفیت ردیابی فیدر کم می‌شود.",
                    meta={"node_id": nd.id}))
                continue
            hit = junction_index.nearest(coord, source_attach_tol_m, kind_rank)
            if hit is None:
                issues.add(ValidationIssue(
                    code="TOPO-SOURCE-ISOLATED", severity=SEVERITY_WARNING,
                    message_fa="گره منبع به هیچ گره خطی نزدیک‌تر از شعاع "
                               f"{source_attach_tol_m:.1f}م متصل نشد.",
                    layer="", record_id="", current_value=nd.feeder_name,
                    suggestion_fa="موقعیت نقطه منبع (ELWFWT) یا شعاع اتصال "
                                  "منبع بازبینی شود.",
                    impact_fa="فیدر از این منبع ردیابی نمی‌شود؛ در گزارش "
                              "منابع ایزوله می‌آید.",
                    meta={"node_id": nd.id}))
                continue
            junction, dist = hit
            g.source_of[junction] = nd.feeder_name
            g.source_attach[nd.id] = (junction, dist)
            if dist > 1e-6:
                issues.add(ValidationIssue(
                    code="TOPO-SOURCE-ATTACHED", severity=SEVERITY_INFO,
                    message_fa=f"گره منبع در فاصله {dist:.2f} متری گره "
                               f"خطی متصل شد (TOPO-POL-02).",
                    current_value=nd.feeder_name,
                    impact_fa="اتصال منبع ثبت‌شده است؛ بازبینی GIS اختیاری.",
                    meta={"source_node": nd.id, "junction": junction,
                          "distance_m": round(dist, 3)}))

        # -- 5) stats ----------------------------------------------------
        orphan_devices = sum(
            1 for nid, n in g.nodes.items()
            if n.kind == NodeKind.DEVICE_HV and not g.adj.get(nid))
        g.stats = {
            "nodes": len(g.nodes),
            "edges": len(g.edges),
            "branches_kept": kept,
            "branches_skipped_excluded": skipped,
            "collapsed_vertex_pairs": collapsed,
            "switches_attached": sum(len(v) for v in g.switch_ids_at.values()),
            "transformers_attached": sum(len(v) for v in g.transformer_ids_at.values()),
            "loads_attached": sum(len(v) for v in g.load_ids_at.values()),
            "sources": len(g.source_of),
            "isolated_device_nodes": orphan_devices,
        }
        return g

    # ------------------------------------------------------------------
    def _add_edge(self, br, dedup_path) -> None:
        for k in range(len(dedup_path) - 1):
            vi_a, na = dedup_path[k]
            vi_b, nb = dedup_path[k + 1]
            seg = br.segments[vi_b - 1] if 0 < vi_b <= len(br.segments) else None
            length = seg.length_m if seg is not None else (
                br.length_geometric_m / max(1, len(br.segments)))
            eid = f"{br.id}#{k}"
            self.edges[eid] = GraphEdge(
                id=eid, branch_id=br.id, seq=k, a=na, b=nb,
                length_m=float(length), kind=br.kind.value,
                feeder_hint=br.feeder_name, conductor=br.conductor,
                section_mm2=br.section_mm2)
            self.adj[na].append((nb, eid))
            self.adj[nb].append((na, eid))
            self.edges_of_branch[br.id].append(eid)

    # ------------------------------------------------------------------
    # convenience API (deterministic ordering everywhere)
    # ------------------------------------------------------------------
    def neighbors(self, node: str) -> list[tuple[str, str]]:
        return sorted(self.adj.get(node, ()))

    def degree(self, node: str) -> int:
        return len(self.adj.get(node, ()))

    def edge(self, edge_id: str) -> GraphEdge:
        return self.edges[edge_id]

    def is_source(self, node: str) -> bool:
        return node in self.source_of

    def has_switch(self, node: str) -> bool:
        return bool(self.switch_ids_at.get(node))
