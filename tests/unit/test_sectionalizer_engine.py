# -*- coding: utf-8 -*-
"""موتور بهینه‌سازی سکشنالایزر و کاهش EENS — آزمون‌های تحلیلی.

لنگرهای عددی از خودِ فرمول کد مرجع محاسبه شده‌اند (نه از خروجی برنامه):

* فیدر یک‌قطعه‌ای:  EENS = (λ/60)·T_rep·P_total
* دو قطعهٔ مساوی:    EENS = 2·(λ/120)·[T_rep·P/2 + T_rest·P/2]
* مدل جهت‌دار:       قطعهٔ بالادست بی‌برق نمی‌شود.
"""
import math
from types import SimpleNamespace

import pytest

from switchloc.reliability.sectionalizer import (SectionalizerEngine,
                                                 SectionalizerSettings,
                                                 build_radial_tree,
                                                 build_sections,
                                                 compute_eens_kwh,
                                                 eens_single_section_kwh,
                                                 length_weighted_lambdas,
                                                 theoretical_eens_kwh)
from switchloc.topology.graph import NetworkGraph
from switchloc.topology.tracing import TracingEngine, TracingPolicy
from switchloc.validation.issues import IssueLog

from conftest import NetBuilder


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def line_network(n_nodes: int = 11, step: float = 100.0, load_kw: float = 100.0,
                 with_switch_at: int | None = None):
    """فیدر خطی: منبع در ابتدا، n گره هر step متر، ترانس روی هر گره.

    گرهٔ کلید موجود (``with_switch_at``) ترانس نمی‌گیرد: در SwitchLoc
    تجهیز روی ترمینال ترانس مرز زون نیست (TOPO-POL-06) و therefore
    نمی‌تواند قطعه‌بندی موجود بسازد.
    """
    b = NetBuilder()
    b.source(0, 0, "F1")
    pts = [(i * step, 0.0) for i in range(n_nodes)]
    b.line(pts, feeder="F1")
    for i in range(1, n_nodes):
        if with_switch_at is not None and i == with_switch_at:
            continue
        b.transformer(i * step, 0.0, 400, feeder="F1")
    if with_switch_at is not None:
        x = with_switch_at * step
        b.switch(x, 0.0, feeder="F1")
    graph = NetworkGraph.from_network(b.net, IssueLog())
    traces = TracingEngine(graph, b.net, TracingPolicy()).trace_all(IssueLog())
    node_load = {n: load_kw for n, tids in graph.transformer_ids_at.items() if tids}
    return b.net, graph, traces, node_load


def node_at_depth(tree, depth):
    return next(n for n in tree.order if tree.depth.get(n) == depth)


# ---------------------------------------------------------------------------
# فرمول‌ها
# ---------------------------------------------------------------------------
def test_single_section_matches_reference_formula():
    assert eens_single_section_kwh(1000.0, 30.0, 50.0) == pytest.approx(25000.0)
    assert theoretical_eens_kwh(1000.0, 30.0, 50.0) == pytest.approx(25000.0)


def test_length_weighted_lambdas_sum_to_feeder_lambda():
    lam = length_weighted_lambdas([500.0, 300.0, 200.0], 30.0)
    assert sum(lam) == pytest.approx(30.0)
    assert lam[0] > lam[1] > lam[2]
    assert length_weighted_lambdas([0.0, 0.0], 30.0) == [0.0, 0.0]


def test_two_equal_sections_analytic_value():
    sections = [SimpleNamespace(load_kw=500.0, length_m=500.0, index=0,
                                parent_index=None, cut_node=None),
                SimpleNamespace(load_kw=500.0, length_m=500.0, index=1,
                                parent_index=0, cut_node="x")]
    eens = compute_eens_kwh(sections, failure_rate=30.0, total_length_m=1000.0,
                            total_load_kw=1000.0, repair_time_min=50.0,
                            restoration_time_min=20.0)
    # 2 × (15/60) × [50×500 + 20×500]
    assert eens == pytest.approx(17500.0)


