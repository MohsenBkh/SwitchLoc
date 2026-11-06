# -*- coding: utf-8 -*-
"""OutageService — orchestration of the Phase-3 engine (ARCHITECTURE §۵).

Pipeline (گام ۲ / بند ۷-۷-۳ + شکل ۵ + بند ۱۰ پرامپت مادر):
  workbook → OutageRecord list (A-08 cleaning) → six-class classifier
  → unmapped-cause Errors → λ/r matrix (model feeders) → four official
  review-level tables (شکل ۵) → QC verdict → persistence + Persian report.

The service never invents data: no planned/unplanned guess (OUT-POL-02),
no category guess for loads, no feeder guess for out-of-model events.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import APP_NAME, TAV_REFERENCE, __version__
from ..persistence.store import ProjectStore
from ..reliability import lambdar
from ..reliability.classify import RULES_DOC, classify_all
from ..reliability.coverage import compute_coverage
from ..reliability.outages import read_outage_workbook
from ..validation.issues import (IssueLog, SEVERITY_ERROR, SEVERITY_INFO,
                                 SEVERITY_WARNING, ValidationIssue)
from ..validation.qc import QcReport, run_qc


@dataclass
class OutageSettings:
    user: str = "unknown"
    model_feeders: tuple = tuple(f"F{i}" for i in range(1, 8))
    persist: bool = True
    #: OUT-POL-02 — planned-outage detection from free text (A-08 limit).
    planned_patterns_note: str = ("الگوی باریک؛ ستون نوع خاموشی در داده ۱۴۰۵ "
                                  "موجود نیست (A-08)")
    #: --- نیاز ۸: دوره پوشش داده و ماه‌های اجباری/حذفی -------------------
    #: «1404/07» — None → استنتاج از اولین/آخرین رکورد
    coverage_start: str | None = None
    coverage_end: str | None = None
    #: ماه‌های فاقد رکورد که مهندس صریحاً دارای پوشش اعلام می‌کند («1404/08»)
    force_cover_months: tuple = ()
    #: ماه‌های دارای رکورد که باید از مواجهه حذف شوند («1404/08»)
    force_exclude_months: tuple = ()
    #: --- ورود خاموشی per-feeder (همزمان با شیپ‌فایل فیدرها) --------------
    #: feeder_key → مسیر فایل اکسل خاموشی همان فیدر؛ وقتی غیرخالی باشد،
    #: همه رکوردهای هر فایل به همان فیدر منسوب و فایل‌ها ادغام می‌شوند.
    per_feeder_files: dict = field(default_factory=dict)
    #: دامنه تک‌فیدر؛ فایل جمعی نیز پیش از طبقه‌بندی فقط به این فیدر محدود می‌شود.
    scope_feeder: str | None = None
    #: explicit multi-feeder study set; takes precedence over scope_feeder
    scope_feeders: tuple = ()


@dataclass
class OutageResult:
    records: list
    reader_stats: dict
    rules: dict
    lambda_r: list
    levels: dict
    issues: IssueLog
    report: QcReport
    settings: dict
    outage_run_id: str | None = None

    @property
    def verdict(self) -> str:
        return self.report.verdict


def filter_records_by_scope(records: list, scope_feeder: str | None = None,
                            scope_feeders=()) -> tuple[list, int]:
    """Keep records in the requested feeder set; return excluded count."""
    if scope_feeders:
        targets = {str(k).strip().upper() for k in scope_feeders if str(k).strip()}
    elif scope_feeder:
        targets = {str(scope_feeder).strip().upper()}
    else:
        return list(records), 0
    kept = [r for r in records
            if str(getattr(r, "feeder_key", "") or "").strip().upper() in targets]
    return kept, len(records) - len(kept)


class OutageService:
    def __init__(self, settings: OutageSettings | None = None):
        self.settings = settings or OutageSettings()

    # ------------------------------------------------------------------
    def run(self, workbook: str | None = None, out_db: str | None = None,
            report_dir: str | None = None,
            project_name: str = "تحلیل خاموشی‌ها") -> OutageResult:
        st = self.settings
        issues = IssueLog()

        # 1) read --------------------------------------------------------
        from ..reliability.outages import default_feeder_mapper, fixed_feeder_mapper
        records: list = []
        reader_stats: dict = {"file": "", "file_sha256": "", "sheets": {},
                              "rows_total": 0, "rows_empty_skipped": 0,
                              "records": 0, "sources": []}
        if st.per_feeder_files:
            # ورود per-feeder: هر فایل با نگاشت ثابت فیدر خودش خوانده و
            # ادغام می‌شود (همان پالت ستون‌ها؛ سطرهای خالی همان‌جا حذف می‌شوند)
            for fkey in sorted(st.per_feeder_files):
                fpath = st.per_feeder_files[fkey]
                recs, stt = read_outage_workbook(
                    fpath, feeder_mapper=fixed_feeder_mapper(fkey),
                    source_tag=fkey)
                records.extend(recs)
                reader_stats["sources"].append(
                    {"feeder_key": fkey, "file": stt["file"],
                     "records": stt["records"],
                     "rows_empty_skipped": stt["rows_empty_skipped"],
                     "sheets": list(stt["sheets"].keys())})
                reader_stats["rows_total"] += stt["rows_total"]
                reader_stats["rows_empty_skipped"] += stt["rows_empty_skipped"]
                reader_stats["records"] += stt["records"]
                for sheet, sst in stt["sheets"].items():
                    skey = f"{fkey}:{sheet}"
                    reader_stats["sheets"][skey] = sst
            reader_stats["file"] = ";".join(
                s["file"] for s in reader_stats["sources"]) or "(empty)"
        else:
            if not workbook:
                raise ValueError("workbook یا per_feeder_files باید داده شود.")
            records, reader_stats = read_outage_workbook(
                workbook, feeder_mapper=default_feeder_mapper(st.model_feeders))

        # دامنه تک‌فیدر: هیچ رخداد فیدر دیگری وارد طبقه‌بندی، پوشش یا λ/r نمی‌شود.
        if st.scope_feeders or st.scope_feeder:
            targets = (sorted({str(k).strip().upper() for k in st.scope_feeders
                               if str(k).strip()}) if st.scope_feeders else
                       [str(st.scope_feeder).strip().upper()])
            before_n = len(records)
            records, excluded_n = filter_records_by_scope(
                records, st.scope_feeder, st.scope_feeders)
            reader_stats["scope_filter"] = {
                "scope_feeders": targets,
                "records_before": before_n,
                "records_after": len(records),
                "records_excluded": excluded_n,
            }
            reader_stats["records"] = len(records)

        # 2) classify ----------------------------------------------------
        rules = classify_all(records)

        # 2b) unmapped causes → Error (an unknown cause must never pass)
        unmapped = [r for r in records if r.rule_id == "R-UNK-99"]
        if unmapped:
            for r in unmapped[:20]:
                issues.add(ValidationIssue(
                    code="OUT-CAUSE-UNMAPPED", severity=SEVERITY_ERROR,
                    message_fa="علت قطع خارج از نگاشت شناخته‌شده است.",
                    source_file=reader_stats["file"], layer=r.sheet,
                    record_id=r.id, field="علت قطع",
                    current_value=r.cause_raw,
                    suggestion_fa="گروه علت را در reliability/classify.py "
                                  "تکمیل و اجرا را تکرار کنید.",
                    impact_fa="رویداد در «داده ناکافی» می‌ماند و λ فیدر "
                              "تحریف می‌شود.",
                    meta={"sheet": r.sheet, "row_ref": r.row_ref}))
            issues.add(ValidationIssue(
                code="OUT-CAUSE-UNMAPPED-COUNT", severity=SEVERITY_ERROR,
                message_fa=f"مجموع {len(unmapped)} رکورد با علت نگاشت‌نشده.",
                current_value=str(len(unmapped)),
                impact_fa="تا رفع نگاشت، پذیرش FAIL است."))

        # 3) A-08 limitations (explicit, auditable) ----------------------
        insuff = sum(1 for r in records if r.rule_id == "R-NAK-01")
        issues.add(ValidationIssue(
            code="OUT-A08-INSUFFICIENT", severity=SEVERITY_WARNING,
            message_fa=f"{insuff} رکورد داده ناکافی (علت/فیدر/تاریخ/مدت "
                       "مفقود) — ستون «نوع خاموشی» و «تعداد مشترکین» در "
                       "لیست ۱۴۰۵ وجود ندارد.",
            current_value=str(insuff),
            suggestion_fa="تکمیل ستون‌های نوع خاموشی/مشترکین در منبع.",
            impact_fa="SAIDI/SAIFI دقیق و تفکیک برنامه‌ای/اتفاقی محدود است.",
            meta={"rule": RULES_DOC["R-NAK-01"]}))
        out_of_model = sum(1 for r in records
                           if not r.in_model and r.rule_id != "R-NAK-01")
        if out_of_model:
            issues.add(ValidationIssue(
                code="OUT-FEEDER-OUT-OF-MODEL", severity=SEVERITY_INFO,
                message_fa=f"{out_of_model} رکورد به فیدرهای خارج از مدل "
                           "GIS (پست کمی آباد) تعلق دارد — فقط در جداول "
                           "چهار سطح شکل ۵ می‌آیند، نه در ماتریس λ/r مدل.",
                meta={"count": out_of_model}))
        issues.add(ValidationIssue(
            code="OUT-A08-ENERGY-UNIT", severity=SEVERITY_INFO,
            message_fa="واحد «انرژی توزیع نشده» در منبع اعلام نشده است؛ "
                       "مقادیر عیناً و بدون تبدیل گزارش می‌شوند (A-08).",
            impact_fa="مقادیر انرژی فقط برای مقایسه نسبی معتبرند."))
        issues.add(ValidationIssue(
            code="OUT-POL-02-PLANNED", severity=SEVERITY_INFO,
            message_fa="تشخیص خاموشی برنامه‌ای فقط با الگوی باریک متنی "
                       "(OUT-POL-02) انجام شد؛ ستون نوع خاموشی مفقود است.",
            impact_fa="همه رخدادهای باقی‌مانده «تصادفی» فرض شده‌اند."))

        # 4) λ/r + four official levels (با زمان مواجهه واقعی — نیاز ۸) ----
        coverage = compute_coverage(
            records, start=st.coverage_start, end=st.coverage_end,
            force_cover=st.force_cover_months,
            force_exclude=st.force_exclude_months)
        if coverage.start is None:
            issues.add(ValidationIssue(
                code="OUT-COVERAGE-NO-DATA", severity=SEVERITY_WARNING,
                message_fa="هیچ رکورد تاریخ‌دار برای محاسبه پوشش داده وجود "
                           "ندارد؛ λ = 0 و زمان مواجهه = 0 در نظر گرفته شد.",
                impact_fa="ماتریس λ/r بدون پوشش معتبر است و رتبه‌بندی باید "
                          "پس از اصلاح داده تکرار شود."))
        else:
            miss = [f"{y}/{m:02d}" for y, m in coverage.missing_months]
            issues.add(ValidationIssue(
                code="OUT-COVERAGE-EXPOSURE", severity=SEVERITY_INFO,
                message_fa=("زمان مواجهه بر اساس پوشش واقعی داده محاسبه شد "
                            f"(نیاز ۸): پنجره {coverage.start[0]}/{coverage.start[1]:02d} "
                            f"تا {coverage.end[0]}/{coverage.end[1]:02d} — "
                            f"{len(coverage.effective_months)} ماه دارای داده، "
                            f"{coverage.exposure_days} روز "
                            f"= {coverage.exposure_years:.4f} سال مواجهه."),
                suggestion_fa="دوره پوشش را در تنظیمات کنترل کنید؛ ماه‌های "
                              "فاقد داده که در واقع دارای پوشش بوده‌اند را "
                              "در تنظیمات صریحاً «دارای پوشش» اعلام کنید.",
                impact_fa="ماه‌های فاقد داده به‌عنوان صفر-رخداد حساب نشده‌اند "
                          "(نبود رکورد ≠ نبود خاموشی)؛ مخرج λ واقعی است.",
                meta={"coverage": coverage.as_dict()}))
            if miss:
                issues.add(ValidationIssue(
                    code="OUT-COVERAGE-MISSING-MONTHS", severity=SEVERITY_WARNING,
                    message_fa="ماه‌های فاقد رکورد در پنجره پوشش: "
                               f"{', '.join(miss)} — نبود رکورد الزاماً "
                               "به معنی نبود خاموشی نیست؛ این ماه‌ها از زمان "
                               "مواجهه حذف شدند.",
                    suggestion_fa="اگر داده آن ماه‌ها موجود است، فایل را "
                                  "تکمیل یا ماه‌ها را در تنظیمات «دارای پوشش» "
                                  "اعلام کنید (فقط با تأیید مهندس).",
                    impact_fa="حذف ماه از مخرج، λ را بزرگ‌تر (محافظه‌کارانه‌تر) "
                              "می‌کند؛ اعلام پوشش نادرست λ را تضعیف می‌کند.",
                    meta={"missing_months": miss}))
        lam = lambdar.feeder_lambda_r(records, st.model_feeders,
                                      coverage=coverage)
        levels = lambdar.as_dict(records, lam, coverage=coverage)

        # 5) QC ------------------------------------------------------------
        class_summary = levels["class_summary"]
        summary = {
            "records": len(records),
            "rows_empty_skipped": reader_stats["rows_empty_skipped"],
            "sheets": reader_stats["sheets"],
            "class_summary": class_summary,
            "rule_counts": rules["rule_counts"],
            "in_model_events": sum(1 for r in records if r.in_model),
            "years": sorted({r.year for r in records if r.year}),
            "coverage": levels.get("coverage"),
            "per_feeder_sources": reader_stats.get("sources", []),
        }
        rep = run_qc(summary, issues, project_name, None)

        result = OutageResult(
            records=records, reader_stats=reader_stats, rules=rules,
            lambda_r=lam, levels=levels, issues=issues, report=rep,
            settings=self._settings_snapshot(st))

        # 6) persistence ----------------------------------------------------
        if st.persist and out_db:
            store = ProjectStore(out_db)
            result.outage_run_id = store.save_outages(
                records=records, lam=lam, settings=result.settings,
                user=st.user, algo_version=f"{APP_NAME} {__version__}",
                summary=summary, verdict=rep.verdict,
                input_file=reader_stats["file"],
                input_sha256=reader_stats["file_sha256"])
            store.close()

        # 7) report ----------------------------------------------------------
        if report_dir:
            self.write_report(result, report_dir)
        return result

    # ------------------------------------------------------------------
    @staticmethod
    def _settings_snapshot(st: OutageSettings) -> dict:
        return {
            "model_feeders": list(st.model_feeders),
            "planned_detection": st.planned_patterns_note,
            "tav_revision": TAV_REFERENCE,
            "coverage": {
                "start": st.coverage_start, "end": st.coverage_end,
                "force_cover_months": list(st.force_cover_months),
                "force_exclude_months": list(st.force_exclude_months),
                "basis_note": "λ بر مخرج روزهای واقعی دارای پوشش داده (نیاز ۸)",
            },
            "per_feeder_files": dict(st.per_feeder_files or {}),
            "scope_feeder": st.scope_feeder,
        }

    # ------------------------------------------------------------------
    def write_report(self, res: OutageResult, report_dir: str) -> None:
        import json
        from pathlib import Path

        rd = Path(report_dir)
        rd.mkdir(parents=True, exist_ok=True)

        lam_md = "\n".join(
            f"| {f.feeder_key} | {f.events_random} | {f.years_covered} | "
            f"{f.lambda_per_year:.2f} | {f.lambda_reducible_per_year:.2f} | "
            f"{f.r_minutes:.1f} | "
            f"{(f.r_minutes_nonzero if f.r_minutes_nonzero is not None else '—')} | "
            f"{f.u_hours:.2f} | {f.energy_kwh:,.2f} |"
            for f in res.lambda_r)
        cls_md = "\n".join(
            f"| {k} | {v} |" for k, v in
            sorted(res.levels["class_summary"].items(), key=lambda kv: -kv[1]))
        l1_md = "\n".join(
            f"| {d['cause']} | {d['events']} | {d['mean_duration_min']} | "
            f"{d['energy_kwh']:,.2f} | {d['dominant_class']} |"
            for d in res.levels["level1_by_cause"])
        l2_md = "\n".join(
            f"| {d['fault_group']} | {d['events']} | {d['mean_duration_min']} |"
            for d in res.levels["level2_by_fault_group"])
        ys = res.levels["level3_by_time"]["year_summary"]
        l3_md = "\n".join(
            f"| {y} | {s['events']} | {s['mean_duration_min']} | "
            f"{s['energy_kwh']:,.2f} |" for y, s in sorted(ys.items()))
        l4_rows = res.levels["level4_by_scope"]["feeder_device_counts"][:25]
        l4_md = "\n".join(
            f"| {d['feeder']} | {d['device']} | {d['events']} |"
            for d in l4_rows)
        rules_md = "\n".join(f"| `{k}` | {v} |" for k, v in RULES_DOC.items())

        md = f"""# گزارش تحلیل خاموشی‌ها — فاز ۳ (گام ۲ روش سطح اول، شکل ۵)

