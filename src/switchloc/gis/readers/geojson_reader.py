# -*- coding: utf-8 -*-
"""GeoJSON GisReader (Phase 1).

RFC 7946 declares WGS84 (OGC:CRS84) unless a legacy "crs" member exists;
a degree-based layer entering a metric analysis pipeline is flagged so
the CRS service transforms it once, explicitly.
"""
from __future__ import annotations

import json
from pathlib import Path

from ...validation.issues import (IssueLog, ValidationIssue,
                                  SEVERITY_ERROR, SEVERITY_INFO)
from ..mapping import field_catalog as fc
from .base import Feature, LayerInfo
from ...logging_setup import get_logger

_log = get_logger("gis")


def _geom_points(geom: dict):
    """Return (points_of_first_part, parts, geometry_type)."""
    if geom is None:
        return [], 0, ""
    t = geom.get("type", "")
    if t == "Point":
        return [tuple(geom["coordinates"])], 1, "POINT"
    if t in ("LineString", "MultiPoint"):
        return [tuple(c) for c in geom["coordinates"]], 1, "POLYLINE"
    if t == "MultiLineString":
        parts = geom["coordinates"]
        if not parts:
            return [], 0, "POLYLINE"
        return [tuple(c) for c in parts[0]], len(parts), "POLYLINE"
    if t in ("Polygon", "MultiPolygon"):
        # distribution feeders are not polygons; keep readable but flagged
        poly = geom["coordinates"]
        first = poly[0] if poly else []
        return [tuple(c) for c in first], len(poly), "POLYGON"
    return [], 0, t


class GeoJSONReader:
    format_name = "geojson"

    def discover(self, source) -> list[LayerInfo]:
        root = Path(source)
        paths = [root] if root.is_file() and root.suffix.lower() == ".geojson" \
            else sorted(root.rglob("*.geojson"))
        layers = []
        for p in paths:
            li = LayerInfo(name=p.stem, path=str(p), geometry_type="", crs_wkt="OGC:CRS84")
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                _log.warning("geojson_reader.py: recoverable error: %s", e)
                li.feature_count = -1
                layers.append(li)
                continue
            crs = data.get("crs")
            if crs:  # legacy named-CRS member
                li.crs_wkt = str(crs.get("properties", {}).get("name", "unknown"))
            feats = [f for f in data.get("features", []) if isinstance(f, dict)]
            li.feature_count = len(feats)
            fields: list[str] = []
            for f in feats[:200]:                 # signature from first 200
                for k in (f.get("properties") or {}):
                    if k not in fields:
                        fields.append(k)
            li.fields = fields
            if feats:
                li.geometry_type = str((feats[0].get("geometry") or {}).get("type", ""))
            layers.append(li)
        return layers

    def read(self, layer: LayerInfo, issues: IssueLog | None = None) -> list[Feature]:
        issues = issues or IssueLog()
        try:
            data = json.loads(Path(layer.path).read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            issues.add(ValidationIssue(
                code="GIS-LAYER-UNREADABLE", severity=SEVERITY_ERROR,
                message_fa=f"لایه «{layer.name}» قابل خواندن نیست: {e}",
                source_file=layer.path, layer=layer.name,
                impact_fa="این لایه از مطالعه کنار گذاشته می‌شود."))
            return []
        feats: list[Feature] = []
        for i, f in enumerate(data.get("features", [])):
            rec = dict(f.get("properties") or {})
            pts, parts, gtype = _geom_points(f.get("geometry"))
            if gtype in ("POLYGON", "MultiPolygon"):
                issues.add(ValidationIssue(
                    code="GIS-INVALID-GEOM", severity=SEVERITY_INFO,
                    message_fa="هندسه چندضلعی در شبکه خطی فشار متوسط استفاده نمی‌شود.",
                    source_file=layer.path, layer=layer.name,
                    record_id=fc.record_id(rec) or str(i),
                    impact_fa="به‌عنوان مرز منطقه قابل استفاده است؛ در گراف خطی نیست."))
            issues.extend(_qc(layer, rec, pts, i))
            feats.append(Feature(
                layer=layer.name, record_index=i, record_id=fc.record_id(rec),
                feeder=fc.feeder_name(rec), service_state=fc.service_state(rec),
                remote_controlled=fc.remote_controlled(rec),
                attributes=rec, points=pts, parts=max(1, parts),
                crs_wkt=layer.crs_wkt))
        return feats


def _qc(li: LayerInfo, rec: dict, pts: list, idx: int):
    out = []
    rid = fc.record_id(rec)
    if not rid:
        out.append(ValidationIssue(
            code="GIS-EMPTY-ID", severity=SEVERITY_WARNING,
            message_fa="شناسه عارضه خالی است.", source_file=li.path, layer=li.name,
            record_id=str(idx), impact_fa="ردیابی تا منبع دشوار می‌شود."))
    if not pts:
        out.append(ValidationIssue(
            code="GIS-NULL-GEOM", severity=SEVERITY_WARNING,
            message_fa="هندسه خالی یا بدون رأس.", source_file=li.path, layer=li.name,
            record_id=rid, impact_fa="در توپولوژی لحاظ نمی‌شود."))
    if not fc.feeder_name(rec):
        out.append(ValidationIssue(
            code="GIS-FEEDER-MISSING", severity=SEVERITY_INFO,
            message_fa="نام فیدر در فیلدهای شناخته‌شده موجود نیست.",
            source_file=li.path, layer=li.name, record_id=rid,
            impact_fa="تخصیص به فیدر نیاز به تصمیم کاربر دارد."))
    return out
