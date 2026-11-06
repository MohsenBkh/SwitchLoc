# -*- coding: utf-8 -*-
"""MainWindow — PySide6 shell (Phases 1-5 + نیازهای ۱-۱۲, English UI).

Five tabs, zero engineering logic (ARCHITECTURE.md rule 1) — each tab
drives one application service and shows its result:
  1. Data Import — pick the GIS folder or open a project, mapping
     wizard, QC verdict + a persistent result-summary panel, and the
     outage-list import: ONE workbook for all feeders **or** a
     per-feeder outage file entered next to each feeder (نیاز/گردش کار
     مطالعات), with an explicit study-scope box (single/multi-feeder).
  2. Topology    — run TopologyService on the open project; results
     panel with feeders / zones / tie-switch candidates (A-09), the
     engineer's confirm/reject review per candidate (persisted), and a
     "Show on map" shortcut.
  3. Placement   — Phase 4: n-1 (tables 13-15), feeder ranking
     (formula 1 / table 16), switching schemes (table 17 + پیوست ب),
     the five acceptance criteria (نیاز ۱۰: no forced plan — the result
     can be «عدم توجیه نصب کلید»), engineering settings dialog
     (load model / capacities / costs / criteria / coverage) and the
     export-format dialog.
  4. Dashboard   — the management view: KPI cards, λ/r/EP/rank charts,
     the merged feeder matrix (with capacity + plan status) and the
     table-18 comparison (ui/dashboard_data.py + ui/qt/dashboard_tab.py).
  5. Map         — the report renderer (NetworkMapRenderer) inside an
     interactive canvas: wheel zoom at the cursor (1000x / 100 000 %),
     region-zoom magnifier (نیاز ۴), drag pan, zoom-to-feeder, OSM
     background toggle (نیاز ۵), 90° landscape rotation (نیاز ۶),
     feeder filter and zone labels (see ui/qt/map_canvas.py).

Window discipline (نیاز ۲/۷): a splash screen with a real progress bar
stays up until the main window is shown; the window opens at 75 % of
the display size (درخواست کاربر: ۵۰٪ بزرگ‌تر), exactly centered.

Windowed-exe discipline: the PyInstaller exe is built with `--windowed`,
so there is no console.  Every unexpected exception is written to the
rotating log (`switchloc.log`, see logging_setup.py) and also shown in
a message box — a crash is never silent and never lost.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from ... import APP_NAME, __version__
from ...logging_setup import (format_exc as _format_exc, get_logger,
                              log_path_text, setup_logging)
from .i18n import set_language, t

#: kept for backward compatibility (messages now show the real log path)
LOG_NAME = "switchloc.log"
_log = get_logger("ui")

_PANEL_HINT = (
    "Nothing analysed yet.\n\n"
    "1.  Data Import tab  ->  import GIS data or open a project.\n"
    "2.  Press 'Run topology on current project'.\n"
    "3.  Feeders / zones / tie candidates appear here and the Map\n"
    "    tab becomes available.")


def _asset_dir() -> Path:
    """Bundled assets: inside a PyInstaller onefile exe -> sys._MEIPASS,
    in development -> <project>/build_assets."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "build_assets"
    return Path(__file__).resolve().parents[4] / "build_assets"


def _write_log(text: str) -> None:
    """Append text to the central rotating log (never raises)."""
    try:
        _log.error(text.rstrip())
    except Exception:                              # noqa: BLE001
        pass


def _fmt_exc(exc: BaseException) -> str:
    return _format_exc(exc)


def _workspace_dir() -> Path:
    """Writable base folder for ``projects/`` and ``reports/``.

    ``SWITCHLOC_HOME`` > current directory > ``~/Documents/SwitchLoc``
    (a packaged exe may sit in a read-only location such as Program Files).
    """
    cands: list[Path] = []
    env = os.environ.get("SWITCHLOC_HOME")
    if env:
        cands.append(Path(env))
    cands += [Path.cwd(), Path.home() / "Documents" / "SwitchLoc"]
    for c in cands:
        try:
            c.mkdir(parents=True, exist_ok=True)
            probe = c / ".switchloc_write_test"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
            return c
        except OSError:
            continue
    return Path.cwd()


def _projects_dir() -> Path:
    return _workspace_dir() / "projects"


def _reports_dir() -> Path:
    return _workspace_dir() / "reports"


def _close_installer_splash() -> None:
    """Close the PyInstaller splash screen (no-op in development runs)."""
    try:
        import pyi_splash                     # provided by the bootloader
        if pyi_splash.is_alive():
            pyi_splash.close()
    except ImportError:
        pass                                  # development run: no bootloader
    except Exception as exc:                  # noqa: BLE001
        _log.debug("installer splash close failed: %s", exc)


# ----------------------------------------------------------------------
# plain-text renderers for the result panels (no Qt objects — testable)
# ----------------------------------------------------------------------
def fmt_import_result(res) -> str:
    """ImportResult -> multi-line English summary for the Import tab."""
    rep = res.report
    lines = [f"Project     : {rep.project}",
             f"Verdict     : {rep.verdict}",
             f"Features    : {rep.total_features}"]
    if rep.layers:
        lines.append("Layers      :")
        for name in sorted(rep.layers):
            lines.append(f"  - {name}: {rep.layers[name]} features")
    sev = rep.severity_counts
    lines.append(f"Issues      : {sev.get('Error', 0)} error / "
                 f"{sev.get('Warning', 0)} warning / "
                 f"{sev.get('Information', 0)} info")
    lines.append(f"Saved to    : {res.db_path or '(not persisted)'}")
    if res.run_id:
        lines.append(f"Run ID      : {res.run_id}")
    lines.append("")
    lines.append("Next: open the Topology tab and press "
                 "'Run topology on current project'.")
    return "\n".join(lines)


def fmt_topology_result(res) -> str:
    """TopologyResult -> multi-line English summary for the Topology tab."""
    lines = [f"Verdict     : {res.verdict}",
             f"Feeders     : {len(res.traces)}"]
    for t in sorted(res.traces, key=lambda t: t.feeder_key):
        lines.append(f"  - {t.feeder_key}: {len(t.nodes)} nodes, "
                     f"{len(t.edges)} edges, {t.length_m / 1000.0:.1f} km")
    kinds: dict[str, int] = {}
    for z in res.zones.zones:
        kinds[z.kind] = kinds.get(z.kind, 0) + 1
    kind_txt = ", ".join(f"{v} {k}" for k, v in sorted(kinds.items())) or "-"
    lines.append(f"Zones       : {len(res.zones.zones)}  ({kind_txt})")
    lines.append(f"Boundaries  : {len(res.zones.boundaries)}")
    lines.append(f"Tie candidates (A-09): {len(res.ties)}")
    for c in res.ties[:10]:
        sw = c.switch_id or "(no switch in GIS)"
        extra = " [remote-capable]" if c.automation_capable else ""
        lines.append(f"  - {c.id}: {c.feeder_a} <-> {c.feeder_b} at {c.node}"
                     f"  [{sw}]  rule={c.rule}  score={c.score}{extra}")
    if len(res.ties) > 10:
        lines.append(f"  ... {len(res.ties) - 10} more (see topology report)")
    s = res.connectivity.summary()
    lines.append(f"Connectivity: {s['energized_nodes']} energized nodes / "
                 f"{s['deenergized_nodes']} de-energized nodes")
    lines.append("")
    lines.append("Open the Map tab:  wheel = zoom,  left-drag = pan,  "
                 "double-click = zoom in,  'Fit view' = full extent.")
    return "\n".join(lines)


def fmt_placement_result(res) -> str:
    """PlacementResult -> multi-line English summary for the Placement tab."""
    snap = res.to_dict()
    errors = [i for i in snap["issues"] if i["severity"] == "Error"]
    lines = [f"Verdict     : {'PASS' if not errors else 'FAIL'}",
             f"Area model  : {snap['settings'].get('area_mode', '-')} "
             "(strict core — A-09 pending confirmation)",
             f"Study scope : "
             f"{snap['settings'].get('scope_feeder') or 'whole network'}",
             f"Load model  : "
             f"{snap.get('load_model', {}).get('level', '-')} "
             f"(coverage: "
             f"{snap.get('load_model', {}).get('coverage', {})})",
             ""]
    lines.append("Table 14 — EP/TL per feeder (n-1):")
    for r in snap["table14_eptl"]:
        lines.append(f"  - {r['feeder_key']}: EP={r['ep_percent']:.1f}%  "
                     f"TL={r['tl_percent']:.1f}%  "
                     f"load={r['total_load_kw']:.0f} kW  "
                     f"zones={r['zone_count']}")
    lines.append("")
    lines.append("Step 6 — feeder ranking (formula 1, table 16):")
    for r in snap["ranking"]:
        lines.append(f"  #{r['rank']} {r['feeder_key']}: score={r['score']:.4f}  "
                     f"ties={r['ties_count']}  EP={r['ep_percent']:.1f}%  "
                     f"lambda={r['lambda_per_year']:.1f}/yr  "
                     f"r={r['r_minutes']:.1f} min")
    lines.append("")
    lines.append(f"Step 7 — schemes generated: {len(snap['schemes'])}")
    for s in snap["schemes"][:8]:
        lines.append(f"  - {s['kind']} [{', '.join(s['feeders'])}]  "
                     f"{len(s['switches'])} switch(es) — {s['note']}")
    if len(snap["schemes"]) > 8:
        lines.append(f"  ... {len(snap['schemes']) - 8} more")
    lines.append("")
    lines.append("Step 8 — table 18 (CE/CN, ★ = best ratio; acceptance "
                 "decides the plan):")
    for c in snap["table18_comparison"]:
        ratio = "—" if c["ce_over_cn"] is None else \
            format(c["ce_over_cn"], ".4g")
        dec = (snap.get("decisions") or {}).get(c["scheme_id"], {})
        tag = {"accepted": "ACCEPTED",
               "needs_capacity_confirmation": "NEEDS CAPACITY",
               "rejected": "rejected"}.get(dec.get("status", ""), "")
        lines.append(f"  {'★' if c['selected'] else ' '} "
                     f"{c['kind']} [{', '.join(c['feeders'])}]  "
                     f"N={c['n_switches']}  CE={c['ce_rials']:.3e}  "
                     f"CN={c['cn_rials']:.3e}  CE/CN={ratio}  {tag}")
    lines.append("")
    lines.append("Plan per feeder (NO forced plan — نیاز ۱۰):")
    for r in snap["recommendation"]:
        status = r.get("status_fa", r.get("status", ""))
        if r.get("scheme_kind"):
            sws = ", ".join(f"{sw['kind']}@{sw['node'][:8]}"
                             for sw in r["switches"]) or "—"
            lines.append(f"  #{r['rank']} {r['feeder_key']}: "
                         f"[{status}] {r['scheme_kind']}  {sws}")
        else:
            lines.append(f"  #{r['rank']} {r['feeder_key']}: "
                         f"[{status}] — نصب کلید توجیه ندارد")
    lines.append("")
    lines.append(f"Issues: "
                 f"{sum(1 for i in snap['issues'] if i['severity'] == 'Error')} E / "
                 f"{sum(1 for i in snap['issues'] if i['severity'] == 'Warning')} W / "
                 f"{sum(1 for i in snap['issues'] if i['severity'] == 'Information')} I "
                 "— the green stars on the Map tab mark the proposed "
                 "switch locations.")
    return "\n".join(lines)


def fmt_outage_result(res) -> str:
    """OutageResult -> multi-line English summary for the Import tab."""
    stats = res.reader_stats
    lines = [f"Verdict     : {res.verdict}"]
    if stats.get("sources"):
        lines.append("Sources     : per-feeder files")
        for s in stats["sources"]:
            lines.append(f"  - {s['feeder_key']}: "
                         f"{Path(s['file']).name} ({s['records']} records)")
    else:
        lines.append(f"Source      : {Path(stats.get('file', '?')).name}")
    lines.append(f"Records     : {len(res.records):,}  "
                 f"(empty rows skipped: {stats.get('rows_empty_skipped', 0):,})")
    for sname, sst in (stats.get("sheets") or {}).items():
        if sst.get("core_missing"):
            lines.append(f"⚠ Sheet '{sname}': core column(s) NOT found: "
                         f"{', '.join(sst['core_missing'])} — records from "
                         "this sheet may be unusable. Map its headers with "
                         "outage_columns.json (see docs).")
        elif sst.get("headers_unmapped"):
            lines.append(f"ℹ Sheet '{sname}': ignored header(s): "
                         f"{', '.join(sst['headers_unmapped'][:6])}")
    cls = getattr(res, "levels", {}).get("class_summary", {})
    if cls:
        lines.append("Classes     : " +
                     ", ".join(f"{k}={v}" for k, v in
                               sorted(cls.items(), key=lambda kv: -kv[1])))
    cov = getattr(res, "levels", {}).get("coverage") or {}
    if cov and cov.get("start"):
        lines.append(
            f"Coverage    : {cov['start'][0]}/{cov['start'][1]:02d} .. "
            f"{cov['end'][0]}/{cov['end'][1]:02d} — "
            f"{len(cov.get('effective_months') or [])} months with data, "
            f"{cov.get('exposure_days')} days = "
            f"{cov.get('exposure_years'):.4f} yr exposure")
        miss = cov.get("missing_months") or []
        if miss:
            lines.append(f"Missing data: {', '.join(miss)} "
                         "(excluded from the exposure — not zero-outage)")
    lines.append("λ/r matrix  :")
    for f in res.lambda_r:
        lines.append(f"  - {f.feeder_key}: λ={f.lambda_per_year:.2f}/yr  "
                     f"r={f.r_minutes:.1f} min  U={f.u_hours:.2f} h/yr  "
                     f"({f.events_random} random events / "
                     f"{f.exposure_days or f.years_covered} "
                     f"{'days exposure' if f.exposure_days else 'years'})")
    lines.append("")
    lines.append("Next: run Placement — it reads this λ/r matrix "
                 "(latest outage run) automatically.")
    return "\n".join(lines)