| مورد | مقدار |
|---|---|
| منبع | `{res.reader_stats['file']}` |
| اثر انگشت SHA-256 | `{res.reader_stats['file_sha256'][:16]}…` |
| رکورد واقعی / سطر خالی حذف‌شده | {len(res.records):,} / {res.reader_stats['rows_empty_skipped']:,} |
| نتیجه پذیرش | {'✅ PASS' if res.verdict == 'PASS' else '❌ FAIL'} — {res.report.verdict_reason_fa} |

## ۱. طبقه‌بندی شش‌طبقه (بند ۱۰ پرامپت مادر)

| طبقه | تعداد |
|---|---|
{cls_md}

## ۲. ماتریس λ/r فیدرهای مدل (ورودی معیارهای ۵ و ۶ جدول ۱۶ — فاز ۴)

| فیدر | رخداد تصادفی | سال‌ها | λ (۱/سال) | λ قابل کاهش | r (دقیقه) | r بدون لحظه‌ای | U=λr/60 (ساعت/سال) | انرژی توزیع‌نشده |
|---|---|---|---|---|---|---|---|---|
{lam_md}

> U با لنگر رسمی V-03 سازگار است (جدول ۲۶: λ=۶٫۳۳، r=۳۶٫۶۳ → U=۳٫۸۶۶).
> رخدادهای «برنامه‌ریزی‌شده» و رکوردهای داده ناکافی در λ دخیل نیستند؛
> واحد انرژی در منبع اعلام نشده است (A-08).

