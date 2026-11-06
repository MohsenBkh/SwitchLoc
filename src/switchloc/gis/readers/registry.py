# -*- coding: utf-8 -*-
"""Reader registry — format detection and fan-out discovery (Phase 1)."""
from __future__ import annotations

from pathlib import Path

from ...validation.issues import IssueLog, ValidationIssue, SEVERITY_WARNING
from .base import Feature, GisReader, LayerInfo
from .geojson_reader import GeoJSONReader
from .gpkg_reader import GeoPackageReader
from .shapefile_reader import ShapefileReader
from .tabular_reader import TabularReader

__all__ = ["Feature", "GisReader", "LayerInfo", "ShapefileReader",
           "GeoJSONReader", "GeoPackageReader", "TabularReader",
           "readers_for_source", "discover_all"]

_SUFFIX_MAP = {
    ".shp": ShapefileReader,
    ".geojson": GeoJSONReader,
    ".gpkg": GeoPackageReader,
    ".xlsx": TabularReader,
    ".csv": TabularReader,
}


def readers_for_source(source) -> list[GisReader]:
    """Which reader classes can handle this path/folder?"""
    p = Path(source)
    sufs = {p.suffix.lower()} if p.is_file() else \
        {c.suffix.lower() for c in p.rglob("*") if c.is_file()}
    classes, seen = [], set()
    for s, cls in sorted(_SUFFIX_MAP.items()):
        if s in sufs and cls.__name__ not in seen:
            classes.append(cls())
            seen.add(cls.__name__)
    return classes


def discover_all(source, issues: IssueLog | None = None):
    """Discover layers across every supported format under `source`.

    Returns (layers, reader_by_layer_name).  Name collisions between
    formats are disambiguated as '<name>@<format>' and an Information
    issue records the rename — nothing is silently merged.
    """
    issues = issues or IssueLog()
    layers: list[LayerInfo] = []
    reader_of: dict[str, GisReader] = {}
    for rdr in readers_for_source(source):
        for li in rdr.discover(source):
            name = li.name
            if name in reader_of:
                issues.add(ValidationIssue(
                    code="GIS-LAYER-NAME-COLLISION", severity=SEVERITY_WARNING,
                    message_fa=f"نام لایه «{name}» در دو قالب تکراری است؛ "
                               f"قالب دوم با پسوند @format ثبت شد.",
                    source_file=li.path, layer=name,
                    impact_fa="هر دو لایه حفظ می‌شوند و قابل تفکیک هستند."))
                name = f"{name}@{rdr.format_name}"
                li.name = name
            layers.append(li)
            reader_of[name] = rdr
    return layers, reader_of
