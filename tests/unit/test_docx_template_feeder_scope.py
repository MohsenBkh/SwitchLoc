from types import SimpleNamespace


from switchloc.reporting.docx_template import _auto_fill_vars_from_model


FEEDER_ROWS = [
    {"feeder_key": "F1 - NORTH", "km": 10.0, "lambda_per_year": 1.0,
     "r_minutes": 30.0},
    {"feeder_key": "F2 - SOUTH", "km": 20.0, "lambda_per_year": 3.5,
     "r_minutes": 60.0},
]


def _model():
    return SimpleNamespace(
        topo=SimpleNamespace(traces=[
            SimpleNamespace(feeder_key="F1 - NORTH"),
            SimpleNamespace(feeder_key="F2 - SOUTH"),
        ]),
        placement=SimpleNamespace(
            ranking=SimpleNamespace(rows=[]),
            economics=SimpleNamespace(ens_before_kwh={}, ens_after_kwh={},
                                      comparisons=[]),
            n1=SimpleNamespace(eptl=[], rows15=[]),
            schemes=[], recommendation=[],
        ),
        eens_study={"study": {
            "feeders": [
                {"feeder_key": "F1 - NORTH", "baseline_eens_kwh": 1000,
                 "best": {"eens_kwh": 500}},
                {"feeder_key": "F2 - SOUTH", "baseline_eens_kwh": 2200,
                 "best": {"eens_kwh": 1100}},
            ],
            # Deliberately unrelated aggregate: must not override selected feeder.
            "baseline_eens_kwh": 9999,
            "best_eens_kwh": 8888,
        }},
        load_model={"feeder_pq": {
            "F1 - NORTH": {"p_kw": 1000, "q_kvar": 0},
            "F2 - SOUTH": {"p_kw": 3000, "q_kvar": 4000},
        }},
        feeder_table=lambda: FEEDER_ROWS,
        build_proposed=lambda: [],
    )


def test_reference_feeder_populates_its_own_specs_load_current_and_eens():
    vars_dict = {"__main_feeder_key": "F2 - SOUTH"}
    _auto_fill_vars_from_model(vars_dict, _model())

    assert vars_dict["طول فیدر"] == "20.00"
    assert vars_dict["عدد نرخ خرابی"] == "3.50"
    assert vars_dict["زمان تعمیر"] == "60.00"
    assert vars_dict["P_load (kW)"] == "3000.00"
    assert vars_dict["Q_load (kW)"] == "4000.00"
    assert vars_dict["جریان فیدر"] == f"{5000 / (3 ** 0.5 * 20):.2f}"
    assert vars_dict["EENS پایه"] == "2.20"
    assert vars_dict["EENS نهایی"] == "1.10"
    assert vars_dict["درصد کاهش"] == "50.00"


def test_missing_reference_feeder_does_not_fall_back_to_another_feeders_eens():
    vars_dict = {"__main_feeder_key": "F1 - NOT IN STUDY"}
    _auto_fill_vars_from_model(vars_dict, _model())

    assert vars_dict["EENS پایه"] == "—"
    assert vars_dict["EENS نهایی"] == "—"
    assert vars_dict["طول فیدر"] == "—"
    assert vars_dict["جریان فیدر"] == "—"
