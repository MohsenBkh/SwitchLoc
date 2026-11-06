# -*- coding: utf-8 -*-
"""n-1 engine of گام‌های ۴-۵ (TAV122-02/00، جداول ۱۳/۱۴/۱۵) — Phase 4.

Computes, on the REAL traced network of Phase 2:

  * جدول ۱۳ — feeder connections (tie pairs); per the official note only
    automation-capable connections count for transfer («تنها اتصالات از
    طریق کلید اتوماسیون محاسبه می‌شوند»).
  * جدول ۱۵ — the zone-by-zone n-1 loop: for a fault in every zone the
    sustained-shed and restorable load follow the algebra of رابطه (۸):
    a fault in zone i hits the zones *downstream* of i (subtree of the
    radial zone tree, including zone i itself); upstream zones are
    restored by reclosing and are not counted (same pattern as
    U1(P1+P2+P3) in رابطه ۸).
  * جدول ۱۴ — EP (ماکزیمم درصد بار خاموش‌شده) and TL (ماکزیمم درصد بار
    قابل انتقال) per feeder, via the audited kernel
    `level1.formulas.compute_ep_tl` (anchor V-02: 1800/2500 → 72٪/28٪).

Transfer rule (level-1): a tie restores the subtree behind the zone
where the automation tie attaches — and only within the backup feeder's
spare capacity.  Per A-10 «فقط ظرفیت فیدرها ملاک است» no load flow is
performed.  If the feeder rated capacity is unknown (not in the GIS),
the capacity check is skipped and an explicit Information issue is
registered instead of a silent assumption (بند ۱۹).

Load model (open decision 4 of Phase 3, default policy): real loads are
absent from the sample GIS → P per zone = Σ transformer capacity_kva
(kVA→kW 1:1 index), recorded in ``NMinusOneSettings.load_proxy``.
Nothing is invented: the proxy is visible in every output row.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from ..domain.entities import CanonicalNetwork
from ..level1.formulas import EPTLResult, ZoneFaultRow, compute_ep_tl
from ..topology.graph import NetworkGraph
from ..topology.tracing import FeederTrace
from ..topology.zones import SwitchZone, ZoneResult


# ---------------------------------------------------------------------------
# settings / results
# ---------------------------------------------------------------------------
@dataclass
class NMinusOneSettings:
    #: load proxy per zone (open decision 4 — pending user confirmation)
    load_proxy: str = "transformer_capacity"   # kW ≈ kVA index, 1:1
    #: rated capacity per feeder key (kW); None → capacity check skipped
    feeder_rated_kw: dict | None = None
    #: treat transfer paths without automation as unavailable (official note)
    automation_only_transfer: bool = True


@dataclass
class FeederConnection:
    """One row of جدول ۱۳ (feeder-to-feeder connection via a tie)."""
    feeder_a: str
    feeder_b: str
    switch_id: str | None
    automation_capable: bool
    #: provisional interpretation of the N/M columns (A-13, pending the
    #: official page image): N = tie count of the pair, M = the
    #: automation-capable subset actually usable for transfer.
    n_ties: int = 1
    m_automation: int = 0


@dataclass
class FeederEPTL:
    """جدول ۱۴ row: EP/TL of one feeder + its worst fault zone."""
    feeder_key: str
    ep: EPTLResult
    total_load_kw: float
    zone_count: int


@dataclass
class NMinusOneResult:
    rows15: list[dict]                     # جدول ۱۵ rows (per feeder×zone)
    eptl: list[FeederEPTL]                 # جدول ۱۴
    connections: list[FeederConnection]    # جدول ۱۳
    ties_of_feeder: dict = field(default_factory=dict)   # key → list[dict]
    zone_load_kw: dict = field(default_factory=dict)     # zone id → kW
    trees: dict = field(default_factory=dict)            # key → ZoneTree
    issues: list = field(default_factory=list)           # (code, sev, msg_fa)
    settings: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# zone tree of one radial feeder
# ---------------------------------------------------------------------------
@dataclass
class ZoneTree:
    """Radial zone tree of one feeder (normal state)."""
    feeder_key: str
    zones: list[SwitchZone]
    load_kw: dict                        # zone id → P (kW proxy)
    parent: dict                         # zone id → parent zone id | None
    children: dict                       # zone id → [child zone ids]
    head_zone: str
    total_load_kw: float
    node_zone: dict = field(default_factory=dict)   # node → owned zone id

    def subtree_zones(self, zone_id: str) -> list[str]:
        """Zone + all its descendants (fault-in-this-zone outage set)."""
        out, queue = [], deque([zone_id])
        while queue:
            z = queue.popleft()
            out.append(z)
            queue.extend(self.children.get(z, ()))
        return out

    def subtree_load_kw(self, zone_id: str) -> float:
        return sum(self.load_kw.get(z, 0.0)
                   for z in self.subtree_zones(zone_id))

    def zone_depth(self, zone_id: str) -> int:
        """Depth in the zone tree (head zone = 0)."""
        d, cur = 0, zone_id
        while self.parent.get(cur) is not None:
            cur = self.parent[cur]
            d += 1
        return d


def build_zone_tree(graph: NetworkGraph, trace: FeederTrace,
                    zones_of_feeder: list[SwitchZone],
                    load_kw_of_transformer: dict[str, float],
                    issues: list) -> ZoneTree | None:
    """Zone adjacency tree of one feeder from its OWNED zones.

    Ownership follows the zone partition handed in (Phase 4 default:
    zones rebuilt on the strict core, so they are disjoint per feeder).
    Zones connect where they share a boundary (cut) node; the head zone
    is the one containing the feeder source node.  A cycle in the zone
    graph is registered and resolved by min-zone_no parent choice.
    """
    feeder = trace.feeder_key
    zones = sorted(zones_of_feeder,
                   key=lambda z: (z.kind != "head", z.zone_no, z.id))
    if not zones:
        return None

    # zone adjacency via shared nodes (boundary switches live ON the node)
    zone_at_node: dict[str, set] = {}
    for z in zones:
        for eid in z.edges:
            e = graph.edges[eid]
            zone_at_node.setdefault(e.a, set()).add(z.id)
            zone_at_node.setdefault(e.b, set()).add(z.id)
    adj: dict[str, set] = {z.id: set() for z in zones}
    for nid, zs in zone_at_node.items():
        zs = sorted(zs)
        for i, a in enumerate(zs):
            for b in zs[i + 1:]:
                adj[a].add(b)
                adj[b].add(a)

    head = next((z.id for z in zones if z.kind == "head"), zones[0].id)
    if trace.source_node:
        src = next((z.id for z in zones if trace.source_node in z.nodes), None)
        if src:
            head = src

    parent: dict[str, str | None] = {head: None}
    children: dict[str, list] = {z.id: [] for z in zones}
    queue = deque([head])
    while queue:
        cur = queue.popleft()
        for nbr in sorted(adj.get(cur, ())):
            if nbr not in parent:
                parent[nbr] = cur
                children[cur].append(nbr)
                queue.append(nbr)
    if len(parent) != len(zones):            # cycle / disconnected remnant
        issues.append((
            "PLAC-ZONE-CYCLE", "Information",
            f"فیدر {feeder}: گراف زون‌ها درختی نیست؛ والد با کمترین "
            "zone_no انتخاب شد (وضعیت عادی باید شعاعی باشد)."))
        for z in zones:
            if z.id not in parent:
                cand = sorted(adj[z.id], key=lambda zid: (
                    next((zz.zone_no for zz in zones if zz.id == zid), 99),
                    zid))
                parent[z.id] = cand[0] if cand else None
                if parent[z.id] in children:
                    children[parent[z.id]].append(z.id)

    # A transformer at a shared boundary node must belong to exactly one
    # zone for load aggregation. Pick the lowest zone_no deterministically;
    # otherwise the same connected load can be counted on both sides.
    node_zone: dict[str, str] = {}
    zone_by_id = {z.id: z for z in zones}
    for z in zones:
        for n in z.nodes:
            cur = node_zone.get(n)
            if cur is None or z.zone_no < zone_by_id[cur].zone_no:
                node_zone[n] = z.id
    zone_of_transformer: dict[str, str] = {}
    for node, tids in graph.transformer_ids_at.items():
        owner = node_zone.get(node)
        if owner is not None:
            for tid in tids:
                zone_of_transformer.setdefault(tid, owner)
    load_kw = {z.id: 0.0 for z in zones}
    for tid, owner in zone_of_transformer.items():
        load_kw[owner] += float(load_kw_of_transformer.get(tid, 0.0) or 0.0)
    total = sum(load_kw.values())
    return ZoneTree(feeder_key=feeder, zones=zones, load_kw=load_kw,
                    parent=parent, children=children, head_zone=head,
                    total_load_kw=total, node_zone=node_zone)


# ---------------------------------------------------------------------------
# transfer capability per tie (جدول ۱۳ + spare capacity rule)
# ---------------------------------------------------------------------------
def transfer_capacity_kw(tree: ZoneTree, tie, spare_kw_of_feeder: dict[str, float],
                         settings: NMinusOneSettings) -> float:
    """kW this tie can back-feed into ``tree``'s feeder (0 = unusable).

    Level-1 rule (A-10): only the backup feeder's capacity limits the
    transfer.  Non-automation ties are ignored when
    ``automation_only_transfer`` (the official جدول ۱۳ note).  When the
    backup rated capacity is unknown the result is ``inf`` and the
    caller must surface the data gap (no silent assumption).
    """
    if settings.automation_only_transfer and not tie.automation_capable:
        return 0.0
    other = (tie.feeder_b if tie.feeder_a == tree.feeder_key
             else tie.feeder_a if tie.feeder_b == tree.feeder_key else None)
    if other is None:
        return 0.0
    spare = spare_kw_of_feeder.get(other)
    if spare is None:                        # rated capacity unknown (A-10)
        return 0.0
    return max(0.0, float(spare))


def spare_capacity_map(trees: dict[str, "ZoneTree"],
                       rated_kw: dict[str, float] | None) -> dict[str, float]:
    """feeder key → spare kW = rated − own load; {} when rated unknown."""
    if not rated_kw:
        return {}
    return {key: max(0.0, float(rated_kw[key]) - tree.total_load_kw)
            for key, tree in trees.items() if key in rated_kw}


# ---------------------------------------------------------------------------
# جدول ۱۵ + جدول ۱۴ for one feeder
# ---------------------------------------------------------------------------
def zone_fault_rows(tree: ZoneTree,
                    tie_transfer_kw: dict[str, float]) -> list[ZoneFaultRow]:
    """One جدول ۱۵ row per zone fault of the feeder.

    tie_transfer_kw: zone id → kW restorable *behind* that zone through
    an automation tie (already capacity-checked).  For a fault in zone i
    every descendant zone behind a tie-equipped zone k (k ≠ i, k in
    subtree(i), deepest first) is restored while its spare capacity and
    the still-interrupted load last.  Nested ties never double-count:
    once a subtree is restored, ancestor ties only carry the remainder.
    """
    rows: list[ZoneFaultRow] = []
    for z in tree.zones:
        subtree = tree.subtree_zones(z.id)
        outage_kw = tree.subtree_load_kw(z.id)
        restored = 0.0
        restored_zones: set[str] = set()
        for k in sorted(subtree, key=lambda zz: -tree.zone_depth(zz)):
            cap = tie_transfer_kw.get(k, 0.0)
            if cap <= 0 or k == z.id:
                continue                     # faulted zone stays isolated
            behind_zones = [zz for zz in tree.subtree_zones(k)
                            if zz not in restored_zones]
            behind = sum(tree.load_kw.get(zz, 0.0) for zz in behind_zones)
            take = behind if cap == float("inf") else min(behind, cap)
            take = max(0.0, min(take, outage_kw - restored))
            if take <= 0:
                continue
            restored += take
            restored_zones.update(behind_zones)
        rows.append(ZoneFaultRow(zone=z.id, shed_kw=outage_kw - restored,
                                 restorable_kw=restored))
    return rows


def evaluate_feeder_n1(tree: ZoneTree,
                       tie_transfer_kw: dict[str, float],
                       ) -> tuple[list[ZoneFaultRow], FeederEPTL]:
    """جدول ۱۵ rows + جدول ۱۴ EP/TL of one feeder (anchor V-02 kernel)."""
    rows = zone_fault_rows(tree, tie_transfer_kw)
    ep = compute_ep_tl(rows, tree.total_load_kw)
    return rows, FeederEPTL(feeder_key=tree.feeder_key, ep=ep,
                            total_load_kw=tree.total_load_kw,
                            zone_count=len(tree.zones))


def run_n_minus_one(graph: NetworkGraph, net: CanonicalNetwork,
                    traces: list[FeederTrace],
                    zones_by_feeder: dict[str, list[SwitchZone]],
                    ties: list,
                    settings: NMinusOneSettings | None = None,
                    transformer_load_kw: dict[str, float] | None = None,
                    ) -> NMinusOneResult:
    """Full جداول ۱۳/۱۴/۱۵ pass over all feeders of the traced network."""
    st = settings or NMinusOneSettings()
    issues: list = []
    transf_kw = (dict(transformer_load_kw) if transformer_load_kw is not None
                 else {t.id: (t.capacity_kva or 0.0) for t in net.transformers})
    if transformer_load_kw is not None:
        issues.append(("PLAC-LOAD-MODEL-N1", "Information",
                       "بار N-1 از همان مدل بار گره‌ای مطالعه دریافت شد."))
    elif st.load_proxy != "transformer_capacity":
        issues.append(("PLAC-LOAD-PROXY", "Information",
                       f"شاخص بار ناشناخته: {st.load_proxy} — ظرفیت ترانس "
                       "استفاده شد."))

    trees: dict[str, ZoneTree] = {}
    for tr in sorted(traces, key=lambda t: t.feeder_key):
        tree = build_zone_tree(graph, tr, zones_by_feeder.get(tr.feeder_key, []),
                               transf_kw, issues)
        if tree is not None:
            trees[tr.feeder_key] = tree

    spare = spare_capacity_map(trees, st.feeder_rated_kw)
    if st.feeder_rated_kw is None:
        issues.append((
            "PLAC-CAP-UNKNOWN", "Information",
            "ظرفیت نامی فیدرها در GIS موجود نیست؛ کنترل ظرفیت پشتیبان "
            "رد شد (A-10). برای فعال‌سازی، feeder_rated_kw را تنظیم کنید."))

    # ---- جدول ۱۳ — connections + per-feeder tie bookkeeping -------------
    connections: list[FeederConnection] = []
    ties_of_feeder: dict[str, list] = {k: [] for k in trees}
    pair_count: dict[tuple[str, str], int] = {}
    for tie in sorted(ties, key=lambda t: t.id):
        a, b = tie.feeder_a, tie.feeder_b
        pair_count[(a, b)] = pair_count.get((a, b), 0) + 1
        if tie.automation_capable:
            connections.append(FeederConnection(
                feeder_a=a, feeder_b=b, switch_id=tie.switch_id,
                automation_capable=True,
                n_ties=pair_count[(a, b)], m_automation=1))
        for f in (a, b):
            if f in trees:              # bookkeeping for modelled feeders
                ties_of_feeder.setdefault(f, []).append({
                    "tie_id": tie.id, "switch_id": tie.switch_id,
                    "other_feeder": b if f == a else a,
                    "automation_capable": bool(tie.automation_capable),
                    "rule": tie.rule, "score": tie.score,
                })

    # ---- transfer capability per (feeder, tie zone) ----------------------
    transfer: dict[str, dict[str, float]] = {k: {} for k in trees}
    for tie in sorted(ties, key=lambda t: t.id):
        if not tie.automation_capable:
            continue
        for feeder_key in (tie.feeder_a, tie.feeder_b):
            tree = trees.get(feeder_key)
            if tree is None:
                continue
            zid = tree.node_zone.get(tie.node)
            if zid is None or zid not in tree.load_kw:
                continue
            cap = transfer_capacity_kw(tree, tie, spare, st)
            prev = transfer[feeder_key].get(zid, 0.0)
            transfer[feeder_key][zid] = (
                float("inf") if (prev == float("inf") or cap == float("inf"))
                else prev + cap)

    # ---- جداول ۱۵/۱۴ per feeder ------------------------------------------
    rows15: list[dict] = []
    eptl: list[FeederEPTL] = []
    for key in sorted(trees):
        tree = trees[key]
        if tree.total_load_kw <= 0:
            issues.append((
                "PLAC-FEEDER-NOLOAD", "Warning",
                f"فیدر {key}: شاخص بار صفر است (بدون ترانس دارای ظرفیت)؛ "
                "از EP/TL و رتبه‌بندی کنار گذاشته شد."))
            continue
        rows, fe = evaluate_feeder_n1(tree, transfer.get(key, {}))
        eptl.append(fe)
        zone_no_of = {z.id: z.zone_no for z in tree.zones}
        for r in rows:
            rows15.append({
                "feeder_key": key, "zone": r.zone,
                "zone_no": zone_no_of.get(r.zone, -1),
                "shed_kw": round(r.shed_kw, 1),
                "restorable_kw": round(r.restorable_kw, 1),
                "feeder_load_kw": round(tree.total_load_kw, 1),
            })

    return NMinusOneResult(
        rows15=rows15, eptl=eptl, connections=connections,
        ties_of_feeder=ties_of_feeder,
        zone_load_kw={k: dict(t.load_kw) for k, t in trees.items()},
        trees=trees, issues=issues,
        settings={
            "load_proxy": st.load_proxy,
            "automation_only_transfer": st.automation_only_transfer,
            "feeder_rated_kw": st.feeder_rated_kw or None,
            "capacity_check_active": st.feeder_rated_kw is not None,
        })
