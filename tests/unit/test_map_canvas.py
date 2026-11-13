# -*- coding: utf-8 -*-
"""Zoom-pack tests for the interactive map canvas.

Three layers:
  * pure zoom math (`zoom_limits`, `span_ok`)                — no Qt
  * the shipped `MapCanvasMixin` engine on a pure-Agg canvas — no Qt
  * the Qt `MapTab` widget strip (offscreen)                 — needs PySide6,
    skipped automatically on headless machines without Qt (BUILD.bat runs
    them on the engineer's Windows machine).
"""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure                          # noqa: E402

import pytest                                    # noqa: E402

from switchloc.ui.qt.map_canvas import (MapCanvasMixin, WHEEL_STEP,  # noqa
                                        ZOOM_IN, ZOOM_OUT, clamp_span,
                                        span_ok, zoom_limits)

try:
    import PySide6.QtWidgets as QtWidgets        # noqa: F401
    HAS_QT = True
except ImportError:                              # no libEGL etc. on headless CI
    HAS_QT = False


class AggCanvas(MapCanvasMixin, FigureCanvasAgg):
    """The shipped zoom engine on a Qt-free canvas (same code path)."""

    def __init__(self):
        self.fig = Figure(figsize=(6, 4))
        FigureCanvasAgg.__init__(self, self.fig)
        self._init_state()
        self.connect_events()


@pytest.fixture()
def canvas():
    """Shipped zoom engine on a pure-Agg canvas (no QApplication needed)."""
    c = AggCanvas()
    ax = c.fig.add_subplot(111)
    ax.set_xlim(0.0, 100.0)
    ax.set_ylim(0.0, 100.0)
    c._home = (ax.get_xlim(), ax.get_ylim())
    return c, ax


# ----------------------------------------------------------------------
# pure math (no Qt)
# ----------------------------------------------------------------------
def test_zoom_limits_is_cursor_anchored():
    lo, hi = zoom_limits(0.0, 100.0, anchor=20.0, scale=0.5)
    # the anchor keeps its relative position: (20-0)/100 == 0.2
    assert abs((20.0 - lo) / (hi - lo) - 0.2) < 1e-12
    assert hi - lo == pytest.approx(50.0)


def test_zoom_limits_symmetric_around_center():
    lo, hi = zoom_limits(0.0, 100.0, anchor=50.0, scale=1.0 / WHEEL_STEP)
    assert lo == pytest.approx(50.0 - 50.0 / WHEEL_STEP)
    assert hi == pytest.approx(50.0 + 50.0 / WHEEL_STEP)


def test_span_ok_window():
    assert span_ok(0.0, 100.0, 0.0, 100.0)          # full extent
    assert span_ok(0.0, 100.0 / ZOOM_IN, 0.0, 100.0)     # deepest zoom in
    assert span_ok(0.0, 100.0 * ZOOM_OUT, 0.0, 100.0)    # deepest zoom out
    assert not span_ok(0.0, 100.0 / ZOOM_IN * 0.9, 0.0, 100.0)
    assert not span_ok(0.0, 100.0 * ZOOM_OUT * 1.1, 0.0, 100.0)
    assert not span_ok(5.0, 5.0, 0.0, 100.0)        # degenerate zero span


def test_clamp_span_snaps_onto_caps():
    # zoom-in overshoot -> lands exactly on the deep-zoom cap
    lo, hi = clamp_span(49.999, 50.001, anchor=50.0, home_lo=0.0, home_hi=100.0)
    assert hi - lo == pytest.approx(100.0 / ZOOM_IN)
    # zoom-out overshoot -> lands exactly on the zoom-out cap
    lo, hi = clamp_span(-5000.0, 5000.0, anchor=0.0, home_lo=0.0, home_hi=100.0)
    assert hi - lo == pytest.approx(100.0 * ZOOM_OUT)
    # a span already inside the window passes untouched (identity)
    lo, hi = clamp_span(10.0, 60.0, anchor=30.0, home_lo=0.0, home_hi=100.0)
    assert (lo, hi) == pytest.approx((10.0, 60.0))


