# -*- coding: utf-8 -*-
"""PlacementService — end-to-end orchestration of Phase 4 (گام‌های ۴-۸).

Loads the project network from SQLite, re-runs the topology in-memory
(persisted for traceability), takes the λ/r matrix (from the optional
outage workbook, else the latest persisted outage run), executes the
PlacementEngine and persists the tables + writes the MD/JSON report.

Nothing is recomputed twice: the engine is pure; persistence/reporting
live here (application layer).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from .. import APP_NAME, TAV_REFERENCE, __version__
from ..application.topology_service import TopologyService, TopologySettings
from ..persistence.store import ProjectStore
from ..placement.service import EngineSettings, PlacementEngine, \
    PlacementResult
from ..logging_setup import get_logger

_log = get_logger("placement")


@dataclass
class PlacementAppSettings:
    user: str = "placement-user"
    persist: bool = True
    report_dir: str | None = None
    #: optional workbook — when given, λ/r are recomputed from it;
    #: otherwise the latest persisted outage run of the same DB is used.
    outage_workbook: str | None = None
    #: نیاز ۱۲ — دامنه مطالعه: None = کل شبکه (چندفیدر)، "F3" = تک‌فیدر
    scope_feeder: str | None = None
    scope_feeders: tuple = ()
    #: جدول تأیید ورودی‌ها (درخواست کاربر، مورد ۵) — ویرایش λ/r هر فیدر
    #: توسط مهندس: {feeder_key: {"lambda_per_year": x, "r_minutes": y}}
    lam_overrides: dict | None = None
    engine: EngineSettings = field(default_factory=EngineSettings)


@dataclass
class PlacementRunResult:
    result: PlacementResult
    run_id: str | None
    db_path: str | None
    report_md: str | None = None
    report_json: str | None = None
    #: the fresh in-memory topology the engine ran on — the UI reuses it
    #: to draw the proposed switch locations on the map.
    topo: object | None = None

    @property
    def verdict(self) -> str:
        severities = {str(i[1]).lower() for i in self.result.issues}
        if "error" in severities:
            return "FAIL"
        if "warning" in severities:
            return "CONDITIONAL"
        return "PASS"


def _lambda_from_workbook(path: str) -> list:
    from ..reliability.classify import classify_all
    from ..reliability.coverage import compute_coverage
    from ..reliability.lambdar import feeder_lambda_r
    from ..reliability.outages import read_outage_workbook
    recs, _stats = read_outage_workbook(Path(path))
    classify_all(recs)
    coverage = compute_coverage(recs)          # نیاز ۸ — مواجهه واقعی
    return feeder_lambda_r(recs, coverage=coverage)


def _lambda_from_store(store: ProjectStore) -> tuple[list, str | None]:
    try:
        data = store.load_outages()
    except ValueError:
        return [], None
    lam = [SimpleNamespace(**row) for row in data["lambda_r"]]
    return lam, data["outage_run_id"]


class PlacementService:
    def __init__(self, settings: PlacementAppSettings | None = None):
        self.settings = settings or PlacementAppSettings()

    # ------------------------------------------------------------------
    def run(self, db_path: str) -> PlacementRunResult:
        st = self.settings
        store = ProjectStore(db_path)
        net, _issues = store.load_network()
        if net is None:
            store.close()
            raise ValueError(
                f"پروژه قابل بارگذاری نیست (شبکه‌ای در {db_path} نیست).")

        topo = TopologyService(TopologySettings(
            user=st.user, persist=st.persist)).run(
            net, out_db=db_path if st.persist else None)
        source_run_id = ""
        try:
            runs = store.runs()
            source_run_id = runs[0]["run_id"] if runs else ""
        except Exception as exc:                   # noqa: BLE001
            _log.warning("source run id unavailable: %s", exc)

        outage_run_id = None
        lam_matrix = None
        if st.outage_workbook:
            lam_matrix = _lambda_from_workbook(st.outage_workbook)
        else:
            lam_matrix, outage_run_id = _lambda_from_store(store)
        # تأیید ورودی‌ها — مقادیر ویرایش‌شدهٔ جدول تأیید بر ماتریس λ/r
        if st.lam_overrides:
            from ..ui.inputs_model import apply_lambda_overrides
            lam_matrix = apply_lambda_overrides(lam_matrix, st.lam_overrides)

        # نیاز ۹ — ظرفیت فیدرهای ثبت‌شده در پروژه (GUI قابل ورود دارد)
        try:
            feeder_capacity = store.load_feeder_capacity()
        except Exception as exc:                   # noqa: BLE001
            # capacities change the n-1 transfer limits: never lose them
            # silently — the study continues without them but it is logged
            _log.warning("feeder capacities NOT loaded (study runs without "
                         "capacity limits): %s", exc)
            feeder_capacity = {}

        engine = PlacementEngine(st.engine)
        result = engine.run(topo.graph, net, topo.traces, topo.zones,
                            topo.ties, lam_matrix=lam_matrix,
                            traces_strict=topo.traces_strict,
                            feeder_capacity=feeder_capacity,
                            scope_feeder=st.scope_feeder,
                            scope_feeders=st.scope_feeders)

        run_id = db_out = None
        snapshot = result.to_dict()
        if st.persist:
            run_id = store.save_placement(
                snapshot, settings=result.settings, user=st.user,
                algo_version=f"{APP_NAME} {__version__}",
                source_run_id=source_run_id or None,
                topo_run_id=getattr(topo, "topo_run_id", None),
                outage_run_id=outage_run_id)
            db_out = str(db_path)
        store.close()

        md = js = None
        if st.report_dir:
            md, js = self.write_report(result, st.report_dir,
                                       run_id=run_id)
        return PlacementRunResult(result=result, run_id=run_id,
                                  db_path=db_out, report_md=md,
                                  report_json=js, topo=topo)

    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_switches(row: dict) -> str:
        parts = [f"{sw['node']}@{sw['kind']}" for sw in row.get("switches", [])]
        return ", ".join(parts) or "—"

    @staticmethod
    def write_report(res: PlacementResult, report_dir: str,
                     run_id: str | None = None) -> tuple[str, str]:
        """Persian MD + JSON report (same convention as phases 1-3)."""
        rd = Path(report_dir)
        rd.mkdir(parents=True, exist_ok=True)
        snap = res.to_dict()
        errors = [i for i in res.issues if i[1] == "Error"]
        verdict = "PASS" if not errors else "FAIL"

        rank_rows = "\n".join(
            f"| {r['rank']} | {r['feeder_key']} | {r['score']:.4f} | "
            f"{r['ep_percent']:.1f}٪ | {r['tl_percent']:.1f}٪ | "
            f"{r['ties_count']} | {r['load_priority_sum']:.0f} | "
            f"{r['lambda_per_year']:.2f} | {r['r_minutes']:.1f} |"
            for r in snap["ranking"])
        eptl_rows = "\n".join(
            f"| {r['feeder_key']} | {r['ep_percent']:.1f}٪ | "
            f"{r['tl_percent']:.1f}٪ | {r['total_load_kw']:.0f} | "
            f"{r['zone_count']} |"
            for r in snap["table14_eptl"])
        scheme_rows = "\n".join(
            f"| {s['kind']} | {', '.join(s['feeders'])} | "
            f"{len(s['switches'])} | {s['note']} |"
            for s in snap["schemes"]) or "| — | — | — | — |"
        comp_rows = "\n".join(
            f"| {c['kind']} | {', '.join(c['feeders'])} | {c['n_switches']} | "
            f"{c['e2_before_kwh']:.0f} | {c['e1_after_kwh']:.0f} | "
            f"{c['ce_rials']:.3e} | {c['cn_rials']:.3e} | "
            f"{'—' if c['ce_over_cn'] is None else format(c['ce_over_cn'], '.4g')}"
            f" | {'★' if c['selected'] else ''} |"
            for c in snap["table18_comparison"]) or "| — | — | — | — | — | — | — | — | — |"
        rec_rows = "\n".join(
            f"| {r['rank']} | {r['feeder_key']} | "
            f"{r.get('status_fa', r.get('status', '—'))} | "
            f"{r['scheme_kind'] or '—'} | {r['n_switches']} | "
            f"{PlacementService._fmt_switches(r)} |"
            for r in snap["recommendation"])
        issue_rows = "\n".join(
            f"| {i['code']} | {i['severity']} | {i['message_fa']} |"
            for i in snap["issues"]) or "| — | — | — |"

        md = f"""# گزارش فاز ۴ — رتبه‌بندی فیدرها و جایابی کلید (گام‌های ۴-۸ روش سطح اول)

