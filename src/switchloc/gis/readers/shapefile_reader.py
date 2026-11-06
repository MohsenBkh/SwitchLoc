# -*- coding: utf-8 -*-
"""Production Shapefile GisReader (Phase 1).

Contract (docs/ARCHITECTURE.md §۲, audit tests GG-01/02/09):
* discover layers recursively in a folder (with ELW/EL aliasing handled
  by the mapping catalog, not by renaming),
* read features + geometry via pyshp (light path, like the audited
  GeoGrid pipeline) with a geopandas fallback,
* keep every record traceable to (file, layer, record index),
* surface every anomaly as a ValidationIssue instead of silently
  dropping anything,
* NEVER modify the input files (GG-02 — hashes taken by ImportService).

Re-used documented knowledge (no code import): pyshp-first reading,
UTF-8/CPG encoding handling, per-feature QC checks — see
docs/ALGORITHM_TRACEABILITY.md entry R-01.
"""
from __future__ import annotations

from pathlib import Path

from ...validation.issues import (IssueLog, ValidationIssue,
                                  SEVERITY_ERROR, SEVERITY_WARNING,
                                  SEVERITY_INFO)
from ..mapping import field_catalog as fc
from .base import Feature, LayerInfo
from ...logging_setup import get_logger

_log = get_logger("gis")

try:  # light path first (pure Python, no GDAL)
    import shapefile as _pyshp
except ImportError:  # pragma: no cover
    _pyshp = None

try:  # heavy fallback
    import geopandas as _gpd
except ImportError:  # pragma: no cover
    _gpd = None


_SHAPE_TYPES = {0: "NULL", 1: "POINT", 3: "POLYLINE", 5: "POLYGON",
                8: "MULTIPOINT", 11: "POINTZ", 13: "POLYLINEZ",
                15: "POLYGONZ", 18: "MULTIPOINTZ", 21: "POINTM",
                23: "POLYLINEM", 25: "POLYGONM", 28: "MULTIPOINTM",
                31: "MULTIPATCH"}


def _read_prj(shp_path: Path) -> str:
    prj = shp_path.with_suffix(".prj")
    if prj.exists():
        try:
            return prj.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            return ""
    return ""


def _read_cpg(shp_path: Path) -> str:
    cpg = shp_path.with_suffix(".cpg")
    if cpg.exists():
        try:
            return cpg.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            return ""
    return ""


