# -*- coding: utf-8 -*-
"""Manual switch placement & evaluation (روش جایابی دستی — درخواست کاربر).

Workflow:
  1. the engineer picks the location: a click on the map OR explicit
     UTM coordinates — `nearest_node()` snaps the point to the nearest
     graph node (a switch sits ON the node — same convention as
     ZoneBuilder / the automatic scheme switches);
  2. `evaluate_manual_placement()` inserts virtual NC switches at the
     chosen node(s) and re-runs the SAME level-1 accounting the
     automatic schemes use (segment tree + رابطه ۸ with tie transfer)
     for the BEFORE and AFTER configurations of that feeder;
  3. the returned indicators — ENS [kWh/yr], EP [%], TL [%],
     segment (zone) count and جدول ۱۸ CE/CN for the new switches —
     make the improvement, or the deterioration, explicit and
     auditable.  Nothing is forced: a bad location is reported as
     worse (ΔENS negative) with the explicit verdict text.

Discipline: Qt-free and deterministic (testable without PySide6);
every number comes from the same engine the automatic placement uses,
so manual and automatic results are directly comparable.
"""
from __future__ import annotations

import math
import copy
from dataclasses import dataclass, field

from .domain.entities import CanonicalNetwork, SwitchDev
from .domain.enums import SwitchFamily, SwitchState
from .level1.n_minus_1 import run_n_minus_one
from .placement.economics import (SegTree, build_seg_tree,
                                   ens_of_configuration, existing_cut_nodes)
from .placement.golden import build_feeder_tree, owned_edges
from .placement.service import EngineSettings, _spare_map
from .reliability.load_model import build_node_loads
from .reliability.lambdar import FeederLambdaR
from .topology.graph import NetworkGraph
from .topology.tracing import FeederTrace
from .topology.zones import ZoneResult, ZoneBuilder, ZonePolicy
from .validation.issues import IssueLog


@dataclass
class ManualEvaluation:
    """Result of one manual evaluation — before/after level-1 indicators."""
    feeder_key: str
    switch_nodes: list = field(default_factory=list)
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    delta: dict = field(default_factory=dict)
    ce_cn: dict = field(default_factory=dict)      # جدول ۱۸ for the switches
    better: bool = False
    verdict_fa: str = ""
    issues: list = field(default_factory=list)
    after_zones: ZoneResult | None = field(default=None, repr=False)

    def as_dict(self) -> dict:
        """JSON-safe snapshot (GUI table / report / copy-paste)."""
        return {"feeder_key": self.feeder_key,
                "switch_nodes": list(self.switch_nodes),
                "before": dict(self.before), "after": dict(self.after),
                "delta": dict(self.delta),
                "ce_cn": {k: v for k, v in self.ce_cn.items()
                          if isinstance(v, (int, float, str))},
                "better": self.better, "verdict_fa": self.verdict_fa,
                "issues": [tuple(i) for i in self.issues],
                "after_zone_count": (len(self.after_zones.zones)
                                     if self.after_zones is not None else None)}


def nearest_node(graph: NetworkGraph, x: float, y: float,
                 restrict_to: set | None = None,
                 max_dist_m: float | None = None,
                 ) -> tuple[str | None, float]:
    """UTM point → (nearest node id, distance [m]).

    ``restrict_to`` limits candidates to the given node set (e.g. one
    feeder's traced nodes).  ``max_dist_m`` refuses far-away clicks
    (None = unlimited).  Returns ``(None, inf)`` when nothing qualifies.
    """
    best, best_d = None, float("inf")
    for nid, nd in graph.nodes.items():
        if nd.coord is None:
            continue
        if restrict_to is not None and nid not in restrict_to:
            continue
        d = math.hypot(nd.coord[0] - x, nd.coord[1] - y)
        if d < best_d:
            best, best_d = nid, d
    if best is None or (max_dist_m is not None and best_d > max_dist_m):
        return None, float("inf")
    return best, best_d