def test_directional_model_ignores_upstream_load():
    sections = [SimpleNamespace(load_kw=500.0, length_m=500.0, index=0,
                                parent_index=None, cut_node=None),
                SimpleNamespace(load_kw=500.0, length_m=500.0, index=1,
                                parent_index=0, cut_node="x")]
    eens = compute_eens_kwh(sections, failure_rate=30.0, total_length_m=1000.0,
                            total_load_kw=1000.0, repair_time_min=50.0,
                            restoration_time_min=20.0,
                            restoration_model="directional")
    # خطای قطعهٔ ریشه → بار پایین‌دست با زمان بازیابی:
    #   (15/60)×[50×500 + 20×500] = 8750
    # خطای قطعهٔ پایین‌دست → فقط همان قطعه (بالادست بی‌برق نمی‌شود):
    #   (15/60)×50×500 = 6250
    assert eens == pytest.approx(8750.0 + 6250.0)


def test_backup_capacity_limits_restoration():
    sections = [SimpleNamespace(load_kw=500.0, length_m=500.0, index=0,
                                parent_index=None, cut_node=None),
                SimpleNamespace(load_kw=500.0, length_m=500.0, index=1,
                                parent_index=0, cut_node="x")]
    unlimited = compute_eens_kwh(sections, failure_rate=30.0,
                                 total_length_m=1000.0, total_load_kw=1000.0,
                                 repair_time_min=50.0, restoration_time_min=20.0)
    limited = compute_eens_kwh(sections, failure_rate=30.0,
                               total_length_m=1000.0, total_load_kw=1000.0,
                               repair_time_min=50.0, restoration_time_min=20.0,
                               backup_kw=0.0)
    assert limited > unlimited
    # بدون ظرفیت پشتیبان، همهٔ بار با زمان تعمیر برمی‌گردد:
    assert limited == pytest.approx(30.0 / 60.0 * 50.0 * 1000.0)


def test_invalid_settings_are_rejected():
    with pytest.raises(ValueError):
        SectionalizerSettings(restoration_model="magic")
    with pytest.raises(ValueError):
        SectionalizerSettings(max_downstream_load_ratio=1.5)
    with pytest.raises(ValueError):
        SectionalizerSettings(total_failure_rate_per_year=-1.0)


# ---------------------------------------------------------------------------
# درخت شعاعی و قطعه‌بندی
# ---------------------------------------------------------------------------
def test_radial_tree_sums_load_and_length():
    _net, graph, traces, node_load = line_network()
    tree = build_radial_tree(graph, traces[0], node_load)
    assert len(tree.order) == 11
    assert tree.total_load_kw == pytest.approx(1000.0)
    assert tree.total_length_m == pytest.approx(1000.0)
    assert not tree.extra_edge_ids


def test_tree_section_loads_are_exclusive_and_complete():
    _net, graph, traces, node_load = line_network()
    tree = build_radial_tree(graph, traces[0], node_load)
    cut = node_at_depth(tree, 6)
    sections = build_sections(tree, [cut])
    assert len(sections) == 2
    assert sum(s.load_kw for s in sections) == pytest.approx(1000.0)
    assert sum(s.length_m for s in sections) == pytest.approx(1000.0)
    assert sections[0].load_kw == pytest.approx(500.0)


