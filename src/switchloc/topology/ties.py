# -*- coding: utf-8 -*-
"""NO / Tie detection — ابهام رسمی A-09 (فاز ۲).

TAV122-02/00 knows two states for a sectioning key: NC (بسته در وضعیت
عادی) and NO (باز در وضعیت عادی).  The Khalkhal GIS export carries **no
NO/NC field** — the Phase-0 audit registered this as ambiguity A-09 and
decided: a *proposed rule* + explicit engineer confirmation, never a
silent guess (main prompt §۵-۷: هر فرض باید ثبت و نمایش داده شود).

Proposed rules (documented, deterministic):
  R1 — «هم‌گرایی دو فیدر»: two feeder traces reach the same node in the
       normal state → an open point is missing somewhere at that node.
       With TOPO-POL-01 (unknown switches pass) whole feeders can flood
       into each other, so R1 candidates are RANKED and CAPPED
       (`TieDetectionPolicy.max_candidates`): switch-bearing nodes with
       a clean two-feeder boundary score highest; everything beyond the
       cap stays in the aggregated overlap statistics (one issue, not
       thousands of rows).  Nodes without any switch are never proposed
       as candidates — they are reported as «نیازمند کلید/بازبینی».
  R2 — «ناسازگاری برچسب کلید»: a switch's GIS feeder label names a
       different feeder than the one its node traces to → the switch
       probably sits on the boundary (feeder-inlet or tie).

Confirmation contract (روحیه بند ۵-۳: هیچ تصمیم خودکاری قطعی نیست):
  confirm()  → switch.normally_state = "NO" + tie.status = "confirmed"
               → caller re-traces; service verifies separation.
  reject()   → tie.status = "rejected", switch untouched (kept for audit).

TieConnection entities carry automation_capable from `T_ctrl_otm`
(بند ۱۳-۳ دستورالعمل: فقط اتصالات دارای کلید اتوماسیون در EP/TL شمرده
می‌شوند — جدول ۱۳).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field as dc_field

from ..domain.entities import CanonicalNetwork, TieConnection
from ..domain.enums import YesNoUnknown
from ..validation.issues import (IssueLog, ValidationIssue, SEVERITY_INFO,
                                 SEVERITY_WARNING)
from .graph import NetworkGraph
from .tracing import (FeederTrace, TracingEngine, feeder_id,
                      same_feeder)


@dataclass
class TieDetectionPolicy:
    max_candidates: int = 40            # proposal list cap (ranked, then cut)
    max_aggregate_pairs: int = 20       # pairs detailed in aggregate stats


@dataclass
class TieCandidate:
    """One proposed NO point awaiting the engineer's decision."""
    id: str
    feeder_a: str                        # canonical feeder keys, sorted
    feeder_b: str
    node: str
    switch_id: str | None
    rule: str                            # R1-overlap | R2-label
    automation_capable: bool = False
    status: str = "candidate"            # candidate | confirmed | rejected
    note_fa: str = ""
    score: int = 0                       # ranking (higher = more plausible)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "feeder_a": self.feeder_a, "feeder_b": self.feeder_b,
            "node": self.node, "switch_id": self.switch_id, "rule": self.rule,
            "automation_capable": self.automation_capable,
            "status": self.status, "score": self.score,
            "note_fa": self.note_fa,
        }


