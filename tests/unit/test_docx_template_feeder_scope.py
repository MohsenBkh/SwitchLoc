from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from docx import Document

from switchloc.reporting.docx_template import (_auto_fill_vars_from_model,
                                                _fill_tables_from_model,
                                                apply_template)
from switchloc.reporting.template_values import (
    FEEDER_VALUE_KEYS, refresh_feeder_template_caches,
)


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
                {"feeder_key": "F1 - NORTH", "baseline_eens_kwh_per_year": 1000,
                 "best_eens_kwh_per_year": 500,
                 "best": {"eens_kwh_per_year": 500}},
                {"feeder_key": "F2 - SOUTH", "baseline_eens_kwh_per_year": 2200,
                 "best_eens_kwh_per_year": 1100,
                 "best": {"eens_kwh_per_year": 1100}},
            ],
            # Deliberately unrelated aggregate: must not override selected feeder.
            "total_baseline_eens_kwh_per_year": 9999,
            "total_best_eens_kwh_per_year": 8888,
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


def test_eens_table_reads_current_serialized_per_feeder_field_names():
    doc = Document()
    table = doc.add_table(rows=2, cols=6)
    for cell, title in zip(
            table.rows[0].cells,
            ("فیدر", "طول", "بار", "EENS پایه", "EENS نهایی", "درصد کاهش")):
        cell.text = title

    _fill_tables_from_model(doc, _model(), primary_key="F2 - SOUTH",
                            display_name="فیدر جنوب")

    assert table.cell(1, 0).text == "فیدر جنوب"
    assert table.cell(1, 3).text == "2.20"
    assert table.cell(1, 4).text == "1.10"
    assert table.cell(1, 5).text == "50.00"


def test_missing_reference_feeder_does_not_fall_back_to_another_feeders_eens():
    vars_dict = {"__main_feeder_key": "F1 - NOT IN STUDY"}
    _auto_fill_vars_from_model(vars_dict, _model())

    assert vars_dict["EENS پایه"] == "—"
    assert vars_dict["EENS نهایی"] == "—"
    assert vars_dict["طول فیدر"] == "—"
    assert vars_dict["جریان فیدر"] == "—"


def test_sectionalizer_switch_count_and_coordinates_are_scoped_to_selected_feeder():
    model = _model()
    model.eens_study["study"]["feeders"] = [
        {"feeder_key": "F1 - NORTH", "baseline_eens_kwh_per_year": 1000,
         "best_eens_kwh_per_year": 500,
         "best": {"selected": [
             {"node": "NORTH-SW", "coord": [10, 20]},
             {"node": "NORTH-SW2", "coord": [30, 40]},
         ]}},
        {"feeder_key": "F2 - SOUTH", "baseline_eens_kwh_per_year": 2200,
         "best_eens_kwh_per_year": 1100,
         "best": {"selected": [
             {"node": "SOUTH-SW", "coord": [200, 300]},
         ]}},
    ]
    # Generic placement results intentionally disagree with the selected EENS
    # feeder; report generation must prefer the scoped EENS candidates.
    model.build_proposed = lambda: [SimpleNamespace(x=900, y=901, node="PLACEMENT-SW")]
    vars_dict = {
        "__main_feeder_key": "F2 - SOUTH",
        "تعداد کلید": "",
        "موقعیت نصب": "",
        "موقعیت": "",
        "مختصات کلیدی پیشنهادی": "",
    }

    _auto_fill_vars_from_model(vars_dict, model)

    assert vars_dict["تعداد کلید"] == "1"
    assert vars_dict["موقعیت نصب"] == "200, 300"
    assert vars_dict["موقعیت"] == "200, 300"
    assert vars_dict["مختصات کلیدی پیشنهادی"] == "200, 300"


def test_sectionalizer_fields_do_not_leak_when_selected_feeder_is_not_in_eens_study():
    model = _model()
    model.eens_study["study"]["feeders"][0]["best"] = {
        "selected": [{"node": "OTHER-SW", "coord": [10, 20]}]
    }
    model.build_proposed = lambda: [SimpleNamespace(x=900, y=901, node="PLACEMENT-SW")]
    vars_dict = {"__main_feeder_key": "F2 - SOUTH"}

    _auto_fill_vars_from_model(vars_dict, model)

    assert vars_dict["تعداد کلید"] == "—"
    assert vars_dict["موقعیت نصب"] == "F2 - SOUTH"
    assert vars_dict["مختصات کلیدی پیشنهادی"] == "F2 - SOUTH"


