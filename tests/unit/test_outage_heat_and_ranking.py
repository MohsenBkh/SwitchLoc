# -*- coding: utf-8 -*-
"""توزیع رنگی مسیر (تکرار خاموشی) و رتبه‌بندی مکان‌های خاموشی.

آزمون‌های خالص (بدون Qt/Matplotlib): منطقِ «چه رنگی؟»، «چند خاموشی روی هر
یال؟» و «کدام مکان رتبهٔ اول است؟» — همان چیزهایی که کاربر خواسته بود.
"""
from types import SimpleNamespace

import pytest

from switchloc.application.outage_review import (assign_heat_level,
                                                 outage_heat_counts,
                                                 outage_place_ranking)
from switchloc.ui.map_style import DEFAULT_OUTAGE_HEAT_LEVELS, MapStyle

LEVELS = [{"max": 2, "color": "#2e7d32", "label": "< ۲"},
          {"max": 10, "color": "#ef6c00", "label": "۲ تا ۱۰"},
          {"max": None, "color": "#c62828", "label": "> ۱۰"}]


# ---------------------------------------------------------------- levels
@pytest.mark.parametrize("count,color", [(1, "#2e7d32"), (2, "#2e7d32"),
                                         (3, "#ef6c00"), (10, "#ef6c00"),
                                         (11, "#c62828"), (500, "#c62828")])
def test_heat_level_boundaries(count, color):
    assert assign_heat_level(count, LEVELS)["color"] == color


def test_zero_or_invalid_count_has_no_level():
    assert assign_heat_level(0, LEVELS) is None
    assert assign_heat_level(-3, LEVELS) is None
    assert assign_heat_level(None, LEVELS) is None


def test_custom_number_of_levels_is_honoured():
    one = [{"max": None, "color": "#123456", "label": "همه"}]
    assert assign_heat_level(99, one)["color"] == "#123456"


# ---------------------------------------------------------------- counts
class _Graph:
    """گراف کوچک: یک خط سه‌گره‌ای در راستای x (فاصلهٔ گره‌ها ۱۰۰۰ متر)."""

    def __init__(self):
        self.nodes = {
            "a": SimpleNamespace(coord=(0.0, 0.0)),
            "b": SimpleNamespace(coord=(1000.0, 0.0)),
            "c": SimpleNamespace(coord=(2000.0, 0.0)),
        }
        self.edges = {
            "e1": SimpleNamespace(a="a", b="b"),
            "e2": SimpleNamespace(a="b", b="c"),
        }


def test_heat_counts_assign_points_to_nearby_edges_only():
    counts = outage_heat_counts(
        [{"x": 100.0, "y": 50.0}, {"x": 150.0, "y": -80.0}],
        _Graph(), radius_m=300.0)
    assert counts == {"e1": 2}          # هر دو نقطه نزدیک یال اول


def test_heat_counts_respects_radius():
    counts = outage_heat_counts([{"x": 500.0, "y": 900.0}], _Graph(),
                                radius_m=200.0)
    assert counts == {}


def test_heat_counts_skips_bad_points_and_edges():
    graph = _Graph()
    graph.edges["bad"] = SimpleNamespace(a="a", b="missing")
    counts = outage_heat_counts(
        [{"x": "?", "y": 1}, {"y": 1}, {"x": 1900.0, "y": 0.0}], graph,
        radius_m=250.0)
    assert counts == {"e2": 1}


# ---------------------------------------------------------------- ranking
def _points():
    return [
        {"x": 1.0, "y": 2.0, "place": "کرندق", "feeder": "F3",
         "status": "confirmed", "zone_id": "z1"},
        {"x": 3.0, "y": 4.0, "place": "کرندق", "feeder": "F3",
         "status": "pending", "zone_id": "z1"},
        {"x": 5.0, "y": 6.0, "place": "نوده", "feeder": "F5",
         "status": "rejected", "zone_id": "z2"},
        {"x": 7.0, "y": 8.0, "place": "نوده", "feeder": "F5",
         "status": "confirmed", "zone_id": "z2"},
        {"x": 9.0, "y": 10.0, "place": "نوده", "feeder": "F5",
         "status": "confirmed", "zone_id": "z2"},
    ]


def test_ranking_orders_by_count_and_computes_share():
    rows = outage_place_ranking(_points())
    assert [r["place"] for r in rows] == ["نوده", "کرندق"]
    assert rows[0]["rank"] == 1 and rows[0]["count"] == 3
    assert rows[0]["share_percent"] == pytest.approx(60.0)
    assert rows[1]["share_percent"] == pytest.approx(40.0)


def test_ranking_keeps_status_breakdown_and_centroid():
    top = outage_place_ranking(_points())[0]
    assert (top["confirmed"], top["pending"], top["rejected"]) == (2, 0, 1)
    assert (top["x"], top["y"]) == pytest.approx((7.0, 8.0))
    assert top["zone_id"] == "z2"


def test_ranking_limit_and_empty_input():
    assert outage_place_ranking(_points(), limit=1)[0]["place"] == "نوده"
    assert outage_place_ranking([]) == []
    assert outage_place_ranking([{"x": None, "y": 1}]) == []


# ---------------------------------------------------------------- style
def test_style_roundtrip_keeps_heat_levels_and_label_options():
    st = MapStyle()
    st.outage_heat_enabled = True
    st.outage_heat_levels = [{"max": 4, "color": "#00aaff",
                              "label": "≤ ۴"}]
    st.outage_label_max_levels = 2
    st.outage_label_leader = False
    back = MapStyle.from_dict(st.as_dict())
    assert back.outage_heat_enabled is True
    assert back.outage_heat_levels == st.outage_heat_levels
    assert back.outage_label_max_levels == 2
    assert back.outage_label_leader is False


def test_style_rejects_bad_heat_levels():
    back = MapStyle.from_dict({"outage_heat_levels": [
        {"max": "x", "color": "#fff"},
        {"max": 1, "color": "green"},
    ]})
    assert back.outage_heat_levels == DEFAULT_OUTAGE_HEAT_LEVELS


def test_style_default_levels_cover_example_of_the_user():
    """نمونهٔ درخواست: <۲ سبز، ۲..۱۰ نارنجی، >۱۰ قرمز."""
    colors = [lvl["color"] for lvl in MapStyle().outage_heat_levels]
    assert colors == ["#2e7d32", "#ef6c00", "#c62828"]
    assert assign_heat_level(1, MapStyle().outage_heat_levels)["color"] == "#2e7d32"
    assert assign_heat_level(5, MapStyle().outage_heat_levels)["color"] == "#ef6c00"
    assert assign_heat_level(20, MapStyle().outage_heat_levels)["color"] == "#c62828"


def test_heat_counts_restricts_selected_edges():
    points = [{"x": 1000, "y": 0}]
    assert outage_heat_counts(points, _Graph(), radius_m=10, edge_ids={"e1"}) == {"e1": 1}
    assert outage_heat_counts(points, _Graph(), radius_m=10, edge_ids=set()) == {}


def test_coordinate_style_and_default_link_roundtrip():
    st = MapStyle()
    assert not st.show_outage_links
    st.coordinate_size, st.coordinate_color, st.coordinate_marker = 120, "#123456", "D"
    back = MapStyle.from_dict(st.as_dict())
    assert (back.coordinate_size, back.coordinate_color, back.coordinate_marker) == (120, "#123456", "D")