class TieDetectionService:
    """Rule proposal + explicit confirmation (A-09)."""

    def __init__(self, graph: NetworkGraph, net: CanonicalNetwork,
                 traces: list[FeederTrace],
                 tracing: TracingEngine | None = None,
                 policy: TieDetectionPolicy | None = None):
        self.graph = graph
        self.net = net
        self.traces = traces
        self.tracing = tracing
        self.policy = policy or TieDetectionPolicy()
        self.switches: dict[str, SwitchDev] = {s.id: s for s in net.switches}
        self.candidates: list[TieCandidate] = []
        self.overlap_stats: dict = {}

    # ------------------------------------------------------------------
    def detect(self, issues: IssueLog) -> list[TieCandidate]:
        out: dict[tuple, TieCandidate] = {}

        def key_pair(a: str, b: str) -> tuple:
            return tuple(sorted((a, b)))

        # edge → claiming feeder keys (for the clean-boundary score)
        edge_feeders: dict[str, set] = defaultdict(set)
        for tr in self.traces:
            for eid in tr.edges:
                edge_feeders[eid].add(tr.feeder_key)

        # -- R1: rank overlap nodes ------------------------------------
        overlap: dict[str, set[str]] = {}          # node → feeder keys
        for tr in self.traces:
            for node, others in tr.overlaps.items():
                overlap.setdefault(node, set()).update(others)
                overlap[node].add(tr.feeder_key)

        pair_nodes: dict[tuple, set] = defaultdict(set)
        for node, feeders in overlap.items():
            fs = sorted(feeders)
            for i in range(len(fs)):
                for j in range(i + 1, len(fs)):
                    pair_nodes[(fs[i], fs[j])].add(node)

        ranked: list[tuple[int, str, str, str]] = []   # (-score, pair, node, sw)
        for (a, b), nodes in pair_nodes.items():
            for node in nodes:
                if self.graph.transformer_ids_at.get(node):
                    continue  # transformer terminal devices are not feeder ties
                sids = sorted(self.graph.switch_ids_at.get(node, ()))
                if not sids:
                    continue                        # no switch → no proposal
                sw = self.switches.get(sids[0])
                incident_feeders: set = set()
                for nbr, eid in self.graph.neighbors(node):
                    incident_feeders |= edge_feeders.get(eid, set())
                clean = incident_feeders <= {a, b}
                auto = (sw is not None
                        and sw.remote_controlled == YesNoUnknown.YES)
                score = (4 if sids else 0) + (3 if clean else 0) + \
                        (1 if auto else 0)
                ranked.append((-score, a, b, node))

        ranked.sort()
        for neg, a, b, node in ranked[: self.policy.max_candidates]:
            score = -neg
            sids = sorted(self.graph.switch_ids_at.get(node, ()))
            sw_id = sids[0]
            auto = (self.switches.get(sw_id) is not None
                    and self.switches[sw_id].remote_controlled == YesNoUnknown.YES)
            out[(a, b, node, sw_id)] = TieCandidate(
                id=f"tie|{a}|{b}|{node}",
                feeder_a=a, feeder_b=b, node=node, switch_id=sw_id,
                rule="R1-overlap", automation_capable=auto, score=score,
                note_fa="دو فیدر در وضعیت عادی به هم می‌رسند؛ کلید موجود "
                        "کاندید NO است (امتیاز قاعده پیشنهادی: "
                        f"{score}).")

        # aggregate statistics for everything beyond the cap
        pair_counts = {p: len(n) for p, n in sorted(pair_nodes.items())}
        switched_pairs = {p: sum(1 for n in nodes
                                 if self.graph.switch_ids_at.get(n))
                          for p, nodes in sorted(pair_nodes.items())}
        self.overlap_stats = {
            "overlap_nodes": len(overlap),
            "pairs": len(pair_counts),
            "top_pairs_by_overlap": [
                {"pair": list(p), "nodes": c, "with_switch": switched_pairs[p]}
                for p, c in sorted(pair_counts.items(),
                                   key=lambda kv: (-kv[1], kv[0]))
                ][: self.policy.max_aggregate_pairs],
        }

        # -- R2: switch label disagrees with traced feeder ---------------
        # (skipped on overlap nodes — there R1 already proposes the point;
        #  under the flood-through condition R2 would be pure noise)
        trace_of_node: dict[str, str] = {}
        for tr in self.traces:
            for n in tr.nodes:
                trace_of_node.setdefault(n, tr.feeder_key)
        for sw in sorted(self.net.switches, key=lambda s: s.id):
            hk = feeder_id(sw.feeder_name)
            tk = trace_of_node.get(sw.node_id, "")
            if not hk or not tk or hk == tk or same_feeder(hk, tk):
                continue                       # یک فیدر با نگارش کوتاه/آراسته
            if sw.node_id in overlap:
                continue                       # R1 territory (A-09)
            pair = key_pair(hk, tk)
            ck = (pair[0], pair[1], sw.node_id, sw.id)
            if ck in out:
                continue
            out[ck] = TieCandidate(
                id=f"tie|{pair[0]}|{pair[1]}|{sw.node_id}|{sw.id}",
                feeder_a=pair[0], feeder_b=pair[1], node=sw.node_id,
                switch_id=sw.id, rule="R2-label",
                automation_capable=sw.remote_controlled == YesNoUnknown.YES,
                note_fa=f"برچسب فیدر کلید («{hk}») با فیدر ردیابی‌شده گره "
                        f"(«{tk}») متفاوت است؛ کاندید مرز فیدر/NO.")

        self.candidates = sorted(out.values(),
                                 key=lambda c: (-c.score, c.rule,
                                                c.feeder_a, c.feeder_b,
                                                c.node, c.switch_id or ""))
        if self.candidates:
            issues.add(ValidationIssue(
                code="TOPO-TIE-CANDIDATES", severity=SEVERITY_INFO,
                message_fa=f"{len(self.candidates)} کاندید اتصال پشتیبان "
                           f"(NO/Tie) با قواعد R1/R2 پیشنهاد شد.",
                suggestion_fa="هر کاندید توسط مهندس تأیید یا رد شود (A-09).",
                impact_fa="تأیید یک کاندید، کلید مربوط را NO می‌کند و "
                          "ردیابی مجدد مرز فیدرها را اصلاح می‌کند.",
                meta={"count": len(self.candidates),
                      "rules": {r: sum(1 for c in self.candidates
                                       if c.rule == r)
                                for r in ("R1-overlap", "R2-label")}}))
        if self.overlap_stats["overlap_nodes"]:
            issues.add(ValidationIssue(
                code="TOPO-FEEDER-INTERCONNECTED", severity=SEVERITY_WARNING,
                message_fa=f"{self.overlap_stats['pairs']} جفت فیدر در "
                           "وضعیت عادی به هم می‌رسند (کلیدهای با وضعیت "
                           "نامشخص عبور داده می‌شوند — TOPO-POL-01).",
                suggestion_fa="نقاط باز (NO) واقعی شبکه توسط مهندس تأیید "
                              "شوند؛ آمار هم‌پوشانی در متادیتا آمده است.",
                impact_fa="تا پیش از تأیید، مرز فیدرها/زون‌ها قطعی نیست و "
                          "زون‌های مشترک ثبت می‌شود.",
                meta=self.overlap_stats))
        return self.candidates

    # ------------------------------------------------------------------
    # confirmation contract — the engineer has the final say
    # ------------------------------------------------------------------
    def confirm(self, cand_id: str, user: str, note: str = "",
                issues: IssueLog | None = None) -> bool:
        cand = self._by_id(cand_id)
        if cand is None:
            return False
        if cand.switch_id:
            sw = self.switches.get(cand.switch_id)
            if sw is not None:
                sw.normally_state = "NO"          # the auditable decision
        cand.status = "confirmed"
        if note:
            cand.note_fa = note
        if issues is not None:
            issues.add(ValidationIssue(
                code="TOPO-TIE-CONFIRMED", severity=SEVERITY_INFO,
                message_fa="کاندید Tie/NO توسط کاربر تأیید شد؛ کلید "
                           "«NO» ثبت و مرز فیدرها با ردیابی مجدد اصلاح می‌شود.",
                record_id=cand.switch_id or "",
                current_value=f"{cand.feeder_a} ↔ {cand.feeder_b}",
                suggestion_fa="", impact_fa="در EP/TL به‌عنوان اتصال "
                             "پشتیبان اتوماسیون شمرده می‌شود "
                             f"(automation_capable={cand.automation_capable}).",
                meta={"tie_id": cand.id, "user": user}))
        return True

    def reject(self, cand_id: str, user: str, note: str = "",
               issues: IssueLog | None = None) -> bool:
        cand = self._by_id(cand_id)
        if cand is None:
            return False
        cand.status = "rejected"
        if note:
            cand.note_fa = note
        if issues is not None:
            issues.add(ValidationIssue(
                code="TOPO-TIE-REJECTED", severity=SEVERITY_INFO,
                message_fa="کاندید Tie توسط کاربر رد شد؛ در محاسبات "
                           "اتصال پشتیبان شمرده نمی‌شود.",
                record_id=cand.switch_id or "",
                current_value=f"{cand.feeder_a} ↔ {cand.feeder_b}",
                meta={"tie_id": cand.id, "user": user}))
        return True

    # ------------------------------------------------------------------
    def to_tie_entities(self) -> list[TieConnection]:
        """TieConnection rows for persistence (status kept verbatim)."""
        out = []
        for c in self.candidates:
            out.append(TieConnection(
                feeder_a=c.feeder_a, feeder_b=c.feeder_b,
                switch_id=c.switch_id,
                automation_capable=c.automation_capable,
                status=c.status))
        return out

    def verified_after_confirmation(self) -> bool:
        """Re-trace with the confirmed NO states → no overlaps left?

        Uses the same overlap rule as `TracingEngine.trace_all`: only
        passable nodes count (opposite sides of the newly-opened switch
        legitimately share its terminal node).
        """
        if self.tracing is None:
            return False
        seen: set[str] = set()
        for t in sorted(self.traces, key=lambda x: x.feeder_key):
            tr = self.tracing.trace_from(t.feeder, t.feeder_key, t.source_node)
            for n in tr.nodes:
                if not self.tracing.node_passable(n):
                    continue                    # separated by the switch
                if n in seen:
                    return False
                seen.add(n)
        return True

    def _by_id(self, cid: str) -> TieCandidate | None:
        for c in self.candidates:
            if c.id == cid:
                return c
        return None