# ----------------------------------------------------------------------
# shipped zoom engine on a pure-Agg canvas (no Qt)
# ----------------------------------------------------------------------
def test_wheel_zoom_in_shrinks_limits_around_cursor(canvas):
    c, ax = canvas
    assert c._zoom_axes(ax, 50.0, 50.0, 1.0 / WHEEL_STEP)
    x0, x1 = ax.get_xlim()
    assert x1 - x0 == pytest.approx(100.0 / WHEEL_STEP)


def test_zoom_out_beyond_cap_snaps_onto_cap(canvas):
    c, ax = canvas
    assert c._zoom_axes(ax, 50.0, 50.0, ZOOM_OUT * 4)    # clamped, accepted
    assert ax.get_xlim()[1] - ax.get_xlim()[0] == \
        pytest.approx(100.0 * ZOOM_OUT)
    # already at the cap -> further zoom-out steps are refused, no drift
    assert not c._zoom_axes(ax, 20.0, 80.0, ZOOM_OUT * 8)
    assert ax.get_xlim()[1] - ax.get_xlim()[0] == \
        pytest.approx(100.0 * ZOOM_OUT)


def test_zoom_in_beyond_cap_snaps_onto_cap(canvas):
    c, ax = canvas
    assert c._zoom_axes(ax, 50.0, 50.0, 1.0 / (WHEEL_STEP ** 50))
    assert ax.get_xlim()[1] - ax.get_xlim()[0] == \
        pytest.approx(100.0 / ZOOM_IN)


def test_deep_zoom_reaches_the_10_000x_cap(canvas):
    """User feedback («افزایش زوم ۱۰ برابر بیشتر»): the cap was 1000x,
    raised 10x to 10 000x — it must be reachable exactly by repeated
    wheel steps, and the normalized indicator must read 100 % there."""
    c, ax = canvas
    ok_steps = 0
    for _ in range(120):
        if not c._zoom_axes(ax, 50.0, 50.0, 1.0 / WHEEL_STEP):
            break                          # cap reached — real end of range
        ok_steps += 1
    # 1.25^n = 10 000  ->  exactly 42 notches from fit to the cap
    assert ok_steps == 42
    assert c.zoom_pct() == pytest.approx(ZOOM_IN * 100.0)   # 1 000 000 %
    assert c.zoom_level_pct() == pytest.approx(100.0)       # scale max
    assert not c._zoom_axes(ax, 50.0, 50.0, 1.0 / WHEEL_STEP)
    assert c.zoom_pct() == pytest.approx(ZOOM_IN * 100.0)   # stays


def test_zoom_level_pct_is_normalized_0_100(canvas):
    """The zoom SCALE reads 0-100 % (user feedback: «اسکیل زوم تا
    ۱۰۰ درصد نمایش دهد») — 0 % at full view, ~100 % at the cap."""
    c, ax = canvas
    assert c.zoom_level_pct() == pytest.approx(0.0)         # full view
    c._zoom_axes(ax, 50.0, 50.0, 1.0 / WHEEL_STEP)
    level = c.zoom_level_pct()
    assert 0.0 < level < 10.0                # one notch of 42 -> small %
    c.fit_view()
    assert c.zoom_level_pct() == pytest.approx(0.0)


def test_scroll_event_zooms_in_and_updates_indicator(canvas):
    c, ax = canvas
    seen = []
    c.on_view_changed = seen.append
    ev = SimpleNamespace(inaxes=ax, xdata=30.0, ydata=40.0, button="up")
    c._on_scroll(ev)
    x0, x1 = ax.get_xlim()
    assert x1 - x0 == pytest.approx(100.0 / WHEEL_STEP)
    assert seen and seen[-1] == pytest.approx(WHEEL_STEP * 100.0, rel=1e-3)


