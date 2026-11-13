"""Outages must survive a SQLite Save As backup and project reopen."""
import sqlite3
import openpyxl
from switchloc.application.outage_service import OutageService, OutageSettings
from switchloc.persistence.store import ProjectStore


def test_processed_outages_survive_project_backup(tmp_path):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(['نام فيدر', 'علت قطع', 'تاريخ حادثه', 'مدت قطع', 'قطع کننده', 'انرژي توزيع نشده'])
    sheet.append(['1', 'برخورد پرندگان', '1404/01/01', '01:00', 'بریکر', 1.5])
    excel = tmp_path / 'outages.xlsx'
    book.save(excel)
    original, saved = tmp_path / 'project.sqlite', tmp_path / 'copy.sqlite'
    settings = OutageSettings(model_feeders=('F1 - MESHKIN',),
                              per_feeder_files={'F1 - MESHKIN': str(excel)})
    result = OutageService(settings).run(out_db=str(original))
    assert len(result.records) == 1
    with sqlite3.connect(original) as src, sqlite3.connect(saved) as dest:
        src.backup(dest)
    store = ProjectStore(str(saved))
    try:
        reopened = store.load_outages()
    finally:
        store.close()
    assert len(reopened['events']) == 1
    assert reopened['events'][0]['event_no'] == result.records[0].event_no
    assert reopened['lambda_r'][0]['feeder_key'] == 'F1 - MESHKIN'
    assert reopened['settings']['energy_unit'] == 'mwh'