def test_nested_cuts_do_not_double_count():
    _net, graph, traces, node_load = line_network(n_nodes=21, load_kw=50.0)
    tree = build_radial_tree(graph, traces[0], node_load)
    outer = node_at_depth(tree, 5)
    inner = node_at_depth(tree, 10)
    sections = build_sections(tree, [outer, inner])
    assert len(sections) == 3
    assert sum(s.load_kw for s in sections) == pytest.approx(1000.0)
    assert sum(s.length_m for s in sections) == pytest.approx(2000.0)
    # زیرقطعهٔ درونی از قطعهٔ بیرونی کم شده است (بدون شمارش مضاعف)
    by_cut = {s.cut_node: s for s in sections}
    assert by_cut[outer].load_kw == pytest.approx(250.0)
    assert by_cut[outer].length_m == pytest.approx(500.0)
    assert by_cut[inner].load_kw == pytest.approx(550.0)
    assert by_cut[inner].length_m == pytest.approx(1100.0)


# ---------------------------------------------------------------------------
# موتور
# ---------------------------------------------------------------------------
def test_engine_baseline_is_analytic_when_no_existing_switch():
    _net, graph, traces, node_load = line_network()
    study = SectionalizerEngine(SectionalizerSettings(max_sectionalizers=3)) \
        .run(graph, traces, node_load)
    f = study.feeders[0]
    assert f.baseline_eens_kwh == pytest.approx(25000.0)
    assert f.theoretical_eens_kwh == pytest.approx(25000.0)
    assert f.steps and f.best is not None
    assert f.best.eens_kwh < f.baseline_eens_kwh


def test_greedy_steps_are_monotone_and_bounded():
    _net, graph, traces, node_load = line_network()
    study = SectionalizerEngine(SectionalizerSettings(max_sectionalizers=3)) \
        .run(graph, traces, node_load)
    f = study.feeders[0]
    eens = [f.baseline_eens_kwh] + [s.eens_kwh for s in f.steps]
    assert all(b <= a + 1e-9 for a, b in zip(eens, eens[1:]))
    assert len(f.steps) <= 3
    for step in f.steps:
        assert step.improvement_percent >= 0.0
        assert len(step.selected) == step.count


def test_three_level_nesting_is_not_double_counted():
    """زنجیرهٔ ریشه → a → b → c: بار/طولِ c نباید دو بار شمرده شود."""
    _net, graph, traces, node_load = line_network(n_nodes=21)
    tree = build_radial_tree(graph, traces[0], node_load)
    order = list(tree.order)
    assert len(order) == 21
    cuts = {order[6], order[12], order[18]}
    sections = build_sections(tree, cuts)
    assert len(sections) == 4
    assert sum(s.load_kw for s in sections) == pytest.approx(tree.total_load_kw)
    assert sum(s.length_m for s in sections) == pytest.approx(tree.total_length_m)
    by_cut = {s.cut_node: s for s in sections}
    a, b, c = order[6], order[12], order[18]
    # عمیق‌ترین قطعه همان زیردرخت خودش است؛ والدها زیرقطعه‌ها را کم کرده‌اند
    assert by_cut[c].load_kw == pytest.approx(tree.subtree_load_kw[c])
    assert by_cut[b].load_kw == pytest.approx(
        tree.subtree_load_kw[b] - tree.subtree_load_kw[c])
    assert by_cut[a].load_kw == pytest.approx(
        tree.subtree_load_kw[a] - tree.subtree_load_kw[b])
    assert by_cut[a].parent_index == 0


def test_existing_switch_defines_baseline_sections():
    """کلید موجود → EENS پایهٔ بهتر از فیدر یک‌قطعه‌ای (بهبود کد مرجع)."""
    _net, graph, traces, node_load = line_network(with_switch_at=6)
    study = SectionalizerEngine(SectionalizerSettings(max_sectionalizers=1)) \
        .run(graph, traces, node_load, net=_net)
    f = study.feeders[0]
    assert len(f.baseline_sections) == 2
    assert len(f.existing_cut_nodes) == 1
    # گره کلید ترانس ندارد → بار کل ۹۰۰ kW؛ دو قطعهٔ ۵۰۰/۴۰۰ kW با طول ۵۰۰/۵۰۰
    # EENS = (15/60)[50×500 + 20×400] + (15/60)[50×400 + 20×500] = 15750
    assert f.baseline_eens_kwh == pytest.approx(15750.0)
    assert f.baseline_eens_kwh < f.theoretical_eens_kwh


