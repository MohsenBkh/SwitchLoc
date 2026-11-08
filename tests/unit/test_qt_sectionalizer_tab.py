# -*- coding: utf-8 -*-
"""Qt offscreen: تب «بهینه‌سازی سکشنالایزر و کاهش EENS»."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

import pytest                                        # noqa: E402

try:
    from PySide6 import QtWidgets                    # noqa: E402
    HAS_QT = True
except ImportError:                                  # pragma: no cover
    HAS_QT = False

pytestmark = pytest.mark.skipif(
    not HAS_QT, reason="PySide6.QtWidgets is not importable")


@pytest.fixture()
def app():
    if QtWidgets.QApplication.instance() is None:
        QtWidgets.QApplication([])
    yield


def _tab():
    from switchloc.ui.qt.sectionalizer_tab import make_sectionalizer_tab
    return make_sectionalizer_tab(None)


def _engine_result():
    from switchloc.reliability.sectionalizer import (SectionalizerEngine,
                                                     SectionalizerSettings)
    from test_sectionalizer_engine import line_network

    net, graph, traces, node_load = line_network(n_nodes=8, step=200.0)
    study = SectionalizerEngine(SectionalizerSettings(max_sectionalizers=2)) \
        .run(graph, traces, node_load, net=net,
             failure_rates={"F1": 30.0}, failure_rate_source="outage")

    class Res:
        def __init__(self, study_):
            self.study = study_
            self.warnings = []
            self.report_md = None

        @property
        def markdown(self):
            return self.study.to_markdown()

    return Res(study), study


def test_tab_exposes_settings_and_defaults(app):
    tab = _tab()
    s = tab.settings()
    assert s["failure_rate_source"] == "outage"
    assert s["total_failure_rate_per_year"] == pytest.approx(30.0)
    assert s["max_sectionalizers"] >= 1
    assert s["use_existing_switches"] is True
    assert 0.0 < s["max_downstream_load_ratio"] <= 1.0
    assert s["restoration_model"] in {"uniform", "directional"}


def test_settings_roundtrip(app):
    tab = _tab()
    tab.apply_settings({
        "failure_rate_source": "configured",
        "total_failure_rate_per_year": 42.5,
        "repair_time_min": 61.0,
        "restoration_time_min": 15.0,
        "max_sectionalizers": 4,
        "min_candidate_depth": 2,
        "max_downstream_load_ratio": 0.55,
        "restoration_model": "directional",
        "use_existing_switches": False,
    })
    s = tab.settings()
    # «منبع λ/r = configured» یعنی روش دستی (کاربر مقادیر را وارد می‌کند)
    assert s["failure_rate_source"] == "configured"
    assert s["method"] == "manual"
    assert s["total_failure_rate_per_year"] == pytest.approx(42.5)
    assert s["max_sectionalizers"] == 4
    assert s["min_candidate_depth"] == 2
    assert s["max_downstream_load_ratio"] == pytest.approx(0.55)
    assert s["restoration_model"] == "uniform"   # روش دستی: بدون مدل بازیابی
    assert s["use_existing_switches"] is False
    # مقدار ناشناخته/تهی نباید ویجت را بشکند
    tab.apply_settings(None)
    tab.apply_settings({"unknown_key": 1})
    assert tab.settings()["max_sectionalizers"] == 4


def test_run_and_settings_callbacks_fire(app):
    tab = _tab()
    seen = {}
    tab.on_run = lambda settings: seen.setdefault("run", settings)
    tab.on_settings_changed = lambda settings: seen.update(changed=settings)
    tab.btn_run.click()
    assert seen["run"]["max_sectionalizers"] == tab.settings()["max_sectionalizers"]
    tab.sp_max.setValue(5)
    assert seen["changed"]["max_sectionalizers"] == 5
    tab.sp_repair.setValue(90.0)
    assert seen["changed"]["repair_time_min"] == pytest.approx(90.0)
    tab.cmb_method.setCurrentIndex(tab.cmb_method.findData("directional"))
    assert seen["changed"]["restoration_model"] == "directional"
    assert seen["changed"]["method"] == "directional"
    tab.chk_existing.setChecked(False)
    assert seen["changed"]["use_existing_switches"] is False


def test_busy_disables_run_button(app):
    tab = _tab()
    tab.set_busy(True, "در حال اجرا…")
    assert not tab.btn_run.isEnabled()
    assert "اجرا" in tab.status.text()
    tab.set_busy(False)
    assert tab.btn_run.isEnabled()


def test_show_result_fills_tables_and_enables_map(app):
    tab = _tab()
    res, study = _engine_result()
    tab.show_result(res)
    summary = tab.summary_table
    detail = tab.detail_table
    assert summary.rowCount() == len(study.feeders)
    assert summary.item(0, 0).text() == "F1"
    assert detail.rowCount() == len(study.candidate_rows())
    # نشانگر ردیف انتخاب‌شده «●» است (✔ در برخی فونت‌ها tofu می‌شد)
    marks = [detail.item(i, 2).text().startswith("●")
             for i in range(detail.rowCount())]
    assert sum(marks) == len(selected_ids := [c.node for f in study.feeders
                                              if f.best for c in f.best.selected])
    # سرصفحهٔ گزارش دقیقاً نوع مطالعه را می‌گوید (v1.15)
    text = tab.panel.toPlainText()
    assert "مطالعهٔ جایابی بهینهٔ کلید و کاهش EENS" in text
    assert "نوع مطالعه" in text and "نوع EENS" in text
    selected = tab.selected_nodes()
    assert selected and all(isinstance(n, str) for n in selected)
    assert tab.btn_map.isEnabled()

    got = {}
    tab.on_show_map = lambda nodes: got.setdefault("nodes", nodes)
    tab.btn_map.click()
    assert got["nodes"] == selected


def test_show_persisted_restores_tables_from_kv_payload(app):
    tab = _tab()
    res, study = _engine_result()
    tab.show_persisted({"markdown": "گزارش ذخیره‌شده",
                        "study": study.as_dict()})
    assert tab.summary_table.rowCount() == len(study.feeders)
    assert tab.summary_table.item(0, 0).text() == "F1"
    assert tab.panel.toPlainText() == "گزارش ذخیره‌شده"
    assert tab.selected_nodes()
    assert tab.btn_map.isEnabled()


def test_show_persisted_tolerates_empty_payload(app):
    tab = _tab()
    tab.show_persisted(None)
    assert tab.summary_table.rowCount() == 0
    assert not tab.btn_map.isEnabled()
