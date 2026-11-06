# -*- coding: utf-8 -*-
"""Tabular reader for Excel (.xlsx) and CSV — attribute-only layers.

Use cases: لیست خاموشی‌ها، جداول اولویت بار، کتابخانه نوع تجهیزات.
Geometry-less features are legal; they simply cannot enter topology and
any attempt is flagged downstream by the assembler/QC.
"""
from __future__ import annotations

import csv
from pathlib import Path

from ...validation.issues import (IssueLog, ValidationIssue,
                                  SEVERITY_ERROR, SEVERITY_INFO,
                                  SEVERITY_WARNING)
from ..mapping import field_catalog as fc
from .base import Feature, LayerInfo
from ...logging_setup import get_logger

_log = get_logger("gis")


def _cell(v):
    if v is None:
        return ""
    return v


class TabularReader:
    """Excel/CSV reader; each sheet (or file) becomes one layer."""
    format_name = "tabular"

    def discover(self, source) -> list[LayerInfo]:
        path = Path(source)
        if path.is_file():
            files = [path]
        else:
            files = sorted(list(path.rglob("*.xlsx")) + list(path.rglob("*.csv")))
        layers: list[LayerInfo] = []
        for f in files:
            suf = f.suffix.lower()
            if suf == ".csv":
                layers.append(self._discover_csv(f))
            elif suf == ".xlsx":
                layers.extend(self._discover_xlsx(f))
        return layers

    def _discover_csv(self, f: Path) -> LayerInfo:
        li = LayerInfo(name=f.stem, path=str(f), geometry_type="TABULAR")
        try:
            with open(f, encoding="utf-8-sig", newline="") as fh:
                rdr = csv.reader(fh)
                header = next(rdr, [])
                li.fields = [h.strip() for h in header]
                li.feature_count = sum(1 for _ in rdr)
        except Exception as _exc:  # noqa: BLE001
            _log.warning("tabular_reader.py: recoverable error: %s", _exc)
            li.feature_count = -1
        return li

    def _discover_xlsx(self, f: Path) -> list[LayerInfo]:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        except Exception as _exc:  # noqa: BLE001
            _log.warning("tabular_reader.py: recoverable error: %s", _exc)
            return [LayerInfo(name=f.stem, path=str(f), feature_count=-1)]
        out = []
        for ws in wb.worksheets:
            li = LayerInfo(name=ws.title, path=str(f), geometry_type="TABULAR")
            rows = ws.iter_rows(min_row=1, max_row=1, values_only=True)
            header = next(rows, None)
            li.fields = [str(h).strip() if h is not None else "" for h in (header or [])]
            li.feature_count = max(0, (ws.max_row or 1) - 1)
            out.append(li)
        wb.close()
        return out

    # -- reading ------------------------------------------------------------
    def read(self, layer: LayerInfo, issues: IssueLog | None = None) -> list[Feature]:
        issues = issues or IssueLog()
        p = Path(layer.path)
        try:
            if p.suffix.lower() == ".csv":
                rows, fields = self._read_csv(p)
            else:
                rows, fields = self._read_xlsx(p, layer.name)
        except Exception as e:  # noqa: BLE001
            issues.add(ValidationIssue(
                code="GIS-LAYER-UNREADABLE", severity=SEVERITY_ERROR,
                message_fa=f"جدول «{layer.name}» قابل خواندن نیست: {e}",
                source_file=layer.path, layer=layer.name,
                impact_fa="این جدول از مطالعه کنار گذاشته می‌شود."))
            return []
        if fields != layer.fields and layer.fields:
            issues.add(ValidationIssue(
                code="DATA-COLUMNS-CHANGED", severity=SEVERITY_INFO,
                message_fa="ستون‌های جدول نسبت به زمان شناسایی تغییر کرده‌اند.",
                source_file=layer.path, layer=layer.name,
                impact_fa="نگاشت فیلدها باید مجدداً تأیید شود."))
        empty_rows = 0
        feats: list[Feature] = []
        for i, row in enumerate(rows):
            rec = {fields[j] if j < len(fields) else f"col{j}": _cell(v)
                   for j, v in enumerate(row)}
            if all((str(v).strip() == "" if not isinstance(v, str) else v.strip() == "")
                   for v in rec.values()):
                empty_rows += 1
                continue                     # skipped + reported once below
            rid = fc.record_id(rec)
            if not rid:
                issues.add(ValidationIssue(
                    code="GIS-EMPTY-ID", severity=SEVERITY_WARNING,
                    message_fa="ردیف بدون شناسه (T_MapID/OBJECTID حاضر نیست).",
                    source_file=layer.path, layer=layer.name, record_id=str(i),
                    impact_fa="ردیابی تا منبع دشوار می‌شود."))
            feats.append(Feature(
                layer=layer.name, record_index=i, record_id=rid,
                feeder=fc.feeder_name(rec), service_state="unknown",
                remote_controlled="unknown", attributes=rec, points=[],
                crs_wkt=""))
        if empty_rows:
            issues.add(ValidationIssue(
                code="DATA-OUTAGE-EMPTY-ROW", severity=SEVERITY_INFO,
                message_fa=f"{empty_rows} ردیف تماماً خالی صرف‌نظر شد.",
                source_file=layer.path, layer=layer.name,
                impact_fa="ردیف‌های خالی در گزارش پاک‌سازی داده ثبت می‌شوند."))
        return feats

    @staticmethod
    def _read_csv(p: Path):
        with open(p, encoding="utf-8-sig", newline="") as fh:
            rdr = csv.reader(fh)
            header = [h.strip() for h in next(rdr, [])]
            return list(rdr), header

    @staticmethod
    def _read_xlsx(p: Path, sheet: str):
        import openpyxl
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        try:
            ws = wb[sheet] if sheet in wb.sheetnames else wb.worksheets[0]
            rows = list(ws.iter_rows(values_only=True))
        finally:
            wb.close()
        if not rows:
            return [], []
        header = [str(h).strip() if h is not None else "" for h in rows[0]]
        return rows[1:], header
