# -*- coding: utf-8 -*-
"""SwitchLoc — مطالعات جایابی کلید و برنامه‌ریزی اتوماسیون شبکه توزیع برق.

Level-1 switch placement & automation planning for MV distribution
networks, per Tavanir directive TAV122-02/00.

Phase-5 scope (this drop — «گزارش‌ها و خروجی GIS»):
- reporting         : StudyModel + neutral content tree (single source of
                       truth), RTL Excel workbook (openpyxl), Persian RTL
                       Word report (python-docx, w:bidi/w:bidiVisual),
                       offline Persian PDF (ReportLab + arabic_reshaper +
                       python-bidi + bundled Vazirmatn, optional extras),
                       GeoJSON×3 + CSV crew sheet in WGS84 (RFC 7946)
- service           : ReportService — in-memory re-run + cross-check vs
                       the persisted placement run (mismatch ⇒ registered
                       issue, بند ۱۹ philosophy)
- cli               : + `python -m switchloc report <db>`
- ui.qt             : + Exports button on the Placement tab
- packaging         : fonts bundled (build_assets/fonts) + report extras
                       installed by BUILD.bat (requirements-report.txt)

Phase-3 scope (this drop — «بار و خاموشی»):
- reliability        : outage-list ingestion (A-08 cleaning, Jalali dates,
                       feeder mapping F1..F7), six-class rule classifier
                       (بند ۱۰ پرامپت مادر on the four official levels of
                       شکل ۵ — A-11), per-feeder λ/r matrix (U=λr/60, V-03)
                       + four official review-level tables, جدول ۱۲ load
                       priority model (configurable + settings_log)
- application        : + OutageService orchestration + Persian report
- persistence        : + outage_run/outage_event/outage_lambda_r tables
- cli                : + `python -m switchloc outages <xlsx>`
- packaging          : RUN.bat / BUILD.bat one-click launchers + PyInstaller
                       entry points (build_tools/)

Phase-2 scope (unchanged, docs/PHASE2_REPORT.md):
- topology          : NetworkGraph (edges split at device vertices — the
                      GeoGrid splice behaviour, re-implemented), normal-state
                      feeder tracing (بازسازی فیدرها), A-09 NO/Tie candidates
                      with explicit confirmation, زون‌بندی per تعریف ۵-۲۱
- scenarios         : base switching model + energized/de-energized
                      evaluation (پایه جدول ۱۵ و EP/TL فاز ۴)
- ui.map_renderer   : headless Matplotlib network map (D-04) + ui.qt PySide6
                      shell (optional — requirements-qt.txt)

Phase-1 scope (unchanged, docs/PHASE1_REPORT.md):
- domain            : canonical entities + deterministic ids (DATA_MODEL.md)
- gis.readers       : shapefile / geojson / gpkg / xlsx / csv readers + registry
- gis.crs           : metric analysis-CRS management, one-time transforms
- gis.snap          : metric-tolerance single-linkage snap (GG-06)
- gis.segmentation  : polyline split + registered-length distribution (GG-03)
- gis.assemble      : CanonicalAssembler (entities + SourceRecord chains)
- gis.mapping       : slot catalog + suggest→confirm layer/field mapping
- persistence       : SQLite project store (deterministic, reproducible)
- validation        : Issue model + QC engine/report (verdict: 0 open Error)
- level1.formulas   : audited TAV122-02/00 kernels (official anchors V-01..V-05)
"""

__version__ = "1.16.0"
APP_NAME = "SwitchLoc"
TAV_REFERENCE = "TAV122-02/00"
