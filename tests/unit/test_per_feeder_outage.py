# -*- coding: utf-8 -*-
"""Tests for per-feeder outage import (همزمان با شیپ‌فایل فیدرها) and the
coverage/exposure settings flowing through OutageService (نیاز ۸)."""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest                                          # noqa: E402

from switchloc.application.outage_service import (      # noqa: E402
    OutageService, OutageSettings)
from switchloc.reliability.outages import fixed_feeder_mapper  # noqa: E402

HEADERS = ["شماره حادثه", "نام پست", "نام فيدر", "تاريخ حادثه",
           "زمان حادثه", "مدت قطع", "تاخير در وصل", "علت قطع",
           "قطع کننده", "انرژي توزيع نشده", "جريان زمان قطع",
           "توضيحات حادثه"]


def _write_workbook(path, rows):
    """rows = [[col, ...], ...] under the official 1405 headers."""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "پست تست"
    ws.append(HEADERS)
    for r in rows:
        ws.append(r)
    wb.save(path)
    return str(path)


# ---------------------------------------------------------------------------
def test_fixed_mapper_assignes_whole_file_to_one_feeder():
    m = fixed_feeder_mapper("F3")
    assert m("any sheet", "1") == ("F3", True)
    assert m("any sheet", "") == ("F3", True)
    assert fixed_feeder_mapper("")("s", "x") == ("", False)


def test_per_feeder_files_flow(tmp_path):
    """دو فایل خاموشی جدا برای دو فیدر → ادغام و نگاشت صریح به همان فیدرها."""
    rows2 = [["2", "پست تست", "2", "1404/01/10", "08:00:00", "01:30:00",
              "", "عملکرد یا اشکال در کات اوت فیوز", "فیوز", "12", "", ""]
             for _ in range(2)]
    f2 = _write_workbook(tmp_path / "f2.xlsx", rows2)
    f5 = _write_workbook(tmp_path / "f5.xlsx", [
        ["5", "پست تست", "5", "1404/03/05", "10:00:00", "02:00:00",
         "", "شکست عایق یا برق‌گرفتگی خط", "رکلازر", "30", "", ""]])
    svc = OutageService(OutageSettings(
        user="test", persist=False, model_feeders=("F2", "F5"),
        per_feeder_files={"F2": f2, "F5": f5}))
    res = svc.run(out_db=None, report_dir=None)
    keys = {row.feeder_key for row in res.lambda_r}
    assert {"F2", "F5"} <= keys
    by = {row.feeder_key: row for row in res.lambda_r}
    assert by["F2"].events_total == 2
    assert by["F5"].events_total == 1
    # مواجهه واقعی: فروردین (۳۱) + خرداد (۳۱) = ۶۲ روز
    cov = res.levels["coverage"]
    assert cov["exposure_days"] == 62
    assert cov["missing_months"] == ["1404/02"]
    # F5's March record is not evidence that F2 was observed in March.
    assert by["F2"].lambda_per_year == pytest.approx(2 / (31 / 365.0))
    # شناسه‌های پایدار دو فایل تداخل ندارند
    ids = {r.id for r in res.records}
    assert len(ids) == len(res.records) == 3
    # منشأ per-feeder در آمار خواننده ثبت است
    srcs = {s["feeder_key"] for s in res.reader_stats["sources"]}
    assert srcs == {"F2", "F5"}


def test_service_requires_input():
    with pytest.raises(ValueError):
        OutageService(OutageSettings(persist=False)).run(out_db=None)


def test_coverage_settings_flow_through_service(tmp_path):
    """دوره پوشش صریح + ماه اجباری → مخرج λ کنترل‌شده توسط تنظیمات."""
    f = _write_workbook(tmp_path / "f1.xlsx", [
        ["1", "پست تست", "1", "1404/05/15", "09:00:00", "01:00:00",
         "", "عملکرد یا اشکال در کات اوت فیوز", "فیوز", "5", "", ""]])
    svc = OutageService(OutageSettings(
        user="test", persist=False, model_feeders=("F1",),
        per_feeder_files={"F1": f},
        coverage_start="1404/01", coverage_end="1404/06",
        force_cover_months=("1404/02", "1404/03", "1404/04")))
    res = svc.run(out_db=None, report_dir=None)
    cov = res.levels["coverage"]
    assert cov["start"] == [1404, 1] and cov["end"] == [1404, 6]
    # مؤثر = اردیبهشت/تیر/مرداد (اجباری) + مرداد رکورددار → ۳ ماه… رکورد در ماه ۵ است
    assert set(cov["effective_months"]) == {"1404/02", "1404/03", "1404/04",
                                            "1404/05"}
    assert cov["exposure_days"] == 31 * 4                 # ماه ۲،۳،۴،۵
    assert res.lambda_r[0].lambda_per_year == pytest.approx(1 / (124 / 365.0))
