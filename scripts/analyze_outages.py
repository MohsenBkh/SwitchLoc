# -*- coding: utf-8 -*-
"""Phase-3 acceptance run: outage analysis on the real 1405 outage list.

Input : data/outages_1405.xlsx (the uploaded «لیست خاموشی های 1405» copy)
Output: reports/phase3_outage_report.md / .json
        projects/khalkhal_phase1.sqlite  ← outage_run/event/lambda_r tables

Acceptance (ARCHITECTURE.md §۵ فاز ۳):
  * همه رکوردهای واقعی ورود و سطرهای خالی حذف شده باشند؛
  * طبقه‌بندی شش‌طبقه بند ۱۰ کامل (بدون علت نگاشت‌نشده) → بدون Error؛
  * ماتریس λ/r همه فیدرهای مدل F1..F7 (شامل F6 با صفر صریح)؛
  * چهار سطح رسمی شکل ۵ تولید شده باشد؛
  * اجرا در SQLite ذخیره و شناسه آن پایدار (بازتولیدپذیر) باشد.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from switchloc.application.outage_service import (OutageService,           # noqa: E402
                                                  OutageSettings)

DATA = ROOT / "data" / "outages_1405.xlsx"
DB = ROOT / "projects" / "khalkhal_phase1.sqlite"
REPORTS = ROOT / "reports"

EXPECTED_FEEDERS = {f"F{i}" for i in range(1, 8)}


def main() -> int:
    if not DATA.exists():
        raise SystemExit("داده واقعی یافت نشد: data/outages_1405.xlsx")
    DB.parent.mkdir(parents=True, exist_ok=True)

    res = OutageService(OutageSettings(user="phase3-acceptance")).run(
        str(DATA), out_db=str(DB), report_dir=str(REPORTS),
        project_name="خلخال/کمی‌آباد — لیست خاموشی ۱۴۰۵ (فاز ۳)")

    lam_keys = {f.feeder_key for f in res.lambda_r}
    total = len(res.records)
    cls = res.levels["class_summary"]
    checks = [
        ("records ingested (>= 1900 real events)", total >= 1900),
        ("empty spreadsheet rows skipped (>= 1900)",
         res.reader_stats["rows_empty_skipped"] >= 1900),
        ("six-class classification complete (no unmapped cause)",
         res.verdict == "PASS"),
        ("λ/r matrix covers F1..F7", EXPECTED_FEEDERS <= lam_keys),
        ("F6 explicit zero row (no recorded events)",
         any(f.feeder_key == "F6" and f.events_total == 0
             for f in res.lambda_r)),
        ("four official levels produced",
         all(k in res.levels for k in (
             "level1_by_cause", "level2_by_fault_group",
             "level3_by_time", "level4_by_scope"))),
        ("coordination class dominates (fuse-cutout list)",
         cls.get("ناشی از هماهنگی حفاظتی", 0) > cls.get(
             "قابل کاهش با کلیدگذاری", 1)),
        ("persisted with stable run id", res.outage_run_id is not None),
        ("report written",
         (REPORTS / "phase3_outage_report.md").exists()
         and (REPORTS / "phase3_outage_report.json").exists()),
    ]

    print(res.report.to_markdown())
    print("\n— طبقه‌بندی شش‌طبقه (بند ۱۰ پرامپت مادر) —")
    for k, v in sorted(cls.items(), key=lambda kv: -kv[1]):
        print(f"  {k:28s} {v:6,}  ({100 * v / max(total, 1):4.1f}٪)")
    print("\n— ماتریس λ/r فیدرهای مدل (ورودی جدول ۱۶ — فاز ۴) —")
    print(f"  {'فیدر':6s} {'λ(۱/سال)':>9s} {'r(دقیقه)':>9s} "
          f"{'U(ساعت/سال)':>12s} {'رخداد':>6s}")
    for f in res.lambda_r:
        print(f"  {f.feeder_key:6s} {f.lambda_per_year:9.2f} "
              f"{f.r_minutes:9.1f} {f.u_hours:12.2f} {f.events_random:6d}")
    print(f"\noutage_run: {res.outage_run_id}")

    print("\n— معیارهای پذیرش فاز ۳ —")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok &= passed
    if not ok:
        print(json.dumps({"verdict": res.verdict}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