def launch(db_path: str | None = None) -> int:      # pragma: no cover (Qt)
    """Start the desktop shell; returns a Qt exit code."""
    try:
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QColor, QFont, QIcon
        from PySide6.QtWidgets import (QAbstractItemView, QApplication,
                                       QCheckBox, QComboBox, QFileDialog,
                                       QFrame, QGridLayout, QHBoxLayout, QDialog,
                                       QDialogButtonBox, QLabel, QListWidget,
                                       QListWidgetItem,
                                       QMainWindow, QMessageBox, QPushButton,
                                       QRadioButton, QTabWidget,
                                       QTableWidget, QTableWidgetItem,
                                       QTextEdit, QVBoxLayout, QWidget, QScrollArea,
                                       QGroupBox, QSizePolicy)
    except ImportError:
        print("PySide6 is not installed: pip install -r requirements-qt.txt")
        return 2

    from ...persistence.store import ProjectStore
    from .chrome import install_chrome
    from .worker import call_in_gui, error_box, install_excepthook, run_task

    setup_logging()
    _log.info("SwitchLoc %s starting", __version__)

    app = QApplication.instance() or QApplication([])
    app.setApplicationName("SwitchLoc")
    app.setOrganizationName("SwitchLoc")

    # language (applied at start-up; RTL layout for Persian)
    try:
        from PySide6.QtCore import QSettings
        set_language(str(QSettings("SwitchLoc", "SwitchLoc")
                         .value("language") or "en"))
    except Exception as exc:                       # noqa: BLE001
        _log.warning("language setting unreadable: %s", exc)
    from .i18n import is_rtl
    if is_rtl():
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    assets = _asset_dir()
    logo = assets / "logo.png"
    if logo.exists():
        app.setWindowIcon(QIcon(str(logo)))

    # -- global safety net: no console exists in the windowed exe ----------
    install_excepthook()

    # -- splash with a REAL progress bar (نیاز ۲) ---------------------------
    # visible from the first moment, fills across the actual start-up
    # steps and closes only after the main window is shown
    from ..qt.splash import make_splash
    splash, step = make_splash(app)
    if splash is not None:
        splash.show()
        app.processEvents()

    # heavy modules load while the splash is visible
    step("Loading engineering modules…")
    from ..map_renderer import NetworkMapRenderer
    from ..qt.dashboard_tab import make_dashboard_tab
    from ..qt.map_canvas import make_map_canvas
    from ..qt.mapping_wizard import MappingWizardPage
    from ...application.import_service import ImportService, ImportSettings
    from ...application.outage_service import OutageService, OutageSettings
    from ...application.outage_review import OutageReviewStore, suggest_event_places
    from ...reliability.zone_outages import calculate_zone_up
    from ...geography.places import PlaceGazetteer
    from ...application.topology_service import TopologyService, TopologySettings

    mono = QFont("Consolas")
    mono.setStyleHint(QFont.StyleHint.Monospace)

    step("Building interface…")
    win = QMainWindow()
    win.setWindowTitle("SwitchLoc — Switch Placement & Automation (TAV122-02/00)")
    if logo.exists():
        win.setWindowIcon(QIcon(str(logo)))
    tabs = QTabWidget()
    win.setCentralWidget(tabs)

    # study workflow strip (نیاز ۱۲ — گردش کار مطالعات) above the pages;
    # the stepper text/theme is owned by the chrome (ui/qt/chrome.py)
    workflow = QLabel("")
    chrome_ref: dict = {"c": None, "wf": "Import"}

    def set_workflow(state_name: str) -> None:
        chrome_ref["wf"] = state_name
        if chrome_ref["c"] is not None:
            chrome_ref["c"].set_workflow(state_name)

    set_workflow("Import")

    state: dict = {"db": db_path, "net": None, "topo": None, "run_id": None,
                   "plc": None, "outage": None,
                   "scope": None,                # None = multi-feeder study
                   "capacity_rows": [],          # نیاز ۹ — GUI-managed
                   "load_model": {}, "criteria": {}, "coverage": {},
                   "weights": [],                # وزن‌های جدول ۱۶ (تأیید ورودی‌ها)
                   "tie_reviews": {},            # نیاز ۱۲ — A-09 review
                   "outage_feeder_files": {},    # فایل خاموشی هر فیدر
                   "manual_evals": [],           # ارزیابی جایابی دستی
                   "lambda_overrides": {},       # تأیید ورودی‌ها — ویرایش λ/r
                   "map_style": None,            # تنظیمات نمایشی نقشه
                   "map_styles_book": {},        # چند استایل نام‌گذاری‌شده
                   "map_style_name": "",
                   "report_project_name": "",    # نام پروژه در گزارش (مورد ۴)
                   "plan_reviews": {},           # تأیید نهایی مهندسی
                   "_loading": False, "dirty": False}

    step("Preparing map canvas…")
    map_tab = make_map_canvas(win)
    dash_tab = make_dashboard_tab(win)

    # ---------------- Dashboard refresh ----------------------------------
    def refresh_dashboard() -> None:
        """Rebuild the management dashboard from the current state."""
        from ..dashboard_data import build_dashboard
        src = state.get("outage") or state.get("outage_store")
        lam_src = "outage list (latest run)" if src else \
            "no outage data (λ = 0)"
        dash = build_dashboard(net=state.get("net"), topo=state.get("topo"),
                               outage=src, placement=state.get("plc")
                               and state["plc"].result,
                               db_path=str(state.get("db") or ""),
                               lambda_source=lam_src,
                               capacity_rows=state.get("capacity_rows") or [],
                               scope=state.get("scope"))
        dash_tab.show_dashboard(dash)

    # ---------------- chrome helpers (status bar / recent / CRS) ----------
    def status_msg(text: str) -> None:
        if chrome_ref["c"] is not None:
            chrome_ref["c"].status(text)

    def project_crs() -> str | None:
        """CRS of the open project (from its imported layers) or None —
        never a hard-coded site default."""
        net = state.get("net")
        for cd in (getattr(net, "crs_definitions", None) or []):
            epsg = getattr(cd, "epsg", None)
            if epsg:
                return f"EPSG:{int(epsg)}"
        return None

    def refresh_project_info() -> None:
        ch = chrome_ref["c"]
        if ch is None:
            return
        net = state.get("net")
        name = Path(state["db"]).stem if state.get("db") else ""
        n_feeders = None
        if net is not None:
            try:
                n_feeders = int(net.summary().get("feeders", 0))
            except Exception as exc:               # noqa: BLE001
                _log.debug("feeder count unavailable: %s", exc)
        ch.set_project_info(name, n_feeders, project_crs() or "")

    def remember_project(path) -> None:
        if path and chrome_ref["c"] is not None:
            chrome_ref["c"].add_recent(str(path))
        refresh_project_info()

    # ---------------- project KV (استایل‌ها + نام گزارش) ------------------
    # درخواست کاربر (مورد ۲): چند استایل نمایشی داخل فایل پروژه ذخیره شود
    # و پس از بستن/بازکردن پروژه همان تنظیمات برگردد.
    def _persist_project_kv() -> None:
        if not state.get("db"):
            return
        try:
            store = ProjectStore(str(state["db"]))
            book = dict(state.get("map_styles_book") or {})
            active_name = state.get("map_style_name") or "پیش‌فرض"
            if state.get("map_style") is not None:
                book[active_name] = state["map_style"].as_dict()
                state["map_styles_book"] = book
                state["map_style_name"] = active_name
            store.set_kv("map_styles", book)
            store.set_kv("map_style_active", active_name)
            store.set_kv("report_project_name",
                         state.get("report_project_name") or "")
            store.close()
            state["dirty"] = True
        except Exception as exc:                   # noqa: BLE001
            _write_log(_fmt_exc(exc))

    def _load_project_kv(path: str) -> None:
        try:
            store = ProjectStore(str(path))
            book = store.get_kv("map_styles") or {}
            name = store.get_kv("map_style_active") or ""
            state["report_project_name"] = store.get_kv(
                "report_project_name") or ""
            store.close()
        except Exception as exc:                   # noqa: BLE001
            _log.warning("project settings of %s not loaded: %s", path, exc)
            return
        if isinstance(book, dict) and book:
            from ..map_style import MapStyle
            state["map_styles_book"] = book
            state["map_style_name"] = name if name in book else \
                next(iter(sorted(book)), "")
            state["map_style"] = MapStyle.from_dict(
                book[state["map_style_name"]])
            map_tab.zone_labels.setChecked(
                bool(state["map_style"].show_zone_labels))

    # ---------------- map style dialog (موارد ۱ و ۲) -----------------------
    def open_map_style() -> None:
        from ..map_style import MapStyle
        from ..qt.map_style_dialog import make_map_style_dialog
        keys = feeder_keys()
        style = state.get("map_style") or MapStyle.default_for(feeders=keys)
        dlg = make_map_style_dialog(
            win, keys, style, state.get("map_styles_book") or {},
            state.get("map_style_name") or "")
        if not dlg.exec():
            return
        state["map_style"] = dlg.result_style()
        map_tab._selected_feeders = None
        map_tab.zone_labels.setChecked(bool(state["map_style"].show_zone_labels))
        state["map_styles_book"] = dlg.result_book()
        state["map_style_name"] = dlg.result_active()
        _persist_project_kv()
        refresh_map()
    map_tab.on_style_request = open_map_style
    def _persist_map_feeders() -> None:
        if getattr(map_tab, "_renderer", None) is not None:
            state["map_style"] = map_tab._renderer.style
        _persist_project_kv()
    map_tab.on_feeders_changed = _persist_map_feeders

    # ---------------- feeder keys of the open project ---------------------
    def feeder_keys() -> list:
        net = state.get("net")
        topo = state.get("topo")
        if topo is not None and getattr(topo, "traces", None):
            return sorted({t.feeder_key for t in topo.traces if t.feeder_key})
        if net is None:
            return []
        from ...topology.tracing import feeder_key as normalize_feeder_key
        keys = {normalize_feeder_key(n.feeder_name)
                for n in net.nodes if n.feeder_name}
        return sorted(k for k in keys if k)

    def study_feeder_keys() -> list:
        """Feeder data requested by the active study scope; GIS still keeps
        the full network for connectivity/backup tracing."""
        from ..inputs_model import scoped_feeder_keys
        scope = state.get("scope")
        if rb_selected.isChecked() and isinstance(scope, (list, tuple, set)) and not scope:
            return []
        return scoped_feeder_keys(feeder_keys(), scope)

    def feeder_s_rated() -> dict:
        """Σ ظرفیت نامی ترانس‌های هر فیدر (برچسب GIS) — برای پیش‌نمایش
        Load Scaling و ورود ظرفیت (نیاز ۹/۱۱)."""
        from ..dashboard_data import gis_transformer_map
        g = gis_transformer_map(state.get("net"))
        return {k: v.get("s_rated_kva", 0.0) for k, v in g.items()
                if k != "(بدون برچسب)"}

    # ---------------- Data Import tab — TWO COLUMNS (درخواست کاربر) -------
    # چپ: ورود GIS + دامنه مطالعه + نتیجه ورود | راست: داده‌های خاموشی +
    # جدول فایل هر فیدر + نتیجه خاموشی — دو پنجره کنار هم.
    from PySide6.QtWidgets import QSplitter
    from ..qt.widgets import (fill_table, make_explain_label,
                              make_required_label)
    import_tab = QWidget()
    import_cols = QHBoxLayout(import_tab)
    splitter = QSplitter()   # horizontal by default
    import_cols.addWidget(splitter)
    left_pane = QWidget()
    left_col = QVBoxLayout(left_pane)
    left_col.setContentsMargins(4, 4, 4, 4)
    right_pane = QWidget()
    right_col = QVBoxLayout(right_pane)
    right_col.setContentsMargins(4, 4, 4, 4)
    splitter.addWidget(left_pane)
    splitter.addWidget(right_pane)
    splitter.setSizes([560, 560])

    head = QLabel("<b>Data Import — GIS to DGS pipeline (Phase 1) + study "
                  "workflow (نیاز ۱۲)</b>")
    desc = make_explain_label(
        "پوشه حاوی Shapefile / GeoJSON / GPKG / Excel / CSV را وارد کنید. "
        "جادوک تطبیق لایه‌ها تأیید صریح می‌خواهد، نتیجه کنترل کیفیت "
        "محاسبه و شبکه کانونی در projects\\<folder>.sqlite ذخیره می‌شود "
        "— یا پروژه موجود را باز کنید. فیلدهای ستاره‌دار (*) الزامی‌اند "
        "و از فایل‌های ورودی قابل دریافت نیستند.")
    left_col.addWidget(head)
    left_col.addWidget(desc)

    import_panel = QTextEdit()
    import_panel.setReadOnly(True)
    import_panel.setFont(mono)
    try:                       # QTextEdit.setPlaceholderText needs Qt >= 6.7
        import_panel.setPlaceholderText("Import result summary will appear here.")
    except AttributeError:
        pass

    # -- study scope: whole / single / selected multi-feeder ---------------
    scope_box = QWidget(); scope_v = QVBoxLayout(scope_box)
    scope_v.setContentsMargins(0, 0, 0, 0)
    scope_lay = QHBoxLayout()
    scope_lay.addWidget(QLabel("<b>Study type:</b>"))
    rb_multi = QRadioButton("Whole network")
    rb_single = QRadioButton("Single feeder:")
    rb_selected = QRadioButton("Selected feeders (multi-feeder):")
    rb_multi.setChecked(True)
    scope_cmb = QComboBox()
    scope_cmb.setEnabled(False)
    scope_cmb.setMinimumWidth(160)
    scope_lay.addWidget(rb_multi)
    scope_lay.addWidget(rb_single)
    scope_lay.addWidget(scope_cmb)
    scope_lay.addWidget(rb_selected)
    scope_lay.addStretch(1)
    scope_v.addLayout(scope_lay)
    scope_list = QListWidget()
    scope_list.setMaximumHeight(115)
    scope_list.setMinimumHeight(65)
    scope_list.setToolTip(
        "برای مطالعه چندفیدری، فیدرهای موردنظر را تیک بزنید؛ "
        "رتبه‌بندی فقط بین همین فیدرها انجام می‌شود.")
    scope_list.setEnabled(False)
    scope_v.addWidget(scope_list)

    def _scope_selection() -> None:
        if rb_single.isChecked():
            state["scope"] = (scope_cmb.currentText()
                               if scope_cmb.currentIndex() > 0 else None)
        elif rb_selected.isChecked():
            state["scope"] = [
                str(scope_list.item(i).data(Qt.ItemDataRole.UserRole))
                for i in range(scope_list.count())
                if scope_list.item(i).checkState() == Qt.CheckState.Checked]
        else:
            state["scope"] = None
        refresh_outage_feeder_table()
        refresh_manual_feeders()
        refresh_tie_table()
        refresh_plan_table()
        refresh_map()
        refresh_dashboard()

    def _scope_mode_changed(_on=False) -> None:
        scope_cmb.setEnabled(rb_single.isChecked())
        scope_list.setEnabled(rb_selected.isChecked())
        _scope_selection()

    rb_multi.toggled.connect(_scope_mode_changed)
    rb_single.toggled.connect(_scope_mode_changed)
    rb_selected.toggled.connect(_scope_mode_changed)
    scope_cmb.currentTextChanged.connect(lambda _t: _scope_selection())
    scope_list.itemChanged.connect(lambda _it: _scope_selection())

    def scope_is_restricted() -> bool:
        return rb_single.isChecked() or rb_selected.isChecked()

    def scope_is_valid() -> bool:
        return bool(study_feeder_keys()) if scope_is_restricted() else True

    def scope_label() -> str:
        active = study_feeder_keys()
        if not scope_is_restricted():
            return "کل شبکه"
        if not active:
            return "هیچ فیدری انتخاب نشده"
        if rb_single.isChecked():
            return f"تک‌فیدری: {active[0]}"
        return f"چندفیدری ({len(active)}): {', '.join(active)}"

    def refresh_scope_choices() -> None:
        keys = feeder_keys()
        current = state.get("scope")
        if isinstance(current, str):
            selected = {current}
        else:
            selected = set(current or [])
        scope_cmb.blockSignals(True)
        scope_cmb.clear()
        scope_cmb.addItem("— select feeder —")
        for k in keys:
            scope_cmb.addItem(k)
        if len(selected) == 1 and next(iter(selected)) in keys:
            scope_cmb.setCurrentText(next(iter(selected)))
        scope_cmb.blockSignals(False)
        scope_list.blockSignals(True)
        scope_list.clear()
        for k in keys:
            item = QListWidgetItem(k)
            item.setData(Qt.ItemDataRole.UserRole, k)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if k in selected
                               else Qt.CheckState.Unchecked)
            scope_list.addItem(item)
        scope_list.blockSignals(False)
        if rb_single.isChecked():
            state["scope"] = (scope_cmb.currentText()
                              if scope_cmb.currentIndex() > 0 else None)
        elif rb_selected.isChecked():
            state["scope"] = sorted(selected.intersection(keys))
        else:
            state["scope"] = None
        refresh_outage_feeder_table()

    left_col.addWidget(scope_box)
    left_col.addWidget(make_explain_label(
        "سه دامنه مطالعه قابل انتخاب است: کل شبکه، یک فیدر، یا هر مجموعه "
        "دلخواه از فیدرها. در حالت چندفیدری، رتبه‌بندی و طرح‌ها فقط میان "
        "فیدرهای تیک‌خورده انجام می‌شود. توپولوژی کامل GIS همچنان برای "
        "شناخت اتصال‌ها نگهداری می‌شود؛ فیلتر نمایش کلیدها در نقشه نیز "
        "هیچ اثری بر محاسبات ندارد."))

    # -- per-feeder outage files (همزمان با شیپ‌فایل فیدرها) — ستون راست ---
    outage_feeder_box = QWidget()
    of_lay = QVBoxLayout(outage_feeder_box)
    of_lay.setContentsMargins(0, 0, 0, 0)
    of_lay.addWidget(make_explain_label(
        "<b>فایل خاموشی هر فیدر</b> — کنار داده GIS هر فیدر، کتاب‌کار "
        "خاموشی همان فیدر را وارد کنید (دوبار کلیک روی ردیف). پردازش، "
        "λ/r و مواجهه واقعی داده را محاسبه می‌کند (نیاز ۸). ورود فایل "
        "خاموشی اختیاری است؛ بدون آن λ=۰ فرض و صریحاً اعلام می‌شود."))
    of_table = QTableWidget(0, 2)
    of_table.setHorizontalHeaderLabels(["Feeder", "Outage workbook (xlsx)"])
    of_table.horizontalHeader().setStretchLastSection(True)
    of_table.verticalHeader().setVisible(False)
    of_table.setMaximumHeight(160)
    of_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    from ..qt.widgets import enable_copy_paste
    enable_copy_paste(of_table)
    of_lay.addWidget(of_table)
    right_col.addWidget(outage_feeder_box)

    def refresh_outage_feeder_table() -> None:
        files = state.setdefault("outage_feeder_files", {})
        keys = study_feeder_keys()
        of_table.setRowCount(len(keys))
        for i, k in enumerate(keys):
            it = QTableWidgetItem(k)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            of_table.setItem(i, 0, it)
            of_table.setItem(i, 1, QTableWidgetItem(files.get(k, "")))

    def do_pick_feeder_outage(row: int) -> None:
        files = state.setdefault("outage_feeder_files", {})
        path, _ = QFileDialog.getOpenFileName(
            win, f"Outage workbook of feeder "
                 f"{of_table.item(row, 0).text()}", "",
            "Excel workbook (*.xlsx *.xlsm)")
        if not path:
            return
        files[of_table.item(row, 0).text()] = path
        of_table.item(row, 1).setText(path)

    of_table.doubleClicked.connect(
        lambda idx: do_pick_feeder_outage(idx.row()))

    left_col.addWidget(QLabel("Last import result:"))
    left_col.addWidget(import_panel, 1)

    btn_row = QHBoxLayout()
    btn_import = QPushButton(t("Choose folder & import GIS data…"))
    btn_open = QPushButton(t("Open project (.sqlite)…"))
    btn_row.addWidget(btn_import)
    btn_row.addWidget(btn_open)
    btn_row.addStretch(1)
    left_col.addLayout(btn_row)

    def do_import() -> None:
        folder = QFileDialog.getExistingDirectory(
            win, "Select the GIS data folder (Shapefile / GeoJSON / GPKG / Excel / CSV)")
        if not folder:
            return
        out_db = (Path(state["db"]) if state.get("db") and state.get("net") is None
                  else _projects_dir() / f"{Path(folder).name}.sqlite")
        out_db.parent.mkdir(parents=True, exist_ok=True)
        settings = ImportSettings(project_name=Path(folder).name,
                                  user="ui-user", out_db=str(out_db))
        svc = ImportService(settings)

        def confirm(suggestions, mapping, layers):
            # runs in the worker thread → the dialog must open on the GUI
            # thread (call_in_gui waits for the engineer's answer)
            def _ask():
                dlg = MappingWizardPage(suggestions, mapping, layers, win)
                ok = dlg.exec()
                return ok and dlg.apply()
            return call_in_gui(_ask)

        run_task(win, "Importing GIS data…",
                 lambda: svc.run(Path(folder), confirm_fn=confirm),
                 _import_done, error_box(win, "Import failed"),
                 title="Import")

    def _import_done(res) -> None:
        state["net"] = res.network
        state["dirty"] = True
        state["db"] = res.db_path
        state["run_id"] = res.run_id
        state["topo"] = None
        state["plc"] = None
        state["outage"] = None          # a fresh project has no outage run
        state["outage_store"] = None
        state["capacity_rows"] = []
        state["manual_evals"] = []
        state["lambda_overrides"] = {}
        state["weights"] = []
        import_panel.setPlainText(fmt_import_result(res))
        refresh_scope_choices()
        refresh_outage_feeder_table()
        QMessageBox.information(
            win, "Import result",
            f"Verdict: {res.report.verdict} — {res.issues.count()} issue(s).\n"
            f"Saved to: {res.db_path or '(not persisted)'}\n\n"
            "Next step 1: enter each feeder's outage workbook below and "
            "press 'Process outage files'.\n"
            "Next step 2: open the Topology tab and run the network "
            "analysis.")
        refresh_map()
        refresh_dashboard()
        remember_project(res.db_path)

    def do_open_project(path: str | None = None) -> None:
        if not _confirm_pending_changes():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                win, "Open SwitchLoc project database",
                str(_projects_dir()), "SwitchLoc project (*.sqlite)")
        if not path:
            return

        def _load():
            store = ProjectStore(str(path))
            try:
                return store.load_network()
            finally:
                store.close()

        def _loaded(result) -> None:
            net, _issues = result
            _project_opened(str(path), net)

        run_task(win, "Opening project…", _load, _loaded,
                 error_box(win, "Open project failed"),
                 title="Open project")

    def _project_opened(path: str, net) -> None:
        if net is None:
            QMessageBox.warning(win, "Open project",
                                "The database contains no importable network.")
            return
        state["net"], state["db"] = net, str(path)
        state["dirty"] = False
        state["topo"] = state["run_id"] = None
        state["plc"] = None
        topo_panel.setPlainText(_PANEL_HINT)
        btn_show_map.setEnabled(False)
        _load_project_kv(str(path))          # استایل‌ها + نام گزارش (مورد ۲/۴)
        # a persisted outage run of THIS project feeds the dashboard λ/r
        state["outage"] = None
        state["outage_store"] = None
        try:
            _st = ProjectStore(str(path))
            state["outage_store"] = _st.load_outages()
            _st.close()
        except ValueError:
            state["outage_store"] = None           # project has no outage run
        except Exception as exc:                       # noqa: BLE001
            _log.warning("outage data of %s not loaded: %s", path, exc)
            state["outage_store"] = None
        try:   # capacities persisted for THIS project (نیاز ۹)
            _st = ProjectStore(str(path))
            state["capacity_rows"] = [c.as_dict() for c in
                                      _st.load_feeder_capacity().values()]
            state["tie_reviews"] = _st.load_tie_reviews()
            _st.close()
        except Exception as exc:                       # noqa: BLE001
            _log.warning("capacities of %s not loaded: %s", path, exc)
            state["capacity_rows"] = []
        try:   # a project that already has a placement run → exports ready
            _st = ProjectStore(str(path))
            _has_plc = bool(_st.list_placement_runs())
            _st.close()
        except Exception as exc:                       # noqa: BLE001
            _log.warning("placement runs of %s not listed: %s", path, exc)
            _has_plc = False
        btn_exports.setEnabled(_has_plc)
        s = net.summary()
        import_panel.setPlainText(
            f"Project     : {s.get('project', '')}\n"
            f"Opened from : {path}\n"
            f"Nodes       : {s.get('nodes', 0)}    "
            f"Branches: {s.get('branches', 0)}    "
            f"Switches: {s.get('switches', 0)}\n"
            f"Transformers: {s.get('transformers', 0)}    "
            f"Loads: {s.get('loads', 0)}    "
            f"Feeders: {s.get('feeders', 0)}\n\n"
            "Next: enter the per-feeder outage files (if available), then "
            "run topology.")
        refresh_scope_choices()
        refresh_outage_feeder_table()
        refresh_manual_feeders()
        refresh_map()
        refresh_dashboard()
        remember_project(str(path))

    btn_import.clicked.connect(lambda *_: do_import())
    btn_open.clicked.connect(lambda *_: do_open_project())

    # -- outage processing (نیاز ۸ + per-feeder ورود) — ستون راست ----------
    right_col.addWidget(make_explain_label(
        "<b>داده‌های خاموشی</b> — یک کتاب‌کار جمعی «یا» فایل‌های "
        "هر فیدر بالا؛ موتور، شش طبقه را دسته‌بندی و λ/r را روی مواجهه "
        "واقعی داده محاسبه می‌کند (ماه‌های بدون داده حدس زده نمی‌شوند) "
        "و ماتریس در پروژه ذخیره می‌شود."))
    btn_row_o = QHBoxLayout()
    btn_outage = QPushButton(t("Import outage list (single workbook)…"))
    btn_outage_feeders = QPushButton(t("Process per-feeder outage files"))
    btn_row_o.addWidget(btn_outage)
    btn_row_o.addWidget(btn_outage_feeders)
    btn_review_outages = QPushButton("Review outage places / zones")
    btn_review_outages.setEnabled(False)
    btn_row_o.addWidget(btn_review_outages)
    btn_row_o.addStretch(1)
    right_col.addLayout(btn_row_o)

    outage_panel = QTextEdit()
    outage_panel.setReadOnly(True)
    outage_panel.setFont(mono)
    try:
        outage_panel.setPlaceholderText(
            "Outage analysis summary will appear here.")
    except AttributeError:
        pass
    right_col.addWidget(outage_panel, 1)

    def review_outage_locations() -> None:
        """Engineer confirms event place and affected zone; no auto-assignment."""
        records = list(getattr(state.get("outage"), "records", []) or [])
        topo = state.get("topo")
        if not records or topo is None or not getattr(topo, "zones", None):
            QMessageBox.information(win, "Outage review",
                                    "ابتدا فایل خاموشی را وارد و تحلیل توپولوژی را اجرا کنید.")
            return
        db_path = state.get("db")
        if not db_path:
            return
        gaz_path = Path(__file__).resolve().parents[4] / "data" / "geography" / "ardabil_places.sqlite"
        gaz = PlaceGazetteer(gaz_path)
        suggestions = {x.event_id: x for x in suggest_event_places(records, gaz)}
        zones = list(topo.zones.zones)
        zone_labels = [(f"{z.feeder} | Zone {z.zone_no} | {z.id}", z.id) for z in zones]
        store = OutageReviewStore(db_path)
        saved = store.load()
        dlg = QDialog(win)
        dlg.setWindowTitle("بازبینی محل و زون رخدادهای خاموشی")
        dlg.resize(1380, 760)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint |
                           Qt.WindowType.WindowMinimizeButtonHint)
        layout = QVBoxLayout(dlg)
        info = QLabel(f"پیشنهاد نام مکان صرفاً راهنماست (تعداد مکان‌های ثبت‌شده در بانک: {gaz.count():,}). فقط زونی که مهندس صریحاً انتخاب و تأیید کند ذخیره می‌شود؛ رخدادهای بدون انتساب در محاسبات زون توزیع نمی‌شوند.")
        info.setWordWrap(True)
        layout.addWidget(info)
        table = QTableWidget(len(records), 8, dlg)
        table.setHorizontalHeaderLabels(["رخداد", "نام پست", "فیدر", "تاریخ", "توضیحات", "مکان پیشنهادی", "زون متاثر (تأیید مهندس)", "وضعیت"])
        table.setWordWrap(True)
        table.setAlternatingRowColors(True)
        table.setColumnWidth(0, 90); table.setColumnWidth(1, 150)
        table.setColumnWidth(2, 75); table.setColumnWidth(3, 95)
        table.setColumnWidth(4, 320); table.setColumnWidth(5, 170)
        table.setColumnWidth(6, 250); table.setColumnWidth(7, 110)
        for i, rec in enumerate(records):
            table.setItem(i, 0, QTableWidgetItem(str(rec.event_no or rec.id)))
            table.setItem(i, 1, QTableWidgetItem(str(rec.substation or "—")))
            table.setItem(i, 2, QTableWidgetItem(str(rec.feeder_key or rec.feeder_raw)))
            table.setItem(i, 3, QTableWidgetItem(str(rec.date_j or "")))
            table.setItem(i, 4, QTableWidgetItem(str(rec.notes or rec.cause_raw or "")))
            sug = suggestions.get(str(rec.id))
            place_box = QComboBox()
            place_box.addItem("بدون مکان تأییدشده", "")
            if sug:
                for m in sug.matches:
                    place_box.addItem(
                        f"{m.place.name} ({m.confidence}) — "
                        f"{m.place.lat:.5f}, {m.place.lon:.5f}",
                        m.place.place_id)
            old = saved.get(str(rec.id), {})
            old_pid = old.get("place_id", "")
            ix = place_box.findData(old_pid)
            if ix >= 0: place_box.setCurrentIndex(ix)
            table.setCellWidget(i, 5, place_box)
            zone_box = QComboBox()
            zone_box.addItem("— انتخاب زون —", "")
            from ...topology.tracing import feeder_key as _norm_fk
            rec_fk = str(rec.feeder_key or _norm_fk(rec.feeder_raw) or "").strip()
            feeder_zones = [(label, zid) for label, zid in zone_labels
                            if not rec_fk or label.split(" | ", 1)[0] == rec_fk]
            for label, zid in feeder_zones: zone_box.addItem(label, zid)
            zi = zone_box.findData(old.get("zone_id", ""))
            if zi >= 0: zone_box.setCurrentIndex(zi)
            table.setCellWidget(i, 6, zone_box)
            status_box = QComboBox()
            status_box.addItem("در انتظار بررسی", "pending")
            status_box.addItem("تأیید مهندس", "confirmed")
            status_box.addItem("رد رخداد", "rejected")
            status_box.setCurrentIndex(max(0, status_box.findData(old.get("status", "pending"))))
            table.setCellWidget(i, 7, status_box)
            table.setRowHeight(i, 48)
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        buttons.rejected.connect(dlg.reject)
        def save_reviews():
            n = 0
            for i, rec in enumerate(records):
                zone_box = table.cellWidget(i, 6)
                status_box = table.cellWidget(i, 7)
                place_box = table.cellWidget(i, 5)
                zid, status = zone_box.currentData(), status_box.currentData()
                if status == "pending" or (status == "confirmed" and not zid):
                    continue
                place_id = place_box.currentData() or ""
                place_name = place_box.currentText() if place_id else ""
                store.save(str(rec.id), str(zid), place_id=str(place_id),
                           place_name=place_name, reviewer="engineer-ui", status=str(status))
                rec.review_status = "confirmed" if status == "confirmed" else "rejected"
                n += 1
            state["outage_zone_assignments"] = store.confirmed_event_to_zone()
            state["dirty"] = True
            coverage = (getattr(state.get("outage"), "levels", {}) or {}).get("coverage") or {}
            exposure_years = float(coverage.get("exposure_years") or 0.0)
            if exposure_years > 0 and state.get("topo") is not None:
                from ..dashboard_data import zone_load_map
                loads = zone_load_map(state["topo"], state.get("net"),
                                      state.get("load_model") or {},
                                      placement=(state["plc"].result if state.get("plc") else None))
                if any(float(v or 0) > 0 for v in loads.values()):
                    metrics = calculate_zone_up(records, state["outage_zone_assignments"],
                                                loads, exposure_years)
                    state["zone_up_mwh"] = {z: m.up_mwh_per_year for z, m in metrics.items()}
                    state["zone_outage_hours"] = {z: m.outage_hours_per_year for z, m in metrics.items()}
                    refresh_map()
                    summary = f"شاخص‌های زون نیز محاسبه شد؛ مبنای مواجهه {exposure_years:.4f} سال."
                else:
                    summary = "بار زون در مدل بار فعلی قابل محاسبه نیست؛ شاخص U×P تا تکمیل بار نامشخص می‌ماند."
            else:
                summary = "پوشش زمانی معتبر در دسترس نیست؛ شاخص سالانه U×P محاسبه نشد."
            QMessageBox.information(dlg, "ذخیره بازبینی", f"{n} انتساب/رد مهندسی ذخیره شد. رخدادهای تأییدنشده بدون انتساب باقی ماندند.\n{summary}")
            dlg.accept()
        buttons.accepted.connect(save_reviews)
        dlg.exec()

    btn_review_outages.clicked.connect(lambda *_: review_outage_locations())

    def do_outage_import() -> None:
        """Phase 3 on the open project: read → classify → λ/r → persist."""
        if not state.get("db"):
            QMessageBox.warning(
                win, "Outage import",
                "Open or import a project first — the outage records are "
                "attached to the same project database.")
            return
        if not scope_is_valid():
            QMessageBox.warning(win, "Study scope",
                                "برای تحلیل محدود، دست‌کم یک فیدر را انتخاب کنید.")
            return
        path, _ = QFileDialog.getOpenFileName(
            win, "Select the outage list workbook (Excel)", "",
            "Excel workbook (*.xlsx *.xlsm)")
        if not path:
            return
        cov = dict(state.get("coverage") or {})
        db = state["db"]

        def work():
            return OutageService(OutageSettings(
                user="ui-user", persist=True,
                model_feeders=tuple(study_feeder_keys()),
                scope_feeder=(state.get("scope") if isinstance(state.get("scope"), str) else None),
                scope_feeders=(tuple(state.get("scope") or [])
                               if isinstance(state.get("scope"), (list, tuple, set)) else ()),
                coverage_start=cov.get("start"),
                coverage_end=cov.get("end"),
                force_cover_months=tuple(cov.get("force_cover_months") or ()),
                force_exclude_months=tuple(
                    cov.get("force_exclude_months") or ()),
            )).run(path, out_db=db, report_dir=str(_reports_dir()),
                   project_name=Path(db).stem)

        def done(res) -> None:
            state["dirty"] = True
            state["outage"] = res
            btn_review_outages.setEnabled(bool(res.records) and state.get("topo") is not None)
            outage_panel.setPlainText(fmt_outage_result(res))
            refresh_dashboard()
            QMessageBox.information(
                win, "Outage analysis ready",
                f"Verdict: {res.verdict}\n"
                f"Records: {len(res.records):,}"
                f"\n\nThe λ/r matrix (real exposure basis) was saved into "
                f"the project; Placement uses it automatically.")

        run_task(win, "Analysing outage list…", work, done,
                 error_box(win, "Outage import failed"),
                 title="Outage analysis")

    def do_outage_per_feeder() -> None:
        """ورود فایل خاموشی «هر فیدر» + پردازش مشترک → نتیجه (نیاز/گردش کار)."""
        if not state.get("db"):
            QMessageBox.warning(
                win, "Per-feeder outages",
                "Open or import a project first — the feeder list comes "
                "from the imported network.")
            return
        if not scope_is_valid():
            QMessageBox.warning(win, "Study scope",
                                "برای تحلیل محدود، دست‌کم یک فیدر را انتخاب کنید.")
            return
        active_keys = set(study_feeder_keys())
        files = {k: v for k, v in
                 state.setdefault("outage_feeder_files", {}).items()
                 if v and k in active_keys}
        if not files:
            QMessageBox.information(
                win, "Per-feeder outages",
                "No file selected yet — double-click a feeder row in the "
                "table above and pick its outage workbook.")
            return
        cov = dict(state.get("coverage") or {})
        db = state["db"]

        def work():
            return OutageService(OutageSettings(
                user="ui-user", persist=True,
                model_feeders=tuple(study_feeder_keys()),
                per_feeder_files=dict(files),
                scope_feeder=(state.get("scope") if isinstance(state.get("scope"), str) else None),
                scope_feeders=(tuple(state.get("scope") or [])
                               if isinstance(state.get("scope"), (list, tuple, set)) else ()),
                coverage_start=cov.get("start"),
                coverage_end=cov.get("end"),
                force_cover_months=tuple(cov.get("force_cover_months") or ()),
                force_exclude_months=tuple(
                    cov.get("force_exclude_months") or ()),
            )).run(out_db=db, report_dir=str(_reports_dir()),
                   project_name=Path(db).stem)

        def done(res) -> None:
            state["dirty"] = True
            state["outage"] = res
            btn_review_outages.setEnabled(bool(res.records) and state.get("topo") is not None)
            outage_panel.setPlainText(fmt_outage_result(res))
            refresh_dashboard()
            QMessageBox.information(
                win, "Outage analysis ready (per-feeder files)",
                f"Verdict: {res.verdict}\n"
                f"Feeder files processed: {len(files)}\n"
                f"Records: {len(res.records):,}\n\n"
                f"λ/r saved into the project with the real exposure basis.")

        run_task(win, "Processing per-feeder outage files…", work, done,
                 error_box(win, "Per-feeder outage processing failed"),
                 title="Outage analysis")

    btn_outage.clicked.connect(lambda *_: do_outage_import())
    btn_outage_feeders.clicked.connect(lambda *_: do_outage_per_feeder())

    # ---------------- Topology tab -----------------------------------------
    topo_tab = QWidget()
    topo_lay = QVBoxLayout(topo_tab)
    topo_lay.addWidget(QLabel(
        "<b>Topology — graph, feeder tracing, zones, tie candidates "
        "(Phase 2)</b>"))
    topo_desc = make_explain_label(
        "گراف از شبکه واردشده ساخته می‌شود، هر فیدر در وضعیت عادی ردیابی "
        "می‌شود، کاندیدهای نقطه اتصال باز (A-09) کشف، زون‌بندی انجام و "
        "اتصال‌پذیری کنترل می‌شود. هر کاندید توسط مهندس بازبینی و تأیید "
        "می‌شود (ذخیره در پروژه). جدول‌ها با کلیک روی هدر ستون مرتب و با "
        "Ctrl+C کپی می‌شوند.")
    topo_lay.addWidget(topo_desc)

    topo_panel = QTextEdit()
    topo_panel.setReadOnly(True)
    topo_panel.setFont(mono)
    topo_panel.setPlainText(_PANEL_HINT)

    btn_show_map = QPushButton(t("Show on map"))
    btn_show_map.setEnabled(False)

    def do_topology() -> None:
        if state.get("net") is None:
            QMessageBox.warning(
                win, "Topology",
                "Import GIS data first (Data Import tab) or start the app "
                "with a project file:  SwitchLoc.exe projects\\x.sqlite")
            return
        net, run_id, db = state["net"], str(state.get("run_id") or ""), \
            state.get("db")

        def work():
            return TopologyService(TopologySettings(user="ui-user")).run(
                net, source_run_id=run_id, out_db=db)

        def done(res) -> None:
            state["dirty"] = True
            state["topo"] = res
            btn_review_outages.setEnabled(bool(getattr(state.get("outage"), "records", [])))
            topo_panel.setPlainText(fmt_topology_result(res))
            btn_show_map.setEnabled(True)
            refresh_scope_choices()
            refresh_tie_table()
            refresh_manual_feeders()
            refresh_map()
            refresh_dashboard()
            set_workflow("Topology")
            QMessageBox.information(
                win, "Topology result",
                f"Verdict: {res.verdict}\n"
                f"Feeders traced: {len(res.traces)}\n"
                f"Tie-switch candidates: {len(res.ties)}\n\n"
                f"Details are shown in this tab; the Map tab is now "
                f"interactive.")

        run_task(win, "Running topology analysis…", work, done,
                 error_box(win, "Topology failed"), title="Topology")

    btn_row2 = QHBoxLayout()
    btn_topo = QPushButton(t("Run topology on current project"))
    btn_topo.clicked.connect(lambda *_: do_topology())
    btn_show_map.clicked.connect(lambda: tabs.setCurrentWidget(map_tab))
    btn_row2.addWidget(btn_topo)
    btn_row2.addWidget(btn_show_map)
    btn_row2.addStretch(1)
    topo_lay.addLayout(btn_row2)
    topo_lay.addWidget(QLabel("Last topology result:"))
    topo_lay.addWidget(topo_panel, 1)

    # -- tie candidate review (گردش تأیید مهندسی کاندیدهای NO — نیاز ۱۲) ---
    tie_table = QTableWidget(0, 4)
    tie_table.setHorizontalHeaderLabels(
        ["Tie candidate", "Feeders", "Switch",
         "Review (proposed/confirmed/rejected)"])
    tie_table.horizontalHeader().setStretchLastSection(True)
    tie_table.verticalHeader().setVisible(False)
    tie_table.setMaximumHeight(200)
    from ..qt.widgets import enable_copy_paste as _ecp_tie
    _ecp_tie(tie_table, editable=True)   # Ctrl+C/Ctrl+V — درخواست کاربر
    topo_lay.addWidget(make_explain_label(
        "<b>بازبینی کاندیدهای NO (A-09)</b> — مهندس هر کاندید را تأیید یا "
        "رد می‌کند؛ تأییدها در پروژه ذخیره می‌شوند. ستون آخر قابل ویرایش "
        "است (proposed / confirmed / rejected)."))
    topo_lay.addWidget(tie_table)

    def visible_ties() -> list:
        topo = state.get("topo")
        if topo is None:
            return []
        ties = sorted(topo.ties, key=lambda t: t.id)
        if scope_is_restricted():
            allowed = set(study_feeder_keys())
            ties = [c for c in ties
                    if c.feeder_a in allowed or c.feeder_b in allowed]
        return ties[:50]

    def refresh_tie_table() -> None:
        topo = state.get("topo")
        state["_loading"] = True
        try:
            if topo is None:
                tie_table.setRowCount(0)
                return
            reviews = state.setdefault("tie_reviews", {})
            ties = visible_ties()
            tie_table.setRowCount(len(ties))
            for i, c in enumerate(ties):
                sw = c.switch_id or "(no switch in GIS)"
                it0 = QTableWidgetItem(c.id)
                it0.setFlags(it0.flags() & ~Qt.ItemFlag.ItemIsEditable)
                tie_table.setItem(i, 0, it0)
                it1 = QTableWidgetItem(f"{c.feeder_a} <-> {c.feeder_b} @ {c.node[:10]}")
                it1.setFlags(it1.flags() & ~Qt.ItemFlag.ItemIsEditable)
                tie_table.setItem(i, 1, it1)
                it2 = QTableWidgetItem(sw)
                it2.setFlags(it2.flags() & ~Qt.ItemFlag.ItemIsEditable)
                tie_table.setItem(i, 2, it2)
                it3 = QTableWidgetItem(reviews.get(c.id, {}).get("status",
                                                                 "proposed"))
                tie_table.setItem(i, 3, it3)
        finally:
            state["_loading"] = False

    def persist_tie_reviews() -> None:
        if state.get("_loading"):
            return
        topo = state.get("topo")
        if topo is None or not state.get("db"):
            return
        rows = []
        for i, c in enumerate(visible_ties()):
            it = tie_table.item(i, 3)
            status = (it.text().strip().lower() if it else "proposed")
            if status not in ("proposed", "confirmed", "rejected"):
                status = "proposed"
            rows.append({"tie_id": c.id, "node": c.node,
                         "feeder_a": c.feeder_a, "feeder_b": c.feeder_b,
                         "switch_id": c.switch_id, "status": status})
        merged_reviews = dict(state.setdefault("tie_reviews", {}))
        merged_reviews.update({r["tie_id"]: r for r in rows})
        state["tie_reviews"] = merged_reviews
        try:
            store = ProjectStore(str(state["db"]))
            store.save_tie_review(rows, user="ui-user")
            state["dirty"] = True
            store.close()
        except Exception as exc:                       # noqa: BLE001
            _write_log(_fmt_exc(exc))

    tie_table.itemChanged.connect(lambda _it: persist_tie_reviews())

    # ---------------- Placement tab — TWO COLUMNS + جایابی دستی ------------
    plac_tab = QWidget()
    plac_split = QSplitter()
    plac_lay = QHBoxLayout(plac_tab)
    plac_lay.setContentsMargins(0, 0, 0, 0)
    plac_lay.addWidget(plac_split)
    plac_left = QWidget()
    plac_lcol = QVBoxLayout(plac_left)
    plac_lcol.setContentsMargins(4, 4, 4, 4)
    plac_right = QWidget()
    plac_rcol = QVBoxLayout(plac_right)
    plac_rcol.setContentsMargins(4, 4, 4, 4)
    plac_scroll = QScrollArea()
    plac_scroll.setWidgetResizable(True)
    plac_scroll.setFrameShape(QFrame.Shape.NoFrame)
    plac_scroll.setWidget(plac_left)
    plac_split.addWidget(plac_scroll)
    plac_split.addWidget(plac_right)
    plac_split.setSizes([700, 560])
    plac_left.setMinimumWidth(560)
    plac_lcol.setSpacing(9)

    plac_lcol.addWidget(QLabel(
        "<b>Placement — n-1, feeder ranking, schemes, acceptance, CE/CN "
        "(Phase 4)</b>"))
    plac_help_row = QHBoxLayout()
    plac_help_row.addWidget(QLabel("<b>جایابی و ارزیابی طرح‌های کلیدگذاری</b>"))
    plac_help_btn = QPushButton("ⓘ راهنمای این بخش")
    plac_help_btn.setMaximumWidth(150)
    plac_help_btn.clicked.connect(lambda: QMessageBox.information(
        win, "راهنمای جایابی",
        "در این بخش جداول n-1، رتبه‌بندی فیدرها، طرح‌های جدول ۱۷، "
        "قاعده U×P و مقایسه اقتصادی جدول ۱۸ اجرا می‌شود. هر طرح باید "
        "معیارهای پذیرش و ظرفیت فیدر پشتیبان را پاس کند. ستاره‌های سبز "
        "روی نقشه محل کلیدهای پیشنهادی را نشان می‌دهند.\n\n"
        "جایابی دستی در پایین همین صفحه است. مختصات باید در CRS پروژه "
        "و روی مسیر فیدر باشند. نتیجه فقط زمانی معتبر است که بار و λ/r "
        "معتبر در ورودی‌ها موجود باشد؛ داده ناقص نباید با صفر جایگزین شود."))
    plac_help_row.addWidget(plac_help_btn)
    plac_help_row.addStretch(1)
    plac_lcol.addLayout(plac_help_row)

    plac_panel = QTextEdit()
    plac_panel.setReadOnly(True)
    plac_panel.setFont(mono)
    plac_panel.setPlainText(
        "Nothing placed yet.\n\n"
        "1. Import / open a project (Data Import tab).\n"
        "2. Press 'Run placement & ranking'.\n"
        "3. Feeders are ranked, schemes are evaluated against the five\n"
        "   acceptance criteria and per-feeder plans (or the explicit\n"
        "   «no justification») appear here and on the Map tab.")

    btn_show_plac_map = QPushButton(t("Show proposals on map"))
    btn_show_plac_map.setEnabled(False)
    btn_exports = QPushButton(t("Exports (choose formats)…"))
    btn_exports.setEnabled(False)
    btn_settings = QPushButton(t("Engineering settings…"))
    btn_approve = QPushButton(t("Approve selected plan"))

    def open_settings() -> None:
        """نیاز ۱۲ — تنظیمات مهندسی (مدل بار/ظرفیت/هزینه/معیار/پوشش).

        Bug fix (switchloc_run_log.txt): the dialog constructor must
        NEVER kill the whole app — any exception is logged and shown,
        the shell stays alive."""
        from ..qt.settings_dialog import make_settings_dialog
        try:
            active_keys = study_feeder_keys()
            if scope_is_restricted() and not active_keys:
                QMessageBox.warning(win, "Study scope",
                                    "برای تحلیل محدود، دست‌کم یک فیدر را انتخاب کنید.")
                return
            active_set = set(active_keys)
            load_model = dict(state.get("load_model") or {})
            if state.get("scope"):
                load_model["feeder_pq"] = {
                    k: v for k, v in (load_model.get("feeder_pq") or {}).items()
                    if k in active_set}
            dlg = make_settings_dialog(win, active_keys, {
                "load_model": load_model,
                "capacity_rows": [r for r in (state.get("capacity_rows") or [])
                                  if r.get("feeder_key") in active_set],
                "cost_model": state.get("cost_model") or {},
                "criteria": state.get("criteria") or {},
                "coverage": state.get("coverage") or {},
            }, feeder_s_rated={k: v for k, v in feeder_s_rated().items()
                               if k in active_set})
            if not dlg.exec():
                return
            applied = dlg.apply()
        except Exception as exc:                   # noqa: BLE001
            _write_log(_fmt_exc(exc))
            QMessageBox.critical(
                win, "Engineering settings",
                f"{exc}\n\nDetails were saved to {log_path_text()}.")
            return
        if state.get("scope"):
            old_lm = dict(state.get("load_model") or {})
            new_lm = dict(applied["load_model"])
            old_pq = dict(old_lm.get("feeder_pq") or {})
            new_pq = dict(new_lm.get("feeder_pq") or {})
            old_pq.update(new_pq)
            new_lm["feeder_pq"] = old_pq
            state["load_model"] = new_lm
        else:
            state["load_model"] = applied["load_model"]
        state["criteria"] = applied["criteria"]
        state["coverage"] = applied["coverage"]
        state["cost_model"] = applied["cost_model"]
        if scope_is_restricted():
            keep = [r for r in (state.get("capacity_rows") or [])
                    if r.get("feeder_key") not in active_set]
            state["capacity_rows"] = keep + applied["capacity_rows"]
        else:
            state["capacity_rows"] = applied["capacity_rows"]
        # capacities persist INTO the project (نیاز ۹)
        if state.get("db") and applied["capacity_rows"]:
            try:
                store = ProjectStore(str(state["db"]))
                store.save_feeder_capacity(applied["capacity_rows"],
                                           user="ui-user")
                store.close()
            except Exception as exc:                   # noqa: BLE001
                _write_log(_fmt_exc(exc))
        QMessageBox.information(
            win, "Engineering settings",
            "Settings applied — they take effect on the NEXT placement run.")

    btn_settings.clicked.connect(open_settings)

    # -- جایابی دستی کلید (روش جدا — درخواست کاربر) -------------------------
    # کاربر مختصات UTM را تایپ می‌کند یا روی نقشه کلیک می‌کند؛ نرم‌افزار
    # شاخص‌های روش سطح اول را قبل/بعد از نصب کلید(ها) مقایسه می‌کند.
    manual_group = QGroupBox("جایابی دستی و اتصال بین‌فیدری")
    manual_lay = QVBoxLayout(manual_group)
    manual_lay.setContentsMargins(10, 12, 10, 10)
    manual_lay.setSpacing(8)
    manual_lay.addWidget(make_explain_label(
        "<b>جایابی دستی کلید (ارزیابی محل پیشنهادی)</b> — فیدر و مختصات "
        "مختصات را با UTM زون ۳۸/۳۹ وارد کنید یا ردیف را انتخاب و «انتخاب "
        "روی نقشه» را بزنید تا با کلیک روی نقشه پر شود. دکمه ارزیابی، "
        "شاخص‌های روش سطح اول (ENS، EP، TL و جدول ۱۸) را قبل و بعد از "
        "نصب کلید یا کلیدها مقایسه می‌کند — بهبود یا بدترشدن صریح اعلام "
        "می‌شود. برای چند کلید، ردیف‌های هم‌فیدر با هم ارزیابی می‌شوند."))
    manual_table = QTableWidget(0, 5)
    manual_table.setHorizontalHeaderLabels(
        ["Feeder*", "X project CRS (m)*", "Y project CRS (m)*", "Snap node", "Dist (m)"])
    manual_table.setToolTip(
        "ستون‌های X/Y مختصات تبدیل‌شده در CRS پروژه هستند. برای ورود UTM "
        "از دکمه Enter UTM coordinates استفاده کنید؛ نقطه دقیق روی نقشه "
        "نشان داده می‌شود و Snap node نزدیک‌ترین گره شبکه است.")
    manual_table.horizontalHeader().setStretchLastSection(True)
    manual_table.verticalHeader().setVisible(False)
    manual_table.setMinimumHeight(245)
    manual_table.setSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Expanding)
    manual_table.verticalHeader().setDefaultSectionSize(34)
    manual_table.setAlternatingRowColors(True)
    manual_table.setToolTip(
        "برای اتصال بین‌فیدری دقیقاً دو ردیف با دو فیدر متفاوت تکمیل کنید. "
        "هر ردیف یک سر مستقل اتصال است؛ نقطه را روی نقشه انتخاب کنید یا UTM بدهید.")
    from ..qt.widgets import enable_copy_paste as _ecp
    _ecp(manual_table, editable=True)
    manual_lay.addWidget(manual_table, 2)

    def _manual_feeder_combo(row: int) -> None:
        keys = study_feeder_keys() or [""]
        combo = QComboBox()
        combo.addItem("— select feeder —")
        for k in keys:
            combo.addItem(k)
        manual_table.setCellWidget(row, 0, combo)

    def manual_add_row() -> None:
        r = manual_table.rowCount()
        manual_table.insertRow(r)
        _manual_feeder_combo(r)
        for j in (1, 2):
            manual_table.setItem(r, j, QTableWidgetItem(""))
        for j in (3, 4):
            it = QTableWidgetItem("—")
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            manual_table.setItem(r, j, it)

    def _sync_manual_highlight() -> None:
        # The map marker is a view of the currently entered coordinate rows,
        # never a sticky independent state. Removing the last coordinate clears it.
        point = None
        for rr in range(manual_table.rowCount()):
            try:
                xx = float(manual_table.item(rr, 1).text().replace(",", ""))
                yy = float(manual_table.item(rr, 2).text().replace(",", ""))
                point = (xx, yy)
            except (ValueError, AttributeError):
                continue
        state["manual_highlight_point"] = point
        refresh_map()

    def manual_remove_row() -> None:
        r = manual_table.currentRow()
        if r >= 0:
            manual_table.removeRow(r)
            map_tab.canvas.set_pick_mode(False)
            _pick_row["row"] = -1
            _sync_manual_highlight()

    def manual_clear_marker() -> None:
        state["manual_highlight_point"] = None
        state["manual_zone_result"] = None
        state["manual_tie_pairs"] = []
        map_tab.canvas.set_pick_mode(False)
        _pick_row["row"] = -1
        refresh_map()

    _pick_row = {"row": -1}

    def manual_enter_utm() -> None:
        r = manual_table.currentRow()
        if r < 0:
            QMessageBox.information(win, "Manual placement",
                                    "ابتدا ردیف محل نصب را انتخاب کنید.")
            return
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QComboBox, QLineEdit, QFormLayout
        from pyproj import CRS
        from ...gis.crs import transform_utm_to_project
        dlg = QDialog(win)
        dlg.setWindowTitle("ورود مختصات UTM — زون ۳۸ یا ۳۹")
        form = QFormLayout(dlg)
        zone = QComboBox(); zone.addItem("38N", 38); zone.addItem("39N", 39)
        easting = QLineEdit(); easting.setPlaceholderText("مثلاً 500000")
        northing = QLineEdit(); northing.setPlaceholderText("مثلاً 3950000")
        form.addRow("UTM Zone:", zone)
        form.addRow("Easting (m):", easting)
        form.addRow("Northing (m):", northing)
        form.addRow(make_explain_label(
            "مختصات ورودی برحسب متر و در نیم‌کره شمالی است. پس از تأیید، "
            "به CRS پروژه تبدیل و نقطه دقیق روی نقشه علامت‌گذاری می‌شود."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept); buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        if not dlg.exec():
            return
        try:
            from ..inputs_model import parse_number
            xx = parse_number(easting.text())
            yy = parse_number(northing.text())
            if xx is None or yy is None:
                raise ValueError("Easting و Northing باید عدد معتبر باشند.")
            if not (100000 <= xx <= 900000 and 0 <= yy <= 10000000):
                raise ValueError("Easting/Northing خارج از محدوده معتبر UTM است.")
            target_text = project_crs()
            if not target_text:
                raise ValueError("CRS پروژه مشخص نیست؛ ابتدا CRS لایه‌های GIS را تعیین کنید.")
            target_crs = CRS.from_user_input(target_text)
            x, y = transform_utm_to_project(
                xx, yy, int(zone.currentData()), target_crs)
        except Exception as exc:
            QMessageBox.warning(win, "UTM coordinates", str(exc))
            return
        manual_table.item(r, 1).setText(f"{x:.3f}")
        manual_table.item(r, 2).setText(f"{y:.3f}")
        state["manual_highlight_point"] = (x, y)
        _manual_snap_row(r)
        refresh_map()
        tabs.setCurrentWidget(map_tab)
        QMessageBox.information(win, "UTM coordinates",
                                f"نقطه تبدیل و روی نقشه نمایش داده شد.\n"
                                f"CRS پروژه: {target_crs.to_string()}\n"
                                f"X={x:.3f} m, Y={y:.3f} m")

    def manual_pick_on_map() -> None:
        r = manual_table.currentRow()
        if r < 0:
            QMessageBox.information(
                win, "Manual placement",
                "Select the row to fill first, then click on the map.")
            return
        _pick_row["row"] = r
        map_tab.canvas.set_pick_mode(True)
        map_tab.canvas.on_pick = _on_map_pick
        tabs.setCurrentWidget(map_tab)
        QMessageBox.information(
            win, "Manual placement",
            "روی نقشه کلیک کنید — مختصات در CRS پروژه، در ردیف انتخاب‌شده "
            "درج و به نزدیک‌ترین گره شبکه می‌چسبد.")

    def _on_map_pick(x: float, y: float) -> None:
        r = _pick_row["row"]
        if r < 0 or r >= manual_table.rowCount():
            return
        manual_table.item(r, 1).setText(f"{x:.2f}")
        manual_table.item(r, 2).setText(f"{y:.2f}")
        state["manual_highlight_point"] = (x, y)
        _manual_snap_row(r)
        refresh_map()
        tabs.setCurrentWidget(plac_tab)

    def _manual_snap_row(r: int) -> None:
        topo = state.get("topo")
        try:
            x = float(manual_table.item(r, 1).text().replace(",", ""))
            y = float(manual_table.item(r, 2).text().replace(",", ""))
        except (ValueError, AttributeError):
            return
        if topo is None:
            return
        from ...manual_placement import nearest_node
        combo = manual_table.cellWidget(r, 0)
        fk = combo.currentText() if combo else ""
        restrict = None
        tr = next((t for t in topo.traces if t.feeder_key == fk), None)
        if tr is not None:
            restrict = set(tr.nodes)
        nid, d = nearest_node(topo.graph, x, y, restrict_to=restrict,
                               max_dist_m=50.0)
        manual_table.item(r, 3).setText(nid or "—")
        manual_table.item(r, 4).setText(f"{d:.1f}" if nid else "—")

    def manual_rows_by_feeder() -> dict:
        """ردیف‌های کامل جدول دستی بر حسب فیدر.

        اگر فیدرِ ردیف انتخاب نشده باشد (باگ «ردیف کامل وجود ندارد» —
        بازخورد کاربر)، فیدر از نزدیک‌ترین گره شبکه استنتاج و در کمبو
        ردیف ثبت می‌شود؛ بنابراین «انتخاب روی نقشه + ارزیابی» حتی بدون
        انتخاب فیدر کار می‌کند."""
        topo = state.get("topo")
        out: dict[str, list] = {}
        for r in range(manual_table.rowCount()):
            combo = manual_table.cellWidget(r, 0)
            fk = (combo.currentText() if combo else "").strip()
            try:
                x = float(manual_table.item(r, 1).text().replace(",", ""))
                y = float(manual_table.item(r, 2).text().replace(",", ""))
            except (ValueError, AttributeError):
                continue
            if not fk or fk.startswith("—"):
                if topo is None:
                    continue
                from ...manual_placement import nearest_node
                allowed = set(study_feeder_keys())
                candidates = [t for t in topo.traces
                              if not allowed or t.feeder_key in allowed]
                best = None
                for candidate in candidates:
                    nid0, d0 = nearest_node(topo.graph, x, y,
                                            restrict_to=set(candidate.nodes))
                    if nid0 is not None and (best is None or d0 < best[0]):
                        best = (d0, nid0, candidate)
                nid = best[1] if best else None
                tr = best[2] if best else None
                if tr is None:
                    continue
                fk = tr.feeder_key
                if combo is not None and combo.findText(fk) > 0:
                    combo.setCurrentText(fk)
            out.setdefault(fk, []).append((x, y))
        return out

    def _lam_rows_of(src) -> list:
        """λ/r از OutageResult (اتریبوت) یا دیکشنری store.load_outages() —
        رفع باگ: getattr روی دیکشنری همیشه [] می‌داد و ارزیابی دستیِ
        پروژهٔ بازشده λ=۰ می‌گرفت."""
        if src is None:
            return []
        rows = getattr(src, "lambda_r", None)
        if rows is None and isinstance(src, dict):
            rows = src.get("lambda_r") or []
        return list(rows or [])

    def _manual_engine_inputs():
        """Use the active study's load/cost/capacity inputs, never defaults silently."""
        from ...placement.service import EngineSettings
        from ...placement.capacity import FeederCapacity
        from ...reliability.load_model import LoadModelSettings
        from ...placement.economics import CostModel
        eng = EngineSettings()
        if state.get("load_model"):
            eng.load_model = LoadModelSettings.from_dict(state["load_model"])
        if state.get("cost_model"):
            eng.cost = CostModel(**{k: v for k, v in state["cost_model"].items()
                                    if k in CostModel.__dataclass_fields__})
        cap_map = {c.feeder_key: c for c in
                   (FeederCapacity.from_row(r) for r in (state.get("capacity_rows") or []))}
        return eng, cap_map

    def manual_start_interfeeder_tie() -> None:
        """Create a clear two-endpoint workflow for an inter-feeder tie."""
        filled = []
        for rr in range(manual_table.rowCount()):
            try:
                x_txt = manual_table.item(rr, 1).text().strip()
                y_txt = manual_table.item(rr, 2).text().strip()
                if x_txt and y_txt:
                    filled.append(rr)
            except AttributeError:
                pass
        if len(filled) > 2:
            QMessageBox.warning(
                win, "اتصال بین‌فیدری",
                "برای یک اتصال فقط دو نقطه لازم است. بیش از دو ردیف دارای مختصات است؛ "
                "دو ردیف موردنظر را نگه دارید و سایر ردیف‌ها را موقتاً خالی کنید.")
            return
        target = list(filled)
        for rr in range(manual_table.rowCount()):
            if len(target) == 2:
                break
            try:
                x_txt = manual_table.item(rr, 1).text().strip()
                y_txt = manual_table.item(rr, 2).text().strip()
            except AttributeError:
                x_txt = y_txt = ""
            if not x_txt and not y_txt and rr not in target:
                target.append(rr)
        while len(target) < 2:
            manual_add_row()
            target.append(manual_table.rowCount() - 1)
        target = target[:2]
        keys = study_feeder_keys()
        if not keys or len(keys) < 2:
            QMessageBox.warning(win, "اتصال بین‌فیدری",
                                "برای تعریف اتصال، ابتدا توپولوژی را اجرا کنید و دست‌کم دو فیدر داشته باشید.")
            return
        for pos, rr in enumerate(target):
            combo = manual_table.cellWidget(rr, 0)
            if combo is not None and combo.count() > 1 and combo.currentIndex() == 0:
                preferred = keys[pos] if pos < len(keys) else keys[0]
                ix = combo.findText(preferred)
                combo.setCurrentIndex(ix if ix > 0 else 1)
        manual_table.selectRow(target[0])
        QMessageBox.information(
            win, "اتصال بین‌فیدری — گردش‌کار دو نقطه‌ای",
            "ردیف اول و دوم به‌ترتیب سر اول و سر دوم اتصال هستند.\n\n"
            "۱) در هر ردیف یک فیدر متفاوت انتخاب کنید.\n"
            "۲) ردیف اول را انتخاب و «انتخاب روی نقشه» را بزنید؛ روی فیدر اول کلیک کنید.\n"
            "۳) همین کار را برای ردیف دوم و فیدر دوم انجام دهید.\n"
            "۴) دکمه «ارزیابی اتصال بین‌فیدری» را اجرا کنید.\n\n"
            "هر دو نقطه باید به گره همان فیدر نزدیک باشند. این ارزیابی سطح اول است؛ "
            "جایگزین پخش بار، کنترل اتصال کوتاه یا هماهنگی حفاظتی نیست.")

    def manual_evaluate_interfeeder_tie() -> None:
        """Dedicated entry point; validate two distinct feeders before scoring."""
        valid = []
        for rr in range(manual_table.rowCount()):
            try:
                x = manual_table.item(rr, 1).text().strip()
                y = manual_table.item(rr, 2).text().strip()
            except AttributeError:
                continue
            if x and y:
                combo = manual_table.cellWidget(rr, 0)
                fk = combo.currentText().strip() if combo else ""
                valid.append((rr, fk))
        if len(valid) != 2 or not all(fk and not fk.startswith("—") for _, fk in valid):
            QMessageBox.warning(win, "اتصال بین‌فیدری",
                                "دقیقاً دو ردیف کامل با فیدر انتخاب‌شده لازم است.")
            return
        if valid[0][1] == valid[1][1]:
            QMessageBox.warning(win, "اتصال بین‌فیدری",
                                "دو نقطه باید متعلق به دو فیدر متفاوت باشند.")
            return
        manual_evaluate()

    def manual_evaluate() -> None:
        """ارزیابی قبل/بعد شاخص‌های روش سطح اول برای کلیدهای دستی."""
        state["manual_zone_result"] = None
        state["manual_tie_pairs"] = []
        if state.get("topo") is not None:
            refresh_map()
        if not scope_is_valid():
            QMessageBox.warning(win, "Study scope",
                                "برای تحلیل محدود، دست‌کم یک فیدر را انتخاب کنید.")
            return
        topo = state.get("topo")
        if topo is None:
            QMessageBox.warning(win, "Manual placement",
                                "Run topology first — the evaluation needs "
                                "the traced network.")
            return
        if not confirm_inputs("تأیید ورودی‌های ارزیابی جایابی دستی"):
            return
        by_feeder = manual_rows_by_feeder()
        if not by_feeder:
            QMessageBox.information(
                win, "Manual placement",
                "ردیف کاملی وجود ندارد — فیدر و مختصات X/Y را وارد کنید "
                "(یا از نقشه انتخاب کنید).")
            return
        manual_settings, manual_cap_map = _manual_engine_inputs()
        from ...topology.zones import ZonePolicy
        manual_zone_policy = ZonePolicy(include_fuse_cutout=bool(
            (getattr(topo, "settings", {}) or {}).get("include_fuse_cutout_as_boundary", False)))
        from ...manual_placement import evaluate_manual_placement, nearest_node
        from ...ui.inputs_model import apply_lambda_overrides
        for r in range(manual_table.rowCount()):
            _manual_snap_row(r)
        # Two selected locations on different feeders describe a proposed
        # inter-feeder tie, not two independent sectionalizers. Do not silently
        # score them as unrelated single-feeder switches.
        selected_rows = sorted({r for r in range(manual_table.rowCount())
                                if manual_table.item(r, 1) is not None and
                                manual_table.item(r, 1).text().strip() and
                                manual_table.item(r, 2) is not None and
                                manual_table.item(r, 2).text().strip()})
        selected_feeders = []
        for rr in selected_rows:
            cb = manual_table.cellWidget(rr, 0)
            selected_feeders.append(cb.currentText() if cb else "")
        distinct = {x for x in selected_feeders if x and x != "— select feeder —"}
        if len(selected_rows) == 2 and len(distinct) == 2:
            from ...manual_placement import (nearest_node,
                                             evaluate_manual_interfeeder_tie)
            from ...ui.inputs_model import apply_lambda_overrides
            endpoints = []
            for rr in selected_rows:
                _manual_snap_row(rr)
                cb = manual_table.cellWidget(rr, 0)
                fk = cb.currentText().strip() if cb else ""
                try:
                    xx = float(manual_table.item(rr, 1).text().replace(",", ""))
                    yy = float(manual_table.item(rr, 2).text().replace(",", ""))
                except (ValueError, AttributeError):
                    QMessageBox.warning(win, "Inter-feeder tie", "مختصات هر دو سر اتصال باید معتبر باشد.")
                    return
                tr = next((t for t in topo.traces if t.feeder_key == fk), None)
                nid, dist = nearest_node(topo.graph, xx, yy,
                                         restrict_to=set(tr.nodes) if tr else None)
                if not nid or dist > 100.0:
                    QMessageBox.warning(win, "Inter-feeder tie",
                                        f"نقطه انتخابی برای فیدر {fk} به گره معتبر نزدیک نیست (فاصله {dist:.1f} متر).")
                    return
                endpoints.append((fk, nid))
            lam_rows = apply_lambda_overrides(
                _lam_rows_of(state.get("outage")) or _lam_rows_of(state.get("outage_store")),
                state.get("lambda_overrides") or {})
            tie_results, tie_issues = evaluate_manual_interfeeder_tie(
                topo.graph, state["net"], topo.traces, topo.zones, topo.ties,
                endpoints[0][0], endpoints[0][1], endpoints[1][0], endpoints[1][1],
                lam_matrix=lam_rows, settings=manual_settings,
                cap_map=manual_cap_map,
                automation_capable=chk_manual_tie_auto.isChecked(),
                zone_policy=manual_zone_policy)
            if not tie_results:
                QMessageBox.warning(win, "Inter-feeder tie — calculation blocked",
                                    "اتصال محاسبه نشد؛ ورودی‌های لازم ناقص است:\n" +
                                    "\n".join(f"{x[0]}: {x[2]}" for x in tie_issues))
                return
            results = list(tie_results.values())
            lines = ["Manual inter-feeder tie — two independent endpoints:",
                     f"{endpoints[0][0]}@{endpoints[0][1]}  <->  {endpoints[1][0]}@{endpoints[1][1]}", ""]
            for ev in results:
                lines.append(f"{ev.feeder_key}: ENS {ev.before['ens_kwh']:,.1f} → {ev.after['ens_kwh']:,.1f} kWh/yr; "
                             f"ΔENS={ev.delta['ens_kwh']:+,.1f}; {ev.verdict_fa}")
            lines.extend(["", "ملاحظات مدل:"] + [f"- {x[2]}" for x in tie_issues])
            state["manual_evals"] = [ev.as_dict() for ev in results]
            state["manual_tie_pairs"] = [(endpoints[0][1], endpoints[1][1])]
            from ...topology.zones import ZoneResult
            base = topo.zones
            replaced = {ev.feeder_key for ev in results if ev.after_zones is not None}
            kept = [z for z in base.zones if z.feeder not in replaced]
            added = [z for ev in results if ev.after_zones is not None
                     for z in ev.after_zones.zones]
            merged = ZoneResult(zones=kept + added)
            for zr in [base] + [ev.after_zones for ev in results if ev.after_zones is not None]:
                merged.zone_of_edge.update(zr.zone_of_edge); merged.zone_of_node.update(zr.zone_of_node)
                merged.boundaries.extend(zr.boundaries)
            merged.boundary_of_switch.update(base.boundary_of_switch)
            valid_ids = {z.id for z in merged.zones}
            merged.zone_of_edge = {e: zid for e, zid in merged.zone_of_edge.items()
                                   if zid in valid_ids}
            merged.zone_of_node = {n: zid for n, zid in merged.zone_of_node.items()
                                   if zid in valid_ids}
            merged.boundaries = [b for b in merged.boundaries
                                 if set(b.zones).intersection(valid_ids)]
            valid_switches = {b.switch_id for b in merged.boundaries}
            merged.boundary_of_switch = {k: v for k, v in merged.boundary_of_switch.items()
                                         if k in valid_switches}
            state["manual_zone_result"] = merged
            manual_panel.setPlainText("\n".join(lines))
            refresh_manual_results(results)
            refresh_map()
            QMessageBox.information(win, "Inter-feeder tie evaluation",
                                    "دو سر اتصال به‌صورت مستقل ارزیابی و زون‌بندی هر دو فیدر بازسازی شد. "
                                    "نتایج و محدودیت‌ها در جدول و متن خروجی نمایش داده شده‌اند.")
            return
        results = []
        lines = ["Manual placement evaluation — level-1 indicators "
                 "BEFORE/AFTER:", ""]
        for fk, pts in sorted(by_feeder.items()):
            graph = topo.graph
            nodes = []
            for x, y in pts:
                tr = next((t for t in topo.traces
                           if t.feeder_key == fk), None)
                restrict = set(tr.nodes) if tr is not None else None
                nid, d = nearest_node(graph, x, y, restrict_to=restrict,
                                      max_dist_m=50.0)
                if nid is None:
                    QMessageBox.warning(
                        win, "Manual placement",
                        f"({x:.0f}, {y:.0f}) نزدیک هیچ گره‌ای از فیدر "
                        f"{fk} نیست.")
                    return
                nodes.append(nid)
            lam_matrix = _lam_rows_of(state.get("outage")) or \
                _lam_rows_of(state.get("outage_store"))
            # مقادیر تأییدشدهٔ جدول ورودی‌ها بر ماتریس λ/r اعمال می‌شود
            lam_matrix = apply_lambda_overrides(
                lam_matrix, state.get("lambda_overrides") or {})
            ev = evaluate_manual_placement(
                graph, state["net"], topo.traces, topo.zones, topo.ties,
                feeder_key=fk, switch_nodes=nodes,
                lam_matrix=lam_matrix, settings=manual_settings,
                cap_map=manual_cap_map, zone_policy=manual_zone_policy)
            results.append(ev)
            lines.append(f"Feeder {fk} — switch(es) at {', '.join(nodes)}:")
            if not ev.before or not ev.after:
                lines.append("  محاسبه انجام نشد؛ ورودی لازم موجود نیست:")
                lines.extend(f"  - {issue[0]}: {issue[2]}" for issue in ev.issues
                             if issue[1] == "Error")
                lines.append(f"  حکم: {ev.verdict_fa}")
                lines.append("")
                continue
            lines.append(f"  ENS  before/after : "
                         f"{ev.before['ens_kwh']:,.1f} → "
                         f"{ev.after['ens_kwh']:,.1f} kWh/yr "
                         f"(Δ = {ev.delta['ens_kwh']:+,.1f}, "
                         f"{ev.delta['ens_percent']:+.1f}%)")
            lines.append(f"  EP%  before/after : "
                         f"{ev.before.get('ep_percent', 0):.1f} → "
                         f"{ev.after.get('ep_percent', 0):.1f}")
            lines.append(f"  TL%  before/after : "
                         f"{ev.before.get('tl_percent', 0):.1f} → "
                         f"{ev.after.get('tl_percent', 0):.1f}")
            lines.append(f"  CE/CN (جدول ۱۸)  : "
                         f"{ev.ce_cn.get('ce_over_cn', float('-inf')):.4g}"
                         if ev.ce_cn.get("ce_over_cn") not in
                         (None, float("-inf")) else
                         f"  CE/CN (جدول ۱۸)  : —")
            lines.append(f"  حکم: {ev.verdict_fa}")
            lines.append("")
        state["manual_evals"] = [ev.as_dict() for ev in results]
        valid_zone_results = [ev.after_zones for ev in results
                              if ev.after_zones is not None]
        if valid_zone_results:
            # Current manual-placement workflow evaluates per feeder. Merge
            # those feeder-specific after-state zone objects without mutating
            # the project's canonical topology snapshot.
            from ...topology.zones import ZoneResult
            base = topo.zones
            replaced = {ev.feeder_key for ev in results if ev.after_zones is not None}
            kept = [z for z in base.zones if z.feeder not in replaced]
            added = [z for zr in valid_zone_results for z in zr.zones]
            merged = ZoneResult(zones=kept + added)
            for zr in [base] + valid_zone_results:
                merged.zone_of_edge.update(zr.zone_of_edge)
                merged.zone_of_node.update(zr.zone_of_node)
                merged.boundaries.extend(zr.boundaries)
            merged.boundary_of_switch.update(base.boundary_of_switch)
            valid_ids = {z.id for z in merged.zones}
            merged.zone_of_edge = {e: zid for e, zid in merged.zone_of_edge.items()
                                   if zid in valid_ids}
            merged.zone_of_node = {n: zid for n, zid in merged.zone_of_node.items()
                                   if zid in valid_ids}
            merged.boundaries = [b for b in merged.boundaries
                                 if set(b.zones).intersection(valid_ids)]
            valid_switches = {b.switch_id for b in merged.boundaries}
            merged.boundary_of_switch = {k: v for k, v in merged.boundary_of_switch.items()
                                         if k in valid_switches}
            state["manual_zone_result"] = merged
        manual_panel.setPlainText("\n".join(lines))
        refresh_manual_results(results)
        # نقاط ارزیابی‌شده روی نقشه (درخواست کاربر، مورد ۶)
        refresh_map()
        QMessageBox.information(
            win, "Manual placement result",
            "ارزیابی انجام شد — جدول قبل/بعد و حکم هر فیدر در پایین "
            "همین ستون نمایش داده شده است؛ مکان کلیدهای دستی با علامت "
            "آبی روی تب Map مشخص شد و نتایج در گزارش نهایی (بخش ۱۰) "
            "می‌آید.")

    def refresh_manual_feeders() -> None:
        """کمبو فیدر ردیف‌های موجود، با فیدرهای پروژه پُر شود —
        رفع باگ «هیچ فیدری برای انتخاب نمایش داده نمی‌شود» (وقتی ردیف
        قبل از اجرای توپولوژی اضافه شده باشد)."""
        keys = study_feeder_keys()
        for r in range(manual_table.rowCount()):
            combo = manual_table.cellWidget(r, 0)
            if combo is None:
                _manual_feeder_combo(r)
                continue
            cur = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("— select feeder —")
            for k in keys:
                combo.addItem(k)
            if cur in keys:
                combo.setCurrentText(cur)
            combo.blockSignals(False)

    def refresh_manual_results(results) -> None:
        from ..qt.widgets import fill_table
        headers = ["Feeder", "Switch node(s)", "ENS before", "ENS after",
                   "ΔENS kWh/yr", "Δ%", "EP→", "TL→", "CE/CN",
                   "Verdict"]
        data = []
        for ev in results:
            ratio = ev.ce_cn.get("ce_over_cn")
            data.append([
                ev.feeder_key, ", ".join(ev.switch_nodes),
                f"{ev.before['ens_kwh']:,.1f}" if ev.before else "—",
                f"{ev.after['ens_kwh']:,.1f}" if ev.after else "—",
                f"{ev.delta['ens_kwh']:+,.1f}" if ev.delta else "—",
                f"{ev.delta['ens_percent']:+.2f}%" if ev.delta else "—",
                (f"{ev.before['ep_percent']:.1f} → {ev.after['ep_percent']:.1f}"
                 if ev.before and ev.after else "—"),
                (f"{ev.before['tl_percent']:.1f} → {ev.after['tl_percent']:.1f}"
                 if ev.before and ev.after else "—"),
                f"{ratio:.4g}" if ratio not in (None, float("-inf"))
                else "—",
                ("✔ " + ev.verdict_fa) if ev.better and ev.before
                else ("✘ " + ev.verdict_fa if ev.before and ev.delta.get("ens_kwh", 0) < 0
                      else ev.verdict_fa)])
        fill_table(manual_result_table, headers, data)
        manual_result_table.resizeColumnsToContents()

    manual_btns = QHBoxLayout()
    btn_m_add = QPushButton("Add row")
    btn_m_del = QPushButton("Remove row")
    btn_m_clear = QPushButton("Clear map marker")
    btn_m_pick = QPushButton("Pick on map…")
    btn_m_utm = QPushButton("Enter UTM coordinates…")
    btn_m_eval = QPushButton("Evaluate before/after")
    btn_m_tie = QPushButton("۱) تعریف اتصال بین‌فیدری")
    btn_m_tie.setToolTip("شروع گردش‌کار دو نقطه‌ای؛ هر نقطه روی یک فیدر متفاوت")
    btn_m_tie.clicked.connect(manual_start_interfeeder_tie)
    btn_m_tie_eval = QPushButton("۲) ارزیابی اتصال بین‌فیدری")
    btn_m_tie_eval.clicked.connect(manual_evaluate_interfeeder_tie)
    chk_manual_tie_auto = QCheckBox("اتصال بین‌فیدری اتوماسیون‌پذیر است")
    chk_manual_tie_auto.setToolTip("فقط در صورت وجود کلید رابط دارای کنترل از راه دور فعال کنید؛ برای محاسبه انتقال، ظرفیت نامی و پیک هر دو فیدر لازم است.")
    btn_m_add.clicked.connect(manual_add_row)
    btn_m_del.clicked.connect(manual_remove_row)
    btn_m_clear.clicked.connect(manual_clear_marker)
    btn_m_pick.clicked.connect(manual_pick_on_map)
    btn_m_utm.clicked.connect(manual_enter_utm)
    btn_m_eval.clicked.connect(manual_evaluate)
    for b in (btn_m_add, btn_m_del, btn_m_clear, btn_m_pick, btn_m_utm, btn_m_tie, btn_m_tie_eval, btn_m_eval):
        manual_btns.addWidget(b)
    manual_btns.addWidget(chk_manual_tie_auto)
    manual_btns.addStretch(1)
    manual_lay.addLayout(manual_btns)
    manual_lay.addWidget(QLabel("Manual placement result (before/after — "
                               "روش سطح اول):"))
    manual_result_table = QTableWidget(0, 10)
    manual_result_table.setMaximumHeight(180)
    manual_result_table.verticalHeader().setVisible(False)
    manual_lay.addWidget(manual_result_table)
    manual_panel = QTextEdit()
    manual_panel.setReadOnly(True)
    manual_panel.setFont(mono)
    manual_panel.setMinimumHeight(130)
    manual_panel.setMaximumHeight(230)
    manual_lay.addWidget(manual_panel)
    plac_lcol.addWidget(manual_group)
    manual_add_row()

    def do_approve() -> None:
        """گردش تأیید نهایی مهندسی — دروازه سخت نیاز ۹/۱۰."""
        from ...placement.acceptance import PlanApprovalError, approve_plan
        from ...placement.capacity import FeederCapacity
        plc = state.get("plc")
        if plc is None:
            QMessageBox.information(win, "Approve plan",
                                    "Run placement first.")
            return
        idx = plan_table.currentRow()
        it = plan_table.item(idx, 0) if idx >= 0 else None
        fk = it.data(Qt.ItemDataRole.UserRole) if it is not None else None
        row = next((r for r in plc.result.recommendation
                    if r["feeder_key"] == fk), None) if fk else None
        if row is None:
            QMessageBox.information(win, "Approve plan",
                                    "Select a feeder row in the plan table.")
            return
        cap_map = {r["feeder_key"]: FeederCapacity.from_row(r)
                   for r in state.get("capacity_rows") or []}
        try:
            approved = approve_plan(row, cap_map)
        except PlanApprovalError as exc:
            QMessageBox.warning(
                win, "Approval refused",
                f"{exc}\n\n plans without a completed capacity check can "
                "never receive final engineering approval (نیاز ۹).")
            return
        state.setdefault("plan_reviews", {})[approved["feeder_key"]] = {
            "feeder_key": approved["feeder_key"],
            "placement_run_id": getattr(plc, "run_id", None),
            "scheme_id": approved.get("scheme_id"),
            "status": "approved",
            "reasons": approved.get("decision_reasons", []),
        }
        if state.get("db"):
            try:
                store = ProjectStore(str(state["db"]))
                store.save_plan_review(
                    [state["plan_reviews"][approved["feeder_key"]]],
                    user="ui-user")
                store.close()
            except Exception as exc:                   # noqa: BLE001
                _write_log(_fmt_exc(exc))
        refresh_plan_table()
        QMessageBox.information(
            win, "Plan approved",
            f"Plan of {approved['feeder_key']} received final engineering "
            "approval and was saved into the project.")

    btn_approve.clicked.connect(do_approve)

    # ---------------- تأیید نهایی ورودی‌ها (درخواست کاربر، مورد ۵) --------
    def _apply_input_edits(edits: dict) -> None:
        """مقادیر تأییدشدهٔ جدول ورودی‌ها → state (+ ذخیره ظرفیت‌ها)."""
        if edits.get("lambda_overrides"):
            ov = state.setdefault("lambda_overrides", {})
            for fk, vals in edits["lambda_overrides"].items():
                ov.setdefault(fk, {}).update(vals)
        lm = state.setdefault("load_model", {})
        lm.update(edits.get("load_model") or {})
        pq = edits.get("feeder_pq") or {}
        if pq:
            cur = lm.setdefault("feeder_pq", {})
            for fk, vals in pq.items():
                cur.setdefault(fk, {}).update(vals)
        state.setdefault("cost_model", {}).update(
            edits.get("cost_model") or {})
        crit = dict(edits.get("criteria") or {})
        # 0 = بدون سقف (همان قرارداد تنظیمات مهندسی)
        if crit.get("max_switches_per_scheme") == 0:
            crit["max_switches_per_scheme"] = None
        if crit.get("max_budget_rials") == 0:
            crit["max_budget_rials"] = None
        state.setdefault("criteria", {}).update(crit)
        state.setdefault("coverage", {}).update(edits.get("coverage") or {})
        if edits.get("weights"):
            state["weights"] = list(edits["weights"])
        cap_upd = edits.get("capacity_updates") or {}
        if cap_upd:
            rows = {r.get("feeder_key"): dict(r) for r in
                    state.get("capacity_rows") or []}
            for fk, vals in cap_upd.items():
                rows.setdefault(fk, {"feeder_key": fk})
                rows[fk].update(vals)
            state["capacity_rows"] = list(rows.values())
            if state.get("db"):
                try:
                    store = ProjectStore(str(state["db"]))
                    store.save_feeder_capacity(state["capacity_rows"],
                                               user="ui-user")
                    store.close()
                except Exception as exc:               # noqa: BLE001
                    _write_log(_fmt_exc(exc))

    def confirm_inputs(title: str =
                       "تأیید نهایی داده‌های ورودی محاسبات") -> bool:
        """جدول همه ورودی‌های محاسبات — فقط «تأیید و اجرا» ادامه می‌دهد؛
        مقادیر ویرایش‌شده دقیقاً همان‌هایی است که محاسبه می‌شوند."""
        from ..inputs_model import collect_placement_rows
        from ..qt.inputs_confirm_dialog import make_inputs_confirm_dialog
        lam_matrix = _lam_rows_of(state.get("outage")) or \
            _lam_rows_of(state.get("outage_store"))
        active_keys = study_feeder_keys()
        active_set = set(active_keys)
        if state.get("scope"):
            lam_matrix = [m for m in lam_matrix
                          if (m.get("feeder_key") if isinstance(m, dict)
                              else getattr(m, "feeder_key", "")) in active_set]
        rows = collect_placement_rows(
            lam_matrix=lam_matrix,
            feeder_keys=active_keys,
            capacity_rows=[r for r in (state.get("capacity_rows") or [])
                           if r.get("feeder_key") in active_set],
            load_model=state.get("load_model") or {},
            cost_model=state.get("cost_model") or {},
            criteria=state.get("criteria") or {},
            coverage=state.get("coverage") or {},
            weights=list(state.get("weights") or []),
            engine_info=[
                ("دامنه مطالعه", scope_label()),
                ("فیدرهای مورد درخواست داده", ", ".join(active_keys)),
                ("منبع λ", "ماتریس فاز ۳ (آخرین اجرای خاموشی)"
                 if lam_matrix else "بدون داده خاموشی — λ=۰")])
        dlg = make_inputs_confirm_dialog(win, rows, title)
        if not dlg.exec():
            return False
        edits = dlg.result_edits()
        if edits:
            _apply_input_edits(edits)
        # Load Scaling is the default.  Do not silently calculate zero-load
        # feeders when the required feeder-total P/Q has not been supplied.
        load_cfg = state.setdefault("load_model", {})
        load_cfg.setdefault("level", "scaled")
        if load_cfg.get("level", "scaled") == "scaled":
            from ..inputs_model import missing_load_scaling_inputs
            missing = missing_load_scaling_inputs(
                active_keys, load_cfg.get("feeder_pq") or {})
            if missing:
                QMessageBox.warning(
                    win, "Load Scaling — missing feeder load",
                    "مدل پیش‌فرض Load Scaling است. برای فیدر(های) زیر هر دو مقدار بار کل "
                    "P (kW) و Q (kvar) وارد نشده است:\n\n"
                    + ", ".join(missing)
                    + "\n\nاز Engineering settings → Load model، بار کل فیدر را وارد "
                      "کنید یا مدل بار دیگری را آگاهانه انتخاب کنید.")
                return False
        return True

    def do_exports() -> None:
        """Phase 5 with an explicit format choice (نیاز ۱۲)."""
        from ..qt.settings_dialog import make_exports_dialog
        plc = state.get("plc")
        if plc is None and state.get("db") is None:
            QMessageBox.warning(
                win, "Exports",
                "No study available. Run placement first, or open a "
                "project that already contains a placement run.")
            return
        dlg = make_exports_dialog(win)
        if not dlg.exec():
            return
        formats = dlg.selected() or ("xlsx",)
        # نام پروژه در گزارش — از کاربر پرسیده می‌شود (درخواست کاربر، مورد ۴)
        default_name = state.get("report_project_name") or \
            (Path(state["db"]).stem if state.get("db") else "")
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            win, "نام پروژه در گزارش",
            "نام پروژه‌ای که در گزارش درج شود:", text=default_name)
        if not ok:
            return
        name = (name or "").strip() or default_name or "پروژه"
        state["report_project_name"] = name
        _persist_project_kv()
        out_dir = str(_reports_dir() / "exports")
        net, topo, db = state.get("net"), state.get("topo"), state["db"]
        manual = list(state.get("manual_evals") or [])

        def work():
            from ...reporting.service import ExportSettings, ReportService
            settings = ExportSettings(out_dir=out_dir, formats=formats,
                                      project_name=name, manual_evals=manual)
            if plc is not None and net is not None and topo is not None:
                return ReportService(settings).run(
                    db_path=db, net=net, topo=topo, placement=plc.result,
                    placement_run_id=getattr(plc, "run_id", "") or "")
            return ReportService(settings).run(db_path=db)

        def done(res) -> None:
            set_workflow("Exports")
            QMessageBox.information(
                win, "Exports ready",
                f"{res.summary_fa}\n\nOutputs are under:\n{out_dir}")

        run_task(win, "Building exports…", work, done,
                 error_box(win, "Exports failed"), title="Exports")

    btn_exports.clicked.connect(lambda *_: do_exports())

    def do_placement() -> None:
        if not scope_is_valid():
            QMessageBox.warning(win, "Study scope",
                                "برای تحلیل محدود، دست‌کم یک فیدر را انتخاب کنید.")
            return
        if state.get("db") is None:
            QMessageBox.warning(
                win, "Placement",
                "No project is open. Import data or open a project first "
                "(Data Import tab), or start the app with a project file:  "
                "SwitchLoc.exe projects\\x.sqlite")
            return
        # جدول تأیید ورودی‌ها قبل از هر اجرا (رنک یا دستی) — مورد ۵
        if not confirm_inputs():
            return
        db = state["db"]

        def work():
            from ...application.placement_service import (
                PlacementAppSettings, PlacementService)
            eng = PlacementAppSettings().engine
            if state.get("load_model"):
                from ...reliability.load_model import LoadModelSettings
                eng.load_model = LoadModelSettings.from_dict(state["load_model"])
            if state.get("criteria"):
                from ...placement.acceptance import AcceptanceCriteria
                eng.criteria = AcceptanceCriteria(**{
                    k: v for k, v in state["criteria"].items()
                    if k in AcceptanceCriteria.__dataclass_fields__})
            if state.get("cost_model"):
                from ...placement.economics import CostModel
                eng.cost = CostModel(**{
                    k: v for k, v in state["cost_model"].items()
                    if k in CostModel.__dataclass_fields__})
            if state.get("weights"):
                eng.ranking.weights = [float(w) for w in state["weights"]]
            svc = PlacementService(PlacementAppSettings(
                user="ui-user", persist=True, report_dir=str(_reports_dir()),
                scope_feeder=(state.get("scope") if isinstance(state.get("scope"), str) else None),
                scope_feeders=(tuple(state.get("scope") or [])
                               if isinstance(state.get("scope"), (list, tuple, set)) else ()),
                engine=eng,
                lam_overrides=(dict(state["lambda_overrides"])
                               if state.get("lambda_overrides") else None)))
            return svc.run(db)

        def done(run) -> None:
            state["dirty"] = True
            state["plc"] = run
            if run.topo is not None:
                state["topo"] = run.topo
            plac_panel.setPlainText(fmt_placement_result(run.result))
            btn_show_plac_map.setEnabled(True)
            btn_exports.setEnabled(True)
            refresh_plan_table()
            refresh_map()
            refresh_dashboard()
            set_workflow("Placement")
            n_acc = sum(1 for r in run.result.recommendation
                        if r.get("status") == "accepted")
            n_cap = sum(1 for r in run.result.recommendation
                        if r.get("status") == "needs_capacity_confirmation")
            n_noj = sum(1 for r in run.result.recommendation
                        if r.get("status") == "no_justification")
            QMessageBox.information(
                win, "Placement result",
                f"Feeders ranked: {len(run.result.ranking.rows)}\n"
                f"Schemes generated: {len(run.result.schemes)}\n"
                f"Plans: {n_acc} accepted / {n_cap} need capacity / "
                f"{n_noj} not justified\n\n"
                "Details are shown in this tab; the Map tab shows the "
                "proposed switch locations.")

        run_task(win, "Running placement & ranking…", work, done,
                 error_box(win, "Placement failed"), title="Placement")

    # plan table (وضعیت طرح هر فیدر + ENS + دروازه تأیید — نیاز ۹/۱۰) -----
    plan_table = QTableWidget(0, 7)
    plan_table.setHorizontalHeaderLabels(
        ["Feeder", "Rank", "Plan status", "Scheme", "Switches",
         "ENS before (kWh/yr)", "ENS after (kWh/yr)"])
    plan_table.horizontalHeader().setStretchLastSection(True)
    plan_table.verticalHeader().setVisible(False)
    plan_table.setSelectionBehavior(
        QAbstractItemView.SelectionBehavior.SelectRows)
    plan_table.setMaximumHeight(190)

    def refresh_plan_table() -> None:
        from ..qt.widgets import fill_table
        plc = state.get("plc")
        if plc is None:
            plan_table.setRowCount(0)
            return
        reviews = state.get("plan_reviews") or {}
        eco = plc.result.economics
        after_of = getattr(eco, "ens_after_kwh", {}) or {}
        active_keys = set(study_feeder_keys())
        visible_rows = [r for r in plc.result.recommendation
                        if not scope_is_restricted()
                        or r.get("feeder_key") in active_keys]
        data = []
        for r in visible_rows:
            status = r.get("status_fa", r.get("status", ""))
            if reviews.get(r["feeder_key"], {}).get("status") == "approved":
                status = "✔ تأیید نهایی مهندسی"
            before = (getattr(eco, "ens_before_kwh", {}) or {}).get(
                r["feeder_key"])
            sid = r.get("scheme_id")
            after = (after_of.get(sid, {}) or {}).get(
                r["feeder_key"]) if sid else before
            data.append([
                r["feeder_key"], str(r.get("rank") or ""), status,
                r.get("scheme_kind") or "—",
                str(r.get("n_switches") or 0),
                f"{before:,.1f}" if before is not None else "—",
                f"{after:,.1f}" if after is not None else "—"])
        fill_table(plan_table, [
            "Feeder", "Rank", "Plan status", "Scheme", "Switches",
            "ENS قبل (kWh/سال)", "ENS بعد (kWh/سال)"], data)
        # نگاشت ردیف مرتب‌شده ← فیدر برای دکمه تأیید
        for i, r in enumerate(visible_rows):
            it = plan_table.item(i, 0)
            if it is not None:
                it.setData(Qt.ItemDataRole.UserRole, r["feeder_key"])

    btn_row3 = QHBoxLayout()
    btn_plac = QPushButton(t("Run placement & ranking"))
    btn_plac.clicked.connect(lambda *_: do_placement())
    btn_show_plac_map.clicked.connect(lambda: tabs.setCurrentWidget(map_tab))
    btn_row3.addWidget(btn_plac)
    btn_row3.addWidget(btn_show_plac_map)
    btn_row3.addWidget(btn_exports)
    btn_row3.addWidget(btn_settings)
    btn_row3.addWidget(btn_approve)
    btn_row3.addStretch(1)
    plac_lcol.addLayout(btn_row3)
    plac_lcol.addWidget(QLabel("Plan per feeder (acceptance status + ENS "
                               "قبل/بعد + دروازه تأیید — نیاز ۹/۱۰):"))
    plac_lcol.addWidget(plan_table)
    # ستون راست = نتیجه (درخواست کاربر: دو پنجره کنار هم)
    plac_rcol.addWidget(QLabel("<b>Placement result</b> — رتبه‌بندی، طرح‌ها "
                               "و مقایسه اقتصادی (خروجی کامل گام‌های ۴-۸):"))
    plac_rcol.addWidget(plac_panel, 1)

    # ---------------- Map tab ------------------------------------------------
    def refresh_map() -> None:
        topo = state.get("topo")
        if topo is None:
            return
        display_zones = state.get("manual_zone_result") or topo.zones
        renderer = NetworkMapRenderer(
            topo.graph, traces=topo.traces, zones=display_zones,
            switches={s.id: s for s in state["net"].switches},
            tie_switch_ids={c.switch_id for c in topo.ties if c.switch_id},
            style=state.get("map_style"))
        proposed = None
        plc = state.get("plc")
        if plc is not None:
            proposed = {sw["node"] for r in plc.result.recommendation
                        for sw in r["switches"]} or None
        # جایابی دستی — نقاط ارزیابی‌شده روی نقشه (درخواست کاربر، مورد ۶)
        manual = sorted({n for ev in (state.get("manual_evals") or [])
                         if ev.get("before") and ev.get("after")
                         for n in (ev.get("switch_nodes") or [])})
        crs = project_crs() or ""      # data-driven — no site default
        from ..dashboard_data import zone_load_map
        plc_result = (state["plc"].result if state.get("plc") is not None
                      else None)
        from types import SimpleNamespace
        display_topo = SimpleNamespace(graph=topo.graph, zones=display_zones)
        zone_loads = zone_load_map(
            display_topo, state.get("net"), state.get("load_model") or {},
            placement=None if state.get("manual_zone_result") else plc_result)
        map_tab.show_network(renderer, title="SwitchLoc — Network Map",
                             proposed_nodes=proposed, crs=crs,
                             manual_nodes=manual or None,
                             highlight_point=state.get("manual_highlight_point"),
                             zone_load_kw=zone_loads,
                             zone_up_mwh=state.get("zone_up_mwh") or {},
                             zone_outage_hours=state.get("zone_outage_hours") or {},
                             manual_tie_pairs=state.get("manual_tie_pairs") or [],
                             feeder_filter=(state.get("scope")
                                            if isinstance(state.get("scope"), str)
                                            else "__ALL__"))

    tabs.addTab(import_tab, "Data Import")
    tabs.addTab(topo_tab, "Topology")
    tabs.addTab(plac_tab, "Placement")
    tabs.addTab(dash_tab, "Dashboard")
    tabs.addTab(map_tab, "Map")

    # ---------------- application chrome (menus / toolbar / sidebar) ------
    def show_help() -> None:
        QMessageBox.information(
            win, "SwitchLoc — Help",
            "<b>گردش کار مطالعه (TAV122-02/00 — روش سطح اول)</b>"
            "<ol>"
            "<li><b>Data Import</b>: ورود GIS (جادوک تطبیق) یا بازکردن "
            "پروژه + ورود فایل خاموشی هر فیدر (نیاز ۸).</li>"
            "<li><b>Topology</b>: اجرای تحلیل توپولوژی و بازبینی کاندیدهای "
            "NO (A-09).</li>"
            "<li><b>Placement</b>: تنظیمات مهندسی (مدل بار Load Scaling، "
            "ظرفیت نیاز ۹، هزینه‌ها)، اجرای جایابی، جایابی دستی کلید با "
            "کلیک روی نقشه یا مختصات UTM، و تأیید نهایی طرح.</li>"
            "<li><b>Dashboard</b>: نمای مدیریتی (λ/r، رتبه، ENS، جدول آشتی "
            "ترانس‌ها).</li>"
            "<li><b>Map</b>: نقشه تعاملی — اسکرول زوم، درگ جابجایی، دابل‌کلیک "
            "زوم، انتخاب محدوده (ذره‌بین)، پس‌زمینه OSM.</li>"
            "</ol>"
            "<b>جداول</b>: کلیک روی هدر ستون = مرتب‌سازی؛ Ctrl+C = کپی "
            "(TSV سازگار با Excel)؛ در جدول‌های ورودی Ctrl+V = چسباندن."
            "<br><b>فیلدهای ستاره‌دار (*)</b> الزامی‌اند.")

    def show_about() -> None:
        QMessageBox.about(
            win, "About SwitchLoc",
            f"<b>{APP_NAME}</b> نسخه {__version__}"
            "<p>ابزار مطالعه جایابی کلید و برنامه‌ریزی اتوماسیون شبکه توزیع "
            "بر مبنای آیین‌نامه TAV122-02/00 توانیر (روش سطح اول، گام‌های "
            "۱ تا ۸).</p>"
            "<p>موتور محاسبات: توپولوژی GIS→DGS، تحلیل n-1 (جداول ۱۳-۱۵)، "
            "رتبه‌بندی فرمول (۱)/جدول ۱۶، طرح‌های جدول ۱۷ با قاعده U×P، "
            "مقایسه اقتصادی جدول ۱۸ (CE/CN) و مدل بار چهار‌سطحی با منشأ "
            "ردیابی‌پذیر (بند ۱۹).</p>"
            f"<p><small>Log: {log_path_text()}</small></p>")

    def do_approve_shim() -> None:
        do_approve()

    # ---------------- project lifecycle: New / Save / Save As ------------
    def _confirm_pending_changes() -> bool:
        if not state.get("dirty"):
            return True
        answer = QMessageBox.question(win, "تغییرات پروژه",
            "تغییرات پروژه فعلی ذخیره نشده است. آیا ذخیره شود؟",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return do_save_project()
        state["dirty"] = False
        return True

    def _save_project_to(path: str) -> bool:
        """Flush the SQLite project; all engineering records are persisted transactionally."""
        import sqlite3
        from pathlib import Path as _Path
        target = _Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        current = state.get("db")
        if current and _Path(current).exists() and _Path(current).resolve() != target.resolve():
            src = sqlite3.connect(str(current))
            dst = sqlite3.connect(str(target))
            try:
                src.backup(dst)
                dst.commit()
            finally:
                dst.close(); src.close()
        elif current and _Path(current).exists():
            con = sqlite3.connect(str(current))
            try:
                con.execute("PRAGMA wal_checkpoint(FULL)")
                con.commit()
            finally:
                con.close()
        else:
            store = ProjectStore(str(target)); store.close()
        state["db"] = str(target)
        state["dirty"] = False
        remember_project(str(target))
        status_msg(f"پروژه ذخیره شد: {target.name}")
        return True

    def do_save_project() -> bool:
        if not state.get("db"):
            return do_save_project_as()
        try:
            return _save_project_to(str(state["db"]))
        except Exception as exc:
            _write_log(_fmt_exc(exc))
            QMessageBox.critical(win, "Save project", f"ذخیره پروژه ناموفق بود:\n{exc}")
            return False

    def do_save_project_as() -> bool:
        if not state.get("db"):
            QMessageBox.information(win, "Save As", "ابتدا داده‌های GIS را وارد یا یک پروژه را باز کنید.")
            return False
        path, _ = QFileDialog.getSaveFileName(win, "Save SwitchLoc project as", str(_projects_dir()), "SwitchLoc project (*.sqlite)")
        if not path:
            return False
        if not path.lower().endswith(".sqlite"):
            path += ".sqlite"
        try:
            return _save_project_to(path)
        except Exception as exc:
            _write_log(_fmt_exc(exc))
            QMessageBox.critical(win, "Save As", f"ذخیره نسخه مستقل ناموفق بود:\n{exc}")
            return False

    def do_new_project() -> None:
        if not _confirm_pending_changes(): return
        path, _ = QFileDialog.getSaveFileName(win, "ایجاد پروژه جدید", str(_projects_dir() / "NewProject.sqlite"), "SwitchLoc project (*.sqlite)")
        if not path: return
        if not path.lower().endswith(".sqlite"): path += ".sqlite"
        try:
            from ...persistence.store import ProjectStore
            store = ProjectStore(path); store.close()
            state.update({"db": path, "net": None, "topo": None, "run_id": None,
                          "plc": None, "outage": None, "outage_store": None,
                          "capacity_rows": [], "manual_evals": [], "manual_zone_result": None, "manual_tie_pairs": [], "scope": None,
                          "dirty": False})
            refresh_dashboard(); refresh_project_info(); remember_project(path)
            import_panel.setPlainText(f"پروژه جدید ایجاد شد: {path}\nاکنون داده‌های GIS را وارد کنید.")
        except Exception as exc:
            QMessageBox.critical(win, "New project", str(exc))

    def _close_with_project_prompt(event) -> None:
        if not _confirm_pending_changes():
            event.ignore(); return
        event.accept()

    chrome = install_chrome(
        win, app, tabs, workflow,
        handlers={
            "open_project": do_open_project,
            "new_project": do_new_project,
            "save_project": do_save_project,
            "save_project_as": do_save_project_as,
            "import_gis": do_import,
            "import_outage": do_outage_import,
            "per_feeder": do_outage_per_feeder,
            "topology": do_topology,
            "placement": do_placement,
            "settings": open_settings,
            "exports": do_exports,
            "approve": do_approve_shim,
            "map_style": open_map_style,
            "help": show_help,
            "about": show_about,
        },
        assets_dir=assets, version=__version__)
    chrome_ref["c"] = chrome
    win.closeEvent = _close_with_project_prompt
    win.setCentralWidget(chrome.central)
    chrome.set_workflow(chrome_ref["wf"])
    # icons + primary emphasis on the existing action buttons
    for _btn, _ico, _prim in (
            (btn_import, "import", True), (btn_open, "folder", False),
            (btn_outage, "outage", True), (btn_outage_feeders, "file", False),
            (btn_topo, "topology", True), (btn_show_map, "map", False),
            (btn_plac, "run", True), (btn_show_plac_map, "map", False),
            (btn_exports, "export", False), (btn_settings, "settings", False),
            (btn_approve, "approve", False), (btn_m_add, "plus", False),
            (btn_m_del, "trash", False), (btn_m_clear, "x-circle", False), (btn_m_pick, "crosshair", False),
            (btn_m_eval, "run", True)):
        chrome.style_button(_btn, _ico, primary=_prim)

    # -- restore an existing project passed on the command line -------------
    if db_path:
        step(f"Opening project {Path(db_path).name}…")
        try:
            store = ProjectStore(str(db_path))
            net, _issues = store.load_network()
            _has_plc = bool(store.list_placement_runs())
            try:
                state["outage_store"] = store.load_outages()
            except ValueError:
                state["outage_store"] = None
            try:
                state["capacity_rows"] = [c.as_dict() for c in
                                          store.load_feeder_capacity().values()]
                state["tie_reviews"] = store.load_tie_reviews()
            except Exception as exc:                   # noqa: BLE001
                _log.warning("capacities/reviews not loaded: %s", exc)
            store.close()
            if net is not None:
                state["net"], state["db"] = net, str(db_path)
                _load_project_kv(str(db_path))   # استایل‌ها + نام گزارش
                # prior placement run → phase-5 exports available
                btn_exports.setEnabled(_has_plc)
        except Exception as exc:                       # noqa: BLE001
            _write_log(_fmt_exc(exc))
            QMessageBox.warning(win, "SwitchLoc",
                                f"Could not open project:\n{exc}")
    refresh_scope_choices()
    refresh_outage_feeder_table()
    refresh_dashboard()
    refresh_plan_table()
    refresh_tie_table()
    refresh_manual_feeders()
    refresh_project_info()
    if state.get("db"):
        chrome.add_recent(str(state["db"]))
    step("Ready — starting interface…")
    _close_installer_splash()

    # -- window geometry: 75 % of the display, centered (نیاز ۷ + درخواست
    #    کاربر: «سایز اولیه پنجره ۵۰٪ بزرگتر شود» — 50% → 75%)
    from PySide6.QtGui import QGuiApplication
    win.setMinimumSize(640, 420)
    screen = QGuiApplication.primaryScreen().availableGeometry()
    target_w = max(640, int(screen.width() * 0.75))
    target_h = max(420, int(screen.height() * 0.75))
    win.resize(target_w, target_h)
    frame = win.frameGeometry()
    frame.moveCenter(screen.center())
    win.move(frame.topLeft())
    win.show()                 # NOT maximized — 75 % centered (نیاز ۷)
    set_workflow("Import")
    if splash is not None:
        splash.finish(win)     # the loading bar stays until the UI is up
    return app.exec()


if __name__ == "__main__":                          # pragma: no cover
    raise SystemExit(launch(sys.argv[1] if len(sys.argv) > 1 else None))
