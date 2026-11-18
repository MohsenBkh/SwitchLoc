from types import SimpleNamespace

import pytest

from switchloc.placement.level2 import (
    Level2Settings, enumerate_location_plans, exact_plan_count)


def candidate(node, feeder):
    return SimpleNamespace(node=node, feeder_key=feeder, edge_id=f"e-{node}")


def test_exact_count_and_enumerator_cover_every_feasible_location_set():
    candidates = {
        "F1": [candidate("a", "F1"), candidate("b", "F1"), candidate("c", "F1")],
        "F2": [candidate("d", "F2"), candidate("e", "F2")],
    }
    budgets = {"F1": 2, "F2": 1}
    assert exact_plan_count(candidates, budgets, 0, 0) == 6
    plans = list(enumerate_location_plans(candidates, budgets, (), 0, 10))
    assert len(plans) == 6
    assert all(len(plan[0]["F1"]) == 2 and len(plan[0]["F2"]) == 1
               for plan in plans)


def test_open_tie_choices_are_enumerated_with_nc_choices():
    candidates = {"F1": [candidate("a", "F1"), candidate("b", "F1")]}
    ties = [SimpleNamespace(id="t1"), SimpleNamespace(id="t2")]
    assert exact_plan_count(candidates, {"F1": 1}, 2, 1) == 4
    plans = list(enumerate_location_plans(candidates, {"F1": 1}, ties, 1, 10))
    assert len(plans) == 4
    assert {p[1][0].id for p in plans} == {"t1", "t2"}


def test_exhaustive_search_fails_instead_of_silently_pruning():
    candidates = {"F1": [candidate(str(i), "F1") for i in range(10)]}
    with pytest.raises(ValueError, match="فضای جست‌وجوی دقیق"):
        list(enumerate_location_plans(candidates, {"F1": 3}, (), 0, 5))


def test_settings_require_a_real_decision_and_known_switch_types():
    with pytest.raises(ValueError, match="حداقل یک بودجه"):
        Level2Settings(nc_budget_by_feeder={}).validate()
    with pytest.raises(ValueError, match="switch_types"):
        Level2Settings(nc_budget_by_feeder={"F1": 1}, switch_types=("fuse",)).validate()
    Level2Settings(nc_budget_by_feeder={"F1": 1}).validate()
