# -*- coding: utf-8 -*-
"""Phase 2 — headless map renderer tests (D-04)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import matplotlib
matplotlib.use("Agg")

from switchloc.topology.graph import NetworkGraph
from switchloc.topology.tracing import TracingEngine, TracingPolicy
from switchloc.topology.zones import ZoneBuilder
from switchloc.ui.map_renderer import NetworkMapRenderer
from switchloc.validation.issues import IssueLog

from conftest import NetBuilder


def _renderer():
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    b.switch(50, 0)
    b.transformer(100, 0)
    g = NetworkGraph.from_network(b.net, IssueLog())
    traces = TracingEngine(g, b.net, TracingPolicy()).trace_all(IssueLog())
    zones = ZoneBuilder(g, b.net, traces).build(IssueLog())
    return NetworkMapRenderer(g, traces=traces, zones=zones,
                              switches={s.id: s for s in b.net.switches})


def test_render_png_created(tmp_path):
    r = _renderer()
    out = tmp_path / "map.png"
    r.render(str(out), title="test map")
    assert out.exists() and out.stat().st_size > 5000


def test_render_single_feeder_filter(tmp_path):
    r = _renderer()
    out = tmp_path / "f1.png"
    r.render(str(out), title="feeder F1", feeder_filter="F1", dpi=80)
    assert out.exists() and out.stat().st_size > 3000


def test_render_zone_labels(tmp_path):
    r = _renderer()
    out = tmp_path / "zones.png"
    r.render(str(out), title="zones", feeder_filter="F1", zone_labels=True,
             dpi=80)
    assert out.exists() and out.stat().st_size > 3000


def test_legend_shows_every_map_symbol(tmp_path):
    """بازخورد کاربر: لجند باید «همه‌ی نمادهای داخل نقشه» را نشان دهد —
    مربع (منبع)، دایره (کلید بسته)، لوزی (نقطه باز/NO)، نقطه (ترانس) و
    رنگ هر فیدر + ستاره‌ی کلید پیشنهادی."""
    import matplotlib.pyplot as plt
    from switchloc.ui.map_renderer import feeder_palette

    r = _renderer()
    r.render(str(tmp_path / "leg.png"), title="legend")
    handles = r._legend_handles(feeder_palette(r.traces), None, proposed=True)
    labels = [h.get_label() for h in handles]
    for expected in ("Feeder F1", "Untraced / no label",
                     "MV/LV transformer", "DCS — دیسکانکتور/سکسیونر",
                     "Source (feeder head)",
                     "Proposed new switch (Phase 4)"):
        assert expected in labels, f"legend misses: {expected}"
    plt.close("all")


def test_rotation_is_removed_everywhere():
    """چرخش ۹۰° حذف شد — مختصات بدون تغییر استفاده می‌شود."""
    r = _renderer()
    fig = plt_figure()
    r.render_into(fig, title="no rotation")
    ax = fig.axes[0]
    # no rotation: a horizontal line stays horizontal — the y span must
    # stay tiny while the x span matches the raw 100 m network length
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    assert 90.0 <= (x1 - x0) <= 130.0
    assert (y1 - y0) < (x1 - x0) / 5.0


def plt_figure():
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(6, 4))
    return fig


def test_terminal_switch_and_typed_coordinate_have_distinct_map_symbols(tmp_path):
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    b.transformer(100, 0)
    b.switch(100, 0)
    g = NetworkGraph.from_network(b.net, IssueLog())
    traces = TracingEngine(g, b.net, TracingPolicy()).trace_all(IssueLog())
    zones = ZoneBuilder(g, b.net, traces).build(IssueLog())
    r = NetworkMapRenderer(g, traces=traces, zones=zones,
                           switches={sw.id: sw for sw in b.net.switches})
    out = tmp_path / "terminal_coordinate.png"
    r.render(str(out), title="typed coordinate", highlight_point=(5000, 5000))
    assert out.exists() and out.stat().st_size > 3000
    assert "device_DCS" in r._drawn
    assert "transformer_terminal_device" in r._drawn
    assert "coordinate" in r._drawn


def test_zone_labels_show_up_and_annual_outage_values():
    import matplotlib.pyplot as plt
    r = _renderer()
    zid = r.zones.zones[0].id
    fig = plt.figure(figsize=(6, 4))
    r.render_into(fig, zone_labels=True, zone_load_kw={zid: 1500},
                  zone_up_mwh={zid: 2.375}, zone_outage_hours={zid: 1.58})
    labels = [t.get_text() for t in fig.axes[0].texts]
    assert any('U×P: 2.375 MWh/سال' in x for x in labels)
    assert any('خاموشی: 1.58 ساعت/سال' in x for x in labels)
    plt.close(fig)


def test_manual_interfeeder_tie_is_drawn_as_dashed_overlay():
    r = _renderer()
    nodes = sorted(r.graph.nodes)
    assert len(nodes) >= 2
    fig = plt_figure()
    r.render_into(fig, manual_tie_pairs=[(nodes[0], nodes[-1])])
    assert "manual_tie" in r._drawn
    assert any(getattr(c, "get_linestyle", lambda: [])() for c in fig.axes[0].collections)


def test_zone_callouts_have_pointer_arrows_and_use_canvas_drag_handler():
    import matplotlib.pyplot as plt
    r = _renderer()
    fig = plt.figure(figsize=(6, 4))
    r.render_into(fig, zone_labels=True)
    labels = [t for t in fig.axes[0].texts
              if isinstance(t.get_gid(), str) and t.get_gid().startswith("zone:")]
    assert labels
    assert labels[0].arrow_patch is not None
    # Dragging is owned by MapCanvasMixin, not Matplotlib pick callbacks.
    assert labels[0]._draggable is None
    plt.close(fig)



def test_zone_callout_respects_user_moved_position():
    import matplotlib.pyplot as plt
    r = _renderer()
    zid = r.zones.zones[0].id
    fig = plt.figure(figsize=(6, 4))
    r.render_into(fig, zone_labels=True,
                  zone_label_positions={zid: (250.0, 175.0)})
    label = next(t for t in fig.axes[0].texts if t.get_gid() == f"zone:{zid}")
    assert tuple(label.get_position()) == (250.0, 175.0)
    assert label.xy != label.get_position()  # leader points back to the zone
    plt.close(fig)
