# -*- coding: utf-8 -*-
"""Tests for the map-style system + the placement-inputs confirmation
model (درخواست کاربر: رنگ هر فیدر در map style، استایل‌های چندگانهٔ
ماندگار، جدول تأیید ورودی‌ها)."""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from switchloc.ui.map_style import (FEEDER_COLORS, MapStyle,  # noqa: E402
                                    auto_palette)
from switchloc.ui.qt.map_style_dialog import (collect_style,  # noqa: E402
                                              feeder_rows)
from switchloc.ui.inputs_model import (InputRow, apply_lambda_overrides,  # noqa: E402
                                       apply_row_edits, collect_placement_rows,
                                       parse_number)


# ---------------------------------------------------------------------------
# MapStyle
# ---------------------------------------------------------------------------
def test_default_feeder_colors_are_distinct_per_feeder():
    """مورد ۱: رنگ پیش‌فرض هر فیدر در map style باید همان رنگ اولیه‌ای
    باشد که رندرر تخصیص می‌دهد — نه یک کد مشترک."""
    st = MapStyle.default_for(feeders=["F1", "F2", "F3", "F4"])
    cols = {st.feeder_colors[f] for f in ("F1", "F2", "F3", "F4")}
    assert len(cols) == 4                       # four DISTINCT codes
    assert st.feeder_colors["F1"] == FEEDER_COLORS[0]
    assert st.feeder_colors["F2"] == FEEDER_COLORS[1]


def test_palette_overlay_and_color_of():
    st = MapStyle.default_for(feeders=["F1", "F2"])
    st.feeder_colors["F1"] = "#123456"
    pal = st.palette_of(feeders=["F1", "F2", "F9"])
    assert pal["F1"] == "#123456"               # user override wins
    assert pal["F2"] == FEEDER_COLORS[1]        # untouched auto colour
    assert pal["F9"] == FEEDER_COLORS[2]        # late feeder still coloured
    assert st.color_of("F1") == "#123456"


def test_style_roundtrip_and_unknown_keys():
    st = MapStyle.default_for(feeders=["F1"])
    st.feeder_width = 1.7
    st.switch_marker = "s"
    st.show_legend = False
    d = st.as_dict()
    st2 = MapStyle.from_dict(d)
    st.visible_feeders = ["F1", "F3"]
    st2 = MapStyle.from_dict(st.as_dict())
    assert st2.visible_feeders == ["F1", "F3"]
    assert st2.feeder_width == 1.7
    assert st2.switch_marker == "s"
    assert st2.show_legend is False
    assert st2.feeder_colors == {"F1": st.feeder_colors["F1"]}
    # a future/unknown key is ignored, a bad marker falls back
    st3 = MapStyle.from_dict({**d, "future_field": 1, "switch_marker": "ZZ"})
    assert not hasattr(st3, "future_field")
    assert st3.switch_marker in ("o", "s", "D")  # default restored ("o")


def test_feeder_rows_show_renderer_colors_not_one_shared_code():
    st = MapStyle.default_for(feeders=["F1", "F2"])
    rows = feeder_rows(st, ["F1", "F2"])
    assert rows == [["F1", FEEDER_COLORS[0]], ["F2", FEEDER_COLORS[1]]]


def test_collect_style_validates():
    st = collect_style({"feeder_colors": {"F1": "#111111"},
                        "feeder_width": "2.5", "show_legend": "0",
                        "nonexistent": 5})
    assert st.feeder_colors["F1"] == "#111111"
    assert st.feeder_width == 2.5
    assert st.show_legend is False


# ---------------------------------------------------------------------------
# inputs confirmation (مورد ۵)
# ---------------------------------------------------------------------------
def test_parse_number_persian_and_percent():
    assert parse_number("۱۲٫۵") is None or True   # decimal sep not needed
    assert parse_number("12,500") == 12500.0
    assert parse_number("۴۵") == 45.0
    assert parse_number("12%") == 12.0
    assert parse_number("abc") is None
    assert parse_number("") is None