# ---------------------------------------------------------------------------
# EP/TL of a segment configuration (same algebra as compute_ep_tl, but on
# the segment tree so the manual switches' effect is visible immediately)
# ---------------------------------------------------------------------------
def _ep_tl_of_segments(segs: SegTree, total_load_kw: float,
                       transfer_cap_by_seg: dict[str, float],
                       barrier_nodes: set[str] | None = None,
                       ) -> tuple[float, float, str]:
    """(EP %, TL %, worst segment) — worst single fault in the tree.

    A fault in segment i sheds its subtree (minus what the ties
    restore) → shed_i / ΣP = EP contribution of that fault; the worst
    fault over all segments defines EP (جدول ۱۴).  TL is the maximum
    over ALL single faults of the restorable share (the same
    independent maximum the official kernel ``compute_ep_tl`` uses).
    The islands restored by automation ties are the connected
    components of the remaining segment tree (cut nodes link the
    segments they separate) — the same model as جداول ۱۵/۱۴ and the
    ENS accounting in ``placement/economics.py`` (see
    ``level1/transfer.py``).
    """
    if total_load_kw <= 0:
        return 0.0, 0.0, ""
    from .level1.transfer import cut_node_links, islands_with_ties

    def _subtree(s):
        out, stack = [], [s]
        while stack:
            cur = stack.pop()
            out.append(cur)
            stack.extend(segs.children.get(cur, ()))
        return out
    ep = tl = 0.0
    worst = ""
    for sid in sorted(segs.seg_len):
        lam_proxy = segs.seg_len[sid]
        if lam_proxy <= 0:
            continue
        outage = sum(segs.seg_load[s] for s in _subtree(sid))
        members = [s for s in _subtree(sid) if s != sid]
        member_load = {s: segs.seg_load.get(s, 0.0) for s in members}
        tie_caps = {s: transfer_cap_by_seg.get(s, 0.0) for s in members}
        links = cut_node_links(segs.node_seg, segs.node_seg_below,
                               barrier_nodes)
        restored = islands_with_ties(members, member_load, tie_caps, links)
        ep_i = 100.0 * (outage - restored) / total_load_kw
        tl_i = 100.0 * restored / total_load_kw
        if ep_i > ep or (ep_i == ep and tl_i > tl):
            ep, worst = ep_i, sid
        if tl_i > tl:
            tl = tl_i
    return ep, tl, worst


def _zones_for_feeder(zones: ZoneResult, feeder: str) -> ZoneResult:
    selected = [z for z in zones.zones if z.feeder == feeder]
    ids = {z.id for z in selected}
    edges = {e for z in selected for e in z.edges}
    nodes = {n for z in selected for n in z.nodes}
    boundaries = [b for b in zones.boundaries if set(b.zones).intersection(ids)]
    switches = {b.switch_id for b in boundaries}
    return ZoneResult(
        zones=selected,
        zone_of_edge={e: zid for e, zid in zones.zone_of_edge.items()
                      if e in edges and zid in ids},
        zone_of_node={n: zid for n, zid in zones.zone_of_node.items()
                      if n in nodes and zid in ids},
        boundaries=boundaries,
        boundary_of_switch={k: v for k, v in zones.boundary_of_switch.items()
                            if k in switches})


def rebuild_zones_with_manual_switches(graph: NetworkGraph,
                                        net: CanonicalNetwork,
                                        traces: list[FeederTrace],
                                        switch_nodes_by_feeder: dict[str, list[str]],
                                        policy: ZonePolicy | None = None,
                                        ) -> ZoneResult:
    """Rebuild an isolated after-state zone model with virtual NC switches.

    The canonical project and its graph are never mutated. The virtual
    devices are study overlays only; they are not persisted as installed
    assets until the engineer explicitly approves/exports them.
    """
    g = copy.deepcopy(graph)
    n = copy.deepcopy(net)
    for feeder, nodes in sorted(switch_nodes_by_feeder.items()):
        for index, node in enumerate(sorted(set(nodes))):
            sid = f"manual-overlay:{feeder}:{index}:{node}"
            sw = SwitchDev(family=SwitchFamily.DISCONNECTOR, node_id=node,
                           normally_state="NC", current_state=SwitchState.IN_SERVICE,
                           local_name="کلید پیشنهادی دستی (مجازی)",
                           feeder_name=feeder, id=sid)
            n.switches.append(sw)
            g.switch_ids_at[node].append(sid)
    issues = IssueLog()
    rebuilt = ZoneBuilder(g, n, traces, policy or ZonePolicy()).build(issues)
    feeders = set(switch_nodes_by_feeder)
    zones = [z for z in rebuilt.zones if z.feeder in feeders]
    zone_ids = {z.id for z in zones}
    edge_ids = {e for z in zones for e in z.edges}
    node_ids = {n for z in zones for n in z.nodes}
    return ZoneResult(
        zones=zones,
        zone_of_edge={e: zid for e, zid in rebuilt.zone_of_edge.items()
                      if e in edge_ids and zid in zone_ids},
        zone_of_node={n: zid for n, zid in rebuilt.zone_of_node.items()
                      if n in node_ids and zid in zone_ids},
        boundaries=[b for b in rebuilt.boundaries
                    if any(zid in zone_ids for zid in b.zones)],
        boundary_of_switch={k: v for k, v in rebuilt.boundary_of_switch.items()
                            if k in {b.switch_id for b in rebuilt.boundaries
                                     if any(zid in zone_ids for zid in b.zones)}})


