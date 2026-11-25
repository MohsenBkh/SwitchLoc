from openpyxl import Workbook

from switchloc.reliability.feeder_load_import import read_feeder_load_workbook


def test_reads_persian_mw_headers_and_converts_to_kw(tmp_path):
    path = tmp_path / "loads.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Feeder Report"
    ws.append(["نام فیدر در GIS", "پیک توان اکتیو (MW)",
               "توان راکتیو در لحظه پیک (MVAr)"])
    ws.append(["F1 - SAMPLE", 7.783, 1.982])
    wb.save(path)

    result = read_feeder_load_workbook(str(path))

    assert result.rows_read == 1
    assert result.feeder_pq == {
        "F1 - SAMPLE": {"p_kw": 7783.0, "q_kvar": 1982.0}}
    assert not result.warnings


def test_conflicting_duplicate_is_not_silently_overwritten(tmp_path):
    path = tmp_path / "duplicates.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["نام فیدر در GIS", "پیک توان اکتیو (MW)",
               "توان راکتیو در لحظه پیک (MVAr)"])
    ws.append(["F7 - NORTH", 4.01, 2.038])
    ws.append(["F7 - NORTH", 3.268, 1.796])
    ws.append(["F8 - NORTH", 2.0, 0.5])
    wb.save(path)

    result = read_feeder_load_workbook(str(path))

    assert "F7 - NORTH" not in result.feeder_pq
    assert result.feeder_pq["F8 - NORTH"] == {"p_kw": 2000.0,
                                                 "q_kvar": 500.0}
    assert any("F7 - NORTH" in warning for warning in result.warnings)
