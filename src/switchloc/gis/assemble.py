# -*- coding: utf-8 -*-
"""CanonicalAssembler — Feature stream → CanonicalNetwork (Phase 1).

Pipeline (docs/ARCHITECTURE.md §۲, decisions مصوب فاز صفر):
  1. CRS resolve/analysis-selection (metric, D-01) + one-time transforms;
  2. single-linkage metric snap of ALL line endpoints across layers
     (replaces GeoGrid decimal rounding — GG-06);
  3. polyline segmentation with registered-length distribution (GG-03);
  4. device splicing onto snapped nodes — devices on a mid-vertex of a
     line connect because that vertex became a segment endpoint (GG-05);
     ambiguous devices (2+ candidates in tolerance) are flagged, never
     guessed; orphans get their own node + distance-annotated issue;
  5. entities + SourceRecord chains; NOTHING dropped without an issue
     (main prompt §۲۲ «هیچ داده‌ای بی‌دلیل حذف نشود»).

Geometric crossing of two lines does NOT create a connection (GG-04) —
connectivity only arises from endpoint coincidence or a device on a
node; that is inherent here because only endpoints enter the snap.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field as dc_field

from .crs import CrsService, CrsInfo
from .mapping import field_catalog as fc
from .mapping.layer_mapping import LayerMappingService
from .mapping.slots import SLOTS
from .readers.base import Feature, LayerInfo
from .segmentation import split_polyline
from .snap import snap_points, ambiguous_device_candidates
from ..domain.entities import (Branch, CanonicalNetwork, CRSDefinition, Feeder,
                               LineSegment, LoadPt, Node, SourceRecord,
                               Substation, SwitchDev, Transformer)
from ..domain.enums import (BranchKind, NodeKind, SwitchFamily, SwitchState,
                            YesNoUnknown)
from ..validation.issues import (IssueLog, ValidationIssue,
                                 SEVERITY_ERROR, SEVERITY_INFO, SEVERITY_WARNING)
from ..logging_setup import get_logger

_log = get_logger("gis")

_PERSIAN_FIX = str.maketrans({"ي": "ی", "ك": "ک", "ة": "ه", "\u200c": " "})

DEFAULT_SNAP_TOL_M = 0.5
DEFAULT_ORPHAN_RADIUS_M = 5.0

_LINE_SLOT_TO_KIND = {
    "mv_line_aerial": BranchKind.LINE_AERIAL,
    "mv_line_underground": BranchKind.LINE_UNDERGROUND,
    "mv_jumper": BranchKind.JUMPER,
    "mv_line_network": BranchKind.LINE_MISC,
    "mv_line_misc": BranchKind.LINE_MISC,
}
_SWITCH_SLOT_FAMILY = {
    "switch_manual": SwitchFamily.DISCONNECTOR,
    "breaker": SwitchFamily.BREAKER,
    "recloser": SwitchFamily.RECLOSER,
    "sectionalizer": SwitchFamily.SECTIONALIZER,
    "fuse_cutout": SwitchFamily.FUSE_CUTOUT,
}


def normalize_feeder(name: str) -> str:
    """Normalize a feeder label (yeh/kaf unification, spacing, case)."""
    s = (name or "").translate(_PERSIAN_FIX).strip()
    s = re.sub(r"\s+", " ", s)
    return s.upper()


def _to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v))
    return float(m.group(0).replace(",", ".")) if m else None


def _state_enum(s: str) -> SwitchState:
    return {"in": SwitchState.IN_SERVICE, "out": SwitchState.OUT_OF_SERVICE}.get(
        s, SwitchState.UNKNOWN)


def _yesno_enum(s: str) -> YesNoUnknown:
    return {"yes": YesNoUnknown.YES, "no": YesNoUnknown.NO}.get(
        s, YesNoUnknown.UNKNOWN)


@dataclass
class AssembleContext:
    snap_tol_m: float = DEFAULT_SNAP_TOL_M
    orphan_radius_m: float = DEFAULT_ORPHAN_RADIUS_M


class CanonicalAssembler:
    """Builds the Phase-1 canonical model from confirmed mappings."""

    def __init__(self, issues: IssueLog, crs: CrsService | None = None,
                 ctx: AssembleContext | None = None):
        self.issues = issues
        self.crs = crs or CrsService()
        self.ctx = ctx or AssembleContext()
        self._source_records: dict[tuple, SourceRecord] = {}

    # ------------------------------------------------------------------
    def assemble(self, layers: list[LayerInfo],
                 feats_by_layer: dict[str, list[Feature]],
                 mapping: LayerMappingService) -> CanonicalNetwork:
        net = CanonicalNetwork()
        # --- confirmed mapping availability ----------------------------
        slot_of_layer: dict[str, str] = {}
        for li in layers:
            ent = mapping.confirmed.get(li.name)
            if ent is None:
                self.issues.add(ValidationIssue(
                    code="GIS-MAPPING-UNCONFIRMED", severity=SEVERITY_ERROR,
                    message_fa=f"لایه «{li.name}» نگاشت تأییدشده ندارد.",
                    source_file=li.path, layer=li.name,
                    suggestion_fa="نقش لایه را تأیید یا آن را از مطالعه حذف کنید.",
                    impact_fa="لایه وارد مدل canonical نمی‌شود."))
                continue
            if ent.enabled:
                slot_of_layer[li.name] = ent.slot_key
            else:
                self.issues.add(ValidationIssue(
                    code="GIS-LAYER-DISABLED", severity=SEVERITY_INFO,
                    message_fa=f"لایه «{li.name}» غیرفعال (disabled) است.",
                    source_file=li.path, layer=li.name,
                    impact_fa="طبق تأیید کاربر از مطالعه کنار گذاشته شد."))
            net.layer_mappings.append(ent)

        # --- CRS: collect + choose analysis -----------------------------
        infos: list[CrsInfo] = []
        for li in layers:
            if li.name not in slot_of_layer:
                continue
            info = self.crs.resolve(li.name, li.crs_wkt, self.issues)
            if info is not None:
                infos.append(info)
        analysis = self.crs.set_analysis_from_majority(infos, self.issues)
        if analysis is None:
            raise RuntimeError("CRS تحلیلی متری تعیین نشد؛ ورود داده متوقف شد.")
        for li in layers:                      # record final definitions
            rec = self.crs.definitions.get(li.name)
            if rec is not None:
                net.crs_definitions.append(CRSDefinition(
                    layer=li.name, crs_original=rec["crs_original"],
                    crs_analysis=rec["crs_analysis"] or f"EPSG:{analysis.to_epsg()}",
                    epsg=rec["epsg"], transformed=rec["transformed"],
                    transform_note=rec["transform_note"]))

        def xform(li_name: str, info: CrsInfo | None, pt: tuple):
            x, y = pt
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError("مختصات غیر عددی")
            if info is not None and not info.is_projected:
                return self.crs.to_analysis(li_name, x, y, info, self.issues)
            return x, y

        info_of_layer = {li.name: self.crs.definitions.get(li.name) for li in layers}
        crsinfo_of_layer = {}
        for li in layers:
            wkt = li.crs_wkt or (info_of_layer[li.name] or {}).get("crs_original", "")
            ci = CrsInfo.parse(wkt) if wkt else None
            crsinfo_of_layer[li.name] = ci

        # --- duplicate record ids ---------------------------------------
        self._dup_ids(feats_by_layer)

        # --- collect line endpoints across all line slots ----------------
        line_feats: list[tuple[str, Feature, str]] = []     # (layer, feat, slot)
        device_feats: list[tuple[str, Feature, str]] = []
        for li in layers:
            slot = slot_of_layer.get(li.name)
            if slot is None:
                continue
            for f in feats_by_layer.get(li.name, []):
                if slot in _LINE_SLOT_TO_KIND:
                    line_feats.append((li.name, f, slot))
                elif slot in SLOTS and SLOTS[slot].geometry == "point":
                    device_feats.append((li.name, f, slot))
                else:
                    self.issues.add(ValidationIssue(
                        code="GIS-SLOT-DEFERRED", severity=SEVERITY_INFO,
                        message_fa=f"نقش «{SLOTS[slot].label_fa}» در فاز ۱ فقط "
                                   f"ثبت می‌شود و وارد گراف نمی‌شود.",
                        source_file=li.path, layer=li.name,
                        record_id=f.record_id,
                        impact_fa="برای فازهای بعد (خازن/DG/پست) نگهداری شد."))

        endpoints: list[tuple[float, float]] = []
        ep_owner: list[tuple[str, int, int]] = []   # (layer, feat_idx, vertex_idx)
        for li_name, f, _slot in line_feats:
            ci = crsinfo_of_layer[li_name]
            for vi, pt in enumerate(f.points):
                try:
                    endpoints.append(xform(li_name, ci, pt))
                except (ValueError, Exception):     # noqa: BLE001 — flagged, not fatal
                    self.issues.add(ValidationIssue(
                        code="GIS-COORD-OUT-OF-RANGE", severity=SEVERITY_WARNING,
                        message_fa="رأس خط دارای مختصات نامعتبر است.",
                        source_file="", layer=li_name, record_id=f.record_id,
                        current_value=str(pt),
                        impact_fa="این رأس در snap شرکت نمی‌کند."))
                    endpoints.append((0.0, 0.0))
                ep_owner.append((li_name, id(f), vi))
        snap_res = snap_points(endpoints, self.ctx.snap_tol_m)

        # nodes from endpoint clusters
        node_by_key: dict[str, Node] = {}
        for key, centroid in snap_res.centroids.items():
            nd = Node(kind=NodeKind.JUNCTION, coord_original=None,
                      coord_snapped=centroid, cluster_key=key)
            node_by_key[key] = nd
            net.nodes.append(nd)

        # --- branches ----------------------------------------------------
        for li_name, f, slot in line_feats:
            ci = crsinfo_of_layer[li_name]
            src = self._source(li_name, f)
            if len(f.points) < 2:
                net.branches.append(Branch(
                    kind=_LINE_SLOT_TO_KIND[slot], node_a="", node_b="",
                    length_registered_m=_to_float(
                        f.attributes.get(self._role(mapping, li_name, "length"))),
                    length_geometric_m=0.0, segments=[], feeder_name=f.feeder,
                    source=src, excluded_with_issue=True))
                continue
            pts = []
            n_bad_vertices = 0
            for pt in f.points:
                try:
                    pts.append(xform(li_name, ci, pt))
                except Exception as exc:        # noqa: BLE001
                    # keep the raw vertex (topology still builds) but make
                    # the data defect VISIBLE — never silent
                    n_bad_vertices += 1
                    _log.warning("vertex transform failed layer=%s rec=%s: %s",
                                 li_name, f.record_id, exc)
                    pts.append(pt)
            if n_bad_vertices:
                self.issues.add(ValidationIssue(
                    code="GIS-VERTEX-TRANSFORM-FAILED",
                    severity=SEVERITY_WARNING,
                    message_fa=(f"{n_bad_vertices} رأس خط به CRS تحلیل تبدیل "
                                "نشد؛ مختصات اصلی نگه داشته شد."),
                    source_file="", layer=li_name, record_id=f.record_id,
                    suggestion_fa="CRS لایه را بررسی/تعیین کنید.",
                    impact_fa="طول هندسی و اتصال این خط ممکن است نادرست باشد."))
            reg_len = _to_float(f.attributes.get(self._role(mapping, li_name, "length")))
            segs, geo_len = split_polyline(pts, reg_len)
            if not reg_len or reg_len <= 0:
                self.issues.add(ValidationIssue(
                    code="DATA-ASSUMED-LENGTH", severity=SEVERITY_INFO,
                    message_fa="طول ثبت‌شده موجود نبود؛ طول هندسی رئوس ملاک شد.",
                    source_file="", layer=li_name, record_id=f.record_id,
                    current_value=f"geometric={geo_len:.2f} m",
                    impact_fa="طول مسیر از هندسه استخراج شد (فرض ثبت‌شده)."))
            elif abs(geo_len - reg_len) > max(1.0, 0.02 * reg_len):
                self.issues.add(ValidationIssue(
                    code="GIS-LENGTH-MISMATCH", severity=SEVERITY_INFO,
                    message_fa=f"طول هندسی ({geo_len:.1f}م) با طول ثبت‌شده "
                               f"({reg_len:.1f}م) اختلاف معنادار دارد.",
                    source_file="", layer=li_name, record_id=f.record_id,
                    impact_fa="هر دو مقدار حفظ شد؛ محاسبات طول از مقدار ثبت‌شده "
                              "با توزیع تناسبی استفاده می‌کند."))
            ka = snap_res.point_keys[self._ep_index(li_name, id(f), 0, ep_owner)]
            kb = snap_res.point_keys[self._ep_index(li_name, id(f), len(pts) - 1, ep_owner)]
            net.branches.append(Branch(
                kind=_LINE_SLOT_TO_KIND[slot], node_a=ka, node_b=kb,
                length_registered_m=reg_len, length_geometric_m=geo_len,
                segments=[LineSegment(a=s.a, b=s.b, length_m=s.length_m)
                          for s in segs],
                feeder_name=f.feeder,
                conductor=fc.s(f.attributes.get(self._role(mapping, li_name, "conductor"))),
                section_mm2=_to_float(f.attributes.get(self._role(mapping, li_name, "section"))),
                installation=fc.s(f.attributes.get(self._role(mapping, li_name, "installation"))),
                source=src))

        # duplicate-line detection (same clusters + similar length)
        self._dup_lines(net)

        # --- devices ------------------------------------------------------
        centroid_items = list(snap_res.centroids.items())
        for li_name, f, slot in device_feats:
            ci = crsinfo_of_layer[li_name]
            src = self._source(li_name, f)
            pt = None
            if f.points:
                try:
                    pt = xform(li_name, ci, f.points[0])
                except Exception:               # noqa: BLE001
                    self.issues.add(ValidationIssue(
                        code="GIS-COORD-OUT-OF-RANGE", severity=SEVERITY_WARNING,
                        message_fa="مختصات تجهیز نامعتبر است.",
                        source_file="", layer=li_name, record_id=f.record_id,
                        impact_fa="تجهیز بدون اتصال ثبت می‌شود."))
                    pt = None
            node_id = ""
            if pt is None:
                node_id = self._device_node(net, NodeKind.DEVICE_HV, None, f.feeder)
            else:
                cands = ambiguous_device_candidates(pt, snap_res.centroids,
                                                    self.ctx.snap_tol_m)
                if not cands:
                    # orphan: own node + distance to nearest cluster
                    nd = self._device_node(net, NodeKind.DEVICE_HV, pt, f.feeder)
                    node_id = nd.id
                    if centroid_items:
                        dmin, _ = min(
                            (math.dist(pt, c), k) for k, c in centroid_items)
                        self.issues.add(ValidationIssue(
                            code="GIS-ORPHAN-DEVICE", severity=SEVERITY_WARNING,
                            message_fa=f"تجهیز در {dmin:.1f} متری نزدیک‌ترین گره "
                                       f"خط است (خارج از تلورانس snap).",
                            source_file="", layer=li_name, record_id=f.record_id,
                            current_value=f"({pt[0]:.2f}, {pt[1]:.2f})",
                            suggestion_fa="موقعیت تجهیز یا تلورانس snap بازبینی شود.",
                            impact_fa="تجهیز ایزوله ثبت شد و در توپولوژی اثری ندارد."))
                else:
                    if len(cands) > 1:
                        self.issues.add(ValidationIssue(
                            code="GIS-AMBIGUOUS-SNAP", severity=SEVERITY_WARNING,
                            message_fa=f"تجهیز به {len(cands)} گره در محدوده "
                                       f"تلورانس می‌رسد؛ به نزدیک‌ترین متصل شد.",
                            source_file="", layer=li_name, record_id=f.record_id,
                            current_value=", ".join(cands[:5]),
                            suggestion_fa="نقاط مبهم در نقشه بازبینی شود.",
                            impact_fa="اتصال به نزدیک‌ترین کاندید (ثبت‌شده)."))
                    best = min(cands, key=lambda k: math.dist(pt, snap_res.centroids[k]))
                    node_id = node_by_key[best].id
            self._make_device_entity(net, li_name, slot, f, node_id, mapping, src)

        # --- feeders -------------------------------------------------------
        self._collect_feeders(net, feats_by_layer)
        net.source_records = list(self._source_records.values())
        net.project_name = ""
        net.stats = {
            "line_features": len(line_feats),
            "device_features": len(device_feats),
            "endpoint_points": len(endpoints),
            "clusters": len(snap_res.centroids),
        }
        return net

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _ep_index(li_name, fid, vi, ep_owner):
        return ep_owner.index((li_name, fid, vi))

    def _source(self, layer: str, f: Feature) -> SourceRecord:
        key = (layer, f.record_index)
        if key not in self._source_records:
            self._source_records[key] = SourceRecord(
                file_path="", file_sha256="", layer=layer,
                record_ref=f.record_id or f"idx:{f.record_index}",
                geometry_ref=f"points[{len(f.points)}]")
        return self._source_records[key]

    def _role(self, mapping: LayerMappingService, layer: str, role: str) -> str:
        ent = mapping.confirmed.get(layer)
        if ent is None:
            return ""
        return ent.field_map.get(role, "")

    def _device_node(self, net: CanonicalNetwork, kind: NodeKind,
                     coord: tuple | None, feeder: str) -> Node:
        nd = Node(kind=kind, coord_original=coord, coord_snapped=coord,
                  feeder_name=feeder)
        net.nodes.append(nd)
        return nd

    def _make_device_entity(self, net: CanonicalNetwork, li_name: str, slot: str,
                            f: Feature, node_id: str,
                            mapping: LayerMappingService, src: SourceRecord):
        fam = _SWITCH_SLOT_FAMILY.get(slot)
        if fam is not None:
            net.switches.append(SwitchDev(
                family=fam, node_id=node_id,
                switch_type_raw=fc.first_value(f.attributes, fc.SWITCH_TYPE_FIELDS),
                current_state=_state_enum(f.service_state),
                rating_a=_to_float(f.attributes.get(
                    self._role(mapping, li_name, "rated_current"))),
                remote_controlled=_yesno_enum(f.remote_controlled),
                local_name=fc.first_value(f.attributes, fc.LOCAL_NAME_FIELDS),
                feeder_name=f.feeder, layer=li_name, source=src))
            if f.service_state == "unknown":
                self.issues.add(ValidationIssue(
                    code="GIS-SWITCH-STATE-UNKNOWN", severity=SEVERITY_WARNING,
                    message_fa="وضعیت سرویس کلید نامشخص است (T__outserv خالی).",
                    source_file="", layer=li_name, record_id=f.record_id,
                    impact_fa="در سناریوها با وضعیت «نامشخص» لحاظ می‌شود.",
                    ))
        elif slot == "transformer":
            cap = _to_float(f.attributes.get(self._role(mapping, li_name, "capacity")))
            tr = Transformer(node_id=node_id, capacity_kva=(cap if cap else None),
                             kind_raw=fc.s(f.attributes.get("T_noe_tera")),
                             feeder_name=f.feeder,
                             local_name=fc.first_value(f.attributes, fc.LOCAL_NAME_FIELDS),
                             source=src)
            if not cap:
                self.issues.add(ValidationIssue(
                    code="GIS-TRANSFORMER-NO-CAPACITY", severity=SEVERITY_WARNING,
                    message_fa="ظرفیت ترانس (T_strn) موجود نیست یا صفر است.",
                    source_file="", layer=li_name, record_id=f.record_id,
                    impact_fa="ظرفیت None نگه داشته شد؛ صفر فرض نشد (قاعده ۵-۵)."))
            net.transformers.append(tr)
            net.loads.append(LoadPt(node_id=node_id, transformer_id=tr.id,
                                     data_source="unassigned", source=src))
        elif slot == "source_feeder":
            nd = self._device_node(net, NodeKind.SOURCE,
                                   None if not f.points else tuple(f.points[0]),
                                   f.feeder)
            net.substations.append(Substation(
                name=fc.first_value(f.attributes, fc.LOCAL_NAME_FIELDS) or li_name))
        else:
            self.issues.add(ValidationIssue(
                code="GIS-SLOT-DEFERRED", severity=SEVERITY_INFO,
                message_fa=f"نقش «{SLOTS[slot].label_fa}» در فاز ۱ ثبت می‌شود.",
                source_file="", layer=li_name, record_id=f.record_id,
                impact_fa="مدیریت کامل این نقش در فازهای بعدی است."))

    def _dup_ids(self, feats_by_layer: dict[str, list[Feature]]):
        for layer, feats in feats_by_layer.items():
            seen: dict[str, int] = {}
            dup: list[str] = []
            for f in feats:
                if not f.record_id:
                    continue
                seen[f.record_id] = seen.get(f.record_id, 0) + 1
                if seen[f.record_id] == 2:
                    dup.append(f.record_id)
            if dup:
                self.issues.add(ValidationIssue(
                    code="GIS-DUP-ID", severity=SEVERITY_WARNING,
                    message_fa=f"{len(dup)} شناسه تکراری در لایه «{layer}».",
                    layer=layer, current_value=", ".join(dup[:10]),
                    suggestion_fa="شناسه‌های تکراری در GIS اصلاح شود.",
                    impact_fa="ردیابی رکوردهای تکراری با شماره ردیف متمایز می‌شود.",
                    meta={"examples": dup[:20]}))

    def _dup_lines(self, net: CanonicalNetwork):
        seen: dict[tuple, Branch] = {}
        for br in net.branches:
            if br.excluded_with_issue or not br.node_a or not br.node_b:
                continue
            key = tuple(sorted((br.node_a, br.node_b))) + (
                round(br.length_registered_m or 0.0, 0),)
            other = seen.get(key)
            if other is not None:
                self.issues.add(ValidationIssue(
                    code="GIS-DUP-LINE", severity=SEVERITY_WARNING,
                    message_fa="دو خط با گره‌های یکسان و طول مشابه ثبت شده است.",
                    layer=br.source.layer if br.source else "",
                    record_id=br.source.record_ref if br.source else "",
                    current_value=f"{key}",
                    impact_fa="در گراف هر دو حفظ می‌شوند؛ نیاز به بازبینی GIS دارد.",
                    meta={"other": other.source.record_ref if other.source else ""}))
            else:
                seen[key] = br

    def _collect_feeders(self, net: CanonicalNetwork, feats_by_layer):
        variants: dict[str, set] = defaultdict(set)
        for feats in feats_by_layer.values():
            for f in feats:
                if f.feeder:
                    variants[normalize_feeder(f.feeder)].add(f.feeder)
        for norm, raws in sorted(variants.items()):
            net.feeders.append(Feeder(name=norm, raw_name=sorted(raws)[0]))
            if len(raws) > 1:
                self.issues.add(ValidationIssue(
                    code="GIS-FEEDER-NAME-CONFLICT", severity=SEVERITY_INFO,
                    message_fa=f"نام فیدر «{norm}» با {len(raws)} نگارش متفاوت ثبت شده است.",
                    current_value="؛ ".join(sorted(raws)),
                    suggestion_fa="نام‌گذاری فیدرها در GIS یکسان‌سازی شود.",
                    impact_fa="نام نرمال‌شده ملاک تجمیع است؛ نگارش‌ها حفظ شدند.",
                    meta={"variants": sorted(raws)}))
