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
from pathlib import Path

from ..ui.map_renderer import NetworkMapRenderer
from .content import build_report
from .docx_report import export_docx
from .gis_export import export_gis
from .model import StudyModel
from .pdf_report import PdfUnavailableError, export_pdf
from .workbook import export_workbook
from ..logging_setup import get_logger
from ..task_control import check_cancelled, report_progress

_log = get_logger("reporting")

FORMATS = ("xlsx", "docx", "pdf", "gis")


def _find_template_files() -> dict[str, Path]:
    """Robust locate of the two Word templates at repo root, beside exe, or in bundle."""
    import sys
    import unicodedata
    import os
    # Normalize Persian characters (ي->ی, ك->ک) and NFC
    _PERSIAN_FIX = str.maketrans({"ي": "ی", "ك": "ک"})
    def _norm_name(s: str) -> str:
        s = s.translate(_PERSIAN_FIX)
        s = unicodedata.normalize("NFC", s)
        return s
    names = ["نمونه دفترچه مطالعات ریکلوزر.docx", "نمونه دفترچه مطالعات سکسیونر.docx"]
    norm_names = { _norm_name(n): n for n in names }
    # Also accept substring matching for robustness (ریکلوزر / سکسیونر)
    substrings = {
        "ریکلوزر": "نمونه دفترچه مطالعات ریکلوزر.docx",
        "سکسیونر": "نمونه دفترچه مطالعات سکسیونر.docx",
        "recloser": "نمونه دفترچه مطالعات ریکلوزر.docx",
        "sectionalizer": "نمونه دفترچه مطالعات سکسیونر.docx",
        "سکسیونر": "نمونه دفترچه مطالعات سکسیونر.docx",
    }
    candidates: list[Path] = []
    try:
        cur = Path.cwd().resolve()
        for _ in range(8):
            candidates.append(cur)
            if cur.parent == cur:
                break
            cur = cur.parent
    except Exception:
        pass
    try:
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            cur = exe_dir
            for _ in range(8):
                candidates.append(cur)
                if cur.parent == cur:
                    break
                cur = cur.parent
            mp = getattr(sys, "_MEIPASS", None)
            if mp:
                try:
                    mp_path = Path(mp).resolve()
                    candidates.append(mp_path)
                    # also search parent and _internal
                    candidates.append(mp_path.parent)
                    candidates.append(mp_path / "_internal")
                except Exception:
                    candidates.append(Path(mp))
    except Exception:
        pass
    try:
        cur = Path(__file__).resolve()
        for _ in range(8):
            cur = cur.parent
            candidates.append(cur)
    except Exception:
        pass
    try:
        import switchloc as _sw
        candidates.append(Path(_sw.__file__).resolve().parents[1])
        candidates.append(Path(_sw.__file__).resolve().parents[2])
        candidates.append(Path(_sw.__file__).resolve().parent)
    except Exception:
        pass
    try:
        candidates.append(Path(sys.argv[0]).resolve().parent)
    except Exception:
        pass
    # dedup
    seen: set[Path] = set()
    uniq: list[Path] = []
    for r in candidates:
        try:
            rp = r.resolve()
        except Exception:
            rp = r
        if rp not in seen:
            seen.add(rp)
            uniq.append(r)
    out: dict[str, Path] = {}
    # 1) Exact normalized match in known subdirs
    for name in names:
        norm_expected = _norm_name(name)
        for root in uniq:
            for sub in ("", "data", "build_assets", "templates", "resources", "_internal", "report_templates"):
                base = root / sub if sub else root
                try:
                    if not base.is_dir():
                        continue
                    # direct check
                    p = base / name
                    if p.is_file():
                        out[name] = p
                        break
                    # normalized directory listing
                    try:
                        for entry in base.iterdir():
                            if entry.is_file() and entry.suffix.lower() == ".docx":
                                norm_entry = _norm_name(entry.name)
                                if norm_entry == norm_expected:
                                    out[name] = entry
                                    break
                                # substring fallback
                                for sub_key, target in substrings.items():
                                    if sub_key in norm_entry and target == name:
                                        out[name] = entry
                                        break
                            if name in out:
                                break
                    except Exception:
                        pass
                except Exception:
                    continue
            if name in out:
                break
        if name not in out:
            try:
                p = Path(name)
                if p.is_file():
                    out[name] = p.resolve()
            except Exception:
                pass
    # 2) Recursive rglob in all candidates (including _MEIPASS)
    for name in names:
        if name in out:
            continue
        norm_expected = _norm_name(name)
        for root in uniq:
            try:
                if not root.is_dir():
                    continue
                for cand in root.rglob("*.docx"):
                    try:
                        norm_cand = _norm_name(cand.name)
                        if norm_cand == norm_expected:
                            out[name] = cand
                            break
                        for sub_key, target in substrings.items():
                            if sub_key in norm_cand and target == name:
                                out[name] = cand
                                break
                    except Exception:
                        continue
                    if name in out:
                        break
            except Exception:
                continue
            if name in out:
                break
    # 3) importlib.resources fallback (package data)
    for name in names:
        if name in out:
            continue
        try:
            import importlib.resources as _ir
            # Try to find via package resources - check multiple packages
            for pkg in ("switchloc", "switchloc.reporting", "switchloc.data"):
                try:
                    # Python 3.9+ API
                    files = _ir.files(pkg)  # type: ignore
                    # Try direct
                    cand = files.joinpath(name)
                    if cand.is_file():
                        # For frozen, this may be inside zip; try to get path
                        try:
                            # Try to get as file path via as_file
                            import importlib.resources as _ir2
                            from contextlib import nullcontext
                            # Use as_file to extract to temp if needed
                            try:
                                with _ir2.as_file(cand) as _p:
                                    if _p.is_file():
                                        out[name] = Path(_p)
                                        break
                            except Exception:
                                pass
                        except Exception:
                            pass
                    # Fallback: rglob via resource
                    try:
                        for res in files.rglob("*.docx"):
                            if _norm_name(res.name) == _norm_name(name):
                                try:
                                    with _ir.as_file(res) as _p2:
                                        out[name] = Path(_p2)
                                        break
                                except Exception:
                                    continue
                    except Exception:
                        pass
                except Exception:
                    continue
                if name in out:
                    break
        except Exception:
            pass