def test_eens_table_coordinate_uses_selected_feeder_not_last_study_feeder():
    model = _model()
    model.eens_study["study"]["feeders"] = [
        {"feeder_key": "F1 - NORTH", "baseline_eens_kwh_per_year": 1000,
         "best_eens_kwh_per_year": 500,
         "best": {"selected": [{"node": "NORTH-SW", "coord": [10, 20]}]}},
        {"feeder_key": "F2 - SOUTH", "baseline_eens_kwh_per_year": 2200,
         "best_eens_kwh_per_year": 1100,
         "best": {"selected": [{"node": "SOUTH-SW", "coord": [200, 300]}]}},
    ]
    model.build_proposed = lambda: []
    doc = Document()
    table = doc.add_table(rows=2, cols=7)
    for cell, title in zip(
            table.rows[0].cells,
            ("فیدر", "طول", "بار", "EENS پایه", "EENS نهایی", "درصد کاهش", "مختصات")):
        cell.text = title

    _fill_tables_from_model(doc, model, primary_key="F2 - SOUTH",
                            display_name="فیدر جنوب")

    assert table.cell(1, 6).text == "200, 300"


def test_sectionalizer_docx_export_uses_selected_feeder_end_to_end():
    model = _model()
    model.eens_study["study"]["feeders"] = [
        {"feeder_key": "F1 - NORTH", "baseline_eens_kwh_per_year": 1000,
         "best_eens_kwh_per_year": 500,
         "best": {"selected": [{"node": "NORTH-SW", "coord": [10, 20]}]}},
        {"feeder_key": "F2 - SOUTH", "baseline_eens_kwh_per_year": 2200,
         "best_eens_kwh_per_year": 1100,
         "best": {"selected": [{"node": "SOUTH-SW", "coord": [200, 300]}]}},
    ]
    template = (Path(__file__).resolve().parents[2]
                / "نمونه دفترچه مطالعات سکسیونر.docx")
    with TemporaryDirectory() as tmp:
        output = Path(tmp) / "sectionalizer-report.docx"
        apply_template(str(template), str(output),
                       {"__main_feeder_key": "F2 - SOUTH"},
                       study_model=model)
        exported = Document(str(output))

    spec = exported.tables[0]
    assert spec.cell(1, 0).text == "F2 - SOUTH"
    assert spec.cell(1, 1).text == "SOUTH"
    metrics = exported.tables[1]
    assert metrics.cell(1, 0).text == "F2 - SOUTH"
    assert metrics.cell(1, 3).text == "2.20"
    assert metrics.cell(1, 4).text == "1.10"
    assert metrics.cell(1, 6).text == "200, 300"


def test_feeder_refresh_updates_sectionalizer_cache_across_template_round_trip():
    # Model the dialog's separate recloser/sectionalizer caches. Switching
    # templates must not restore stale feeder-derived values, while unrelated
    # manually entered values remain template-local.
    defaults = {"یادداشت شخصی": "default"}
    caches = {
        "recloser": {"یادداشت شخصی": "recloser note", "EENS پایه": "1.00"},
        "sectionalizer": {"یادداشت شخصی": "sectionalizer note", "EENS پایه": "9.00",
                          "مختصات کلیدی پیشنهادی": "old coordinate"},
    }
    generated = {
        "EENS پایه": "2.20",
        "مختصات کلیدی پیشنهادی": "200, 300",
        "تعداد کلید": "1",
        "__main_feeder_key": "F2 - SOUTH",
    }

    visible = refresh_feeder_template_caches(generated, defaults, caches,
                                             FEEDER_VALUE_KEYS)

    # Simulate switching away and back: both caches now point at the selected
    # feeder, and each template's unrelated data is still preserved.
    assert caches["recloser"]["EENS پایه"] == "2.20"
    assert caches["sectionalizer"]["EENS پایه"] == "2.20"
    assert caches["sectionalizer"]["مختصات کلیدی پیشنهادی"] == "200, 300"
    assert visible["مختصات کلیدی پیشنهادی"] == "200, 300"
    assert caches["recloser"]["یادداشت شخصی"] == "recloser note"
    assert caches["sectionalizer"]["یادداشت شخصی"] == "sectionalizer note"
    assert "__main_feeder_key" not in caches["sectionalizer"]