## ۳. قواعد طبقه‌بند (قابل بازبینی توسط مهندس)

| قاعده | شرح |
|---|---|
{rules_md}

## ۴. سطح اول شکل ۵ — بر اساس علت اشکال

| علت قطع | رخداد | مدت متوسط (دقیقه) | انرژی | طبقه غالب |
|---|---|---|---|---|
{l1_md}

## ۵. سطح دوم شکل ۵ — بر اساس نوع اشکال

| گروه نوع اشکال | رخداد | مدت متوسط (دقیقه) |
|---|---|---|
{l2_md}

## ۶. سطح سوم شکل ۵ — زمان رخداد (سالانه)

| سال | رخداد | مدت متوسط (دقیقه) | انرژی |
|---|---|---|---|
{l3_md}

## ۷. سطح چهارم شکل ۵ — محدوده (۲۵ ترکیب برتر فیدر×قطع‌کننده)

| فیدر | قطع‌کننده | رخداد |
|---|---|---|
{l4_md}

## ۸. شمارش Issueهای تحلیل

| کد | تعداد |
|---|---|
""" + "\n".join(f"| {c} | {n} |" for c, n in res.report.code_counts.most_common()) + """
"""
        (rd / "phase3_outage_report.md").write_text(md, encoding="utf-8")
        payload = {
            "verdict": res.verdict,
            "verdict_reason_fa": res.report.verdict_reason_fa,
            "outage_run_id": res.outage_run_id,
            "reader_stats": res.reader_stats,
            "settings": res.settings,
            "summary": res.report.summary,
            "lambda_r": [f.as_dict() for f in res.lambda_r],
            "levels": res.levels,
            "rule_counts": res.rules["rule_counts"],
            "issue_codes": dict(res.report.code_counts.most_common()),
        }
        (rd / "phase3_outage_report.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