# ---------------------------------------------------------------------------
# the evaluator
# ---------------------------------------------------------------------------
def evaluate_manual_placement(graph: NetworkGraph, net: CanonicalNetwork,
                              traces: list[FeederTrace],
                              zones: ZoneResult, ties,
                              feeder_key: str, switch_nodes: list[str],
                              lam_matrix: list[FeederLambdaR] | None = None,
                              settings: EngineSettings | None = None,
                              cap_map: dict | None = None,
                              switch_cost_rials: float | None = None,
                              allow_existing_cut: bool = False,
                              zone_policy: ZonePolicy | None = None,
                              ) -> ManualEvaluation:
    """Before/after level-1 indicators for manual switch node(s).

    ``switch_nodes``: graph node ids (from `nearest_node` or typed UTM
    coordinates snapped by the caller).  Every node must belong to the
    feeder's own traced tree — a foreign node is refused with an
    explicit issue, never silently moved.
    """
    st = settings or EngineSettings()
    nodes = sorted(dict.fromkeys(str(n).strip() for n in switch_nodes
                                 if str(n).strip()))
    ev = ManualEvaluation(feeder_key=feeder_key, switch_nodes=nodes)

    trace = next((t for t in traces if t.feeder_key == feeder_key), None)
    if trace is None:
        ev.issues.append(("MANUAL-FEEDER-UNKNOWN", "Error",
                          f"فیدر «{feeder_key}» در ردیابی فعلی وجود ندارد."))
        ev.verdict_fa = "ارزیابی ممکن نشد — فیدر یافت نشد."
        return ev
    if not nodes:
        ev.issues.append(("MANUAL-NO-NODE", "Error",
                          "هیچ مکانی برای کلید انتخاب نشده است."))
        ev.verdict_fa = "ارزیابی ممکن نشد — مکان کلید انتخاب نشده."
        return ev

    zones_of = [z for z in zones.zones if z.feeder == feeder_key]
    edge_set = owned_edges(zones_of)
    tree = build_feeder_tree(graph, trace, edge_set, {})
    in_tree = set(tree.order)
    foreign = [n for n in nodes if n not in in_tree]
    if foreign:
        ev.issues.append((
            "MANUAL-NODE-NOT-ON-FEEDER", "Error",
            "گره(های) انتخاب‌شده روی گستره ردیابی‌شده فیدر "
            f"{feeder_key} نیستند: {', '.join(foreign)} — کلید باید روی "
            "خط همان فیدر نصب شود."))
        ev.verdict_fa = "ارزیابی ممکن نشد — مکان انتخابی روی فیدر نیست."
        return ev
    # A device already attached to a transformer terminal is not treated
    # as a feeder sectionalizing switch.  Manual proposed locations remain
    # engineer-selectable; when they coincide with such an existing device,
    # register a warning so the physical point is checked on site.
    terminal_with_device = [n for n in nodes
                            if graph.transformer_ids_at.get(n)]
    if terminal_with_device and not set(nodes).issubset(existing_cut_nodes(zones_of)):
        ev.issues.append((
            "MANUAL-TRANSFORMER-TERMINAL-DEVICE", "Error",
            "محاسبه متوقف شد: نقطه انتخابی روی ترمینال مستقیم ترانس/تجهیز "
            f"موجود قرار دارد ({', '.join(terminal_with_device)}). طبق سیاست "
            "TOPO-POL-06 این نقاط مرز سکسیونینگ فیدر نیستند؛ محل کلید جدید "
            "باید روی هادی فیدر و خارج از ترمینال ترانس انتخاب شود."))
        ev.verdict_fa = "ارزیابی انجام نشد — نقطه انتخابی محل مجاز سکسیونینگ نیست."
        return ev

    dup = [n for n in nodes if n in tree.cut_nodes] \
        if hasattr(tree, "cut_nodes") else []
    already_cut = [n for n in nodes if n in existing_cut_nodes(zones_of)]
    if already_cut:
        ev.issues.append((
            "MANUAL-NODE-ALREADY-CUT", "Warning",
            "این گره‌ها هم‌اکنون مرز زون هستند و کلید جدید اثری ندارند: "
            f"{', '.join(already_cut)}"))

    # ---- بارها و λ/r — همان موتور جایابی خودکار --------------------------
    lm = build_node_loads(graph, net, st.load_model)
    node_load = lm.node_kw
    lam_of = {m.feeder_key: m.lambda_per_year for m in (lam_matrix or [])}
    r_of = {m.feeder_key: m.r_minutes for m in (lam_matrix or [])}
    lam = float(lam_of.get(feeder_key, 0.0))
    r_min = float(r_of.get(feeder_key, 0.0))
    if lam <= 0:
        ev.issues.append((
            "MANUAL-LAMBDA-MISSING", "Warning",
            f"نرخ خرابی λ برای فیدر {feeder_key} در دسترس نیست (۰ فرض شد) "
            "— ΔENS معنادار نیست؛ ابتدا داده خاموشی را وارد کنید (نیاز ۸)."))

    # n-1 only for the spare-capacity map of the BACKUP feeders (A-10)
    zones_by_feeder: dict[str, list] = {}
    for t in traces:
        zones_by_feeder[t.feeder_key] = [
            z for z in zones.zones if z.feeder == t.feeder_key]
    n1 = run_n_minus_one(graph, net, traces, zones_by_feeder, ties,
                         settings=st.n1)
    spare = _spare_map(n1, st.placement.feeder_rated_kw, cap_map or {})

    def transfers_for(segs: SegTree) -> dict[str, float]:
        out: dict[str, float] = {}
        for tie in ties:
            if not tie.automation_capable or \
                    feeder_key not in (tie.feeder_a, tie.feeder_b):
                continue
            other = tie.feeder_b if tie.feeder_a == feeder_key \
                else tie.feeder_a
            seg = segs.node_seg_below.get(tie.node) \
                or segs.node_seg.get(tie.node)
            if seg is None:
                continue
            # Unknown reserve is NOT unlimited reserve. Missing capacity
            # data disables restoration rather than silently granting it.
            cap = spare.get(other, 0.0)
            if other not in spare:
                ev.issues.append(("MANUAL-TIE-RESERVE-MISSING", "Warning",
                                  f"ظرفیت رزرو فیدر پشتیبان {other} مشخص نیست؛ انتقال بار از این اتصال منظور نشد."))
            prev = out.get(seg, 0.0)
            out[seg] = float("inf") if (prev == float("inf")
                                        or cap == float("inf")) \
                else prev + cap
        return out

    total_len = tree.sub_len.get(tree.order[0], 0.0)
    total_load = sum(node_load.get(n, 0.0) for n in tree.order)

    # Missing inputs are NOT zero-valued engineering results. Refuse the
    # evaluation before creating before/after numbers, so the GUI cannot
    # present a false zero ENS as a successful calculation.
    if set(nodes).issubset(already_cut) and not allow_existing_cut:
        # No new boundary is introduced. The incremental effect is exactly
        # zero even when absolute ENS inputs are incomplete; do not invent
        # absolute before/after ENS values.
        ev.delta = {"ens_kwh": 0.0, "ens_percent": None,
                    "ep_points": 0.0, "tl_points": 0.0,
                    "segments_added": 0}
        ev.better = False
        ev.after_zones = zones
        ev.verdict_fa = "بدون تغییر: محل انتخابی از قبل مرز زون است و کلید جدید اثری ندارد."
        return ev

    if lam <= 0 or r_min <= 0:
        ev.issues.append(("MANUAL-RELIABILITY-INPUT-MISSING", "Error",
                          "محاسبه متوقف شد: λ و زمان بازیابی r باید از داده خاموشی "
                          "معتبر و دارای پوشش زمانی استخراج/تأیید شوند. مقدار صفر "
                          "به‌عنوان ورودی معتبر پذیرفته نمی‌شود."))
    if total_load <= 0:
        ev.issues.append(("MANUAL-LOAD-MISSING", "Error",
                          "محاسبه متوقف شد: بار اکتیو فیدر از مدل بار قابل استخراج نیست "
                          "یا صفر است. ظرفیت نامی ترانس به‌تنهایی جایگزین بار اکتیو "
                          "معتبر نیست مگر مدل بار صریحاً آن را مجاز کرده باشد."))
    if total_len <= 0:
        ev.issues.append(("MANUAL-LENGTH-MISSING", "Error",
                          "محاسبه متوقف شد: طول معتبر شبکه فیدر در دسترس نیست."))
    if ev.issues and any(i[1] == "Error" for i in ev.issues):
        ev.verdict_fa = "ارزیابی انجام نشد — ورودی مهندسی ناقص است؛ خروجی صفر تولید نشد."
        return ev

    from .level1.transfer import barrier_cut_nodes
    barriers = barrier_cut_nodes(graph, net, ties)

    def measure(cuts: set) -> dict:
        segs = build_seg_tree(graph, trace, tree, cuts, node_load, edge_set)
        tmap = transfers_for(segs)
        ens, _rows = ens_of_configuration(
            segs, lam, r_min, st.cost.switching_minutes, tmap,
            total_length_m=total_len, barrier_nodes=barriers)
        ep, tl, worst = _ep_tl_of_segments(segs, total_load, tmap, barriers)
        return {"ens_kwh": round(ens, 2),
                "ep_percent": round(ep, 2), "tl_percent": round(tl, 2),
                "worst_segment": worst,
                "segments": len(segs.seg_len),
                "total_load_kw": round(total_load, 1),
                "lambda_per_year": lam, "r_minutes": r_min}

    cut0 = existing_cut_nodes(zones_of)
    ev.before = measure(cut0)
    ev.after = measure(cut0 | set(nodes))
    d_ens = round(ev.before["ens_kwh"] - ev.after["ens_kwh"], 2)
    ev.delta = {
        "ens_kwh": d_ens,
        "ens_percent": (round(100.0 * d_ens / ev.before["ens_kwh"], 2)
                        if ev.before["ens_kwh"] > 0 else 0.0),
        "ep_points": round(ev.before["ep_percent"] - ev.after["ep_percent"], 2),
        "tl_points": round(ev.after["tl_percent"] - ev.before["tl_percent"], 2),
        "segments_added": ev.after["segments"] - ev.before["segments"],
    }
    ev.better = d_ens > 0
    ev.after_zones = (_zones_for_feeder(zones, feeder_key)
                      if set(nodes).issubset(already_cut) else
                      rebuild_zones_with_manual_switches(
                          graph, net, traces, {feeder_key: nodes},
                          policy=zone_policy))
    # Guard against a mismatch between the segment accounting and the
    # explicit topology rebuild: the manual NC locations must create cuts.
    if (not set(nodes).issubset(already_cut) and
            len(ev.after_zones.zones_of_feeder(feeder_key)) <= len(zones_of)):
        ev.issues.append(("MANUAL-ZONE-REBUILD-FAILED", "Error",
                          "بازسازی زون‌بندی پس از کلیدگذاری دستی تعداد زون‌ها را کاهش داد؛ "
                          "نتیجه برای پذیرش مهندسی معتبر نیست."))
        ev.verdict_fa = "ارزیابی محاسباتی انجام شد، اما بازسازی زون‌بندی نامعتبر است."
        ev.before = {}; ev.after = {}; ev.delta = {}; ev.ce_cn = {}
        return ev

    cost = float(switch_cost_rials if switch_cost_rials is not None
                 else st.cost.nc_new_rials * len(nodes))
    from .level1.formulas import ce_cn
    ev.ce_cn = ce_cn(e1_kwh=ev.before["ens_kwh"], e2_kwh=ev.after["ens_kwh"],
                     cost_rials=cost, rial_per_kwh=st.cost.rial_per_kwh)
    if d_ens > 0:
        ev.verdict_fa = (f"بهبود: انرژی توزیع‌نشده {d_ens:,.2f} kWh/سال "
                         f"({ev.delta['ens_percent']:.2f}٪) کاهش می‌یابد؛ "
                         "این مکان مفید است.")
    elif d_ens < 0:
        ev.verdict_fa = (f"بدترشدن: انرژی توزیع‌نشده {abs(d_ens):,.2f} "
                         "kWh/سال افزایش می‌یابد — این مکان توصیه نمی‌شود.")
    else:
        ev.verdict_fa = ("بدون تغییر: این کلید شاخص‌های روش سطح اول را "
                         "بهتر نمی‌کند (توجیه نصب از نظر ENS ندارد).")
    return ev


