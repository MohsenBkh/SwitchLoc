# -*- coding: utf-8 -*-
"""StudyModel — the read-only data bundle behind every Phase-5 export.

Built from the three in-memory artefacts the pipeline already produces
(`CanonicalNetwork`, the TopologyService result, the PlacementResult) —
no exporter talks to SQLite or the engine directly, so a report can be
regenerated offline from any completed project (or from a live run the
UI just made — same class either way).

Coordinates: the analysis CRS is whatever the Phase-1 import recorded
(`net.crs_definitions[0].epsg`, UTM for the sample).  Field deliverables
are additionally offered in WGS84 (GeoJSON convention) through the lazy
`to_wgs84()` helper — pyproj is already a core dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.entities import CanonicalNetwork
from ..domain.enums import NodeKind
from ..logging_setup import get_logger

_log = get_logger("reporting")


@dataclass
class ProposedSwitch:
    """One actionable «کلید پیشنهادی» row (کاربرگ اجرایی)."""
    feeder: str
    node: str
    kind: str                       # NC | NO | automation_upgrade
    scheme_id: str
    scheme_kind: str                # sequential_nc | one_half_switch | …
    x: float | None = None          # analysis CRS (UTM metres)
    y: float | None = None
    lon: float | None = None        # WGS84 (derived, may stay None)
    lat: float | None = None
    zone_no: int | None = None
    note: str = ""
    order_in_scheme: int = 0

    @property
    def kind_fa(self) -> str:
        return {"NC": "کلید واکنش‌گر جدید (قطع‌کننده)",
                "NO": "کلید نرمال‌باز / اتصال‌دهنده",
                "automation_upgrade": "ارتقای اتوماسیون کلید موجود",
                }.get(self.kind, self.kind)


@dataclass
class StudyModel:
    net: CanonicalNetwork
    topo: object                                    # TopologyService result
    placement: object                               # PlacementResult
    project_name: str = ""
    db_path: str = ""
    placement_run_id: str = ""                      # persisted run (may differ)
    crosscheck: dict = field(default_factory=dict)  # persisted-vs-fresh result
    #: (code, severity, message_fa) triples appended by the report layer
    extra_issues: list = field(default_factory=list)
    #: مطالعهٔ جایابی کلید / EENS ذخیره‌شده در پروژه
    #: (``project_kv['sectionalizer_study']``) — وقتی پر باشد، گزارش نهایی
    #: فقط همان مطالعه را مستند می‌کند (درخواست کاربر v1.15).
    eens_study: dict = field(default_factory=dict)
    #: نوع مطالعهٔ فعال: auto | eens | placement
    study_type: str = "auto"
    #: جایابی دستی مهندس (درخواست کاربر، مورد ۶) — لیست dict خروجی
    #: ManualEvaluation.as_dict(): feeder_key / switch_nodes / before /
    #: after / delta / ce_cn / verdict_fa — وقتی غیرخالی باشد بخش
    #: «جایابی دستی» به گزارش اضافه می‌شود.
    manual_evals: list = field(default_factory=list)

    # ------------------------------------------------------------------
    # study type
    # ------------------------------------------------------------------
    @property
    def has_eens_study(self) -> bool:
        """آیا مطالعهٔ EENS ذخیره‌شده‌ای برای گزارش وجود دارد؟"""
        from .eens_report import is_eens_study
        return is_eens_study(self.eens_study)

    @property
    def active_study(self) -> str:
        """نوع مطالعهٔ گزارش: ``eens`` یا ``placement`` (دقیقاً یکی)."""
        if self.study_type in ("eens", "placement"):
            return self.study_type
        return "eens" if self.has_eens_study else "placement"

    # ------------------------------------------------------------------
    # identity / metadata
    # ------------------------------------------------------------------
    @property
    def name(self) -> str:
        return self.project_name or self.net.project_name or "پروژه"

    @property
    def epsg(self) -> int | None:
        for d in self.net.crs_definitions:
            if d.epsg:
                return int(d.epsg)
        return None

    @property
    def crs_label(self) -> str:
        for d in self.net.crs_definitions:
            if d.epsg:
                return f"EPSG:{int(d.epsg)} — {d.crs_analysis or d.crs_original}"
        return "نامشخص (مختصات خام مطابق داده ورودی)"

    # ------------------------------------------------------------------
    # geometry
    # ------------------------------------------------------------------
    def node_coord(self, node_id: str) -> tuple | None:
        nd = self.topo.graph.nodes.get(node_id)
        return nd.coord if nd is not None else None

    def branch_polylines(self) -> list[dict]:
        """[{branch_id, kind, feeder, conductor, length_m, lines:[[(x,y)…]]}]
        from the canonical branches (full polylines, not straight chords).
        """
        out = []
        for br in self.net.branches:
            lines = []
            for seg in br.segments:
                if seg.a and seg.b:
                    lines.append([(float(seg.a[0]), float(seg.a[1])),
                                  (float(seg.b[0]), float(seg.b[1]))])
            if lines:
                out.append({
                    "branch_id": br.id, "kind": getattr(br.kind, "value", str(br.kind)),
                    "feeder": br.feeder_name or "", "conductor": br.conductor or "",
                    "length_m": float(br.length_registered_m or 0.0),
                    "lines": lines})
        return out

    def feeder_of_edge(self) -> dict:
        """edge_id → feeder key of the traced winner (map renderer rule)."""
        out: dict[str, str] = {}
        for t in self.topo.traces:
            for eid in t.edges:
                out.setdefault(eid, t.feeder_key)
        return out

    def zone_edges(self, zone) -> list:
        g = self.topo.graph
        lines = []
        for eid in zone.edges:
            e = g.edges.get(eid)
            if e is None:
                continue
            a, b = g.nodes.get(e.a), g.nodes.get(e.b)
            if a is not None and b is not None and a.coord and b.coord:
                lines.append([tuple(a.coord), tuple(b.coord)])
        return lines

    # ------------------------------------------------------------------
    # zone register — the same strict n-1 tree used by the engine
    # ------------------------------------------------------------------
    def zone_rows(self) -> list[dict]:
        """Detailed, auditable zone register for reports and workbooks."""
        rows = []
        trees = getattr(self.placement.n1, "trees", {}) or {}
        for feeder, tree in sorted(trees.items()):
            for zone in sorted(tree.zones, key=lambda z: (z.zone_no, z.id)):
                length = max(0.0, float(getattr(zone, "length_m", 0.0) or 0.0))
                rows.append({
                    "feeder_key": feeder, "zone_id": zone.id,
                    "zone_no": zone.zone_no, "kind": zone.kind,
                    "length_m": round(length, 1),
                    "length_label": (f"{length:,.0f} m" if length < 1000.0
                                     else f"{length / 1000.0:,.2f} km"),
                    "nodes": len(zone.nodes), "edges": len(zone.edges),
                    "branches": len(zone.branches),
                    "transformers": len(zone.transformer_ids),
                    "loads": len(zone.load_ids),
                    "load_kw": round(float(tree.load_kw.get(zone.id, 0.0) or 0.0), 2),
                    "source": "placement.n1",
                })
        return rows

    # ------------------------------------------------------------------
    # proposed switches (گام ۸ خروجی عملیاتی)
    # ------------------------------------------------------------------
    def build_proposed(self) -> list[ProposedSwitch]:
        """Flatten the recommendation into coordinate-annotated rows.

        Zone numbers come from the strict n-1 trees (the same trees the
        engine ranked); coordinates from the snapped graph nodes.
        """
        schemes = {s.id: s for s in self.placement.schemes}
        zone_no_of: dict[tuple, int] = {}
        for key, tree in self.placement.n1.trees.items():
            for z in tree.zones:
                for n in z.nodes:
                    cur = zone_no_of.get((key, n))
                    if cur is None or z.zone_no < cur:
                        zone_no_of[(key, n)] = z.zone_no
        out: list[ProposedSwitch] = []
        for row in self.placement.recommendation:
            sid = row.get("scheme_id")
            if not sid or sid not in schemes:
                continue
            sc = schemes[sid]
            for i, sw in enumerate(sc.switches, start=1):
                coord = self.node_coord(sw.node)
                zn = zone_no_of.get((sw.feeder, sw.node))
                if zn is None:
                    zn = zone_no_of.get(
                        ((sc.feeders[0] if sc.feeders else ""), sw.node))
                ps = ProposedSwitch(
                    feeder=", ".join(sc.feeders), node=sw.node, kind=sw.kind,
                    scheme_id=sid, scheme_kind=sc.kind,
                    x=(float(coord[0]) if coord else None),
                    y=(float(coord[1]) if coord else None),
                    zone_no=zn,
                    note=getattr(sw, "note", "") or "",
                    order_in_scheme=i)
                if ps.lon is None and coord:
                    ll = self.to_wgs84(coord[0], coord[1])
                    if ll:
                        ps.lon, ps.lat = ll
                out.append(ps)
        return out

    # ------------------------------------------------------------------
    # CRS conversion (lazy, never raises)
    # ------------------------------------------------------------------
    def to_wgs84(self, x: float, y: float) -> tuple | None:
        """Analysis-CRS metres → (lon, lat) WGS84; None when unknown."""
        epsg = self.epsg
        if not epsg or epsg == 4326:
            return None
        try:
            from pyproj import Transformer
            tr = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326",
                                      always_xy=True)
            lon, lat = tr.transform(x, y)
            return (float(lon), float(lat))
        except Exception as exc:                   # noqa: BLE001
            _log.warning("WGS84 transform failed (EPSG:%s): %s", epsg, exc)
            return None

    # ------------------------------------------------------------------
    # KPI summary (خلاصه مدیریتی)
    # ------------------------------------------------------------------
    def kpis(self) -> dict:
        rec = self.placement.recommendation
        sel = [r for r in rec if r.get("scheme_id")]
        comp = self.placement.economics.comparisons
        best = None
        for c in comp:
            if c.selected and c.ce_over_cn not in (None, float("-inf")):
                if best is None or c.ce_over_cn > best.ce_over_cn:
                    best = c
        ens_before = sum(self.placement.economics.ens_before_kwh.values())
        # Σ ENS after over the selected schemes, feeders counted once
        ens_after = 0.0
        covered: set[str] = set()
        for r in sel:
            for f, v in self.placement.economics.ens_after_kwh.get(
                    r["scheme_id"], {}).items():
                if f not in covered:
                    ens_after += v
                    covered.add(f)
        for f in self.placement.economics.ens_before_kwh:
            if f not in covered:
                ens_after += self.placement.economics.ens_before_kwh[f]
        proposed = self.build_proposed()
        return {
            "feeder_count": len(self.topo.traces),
            "zone_count": len(self.topo.zones.zones),
            "switch_existing": len(self.net.switches),
            "switch_proposed": len(proposed),
            "transformer_count": len(self.net.transformers),
            "branch_count": len(self.net.branches),
            "ens_before_kwh": ens_before,
            "ens_after_kwh": ens_after,
            "ens_saved_kwh": max(0.0, ens_before - ens_after),
            "best_ce_over_cn": best.ce_over_cn if best else None,
            "best_scheme": (best.kind if best else None),
            "top_feeder": (self.placement.ranking.rows[0].feeder_key
                           if self.placement.ranking.rows else ""),
            "tie_candidates": len(self.topo.ties),
        }

    # ------------------------------------------------------------------
    def issues_all(self) -> list:
        out = list(self.placement.issues)
        out.extend(self.extra_issues)
        return out

    def verdict(self) -> str:
        return "PASS" if not [i for i in self.issues_all()
                              if i[1] == "Error"] else "FAIL"


def _scheme_feeders(placement, scheme_id: str) -> list[str]:
    for s in placement.schemes:
        if s.id == scheme_id:
            return s.feeders
    return []
