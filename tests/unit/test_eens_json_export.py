# -*- coding: utf-8 -*-
"""JSON export for the complete EENS study shown in the UI report panel."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from switchloc.reporting.eens_report import export_eens_json


def test_export_eens_json_preserves_markdown_and_structured_study(tmp_path):
    markdown = "# گزارش EENS\n\n| فیدر | EENS پایه |\n|---|---:|\n| F1 | 12.5 |"
    payload = {
        "algo_version": "SwitchLoc test",
        "settings": {"method": "uniform"},
        "markdown": markdown,
        "study": {
            "settings": {"studied_feeders": ["F1"]},
            "feeders": [{"feeder_key": "F1", "baseline_eens_kwh": 12500.0}],
        },
    }
    path = tmp_path / "exports" / "sectionalizer_eens_report.json"

    returned = export_eens_json(payload, str(path))

    assert returned == str(path)
    assert path.is_file()
    exported = json.loads(path.read_text(encoding="utf-8"))
    assert exported == payload
    assert exported["markdown"] == markdown
    assert exported["study"]["feeders"][0]["feeder_key"] == "F1"


def test_export_eens_json_rejects_missing_study(tmp_path):
    with pytest.raises(ValueError, match="مطالعهٔ EENS معتبر"):
        export_eens_json({"markdown": "فقط متن"}, str(tmp_path / "bad.json"))


def test_report_service_exposes_eens_json_format(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from switchloc.reporting.model import StudyModel
    from switchloc.reporting.service import ExportSettings, ReportService

    payload = {
        "markdown": "# گزارش کامل EENS",
        "study": {"settings": {"method": "uniform"}, "feeders": [{"feeder_key": "F1"}]},
    }
    monkeypatch.setattr(
        ReportService, "_load_eens_study",
        staticmethod(lambda _db, _issues: payload))
    monkeypatch.setattr(StudyModel, "feeder_table", lambda _self: [])
    result = ReportService(ExportSettings(
        out_dir=str(tmp_path / "exports"), formats=("eens_json",),
        make_map=False)).run(
            net=SimpleNamespace(project_name="پروژهٔ آزمون"),
            topo=object(), placement=object())

    assert result.verdict == "PASS"
    assert result.paths["eens_json"].endswith("sectionalizer_eens_report.json")
    exported = json.loads(Path(result.paths["eens_json"]).read_text(encoding="utf-8"))
    assert exported == payload