def _switch_type_from_eens(eens_study: dict | None) -> str:
    """Return 'recloser' | 'sectionalizer' | 'disconnector' | '' from EENS payload.
    The payload is the dict stored under KV_KEY 'sectionalizer_study':
      {settings: {switch_type: ...}, study: {settings: {switch_type: ...}, feeders: [...]}, ...}
    Recloser must use the recloser template, all others use sectionalizer template.
    """
    if not eens_study or not isinstance(eens_study, dict):
        return ""
    # check common locations
    for d in (eens_study, eens_study.get("study") if isinstance(eens_study.get("study"), dict) else None):
        if not isinstance(d, dict):
            continue
        st = d.get("settings") if isinstance(d.get("settings"), dict) else None
        if isinstance(st, dict):
            v = st.get("switch_type")
            if isinstance(v, str) and v.strip().lower() in ("recloser", "sectionalizer", "disconnector"):
                return v.strip().lower()
        v = d.get("switch_type")
        if isinstance(v, str) and v.strip().lower() in ("recloser", "sectionalizer", "disconnector"):
            return v.strip().lower()
    # fallback: check top-level study.settings
    try:
        st2 = eens_study.get("study", {}).get("settings", {}) if isinstance(eens_study.get("study"), dict) else {}
        if isinstance(st2, dict):
            v = st2.get("switch_type")
            if isinstance(v, str) and v.strip().lower() in ("recloser", "sectionalizer", "disconnector"):
                return v.strip().lower()
    except Exception:
        pass
    return ""


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
    #: ماتریس λ/r و شاخص‌های پیوستگی برای جدول «شاخص‌های فیدرها»؛ خالی =
    #: از پروژهٔ ذخیره‌شده خوانده می‌شود (اگر موجود باشد).
    outage_lambda: list = field(default_factory=list)
    feeder_indices: dict = field(default_factory=dict)
    #: نوع مطالعهٔ گزارش: ``auto`` (پیش‌فرض) | ``eens`` | ``placement``
    #: در حالت auto، اگر مطالعهٔ جایابی کلید/EENS در پروژه ذخیره شده باشد،
    #: گزارش نهایی فقط همان مطالعه را مستند می‌کند (درخواست کاربر v1.15).
    study_type: str = "auto"
    #: فیدرهای انتخاب‌شده برای مطالعه (scope) — فقط همین‌ها در feeder_indices.png
    #: و جدول‌های مرتبط نمایش داده می‌شوند (task 3).
    selected_feeders: list = field(default_factory=list)
    #: تمپلیت گزارش Word (ریکلووزر / سکسیونر) — مسیر فایل .docx
    template_path: str | None = None
    #: مقادیر متغیرهای تمپلیت (کلیدهای داخل {} و قطعات قرمز)
    template_vars: dict = field(default_factory=dict)
    #: تصاویر اضافی کاربر برای محل‌های «منحنی توسط کاربر …»
    extra_images: dict = field(default_factory=dict)


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
                 "eens_json": "گزارش JSON جایابی EENS",
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
        check_cancelled()
        report_progress(0, "آماده‌سازی خروجی‌ها")
        issues: list = []
        crosscheck = {"status": "skipped", "status_fa": "— (اجرای در حافظه)"}

        if net is None or topo is None or placement is None:
            if not db_path:
                raise ValueError("یا db_path بدهید یا (net, topo, placement).")
            check_cancelled()
            report_progress(10, "بازتولید و کنترل مطالعه")
            db_path, net, topo, placement, placement_run_id = \
                self._rerun(db_path, issues)
            check_cancelled()
        else:
            db_path = db_path or ""

        outage_lambda = list(self.settings.outage_lambda or [])
        feeder_indices = dict(self.settings.feeder_indices or {})
        if db_path and not (outage_lambda and feeder_indices):
            lam_store, idx_store = self._load_outage_data(db_path, issues)
            outage_lambda = outage_lambda or lam_store
            feeder_indices = feeder_indices or idx_store

        m = StudyModel(net=net, topo=topo, placement=placement,
                       db_path=str(db_path or ""),
                       placement_run_id=placement_run_id or "",
                       crosscheck=crosscheck,
                       project_name=self.settings.project_name or "",
                       manual_evals=list(self.settings.manual_evals or []),
                       eens_study=self._load_eens_study(db_path, issues),
                       study_type=str(self.settings.study_type or "auto"),
                       outage_lambda=outage_lambda,
                       feeder_indices=feeder_indices)

        if db_path:
            crosscheck = self._crosscheck(db_path, placement)
            m.crosscheck = crosscheck
            issues.append(("PHASE5-CROSSCHECK", "Information",
                           crosscheck["status_fa"]))

        paths: dict = {}
        map_png = None
        if st.make_map:
            try:
                check_cancelled()
                report_progress(55, "ترسیم نقشه گزارش")
                map_png = self._render_map(m, st.out_dir, project_name=st.project_name or None)
                check_cancelled()
                if map_png:
                    paths["map"] = map_png
            except Exception as exc:
                issues.append(("PHASE5-MAP-FAIL", "Warning",
                               f"ترسیم نقشه برای گزارش ناموفق بود: {exc}"))

        charts_png = None
        try:
            from .figures import indices_figure
            rows_idx = m.feeder_table()
            if rows_idx:
                charts_png = indices_figure(
                    rows_idx,
                    str(_out(st.out_dir, "feeder_indices.png", project_name=st.project_name or None)),
                    selected_feeders=list(st.selected_feeders or []))
        except Exception as exc:                       # noqa: BLE001
            issues.append(("PHASE5-CHART-FAIL", "Warning",
                           f"ترسیم نمودار شاخص‌ها ناموفق بود: {exc}"))

        report_progress(70, "ساخت فایل‌های گزارش")
        check_cancelled()
        if "xlsx" in st.formats:
            proj_x = (st.project_name or "").strip()
            import re as _re4
            safe_x = _re4.sub(r'[|/\\\\:*?"<>\n\r]', "_", proj_x).strip()[:40] if proj_x else ""
            xlsx_name = f"{safe_x}_کتاب_کار.xlsx" if safe_x else "SwitchLoc_study.xlsx"
            paths["xlsx"] = export_workbook(
                m, str(_out(st.out_dir, xlsx_name, project_name=st.project_name or None)))
        # When PDF is requested, also produce its Word counterpart (user request)
        effective_formats = set(st.formats or [])
        if "pdf" in effective_formats and "docx" not in effective_formats:
            effective_formats.add("docx")
            _log.info("PDF requested -> also generating Word (DOCX) counterpart")

        if "docx" in effective_formats:
            # template_vars may have been collected via UI dialog (task 4)
            tmpl = getattr(st, "template_path", None)
            tvars = dict(getattr(st, "template_vars", None) or {})
            extra = dict(getattr(st, "extra_images", None) or {})
            # auto-detect template if not explicitly set (robust search) — switch_type aware
            if not tmpl:
                try:
                    found = _find_template_files()
                    cand_recl = found.get("نمونه دفترچه مطالعات ریکلوزر.docx")
                    cand_sec = found.get("نمونه دفترچه مطالعات سکسیونر.docx")
                    if cand_recl or cand_sec:
                        sw = _switch_type_from_eens(m.eens_study if hasattr(m, "eens_study") else {})
                        # recloser -> recloser template, sectionalizer/disconnector -> sectionalizer template
                        if sw == "recloser" and cand_recl is not None:
                            tmpl = str(cand_recl.resolve())
                        elif sw in ("sectionalizer", "disconnector") and cand_sec is not None:
                            tmpl = str(cand_sec.resolve())
                        elif m.has_eens_study and cand_sec is not None:
                            # fallback for old payloads without switch_type -> sectionalizer
                            tmpl = str(cand_sec.resolve())
                        elif cand_recl is not None:
                            tmpl = str(cand_recl.resolve())
                        elif cand_sec is not None:
                            tmpl = str(cand_sec.resolve())
                except Exception:
                    tmpl = None
            # distinct filenames per switch_type / project so recloser vs sectionalizer don't overwrite each other
            # and Word vs PDF are distinguishable (user request: اسم گزارش پروژه رو تغییر بده)
            sw_for_name = _switch_type_from_eens(m.eens_study if hasattr(m, "eens_study") else {})
            proj = (st.project_name or "").strip()
            import re as _re2
            safe_proj = _re2.sub(r'[|/\\\\:*?"<>\n\r]', "_", proj).strip()[:40] if proj else ""
            if safe_proj:
                if sw_for_name == "recloser":
                    docx_name = f"{safe_proj}_ریکلووزر_دفترچه.docx"
                elif sw_for_name in ("sectionalizer", "disconnector"):
                    docx_name = f"{safe_proj}_سکسیونر_دفترچه.docx"
                else:
                    docx_name = f"{safe_proj}_گزارش.docx"
            else:
                if sw_for_name == "recloser":
                    docx_name = "SwitchLoc_ریکلووزر_دفترچه.docx"
                elif sw_for_name in ("sectionalizer", "disconnector"):
                    docx_name = "SwitchLoc_سکسیونر_دفترچه.docx"
                else:
                    docx_name = "SwitchLoc_report.docx"
            paths["docx"] = export_docx(
                build_report(m, map_note=_MAP_NOTE if map_png else ""),
                str(_out(st.out_dir, docx_name, project_name=st.project_name or None)),
                map_png=map_png, charts_png=charts_png,
                template_path=tmpl, template_vars=tvars,
                extra_images=extra, study_model=m)
        if "pdf" in effective_formats:
            try:
                sw_for_name_pdf = _switch_type_from_eens(m.eens_study if hasattr(m, "eens_study") else {})
                proj_pdf = (st.project_name or "").strip()
                import re as _re3
                safe_pdf = _re3.sub(r'[|/\\\\:*?"<>\n\r]', "_", proj_pdf).strip()[:40] if proj_pdf else ""
                if safe_pdf:
                    if sw_for_name_pdf == "recloser":
                        pdf_name = f"{safe_pdf}_ریکلووزر_دفترچه.pdf"
                    elif sw_for_name_pdf in ("sectionalizer", "disconnector"):
                        pdf_name = f"{safe_pdf}_سکسیونر_دفترچه.pdf"
                    else:
                        pdf_name = f"{safe_pdf}_گزارش.pdf"
                else:
                    if sw_for_name_pdf == "recloser":
                        pdf_name = "SwitchLoc_ریکلووزر_دفترچه.pdf"
                    elif sw_for_name_pdf in ("sectionalizer", "disconnector"):
                        pdf_name = "SwitchLoc_سکسیونر_دفترچه.pdf"
                    else:
                        pdf_name = "SwitchLoc_report.pdf"
                paths["pdf"] = export_pdf(
                    build_report(m, map_note=_MAP_NOTE if map_png else ""),
                    str(_out(st.out_dir, pdf_name, project_name=st.project_name or None)),
                    map_png=map_png, charts_png=charts_png)
            except PdfUnavailableError as exc:
                issues.append(("PHASE5-PDF-SKIP", "Information", str(exc)))
        if "gis" in st.formats:
            paths["gis"] = export_gis(m, str(_out(st.out_dir, "gis", project_name=st.project_name or None)))
        if "eens_json" in st.formats:
            if m.has_eens_study:
                from .eens_report import export_eens_json
                sw_e = _switch_type_from_eens(m.eens_study)
                proj_e = (st.project_name or "").strip()
                import re as _re5
                safe_e = _re5.sub(r'[|/\\\\:*?"<>\n\r]', "_", proj_e).strip()[:40] if proj_e else ""
                if sw_e == "recloser":
                    eens_name = f"{safe_e + '_' if safe_e else ''}recloser_eens_report.json"
                elif sw_e in ("sectionalizer", "disconnector"):
                    eens_name = f"{safe_e + '_' if safe_e else ''}sectionalizer_eens_report.json"
                else:
                    eens_name = f"{safe_e + '_' if safe_e else ''}eens_report.json"
                paths["eens_json"] = export_eens_json(
                    m.eens_study,
                    str(_out(st.out_dir, eens_name, project_name=st.project_name or None)))
            else:
                issues.append(("PHASE5-EENS-JSON-SKIP", "Information",
                               "گزارش JSON جایابی EENS ساخته نشد؛ مطالعهٔ "
                               "ذخیره‌شده‌ای در پروژه وجود ندارد."))

        check_cancelled()
        report_progress(100, "گزارش‌ها آماده‌اند")
        errors = [i for i in issues if i[1] == "Error"]
        return ExportResult(paths=paths, crosscheck=crosscheck,
                            issues=issues,
                            verdict="PASS" if not errors else "FAIL")

    # ------------------------------------------------------------------
    @staticmethod
    def _load_outage_data(db_path: str | None,
                          issues: list) -> tuple[list, dict]:
        """ماتریس λ/r و شاخص‌های پیوستگی از آخرین اجرای خاموشی پروژه."""
        if not db_path:
            return [], {}
        try:
            from ..persistence.store import ProjectStore
            store = ProjectStore(str(db_path))
            try:
                payload = store.load_outages()
            finally:
                store.close()
        except Exception as exc:                       # noqa: BLE001
            issues.append(("PHASE5-OUTAGE-DATA", "Information",
                           f"دادهٔ خاموشی پروژه خوانده نشد: {exc}"))
            return [], {}
        lam = list(payload.get("lambda_r") or [])
        summary = payload.get("summary") or {}
        indices = summary.get("service_indices") or {}
        if lam:
            issues.append(("PHASE5-OUTAGE-DATA", "Information",
                           f"{len(lam)} ردیف λ/r از پروژه برای جدول شاخص‌ها "
                           "استفاده شد."))
        return lam, dict(indices)

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
    def _render_map(self, m: StudyModel, out_dir: str, *, project_name: str | None = None) -> str | None:
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
        path = str(_out(out_dir, "report_map.png", project_name=project_name))
        renderer.render(
            path, title=f"SwitchLoc — {m.name} (proposed switches = stars)",
            zone_labels=False, proposed_nodes=sorted(set(proposed)),
            manual_nodes=manual)
        return path


