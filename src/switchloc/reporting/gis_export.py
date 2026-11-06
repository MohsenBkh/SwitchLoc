# -*- coding: utf-8 -*-
"""gis_export.py — خروجی GIS فاز ۵ (GeoJSON + CSV، بدون وابستگی جدید).

Four field/GIS-ready artefacts in one directory:

  switchloc_network.geojson   — feeder lines (canonical branch polylines,
                                attributes: feeder, conductor, length,
                                traced feeder, zone number)
  switchloc_switches.geojson  — points: existing switchgear + ★ proposed
                                Phase-4 switches + feeder-head sources
  switchloc_zones.geojson     — per-zone MultiLineString with load proxy
                                and boundary switches (جدول ۱۵ geometry)
  switch_schedule.csv         — the actionable crew sheet (Excel-friendly
                                UTF-8-BOM): analysis-CRS metres + WGS84

GeoJSON follows RFC 7946: geometries are transformed to WGS84 lon/lat
with pyproj (already a core dependency) when the analysis EPSG is known;
the analysis CRS is still recorded top-level and in the metadata so no
information is lost.  When the EPSG is unknown the coordinates are
exported as-is with an explicit crs member — never silently wrong.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ..domain.enums import NodeKind
from .model import StudyModel
from ..logging_setup import get_logger

_log = get_logger("reporting")

_PROPOSED_COLOR = "#2e7d32"


class _Wgs84:
    """Cached per-model WGS84 transformer (None → passthrough)."""

    def __init__(self, m: StudyModel):
        self.epsg = m.epsg
        self._tr = None
        self.available = False
        if self.epsg and self.epsg != 4326:
            try:
                from pyproj import Transformer
                self._tr = Transformer.from_crs(
                    f"EPSG:{self.epsg}", "EPSG:4326", always_xy=True)
                self.available = True
            except Exception as exc:                   # noqa: BLE001
                _log.warning("GIS export: no WGS84 transformer for EPSG:%s "
                             "(%s) — coordinates will NOT be reprojected",
                             self.epsg, exc)
                self._tr = None

    def pt(self, xy) -> list:
        if self._tr is None:
            return [float(xy[0]), float(xy[1])]
        lon, lat = self._tr.transform(float(xy[0]), float(xy[1]))
        return [round(float(lon), 7), round(float(lat), 7)]

    def line(self, coords) -> list:
        return [self.pt(c) for c in coords]


def _feat(geom_type, coords, props: dict) -> dict:
    return {"type": "Feature", "geometry": {"type": geom_type,
                                            "coordinates": coords},
            "properties": props}


def export_gis(m: StudyModel, out_dir: str) -> list:
    """Write the four artefacts; return their paths."""
    od = Path(out_dir)
    od.mkdir(parents=True, exist_ok=True)
    w = _Wgs84(m)

    crs_block = {
        "analysis_crs": m.crs_label,
        "analysis_epsg": m.epsg,
        "geometry_crs": ("EPSG:4326 (WGS84 — RFC 7946)"
                         if w.available else "همان مختصات تحلیل (EPSG نامشخص)"),
    }
    paths = []

    # ---------------- network lines ---------------------------------------
    feeder_of_edge = m.feeder_of_edge()
    zone_no_of_edge: dict = {}
    for z in m.topo.zones.zones:
        for eid in z.edges:
            cur = zone_no_of_edge.get(eid)
            if cur is None or z.zone_no < cur:
                zone_no_of_edge[eid] = z.zone_no
    feats = []
    for br in m.branch_polylines():
        lines = [w.line(ln) for ln in br["lines"]]
        geom = ({"type": "LineString", "coordinates": lines[0]}
                if len(lines) == 1 else
                {"type": "MultiLineString", "coordinates": lines})
        eid_of = _edge_id_of_branch(m, br["branch_id"])
        traced = ""
        for eid in eid_of:
            if eid in feeder_of_edge:
                traced = feeder_of_edge[eid]
                break
        zn = min((zone_no_of_edge[e] for e in eid_of
                  if e in zone_no_of_edge), default=None)
        feats.append({"type": "Feature", "geometry": geom,
                      "properties": {
                          "branch_id": br["branch_id"],
                          "kind": br["kind"], "feeder": br["feeder"],
                          "feeder_traced": traced,
                          "zone_no": zn,
                          "conductor": br["conductor"],
                          "length_m": round(br["length_m"], 1)}})
    paths.append(_dump(od / "switchloc_network.geojson", {
        "type": "FeatureCollection",
        "name": "switchloc_network",
        **crs_block,
        "features": feats}))

    # ---------------- switches + proposed ---------------------------------
    feats = []
    for sw in sorted(m.net.switches, key=lambda s: s.id):
        c = m.node_coord(sw.node_id)
        if c is None:
            continue
        feats.append(_feat("Point", w.pt(c), {
            "role": "existing_switch",
            "switch_id": sw.id, "node": sw.node_id,
            "family": getattr(sw.family, "value", str(sw.family)),
            "switch_type": sw.switch_type_raw or "",
            "normally_state": sw.normally_state or "",
            "current_state": getattr(sw.current_state, "value",
                                     str(sw.current_state)),
            "remote_controlled": getattr(sw.remote_controlled, "value",
                                         str(sw.remote_controlled)),
            "feeder": sw.feeder_name or "", "proposed": False}))
    # feeder-head sources
    for nd_id, nd in sorted(m.topo.graph.nodes.items()):
        if nd.coord is None:
            continue
        if getattr(nd.kind, "value", str(nd.kind)) == NodeKind.SOURCE.value:
            feats.append(_feat("Point", w.pt(nd.coord), {
                "role": "source", "node": nd_id,
                "feeder": nd.feeder_hint or "", "proposed": False}))
    for p in m.build_proposed():
        if p.x is None or p.y is None:
            continue
        feats.append(_feat("Point", w.pt((p.x, p.y)), {
            "role": "proposed_switch",
            "node": p.node, "feeder": p.feeder, "kind": p.kind,
            "kind_fa": p.kind_fa, "order_in_scheme": p.order_in_scheme,
            "zone_no": p.zone_no, "scheme_id": p.scheme_id,
            "scheme_kind": p.scheme_kind, "note": p.note,
            "proposed": True,
            "_style": {"color": _PROPOSED_COLOR, "marker-symbol": "star"}}))
    paths.append(_dump(od / "switchloc_switches.geojson", {
        "type": "FeatureCollection",
        "name": "switchloc_switches",
        **crs_block,
        "features": feats}))

    # ---------------- zones -------------------------------------------------
    n1 = m.placement.n1
    feats = []
    for z in m.topo.zones.zones:
        lines = [w.line(ln) for ln in m.zone_edges(z)]
        if not lines:
            continue
        bnd = sorted(r.switch_id for r in m.topo.zones.boundaries
                     if z.id in r.zones and r.switch_id)
        feats.append(_feat("MultiLineString", lines, {
            "zone_id": z.id, "feeder": z.feeder,
            "zone_no": z.zone_no, "kind": z.kind,
            "length_m": round(z.length_m, 1),
            "load_kw": round(n1.zone_load_kw.get(z.id, 0.0), 1),
            "transformers": len(z.transformer_ids),
            "boundary_switches": bnd}))
    paths.append(_dump(od / "switchloc_zones.geojson", {
        "type": "FeatureCollection",
        "name": "switchloc_zones",
        **crs_block,
        "features": feats}))

    # ---------------- CSV crew sheet ---------------------------------------
    csv_path = od / "switch_schedule.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        wcsv = csv.writer(fh)
        wcsv.writerow(["feeder", "node", "kind", "kind_fa", "order",
                       "zone_no", "x_analysis_m", "y_analysis_m",
                       "lon_wgs84", "lat_wgs84", "scheme_id", "note"])
        for p in m.build_proposed():
            wcsv.writerow([p.feeder, p.node, p.kind, p.kind_fa,
                           p.order_in_scheme,
                           "" if p.zone_no is None else p.zone_no,
                           "" if p.x is None else round(p.x, 2),
                           "" if p.y is None else round(p.y, 2),
                           "" if p.lon is None else round(p.lon, 6),
                           "" if p.lat is None else round(p.lat, 6),
                           p.scheme_id, p.note])
    paths.append(str(csv_path))

    # ---------------- metadata ----------------------------------------------
    meta = {
        "what": "SwitchLoc فاز ۵ — خروجی GIS مطالعه جایابی کلید",
        "project": m.name, "placement_run_id": m.placement_run_id,
        "analysis_crs": m.crs_label, **crs_block,
        "counts": m.kpis(),
        "layers": {
            "switchloc_network.geojson": "خطوط فیدر با فیدر ردیابی‌شده و زون",
            "switchloc_switches.geojson":
                "کلیدهای موجود + منابع + ★ کلیدهای پیشنهادی",
            "switchloc_zones.geojson": "زون‌های تعریف ۵-۲۱ با بار زون",
            "switch_schedule.csv": "کاربرگ اجرایی کلیدها (اکسل‌پسند)",
        },
    }
    paths.append(str(od / "switchloc_export_metadata.json"))
    (od / "switchloc_export_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    return paths


def _edge_id_of_branch(m: StudyModel, branch_id: str) -> list:
    """graph edge ids belonging to one canonical branch."""
    out = []
    for eid, e in m.topo.graph.edges.items():
        if getattr(e, "branch_id", "") == branch_id:
            out.append(eid)
    return out


def _dump(path: Path, payload: dict) -> str:
    path.write_text(json.dumps(payload, ensure_ascii=False,
                               default=str), encoding="utf-8")
    return str(path)