def test_scroll_down_zooms_out(canvas):
    c, ax = canvas
    c._on_scroll(SimpleNamespace(inaxes=ax, xdata=50.0, ydata=50.0,
                                 button="down"))
    assert ax.get_xlim()[1] - ax.get_xlim()[0] == pytest.approx(
        100.0 * WHEEL_STEP)


def test_scroll_outside_axes_is_ignored(canvas):
    c, ax = canvas
    c._on_scroll(SimpleNamespace(inaxes=None, xdata=None, ydata=None,
                                 button="up"))
    assert ax.get_xlim() == pytest.approx((0.0, 100.0))


def test_double_click_zooms_in_at_cursor(canvas):
    c, ax = canvas
    px, py = ax.transData.transform((25.0, 75.0))
    c._on_press(SimpleNamespace(inaxes=ax, button=1, dblclick=True,
                                x=px, y=py, xdata=25.0, ydata=75.0))
    x0, x1 = ax.get_xlim()
    assert x1 - x0 == pytest.approx(100.0 / WHEEL_STEP)
    assert abs((25.0 - x0) / (x1 - x0) - 0.25) < 1e-9    # anchored


def test_left_drag_pans_and_release_stops(canvas):
    c, ax = canvas
    px0, py0 = ax.transData.transform((60.0, 60.0))
    c._on_press(SimpleNamespace(inaxes=ax, button=1, dblclick=False,
                                x=px0, y=py0, xdata=60.0, ydata=60.0))
    assert c._pan is not None
    px1, py1 = ax.transData.transform((40.0, 45.0))
    c._on_motion(SimpleNamespace(inaxes=ax, x=px1, y=py1,
                                 xdata=40.0, ydata=45.0))
    x0, _ = ax.get_xlim()
    y0, _ = ax.get_ylim()
    assert x0 == pytest.approx(20.0)          # content follows the cursor
    assert y0 == pytest.approx(15.0)
    c._on_release(SimpleNamespace(inaxes=ax, x=px1, y=py1,
                                  xdata=40.0, ydata=45.0))
    assert c._pan is None


def test_fit_view_restores_home_limits(canvas):
    c, ax = canvas
    c._zoom_axes(ax, 50.0, 50.0, 1.0 / WHEEL_STEP ** 3)
    assert ax.get_xlim()[1] - ax.get_xlim()[0] < 100.0
    c.fit_view()
    assert ax.get_xlim() == pytest.approx((0.0, 100.0))
    assert ax.get_ylim() == pytest.approx((0.0, 100.0))
    assert c.zoom_pct() == pytest.approx(100.0)


def test_zoom_center_buttons(canvas):
    c, ax = canvas
    c._zoom_center(1.0 / WHEEL_STEP)
    assert c.zoom_pct() == pytest.approx(WHEEL_STEP * 100.0, rel=1e-3)
    c._zoom_center(WHEEL_STEP)
    c._zoom_center(WHEEL_STEP)
    assert c.zoom_pct() < 100.0
    c.fit_view()
    assert c.zoom_pct() == pytest.approx(100.0)


def test_show_network_sets_home_and_home_pct():
    """End-to-end: renderer output becomes the home (full-extent) view."""
    from switchloc.ui.map_renderer import NetworkMapRenderer

    graph = SimpleNamespace(edges={}, nodes={}, switch_ids_at={},
                            transformer_ids_at={})
    rend = NetworkMapRenderer(graph, traces=[], zones=None, switches={})
    c = AggCanvas()
    c.show_network(rend, title="smoke")
    assert c.map_renderer is rend
    assert c._home is not None
    assert c.zoom_pct() == pytest.approx(100.0)


