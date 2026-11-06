# -*- coding: utf-8 -*-
"""Phase-3 acceptance tests — real 1405 outage list, end to end.

Covers: ingestion of the real workbook (data/outages_1405.xlsx), the
six-class distribution, the complete λ/r matrix (F1..F7 incl. F6=0),
the four official review levels of شکل ۵, persistence round-trip with a
deterministic run id, and the acceptance verdict (0 open Errors).
Skipped cleanly when the data file is absent.
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest                                       # noqa: E402

from switchloc.application.outage_service import (  # noqa: E402
    OutageService, OutageSettings)
from switchloc.domain.enums import OUTAGE_CLASSES   # noqa: E402
from switchloc.reliability.lambdar import feeder_lambda_r  # noqa: E402
from switchloc.reliability.outages import read_outage_workbook  # noqa: E402
from switchloc.reliability.classify import classify_all  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data" / "outages_1405.xlsx"

pytestmark = pytest.mark.skipif(not DATA.exists(),
                                reason="data/outages_1405.xlsx not present")


@pytest.fixture(scope="module")
def real_records():
    recs, stats = read_outage_workbook(DATA)
    classify_all(recs)
    return recs, stats


def test_reader_real_workbook(real_records):
    recs, stats = real_records
    # 896 + 1,104 real rows; the fully-empty spreadsheet rows are skipped
    assert len(recs) == 2000
    assert stats["rows_empty_skipped"] == 1962
    assert set(stats["sheets"]) == {"پست خلخال", "پست کمی آباد"}


def test_six_classes_complete_and_populated(real_records):
    recs, _ = real_records
    assert {r.outage_class for r in recs} <= set(OUTAGE_CLASSES)
    counts = {c: sum(1 for r in recs if r.outage_class == c)
              for c in OUTAGE_CLASSES}
    # every non-planned class has real members in the 1405 list
    for cls in OUTAGE_CLASSES:
        if cls != "برنامه‌ریزی‌شده":
            assert counts[cls] > 0, cls
    # the dominant real cause is fuse-cutout operation → coordination class
    # Head-of-feeder cutout events are held for engineer review instead of
    # being automatically treated as downstream protective coordination.
    assert counts["ناشی از هماهنگی حفاظتی"] > 500
    assert counts["داده ناکافی"] > 0
    # nothing classified silently: every event carries a rule id
    assert all(r.rule_id for r in recs)


def test_lambda_r_matrix_complete_f1_to_f7(real_records):
    recs, _ = real_records
    lam = {f.feeder_key: f for f in feeder_lambda_r(
        recs, model_feeders=tuple(f"F{i}" for i in range(1, 8)))}
    assert set(lam) == {f"F{i}" for i in range(1, 8)}
    # the workbook carries BOTH stations (خلخال bare numbers + کمی آباد
    # «nکمي …» names) — since the prefix-feeder fix both sheets join the
    # matrix: F6 = 171 (all from the کمی آباد sheet), F4 = 319 + 316 = 635
    assert lam["F6"].events_total == 171 and lam["F6"].lambda_per_year > 0
    assert lam["F4"].events_total == 635
    assert lam["F4"].lambda_per_year > 100
    # every λ/r row is internally consistent: U = λ × r / 60
    for f in lam.values():
        assert abs(f.u_hours - f.lambda_per_year * f.r_minutes / 60.0) < 1e-9


def test_level_tables_shape(real_records):
    from switchloc.reliability import lambdar
    recs, _ = real_records
    lam = lambdar.feeder_lambda_r(recs)
    levels = lambdar.as_dict(recs, lam)
    # سطح اول: dominant cause of the whole list
    assert levels["level1_by_cause"][0]["cause"] == \
        "عملکرد یا اشکال در کات اوت فیوز"
    # سطح دوم: no unmapped fault group in the real data
    assert all(d["fault_group"] != "نگاشت‌نشده"
               for d in levels["level2_by_fault_group"])
    # سطح سوم: both Jalali years; collection starts mid-1404 (month 07)
    ym = levels["level3_by_time"]["year_month_counts"]
    assert set(ym) == {"1404", "1405"}
    assert min(ym["1404"]) == "07" and 6 <= len(ym["1404"]) <= 12
    assert 8 <= len(ym["1405"]) <= 12
    assert all(k == f"{int(k):02d}" for k in ym["1404"])   # zero-padded keys
    # سطح چهارم: کمی آباد feeders present as raw scope, not in model keys
    # سطح چهارم: کمی آباد feeders now map to model keys too — F4 scope
    # is the merged khalkhal+kamiabad view (635 events), dominated by
    # the head fuse-cutout device
    f4 = [d for d in levels["level4_by_scope"]["feeder_device_counts"]
          if d["feeder"] == "F4"]
    assert f4 and sum(d["events"] for d in f4) == 635
    assert f4[0]["device"] == "کات اوت سرخط"           # dominant scope pair
    assert f4[0]["device"] == "کات اوت سرخط"           # dominant scope pair


def test_service_end_to_end_persist_deterministic(tmp_path):
    db = tmp_path / "outages.sqlite"
    s = OutageService(OutageSettings(user="acceptance-test"))
    r1 = s.run(str(DATA), out_db=str(db), report_dir=str(tmp_path))
    assert r1.verdict == "PASS"                       # every cause mapped
    assert r1.outage_run_id

    # report files
    assert (tmp_path / "phase3_outage_report.md").exists()
    assert (tmp_path / "phase3_outage_report.json").exists()

    # reload round-trip
    from switchloc.persistence.store import ProjectStore
    store = ProjectStore(db)
    loaded = store.load_outages(r1.outage_run_id)
    assert len(loaded["events"]) == len(r1.records)
    assert len(loaded["lambda_r"]) == 7
    assert loaded["verdict"] == "PASS"
    store.close()

    # deterministic run id on a second identical execution
    r2 = OutageService(OutageSettings(user="acceptance-test")).run(
        str(DATA), out_db=str(tmp_path / "outages2.sqlite"))
    assert r2.outage_run_id == r1.outage_run_id


def test_service_unmapped_cause_blocks_acceptance(tmp_path):
    from switchloc.reliability.outages import OutageRecord
    from switchloc.reliability.classify import classify_all

    # a workbook whose new cause is unknown → Error → FAIL (بند ۱۰)
    import openpyxl
    p = tmp_path / "new_cause.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "پست آزمون"
    ws.append(["شماره حادثه", "نام پست", "نام فيدر", "تاريخ حادثه",
               "زمان حادثه", "مدت قطع", "تاخير در وصل", "علت قطع",
               "قطع کننده", "انرژي توزيع نشده", "جريان زمان قطع",
               "توضيحات حادثه"])
    ws.append(["X1", "پست آزمون", "1", "1405/01/01", "08:00", "00:10:00",
               "00:01:00", "علت فرضی جدید کاملاً", "بریکر پست فوق توزیع",
               1, "", ""])
    wb.save(p)

    recs, _ = read_outage_workbook(p)
    classify_all(recs)
    assert recs[0].rule_id == "R-UNK-99"

    res = OutageService(OutageSettings(user="acceptance-test",
                                       persist=False)).run(str(p))
    assert res.verdict == "FAIL"
    assert res.report.code_counts.get("OUT-CAUSE-UNMAPPED", 0) >= 1
