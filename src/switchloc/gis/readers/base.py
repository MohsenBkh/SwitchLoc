# -*- coding: utf-8 -*-
"""Reader contract (docs/ARCHITECTURE.md §۲ — رابط GIS Adapter).

Every input format must satisfy `GisReader`: discover() returns layer
metadata, read() returns traceable Features and surfaces every anomaly
as a ValidationIssue — never a silent drop, never an input mutation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field as dc_field

from ...validation.issues import IssueLog


@dataclass
class LayerInfo:
    """Metadata of one discovered layer."""
    name: str                       # base name without extension / sheet name
    path: str                       # full path of the backing file
    geometry_type: str = ""         # POINT | POLYLINE | TABULAR | ...
    feature_count: int = 0          # -1 while unknown/unreadable
    fields: list = dc_field(default_factory=list)
    crs_wkt: str = ""               # WKT1 or 'EPSG:xxxx' or 'OGC:CRS84'
    encoding: str = "utf-8"

    def to_dict(self) -> dict:
        return {
            "name": self.name, "path": self.path,
            "geometry_type": self.geometry_type,
            "feature_count": self.feature_count,
            "fields": list(self.fields), "crs_wkt": self.crs_wkt,
            "encoding": self.encoding,
        }


@dataclass
class Feature:
    """One traceable feature (record) of a layer."""
    layer: str
    record_index: int
    record_id: str                  # first non-empty of ID_FIELDS
    feeder: str                     # documented fallback chain
    service_state: str              # in | out | unknown
    remote_controlled: str          # yes | no | unknown
    attributes: dict
    points: list                    # [(x, y), ...] first part; [] for tabular
    parts: int = 1                  # number of geometry parts
    crs_wkt: str = ""               # per-layer CRS (filled by reader)


class GisReader:
    """Interface — subclass per format (shapefile/geojson/gpkg/tabular)."""
    format_name = "abstract"

    def discover(self, source: str | os.PathLike) -> list[LayerInfo]:
        raise NotImplementedError

    def read(self, layer: LayerInfo, issues: IssueLog | None = None) -> list[Feature]:
        raise NotImplementedError