def test_show_network_is_full_frame_with_border():
    """User feedback («نمایش زاویه دار»): NO rotation and NO anisotropic
    stretch — the map tab must show the same undistorted, perpendicular
    view as the printed report (aspect EQUAL, like the renderer), while
    the axes box still covers the widget and a visible border marks the
    displayable extent."""
    from switchloc.ui.map_renderer import NetworkMapRenderer

    graph = SimpleNamespace(edges={}, nodes={}, switch_ids_at={},
                            transformer_ids_at={})
    rend = NetworkMapRenderer(graph, traces=[], zones=None, switches={})
    c = AggCanvas()
    c.show_network(rend, title="true-geometry", rotate=True)  # must be ignored
    ax = c.main_ax()
    assert ax.get_aspect() == 1.0            # equal aspect — no skew
    assert all(sp.get_visible() for sp in ax.spines.values())
    assert all(sp.get_edgecolor() != "none" for sp in ax.spines.values())
    # the old rotate checkbox behaviour is gone: no 90° axis swap
    assert c._home is not None
    assert c.zoom_pct() == pytest.approx(100.0)


def test_osm_background_stays_under_the_network_and_keeps_view():
    """User feedback نیاز ۲: the OSM raster must sit UNDER the feeders
    (zorder 0) and must NOT widen the view with its padding."""
    import numpy as np
    from switchloc.ui.map_renderer import NetworkMapRenderer

    graph = SimpleNamespace(edges={}, nodes={}, switch_ids_at={},
                            transformer_ids_at={})
    rend = NetworkMapRenderer(graph, traces=[], zones=None, switches={})
    c = AggCanvas()
    c.show_network(rend, title="osm")
    ax = c.main_ax()
    hx0, hx1 = ax.get_xlim()
    hy0, hy1 = ax.get_ylim()
    img = np.zeros((16, 16, 4), dtype=np.uint8)
    img[..., 3] = 255
    c.show_network(rend, title="osm", osm_image=img,
                   osm_extent=(hx0 - 50.0, hx1 + 50.0,
                               hy0 - 50.0, hy1 + 50.0))
    ax = c.main_ax()                       # fresh axes (fig.clf above)
    # the padded raster (±50 m) must NOT widen the view: limits stay
    assert ax.get_xlim() == pytest.approx((hx0, hx1))
    assert ax.get_ylim() == pytest.approx((hy0, hy1))
    assert c._home[0] == pytest.approx((hx0, hx1))
    images = list(ax.get_images())
    assert images and images[0].zorder == 0    # raster at the bottom


# ----------------------------------------------------------------------
# نیاز ۴ — region zoom («ذره‌بین»)
# ----------------------------------------------------------------------
def test_zoom_to_region_fills_the_rectangle(canvas):
    c, ax = canvas
    assert c.zoom_to_region(ax, 10.0, 20.0, 30.0, 40.0)
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    assert (x0, x1) == pytest.approx((10.0, 30.0))
    assert (y0, y1) == pytest.approx((20.0, 40.0))
    # reversed corners are normalized
    c.zoom_to_region(ax, 60.0, 15.0, 40.0, 35.0)
    assert ax.get_xlim() == pytest.approx((40.0, 60.0))
    assert ax.get_ylim() == pytest.approx((15.0, 35.0))


def test_zoom_to_region_respects_the_zoom_out_cap(canvas):
    c, ax = canvas
    assert c.zoom_to_region(ax, -5000.0, -5000.0, 5000.0, 5000.0)
    assert ax.get_xlim()[1] - ax.get_xlim()[0] == \
        pytest.approx(100.0 * ZOOM_OUT)


def test_region_mode_rubber_band_zooms_on_release(canvas):
    c, ax = canvas
    c.set_region_mode(True)
    assert c.region_mode
    c._on_press(SimpleNamespace(inaxes=ax, button=1, dblclick=False,
                                x=10, y=10, xdata=20.0, ydata=50.0))
    assert c._region is not None
    c._on_motion(SimpleNamespace(inaxes=ax, x=40, y=40,
                                 xdata=40.0, ydata=30.0))
    rect = c.region_rect_data()
    assert rect[0] == pytest.approx((20.0, 40.0))
    assert rect[1] == pytest.approx((30.0, 50.0))
    consumed = c._on_release(SimpleNamespace(inaxes=ax, x=40, y=40,
                                             xdata=40.0, ydata=30.0))
    assert consumed
    assert c._region is None
    assert ax.get_xlim() == pytest.approx((20.0, 40.0))
    assert ax.get_ylim() == pytest.approx((30.0, 50.0))
    c.set_region_mode(False)
    assert not c.region_mode