class ShapefileReader:
    """GisReader implementation for ESRI shapefiles."""

    format_name = "shapefile"

    # -- discovery ---------------------------------------------------------
    def discover(self, folder: str | Path) -> list[LayerInfo]:
        """Recursively find *.shp under `folder`; unique by base name."""
        root = Path(folder)
        if not root.is_dir():
            raise NotADirectoryError(str(folder))
        layers: dict[str, LayerInfo] = {}
        for path in sorted(root.rglob("*.shp")):
            name = path.stem
            if name in layers:      # first (lexicographic) wins; duplicates noted by caller
                continue
            li = LayerInfo(
                name=name, path=str(path),
                crs_wkt=_read_prj(path), encoding=_read_cpg(path) or "utf-8",
            )
            layers[name] = li
        if _pyshp is not None:
            for li in layers.values():
                try:
                    r = _pyshp.Reader(li.path, encoding=li.encoding)
                    li.fields = [f[0] for f in r.fields[1:]]
                    li.feature_count = len(r)
                    li.geometry_type = _SHAPE_TYPES.get(r.shapeType, f"TYPE{r.shapeType}")
                except Exception as _exc:
                    _log.warning("shapefile_reader.py: recoverable error: %s", _exc)
                    li.feature_count = -1    # unreadable; surface at read()
        return [layers[k] for k in sorted(layers)]

    # -- reading -----------------------------------------------------------
    def read(self, layer: LayerInfo, issues: IssueLog | None = None) -> list[Feature]:
        """Read all features of one layer; log issues, never drop silently."""
        issues = issues or IssueLog()
        if _pyshp is not None:
            return self._read_pyshp(layer, issues)
        if _gpd is not None:
            return self._read_geopandas(layer, issues)
        raise RuntimeError("Neither pyshp nor geopandas is installed")

    # pyshp path -----------------------------------------------------------
    def _read_pyshp(self, li: LayerInfo, issues: IssueLog) -> list[Feature]:
        try:
            r = _pyshp.Reader(li.path, encoding=li.encoding)
            flds = [f[0] for f in r.fields[1:]]
        except Exception as e:  # noqa: BLE001
            issues.add(ValidationIssue(
                code="GIS-LAYER-UNREADABLE", severity=SEVERITY_ERROR,
                message_fa=f"لایه «{li.name}» قابل خواندن نیست: {e}",
                source_file=li.path, layer=li.name,
                impact_fa="این لایه از مطالعه کنار گذاشته می‌شود.",
            ))
            return []
        feats: list[Feature] = []
        for i, sr in enumerate(r.iterShapeRecords()):
            rec = dict(zip(flds, sr.record))
            sh = sr.shape
            pts = list(getattr(sh, "points", []) or [])
            parts = max(1, len(getattr(sh, "parts", []) or [0]))
            issues.extend(self._quality_issues(li, rec, pts, i, parts))
            feats.append(Feature(
                layer=li.name, record_index=i, record_id=fc.record_id(rec),
                feeder=fc.feeder_name(rec), service_state=fc.service_state(rec),
                remote_controlled=fc.remote_controlled(rec),
                attributes=rec, points=pts, parts=parts, crs_wkt=li.crs_wkt,
            ))
        if not feats:
            issues.add(ValidationIssue(
                code="GIS-LAYER-EMPTY", severity=SEVERITY_INFO,
                message_fa=f"لایه «{li.name}» هیچ عارضه‌ای ندارد.",
                source_file=li.path, layer=li.name,
                impact_fa="بدون اثر؛ صرفاً ثبت‌شده.",
            ))
        return feats

    def _read_geopandas(self, li: LayerInfo, issues: IssueLog) -> list[Feature]:
        try:
            import geopandas as gpd
            gdf = gpd.read_file(li.path, encoding=li.encoding or "utf-8")
        except Exception as e:  # noqa: BLE001
            issues.add(ValidationIssue(
                code="GIS-LAYER-UNREADABLE", severity=SEVERITY_ERROR,
                message_fa=f"لایه «{li.name}» قابل خواندن نیست: {e}",
                source_file=li.path, layer=li.name, impact_fa="لایه کنار گذاشته می‌شود.",
            ))
            return []
        feats: list[Feature] = []
        for i, row in gdf.iterrows():
            geom = row.geometry
            pts, parts = [], 1
            if geom is not None and not geom.is_empty:
                g = list(getattr(geom, "geoms", [geom]))[0]
                pts = list(g.coords) if hasattr(g, "coords") else []
            rec = {c: row[c] for c in gdf.columns if c != "geometry"}
            issues.extend(self._quality_issues(li, rec, pts, int(i), parts))
            feats.append(Feature(
                layer=li.name, record_index=int(i), record_id=fc.record_id(rec),
                feeder=fc.feeder_name(rec), service_state=fc.service_state(rec),
                remote_controlled=fc.remote_controlled(rec),
                attributes=rec, points=pts, parts=parts, crs_wkt=li.crs_wkt,
            ))
        return feats

    # QC -------------------------------------------------------------------
    def _quality_issues(self, li: LayerInfo, rec: dict, pts: list, idx: int,
                        parts: int = 1):
        out = []
        rid = fc.record_id(rec)
        if not rid:
            out.append(ValidationIssue(
                code="GIS-EMPTY-ID", severity=SEVERITY_WARNING,
                message_fa="شناسه عارضه (T_MapID/OBJECTID) خالی است.",
                source_file=li.path, layer=li.name,
                record_id=str(idx), field="T_MapID",
                impact_fa="ردیابی این رکورد تا منبع دشوار می‌شود.",
            ))
        if not pts:
            out.append(ValidationIssue(
                code="GIS-NULL-GEOM", severity=SEVERITY_WARNING,
                message_fa="هندسه خالی یا بدون رأس.",
                source_file=li.path, layer=li.name, record_id=rid,
                impact_fa="در توپولوژی و محاسبات لحاظ نمی‌شود.",
            ))
        elif len(pts) == 1 and li.geometry_type.startswith("POLYLINE"):
            out.append(ValidationIssue(
                code="GIS-ZERO-LENGTH", severity=SEVERITY_WARNING,
                message_fa="خط تک‌رأسی (طول مؤثر صفر).",
                source_file=li.path, layer=li.name, record_id=rid,
                impact_fa="اتصال الکتریکی ایجاد نمی‌کند.",
            ))
        if parts > 1:
            out.append(ValidationIssue(
                code="GIS-MULTIPART", severity=SEVERITY_INFO,
                message_fa=f"هندسه چندقسمتی ({parts} قسمت)؛ فقط قسمت اول در "
                           f"توپولوژی استفاده می‌شود.",
                source_file=li.path, layer=li.name, record_id=rid,
                suggestion_fa="در صورت نیاز، قسمت‌ها به‌صورت عارضه جداگانه وارد شود.",
                impact_fa="قسمت‌های دوم به بعد نادیده گرفته می‌شوند (ثبت‌شده).",
            ))
        if not fc.feeder_name(rec):
            out.append(ValidationIssue(
                code="GIS-FEEDER-MISSING", severity=SEVERITY_INFO,
                message_fa="نام فیدر در هیچ‌یک از فیلدهای شناخته‌شده موجود نیست.",
                source_file=li.path, layer=li.name, record_id=rid,
                field="Feeder/T_FeederNa/T_feader/T_name_fdr",
                impact_fa="تخصیص به فیدر نیاز به تصمیم کاربر دارد.",
            ))
        return out
