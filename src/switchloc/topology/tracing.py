# -*- coding: utf-8 -*-
"""Feeder tracing — بازسازی فیدرها در وضعیت عادی شبکه (فاز ۲).

Method (docs/TAV122_TRACEABILITY.md تعریف ۵-۱۵/۵-۱۹ + ARCHITECTURE.md §۵ فاز ۲):
* seeds  : SOURCE nodes attached to the graph (`NetworkGraph.source_of`).
           Fallback when none attach: BREAKER-family switch nodes grouped
           by their GIS feeder label (TOPO-POL-02b).
* rule   : normal-state breadth-first traversal.  Traversal may ENTER any
           node and ENERGIZE it, but may PASS THROUGH a node only when
           every switch sitting on it is «passable» (TOPO-POL-01):
             - normally_state == "NO"          → open in normal state → blocks;
             - current_state == OUT_OF_SERVICE → physically out of service → blocks;
             - current_state == UNKNOWN        → policy flag (default: pass,
               already surfaced as GIS-SWITCH-STATE-UNKNOWN in Phase 1);
             - IN_SERVICE / no switch          → passes.
* gate   : TOPO-POL-05 (default ON) — a branch the GIS labels with a
           DIFFERENT feeder is never traversed.  Rationale: the Khalkhal
           export records no NO/NC switch state at all (A-09), so with
           TOPO-POL-01 alone every feeder's BFS floods through the
           unknown-state tie/section switches into the whole network and
           F2..F7 collapse into one identical 10 440-edge trace (user-
           confirmed wrong: the feeders are separate networks with very
           different sizes).  The GIS feeder label IS the utility's
           normal-state partition of the conductors, so the label gates
           the traversal; unlabeled branches stay traversable and an
           empty gated trace falls back to the ungated pass (explicit
           WARNING, never silent).
* output : one `FeederTrace` per source, plus
             - feeder-key overlap detection  (two sources reach the same
               node → the missing NO point, A-09 rule R1 input);
             - GIS-label mismatch detection  (traced feeder ≠ the branch's
               GIS feeder field beyond the fallback chain — e.g. the
               documented «F5 - KOLOOR» inconsistency);
             - untraced-area accounting      (energized edges reachable
               from no source: islands, orphan spurs, beyond-open areas).
"""
from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field as dc_field

from ..domain.entities import CanonicalNetwork, SwitchDev
from ..domain.enums import SwitchFamily, SwitchState
from ..validation.issues import (IssueLog, ValidationIssue, SEVERITY_ERROR,
                                 SEVERITY_INFO, SEVERITY_WARNING)
from .graph import NetworkGraph

_PERSIAN_FIX = str.maketrans({"ي": "ی", "ك": "ک"})


def feeder_id(name: str) -> str:
    """هویت کامل فیدر — نام نرمال‌شدهٔ کامل (بدون کوتاه‌سازی).

    «F2 - MESHKIN» و «F2 - HADIDMOBTAKERAN» دو فیدر جدا هستند ولی هر دو
    با :func:`feeder_key` به «F2» تبدیل می‌شدند و در فهرست فیدرها یکی
    می‌شدند. این تابع نام کامل را نگه می‌دارد؛ یکی‌دانستن نگارش کوتاه و
    آراسته (مثل «F1» با «F1 - MESHKIN») کار :func:`same_feeder` است.
    """
    s = (name or "").translate(_PERSIAN_FIX).strip().upper()
    s = re.sub(r"\s+", " ", s)
    # «F4- KOSAR» / «F4  -  KOSAR» → «F4 - KOSAR» (یک نگارش نمایشی)
    return re.sub(r"\s*-\s*", " - ", s)


