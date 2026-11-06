# -*- coding: utf-8 -*-
"""Switching-scheme generation of گام ۷ (جدول ۱۷ + پیوست ب) — Phase 4.

Three scheme families of جدول ۱۷ (A-12: the official table is an
image; the text + پیوست ب relations define them):

  (الف) ``sequential_nc`` — کلیدگذاری متوالی NC (پیوست ب-۱): golden-rule
        section points (رابطه ۱۰) along the feeder trunk;
  (ب)   ``one_half_switch`` — طرح ۱٫۵ کلیدی (پیوست ب-۲، روابط ۱۱-۱۳):
        one end-NC per feeder + one NO between two feeders; validity
        rule of رابطه ۱۱: both feeders loaded ≤ 2/3 of the emergency
        capacity (checked when rated capacities are known — A-10);
  (ج)   ``head_tie`` — سایر طرح‌های مانوری: tie candidates in the head
        zones (ارتباط زون‌های ابتدایی).

Switch kinds (costed separately in the cost model):
  NC / NO = a new switch at the node; ``automation_upgrade`` = the node
  already hosts a switch that must gain boundary/automation duty.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.ids import stable_id
from ..domain.entities import CanonicalNetwork
from ..topology.graph import NetworkGraph
from ..topology.tracing import FeederTrace
from .golden import GoldenSectioning, GoldenSettings, \
    feeder_trunk, golden_section, owned_edges


@dataclass
class PlacementSettings:
    #: (الف) sequential NC — feeders processed by ranking order
    max_feeders: int = 3
    golden: GoldenSettings = field(default_factory=GoldenSettings)
    #: (ب) 1.5-switch — top automation-capable tie candidates
    max_tie_schemes: int = 5
    #: rated capacity per feeder (kW) — legacy single-number input (A-10)
    feeder_rated_kw: dict | None = None
    #: نیاز ۹ — مدل ظرفیت کامل (نامی/پیک/اضطراری + منشأ)؛ وقتی داده شود
    #: رابطه ۱۱ با «ظرفیت اضطراری» کنترل می‌شود و نامشخص‌بودنش پرچم
    #: «نیازمند تأیید ظرفیت» می‌زند (نه حدس و نه رد بی‌دلیل)
    feeder_capacity: dict | None = None
    #: n-1 area model: "strict" = the guaranteed core (unknown switches
    #: treated open — disjoint feeders, A-09 pending confirmation);
    #: "traced" = the flooded normal-state trace (whole island overlap).
    area_mode: str = "strict"
    include_fuse_cutout_as_boundary: bool = False   # TOPO-POL-03


@dataclass
class ProposedSwitch:
    node: str
    feeder: str
    kind: str                  # NC | NO | automation_upgrade
    note: str = ""


@dataclass
class SwitchScheme:
    id: str
    kind: str                  # sequential_nc | one_half_switch | head_tie
    feeders: list
    switches: list
    relations: list            # directive anchors used by the scheme
    note: str = ""
    extra: dict = field(default_factory=dict)


def generate_schemes(graph: NetworkGraph, net: CanonicalNetwork,
                     traces: list[FeederTrace], trees: dict,
                     ranking_rows: list, ties: list,
                     zone_no_of: dict, load_kw_at: dict[str, float],
                     lam_of: dict, r_of: dict,
                     cut_nodes_of: dict[str, set],
                     edge_set_of: dict[str, set],
                     settings: PlacementSettings | None = None,
                     ) -> tuple[list[SwitchScheme], dict[str, GoldenSectioning],
                                list]:
    """Generate the جدول ۱۷ families; returns (schemes, golden_by_feeder,
    issues).  Deterministic throughout (stable ids, sorted iteration)."""
    st = settings or PlacementSettings()
    issues: list = []
    trace_of = {t.feeder_key: t for t in traces}
    # تجهیز متصل مستقیم به ترانس توزیع، گزینه ارتقای سکسیونینگ فیدر نیست.
    transformer_terminal_nodes = set(graph.transformer_ids_at)
    transformer_terminal_switch_nodes = {
        sw.node_id for sw in net.switches
        if sw.node_id in transformer_terminal_nodes}
    switch_nodes: set[str] = {s.node_id for s in net.switches
                              if s.node_id not in transformer_terminal_switch_nodes}

    schemes: list[SwitchScheme] = []
    signatures: set = set()
    golden_of: dict[str, GoldenSectioning] = {}

    # ---- (الف) sequential NC along the trunk (پیوست ب-۱ / رابطه ۱۰) -----
    ranked = [r.feeder_key for r in ranking_rows][: max(0, st.max_feeders)]
    for key in ranked:
        trace = trace_of.get(key)
        tree = trees.get(key)
        if trace is None or tree is None:
            continue
        cuts_existing = cut_nodes_of.get(key, set())
        gs = golden_section(graph, trace, edge_set_of.get(key, set()),
                            load_kw_at,
                            lam_of.get(key, 0.0), r_of.get(key, 0.0),
                            cuts_existing, switch_nodes,
                            settings=st.golden,
                            excluded_nodes=transformer_terminal_switch_nodes)
        if gs is None:
            issues.append((
                "PLAC-GOLDEN-SKIP", "Information",
                f"فیدر {key}: نقطه کافی برای قطعه‌بندی طلایی روی تنه "
                "اصلی وجود ندارد؛ طرح (الف) تولید نشد."))
            continue
        golden_of[key] = gs
        switches = []
        for node in gs.cut_nodes:
            kind = "automation_upgrade" if node in switch_nodes else "NC"
            switches.append(ProposedSwitch(
                node=node, feeder=key, kind=kind,
                note="قاعده طلایی U×P (رابطه ۱۰) — قطعه‌بندی متوالی NC"))
        sig = frozenset((s.node, s.kind) for s in switches)
        if switches and sig not in signatures:
            signatures.add(sig)
            schemes.append(SwitchScheme(
                id=stable_id("scheme", "sequential_nc", key,
                             tuple(sorted((s.node, s.kind)
                                          for s in switches))),
                kind="sequential_nc", feeders=[key], switches=switches,
                relations=["جدول ۱۷-الف", "پیوست ب-۱", "رابطه (۹)",
                           "رابطه (۱۰) — قاعده طلایی U×P"],
                note=(f"قطعه‌بندی تنه اصلی فیدر {key} به "
                      f"{len(gs.segments)} زون با انحراف U×P = "
                      f"{gs.deviation:.3f}"),
                extra={"deviation": round(gs.deviation, 5),
                       "deviation_before": round(gs.deviation_before, 5),
                       "trunk_nodes": len(gs.trunk)}))

    # ---- (ب) 1.5-switch scheme (پیوست ب-۲ / روابط ۱۱-۱۳) ----------------
    auto_ties = sorted((t for t in ties if t.automation_capable
                        and t.feeder_a in trace_of
                        and t.feeder_b in trace_of),
                       key=lambda t: (-t.score, t.id))
    rated = st.feeder_rated_kw or {}
    cap_map = st.feeder_capacity or {}

    def emergency_of(fkey: str):
        """ظرفیت اضطراری — مدل کامل ظرفیت (نیاز ۹) یا بازگشت به ورودی
        قدیمی نامی (A-10)؛ None یعنی کنترل رابطه ۱۱ ممکن نیست."""
        cap = cap_map.get(fkey)
        if cap is not None:
            em = getattr(cap, "emergency_kw", None)
            if em is not None:
                return float(em)
            # ظرفیت اضطراری اعلام‌نشده → حدس ممنوع؛ None
            return None
        return rated.get(fkey)          # legacy single-number input

    def emergency_known(fkey: str) -> bool:
        cap = cap_map.get(fkey)
        if cap is not None:
            return cap.emergency_kw is not None
        return fkey in rated

    for tie in auto_ties[: max(0, st.max_tie_schemes)]:
        a, b = tie.feeder_a, tie.feeder_b
        ta, tb = trees.get(a), trees.get(b)
        if ta is None or tb is None:
            continue
        # رابطه ۱۱ validity: both feeders ≤ 2/3 emergency loading
        if emergency_known(a) and emergency_known(b):
            em_a, em_b = emergency_of(a), emergency_of(b)
            ok_a = ta.total_load_kw <= em_a * 2 / 3
            ok_b = tb.total_load_kw <= em_b * 2 / 3
            if not (ok_a and ok_b):
                issues.append((
                    "PLAC-15-CAPACITY", "Warning",
                    f"طرح ۱٫۵ کلیدی بین {a} و {b} رد شد: شرط بارگذاری "
                    "۲/۳ ظرفیت اضطراری رابطه (۱۱) برقرار نیست."))
                continue
        else:
            unk = [f for f in (a, b) if not emergency_known(f)]
            issues.append((
                "PLAC-15-CAP-UNKNOWN", "Information",
                f"طرح ۱٫۵ کلیدی بین {a} و {b}: ظرفیت اضطراری "
                f"{'، '.join(unk)} نامشخص — طرح تولید شد اما در وضعیت "
                "«نیازمند تأیید ظرفیت» می‌ماند (نیاز ۹/۱۰)."))
        switches = [ProposedSwitch(
            node=tie.node, feeder=a, kind="NO",
            note=("کلید NO بین دو فیدر (رابطه ۱۱)"
                  + (f" — کلید موجود: {tie.switch_id}"
                     if tie.switch_id else " — کلید جدید")))]
        for key, tree in ((a, ta), (b, tb)):
            end_node = feeder_trunk(graph, trace_of[key],
                                    edge_set_of.get(key, set()))[-1]
            kind = "automation_upgrade" if end_node in switch_nodes else "NC"
            switches.append(ProposedSwitch(
                node=end_node, feeder=key, kind=kind,
                note="کلید NC انتهایی فیدر (طرح ۱٫۵ کلیدی)"))
        sig = frozenset((s.node, s.kind) for s in switches)
        if sig not in signatures:
            signatures.add(sig)
            schemes.append(SwitchScheme(
                id=stable_id("scheme", "one_half_switch", a, b, tie.node),
                kind="one_half_switch", feeders=[a, b], switches=switches,
                relations=["جدول ۱۷-ب", "پیوست ب-۲", "روابط (۱۱)-(۱۳)"],
                note=f"طرح ۱٫۵ کلیدی بین {a} و {b} در گره {tie.node}",
                extra={"tie_id": tie.id, "tie_rule": tie.rule}))

    # ---- (ج) head-zone ties (سایر طرح‌های مانوری) ------------------------
    for tie in auto_ties[: max(0, st.max_tie_schemes)]:
        zno_a = zone_no_of.get((tie.feeder_a, tie.node))
        zno_b = zone_no_of.get((tie.feeder_b, tie.node))
        near_head = (zno_a is not None and zno_a <= 1) or \
                    (zno_b is not None and zno_b <= 1)
        if not near_head:
            continue
        if tie.feeder_a not in trace_of or tie.feeder_b not in trace_of:
            continue
        switches = [ProposedSwitch(
            node=tie.node, feeder=tie.feeder_a, kind="NO",
            note="ارتباط زون‌های ابتدایی (سایر طرح‌های مانوری جدول ۱۷-ج)")]
        sig = frozenset((s.node, s.kind) for s in switches)
        if sig in signatures:
            continue
        signatures.add(sig)
        schemes.append(SwitchScheme(
            id=stable_id("scheme", "head_tie", tie.feeder_a, tie.feeder_b,
                         tie.node),
            kind="head_tie", feeders=[tie.feeder_a, tie.feeder_b],
            switches=switches,
            relations=["جدول ۱۷-ج"],
            note=(f"اتصال ابتدای فیدرها {tie.feeder_a}/{tie.feeder_b} "
                  f"در گره {tie.node}")))

    return schemes, golden_of, issues