_MAP_NOTE = ("نقشه شبکه با ستاره‌های سبز (مکان کلیدهای پیشنهادی) در "
             "انتهای این گزارش آمده است؛ مختصات دقیق در پیوست الف و "
             "خروجی GIS.")


def _out(out_dir: str, name: str, *, project_name: str | None = None):
    """Resolve export path under ``reports/exports/<project_name>/`` when project_name is given.

    If **project_name** is set (non-empty, stripped), the file lands in a subfolder named after the
    sanitized project name (`` |/\\:*?\"<>\\n\\r`` -> ``_``) under *out_dir*, and the .xlsx/.docx/etc
    filename itself is the generic name (e.g., ``SwitchLoc_report.docx``) inside that subfolder.
    When *project_name* is falsy, the path is just ``out_dir/name`` for backward compat (unit tests).
    """
    from pathlib import Path
    import re as _re
    base = Path(out_dir)
    sub = (project_name or "").strip()
    if sub:
        # sanitize for Windows/Unix illegal filename chars
        sub = _re.sub(r'[|/\\:*?\"<>\n\r]', "_", sub).strip()
        sub = sub[:80] or "project"
        d = base / sub
    else:
        d = base
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def _net_of(res, db_path: str):
    """The CanonicalNetwork behind a PlacementRunResult (reloaded once)."""
    from ..persistence.store import ProjectStore
    store = ProjectStore(db_path)
    net, _issues = store.load_network()
    store.close()
    return net
