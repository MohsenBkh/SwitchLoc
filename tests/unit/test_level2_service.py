from dataclasses import replace

import pytest

from switchloc.application.level2_placement_service import (
    Level2AppSettings, Level2PlacementService, level2_settings_from_data)
from switchloc.domain.entities import StudyRunMeta
from switchloc.placement.level2 import Level2Settings
from switchloc.reliability.power_flow import PowerFlowSettings
from switchloc.validation.issues import IssueLog

from conftest import NetBuilder


def test_level2_settings_can_be_built_from_direct_form_data():
    settings = level2_settings_from_data({
        "level2": {"nc_budget_by_feeder": {"F1": 1}, "no_budget": 0,
                   "switch_types": ["recloser"]},
        "power_flow": {"base_voltage_kv": 20.0,
                       "type_ampacity_a": {"35-Al_St": 200.0}},
        "load_model": {"level": "scaled",
                       "feeder_pq": {"F1": {"p_kw": 40, "q_kvar": 12}}},
        "reliability": {"failure_rates": {"F1": 2.0}},
        "feeder_keys": ["F1"],
    })
    assert settings.level2.nc_budget_by_feeder == {"F1": 1}
    assert settings.power_flow.type_ampacity_a == {"35-Al_St": 200.0}
    assert settings.load_model["feeder_pq"]["F1"]["p_kw"] == 40
    assert settings.reliability["failure_rates"]["F1"] == 2.0
    assert settings.feeder_keys == ("F1",)


def test_level2_service_runs_exact_all_type_search_with_load_flow(tmp_path):
    builder = NetBuilder()
    builder.source(0, 0, "F1")
    branch = builder.line([(0, 0), (100, 0), (200, 0)], feeder="F1")
    branch.conductor = "(ACSR) آلومينيوم – فولاد"
    branch.section_mm2 = 35.0
    branch.installation = "سيم لخت"
    builder.transformer(200, 0, kva=200, feeder="F1")
    builder.source(1000, 0, "F2")
    branch2 = builder.line([(1000, 0), (1100, 0), (1200, 0)], feeder="F2")
    branch2.conductor = "(ACSR) آلومينيوم – فولاد"
    branch2.section_mm2 = 35.0
    branch2.installation = "سيم لخت"
    builder.transformer(1200, 0, kva=200, feeder="F2")

    db = tmp_path / "level2.sqlite"
    from switchloc.persistence.store import ProjectStore
    store = ProjectStore(db)
    store.save_network(
        builder.net, IssueLog(),
        StudyRunMeta(project_name="level2-test", started_at="2026-11-14T00:00:00Z",
                     user="test", algo_version="test"))
    store.close()

    settings = Level2AppSettings(
        level2=Level2Settings(nc_budget_by_feeder={"F1": 1},
                              max_search_states=100),
        power_flow=PowerFlowSettings(
            base_voltage_kv=20.0, voltage_min_pu=0.9, voltage_max_pu=1.1,
            type_ampacity_a={"35-Al_St": 200.0}),
        load_model={"level": "scaled", "feeder_pq": {"F1": {"p_kw": 100, "q_kvar": 30}}},
        reliability={
            "failure_rates": {"F1": 2.0},
            "repair_times_min": {"F1": 50.0},
            "transient_rates": {"F1": 0.1},
            "engine": {"min_candidate_depth": 1,
                       "max_downstream_load_ratio": 1.0,
                       "restoration_model": "uniform",
                       "repair_time_min": 50.0,
                       "restoration_time_min": 20.0},
        },
        feeder_keys=("F1",),
    )
    result = Level2PlacementService(settings).run(str(db))

    assert result.status == "ok"
    assert result.feeder_keys == ["F1"]
    assert set(result.best_plans) == {"recloser", "sectionalizer", "disconnector"}
    assert all(result.best_plans[k] is not None for k in result.best_plans)
    assert all(result.feasible_plan_count_by_type[k] > 0 for k in result.best_plans)
    assert result.flow_baseline[0]["status"] == "feasible"
    assert result.search_state_count == 3
    assert all(set(row) == {"F1"} for row in result.baseline_eens_by_type.values())

    no_ties_settings = replace(
        settings,
        level2=Level2Settings(nc_budget_by_feeder={"F1": 1}, no_budget=1,
                              max_search_states=100))
    with pytest.raises(ValueError, match="کاندید tie معتبر"):
        Level2PlacementService(no_ties_settings).run(str(db))
