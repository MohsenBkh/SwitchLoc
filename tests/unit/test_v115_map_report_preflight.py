# -*- coding: utf-8 -*-
"""v1.15 — نقشه (فیوز پنهان، پنجرهٔ تنظیمات، شعاع اثر)، گزارش بر اساس نوع
مطالعه، بازبینی ورودی‌ها و رفع باگ λ/r در مسیر رابط کاربری."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import matplotlib
matplotlib.use("Agg")

import pytest

from switchloc.topology.graph import NetworkGraph
from switchloc.topology.tracing import TracingEngine, TracingPolicy
from switchloc.topology.zones import ZoneBuilder
from switchloc.ui.map_renderer import NetworkMapRenderer
from switchloc.ui.map_style import MapStyle
from switchloc.validation.issues import IssueLog
from switchloc.domain.enums import SwitchFamily

from conftest import NetBuilder


# ---------------------------------------------------------------------------
# ۱) نقشه: فیوزها پیش‌فرض پنهان، شعاع اثر ۵۰۰۰ و بدون سقف
# ---------------------------------------------------------------------------
def test_map_style_defaults_hide_fuses_and_use_5000m_radius():
    st = MapStyle()
    assert st.show_fuse_cutouts is False, "فیوزها باید پیش‌فرض پنهان باشند"
    assert st.outage_heat_radius_m == 5000.0


def test_map_style_roundtrip_keeps_fuse_flag_and_radius():
    st = MapStyle.from_dict({"show_fuse_cutouts": True,
                             "outage_heat_radius_m": 12000})
    assert st.show_fuse_cutouts is True
    assert st.outage_heat_radius_m == 12000.0
    # بدون سقف: مقدار بسیار بزرگ هم پذیرفته می‌شود
    st2 = MapStyle.from_dict({"outage_heat_radius_m": 250000})
    assert st2.outage_heat_radius_m == 250000.0


def _renderer_with_fuse(style=None):
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    b.switch(50, 0, family=SwitchFamily.FUSE_CUTOUT)
    b.transformer(100, 0, feeder="F1")
    g = NetworkGraph.from_network(b.net, IssueLog())
    traces = TracingEngine(g, b.net, TracingPolicy()).trace_all(IssueLog())
    zones = ZoneBuilder(g, b.net, traces).build(IssueLog())
    return NetworkMapRenderer(g, traces=traces, zones=zones,
                              switches={s.id: s for s in b.net.switches},
                              style=style)


def _drawn(renderer, hidden="__default__"):
    import matplotlib.pyplot as plt
    fig = plt.figure()
    try:
        if hidden == "__default__":
            renderer.render_into(fig)
        else:
            renderer.render_into(fig, hidden_switch_ids=hidden)
        return set(renderer._drawn)                 # noqa: SLF001
    finally:
        plt.close(fig)


def test_renderer_hides_fuse_cutouts_by_default():
    assert "device_FCT" not in _drawn(_renderer_with_fuse())


def test_renderer_shows_fuses_when_style_enables_them():
    st = MapStyle.default_for(feeders=["F1"])
    st.show_fuse_cutouts = True
    assert "device_FCT" in _drawn(_renderer_with_fuse(style=st))


def test_renderer_respects_explicit_hidden_list():
    """نقشهٔ تعاملی خودش فهرست پنهان را می‌دهد؛ پیش‌فرض دوباره اعمال نشود."""
    assert "device_FCT" in _drawn(_renderer_with_fuse(), hidden=set())


# ---------------------------------------------------------------------------
# ۲) پنجرهٔ تنظیمات نمایشی: دو باکس کنار هم + وسط‌چین + دکمهٔ فیوز
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


def test_map_style_dialog_outage_tab_has_two_side_by_side_boxes(qapp):
    from PySide6.QtWidgets import QSplitter, QTabWidget

    from switchloc.ui.qt.map_style_dialog import make_map_style_dialog

    st = MapStyle.default_for(feeders=["F1", "F2"])
    dlg = make_map_style_dialog(None, ["F1", "F2"], st,
                                {"پیش‌فرض": st.as_dict()}, "پیش‌فرض")
    tabs = dlg.findChildren(QTabWidget)[0]
    titles = [tabs.tabText(i) for i in range(tabs.count())]
    assert "خاموشی‌ها" in titles
    page = tabs.widget(titles.index("خاموشی‌ها"))
    splits = page.findChildren(QSplitter)
    assert splits, "تب خاموشی‌ها باید دو باکس کنار هم داشته باشد"
    assert splits[0].count() == 2
    from PySide6.QtCore import Qt
    assert splits[0].orientation() == Qt.Orientation.Horizontal


def test_map_style_dialog_heat_radius_default_and_no_cap(qapp):
    from PySide6.QtWidgets import QDoubleSpinBox

    from switchloc.ui.qt.map_style_dialog import make_map_style_dialog

    st = MapStyle.default_for(feeders=["F1"])
    dlg = make_map_style_dialog(None, ["F1"], st, {}, "پیش‌فرض")
    big = [s for s in dlg.findChildren(QDoubleSpinBox)
           if s.maximum() >= 1e8]
    assert big, "شعاع اثر باید بدون سقف باشد"
    assert any(abs(s.value() - 5000.0) < 1e-6 for s in big)
    assert big[0].maximum() >= 1e9


def test_map_style_dialog_is_fitted_and_centered_on_screen(qapp):
    from switchloc.ui.qt.map_style_dialog import (fit_dialog_to_screen,
                                                  make_map_style_dialog)

    st = MapStyle.default_for(feeders=["F1"])
    dlg = make_map_style_dialog(None, ["F1"], st, {}, "پیش‌فرض")
    screen = dlg.screen()
    if screen is None:                       # محیط بدون صفحهٔ واقعی
        pytest.skip("no screen in this environment")
    avail = screen.availableGeometry()
    dlg.resize(avail.width() + 400, avail.height() + 400)
    fit_dialog_to_screen(dlg)
    assert dlg.width() <= avail.width()
    assert dlg.height() <= avail.height()
    cx = dlg.x() + dlg.width() // 2
    cy = dlg.y() + dlg.height() // 2
    assert abs(cx - avail.center().x()) <= 2
    assert abs(cy - avail.center().y()) <= 2


# ---------------------------------------------------------------------------
# ۳) باگ λ/r: سرویس باید ماتریس واقعی را حتی وقتی شبکه در حافظه است بخواند
# ---------------------------------------------------------------------------
def test_service_reads_outage_matrix_even_when_network_is_in_memory(
        tmp_path, monkeypatch):
    from switchloc.application import switch_placement_service as mod
    from switchloc.reliability.switch_placement import SwitchPlacementStudy

    calls = {"opened": 0, "kv": 0}

    class FakeStore:
        def __init__(self, path):
            calls["opened"] += 1

        def load_outages(self):
            return {"lambda_r": [{"feeder_key": "F3",
                                  "lambda_per_year": 27.0, "r_minutes": 34.6}],
                    "events": []}

        def set_kv(self, *a, **k):
            calls["kv"] += 1

        def close(self):
            pass

    monkeypatch.setattr(mod, "ProjectStore", FakeStore)
    db = tmp_path / "project.sqlite"
    db.write_bytes(b"")                       # فقط «وجود فایل» مهم است

    svc = mod.SwitchPlacementService(mod.SwitchPlacementAppSettings(
        persist=True, method="directional"))
    captured = {}

    def fake_build(net, topo, store, outage_lambda, warnings):
        captured["store"] = store
        return SwitchPlacementStudy(settings={"method": "directional"})

    monkeypatch.setattr(svc, "_build_study", fake_build)
    svc.run(str(db), net=object(), topo=object())
    assert captured["store"] is not None, (
        "با شبکهٔ درون‌حافظه‌ای هم باید store باز شود تا λ/r واقعی خوانده شود")
    assert calls["opened"] >= 1 and calls["kv"] >= 1


def test_service_does_not_create_store_for_missing_db(tmp_path):
    from switchloc.application import switch_placement_service as mod

    svc = mod.SwitchPlacementService(mod.SwitchPlacementAppSettings(
        persist=False))
    seen = {}
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(svc, "_build_study",
                            lambda net, topo, store, ol, w: seen.setdefault(
                                "store", store) or
                            __import__("switchloc.reliability.switch_placement",
                                       fromlist=["SwitchPlacementStudy"])
                            .SwitchPlacementStudy())
        svc.run(str(tmp_path / "missing.sqlite"), net=object(), topo=object())
    finally:
        monkeypatch.undo()
    assert seen["store"] is None, "برای فایل ناموجود نباید پایگاه ساخته شود"


# ---------------------------------------------------------------------------
# ۴) گزارش موتور: منطبق با نوع مطالعه + فرمول‌بندی
# ---------------------------------------------------------------------------
def _study(method="directional", scope="multi"):
    from switchloc.reliability.switch_placement import (FeederStudy,
                                                        SwitchPlacementStudy)
    st = SwitchPlacementStudy(settings={
        "method": method,
        "switch_type": "sectionalizer", "switch_type_fa": "سکشنالایزر",
        "total_failure_rate_per_year": 30, "repair_time_min": 50,
        "restoration_time_min": 20, "max_sectionalizers": 2,
        "studied_feeders": ["F3", "F5"], "all_feeders": ["F3", "F4", "F5"],
        "failure_rates": {"F3": 27.0}, "repair_time_by_feeder": {"F3": 34.6},
        "load_model_level": "estimated",
    })
    st.feeders.append(FeederStudy(
        feeder_key="F3", line_length_m=12000, total_load_kw=2500,
        failure_rate_per_year=27.0, failure_rate_source="outage-lambda",
        repair_time_min=34.6, baseline_eens_kwh=49710))
    return st


def test_study_markdown_states_scope_method_and_rate_sources():
    md = _study().to_markdown()
    assert "چندفیدره" in md
    assert "دایرکشنال" in md
    assert "outage-lambda" in md and "configured-default" in md
    assert "فرمول‌بندی محاسبات" in md
    assert "P_down" in md              # فرمول مدل جهت‌دار


def test_study_markdown_uniform_uses_uniform_formula_only():
    md = _study(method="uniform").to_markdown()
    assert "P_ok" in md
    assert "P_down" not in md


def test_study_profile_reports_single_feeder_scope():
    st = _study()
    st.settings["studied_feeders"] = ["F3"]
    prof = st.study_profile()
    assert prof["scope"] == "single"
    assert prof["scope_fa"] == "تک‌فیدره"


# ---------------------------------------------------------------------------
# ۵) گزارش نهایی: بر اساس نوع مطالعه، بدون آیتم اضافی
# ---------------------------------------------------------------------------
def _eens_payload():
    payload = {"algo_version": "SwitchLoc v1.15.0",
               "settings": {}, "failure_rates": {}, "markdown": ""}
    st = _study()
    d = st.as_dict()
    d["settings"]["load_model_level"] = "estimated"
    payload["study"] = d
    return payload


def test_final_report_switches_to_eens_study():
    from switchloc.reporting.content import build_report

    class _Net:
        project_name = "پروژه آزمون"
        crs_definitions = []

    class _M:
        eens_study = _eens_payload()
        study_type = "auto"
        name = "پروژه آزمون"
        db_path = "/tmp/x.sqlite"
        crs_label = "EPSG:32639"
        manual_evals = []

        @property
        def active_study(self):
            from switchloc.reporting.eens_report import is_eens_study
            return "eens" if is_eens_study(self.eens_study) else "placement"

    doc = build_report(_M())
    assert "EENS" in doc.title
    ids = [s.id for s in doc.sections]
    assert ids[0] == "eens_summary"
    assert "eens_calculations" in ids
    for absent in ("n1", "ranking", "schemes", "economics"):
        assert absent not in ids, f"بخش {absent} نباید در گزارش EENS بیاید"
    calc = next(s for s in doc.sections if s.id == "eens_calculations")
    assert len(calc.equations) >= 5, "همهٔ فرمول‌های موتور باید بیاید"
    texts = " ".join(e.text for e in calc.equations)
    assert "P_ok,i" in texts, "رابطهٔ مدل یکنواخت باید باشد"
    assert "P_down,i" in texts, "رابطهٔ مدل جهت‌دار باید باشد"


def test_eens_profile_reads_scope_and_method():
    from switchloc.reporting.eens_report import eens_profile, is_eens_study

    payload = _eens_payload()
    assert is_eens_study(payload)
    prof = eens_profile(payload)
    assert prof["scope"] == "multi"
    assert prof["method"] == "directional"
    assert prof["scope_fa"] == "چندفیدره"
    assert prof["switches"] == 0


# ---------------------------------------------------------------------------
# ۶) بازبینی ورودی‌ها پیش از اجرا
# ---------------------------------------------------------------------------
def _preflight(**kw):
    from switchloc.application.study_preflight import preflight_from_settings
    base = dict(
        settings={"method": "directional", "switch_type": "sectionalizer",
                  "total_failure_rate_per_year": 30.0, "repair_time_min": 50.0,
                  "restoration_time_min": 20.0, "max_sectionalizers": 3,
                  "min_candidate_depth": 3, "max_downstream_load_ratio": 0.8,
                  "use_existing_switches": True},
        load_model={"level": "estimated"}, load_total_kw=12000.0,
        feeders=["F3", "F5"], all_feeders=["F3", "F4", "F5"],
        persisted_outages={"lambda_r": [
            {"feeder_key": "F3", "lambda_per_year": 27.0, "r_minutes": 34.6},
            {"feeder_key": "F5", "lambda_per_year": 57.3, "r_minutes": 25.9}]})
    base.update(kw)
    return preflight_from_settings(**base)


def test_preflight_warns_about_estimated_load():
    rep = _preflight()
    assert not rep.blocking
    groups = {(r.group, r.item) for r in rep.warnings}
    assert ("مدل بار", "سطح مدل بار") in groups
    assert any("تخمینی" in r.value for r in rep.rows)


def test_preflight_blocks_on_zero_load_and_empty_scope():
    rep = _preflight(load_total_kw=0.0, feeders=[])
    assert rep.blocking
    items = {r.item for r in rep.errors}
    assert "مجموع بار شبکه (kW)" in items
    assert "دامنه (فیدرهای انتخاب‌شده)" in items


def test_preflight_warns_for_feeders_without_real_lambda():
    rep = _preflight(feeders=["F3", "F7"])
    warns = [r for r in rep.rows if r.item == "فیدرهای دارای λ واقعی"]
    assert warns and warns[0].status == "warn"
    assert "F7" in warns[0].note


def test_preflight_recloser_probability_validation():
    from switchloc.application.study_preflight import build_preflight
    rep = build_preflight(method="uniform", switch_type="recloser",
                          engine={"reclose_success_probability": 1.7,
                                  "reclose_time_min": 0.25,
                                  "transient_max_duration_min": 3.0,
                                  "max_sectionalizers": 2,
                                  "min_candidate_depth": 3,
                                  "max_downstream_load_ratio": 0.8},
                          load_model={"level": "actual"},
                          load_total_kw=1000.0, feeders=["F1"],
                          all_feeders=["F1"])
    assert rep.blocking
    assert any("احتمال موفقیت" in r.item for r in rep.errors)


def test_preflight_dialog_disables_run_on_errors(qapp):
    from switchloc.ui.qt.preflight_dialog import make_preflight_dialog

    dlg = make_preflight_dialog(None, _preflight(load_total_kw=0.0))
    assert dlg.run_button.isEnabled() is False
    ok = make_preflight_dialog(None, _preflight())
    assert ok.run_button.isEnabled() is True


# ---------------------------------------------------------------------------
# ۷) نقشهٔ تعاملی: فیوزها در فهرست کلیدها پیش‌فرض تیک‌نخورده‌اند
# ---------------------------------------------------------------------------
def test_map_canvas_hides_fuses_in_the_switch_list_by_default(qapp):
    from PySide6.QtCore import Qt

    from switchloc.ui.qt.map_canvas import make_map_canvas

    tab = make_map_canvas()
    r = _renderer_with_fuse()
    tab.show_network(r)
    fuse_ids = {sid for ids in (r.graph.switch_ids_at or {}).values()
                for sid in ids}
    assert fuse_ids, "گراف آزمون باید یک کلید داشته باشد"
    assert fuse_ids <= tab._hidden_switch_ids, (
        "فیوزها باید پیش‌فرض پنهان باشند")

    # روشن‌کردن دستی کاربر باید معتبر بماند (پیش‌فرض بازنویسی نکند)
    tree = tab.switch_list
    for i in range(tree.topLevelItemCount()):
        parent = tree.topLevelItem(i)
        for j in range(parent.childCount()):
            parent.child(j).setCheckState(0, Qt.CheckState.Checked)
    tab.show_network(r)
    assert not (tab._hidden_switch_ids & fuse_ids)