def test_region_mode_click_without_drag_is_not_a_zoom(canvas):
    """A marquee smaller than the pixel threshold must NOT zoom."""
    c, ax = canvas
    c.set_region_mode(True)
    c._on_press(SimpleNamespace(inaxes=ax, button=1, dblclick=False,
                                x=10, y=10, xdata=50.0, ydata=50.0))
    consumed = c._on_release(SimpleNamespace(inaxes=ax, x=10.5, y=10.5,
                                             xdata=50.2, ydata=50.2))
    assert consumed
    assert ax.get_xlim() == pytest.approx((0.0, 100.0))   # view untouched


def test_region_mode_disables_panning(canvas):
    """While the magnifier is armed, a left-drag must not start a pan."""
    c, ax = canvas
    c.set_region_mode(True)
    c._on_press(SimpleNamespace(inaxes=ax, button=1, dblclick=False,
                                x=10, y=10, xdata=60.0, ydata=60.0))
    assert c._pan is None                                 # no pan in region mode
    c._on_release(SimpleNamespace(inaxes=ax, x=12, y=12,
                                  xdata=62.0, ydata=62.0))
    c.set_region_mode(False)
    c._on_press(SimpleNamespace(inaxes=ax, button=1, dblclick=False,
                                x=10, y=10, xdata=60.0, ydata=60.0))
    assert c._pan is not None                             # pan works again


# ----------------------------------------------------------------------
# Qt widget strip (offscreen; runs where PySide6 is importable)
# ----------------------------------------------------------------------
@pytest.fixture()
def app():
    if not HAS_QT:
        pytest.skip("PySide6.QtWidgets is not importable on this machine")
    if QtWidgets.QApplication.instance() is None:
        QtWidgets.QApplication([])
    yield


@pytest.mark.skipif(not HAS_QT, reason="PySide6.QtWidgets is not importable")
def test_map_tab_has_control_strip(app):
    from switchloc.ui.qt.map_canvas import make_map_canvas
    tab = make_map_canvas()
    assert tab.feeder.count() >= 1
    assert tab.feeder.itemText(0) == "All feeders"
    assert tab.zone_labels.isChecked() is False
    assert tab.zoom_label.text().startswith("Zoom: 0 %")
    assert not hasattr(tab, "rotate")          # 90° rotation removed
    assert tab.canvas.map_renderer is None


@pytest.mark.skipif(not HAS_QT, reason="PySide6.QtWidgets is not importable")
def test_map_tab_feeder_combo_rebuild_keeps_selection(app):
    from types import SimpleNamespace as NS
    from switchloc.ui.map_renderer import NetworkMapRenderer
    from switchloc.ui.qt.map_canvas import make_map_canvas

    graph = NS(edges={}, nodes={}, switch_ids_at={}, transformer_ids_at={})
    rend = NetworkMapRenderer(graph, traces=[], zones=None, switches={})
    tab = make_map_canvas()
    tab.show_network(rend, title="t")
    assert tab.feeder.count() == 1              # no feeders -> filter only
    assert tab.canvas._home is not None
    assert tab.canvas.zoom_pct() == pytest.approx(100.0)


