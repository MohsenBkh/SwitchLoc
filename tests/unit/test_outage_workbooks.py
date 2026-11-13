import hashlib
import sqlite3
import openpyxl
import pytest
from switchloc.persistence.outage_workbooks import save_workbook, list_workbooks, export_workbook
from switchloc.application.outage_service import OutageSettings, OutageService
from switchloc.persistence.store import ProjectStore


def _book(path, feeder):
    w = openpyxl.Workbook()
    w.active.append(['نام فيدر', 'علت قطع', 'تاريخ حادثه', 'مدت قطع', 'قطع کننده'])
    w.active.append([feeder, 'برخورد پرندگان', '1404/01/01', '01:00', 'بریکر'])
    w.save(path)


def test_sources_and_events_survive_save_as_without_external_files(tmp_path):
    project, backup = tmp_path/'original.sqlite', tmp_path/'copy.sqlite'
    source_a, source_b = tmp_path/'one.xlsx', tmp_path/'two.xlsx'
    _book(source_a, 1); _book(source_b, 2)
    expected = {str(k): hashlib.sha256(p.read_bytes()).hexdigest() for k, p in
                [('F1 - MESHKIN', source_a), ('F2 - MESHKIN', source_b)]}
    for key, source in [('F1 - MESHKIN', source_a), ('F2 - MESHKIN', source_b)]:
        save_workbook(str(project), key, source)
    source_a.unlink(); source_b.unlink()
    with sqlite3.connect(project) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)
    metadata = list_workbooks(str(backup))
    assert {k: v['sha256'] for k, v in metadata.items()} == expected
    files = {k: str(export_workbook(str(backup), k, tmp_path / (str(i)+'.xlsx')))
             for i, k in enumerate(sorted(metadata))}
    settings = OutageSettings(model_feeders=tuple(files), per_feeder_files=files,
        per_feeder_labels={k: 'project:' + metadata[k]['filename'] for k in files})
    result = OutageService(settings).run(out_db=str(backup))
    assert len(result.records) == 2
    store = ProjectStore(str(backup))
    try:
        data = store.load_outages()
    finally:
        store.close()
    assert len(data['events']) == 2
    assert {r['feeder_key'] for r in data['events']} == set(files)
    assert all(v.startswith('project:') for v in data['settings']['per_feeder_files'].values())


def test_invalid_workbook_does_not_replace_existing(tmp_path):
    db, good, bad = tmp_path/'project.sqlite', tmp_path/'good.xlsx', tmp_path/'bad.xlsx'
    _book(good, 1)
    before = save_workbook(str(db), 'F1', good)
    bad.write_text('not a workbook')
    with pytest.raises(ValueError):
        save_workbook(str(db), 'F1', bad)
    assert list_workbooks(str(db))['F1']['sha256'] == before['sha256']


def test_corruption_fails_explicitly(tmp_path):
    db, source = tmp_path/'project.sqlite', tmp_path/'good.xlsx'
    _book(source, 1)
    save_workbook(str(db), 'F1', source)
    with sqlite3.connect(db) as conn:
        conn.execute("update outage_workbook set content=?", (b'corrupted',))
    with pytest.raises(ValueError, match='SHA-256'):
        export_workbook(str(db), 'F1', tmp_path/'recovered.xlsx')