| مورد | مقدار |
|---|---|
| مرجع روش | TAV122-02/00 — بند ۷-۷-۴ تا ۷-۷-۷ (جداول ۱۳-۱۸، فرمول ۱، پیوست ب) |
| نتیجه پذیرش | {'✅ PASS' if verdict == 'PASS' else '❌ FAIL'} |
| شناسه اجرا | {run_id or '—'} |

## جدول ۱۴ — EP/TL فیدرها (n-1)

| فیدر | EP (ماکزیمم بار خاموش‌شده) | TL (قابل انتقال) | شاخص بار (kW) | تعداد زون |
|---|---|---|---|---|
{eptl_rows}

## گام ۶ — رتبه‌بندی فیدرها (فرمول ۱ + جدول ۱۶، وزن‌های ۱،۲،۲،۳،۱،۱)

| رتبه | فیدر | امتیاز | EP | TL | ارتباطات | مجموع اولویت بار | λ | r |
|---|---|---|---|---|---|---|---|---|
{rank_rows}

## گام ۷ — طرح‌های کلیدگذاری (جدول ۱۷ + پیوست ب)

| نوع طرح | فیدرها | تعداد کلید | شرح |
|---|---|---|---|
{scheme_rows}

## گام ۸ — مقایسه طرح‌ها (جدول ۱۸؛ انتخاب: بیشینه CE/CN)