def evaluate_manual_interfeeder_tie(graph: NetworkGraph, net: CanonicalNetwork,
                                    traces: list[FeederTrace], zones: ZoneResult,
                                    ties, feeder_a: str, node_a: str,
                                    feeder_b: str, node_b: str,
                                    lam_matrix=None, settings=None,
                                    cap_map=None, automation_capable=False,
                                    zone_policy: ZonePolicy | None = None):
    """Evaluate a proposed two-point NO tie between two adjacent feeders.

    The tie is represented as a normally-open transfer opportunity at each
    selected feeder endpoint. Restoration is credited only when the user
    explicitly marks the link automation-capable AND usable reserve data for
    both feeders is supplied. This is a Level-1 screening model; it does not
    replace load-flow, protection coordination, voltage-drop or route design.
    Returns (evaluations_by_feeder, issues).
    """
    from types import SimpleNamespace
    issues = []
    if feeder_a == feeder_b:
        return {}, [("MANUAL-TIE-SAME-FEEDER", "Error",
                     "دو سر اتصال باید متعلق به دو فیدر متفاوت باشند.")]
    if not any(t.feeder_key == feeder_a and node_a in t.nodes for t in traces):
        return {}, [("MANUAL-TIE-ENDPOINT-A", "Error",
                     f"نقطه اول {node_a} در فیدر {feeder_a} نیست.")]
    if not any(t.feeder_key == feeder_b and node_b in t.nodes for t in traces):
        return {}, [("MANUAL-TIE-ENDPOINT-B", "Error",
                     f"نقطه دوم {node_b} در فیدر {feeder_b} نیست.")]
    capacities = dict(cap_map or {})
    if automation_capable:
        missing = [fk for fk in (feeder_a, feeder_b)
                   if fk not in capacities or
                   getattr(capacities[fk], "usable_reserve_kw", None) is None]
        if missing:
            return {}, [("MANUAL-TIE-CAPACITY-MISSING", "Error",
                         "برای اتصال اتوماسیون‌پذیر، ظرفیت نامی و پیک معتبر هر دو "
                         "فیدر لازم است؛ داده ناقص: " + ", ".join(missing))]
    # Two endpoint-specific virtual records are needed because the engine's
    # transfer accounting locates the tie on the feeder tree being evaluated.
    virtual_a = SimpleNamespace(feeder_a=feeder_a, feeder_b=feeder_b,
                                node=node_a, switch_id=None,
                                automation_capable=bool(automation_capable),
                                status="candidate", rule="manual-two-point",
                                score=0, id=f"manual-tie:{feeder_a}:{feeder_b}:A")
    virtual_b = SimpleNamespace(feeder_a=feeder_a, feeder_b=feeder_b,
                                node=node_b, switch_id=None,
                                automation_capable=bool(automation_capable),
                                status="candidate", rule="manual-two-point",
                                score=0, id=f"manual-tie:{feeder_a}:{feeder_b}:B")
    all_virtual_ties = [virtual_a, virtual_b]
    all_ties_a = list(ties or []) + all_virtual_ties
    all_ties_b = list(ties or []) + all_virtual_ties
    ev_a = evaluate_manual_placement(
        graph, net, traces, zones, all_ties_a, feeder_a, [node_a],
        lam_matrix=lam_matrix, settings=settings, cap_map=capacities,
        allow_existing_cut=True, zone_policy=zone_policy)
    ev_b = evaluate_manual_placement(
        graph, net, traces, zones, all_ties_b, feeder_b, [node_b],
        lam_matrix=lam_matrix, settings=settings, cap_map=capacities,
        allow_existing_cut=True, zone_policy=zone_policy)
    for ev in (ev_a, ev_b):
        issues.extend(ev.issues)
    if not ev_a.before or not ev_b.before:
        return {}, issues or [("MANUAL-TIE-EVALUATION-FAILED", "Error",
                               "محاسبه دو سر اتصال کامل نشد.")]
    ca = graph.nodes[node_a].coord
    cb = graph.nodes[node_b].coord
    distance = math.dist(ca, cb) if ca is not None and cb is not None else None
    if distance is None:
        issues.append(("MANUAL-TIE-LENGTH-UNKNOWN", "Warning",
                       "مختصات یکی از دو سر اتصال موجود نیست؛ طول رابط قابل برآورد نیست."))
    else:
        issues.append(("MANUAL-TIE-STRAIGHT-LINE-LENGTH", "Information",
                       f"فاصله مستقیم دو نقطه {distance:.1f} متر است؛ طول مسیر اجرایی باید از نقشه مسیر/طراحی برداشت شود."))
    if not automation_capable:
        issues.append(("MANUAL-TIE-NON_AUTOMATED", "Warning",
                       "کلید رابط اتوماسیون‌پذیر اعلام نشده است؛ هیچ بازیابی خودکاری در ENS منظور نشده است."))
    return {feeder_a: ev_a, feeder_b: ev_b}, issues
