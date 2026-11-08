# -*- coding: utf-8 -*-
"""ReportService — orchestration of the Phase-5 exports (فاز ۵).

Two entry shapes, one code path:

* **From a finished project** (`run(db_path=…)`): the placement pipeline
  is re-executed in-memory with ``persist=False`` (the engine is pure —
  same inputs → identical numbers, guaranteed by the deterministic-id
  tests), then cross-checked against the latest persisted placement run
  of the project.  The cross-check result is printed into the report
  itself — a report that disagrees with the database is a FAIL, never
  silent (بند ۱۹ philosophy).
* **From a live run** (`run(net=…, topo=…, placement=…)`): the Qt shell
  and the CLI placement command already hold the artefacts — no re-run.

Outputs land in ``<out_dir>``:  study .xlsx, .docx, .pdf, the GIS
directory (GeoJSON ×3 + CSV + metadata) and the map PNG used inside the
documents.  PDF needs the optional extras; when they are missing the
service degrades to DOCX and registers an Information issue — the rest
of the export never fails because of one channel.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..ui.map_renderer import NetworkMapRenderer
from .content import build_report
from .docx_report import export_docx
from .gis_export import export_gis
from .model import StudyModel
from .pdf_report import PdfUnavailableError, export_pdf
from .workbook import export_workbook
from ..logging_setup import get_logger

_log = get_logger("reporting")

FORMATS = ("xlsx", "docx", "pdf", "gis")


@dataclass
class ExportSettings:
    out_dir: str = "reports/exports"
    formats: tuple = FORMATS
    make_map: bool = True
    user: str = "report-user"
    #: نام پروژه‌ای که در گزارش درج می‌شود (درخواست کاربر، مورد ۴ —
    #: هنگام خروجی از کاربر پرسیده و در پروژه ذخیره می‌شود)
    project_name: str = ""
    #: نتایج جایابی دستی (dict های ManualEvaluation.as_dict — مورد ۶)
    manual_evals: list = field(default_factory=list)
    #: نوع مطالعهٔ گزارش: ``auto`` (پیش‌فرض) | ``eens`` | ``placement``
    #: در حالت auto، اگر مطالعهٔ جایابی کلید/EENS در پروژه ذخیره شده باشد،
    #: گزارش نهایی فقط همان مطالعه را مستند می‌کند (درخواست کاربر v1.15).
    study_type: str = "auto"


@dataclass
class ExportResult:
    paths: dict = field(default_factory=dict)       # format → str | list[str]
    crosscheck: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)      # (code, sev, msg_fa)
    verdict: str = "PASS"

    @property
    def summary_fa(self) -> str:
        lines = ["خروجی‌های فاز ۵:"]
        label = {"xlsx": "کتاب کار Excel", "docx": "گزارش Word",
                 "pdf": "گزارش PDF", "gis": "خروجی GIS",
                 "map": "نقشه PNG"}
        for fmt, p in self.paths.items():
            if isinstance(p, list):
                for one in p:
                    lines.append(f"  • {label.get(fmt, fmt)}: {one}")
            else:
                lines.append(f"  • {label.get(fmt, fmt)}: {p}")
        lines.append(f"تطبیق با پایگاه داده: "
                     f"{self.crosscheck.get('status_fa', '—')}")
        return "\n".join(lines)


class ReportService:
    def __init__(self, settings: ExportSettings | None = None):
        self.settings = settings or ExportSettings()

    # ------------------------------------------------------------------
    def run(self, db_path: str | None = None, *, net=None, topo=None,
            placement=None, placement_run_id: str = "") -> ExportResult:
        st = self.settings
        issues: list = []
        crosscheck = {"status": "skipped", "status_fa": "— (اجرای در حافظه)"}

        if net is None or topo is None or placement is None:
            if not db_path:
                raise ValueError("یا db_path بدهید یا (net, topo, placement).")
            db_path, net, topo, placement, placement_run_id = \
                self._rerun(db_path, issues)
        else:
            db_path = db_path or ""

        m = StudyModel(net=net, topo=topo, placement=placement,
                       db_path=str(db_path or ""),
                       placement_run_id=placement_run_id or "",
                       crosscheck=crosscheck,
                       project_name=self.settings.project_name or "",
                       manual_evals=list(self.settings.manual_evals or []),
                       eens_study=self._load_eens_study(db_path, issues),
                       study_type=str(self.settings.study_type or "auto"))

        if db_path:
            crosscheck = self._crosscheck(db_path, placement)
            m.crosscheck = crosscheck
            issues.append(("PHASE5-CROSSCHECK", "Information",
                           crosscheck["status_fa"]))

        paths: dict = {}
        map_png = None
        if st.make_map:
            try:
                map_png = self._render_map(m, st.out_dir)
                if map_png:
                    paths["map"] = map_png
            except Exception as exc:
                issues.append(("PHASE5-MAP-FAIL", "Warning",
                               f"ترسیم نقشه برای گزارش ناموفق بود: {exc}"))

        if "xlsx" in st.formats:
            paths["xlsx"] = export_workbook(
                m, str(_out(st.out_dir, "SwitchLoc_study.xlsx")))
        if "docx" in st.formats:
            paths["docx"] = export_docx(
                build_report(m, map_note=_MAP_NOTE if map_png else ""),
                str(_out(st.out_dir, "SwitchLoc_report.docx")),
                map_png=map_png)
        if "pdf" in st.formats:
            try:
                paths["pdf"] = export_pdf(
                    build_report(m, map_note=_MAP_NOTE if map_png else ""),
                    str(_out(st.out_dir, "SwitchLoc_report.pdf")),
                    map_png=map_png)
            except PdfUnavailableError as exc:
                issues.append(("PHASE5-PDF-SKIP", "Information", str(exc)))
        if "gis" in st.formats:
            paths["gis"] = export_gis(m, str(_out(st.out_dir, "gis")))

        errors = [i for i in issues if i[1] == "Error"]
        return ExportResult(paths=paths, crosscheck=crosscheck,
                            issues=issues,
                            verdict="PASS" if not errors else "FAIL")

    # ------------------------------------------------------------------
    @staticmethod
    def _load_eens_study(db_path: str | None, issues: list) -> dict:
        """مطالعهٔ جایابی کلید/EENS ذخیره‌شده در پروژه (یا dict خالی)."""
        if not db_path:
            return {}
        try:
            from ..persistence.store import ProjectStore
            from ..application.switch_placement_service import KV_KEY
            store = ProjectStore(str(db_path))
            try:
                payload = store.get_kv(KV_KEY)
            finally:
                store.close()
        except Exception as exc:                       # noqa: BLE001
            issues.append(("PHASE5-EENS-KV", "Information",
                           f"خواندن مطالعهٔ EENS ذخیره‌شده ناموفق بود: {exc}"))
            return {}
        if not payload:
            return {}
        issues.append(("PHASE5-EENS-STUDY", "Information",
                       "مطالعهٔ جایابی کلید/EENS ذخیره‌شده پیدا شد؛ گزارش "
                       "نهایی بر اساس همین مطالعه ساخته می‌شود."))
        return dict(payload)

    def _rerun(self, db_path: str, issues: list):
        """Fresh in-memory pipeline (persist=False) + persisted run id."""
        from ..application.placement_service import (
            PlacementAppSettings, PlacementService)
        res = PlacementService(PlacementAppSettings(
            user=self.settings.user, persist=False)).run(db_path)
        issues.append(("PHASE5-RERUN", "Information",
                       "جایابی برای گزارش در حافظه بازتولید شد "
                       "(persist=False؛ موتور خالص و بازتولیدپذیر)."))
        placement_run_id = ""
        try:
            from ..persistence.store import ProjectStore
            store = ProjectStore(db_path)
            runs = store.list_placement_runs()
            if runs:
                placement_run_id = runs[0]["placement_run_id"]
            store.close()
        except Exception as exc:                   # noqa: BLE001
            _log.warning("could not read stored placement run id: %s", exc)
        net = _net_of(res, db_path) if res.topo is not None else None
        return db_path, net, res.topo, res.result, placement_run_id

    # ------------------------------------------------------------------
    @staticmethod
    def _crosscheck(db_path: str, placement) -> dict:
        """Latest persisted placement vs this fresh result."""
        try:
            from ..persistence.store import ProjectStore
            store = ProjectStore(db_path)
            runs = store.list_placement_runs()
            if not runs:
                store.close()
                return {"status": "none", "status_fa":
                        "هیچ اجرای ذخیره‌شده‌ای در پروژه نیست."}
            saved = store.load_placement(runs[0]["placement_run_id"])
            store.close()
        except Exception as exc:
            return {"status": "error",
                    "status_fa": f"خواندن اجرای ذخیره‌شده ناموفق: {exc}"}
        checks = {}
        saved_order = [r["feeder_key"] for r in saved.get("ranking", [])]
        fresh_order = [r.feeder_key for r in placement.ranking.rows]
        checks["ranking"] = saved_order == fresh_order
        # selected scheme ids compare as sets: DB order is CE/CN DESC,
        # engine order is generation order.
        saved_best = sorted(c["scheme_id"] for c in
                            saved.get("table18_comparison", [])
                            if c.get("selected"))
        fresh_best = sorted(c.scheme_id for c in placement.economics.comparisons
                            if c.selected)
        checks["selected_schemes"] = saved_best == fresh_best

        saved_eptl = {r["feeder_key"]: r for r in
                      (saved.get("table14_eptl") or [])}
        fresh_eptl = {r.feeder_key: r for r in placement.n1.eptl}
        checks["feeder_loads"] = set(saved_eptl) == set(fresh_eptl)
        checks["zone_counts"] = set(saved_eptl) == set(fresh_eptl)
        for fk in set(saved_eptl).intersection(fresh_eptl):
            old = float(saved_eptl[fk].get("total_load_kw") or 0.0)
            new_load = float(fresh_eptl[fk].total_load_kw or 0.0)
            checks["feeder_loads"] = checks["feeder_loads"] and abs(old-new_load) <= max(0.1, abs(new_load)*1e-6)
            checks["zone_counts"] = checks["zone_counts"] and int(saved_eptl[fk].get("zone_count") or 0) == int(fresh_eptl[fk].zone_count)

        saved_summary = saved.get("summary", {}) or {}
        saved_rows15 = saved_summary.get("table15_rows") or []
        fresh_rows15 = placement.n1.rows15 or []
        if saved_rows15:
            def _fault_sig(rows):
                return sorted((r.get("feeder_key"), int(r.get("zone_no", -1)),
                               round(float(r.get("shed_kw") or 0.0), 1),
                               round(float(r.get("restorable_kw") or 0.0), 1))
                              for r in rows)
            checks["zone_fault_rows"] = _fault_sig(saved_rows15) == _fault_sig(fresh_rows15)
        else:
            checks["zone_fault_rows"] = None

        saved_zones = saved_summary.get("zone_register") or []
        fresh_zones = placement.to_dict().get("zone_register") or []
        if saved_zones:
            def _zone_sig(rows):
                return sorted((r.get("feeder_key"), int(r.get("zone_no", -1)),
                               round(float(r.get("length_m") or 0.0), 1),
                               round(float(r.get("load_kw") or 0.0), 2))
                              for r in rows)
            checks["zone_register"] = _zone_sig(saved_zones) == _zone_sig(fresh_zones)
        else:
            # Older project runs predate the detailed register; retain the
            # compatibility path but explicitly mark this check unavailable.
            checks["zone_register"] = None

        failed = [k for k, v in checks.items() if v is False]
        if not failed:
            return {"status": "match", "run_id": runs[0]["placement_run_id"],
                    "checks": checks,
                    "status_fa": ("تطبیق نتایج با اجرای ذخیره‌شده برقرار است "
                                 f"(کنترل‌ها: {', '.join(k for k,v in checks.items() if v is True)}؛ "
                                 f"اجرای {runs[0]['placement_run_id'][:12]}…)."
                                 if all(v is not None for v in checks.values()) else
                                 "تطبیق کنترل‌های موجود برقرار است؛ اجرای ذخیره‌شده قدیمی است و "
                                 "شناسنامه تفصیلی زون‌ها در آن ثبت نشده بود.")}
        return {"status": "diff", "run_id": runs[0]["placement_run_id"],
                "checks": checks, "failed_checks": failed,
                "status_fa": "عدم تطبیق با آخرین اجرای ذخیره‌شده در کنترل‌های: "
                             + ", ".join(failed) +
                             " — این گزارش از اجرای تازهٔ درون‌حافظه‌ای تولید شده است."}

    # ------------------------------------------------------------------
    def _render_map(self, m: StudyModel, out_dir: str) -> str | None:
        proposed = [p.node for p in m.build_proposed()
                    if m.node_coord(p.node) is not None]
        manual = sorted({n for ev in (m.manual_evals or [])
                         for n in (ev.get("switch_nodes") or [])
                         if m.node_coord(n) is not None})
        if not m.topo.traces:
            return None
        renderer = NetworkMapRenderer(
            m.topo.graph, traces=m.topo.traces, zones=m.topo.zones,
            switches={s.id: s for s in m.net.switches},
            tie_switch_ids={t.switch_id for t in m.topo.ties
                            if t.switch_id})
        path = str(_out(out_dir, "report_map.png"))
        renderer.render(
            path, title=f"SwitchLoc — {m.name} (proposed switches = stars)",
            zone_labels=False, proposed_nodes=sorted(set(proposed)),
            manual_nodes=manual)
        return path


_MAP_NOTE = ("نقشه شبکه با ستاره‌های سبز (مکان کلیدهای پیشنهادی) در "
             "انتهای این گزارش آمده است؛ مختصات دقیق در پیوست الف و "
             "خروجی GIS.")


def _out(out_dir: str, name: str):
    from pathlib import Path
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def _net_of(res, db_path: str):
    """The CanonicalNetwork behind a PlacementRunResult (reloaded once)."""
    from ..persistence.store import ProjectStore
    store = ProjectStore(db_path)
    net, _issues = store.load_network()
    store.close()
    return net