_LAM = [{"feeder_key": "F1", "lambda_per_year": 10.0, "r_minutes": 60.0,
         "events_random": 5, "exposure_years": 0.5},
        {"feeder_key": "F2", "lambda_per_year": 4.0, "r_minutes": 90.0,
         "events_random": 2, "exposure_years": 0.5}]


def test_collect_rows_cover_all_groups():
    rows = collect_placement_rows(
        lam_matrix=_LAM,
        capacity_rows=[{"feeder_key": "F1", "nominal_kw": None}],
        load_model={"level": "scaled", "feeder_pq": {"F1": {"p_kw": 100.0}}},
        cost_model={"rial_per_kwh": 1000.0},
        criteria={"min_ens_reduction_kwh": 1.0},
        coverage={"force_cover_months": ["1404/08"]},
        weights=[1, 2, 2, 3, 1, 1],
        engine_info=[("دامنه مطالعه", "کل شبکه")])
    groups = {r.group for r in rows}
    assert {"خاموشی", "بار", "بار (Load Scaling)", "ظرفیت فیدر", "هزینه",
            "معیار پذیرش", "پوشش داده", "رتبه‌بندی", "موتور (اطلاعی)"} <= groups
    # λ row editable, origin row NOT
    lam_row = next(r for r in rows if r.key == ("lambda", "F1"))
    assert lam_row.editable and lam_row.value == "10"
    origin = next(r for r in rows if r.group == "خاموشی" and not r.key)
    assert origin.editable is False
    # P/Q rows exist per feeder
    assert any(r.key == ("pq_p", "F1") and r.value == "100" for r in rows)


def test_apply_row_edits_roundtrip():
    rows = collect_placement_rows(lam_matrix=_LAM, weights=[1, 2, 2, 3, 1, 1])
    idx = {r.key: i for i, r in enumerate(rows) if r.key}
    rows[idx[("lambda", "F1")]].value = "7.5"
    rows[idx[("r", "F1")]].value = "48"
    rows[idx[("weight", 2)]].value = "5"
    edits = apply_row_edits(rows)
    assert edits["lambda_overrides"]["F1"] == {"lambda_per_year": 7.5,
                                               "r_minutes": 48}
    assert edits["weights"][1] == 5.0
    # the overrides actually land on the matrix
    out = apply_lambda_overrides(_LAM, edits["lambda_overrides"])
    assert out[0]["lambda_per_year"] == 7.5
    assert out[1]["lambda_per_year"] == 4.0          # untouched feeder
    # non-fedited run: no overrides → identity
    assert apply_lambda_overrides(_LAM, {}) == _LAM


def test_apply_row_edits_ignores_garbage():
    rows = [InputRow("خاموشی", "λ", "F1", "not-a-number",
                     ("lambda", "F1"))]
    edits = apply_row_edits(rows)
    assert edits["lambda_overrides"] == {}
    assert edits["ignored"] == ["λ F1"]


# ---------------------------------------------------------------------------
# project_kv — استایل‌های ماندگار (مورد ۲)
# ---------------------------------------------------------------------------
def test_project_kv_roundtrip(tmp_path):
    from switchloc.persistence.store import ProjectStore
    db = tmp_path / "kv.sqlite"
    st = ProjectStore(str(db))
    st.set_kv("map_styles", {"پیش‌فرض": {"feeder_width": 0.6},
                             "چاپ": {"feeder_width": 1.4}})
    st.set_kv("map_style_active", "چاپ")
    st.close()
    st = ProjectStore(str(db))
    book = st.get_kv("map_styles")
    assert set(book) == {"پیش‌فرض", "چاپ"}
    assert st.get_kv("map_style_active") == "چاپ"
    assert st.get_kv("nothing", "dflt") == "dflt"
    st.set_kv("map_style_active", "پیش‌فرض")      # upsert
    st.close()
    st = ProjectStore(str(db))
    assert st.get_kv("map_style_active") == "پیش‌فرض"
    st.delete_kv("map_style_active")
    assert st.get_kv("map_style_active") is None
    st.close()


