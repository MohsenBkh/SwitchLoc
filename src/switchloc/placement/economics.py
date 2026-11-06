# -*- coding: utf-8 -*-
"""ENS accounting + جدول ۱۸ (CE/CN) scheme comparison — Phase 4.

Energy model (level-1, رابطه ۸ algebra + the transfer extension of
رابطه ۱۱): a fault in segment i hits the segments *downstream* of i
(subtree of the radial segment tree, i included) — upstream segments
are restored by reclosing and never appear in the outage terms, exactly
the ``U1(P1+P2+P3)`` pattern of رابطه ۸.  An automation tie at segment
k back-feeds the subtree behind k within the backup feeder's spare
capacity; restored zones only suffer the switching time ``s`` while
non-transferable ones stay out for the repair time ``r``::

    ENS = Σ_i λ_i/60 × [ r × shed_i + s × restored_i ]   [kWh/yr]

with λ_i = λ_feeder × length_i / Σlength (uniform fault-rate
assumption of رابطه ۹ — A-15).  The SAME accounting runs for the
before (current zone cuts from Phase 2) and after (scheme cuts +
scheme ties) states, so CE = 1000×(E2−E1) of جدول ۱۸ compares like
with like.  Selection direction: **maximize CE/CN** (A-01, locked).

Cost model parameters are company policy (the directive fixes only the
1000 rial/kWh factor) — configurable, logged, never hidden.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from ..level1.formulas import DEFAULT_RIAL_PER_KWH, ce_cn
from ..topology.graph import NetworkGraph
from ..topology.tracing import FeederTrace
from .golden import _Tree
from .schemes import SwitchScheme


# ---------------------------------------------------------------------------
@dataclass
class CostModel:
    #: company-policy parameters (defaults documented in PHASE4_REPORT)
    nc_new_rials: float = 2_000_000_000.0
    no_new_rials: float = 3_000_000_000.0
    automation_upgrade_rials: float = 1_500_000_000.0
    #: جدول ۱۸ factor — official constant, configurable per company
    rial_per_kwh: float = DEFAULT_RIAL_PER_KWH
    #: maneuver/isolation time for transferred zones [minutes]
    switching_minutes: float = 10.0


@dataclass
class SchemeComparison:
    """One row of جدول ۱۸."""
    scheme_id: str
    kind: str
    feeders: list
    n_switches: int
    e2_before_kwh: float          # انرژی توزیع‌نشده *قبل* (حرف رسمی E2)
    e1_after_kwh: float           # انرژی توزیع‌نشده *بعد* (حرف رسمی E1)
    ce_rials: float
    cn_rials: float
    ce_over_cn: float
    selected: bool = False


@dataclass
class EconomicsResult:
    ens_before_kwh: dict = field(default_factory=dict)   # feeder → kWh/yr
    ens_after_kwh: dict = field(default_factory=dict)    # scheme → {feeder: kWh}
    comparisons: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    cost_model: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# segment tree (components between cut nodes) — the ENS backbone
# ---------------------------------------------------------------------------
@dataclass
class SegTree:
    seg_load: dict                     # seg id → kW
    seg_len: dict                      # seg id → m
    parent: dict                       # seg id → seg id | None
    children: dict                     # seg id → [seg ids]
    root: str
    node_seg: dict                     # node → its (upper-side) segment
    node_seg_below: dict               # cut node → the segment it opens


def build_seg_tree(graph: NetworkGraph, trace: FeederTrace,
                   tree: _Tree, cut_nodes: set[str],
                   load_kw_at: dict[str, float],
                   edge_set: set) -> SegTree:
    """Edge components of the feeder tree when traversal is blocked at
    ``cut_nodes`` (same convention as ZoneBuilder: a boundary switch
    node separates two segments).  The edge above a cut belongs to the
    upper segment; the cut node's own load is counted on the lower
    (below) side.  Segment parent relations are produced directly by
    the BFS — no second pass."""
    root = tree.order[0]
    seg_load: dict[str, float] = {}
    seg_len: dict[str, float] = {}
    seg_of_edge: dict[str, str] = {}
    node_seg: dict[str, str] = {}
    node_seg_below: dict[str, str] = {}
    parent: dict[str, str | None] = {}
    children: dict[str, list] = {}
    counter = [0]

    def new_seg() -> str:
        counter[0] += 1
        sid = f"S{counter[0]:04d}"
        seg_load[sid] = 0.0
        seg_len[sid] = 0.0
        parent[sid] = None
        children[sid] = []
        return sid

    root_seg = new_seg()
    queue = deque([(root, root_seg)])
    while queue:
        node, sid = queue.popleft()
        node_seg.setdefault(node, sid)
        seg_load[sid] += load_kw_at.get(node, 0.0)
        for child in tree.children.get(node, ()):
            eid = _edge_between(graph, edge_set, node, child)
            seg_len[sid] += graph.edges[eid].length_m
            seg_of_edge[eid] = sid
            if child in cut_nodes:
                child_seg = new_seg()
                parent[child_seg] = sid
                children[sid].append(child_seg)
                node_seg_below[child] = child_seg
                queue.append((child, child_seg))
            else:
                queue.append((child, sid))

    return SegTree(seg_load=seg_load, seg_len=seg_len, parent=parent,
                   children=children, root=root_seg, node_seg=node_seg,
                   node_seg_below=node_seg_below)


def _edge_between(graph: NetworkGraph, edge_set: set, a: str,
                  b: str) -> str:
    for nbr, eid in graph.neighbors(a):
        if nbr == b and eid in edge_set:
            return eid
    raise KeyError(f"no feeder edge {a}->{b}")


# ---------------------------------------------------------------------------
# ENS of one feeder for a given cut/transfer configuration
# ---------------------------------------------------------------------------
def ens_of_configuration(segs: SegTree, lam_per_year: float,
                         r_minutes: float, switching_minutes: float,
                         transfer_cap_by_seg: dict[str, float],
                         total_length_m: float | None = None,
                         ) -> tuple[float, list[dict]]:
    """ENS [kWh/yr] of the feeder for one (cuts, ties) configuration.

    ``transfer_cap_by_seg``: segment id → kW restorable BEHIND that
    segment through an automation tie (inf when the backup capacity is
    unknown — flagged by the caller).  Returns (ens, per-fault rows).
    """
    Ltot = total_length_m if total_length_m else sum(segs.seg_len.values())
    if Ltot <= 0:
        return 0.0, []
    rows = []
    ens = 0.0
    for sid in sorted(segs.seg_len):
        lam_i = lam_per_year * segs.seg_len[sid] / Ltot
        if lam_i <= 0:
            continue
        outage = _subtree_load(segs, sid)
        restored, restored_set = 0.0, set()
        for k in sorted(_subtree_segs(segs, sid),
                        key=lambda s: -_depth(segs, s)):
            cap = transfer_cap_by_seg.get(k, 0.0)
            if cap <= 0 or k == sid:
                continue                 # faulted segment stays isolated
            behind_zones = [s for s in _subtree_segs(segs, k)
                            if s not in restored_set]
            behind = sum(segs.seg_load[s] for s in behind_zones)
            take = behind if cap == float("inf") else min(behind, cap)
            take = max(0.0, min(take, outage - restored))
            if take <= 0:
                continue
            restored += take
            restored_set.update(behind_zones)
        shed = outage - restored
        e_i = lam_i / 60.0 * (r_minutes * shed + switching_minutes * restored)
        ens += e_i
        rows.append({"seg": sid, "lambda": round(lam_i, 5),
                     "outage_kw": round(outage, 1), "shed_kw": round(shed, 1),
                     "restored_kw": round(restored, 1),
                     "ens_kwh": round(e_i, 2)})
    return ens, rows


def _subtree_segs(segs: SegTree, sid: str) -> list[str]:
    out, queue = [], [sid]
    while queue:
        cur = queue.pop()
        out.append(cur)
        queue.extend(segs.children.get(cur, ()))
    return out


def _subtree_load(segs: SegTree, sid: str) -> float:
    return sum(segs.seg_load[s] for s in _subtree_segs(segs, sid))


def _depth(segs: SegTree, sid: str) -> int:
    d = 0
    while segs.parent.get(sid) is not None:
        sid = segs.parent[sid]
        d += 1
    return d


def existing_cut_nodes(zone_list) -> set[str]:
    """Nodes where two zones of THIS feeder meet (= current zone cuts).

    ``zone_list`` = the feeder's own zones (Phase-4 default: strict-core
    zones, disjoint per feeder).
    """
    by_node: dict[str, set] = {}
    for z in zone_list:
        for n in z.nodes:
            by_node.setdefault(n, set()).add(z.id)
    return {n for n, zs in by_node.items() if len(zs) > 1}


# ---------------------------------------------------------------------------
# scheme costs + جدول ۱۸ comparison
# ---------------------------------------------------------------------------
def scheme_cost(scheme: SwitchScheme, cm: CostModel) -> float:
    unit = {"NC": cm.nc_new_rials, "NO": cm.no_new_rials,
            "automation_upgrade": cm.automation_upgrade_rials}
    return float(sum(unit.get(sw.kind, 0.0) for sw in scheme.switches))


def compare_schemes(schemes: list[SwitchScheme],
                    ens_before: dict[str, float],           # feeder → kWh
                    ens_after_of: dict[str, dict[str, float]],
                    cm: CostModel,
                    ) -> list[SchemeComparison]:
    """جدول ۱۸ rows; ``selected`` = max CE/CN per involved feeder
    («طرح‌هایی که مقدار CE/CN بیشتری دارند به‌عنوان طرح اصلی برای هر
    اولویت انتخاب می‌شوند»)."""
    rows: list[SchemeComparison] = []
    for sc in schemes:
        after = ens_after_of.get(sc.id, {})
        # round FIRST, then apply the official algebra on the rounded
        # values — the جدول ۱۸ row stays internally consistent (audit)
        e_before = round(sum(ens_before.get(f, 0.0) for f in sc.feeders), 2)
        e_after = round(sum(after.get(f, ens_before.get(f, 0.0))
                            for f in sc.feeders), 2)
        cost = scheme_cost(sc, cm)
        cc = ce_cn(e1_kwh=e_before, e2_kwh=e_after, cost_rials=cost,
                   rial_per_kwh=cm.rial_per_kwh)
        ratio = cc["ce_over_cn"]
        rows.append(SchemeComparison(
            scheme_id=sc.id, kind=sc.kind, feeders=list(sc.feeders),
            n_switches=len(sc.switches),
            e2_before_kwh=round(e_before, 2), e1_after_kwh=round(e_after, 2),
            ce_rials=round(cc["ce_rials"], 0), cn_rials=round(cost, 0),
            ce_over_cn=(round(ratio, 6) if ratio != float("-inf")
                        else float("-inf"))))
    # selection: best CE/CN per feeder priority
    best_of: dict[str, tuple[float, str]] = {}
    for r in rows:
        if r.ce_over_cn == float("-inf"):
            continue
        for f in r.feeders:
            cur = best_of.get(f)
            if cur is None or r.ce_over_cn > cur[0]:
                best_of[f] = (r.ce_over_cn, r.scheme_id)
    sel = {v[1] for v in best_of.values()}
    for r in rows:
        r.selected = r.scheme_id in sel
    return rows
