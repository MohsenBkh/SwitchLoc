import pytest

from switchloc.reliability.power_flow import (
    PowerFlowSettings, solve_radial_power_flow)
from switchloc.reliability.switch_placement import RadialTree
from switchloc.topology.graph import GraphEdge, NetworkGraph


def tiny_feeder():
    graph = NetworkGraph()
    graph.edges["e0"] = GraphEdge(
        id="e0", branch_id="b0", seq=0, a="source", b="load",
        length_m=1000.0, kind="line_aerial", feeder_hint="F1",
        conductor="AAAC", section_mm2=50.0, installation="overhead")
    graph.adj["source"].append(("load", "e0"))
    graph.adj["load"].append(("source", "e0"))
    tree = RadialTree(root="source", order=["source", "load"],
                      parent={"source": None, "load": "source"},
                      parent_edge={"source": None, "load": "e0"},
                      extra_edge_ids=[], unreachable_edge_ids=[])
    settings = PowerFlowSettings(
        base_voltage_kv=11.0,
        voltage_min_pu=0.90,
        voltage_max_pu=1.05,
        line_catalog={"AAAC|50|OVERHEAD": {
            "r_ohm_per_km": 0.3, "x_ohm_per_km": 0.2,
            "max_current_a": 20.0}},
    )
    return graph, tree, settings


def test_balanced_radial_flow_converges_and_reports_power_and_losses():
    graph, tree, settings = tiny_feeder()
    result = solve_radial_power_flow(
        graph, tree, feeder_key="F1",
        loads_kw={"load": 100.0}, loads_kvar={"load": 50.0},
        transformer_kva_by_node={"load": 200.0}, settings=settings)

    assert result.converged
    assert result.feasible
    assert result.constraints_complete
    assert result.iterations >= 1
    assert 0.99 < result.min_voltage_pu < 1.0
    assert result.max_voltage_pu == pytest.approx(1.0)
    assert result.total_load_kw == pytest.approx(100.0)
    assert result.total_load_kvar == pytest.approx(50.0)
    assert result.losses_kw > 0
    assert result.branch_currents_a["e0"] > 0
    assert result.source_p_kw > result.total_load_kw
    assert result.transformer_loading_pct["load"] == pytest.approx(
        (100.0**2 + 50.0**2) ** 0.5 / 200.0 * 100.0)


def test_line_and_transformer_overloads_are_explicit_infeasibilities():
    graph, tree, settings = tiny_feeder()
    settings.line_catalog["AAAC|50|OVERHEAD"]["max_current_a"] = 2.0
    result = solve_radial_power_flow(
        graph, tree, feeder_key="F1", loads_kw={"load": 100.0},
        loads_kvar={"load": 50.0}, transformer_kva_by_node={"load": 100.0},
        settings=settings)

    assert not result.feasible
    kinds = {v["kind"] for v in result.violations}
    assert kinds == {"line_overload", "transformer_overload"}
    assert result.max_line_loading_pct > 100
    assert result.max_transformer_loading_pct > 100


def test_missing_line_impedance_is_not_silently_estimated():
    graph, tree, settings = tiny_feeder()
    settings.line_catalog = {}
    with pytest.raises(ValueError, match="امپدانس/حد جریان"):
        solve_radial_power_flow(
            graph, tree, feeder_key="F1", loads_kw={"load": 100.0},
            transformer_kva_by_node={"load": 200.0}, settings=settings)


def test_meshed_feeder_is_rejected_instead_of_using_a_spanning_tree():
    graph, tree, settings = tiny_feeder()
    tree.extra_edge_ids = ["loop-edge"]
    with pytest.raises(ValueError, match="فقط برای فیدر شعاعی"):
        solve_radial_power_flow(
            graph, tree, feeder_key="F1", loads_kw={"load": 100.0},
            transformer_kva_by_node={"load": 200.0}, settings=settings)


def test_missing_transformer_rating_marks_constraints_incomplete():
    graph, tree, settings = tiny_feeder()
    result = solve_radial_power_flow(
        graph, tree, feeder_key="F1", loads_kw={"load": 100.0},
        transformer_kva_by_node={}, settings=settings)
    assert not result.feasible
    assert not result.constraints_complete
    assert result.missing_transformer_limits == ["load"]