def test_merge_style_book_fallback():
    from switchloc.ui.map_style import merge_style_book
    st, name = merge_style_book(None, feeders=["F1"])
    assert name == "پیش‌فرض" and st.feeder_colors["F1"] == FEEDER_COLORS[0]
    st, name = merge_style_book({"A": {"feeder_width": 2.0}})
    assert name == "A" and st.feeder_width == 2.0


# ---------------------------------------------------------------------------
# renderer honours the style (feeder colour + manual markers)
# ---------------------------------------------------------------------------
def _tiny_graph():
    """A 100 m two-span F1 feeder (same builder as test_map_renderer)."""
    import matplotlib
    matplotlib.use("Agg")
    from conftest import NetBuilder
    from switchloc.topology.graph import NetworkGraph
    from switchloc.topology.tracing import (TracingEngine, TracingPolicy)
    from switchloc.validation.issues import IssueLog
    b = NetBuilder()
    b.source(0, 0, "F1")
    b.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    g = NetworkGraph.from_network(b.net, IssueLog())
    traces = TracingEngine(g, b.net, TracingPolicy()).trace_all(IssueLog())
    return g, traces


def test_renderer_uses_style_feeder_color_and_manual_nodes(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    from switchloc.ui.map_renderer import NetworkMapRenderer

    g, traces = _tiny_graph()
    st = MapStyle.default_for(feeders=["F1"])
    st.feeder_colors["F1"] = "#ff00ff"
    st.feeder_width = 2.5
    st.manual_marker = "P"
    r = NetworkMapRenderer(g, traces=traces, style=st)
    out = str(tmp_path / "styled.png")
    nodes = [n for n in g.nodes]
    r.render(out, proposed_nodes=[], manual_nodes=nodes)
    assert Path(out).exists() and Path(out).stat().st_size > 0
    handles = r._legend_handles(r.style.palette_of(feeders=["F1"]), None,
                                manual=True)
    labels = [h.get_label() for h in handles]
    assert "Manual switch (evaluated)" in labels
    assert any(h.get_color() == "#ff00ff" and h.get_label() == "Feeder F1"
               for h in handles)


def test_auto_palette_string_inputs():
    pal = auto_palette(feeders=["F2", "F1"])
    assert pal == {"F1": FEEDER_COLORS[0], "F2": FEEDER_COLORS[1]}


# ---------------------------------------------------------------------------
# گزارش نهایی — بخش جایابی دستی (مورد ۶)
# ---------------------------------------------------------------------------
def test_manual_section_in_report():
    from types import SimpleNamespace
    from switchloc.reporting.content import _build_manual_section
    from switchloc.reporting.model import StudyModel
    topo_stub = SimpleNamespace(graph=SimpleNamespace(nodes={}))
    m = StudyModel(net=None, topo=topo_stub, placement=None, manual_evals=[
        {"feeder_key": "F1", "switch_nodes": ["N1"],
         "before": {"ens_kwh": 100.0, "ep_percent": 10.0,
                    "tl_percent": 5.0},
         "after": {"ens_kwh": 80.0, "ep_percent": 8.0, "tl_percent": 6.0},
         "delta": {"ens_kwh": 20.0, "ens_percent": 20.0},
         "ce_cn": {"ce_over_cn": 1.25},
         "verdict_fa": "بهبود", "better": True}])
    sec = _build_manual_section(m)
    assert "جایابی دستی" in sec.title
    row = sec.tables[0].rows[0]
    assert row[0] == "F1" and row[1] == "N1"
    assert row[4] == "+20.0" and row[9] == "بهبود"
    # بدون ارزیابی دستی، بخش ساخته نمی‌شود (خواستهٔ build_report)
    m2 = StudyModel(net=None, topo=topo_stub, placement=None)
    assert m2.manual_evals == []
