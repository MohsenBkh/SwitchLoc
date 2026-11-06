# -*- coding: utf-8 -*-
"""GeoPackage GisReader (Phase 1).

Implemented over pyogrio (GDAL binding) when available — the offline
Windows bundle may omit it, in which case the reader reports a clear,
actionable error instead of failing silently.
"""
from __future__ import annotations

from pathlib import Path

from ...validation.issues import (IssueLog, ValidationIssue, SEVERITY_ERROR)
from ..mapping import field_catalog as fc
from .base import Feature, LayerInfo
from ...logging_setup import get_logger

_log = get_logger("gis")

try:
    import pyogrio  # noqa: F401
    _HAS_OGR = True
except ImportError:  # pragma: no cover
    _HAS_OGR = False


class GeoPackageReader:
    format_name = "gpkg"

    def discover(self, source) -> list[LayerInfo]:
        path = Path(source)
        gpkg_files = [path] if path.is_file() and path.suffix.lower() == ".gpkg" \
            else sorted(path.rglob("*.gpkg"))
        if gpkg_files and not _HAS_OGR:
            raise RuntimeError(
                "خواندن GeoPackage نیازمند بسته pyogrio است؛ آن را نصب کنید یا "
                "داده را به Shapefile/GeoJSON تبدیل نمایید.")
        layers: list[LayerInfo] = []
        for gp in gpkg_files:
            try:
                import pyogrio
                info = pyogrio.list_layers(str(gp))   # [(name, geom_type), ...]
            except Exception as e:  # noqa: BLE001
                _log.warning("gpkg_reader.py: recoverable error: %s", e)
                layers.append(LayerInfo(name=gp.stem, path=str(gp), feature_count=-1))
                continue
            for name, gtype in info:
                try:
                    meta = pyogrio.read_info(str(gp), layer=name)
                    fields = [f for f in meta["fields"]]
                    cnt = int(meta["features"])
                    crs = ""
                    epsg = meta.get("crs") and getattr(meta["crs"], "to_epsg", lambda: None)()
                    if epsg:
                        crs = f"EPSG:{epsg}"
                except Exception as _exc:  # noqa: BLE001
                    _log.warning("gpkg_reader.py: recoverable error: %s", _exc)
                    fields, cnt, crs = [], -1, ""
                layers.append(LayerInfo(name=str(name), path=str(gp),
                                        geometry_type=str(gtype),
                                        feature_count=cnt, fields=fields,
                                        crs_wkt=crs))
        return layers

    def read(self, layer: LayerInfo, issues: IssueLog | None = None) -> list[Feature]:
        issues = issues or IssueLog()
        try:
            import pyogrio
            import geopandas as gpd
            gdf = gpd.read_file(layer.path, layer=layer.name)
        except Exception as e:  # noqa: BLE001
            issues.add(ValidationIssue(
                code="GIS-LAYER-UNREADABLE", severity=SEVERITY_ERROR,
                message_fa=f"لایه «{layer.name}» از GeoPackage خوانده نشد: {e}",
                source_file=layer.path, layer=layer.name,
                impact_fa="این لایه از مطالعه کنار گذاشته می‌شود."))
            return []
        epsg = gdf.crs.to_epsg() if gdf.crs is not None else None
        crs_txt = f"EPSG:{epsg}" if epsg else (str(gdf.crs) if gdf.crs else "")
        feats: list[Feature] = []
        for i, row in gdf.iterrows():
            geom = row.geometry
            pts, parts = [], 1
            if geom is not None and not geom.is_empty:
                g = list(getattr(geom, "geoms", [geom]))[0]
                pts = list(g.coords) if hasattr(g, "coords") else \
                    ([tuple(geom.coords)] if hasattr(geom, "coords") else [])
                parts = len(list(getattr(geom, "geoms", [geom])))
            rec = {c: row[c] for c in gdf.columns if c != "geometry"}
            rid = fc.record_id(rec)
            if not rid:
                issues.add(ValidationIssue(
                    code="GIS-EMPTY-ID", severity="Warning",
                    message_fa="شناسه عارضه خالی است.",
                    source_file=layer.path, layer=layer.name, record_id=str(i),
                    impact_fa="ردیابی تا منبع دشوار می‌شود."))
            if not fc.feeder_name(rec):
                issues.add(ValidationIssue(
                    code="GIS-FEEDER-MISSING", severity="Information",
                    message_fa="نام فیدر در فیلدهای شناخته‌شده موجود نیست.",
                    source_file=layer.path, layer=layer.name, record_id=rid,
                    impact_fa="تخصیص به فیدر نیاز به تصمیم کاربر دارد."))
            feats.append(Feature(
                layer=layer.name, record_index=int(i), record_id=rid,
                feeder=fc.feeder_name(rec), service_state=fc.service_state(rec),
                remote_controlled=fc.remote_controlled(rec),
                attributes=rec, points=pts, parts=parts, crs_wkt=crs_txt))
        return feats
