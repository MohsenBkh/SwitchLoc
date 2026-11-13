# -*- coding: utf-8 -*-
"""CRS management (main prompt §۵-۴ / D-01 of ARCHITECTURE.md).

Rules implemented:
* resolve each layer's CRS: explicit EPSG parameter > .prj WKT > GeoJSON
  default (OGC:CRS84) — the same precedence documented for GeoGrid geo.py
  (audit §۶) but re-implemented independently with pyproj;
* project-level analysis CRS = a *metric* CRS (UTM here); layers whose
  CRS differs are transformed **once**, recorded in CRSDefinition, and
  repeated transforms are blocked (GIS-DOUBLE-TRANSFORM guard);
* degree-based (geographic) layers are never silently mixed into metric
  math — they are transformed or the study stops with an issue.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from pyproj import CRS, Transformer

from ..validation.issues import (IssueLog, ValidationIssue,
                                 SEVERITY_ERROR, SEVERITY_WARNING,
                                 SEVERITY_INFO)
from ..logging_setup import get_logger

_log = get_logger("gis")

_EPSG_RE = re.compile(r"EPSG[\":\s]+(\d{4,5})", re.IGNORECASE)


@dataclass
class CrsInfo:
    wkt: str
    epsg: int | None
    is_projected: bool
    unit_name: str

    @classmethod
    def parse(cls, text: str) -> "CrsInfo | None":
        """Parse a WKT1 string or 'EPSG:xxxx'."""
        t = (text or "").strip()
        if not t:
            return None
        try:
            if t.upper().startswith("EPSG:"):
                c = CRS.from_epsg(t.split(":", 1)[1])
            else:
                c = CRS.from_wkt(t)
        except Exception as _exc:  # noqa: BLE001
            _log.warning("crs.py: recoverable error: %s", _exc)
            m = _EPSG_RE.search(t)
            if m:
                try:
                    c = CRS.from_epsg(m.group(1))
                except Exception as _exc:  # noqa: BLE001
                    _log.warning("crs.py: recoverable error: %s", _exc)
                    return None
            else:
                return None
        return cls(wkt=t, epsg=c.to_epsg(), is_projected=c.is_projected,
                   unit_name=(c.axis_info[0].unit_name if c.axis_info else ""))


def transform_utm_to_project(easting: float, northing: float,
                             zone: int, target_crs: str | int) -> tuple[float, float]:
    """Convert a northern-hemisphere UTM coordinate in zone 38/39 to
    the project's metric CRS.  Coordinates are never silently treated as
    project coordinates when the selected UTM zone differs.
    """
    if zone not in (38, 39):
        raise ValueError("UTM zone must be 38N or 39N.")
    x, y = float(easting), float(northing)
    if not (100000.0 <= x <= 900000.0 and 0.0 <= y <= 10000000.0):
        raise ValueError("UTM Easting/Northing is outside the valid range.")
    dst = CRS.from_user_input(target_crs)
    if not dst.is_projected:
        raise ValueError("Project CRS must be projected (metric).")
    unit_factor = (dst.axis_info[0].unit_conversion_factor
                   if dst.axis_info else None)
    if unit_factor is None or abs(float(unit_factor) - 1.0) > 1e-9:
        raise ValueError("Project CRS must use metres for network coordinates.")
    src = CRS.from_epsg(32600 + zone)  # UTM northern hemisphere
    tr = Transformer.from_crs(src, dst, always_xy=True)
    rx, ry = tr.transform(x, y)
    if not (math.isfinite(rx) and math.isfinite(ry)):
        raise ValueError("UTM coordinate transformation returned invalid values.")
    return float(rx), float(ry)


from functools import lru_cache


@lru_cache(maxsize=64)
def _wgs84_transformer(target_crs):
    dst = CRS.from_user_input(target_crs)
    if not dst.is_projected:
        raise ValueError("CRS پروژه باید متری (projected) باشد.")
    return Transformer.from_crs(CRS.from_epsg(4326), dst, always_xy=True)


def transform_wgs84_to_project(lat: float, lon: float,
                               target_crs: str | int) -> tuple[float, float]:
    """(lat, lon) WGS84 → مختصات متری پروژه.

    برای جای‌گذاری نقاط گازیتیر (درجه) روی شبکه با CRS متری لازم است.
    خطای ورودی/CRS به‌صورت ValueError منتقل می‌شود تا هیچ مختصاتی حدس
    زده نشود (بند ۱۹).
    """
    lat_f, lon_f = float(lat), float(lon)
    if not (math.isfinite(lat_f) and math.isfinite(lon_f)):
        raise ValueError("مختصات جغرافیایی نامعتبر است.")
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
        raise ValueError("مختصات جغرافیایی خارج از بازهٔ مجاز است.")
    x, y = _wgs84_transformer(target_crs).transform(lon_f, lat_f)
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError("تبدیل مختصات نتیجهٔ معتبری برنگرداند.")
    return float(x), float(y)


class CrsService:
    """Per-project CRS bookkeeping and one-time transformation."""

    def __init__(self, analysis_epsg: int | None = None,
                 analysis_wkt: str = ""):
        self._analysis: CRS | None = None
        if analysis_epsg:
            self._analysis = CRS.from_epsg(analysis_epsg)
        elif analysis_wkt:
            self._analysis = CRS.from_wkt(analysis_wkt)
        self._transformers: dict[tuple[int, int], Transformer] = {}
        self.definitions: dict[str, dict] = {}   # layer → record

    # -- resolution ---------------------------------------------------------
    @property
    def analysis_crs(self) -> CRS | None:
        return self._analysis

    def set_analysis_from_majority(self, infos: list[CrsInfo],
                                   issues: IssueLog) -> CRS | None:
        """Choose the most frequent projected (metric) CRS as analysis CRS."""
        projected = [c for c in infos if c and c.is_projected]
        if not projected:
            issues.add(ValidationIssue(
                code="GIS-NO-CRS", severity=SEVERITY_ERROR,
                message_fa="هیچ لایه‌ای CRS متری ندارد؛ محاسبات متری ممکن نیست.",
                impact_fa="CRS لایه‌ها را تعیین کنید (فایل .prj یا EPSG صریح)."))
            return None
        counts: dict[int | None, int] = {}
        for c in projected:
            counts[c.epsg] = counts.get(c.epsg, 0) + 1
        epsg = max(counts, key=lambda k: counts[k])
        self._analysis = CRS.from_epsg(epsg)
        return self._analysis

    def resolve(self, layer_name: str, layer_crs_wkt: str,
                issues: IssueLog, explicit_epsg: int | None = None) -> CrsInfo | None:
        """Resolve one layer's CRS; emits issues when missing/geographic."""
        if explicit_epsg:
            wkt = f"EPSG:{explicit_epsg}"
        else:
            wkt = layer_crs_wkt
        info = CrsInfo.parse(wkt)
        if info is None:
            issues.add(ValidationIssue(
                code="GIS-NO-CRS", severity=SEVERITY_ERROR,
                message_fa=f"CRS لایه «{layer_name}» قابل تشخیص نیست.",
                source_file="", layer=layer_name, field="CRS",
                suggestion_fa="فایل .prj سالم قرار دهید یا EPSG را صریح وارد کنید.",
                impact_fa="این لایه وارد محاسبات متری نمی‌شود."))
            self.definitions[layer_name] = {
                "layer": layer_name, "crs_original": wkt, "crs_analysis": "",
                "epsg": None, "transformed": False, "transform_note": "unresolved"}
            return None
        if not info.is_projected:
            issues.add(ValidationIssue(
                code="GIS-CRS-GEOGRAPHIC", severity=SEVERITY_WARNING,
                message_fa=f"CRS لایه «{layer_name}» جغرافیایی (درجه) است؛ "
                           f"برای تحلیل متری تبدیل می‌شود.",
                layer=layer_name, field="CRS",
                impact_fa="یک‌بار به CRS تحلیلی متری تبدیل خواهد شد."))
        self.definitions[layer_name] = {
            "layer": layer_name, "crs_original": info.wkt,
            "crs_analysis": "", "epsg": info.epsg,
            "transformed": False, "transform_note": "resolved"}
        return info

    # -- transformation -----------------------------------------------------
    def to_analysis(self, layer_name: str, x: float, y: float,
                    source: CrsInfo, issues: IssueLog) -> tuple[float, float]:
        """Transform one point to the analysis CRS — once per layer."""
        if self._analysis is None:
            raise RuntimeError("CRS تحلیلی هنوز انتخاب نشده است.")
        if source.epsg is not None and self._analysis.to_epsg() == source.epsg:
            return x, y                      # already the analysis CRS
        if not source.is_projected and not math.isfinite(x + y):
            raise ValueError("مختصات نامعتبر")
        key = (source.epsg if source.epsg is not None else -1,
               self._analysis.to_epsg() or -1)
        tr = self._transformers.get(key)
        if tr is None:
            src = CRS.from_epsg(source.epsg) if source.epsg else CRS.from_wkt(source.wkt)
            tr = Transformer.from_crs(src, self._analysis, always_xy=True)
            self._transformers[key] = tr
        try:
            rx, ry = tr.transform(x, y)
        except Exception as e:  # noqa: BLE001
            issues.add(ValidationIssue(
                code="GIS-COORD-OUT-OF-RANGE", severity=SEVERITY_WARNING,
                message_fa=f"تبدیل نقطه لایه «{layer_name}» ناموفق بود: {e}",
                layer=layer_name, current_value=f"({x}, {y})",
                impact_fa="این نقطه از تحلیل متری کنار گذاشته می‌شود."))
            raise
        rec = self.definitions.get(layer_name)
        if rec is not None and not rec["transformed"]:
            rec["transformed"] = True
            rec["crs_analysis"] = f"EPSG:{self._analysis.to_epsg()}"
            rec["transform_note"] = "one-time transform"
        return rx, ry

    def guard_no_double_transform(self, layer_name: str) -> None:
        """Explicit guard: transforming a layer twice is a bug → raise."""
        rec = self.definitions.get(layer_name)
        if rec is not None and rec["transformed"] and rec["transform_note"] == "one-time transform":
            raise RuntimeError(
                f"تبدیل تکراری CRS برای لایه «{layer_name}» مسدود است "
                f"(GIS-DOUBLE-TRANSFORM).")
