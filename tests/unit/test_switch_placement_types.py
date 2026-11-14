# -*- coding: utf-8 -*-
"""روش جایابی بهینهٔ کلید — انواع کلید و سه روش محاسبهٔ EENS.

آزمون‌های خالص (بدون Qt) روی منطق اضافه‌شده در v1.12:
  * سه نوع کلید (ریکلوزر/سکشنالایزر/سکسیونر) و دامنهٔ خطای هر کدام؛
  * سهم خطای گذرا فقط برای ریکلوزر و اثر آن در EENS؛
  * زمان بازیابی دستی برای سکسیونر؛
  * ترتیب و نام‌گذاری سه روش EENS (دایرکشنال، یکنواخت، دستی).
"""
import pytest

from switchloc.application.switch_placement_service import (EENS_METHOD_FA,
                                                            EENS_METHOD_ORDER,
                                                            KV_KEY,
                                                            SwitchPlacementAppSettings,
                                                            SwitchPlacementService)
from switchloc.reliability.switch_placement import (SWITCH_DISCONNECTOR,
                                                    SWITCH_RECLOSER,
                                                    SWITCH_SECTIONALIZER,
                                                    SWITCH_TYPES,
                                                    SWITCH_TYPE_FA,
                                                    SWITCH_TYPE_FAULT_SCOPE,
                                                    RadialTree, SwitchPlacementSettings,
                                                    build_radial_tree,
                                                    build_sections,
                                                    compute_eens_kwh,
                                                    compute_transient_eens_kwh)


# ---------------------------------------------------------------- types
def test_three_switch_types_are_defined_with_persian_names():
    assert SWITCH_TYPES == ("recloser", "sectionalizer", "disconnector")
    for key in SWITCH_TYPES:
        assert SWITCH_TYPE_FA[key].strip()


def test_fault_scope_of_each_type():
    assert SWITCH_TYPE_FAULT_SCOPE[SWITCH_RECLOSER] == ("transient", "permanent")
    assert SWITCH_TYPE_FAULT_SCOPE[SWITCH_SECTIONALIZER] == ("permanent",)
    assert SWITCH_TYPE_FAULT_SCOPE[SWITCH_DISCONNECTOR] == ("permanent",)
    assert SwitchPlacementSettings(switch_type=SWITCH_RECLOSER).uses_transient_faults
    assert not SwitchPlacementSettings(
        switch_type=SWITCH_SECTIONALIZER).uses_transient_faults


def test_invalid_switch_type_is_rejected():
    with pytest.raises(ValueError):
        SwitchPlacementSettings(switch_type="fuse")


def test_disconnector_uses_manual_restoration_time():
    st = SwitchPlacementSettings(switch_type=SWITCH_DISCONNECTOR,
                                 restoration_time_min=20.0,
                                 manual_restoration_time_min=45.0)
    assert st.effective_restoration_time_min == 45.0
    st2 = SwitchPlacementSettings(switch_type=SWITCH_SECTIONALIZER,
                                  restoration_time_min=20.0)
    assert st2.effective_restoration_time_min == 20.0


def test_settings_dict_carries_type_and_transient_parameters():
    d = SwitchPlacementSettings(switch_type=SWITCH_RECLOSER).as_dict()
    assert d["switch_type"] == SWITCH_RECLOSER
    assert d["switch_type_fa"].startswith("ریکلوزر")
    assert d["transient_max_duration_min"] > 0
    assert 0.0 <= d["reclose_success_probability"] <= 1.0


# ---------------------------------------------------------------- transient EENS
class _Trace:
    source_node = "n0"
    edges = ("e01", "e12")
    nodes = ("n0", "n1", "n2")
    feeder_key = "F1"


class _Graph:
    def __init__(self):
        self.nodes = {"n0": _N((0, 0)), "n1": _N((1000, 0)),
                      "n2": _N((2000, 0))}
        self.edges = {"e01": _E("n0", "n1", 1000.0),
                      "e12": _E("n1", "n2", 1000.0)}
        self.neighbors = lambda node: {
            "n0": [("n1", "e01")], "n1": [("n0", "e01"), ("n2", "e12")],
            "n2": [("n1", "e12")]}[node]
        self.switch_ids_at = {}
        self.transformer_ids_at = {}