def same_feeder(a: str, b: str) -> bool:
    """آیا دو برچسب به یک فیدر اشاره می‌کنند؟

    * نگارش‌های نرمال‌شدهٔ یکسان → بله؛
    * اگر هر دو فقط «توکن کوتاه» یکسانی دارند (F2 و F2) → بله؛
    * اگر یکی از دو نام **تنها** همان توکن کوتاه باشد («F1» در برابر
      «F1 - MESHKIN») → بله (زنجیرهٔ فالبک GIS در لایه‌های مختلف کوتاه و
      آراسته را مخلوط می‌کند)؛
    * «F2 - MESHKIN» در برابر «F2 - HADIDMOBTAKERAN» → **خیر** (دو فیدر).
    """
    na, nb = feeder_id(a), feeder_id(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ka, kb = feeder_key(a), feeder_key(b)
    if not ka or ka != kb:
        return False
    return na == ka or nb == kb


def resolve_feeder(name: str, candidates) -> str:
    """نگاشت یک نام/کلید بیرونی به شناسهٔ یکی از ``candidates``.

    ترتیب: تطبیق دقیق (پس از نرمال‌سازی) → تطبیق :func:`same_feeder` وقتی
    **یکتا** باشد. اگر چند کاندید تطبیق دهند (مثل «F2» وقتی هم «F2 - MESHKIN»
    و هم «F2 - HADIDMOBTAKERAN» وجود دارد) یا هیچ‌کدام، همان نام نرمال‌شده
    برگردانده می‌شود — بدون حدس و بدون ادغام دو فیدر متفاوت.
    """
    target = feeder_id(name)
    if not target:
        return ""
    cands = [str(c) for c in (candidates or ()) if str(c)]
    for c in cands:
        if feeder_id(c) == target:
            return feeder_id(c)
    matches = [c for c in cands if same_feeder(c, name)]
    if len(matches) == 1:
        return feeder_id(matches[0])
    return target


def match_feeders(name: str, candidates) -> list[str]:
    """همهٔ کاندیدهایی که با یک برچسب یکی‌اند (برای انتخاب‌های ذخیره‌شده).

    مثل :func:`resolve_feeder` ولی **فهرست** برمی‌گرداند: اگر برچسب کوتاه
    («F2») به دو فیدر بخورد، هر دو را می‌دهد (نمایش هر دو بهتر از نمایش
    هیچ است)؛ اگر هیچ تطبیقی نبود، فهرست خالی.

    برای فیلترهای نمایشی (لایهٔ فیدرهای نقشه، رنگ فیدر، دامنهٔ گزارش) که
    مقادیر ذخیره‌شدهٔ نسخه‌های قبل با کلید کوتاه نوشته شده‌اند.
    """
    target = feeder_id(name)
    if not target:
        return []
    cands = [str(c) for c in (candidates or ()) if str(c)]
    exact = [c for c in cands if feeder_id(c) == target]
    if exact:
        return exact
    return [c for c in cands if same_feeder(c, name)]


def feeder_key(name: str) -> str:
    """Canonical short feeder identity: leading token, RTL-normalized.

    «F1 - KHALKHAL», «f1», «F1» → «F1» — the GIS fallback chain mixes
    short and decorated names for the same feeder, so mismatch detection
    must compare identities, not decorations.

    توجه: این «توکن کوتاه» برای مقایسه/نمایش کوتاه است، نه شناسهٔ یکتا؛
    شناسهٔ فیدر :func:`feeder_id` است.
    """
    s = (name or "").translate(_PERSIAN_FIX).strip().upper()
    s = re.sub(r"\s+", " ", s)
    # Feeder identifiers are the leading alphanumeric token.  Treat hyphen,
    # underscore and whitespace as decoration separators: F4- KOSAR,
    # F4-KOSAR and F4 - KOSAR all resolve to F4.
    match = re.match(r"^([A-Z]+\d+|\d+)", s)
    return match.group(1) if match else (re.split(r"[\s_-]+", s, maxsplit=1)[0] if s else "")


@dataclass
class TracingPolicy:
    """Explicit, auditable traversal policies (nothing hidden)."""
    unknown_switch_pass: bool = True     # TOPO-POL-01
    #: treat an OUT_OF_SERVICE switch as an open point (physically absent)
    out_of_service_blocks: bool = True
    #: TOPO-POL-05 — branches labelled with another feeder are not
    #: traversed (the GIS label is the utility's normal-state partition;
    #: without the gate, unknown-state switches flood feeders together)
    hint_gated: bool = True


@dataclass
class FeederTrace:
    feeder: str                          # full normalized name from the source
    #: شناسهٔ یکتای فیدر — نام کامل نرمال‌شده (نه توکن کوتاه «F2»)
    feeder_key: str
    source_node: str
    nodes: set = dc_field(default_factory=set)
    edges: set = dc_field(default_factory=set)
    branches: set = dc_field(default_factory=set)
    length_m: float = 0.0
    transformer_ids: set = dc_field(default_factory=set)
    load_ids: set = dc_field(default_factory=set)
    switch_nodes: set = dc_field(default_factory=set)
    overlaps: dict = dc_field(default_factory=dict)   # node → [other feeder keys]
    gated_blocked: int = 0               # TOPO-POL-05 crossings refused

    def as_dict(self) -> dict:
        return {
            "feeder": self.feeder, "feeder_key": self.feeder_key,
            "source_node": self.source_node,
            "nodes": len(self.nodes), "edges": len(self.edges),
            "branches": len(self.branches),
            "length_m": round(self.length_m, 1),
            "transformers": len(self.transformer_ids),
            "loads": len(self.load_ids),
            "switch_nodes": len(self.switch_nodes),
            "gated_blocked": self.gated_blocked,
            "overlaps": {k: v for k, v in self.overlaps.items()},
        }


class TracingEngine:
    """Normal-state feeder reconstruction (deterministic BFS)."""

    def __init__(self, graph: NetworkGraph, net: CanonicalNetwork,
                 policy: TracingPolicy | None = None):
        self.graph = graph
        self.net = net                       # kept for the POL-05 fallback engine
        self.policy = policy or TracingPolicy()
        self.switches: dict[str, SwitchDev] = {s.id: s for s in net.switches}

    # -- passability (TOPO-POL-01) --------------------------------------
    def switch_passable(self, sw: SwitchDev) -> bool:
        if (sw.normally_state or "").strip().upper() == "NO":
            return False                       # user-confirmed normally-open
        if sw.current_state == SwitchState.OUT_OF_SERVICE:
            return not self.policy.out_of_service_blocks
        if sw.current_state == SwitchState.UNKNOWN:
            return self.policy.unknown_switch_pass
        return True                            # IN_SERVICE

    def node_passable(self, node: str) -> bool:
        for sid in self.graph.switch_ids_at.get(node, ()):
            sw = self.switches.get(sid)
            if sw is not None and not self.switch_passable(sw):
                return False
        return True

    # -- seeds -----------------------------------------------------------
    def seeds(self) -> list[tuple[str, str, str]]:
        """[(feeder_name, feeder_id, junction_node)] — قطعی و بدون تکرار.

        یک گره می‌تواند سرچند فیدر باشد (شینهٔ پست)؛ هر فیدر یک بذر
        می‌گیرد. قبلاً نقشهٔ «گره → یک نام» فیدرهای بعدی را روی قبلی
        بازنویسی می‌کرد و آن فیدرها از فهرست/توپولوژی کامل حذف می‌شدند.
        """
        pairs = []
        sources_at = getattr(self.graph, "sources_at", None) or {}
        if sources_at:
            for node, names in sorted(sources_at.items()):
                for fname in names:
                    pairs.append((fname, node))
        else:                                  # سازگاری با گراف قدیمی
            for node, fname in sorted(self.graph.source_of.items()):
                pairs.append((fname, node))
        out, seen = [], set()
        for fname, node in pairs:
            fid = feeder_id(fname)
            if not fid or (fid, node) in seen:
                continue
            seen.add((fid, node))
            out.append((fname, fid, node))
        return out

    def fallback_seeds(self) -> list[tuple[str, str, str]]:
        """TOPO-POL-02b: no usable SOURCE nodes → seed at breaker nodes."""
        by_feeder: dict[str, list[str]] = defaultdict(list)
        for node, sids in self.graph.switch_ids_at.items():
            for sid in sids:
                sw = self.switches.get(sid)
                if sw is not None and sw.family == SwitchFamily.BREAKER:
                    key = feeder_id(sw.feeder_name) or "?"
                    by_feeder[key].append(node)
        out = []
        for key in sorted(by_feeder):
            node = sorted(by_feeder[key])[0]
            out.append((key, key, node))
        return out

    # -- traversal ---------------------------------------------------------
    def trace_from(self, feeder_name: str, key: str,
                   start: str) -> FeederTrace:
        tr = FeederTrace(feeder=feeder_name, feeder_key=key, source_node=start)
        if start not in self.graph.nodes:
            return tr
        tr.nodes.add(start)
        queue = deque([start]) if self.node_passable(start) else deque()
        while queue:
            node = queue.popleft()
            for nbr, eid in self.graph.neighbors(node):
                if eid in tr.edges:
                    continue
                edge = self.graph.edges[eid]
                if self.policy.hint_gated:            # TOPO-POL-05
                    hint = edge.feeder_hint
                    if hint and not same_feeder(hint, feeder_name):
                        tr.gated_blocked += 1         # label of another feeder
                        continue
                tr.edges.add(eid)
                tr.branches.add(edge.branch_id)
                tr.length_m += edge.length_m
                tr.nodes.add(nbr)
                tr.transformer_ids.update(
                    self.graph.transformer_ids_at.get(nbr, ()))
                tr.load_ids.update(self.graph.load_ids_at.get(nbr, ()))
                if self.graph.switch_ids_at.get(nbr):
                    tr.switch_nodes.add(nbr)
                if self.node_passable(nbr):
                    queue.append(nbr)
        return tr

    # -- full pass ---------------------------------------------------------
    def trace_all(self, issues: IssueLog, quiet: bool = False) -> list[FeederTrace]:
        """Trace every seed; `quiet=True` returns traces without Issues
        (used by the strict-core diagnostic so it cannot pollute QC)."""
        seeds = self.seeds()
        used_fallback = False
        if not seeds:
            seeds = self.fallback_seeds()
            used_fallback = bool(seeds)
        if not seeds:
            issues.add(ValidationIssue(
                code="TOPO-NO-SOURCE", severity=SEVERITY_ERROR,
                message_fa="هیچ گره منبع (SOURCE/بریکر سرخط) قابل استفاده "
                           "برای ردیابی فیدرها یافت نشد.",
                suggestion_fa="لایه ELWFWT یا لایه بریکرها را وارد/نگاشت کنید.",
                impact_fa="بازسازی فیدرها ممکن نشد."))
            return []

        if used_fallback:
            issues.add(ValidationIssue(
                code="TOPO-FALLBACK-SEEDS", severity=SEVERITY_INFO,
                message_fa="گره منبع در دسترس نبود؛ ردیابی از گره‌های بریکر "
                           "شروع شد (TOPO-POL-02b).",
                impact_fa="مرز دقیق پست به‌جای نقطه ELWFWT، بریکر سرخط است."))

        traces: list[FeederTrace] = []
        for fname, key, node in seeds:
            traces.append(self.trace_from(fname, key, node))

        # TOPO-POL-05 safety net: a feeder fully enclosed by other feeders'
        # labels (its gated trace is empty) falls back to the ungated pass
        # — explicitly, never silently.
        fallback_feeders: list[str] = []
        if self.policy.hint_gated:
            from dataclasses import replace as dc_replace
            for i, tr in enumerate(traces):
                if not tr.edges:
                    ungated = TracingEngine(
                        self.graph, self.net,
                        dc_replace(self.policy, hint_gated=False))
                    traces[i] = ungated.trace_from(*seeds[i])
                    fallback_feeders.append(seeds[i][1])

        # overlap detection (A-09 / R1): same node reached by 2+ feeders.
        # Only PASSABLE nodes count — two traces touching opposite sides of
        # an open/NO switch terminal are separated by that switch, not
        # interconnected (the node-level model shares the terminal).
        # گره‌های منبعِ مشترک (شینهٔ پست) نقطهٔ اشتراک طبیعی فیدرهاست، نه
        # اتصال بین‌فیدری؛ در شمارش هم‌پوشانی نمی‌آیند.
        source_junctions = {j for j in (getattr(self.graph, "sources_at", {})
                                        or {})}
        seen_by: dict[str, list[str]] = defaultdict(list)
        for tr in traces:
            for n in tr.nodes:
                if n in source_junctions:
                    continue
                seen_by[n].append(tr.feeder_key)
        for tr in traces:
            for n in sorted(tr.nodes):
                if n in source_junctions:
                    continue
                if not self.node_passable(n):
                    continue                    # separated by a device
                others = [f for f in seen_by[n] if f != tr.feeder_key]
                if others:
                    tr.overlaps[n] = sorted(set(others))

        if quiet:                        # diagnostic pass — no QC noise
            return traces

        # TOPO-POL-05 audit trail (one aggregated INFO, never per-edge)
        if self.policy.hint_gated:
            blocked_total = sum(t.gated_blocked for t in traces)
            issues.add(ValidationIssue(
                code="TOPO-POL-05-GATE", severity=SEVERITY_INFO,
                message_fa="ردیابی با دروازه برچسب فیدر انجام شد "
                           "(TOPO-POL-05): قطعه‌ای که GIS آن را به فیدر "
                           "دیگری منسوب کرده از مسیر ردیابی این فیدر خارج "
                           f"است ({blocked_total} قطعه رد شد).",
                suggestion_fa="اگر خط دو-فیدره واقعی وجود دارد، برچسب GIS "
                              "رکوردها بازبینی/اصلاح شود.",
                impact_fa="بدون این دروازه، کلیدهای با وضعیت نامشخص "
                          "(A-09) کل شبکه را به‌هم غرق می‌کنند و همه "
                          "فیدرها یکسان دیده می‌شوند.",
                meta={"blocked_total": blocked_total,
                      "blocked_by_feeder": {
                          t.feeder_key: t.gated_blocked for t in traces},
                      "fallback_feeders": fallback_feeders}))

        # GIS-label mismatch: branch feeder_hint vs traced feeder identity
        mismatch_count: dict[tuple, int] = defaultdict(int)
        for tr in traces:
            for eid in tr.edges:
                hint = self.graph.edges[eid].feeder_hint
                hk = feeder_id(hint)
                if hk and not same_feeder(hint, tr.feeder):
                    mismatch_count[(tr.feeder_key, hk)] += 1
        for (tk, hk), n in sorted(mismatch_count.items()):
            issues.add(ValidationIssue(
                code="TOPO-FEEDER-MISMATCH", severity=SEVERITY_WARNING,
                message_fa=f"{n} قطعه خط با برچسب فیدر «{hk}» در توپولوژی "
                           f"زیر فیدر «{tk}» قرار گرفت.",
                suggestion_fa="برچسب فیدر رکوردها در GIS اصلاح یا تأیید "
                              "شود که خط دو-فیدره واقعی است.",
                impact_fa="ردیابی بر توپولوژی ملاک است؛ برچسب GIS حفظ شد.",
                meta={"traced_feeder": tk, "gis_label": hk, "edges": n}))

        # untraced energized-ish edges (islands / beyond open points)
        traced_edges = set().union(*(t.edges for t in traces)) if traces else set()
        untraced = [eid for eid in self.graph.edges if eid not in traced_edges]
        if untraced:
            by_hint: dict[str, int] = defaultdict(int)
            for eid in untraced:
                by_hint[feeder_id(self.graph.edges[eid].feeder_hint)
                        or "بدون برچسب"] += 1
            issues.add(ValidationIssue(
                code="TOPO-UNTRACED-AREA", severity=SEVERITY_WARNING,
                message_fa=f"{len(untraced)} یال از هیچ منبعی ردیابی نشد "
                           f"(جزیره/پشت کلید باز/تجهیز یتیم).",
                suggestion_fa="وضعیت کلیدهای مرزی و اتصال این نواحی در GIS "
                              "بازبینی شود.",
                impact_fa="نواحی ردیابی‌نشده زون‌بندی نمی‌شوند و در آمار "
                          "فیدرها لحاظ نمی‌گردند.",
                meta={"edges": len(untraced),
                      "by_feeder_hint": dict(sorted(by_hint.items()))}))
        return traces
