# -*- coding: utf-8 -*-
"""لایهٔ خاموشی‌های دارای مختصات — سبک نقشه + رندرر (بدون Qt)."""
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

from conftest import NetBuilder

POINTS = [
    {"id": "e1", "x": 50.0, "y": 0.0, "label": "F1 · پست الف",
     "status": "confirmed", "feeder": "F1", "zone_x": 60.0, "zone_y": 0.0},
    {"id": "e2", "x": 90.0, "y": 5.0, "label": "F1 · پست ب",
     "status": "pending", "feeder": "F1", "zone_x": None, "zone_y": None},
    {"id": "e3", "x": 100.0, "y": 0.0, "label": "F1 · پست ج",
     "status": "rejected", "feeder": "F1", "zone_x": 60.0, "zone_y": 0.0},
]


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


def test_style_has_a_drawable_outage_layer_by_default():
    st = MapStyle.default_for(feeders=["F1"])
    assert st.show_outages is True
    assert st.show_outage_labels is True
    assert st.show_outage_links is True
    assert st.hidden_outage_ids is None
    assert st.outage_marker                 # مارکر معتبر پیش‌فرض
    assert st.outage_size > 0


def test_outage_style_survives_a_dict_roundtrip():
    st = MapStyle.default_for(feeders=["F1"])
    st.show_outages = False
    st.outage_color = "#123456"
    st.outage_marker = "^"
    st.hidden_outage_ids = ["e2", "e1"]
    back = MapStyle.from_dict(st.as_dict())
    assert back.show_outages is False
    assert back.outage_color == "#123456"
    assert back.outage_marker == "^"
    assert sorted(back.hidden_outage_ids or []) == ["e1", "e2"]


def test_outage_marker_whitelist_rejects_garbage():
    st = MapStyle.default_for(feeders=["F1"])
    st.outage_marker = "not-a-marker"
    back = MapStyle.from_dict(st.as_dict())
    assert back.outage_marker == MapStyle.default_for(feeders=[]).outage_marker


def test_renderer_draws_the_layer_when_enabled(tmp_path):
    r = _renderer()
    out = r.render(str(tmp_path / "on.png"), outage_points=POINTS, dpi=70)
    assert Path(out).is_file() and Path(out).stat().st_size > 3000
    assert "outage" in r._drawn
    assert "outage_link" in r._drawn          # لینک به زون (ردیف‌های دارای زون)


def test_renderer_skips_the_layer_when_switched_off(tmp_path):
    st = MapStyle.default_for(feeders=["F1"])
    st.show_outages = False
    r = _renderer(style=st)
    r.render(str(tmp_path / "off.png"), outage_points=POINTS, dpi=70)
    assert "outage" not in r._drawn
    assert "outage_link" not in r._drawn


def test_hidden_outage_ids_are_not_drawn(tmp_path):
    r = _renderer()
    r.render(str(tmp_path / "hidden.png"), outage_points=POINTS, dpi=70,
             hidden_outage_ids=["e1", "e2", "e3"])
    # هیچ رخدادی رسم نمی‌شود (به‌جز لینک صفر → هیچ collection)
    assert "outage" not in r._drawn
    r2 = _renderer()
    r2.render(str(tmp_path / "partial.png"), outage_points=POINTS, dpi=70,
              hidden_outage_ids=["e1", "e3"])
    assert "outage" in r2._drawn


def test_labels_can_be_disabled_without_losing_points(tmp_path):
    st = MapStyle.default_for(feeders=["F1"])
    st.show_outage_labels = False
    r = _renderer(style=st)
    r.render(str(tmp_path / "nolabels.png"), outage_points=POINTS, dpi=70)
    assert "outage" in r._drawn


def test_malformed_points_never_crash_the_renderer(tmp_path):
    bad = [{"id": "x"}, {"id": "y", "x": "nope", "y": 1}, POINTS[0]]
    r = _renderer()
    r.render(str(tmp_path / "bad.png"), outage_points=bad, dpi=70)
    assert "outage" in r._drawn


def test_style_hidden_ids_apply_when_no_explicit_list_is_passed(tmp_path):
    """گزارش headless هم باید انتخاب «پنهان‌کردن» ذخیره‌شده در سبک را رعایت کند."""
    st = MapStyle.default_for(feeders=["F1"])
    st.hidden_outage_ids = ["e1", "e2", "e3"]
    r = _renderer(style=st)
    r.render(str(tmp_path / "style_hidden.png"), outage_points=POINTS, dpi=70)
    assert "outage" not in r._drawn

    st.hidden_outage_ids = []
    r2 = _renderer(style=st)
    r2.render(str(tmp_path / "style_shown.png"), outage_points=POINTS, dpi=70)
    assert "outage" in r2._drawn
