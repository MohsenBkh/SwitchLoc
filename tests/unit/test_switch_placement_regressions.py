# -*- coding: utf-8 -*-
"""آزمون‌های رگرسیون برای اصلاحات نسخهٔ ۱.۱۳.

هر آزمون یک باگ واقعیِ پیدا‌شده در بازبینی کامل برنامه را قفل می‌کند:

1. **مدل EENS**: اگر زمان بازیابی بار سالم از زمان تعمیر بیشتر باشد، نصب
   کلید نباید EENS را *افزایش* دهد (clamp به کمینهٔ تعمیر/بازیابی).
2. **بازخوانی تنظیمات تب** از snapshot ذخیره‌شدهٔ سرویس (دو سطح
   ``engine`` + تنظیمات تب) و پذیرش ``backup_kw`` به‌صورت dict.
3. **برچسب سطوح نقشهٔ حرارتی** پس از ویرایش دستی.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest                                        # noqa: E402

from switchloc.reliability.switch_placement import (SWITCH_DISCONNECTOR,  # noqa: E402
                                                   build_radial_tree,
                                                   build_sections,
                                                   compute_eens_kwh)
from switchloc.ui.map_style import MapStyle           # noqa: E402

try:
    from PySide6 import QtWidgets                     # noqa: E402
    HAS_QT = True
except ImportError:                                  # pragma: no cover
    HAS_QT = False


@pytest.fixture()
def app():
    if not HAS_QT:                                    # pragma: no cover
        pytest.skip("PySide6.QtWidgets is not importable")
    if QtWidgets.QApplication.instance() is None:
        QtWidgets.QApplication([])
    yield


# ------------------------------------------------------------------ helpers
class _N:
    def __init__(self, coord):
        self.coord = coord


class _E:
    def __init__(self, a, b, length):
        self.a, self.b, self.length_m = a, b, length
        self.kind, self.branch_id = "line_aerial", ""


class _Trace:
    source_node = "n0"
    edges = ("e01", "e12", "e23")
    nodes = ("n0", "n1", "n2", "n3")
    feeder_key = "F1"


class _Graph:
    def __init__(self):
        self.nodes = {f"n{i}": _N((i * 1000, 0)) for i in range(4)}
        self.edges = {"e01": _E("n0", "n1", 1000.0),
                      "e12": _E("n1", "n2", 1000.0),
                      "e23": _E("n2", "n3", 1000.0)}
        self.neighbors = lambda node: {
            "n0": [("n1", "e01")],
            "n1": [("n0", "e01"), ("n2", "e12")],
            "n2": [("n1", "e12"), ("n3", "e23")],
            "n3": [("n2", "e23")],
        }[node]
        self.switch_ids_at = {}
        self.transformer_ids_at = {}


LOADS = {"n1": 400.0, "n2": 300.0, "n3": 300.0}


def _eens(cuts, *, repair, restore):
    tree = build_radial_tree(_Graph(), _Trace(), LOADS)
    sections = build_sections(tree, cuts)
    return compute_eens_kwh(sections, failure_rate=30.0,
                            total_length_m=tree.total_length_m,
                            total_load_kw=tree.total_load_kw,
                            repair_time_min=repair,
                            restoration_time_min=restore)


# ------------------------------------------------------- EENS model clamp
def test_adding_a_switch_never_worsens_eens_when_restore_slower_than_repair():
    """با زمان بازیابی دستی ۴۵ > تعمیر ۳۰، نصب سوئیچ نباید EENS را بالا ببرد."""
    base = _eens((), repair=30.0, restore=45.0)
    with_switch = _eens(("n2",), repair=30.0, restore=45.0)
    assert with_switch <= base + 1e-9
    # و دقیقاً همان مقدار است: عملاً انتظار تعمیر، نه بازیابی
    assert with_switch == pytest.approx(base, rel=1e-12)


def test_faster_restore_still_improves_eens():
    """حالت عادی (بازیابی سریع‌تر از تعمیر) باید همچنان کاهش EENS بدهد."""
    base = _eens((), repair=60.0, restore=20.0)
    with_switch = _eens(("n2",), repair=60.0, restore=20.0)
    assert with_switch < base - 1e-6


def test_disconnector_settings_with_slow_manual_restore_is_flagged(tmp_path):
    """موتور باید دلیل «هیچ کلید پیشنهادی» را صریح بنویسد."""
    from switchloc.reliability.switch_placement import (SwitchPlacementEngine,
                                                       SwitchPlacementSettings)
    settings = SwitchPlacementSettings(
        switch_type=SWITCH_DISCONNECTOR, repair_time_min=20.0,
        manual_restoration_time_min=45.0, max_sectionalizers=1)
    engine = SwitchPlacementEngine(settings)
    study = engine.run(_Graph(), [_Trace()], LOADS)
    feeder = study.feeders[0]
    assert not (feeder.best and feeder.best.selected)
    joined = " ".join(feeder.notes or [])
    assert "زمان بازیابی بار سالم" in joined
    assert "کمتر نیست" in joined


# ------------------------------------------------ tab settings round-trip
def _tab():
    from switchloc.ui.qt.switch_placement_tab import make_sectionalizer_tab
    return make_sectionalizer_tab(None)


def test_tab_apply_settings_reads_nested_service_snapshot(app):
    tab = _tab()
    snapshot = {
        "method": "manual",
        "failure_rate_source": "configured",
        "backup_kw": {"F3": 1000.0, "F5": 1200.0},
        "engine": {"switch_type": SWITCH_DISCONNECTOR,
                   "restoration_model": "uniform",
                   "total_failure_rate_per_year": 42.0,
                   "repair_time_min": 61.0,
                   "restoration_time_min": 15.0,
                   "max_sectionalizers": 4,
                   "min_candidate_depth": 2,
                   "max_downstream_load_ratio": 0.55,
                   "use_existing_switches": False,
                   "manual_restoration_time_min": 45.0},
    }
    tab.apply_settings(snapshot)
    got = tab.settings()
    assert got["method"] == "manual"
    assert got["switch_type"] == SWITCH_DISCONNECTOR
    assert got["total_failure_rate_per_year"] == pytest.approx(42.0)
    assert got["repair_time_min"] == pytest.approx(61.0)
    assert got["restoration_time_min"] == pytest.approx(15.0)
    assert got["manual_restoration_time_min"] == pytest.approx(45.0)
    assert got["max_sectionalizers"] == 4
    assert got["min_candidate_depth"] == 2
    assert got["max_downstream_load_ratio"] == pytest.approx(0.55)
    assert got["backup_kw"] == pytest.approx(1200.0)   # dict → بیشینه
    assert got["use_existing_switches"] is False


def test_tab_apply_settings_ignores_broken_values(app):
    tab = _tab()
    tab.apply_settings({"total_failure_rate_per_year": "not-a-number",
                        "backup_kw": {"F1": None},
                        "max_sectionalizers": {"x": 1}})
    got = tab.settings()
    assert got["total_failure_rate_per_year"] > 0
    assert got["max_sectionalizers"] >= 1


def test_tab_method_manual_unlocks_rate_fields(app):
    tab = _tab()
    tab.apply_settings({"method": "manual"})
    assert tab.settings()["method"] == "manual"
    tab.apply_settings({"method": "directional"})
    assert tab.settings()["method"] == "directional"


# --------------------------------------------------- map heat level labels
def test_heat_level_labels_regenerated_in_persian_after_edit():
    style = MapStyle.from_dict({
        "outage_heat_levels": [
            {"max": 5, "color": "#2e7d32"},
            {"max": None, "color": "#c62828"},
        ]})
    labels = [lv["label"] for lv in style.outage_heat_levels]
    assert labels[0] == "≤ 5 خاموشی"
    assert labels[1] == "همهٔ تکرارها"


def test_heat_level_colors_survive_roundtrip():
    style = MapStyle()
    style.outage_heat_levels = [
        {"max": 3, "color": "#00897b", "label": "≤ 3 خاموشی"},
        {"max": None, "color": "#d81b60", "label": "همهٔ تکرارها"},
    ]
    back = MapStyle.from_dict(style.as_dict())
    assert [lv["max"] for lv in back.outage_heat_levels] == [3, None]
    assert [lv["color"] for lv in back.outage_heat_levels] == ["#00897b",
                                                               "#d81b60"]