| نوع طرح | فیدرها | N | E2 قبل (kWh) | E1 بعد (kWh) | CE (ریال) | CN (ریال) | CE/CN | طرح اصلی |
|---|---|---|---|---|---|---|---|---|
{comp_rows}

## طرح اصلی برای هر اولویت (بدون اجبار — نیاز ۱۰)

| رتبه | فیدر | وضعیت پذیرش | طرح انتخابی | تعداد کلید | مکان/نوع کلیدها |
|---|---|---|---|---|---|
{rec_rows}

> وضعیت‌ها: «طرح اصلی — قابل تأیید مهندسی»، «نیازمند تأیید ظرفیت»
> (ظرفیت نامشخص — تأیید نهایی نمی‌گیرد) و «عدم توجیه نصب کلید»
> (هیچ طرح قابل قبولی نیست — نرم‌افزار به اجبار طرح معرفی نمی‌کند).

## محدودیت‌ها و تصمیم‌های ثبت‌شده (بند ۱۹)

| کد | شدت | شرح |
|---|---|---|
{issue_rows}

> بار زون‌ها از مدل بار سه‌سطحی (نیاز ۱۱) با منشأ ردیابی‌پذیر گرفته شده
> است؛ λ از ماتریس فاز ۳ با زمان مواجهه واقعی (پوشش داده — نیاز ۸).
> ظرفیت فیدرها از مدل ظرفیت (نیاز ۹) می‌آید؛ پارامترهای هزینه،
> سیاست شرکت‌اند و قابل تنظیم (CostModel).
"""
        (rd / "phase4_placement_report.md").write_text(md, encoding="utf-8")
        import json as _json
        js = {k: v for k, v in snap.items()}
        js["verdict"] = verdict
        js["run_id"] = run_id
        js["tav_revision"] = TAV_REFERENCE
        (rd / "phase4_placement_report.json").write_text(
            _json.dumps(js, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8")
        return str(rd / "phase4_placement_report.md"), \
            str(rd / "phase4_placement_report.json")