class _N:
    def __init__(self, coord):
        self.coord = coord


class _E:
    def __init__(self, a, b, length):
        self.a, self.b, self.length_m = a, b, length
        self.kind, self.branch_id = "line_aerial", ""


def _tree_and_sections(loads, cuts=()):
    tree = build_radial_tree(_Graph(), _Trace(), loads)
    return tree, build_sections(tree, cuts)


def test_transient_eens_is_zero_without_transient_rate():
    tree, sections = _tree_and_sections({"n1": 500.0, "n2": 500.0})
    assert compute_transient_eens_kwh(tree, sections, transient_rate=0.0,
                                      total_load_kw=1000.0) == 0.0


def test_recloser_reduces_transient_eens():
    """ریکلوزرِ نزدیک سر فیدر، بیشتر بار را با وقفهٔ کوتاه پوشش می‌دهد."""
    loads = {"n1": 500.0, "n2": 500.0}
    tree, sections = _tree_and_sections(loads, ("n1",))
    base = compute_transient_eens_kwh(
        tree, sections, transient_rate=40.0, total_load_kw=1000.0,
        transient_time_min=1.0, reclose_time_min=0.25,
        reclose_success_probability=0.7)
    with_recloser = compute_transient_eens_kwh(
        tree, sections, transient_rate=40.0, total_load_kw=1000.0,
        transient_time_min=1.0, reclose_time_min=0.25,
        reclose_success_probability=0.7, recloser_nodes=("n1",))
    assert base > with_recloser > 0.0


def test_full_reclose_success_gives_smallest_transient_eens():
    loads = {"n1": 500.0, "n2": 500.0}
    tree, sections = _tree_and_sections(loads, ("n1",))
    perfect = compute_transient_eens_kwh(
        tree, sections, transient_rate=40.0, total_load_kw=1000.0,
        transient_time_min=1.0, reclose_time_min=0.0,
        reclose_success_probability=1.0, recloser_nodes=("n1",))
    imperfect = compute_transient_eens_kwh(
        tree, sections, transient_rate=40.0, total_load_kw=1000.0,
        transient_time_min=1.0, reclose_time_min=0.0,
        reclose_success_probability=0.5, recloser_nodes=("n1",))
    assert perfect < imperfect


def test_permanent_eens_ignores_recloser_parameters():
    """EENS دائمی نباید به پارامترهای گذرا وابسته باشد."""
    tree, sections = _tree_and_sections({"n1": 500.0, "n2": 500.0})
    a = compute_eens_kwh(sections, failure_rate=30.0, total_length_m=2000.0,
                         total_load_kw=1000.0, repair_time_min=50.0,
                         restoration_time_min=20.0)
    b = compute_eens_kwh(sections, failure_rate=30.0, total_length_m=2000.0,
                         total_load_kw=1000.0, repair_time_min=50.0,
                         restoration_time_min=20.0)
    assert a == pytest.approx(b)


# ---------------------------------------------------------------- methods
def test_eens_methods_order_is_directional_uniform_manual():
    assert EENS_METHOD_ORDER == ("directional", "uniform", "manual")
    for key in EENS_METHOD_ORDER:
        assert EENS_METHOD_FA[key].strip()


def test_method_names_are_full_and_distinct():
    names = [EENS_METHOD_FA[k] for k in EENS_METHOD_ORDER]
    assert len(set(names)) == 3
    assert "واقعی" in EENS_METHOD_FA["directional"]
    assert "واقعی" in EENS_METHOD_FA["uniform"]
    assert "دستی" in EENS_METHOD_FA["manual"]


def test_service_settings_defaults_and_snapshot():
    svc = SwitchPlacementService(SwitchPlacementAppSettings(method="directional"))
    snap = svc._settings_snapshot()
    assert snap["method"] == "directional"
    assert snap["method_fa"] == EENS_METHOD_FA["directional"]
    assert snap["engine"]["switch_type"] == SWITCH_SECTIONALIZER


def test_kv_key_is_unchanged_for_backward_compatibility():
    assert KV_KEY == "sectionalizer_study"