def test_existing_switch_can_be_ignored_for_reference_comparison():
    net, graph, traces, node_load = line_network(with_switch_at=6)
    study = SectionalizerEngine(SectionalizerSettings(
        max_sectionalizers=1, use_existing_switches=False)) \
        .run(graph, traces, node_load, net=net)
    f = study.feeders[0]
    assert len(f.baseline_sections) == 1
    assert f.baseline_eens_kwh == pytest.approx(f.theoretical_eens_kwh)


def test_candidate_filters_depth_ratio_and_devices():
    net, graph, traces, node_load = line_network(with_switch_at=6)
    settings = SectionalizerSettings(max_sectionalizers=1, min_candidate_depth=4,
                                     max_downstream_load_ratio=0.5)
    study = SectionalizerEngine(settings).run(graph, traces, node_load, net=net)
    f = study.feeders[0]
    assert f.rejected["too_shallow"] > 0
    assert f.rejected["over_load_ratio"] > 0
    assert f.rejected["already_has_device"] > 0
    for c in f.candidates:
        assert c.depth >= 4
        assert c.downstream_ratio <= 0.5 + 1e-12
        assert c.downstream_load_kw > 0


def test_candidates_carry_coordinates_and_zone_ids():
    _net, graph, traces, node_load = line_network()
    study = SectionalizerEngine(SectionalizerSettings(max_sectionalizers=1)) \
        .run(graph, traces, node_load)
    for c in study.feeders[0].candidates:
        assert c.coord is not None
        assert math.isfinite(c.coord[0]) and math.isfinite(c.coord[1])


def test_non_radial_graph_is_reported_and_still_optimized():
    """حلقه/خط موازی: کد مرجع کل اجرا را رد می‌کرد؛ اینجا با هشدار ادامه."""
    b = NetBuilder()
    b.source(0, 0, "F1")
    pts = [(i * 100.0, 0.0) for i in range(6)]
    b.line(pts, feeder="F1")
    # یال اضافی (حلقه) بین گره ۱ و گره ۵ → گراف غیردرختی
    b.line([(100.0, 0.0), (300.0, 60.0), (500.0, 0.0)], feeder="F1")
    for i in range(1, 6):
        b.transformer(i * 100.0, 0.0, 400.0, feeder="F1")
    graph = NetworkGraph.from_network(b.net, IssueLog())
    traces = TracingEngine(graph, b.net, TracingPolicy()).trace_all(IssueLog())
    node_load = {n: 100.0 for n, tids in graph.transformer_ids_at.items() if tids}
    f = SectionalizerEngine(SectionalizerSettings(max_sectionalizers=2)) \
        .run(graph, traces, node_load).feeders[0]
    assert f.radial is False
    assert f.extra_edges >= 1
    # طول کل شامل یال اضافی است (هیچ طولی گم نمی‌شود)
    trace_len = sum(graph.edges[e].length_m for e in traces[0].edges)
    assert f.line_length_m == pytest.approx(trace_len)


def test_feeder_selection_limits_the_study():
    _net, graph, traces, node_load = line_network()
    study = SectionalizerEngine().run(graph, traces, node_load,
                                      feeders=["NOPE"])
    assert study.feeders == []


def test_study_dict_and_markdown_are_json_safe():
    _net, graph, traces, node_load = line_network()
    study = SectionalizerEngine(SectionalizerSettings(max_sectionalizers=2)) \
        .run(graph, traces, node_load)
    import json
    payload = json.loads(json.dumps(study.as_dict(), default=str))
    assert payload["feeders"][0]["feeder_key"] == "F1"
    md = study.to_markdown()
    assert "بهینه‌سازی سکشنالایزر" in md and "| F1 |" in md
