# -*- coding: utf-8 -*-
"""برچسب‌های لایهٔ خاموشی: «نام مکان (تعداد خطا)» بدون هم‌پوشانی.

درخواست کاربر: به‌جای چند برچسب تکراری روی هم که تعداد خطا را نشان نمی‌داد،
هر مکان یک برچسب «کرندق (۴)» / «نوده (۶)» بگیرد و اگر چند نام در یک محل
افتاد، برچسب‌ها از هم فاصله بگیرند.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from switchloc.application.outage_review import (_clean_place_name,
                                                 outage_label_groups,
                                                 outage_map_points)
from switchloc.topology.graph import NetworkGraph
from switchloc.topology.tracing import TracingEngine, TracingPolicy
from switchloc.topology.zones import ZoneBuilder
from switchloc.ui.map_renderer import NetworkMapRenderer
from switchloc.validation.issues import IssueLog

from conftest import NetBuilder


def _pt(name, x=0.0, y=0.0, feeder="F3", status="confirmed", pid=None):
    return {"id": pid or f"{name}-{x}-{y}", "x": x, "y": y, "place": name,
            "label": name, "status": status, "feeder": feeder}


# ------------------------------------------------------------------ گروه‌بندی
def test_repeated_faults_at_one_place_become_one_label_with_count():
    groups = outage_label_groups([
        _pt("کرندق", 100.0, 200.0), _pt("کرندق", 100.0, 200.0),
        _pt("کرندق", 120.0, 200.0), _pt("کرندق", 90.0, 210.0),
        _pt("نوده", 5000.0, 200.0), _pt("نوده", 5000.0, 200.0),
    ])
    texts = {g["text"] for g in groups}
    assert texts == {"کرندق (4)", "نوده (2)"}
    by_name = {g["name"]: g for g in groups}
    assert by_name["کرندق"]["count"] == 4
    assert by_name["کرندق"]["x"] == pytest.approx(102.5)
    assert by_name["کرندق"]["y"] == pytest.approx(202.5)


def test_counts_never_silently_drop_points():
    pts = [_pt("کرندق", i * 10.0, 0.0) for i in range(6)]
    groups = outage_label_groups(pts)
    assert len(groups) == 1
    assert groups[0]["count"] == len(pts)
    assert groups[0]["text"] == "کرندق (6)"


def test_same_name_far_apart_is_split_into_two_labels():
    groups = outage_label_groups([
        _pt("کرندق", 0.0, 0.0), _pt("کرندق", 10.0, 0.0),
        _pt("کرندق", 30000.0, 0.0),
    ], cluster_distance_m=2000.0)
    assert sorted(g["count"] for g in groups) == [1, 2]
    assert {g["text"] for g in groups} == {"کرندق (1)", "کرندق (2)"}


def test_feeders_are_not_mixed_in_one_label():
    groups = outage_label_groups([_pt("کرندق", 0, 0, feeder="F3"),
                                  _pt("کرندق", 0, 0, feeder="F5")])
    assert {g["feeder"] for g in groups} == {"F3", "F5"}
    assert all(g["count"] == 1 for g in groups)


def test_empty_and_junk_names_are_ignored_or_cleaned():
    assert _clean_place_name("Sheet1") == ""
    assert _clean_place_name(" sheet ") == ""
    assert _clean_place_name("—") == ""
    assert _clean_place_name("Sheet1x") == "Sheet1x"
    assert _clean_place_name("  زرج   آباد ") == "زرج آباد"
    groups = outage_label_groups([
        {"x": 0, "y": 0, "place": ""}, {"x": 1, "y": 1},
        {"x": "bad", "y": 0, "place": "نوده"}, _pt("نوده", 2.0, 0.0)])
    assert len(groups) == 1 and groups[0]["count"] == 1


def test_grouping_is_deterministic():
    pts = [_pt("نوده", 0, 0), _pt("کرندق", 0, 0), _pt("آبادی", 0, 0)]
    a = [(g["name"], g["text"]) for g in outage_label_groups(pts)]
    b = [(g["name"], g["text"]) for g in outage_label_groups(list(reversed(pts)))]
    assert a == b


# ----------------------------------------------------- نام مکان در نقاط نقشه
def test_map_point_label_is_the_place_not_the_event_number():
    m = SimpleNamespace(place=SimpleNamespace(place_id="p1", name="زرج آباد",
                                              lat=38.05, lon=48.06),
                        confidence="بالا")
    rec = SimpleNamespace(id="e1", feeder_key="F3", feeder_raw="F3",
                          event_no="10048006", substation="Sheet1", notes="")
    points = outage_map_points([rec],
                               suggestions={"e1": SimpleNamespace(matches=(m,))},
                               transform=lambda lat, lon: (700000.0, 4160000.0))
    assert len(points) == 1
    assert points[0]["place"] == "زرج آباد"
    assert points[0]["label"] == "زرج آباد"
    assert "Sheet1" not in points[0]["label"]


def test_saved_review_place_name_wins_for_the_label():
    rec = SimpleNamespace(id="e1", feeder_key="F3", event_no="1",
                          substation="Sheet1")
    points = outage_map_points(
        [rec], saved={"e1": {"coord_x": 10.0, "coord_y": 20.0,
                             "place_name": "کرندق", "status": "confirmed"}},
        transform=None)
    assert points[0]["place"] == "کرندق"
    assert points[0]["status"] == "confirmed"


# --------------------------------------------------------------- رندر برچسب‌ها
def _renderer(style=None):
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    b.switch(50, 0)
    b.transformer(100, 0)
    g = NetworkGraph.from_network(b.net, IssueLog())
    traces = TracingEngine(g, b.net, TracingPolicy()).trace_all(IssueLog())
    zones = ZoneBuilder(g, b.net, traces).build(IssueLog())
    return NetworkMapRenderer(g, traces=traces, zones=zones,
                              switches={s.id: s for s in b.net.switches},
                              style=style)


def _render_labels(points, style=None):
    from switchloc.ui.map_style import MapStyle

    fig = plt.figure(figsize=(8, 6), constrained_layout=True)
    r = _renderer(style or MapStyle.default_for(feeders=["F1"]))
    r.render_into(fig, title="labels", outage_points=points)
    ax = fig.axes[0]
    anns = [(t.get_text(), tuple(t.xyann)) for t in ax.texts]
    plt.close(fig)
    return anns


def test_renderer_shows_one_label_per_place_with_the_count():
    anns = _render_labels([
        _pt("کرندق", 50.0, 0.0), _pt("کرندق", 50.0, 0.0),
        _pt("کرندق", 50.0, 0.0), _pt("کرندق", 50.0, 0.0),
    ])
    assert [a[0] for a in anns] == ["کرندق (4)"]


def test_two_names_at_the_same_place_are_staggered():
    anns = _render_labels([_pt("کرندق", 50.0, 0.0), _pt("نوده", 51.0, 0.0)])
    texts = [a[0] for a in anns]
    assert set(texts) == {"کرندق (1)", "نوده (1)"}
    offsets = sorted(a[1][1] for a in anns)
    assert len(set(offsets)) == 2, "برچسب‌های هم‌مکان باید عمودی از هم جدا شوند"
    assert offsets[0] == 0.0                         # برچسب اول سرجای خودش
    assert offsets[1] >= 6.0                         # دومی یک پله بالا می‌رود


def test_far_apart_labels_are_not_shifted():
    anns = _render_labels([_pt("کرندق", 10.0, 0.0), _pt("نوده", 90.0, 0.0)])
    assert [a[1][1] for a in anns] == [0.0, 0.0]


def test_labels_can_be_switched_off():
    from switchloc.ui.map_style import MapStyle

    st = MapStyle.default_for(feeders=["F1"])
    st.show_outage_labels = False
    assert _render_labels([_pt("کرندق", 50.0, 0.0)], st) == []


def test_hidden_events_do_not_count_in_the_label():
    from switchloc.ui.map_style import MapStyle

    st = MapStyle.default_for(feeders=["F1"])
    pts = [_pt("کرندق", 50.0, 0.0, pid="a"), _pt("کرندق", 50.0, 0.0, pid="b")]
    fig = plt.figure(figsize=(8, 6), constrained_layout=True)
    r = _renderer(st)
    r.render_into(fig, title="t", outage_points=pts, hidden_outage_ids=["b"])
    texts = [t.get_text() for t in fig.axes[0].texts]
    plt.close(fig)
    assert texts == ["کرندق (1)"]
