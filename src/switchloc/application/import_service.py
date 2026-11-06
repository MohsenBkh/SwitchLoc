# -*- coding: utf-8 -*-
"""ImportService — end-to-end import orchestration (Phase 1).

Flow (docs/ARCHITECTURE.md §۲):
  hash inputs → discover (multi-format) → suggest mapping → *explicit
  confirmation* → read → CRS resolve/transform → canonical assembly →
  QC → persist SQLite → re-hash inputs (GG-02 guarantee).

The confirmation step is deliberate: per main prompt §۵-۳ no automatic
mapping is ever final.  The caller supplies `confirm_fn`; without it the
service stops before reading and returns the suggestions (the UI wizard
of Phase 2 will plug in here — same contract).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field as dc_field
from datetime import datetime
from pathlib import Path

from ..domain.entities import CanonicalNetwork, StudyRunMeta
from ..gis.assemble import (AssembleContext, CanonicalAssembler,
                            DEFAULT_ORPHAN_RADIUS_M, DEFAULT_SNAP_TOL_M)
from ..gis.crs import CrsService
from ..gis.mapping.layer_mapping import LayerMappingService
from ..gis.readers.registry import discover_all
from ..persistence.store import ProjectStore
from ..validation.issues import (IssueLog, ValidationIssue, SEVERITY_ERROR,
                                 SEVERITY_INFO)
from ..validation.qc import QcReport, run_qc
from .. import APP_NAME, TAV_REFERENCE, __version__


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ImportSettings:
    project_name: str = "بدون نام"
    user: str = "unknown"
    snap_tol_m: float = DEFAULT_SNAP_TOL_M
    orphan_radius_m: float = DEFAULT_ORPHAN_RADIUS_M
    analysis_epsg: int | None = None       # None → majority of layers (D-01)
    out_db: str | None = None


@dataclass
class ImportResult:
    network: CanonicalNetwork
    issues: IssueLog
    report: QcReport
    suggestions: list
    mapping_service: LayerMappingService
    run_id: str | None
    db_path: str | None
    input_hashes: dict
    unchanged: bool

    @property
    def accepted(self) -> bool:
        return self.report.verdict == "PASS"


class ImportService:
    def __init__(self, settings: ImportSettings | None = None):
        self.settings = settings or ImportSettings()

    # ------------------------------------------------------------------
    def run(self, source, confirm_fn=None) -> ImportResult:
        st = self.settings
        issues = IssueLog()
        source = Path(source)
        if not source.exists():
            raise NotADirectoryError(str(source))

        # 1) input hashes (before) — GG-02
        files = sorted([p for p in (source.rglob("*") if source.is_dir()
                                    else [source]) if p.is_file()])
        hashes = {str(p): sha256_of(p) for p in files}

        # 2) discover across formats
        layers, reader_of = discover_all(source, issues)
        if not layers:
            issues.add(ValidationIssue(
                code="GIS-NO-LAYERS", severity=SEVERITY_ERROR,
                message_fa="هیچ لایه قابل خواندنی در مسیر ورودی یافت نشد.",
                source_file=str(source),
                impact_fa="ورود داده متوقف شد."))
            net = CanonicalNetwork(project_name=st.project_name)
            rep = run_qc(net.summary(), issues, st.project_name, {})
            return ImportResult(net, issues, rep, [], LayerMappingService(),
                                None, None, hashes, True)

        # 3) mapping suggestions + explicit confirmation
        mapping = LayerMappingService()
        suggestions = mapping.suggest(layers)
        if confirm_fn is None:
            rep = run_qc(CanonicalNetwork(project_name=st.project_name).summary(),
                         issues, st.project_name,
                         {li.name: li.feature_count for li in layers})
            return ImportResult(net := CanonicalNetwork(project_name=st.project_name),
                                issues, rep, suggestions, mapping,
                                None, None, hashes, True)
        for s in suggestions:
            li = next(x for x in layers if x.name == s.layer_name)
            mapping.confirm(li, s.slot_key, confirmed_by=st.user,
                            field_map=s.field_map)
        confirm_fn(suggestions, mapping, layers)   # final say of the user/engineer

        # 4) read every layer
        feats_by_layer: dict[str, list] = {}
        counts: dict[str, int] = {}
        for li in layers:
            feats = reader_of[li.name].read(li, issues)
            feats_by_layer[li.name] = feats
            counts[li.name] = li.feature_count if li.feature_count >= 0 else len(feats)

        # 5) assemble canonical model
        crs = CrsService(analysis_epsg=st.analysis_epsg)
        asm = CanonicalAssembler(issues, crs=crs, ctx=AssembleContext(
            snap_tol_m=st.snap_tol_m, orphan_radius_m=st.orphan_radius_m))
        net = asm.assemble(layers, feats_by_layer, mapping)
        net.project_name = st.project_name
        for s in net.source_records:            # carry hashes into traceability
            for path in hashes:
                if path.endswith((".shp", ".geojson", ".gpkg", ".xlsx", ".csv")) \
                        and Path(path).stem.split(".")[0].replace("@", ".") \
                        .startswith(s.layer.split("@")[0]):
                    s.file_path = path
                    s.file_sha256 = hashes[path]
                    break

        # 6) QC
        rep = run_qc(net.summary(), issues, st.project_name, counts)

        # 7) re-hash (GG-02) — inputs must be untouched
        after = {str(p): sha256_of(p) for p in files}
        unchanged = after == hashes
        if not unchanged:
            issues.add(ValidationIssue(
                code="GIS-INPUT-MODIFIED", severity=SEVERITY_ERROR,
                message_fa="فایل‌های ورودی در طول مطالعه تغییر کرده‌اند!",
                source_file=str(source),
                impact_fa="اصل عدم تغییر ورودی نقض شد؛ اجرا قابل اعتماد نیست."))

        # 8) persist
        run_id, db_path = None, None
        if st.out_db:
            store = ProjectStore(st.out_db)
            run_meta = StudyRunMeta(
                project_name=st.project_name,
                started_at=datetime.now().isoformat(timespec="seconds"),
                user=st.user, algo_version=f"switchloc {__version__}",
                tav_revision=TAV_REFERENCE,
                settings_snapshot={
                    "snap_tol_m": st.snap_tol_m,
                    "orphan_radius_m": st.orphan_radius_m,
                    "analysis_epsg": (st.analysis_epsg
                                      or (crs.analysis_crs.to_epsg()
                                          if crs.analysis_crs else None)),
                    "inverse_zero_policy": "confirmed(10) — TAV122 بند ۷-۷-۵",
                },
                input_hashes=hashes)
            run_id = store.save_network(net, issues, run_meta)
            store.close()
            db_path = str(st.out_db)

        return ImportResult(net, issues, rep, suggestions, mapping,
                            run_id, db_path, hashes, unchanged)
