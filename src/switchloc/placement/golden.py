# -*- coding: utf-8 -*-
"""Golden-rule sectioning (پیوست ب، روابط ۹ و ۱۰) — Phase 4.

رابطه (۱۰) — «قاعده طلایی»: ``U_i × P_i = U_j × P_j`` — the directive's
ideal for the zones of one feeder.  With the level-1 uniform fault-rate
assumption (λ_i ∝ length, رابطه ۹; A-15) and a common r, minimising the
U×P deviation reduces to choosing trunk section points that equalise
``length_i × load_i`` of the resulting segments.

* trunk = longest path of the radial feeder tree (by length);
* segment load  = transformer-capacity index hanging below the segment
  (the documented open-decision-4 proxy);
* segment length includes ALL branches (رابطه ۹: «با احتساب تمام
  شاخه‌ها»);
* exact search over trunk candidates (deterministic subsample,
  ≤ C(40, k−1) combinations — cheap, reproducible, no heuristics).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..topology.graph import NetworkGraph
from ..topology.tracing import FeederTrace


@dataclass
class GoldenSettings:
    target_zones: int = 3              # segments per feeder (k of رابطه ۹)
    #: "all_trunk" = every trunk node is a candidate (subsampled to
    #: max_candidates by deterministic rank); "switch_nodes" = only
    #: nodes that host a switch but are not yet zone boundaries
    #: (upgrade candidates).
    candidate_mode: str = "all_trunk"
    max_candidates: int = 40


@dataclass
class GoldenSectioning:
    feeder_key: str
    trunk: list                        # node ids, source → end
    cut_nodes: list                    # chosen new section points (inside→out)
    segments: list                     # [{length_m, load_kw}]
    deviation: float                   # normalised RMS of U×P (0 = ideal)
    deviation_before: float            # single-segment reference
    total_length_m: float = 0.0
    total_load_kw: float = 0.0
    lambda_per_year: float = 0.0       # feeder λ (for the U×P index)
    r_minutes: float = 0.0


@dataclass
class _Tree:
    parent: dict = field(default_factory=dict)       # node → parent node
    children: dict = field(default_factory=dict)     # node → [child nodes]
    depth_len: dict = field(default_factory=dict)    # node → length from root
    sub_load: dict = field(default_factory=dict)     # node → subtree load kW
    sub_len: dict = field(default_factory=dict)      # node → subtree length m
    order: list = field(default_factory=list)        # BFS order


def build_feeder_tree(graph: NetworkGraph, trace: FeederTrace,
                      edge_set: set, load_kw_at: dict[str, float]) -> _Tree:
    """Radial node tree of one feeder over ``edge_set`` (the feeder's
    OWNED edges — Phase 4 default: the strict-core zones' edges).
    Root = source."""
    t = _Tree()
    root = trace.source_node
    t.parent[root] = None
    t.children[root] = []
    t.depth_len[root] = 0.0
    t.order = []
    queue = [root]
    while queue:
        nxt = []
        for n in queue:
            t.order.append(n)            # BFS order: parents before children
            for nbr, eid in graph.neighbors(n):
                if nbr in t.parent or eid not in edge_set:
                    continue
                t.parent[nbr] = n
                t.children[nbr] = []
                t.children[n].append(nbr)
                t.depth_len[nbr] = t.depth_len[n] + graph.edges[eid].length_m
                nxt.append(nbr)
        queue = nxt
    for n in reversed(t.order):              # post-order accumulation
        t.sub_load[n] = load_kw_at.get(n, 0.0) + sum(
            t.sub_load[c] for c in t.children[n])
        # sub_len = length of the edges strictly BELOW n (its own parent
        # edge belongs to the segment ABOVE it)
        t.sub_len[n] = sum(
            graph.edges[_edge_of(graph, edge_set, c, n)].length_m
            + t.sub_len[c] for c in t.children[n])
    return t


def _edge_of(graph: NetworkGraph, edge_set: set, child: str,
             parent: str | None) -> str:
    """The feeder edge between a child and its tree parent."""
    for nbr, eid in graph.neighbors(parent):
        if nbr == child and eid in edge_set:
            return eid
    raise KeyError(f"no feeder edge {parent}->{child}")


def feeder_trunk(graph: NetworkGraph, trace: FeederTrace,
                 edge_set: set) -> list[str]:
    """Longest root path of the radial feeder tree (by length)."""
    root = trace.source_node
    parent = {root: None}
    dist = {root: 0.0}
    order = [root]
    queue = [root]
    while queue:
        nxt = []
        for n in queue:
            for nbr, eid in graph.neighbors(n):
                if nbr in parent or eid not in edge_set:
                    continue
                parent[nbr] = n
                dist[nbr] = dist[n] + graph.edges[eid].length_m
                nxt.append(nbr)
        queue = nxt
        order.extend(nxt)
    best = max(order, key=lambda n: (dist[n], n))
    path = [best]
    while parent[best] is not None:
        best = parent[best]
        path.append(best)
    path.reverse()
    return path


def owned_edges(zones) -> set:
    """Union of the edges of one feeder's own zones."""
    out: set = set()
    for z in zones:
        out.update(z.edges)
    return out


def _root_of(t: _Tree) -> str:
    return t.order[0]


def segment_stats(t: _Tree, cuts: list[str]) -> list[dict]:
    """Per-segment (length, load) between consecutive trunk cut points.

    Segment i spans from ``starts[i]`` (root for i=0, else cuts[i-1])
    down to (excluding) ``cuts[i]``; its load/length = subtree(start) −
    subtree(end) — off-trunk branches hang below their trunk node and
    are therefore counted exactly once (رابطه ۹ branch inclusion).
    """
    root = _root_of(t)
    starts = [root] + list(cuts)
    stats = []
    for i, start in enumerate(starts):
        end = cuts[i] if i < len(cuts) else None
        length = t.sub_len.get(start, 0.0)
        load = t.sub_load.get(start, 0.0)
        if end is not None:
            length -= t.sub_len.get(end, 0.0)
            load -= t.sub_load.get(end, 0.0)
        stats.append({"length_m": length, "load_kw": load})
    return stats


def up_deviation(segments: list[dict]) -> float:
    """Normalised RMS deviation of U_i×P_i (رابطه ۱۰) for the segments.

    With λ_i ∝ length_i and a common r, U_i×P_i ∝ length_i × load_i,
    so the constant factors cancel inside the relative deviation.
    """
    ups = [s["length_m"] * s["load_kw"] for s in segments]
    mean = sum(ups) / len(ups) if ups else 0.0
    if mean <= 0:
        return 0.0
    rms = (sum((u - mean) ** 2 for u in ups) / len(ups)) ** 0.5
    return rms / mean


def golden_section(graph: NetworkGraph, trace: FeederTrace,
                   edge_set: set, load_kw_at: dict[str, float],
                   lam_per_year: float, r_minutes: float,
                   existing_cut_nodes: set[str],
                   switch_nodes: set[str] | None = None,
                   settings: GoldenSettings | None = None,
                   excluded_nodes: set[str] | None = None,
                   ) -> GoldenSectioning | None:
    """Choose ``target_zones − 1`` trunk section points minimising the
    U×P deviation (exact search).  Returns None for degenerate trunks.
    """
    st = settings or GoldenSettings()
    t = build_feeder_tree(graph, trace, edge_set, load_kw_at)
    trunk = feeder_trunk(graph, trace, edge_set)
    root = _root_of(t)
    if len(trunk) < 3 or t.sub_load.get(root, 0.0) <= 0:
        return None

    excluded = set(excluded_nodes or ())
    cands = [n for n in trunk[1:-1]
             if n not in existing_cut_nodes and n not in excluded]
    if st.candidate_mode == "switch_nodes":
        cands = [n for n in cands
                 if n in (switch_nodes or set()) and n not in existing_cut_nodes]
    # deterministic subsample: rank by subtree load (desc), then node id
    cands.sort(key=lambda n: (-t.sub_load.get(n, 0.0), n))
    cands = cands[: st.max_candidates]
    cands.sort(key=trunk.index)          # restore trunk order for the search
    k = max(2, int(st.target_zones))
    if len(cands) < k - 1:
        return None

    from itertools import combinations
    best = (float("inf"), None)
    for combo in combinations(range(len(cands)), k - 1):
        cuts = [cands[i] for i in combo]
        dev = up_deviation(segment_stats(t, cuts))
        if dev < best[0] - 1e-15:
            best = (dev, cuts)
    if best[1] is None:
        return None
    cuts = best[1]
    segs = segment_stats(t, cuts)
    total_len, total_load = t.sub_len[root], t.sub_load[root]
    # reference: the CURRENT partition (existing cut nodes on the trunk)
    cur_cuts = [n for n in trunk if n in (existing_cut_nodes or set())
                and n not in cuts]
    dev_before = up_deviation(segment_stats(t, cur_cuts)) if cur_cuts else 0.0
    return GoldenSectioning(
        feeder_key=trace.feeder_key, trunk=trunk, cut_nodes=cuts,
        segments=segs, deviation=best[0],
        deviation_before=dev_before,
        total_length_m=total_len, total_load_kw=total_load,
        lambda_per_year=lam_per_year, r_minutes=r_minutes)