def test_redraw_preserves_zoom_window_and_full_extent_home():
    """Zone-label/style/visibility redraws must not redefine the zoom home."""
    from switchloc.ui.map_renderer import NetworkMapRenderer

    graph = SimpleNamespace(edges={}, nodes={}, switch_ids_at={},
                            transformer_ids_at={})
    rend = NetworkMapRenderer(graph, traces=[], zones=None, switches={})
    c = AggCanvas()
    c.show_network(rend, title="initial")
    ax = c.main_ax()
    assert ax is not None
    home = c._home
    c._zoom_axes(ax, sum(ax.get_xlim()) / 2,
                 sum(ax.get_ylim()) / 2, 1.0 / WHEEL_STEP ** 4)
    zoomed = (ax.get_xlim(), ax.get_ylim())
    assert zoomed != home

    # Same graph, new renderer instance: exactly what refresh_map does.
    rend2 = NetworkMapRenderer(graph, traces=[], zones=None, switches={})
    c.show_network(rend2, title="redrawn")
    ax2 = c.main_ax()
    assert ax2.get_xlim() == pytest.approx(zoomed[0])
    assert ax2.get_ylim() == pytest.approx(zoomed[1])
    assert c._home[0] == pytest.approx(home[0])
    assert c._home[1] == pytest.approx(home[1])


def test_zone_callout_drag_moves_box_keeps_anchor_and_persists(canvas):
    """Dragging a zone label moves only its box; the leader stays anchored."""
    from matplotlib.backend_bases import MouseEvent

    c, ax = canvas
    ann = ax.annotate("F3 / Z1", xy=(30.0, 35.0), xytext=(30.0, 35.0),
                      textcoords="data", arrowprops={"arrowstyle": "-"},
                      bbox={"boxstyle": "round"}, picker=5)
    ann.set_gid("zone:zone-1")
    c.draw()
    before_anchor = tuple(ann.xy)
    px0, py0 = ax.transData.transform(ann.get_position())
    px1, py1 = ax.transData.transform((55.0, 65.0))

    press = MouseEvent("button_press_event", c, px0, py0, button=1)
    c._on_press(press)
    assert c._zone_drag is not None
    motion = MouseEvent("motion_notify_event", c, px1, py1, button=1)
    c._on_motion(motion)
    release = MouseEvent("button_release_event", c, px1, py1, button=1)
    c._on_release(release)

    assert ann.get_position() == pytest.approx((55.0, 65.0), abs=0.5)
    assert tuple(ann.xy) == before_anchor
    assert c._zone_label_positions["zone-1"] == pytest.approx(
        ann.get_position())
    assert c._pan is None


@pytest.mark.skipif(not HAS_QT, reason="PySide6.QtWidgets is not importable")
def test_unchecking_one_switch_does_not_hide_its_whole_category(app):
    """باگ: حالت «نیمه‌انتخاب» والد (AutoTristate) به فرزندان تحمیل می‌شد و
    خاموش‌کردن یک کلید، همهٔ کلیدهای آن دسته را پنهان می‌کرد."""
    from PySide6.QtCore import Qt
    from switchloc.topology.graph import NetworkGraph
    from switchloc.topology.tracing import TracingEngine, TracingPolicy
    from switchloc.ui.map_renderer import NetworkMapRenderer
    from switchloc.ui.qt.map_canvas import make_map_canvas
    from switchloc.validation.issues import IssueLog
    from conftest import NetBuilder

    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0), (150, 0)], feeder="F1")
    b.switch(50, 0, feeder="F1")
    b.switch(100, 0, feeder="F1")
    b.transformer(150, 0, feeder="F1")
    g = NetworkGraph.from_network(b.net, IssueLog())
    traces = TracingEngine(g, b.net, TracingPolicy()).trace_all(IssueLog())
    rend = NetworkMapRenderer(g, traces=traces, zones=None,
                              switches={s.id: s for s in b.net.switches})
    tab = make_map_canvas()
    tab.show_network(rend, title="switches")

    tree = tab.switch_list
    children = [tree.topLevelItem(i).child(j)
                for i in range(tree.topLevelItemCount())
                for j in range(tree.topLevelItem(i).childCount())]
    assert len(children) == 2 and children[0].parent().childCount() == 2
    first = children[0]
    first.setCheckState(0, Qt.CheckState.Unchecked)
    assert len(tab._hidden_switch_ids) == 1
    assert first.data(0, Qt.ItemDataRole.UserRole) in tab._hidden_switch_ids
    # برچسب شمارش هم درست به‌روز می‌شود
    assert "1 قابل نمایش" in tab.switch_count.text()
