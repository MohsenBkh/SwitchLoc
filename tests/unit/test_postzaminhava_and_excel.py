from pathlib import Path

from openpyxl import load_workbook
from switchloc.geography.places import PlaceGazetteer
from switchloc.reporting.workbook import export_dashboard_feeder_indices


def test_bundled_named_substations_have_auditable_coordinates():
    path = Path(__file__).resolve().parents[2] / 'data/geography/ardabil_places.sqlite'
    bank = PlaceGazetteer(path)
    stats = bank.stats()
    assert stats['by_source']['postzaminhava:ELWADS'] >= 8900
    assert stats['by_source']['postzaminhava:ELWGDS'] >= 500
    matches = bank.search('پست كم تلفات قلپنلو')
    assert any(m.place.source == 'postzaminhava:ELWADS' for m in matches)


def test_dashboard_indices_export_without_placement(tmp_path):
    dash = {'feeders': [{'feeder_key': 'F10 - RADIO', 'km': 50.5,
                         'transformers': 3, 'saidi': 14.25, 'ens_per_year_kwh': 22.0}],
            'outage': {'service_indices': {}}}
    path = tmp_path / 'indices.xlsx'
    export_dashboard_feeder_indices(dash, str(path))
    wb = load_workbook(path, data_only=True)
    sheet = wb['شاخصهای فیدرها'] if 'شاخصهای فیدرها' in wb else wb['شاخص‌های فیدرها']
    rows = list(sheet.values)
    assert any('F10 - RADIO' in r and 14.2 in r for r in rows)


def test_clear_study_preserves_unrelated_project_data(tmp_path):
    from switchloc.persistence.store import ProjectStore
    from switchloc.application.switch_placement_service import clear_persisted_study
    path = str(tmp_path / 'project.sqlite')
    store = ProjectStore(path)
    store.set_kv('sectionalizer_study', {'study': {'result': 5}})
    store.set_kv('sectionalizer_settings', {'switch_type': 'recloser'})
    store.set_kv('unrelated', {'value': 1})
    store.close()
    clear_persisted_study(path)
    store = ProjectStore(path)
    try:
        assert store.get_kv('sectionalizer_study') is None
        assert store.get_kv('sectionalizer_settings')['switch_type'] == 'recloser'
        assert store.get_kv('unrelated') == {'value': 1}
    finally:
        store.close()
