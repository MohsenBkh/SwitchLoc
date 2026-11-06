# -*- coding: utf-8 -*-
"""Canonical domain entities (Phase 1 — docs/DATA_MODEL.md §۱ و §۲).

Design rules (docs/DATA_MODEL.md «قواعد داده»):
* every entity keeps its SourceRecord chain — traceable to (file, layer,
  record);
* `coord_original` is preserved forever; `coord_snapped` is derived;
* nothing is deleted without a recorded issue (`excluded_with_issue`);
* missing value ≠ zero — missing stays None and surfaces as an issue;
* quantitative fields carry their unit in the attribute name.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Optional

from .enums import (BranchKind, NodeKind, SwitchFamily, SwitchState,
                    YesNoUnknown)
from .ids import stable_id


# ---------------------------------------------------------------------------
# گروه پروژه مطالعاتی
# ---------------------------------------------------------------------------
@dataclass
class SourceRecord:
    """Traceability anchor: every entity points at one of these."""
    file_path: str
    file_sha256: str
    layer: str
    record_ref: str                     # record id (T_MapID/OBJECTID) or index
    geometry_ref: str = ""              # e.g. "points[0]", "part[0]"

    def as_row(self, entity_id: str) -> tuple:
        return (entity_id, self.file_path, self.file_sha256, self.layer,
                self.record_ref, self.geometry_ref)


@dataclass
class LayerMapping:
    """One confirmed slot→layer binding (never automatic-final, بند ۵-۳)."""
    slot_key: str
    file_path: str
    layer_name: str
    field_map: dict = dc_field(default_factory=dict)
    enabled: bool = True
    confirmed_by: str = ""
    confirmed_at: str = ""


@dataclass
class CRSDefinition:
    """Per-layer CRS bookkeeping — prevents double transforms (D-01)."""
    layer: str
    crs_original: str                   # WKT1 / EPSG:xxxx as found
    crs_analysis: str
    epsg: Optional[int]
    transformed: bool = False
    transform_note: str = ""


@dataclass
class StudyRunMeta:
    """Snapshot of one study execution (reproducibility, بند ۱۹)."""
    project_name: str
    started_at: str
    user: str
    algo_version: str
    tav_revision: str = "TAV122-02/00"
    settings_snapshot: dict = dc_field(default_factory=dict)
    input_hashes: dict = dc_field(default_factory=dict)   # path → sha256


# ---------------------------------------------------------------------------
# گروه شبکه
# ---------------------------------------------------------------------------
@dataclass
class Feeder:
    name: str                            # normalized name (e.g. "F1")
    raw_name: str = ""                   # exactly as found in GIS
    substation_hint: str = ""            # e.g. "خلخال" از نام لایه ELWFWT
    nominal_kv: Optional[float] = None
    source: Optional[SourceRecord] = None
    id: str = ""
    _extra: dict = dc_field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = stable_id("feeder", self.name, self.substation_hint)


@dataclass
class Node:
    kind: NodeKind
    coord_original: Optional[tuple]      # (x, y) exactly as read
    coord_snapped: Optional[tuple]       # cluster centroid (tolerance-based)
    feeder_name: str = ""
    id: str = ""
    cluster_key: str = ""                # snap-cluster key (Phase-2 graph)
    source: Optional[SourceRecord] = None
    excluded_with_issue: bool = False

    def __post_init__(self):
        if not self.id:
            self.id = stable_id("node", self.kind.value,
                                repr(self.coord_original),
                                repr(self.coord_snapped), self.cluster_key)


@dataclass
class LineSegment:
    """One 2-point piece of a split polyline (GG-03)."""
    a: tuple
    b: tuple
    length_m: float
    node_a: str = ""                     # filled by assembler (cluster id)
    node_b: str = ""


@dataclass
class Branch:
    kind: BranchKind
    node_a: str                          # cluster/node id at first endpoint
    node_b: str                          # cluster/node id at last endpoint
    length_registered_m: Optional[float] # as recorded in GIS (Shape_STLe)
    length_geometric_m: float            # Σ of segment Euclidean lengths
    segments: list = dc_field(default_factory=list)       # [LineSegment]
    feeder_name: str = ""
    conductor: str = ""                  # T_jns_hadi
    section_mm2: Optional[float] = None  # T_cod_sath
    installation: str = ""               # T_typ_shab (هوایی/زمینی/توزیع)
    source: Optional[SourceRecord] = None
    excluded_with_issue: bool = False
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = stable_id("branch", self.kind.value,
                                repr(self.node_a), repr(self.node_b),
                                self.length_registered_m,
                                self.length_geometric_m,
                                "" if self.source is None else self.source.record_ref)


@dataclass
class SwitchDev:
    family: SwitchFamily
    node_id: str                         # snapped node it sits on
    switch_type_raw: str = ""            # T_type / T_noe_sec / T_noe_kld
    normally_state: str = ""             # NO / NC — user-confirmed (A-09)
    current_state: SwitchState = SwitchState.UNKNOWN
    rating_a: Optional[float] = None     # T_jar_nami
    remote_controlled: YesNoUnknown = YesNoUnknown.UNKNOWN   # T_ctrl_otm
    local_name: str = ""                 # T_lname / T_nam_ght
    feeder_name: str = ""
    layer: str = ""
    source: Optional[SourceRecord] = None
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = stable_id("switch", self.family.value, self.layer,
                                "" if self.source is None else self.source.record_ref,
                                repr(self.node_id))


@dataclass
class Transformer:
    node_id: str
    capacity_kva: Optional[float]        # T_strn — None ≠ 0 (قاعده ۵)
    kind_raw: str = ""                   # T_noe_tera
    feeder_name: str = ""
    local_name: str = ""
    lv_term_registered: bool = False     # Phase 2 will attach LV network
    source: Optional[SourceRecord] = None
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = stable_id("transformer", "" if self.source is None else self.source.record_ref)


@dataclass
class LoadPt:
    """نقاط بار = نقاط ترانسفورماتورهای توزیع (بند ۷-۶ متن رسمی)."""
    node_id: str
    transformer_id: Optional[str] = None
    p_kw: Optional[float] = None         # None until Phase-3 load model
    q_kvar: Optional[float] = None
    category: str = ""                   # جدول ۱۲ دسته (شهری/روستایی/...)
    priority_weight: Optional[float] = None   # جدول ۱۲ — configurable
    data_source: str = "unassigned"      # measured | estimated | unassigned
    source: Optional[SourceRecord] = None
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = stable_id("load", self.node_id,
                                "" if self.transformer_id is None else self.transformer_id)


@dataclass
class Substation:
    name: str
    code: str = ""
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = stable_id("substation", self.name, self.code)


@dataclass
class TieConnection:
    """اتصال پشتیبان فیدرها — ثبت فقط با کلید اتوماسیون (جدول ۱۳ متن رسمی)."""
    feeder_a: str
    feeder_b: str
    switch_id: Optional[str] = None
    automation_capable: bool = False     # فقط اتصالات اتوماسیون در EP/TL شمرده می‌شوند
    status: str = "candidate"            # candidate | confirmed | rejected
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = stable_id("tie", self.feeder_a, self.feeder_b, str(self.switch_id))


# ---------------------------------------------------------------------------
# ظرف تجمیع‌کننده
# ---------------------------------------------------------------------------
@dataclass
class CanonicalNetwork:
    """In-memory canonical model produced by the assembler (Phase 1)."""
    project_name: str = ""
    nodes: list = dc_field(default_factory=list)
    branches: list = dc_field(default_factory=list)
    switches: list = dc_field(default_factory=list)
    transformers: list = dc_field(default_factory=list)
    loads: list = dc_field(default_factory=list)
    feeders: list = dc_field(default_factory=list)
    substations: list = dc_field(default_factory=list)
    ties: list = dc_field(default_factory=list)
    crs_definitions: list = dc_field(default_factory=list)
    layer_mappings: list = dc_field(default_factory=list)
    source_records: list = dc_field(default_factory=list)   # unique-kept
    stats: dict = dc_field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "project": self.project_name,
            "nodes": len(self.nodes),
            "branches": len(self.branches),
            "branches_excluded": sum(1 for b in self.branches if b.excluded_with_issue),
            "switches": len(self.switches),
            "transformers": len(self.transformers),
            "loads": len(self.loads),
            "feeders": len(self.feeders),
            "source_records": len(self.source_records),
            "stats": self.stats,
        }
