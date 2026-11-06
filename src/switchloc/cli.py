# -*- coding: utf-8 -*-
"""CLI — python -m switchloc (Phase 1: import / inspect).

The PySide6 wizard (Phase 2) reuses exactly these services; the CLI is
the UI-agnostic contract.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .application.import_service import ImportService, ImportSettings
from .application.outage_service import OutageService, OutageSettings
from .application.topology_service import TopologyService, TopologySettings
from .persistence.store import ProjectStore


def _cmd_import(args) -> int:
    def confirm(suggestions, mapping, layers):
        # explicit consent on the CLI: --auto-confirm or a mapping file.
        # Without consent the service would have stopped before reading.
        return True

    if not args.auto_confirm:
        print("No automatic mapping is final (master-prompt rule §5-3).")
        print("Give explicit consent with --auto-confirm or --mapping mapping.json")
        return 2

    settings = ImportSettings(
        project_name=args.project, user=args.user,
        snap_tol_m=args.snap_tol, out_db=args.out)
    svc = ImportService(settings)
    res = svc.run(args.source, confirm_fn=confirm)
    rep = res.report
    print(rep.to_markdown())
    if args.report_json:
        Path(args.report_json).write_text(
            json.dumps(rep.as_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8")
    if not res.unchanged:
        print("WARNING: input files were modified during the study (GG-02).")
        return 1
    return 0 if res.accepted else 1


def _cmd_inspect(args) -> int:
    store = ProjectStore(args.db)
    runs = store.runs()
    if not runs:
        print("The project is empty.")
        return 1
    for r in runs:
        print(f"- run {r['id'][:12]}… project={r['project']} at={r['started_at']}"
              f" user={r['user']} algo={r['algo_version']}")
    net, issues = store.load_network(runs[-1]["id"])
    s = net.summary()
    print(json.dumps(s, ensure_ascii=False, indent=2, default=str))
    print(f"Issue counts: Error={issues.count('Error')} "
          f"Warning={issues.count('Warning')} "
          f"Information={issues.count('Information')}")
    store.close()
    return 0


def _cmd_topology(args) -> int:
    """Phase 2 — graph, feeder tracing, tie candidates and zones."""
    path = Path(args.db_or_source)
    source_run_id = ""
    if path.is_file() and path.suffix.lower() in (".sqlite", ".db"):
        store = ProjectStore(path)
        runs = store.runs()
        if not runs:
            print("The SQLite project contains no runs.")
            return 1
        source_run_id = runs[-1]["id"]
        net, issues = store.load_network(source_run_id)
        store.close()
    else:
        def confirm(suggestions, mapping, layers):
            return True
        settings = ImportSettings(project_name=args.project, user=args.user)
        res = ImportService(settings).run(path, confirm_fn=confirm)
        if not res.accepted:
            print(res.report.to_markdown())
            return 1
        net, issues, source_run_id = res.network, res.issues, res.run_id

    topo = TopologyService(TopologySettings(
        user=args.user,
        unknown_switch_pass=not args.unknown_blocks,
        include_fuse_cutout_as_boundary=args.fuses_bound_zones,
        persist=bool(args.out_db),
    )).run(net, issues=issues, source_run_id=source_run_id,
           out_db=args.out_db)

    print(topo.report.to_markdown())
    print("\n— Topology summary —")
    print(json.dumps(topo.zones.as_dict(), ensure_ascii=False, indent=2))
    for t in topo.traces:
        print(f"  feeder {t.feeder_key:12s} nodes={len(t.nodes):6d} "
              f"length={t.length_m/1000:8.2f} km")
    print(f"  tie candidates: {len(topo.ties)}")
    if args.report_dir:
        rd = Path(args.report_dir)
        rd.mkdir(parents=True, exist_ok=True)
        (rd / "topology_report.json").write_text(
            json.dumps({
                "verdict": topo.report.verdict,
                "summary": topo.report.summary,
                "zones": topo.zones.as_dict(),
                "traces": [t.as_dict() for t in topo.traces],
                "ties": [c.as_dict() for c in topo.ties],
                "settings": topo.settings,
            }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"report → {rd / 'topology_report.json'}")
    return 0 if topo.verdict == "PASS" else 1


def _cmd_report(args) -> int:
    """Phase 5 — Excel / Word / PDF / GIS exports of a completed study."""
    from switchloc.reporting.service import ExportSettings, ReportService
    formats = tuple(f.strip() for f in args.formats.split(",")
                    if f.strip() in ("xlsx", "docx", "pdf", "gis"))
    if not formats:
        print("ERROR: no valid format in --formats "
              "(valid: xlsx,docx,pdf,gis)")
        return 2
    svc = ReportService(ExportSettings(
        out_dir=args.out, formats=formats, user=args.user))
    try:
        res = svc.run(db_path=args.db)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2
    print(res.summary_fa)
    for code, sev, msg in res.issues:
        print(f"  [{sev}] {code}: {msg}")
    return 0 if res.verdict == "PASS" else 1


def _cmd_placement(args) -> int:
    """Phase 4 — n-1, feeder ranking (formula 1 / table 16), schemes
    (table 17), CE/CN comparison (table 18)."""
    from switchloc.application.placement_service import (
        PlacementAppSettings, PlacementService)
    from switchloc.placement.golden import GoldenSettings
    from switchloc.placement.schemes import PlacementSettings
    from switchloc.placement.service import EngineSettings
    engine_settings = EngineSettings()
    engine_settings.placement.max_feeders = args.max_feeders
    engine_settings.placement.golden = GoldenSettings(
        target_zones=args.nc_sections)
    if args.rated:
        rated = {}
        for part in args.rated.split(","):
            key, _, val = part.partition("=")
            rated[key.strip()] = float(val)
        engine_settings.placement.feeder_rated_kw = rated
    svc = PlacementService(PlacementAppSettings(
        user=args.user, persist=not args.no_persist,
        report_dir=args.report_dir, outage_workbook=args.outages,
        engine=engine_settings))
    try:
        res = svc.run(args.db)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2
    snap = res.result.to_dict()
    print("— جدول ۱۴ (EP/TL) —")
    for r in snap["table14_eptl"]:
        print(f"  {r['feeder_key']:5s} EP={r['ep_percent']:6.1f}%  "
              f"TL={r['tl_percent']:6.1f}%  load={r['total_load_kw']:9.0f} kW "
              f"zones={r['zone_count']}")
    print("— رتبه‌بندی (فرمول ۱ + جدول ۱۶) —")
    for r in snap["ranking"]:
        print(f"  #{r['rank']} {r['feeder_key']:5s} score={r['score']:.4f} "
              f"ties={r['ties_count']} λ={r['lambda_per_year']:.2f}/yr "
              f"r={r['r_minutes']:.1f}min")
    print(f"— طرح‌ها: {len(snap['schemes'])} | مقایسه جدول ۱۸: "
          f"{sum(1 for c in snap['table18_comparison'] if c['selected'])} "
          "طرح اصلی —")
    for r in snap["recommendation"]:
        sw = PlacementService._fmt_switches(r)
        print(f"  #{r['rank']} {r['feeder_key']:5s} → "
              f"{r['scheme_kind'] or '— (صرفه صفر)'} {sw}")
    if res.run_id:
        print(f"persisted: placement_run {res.run_id} → {res.db_path}")
    if res.report_md:
        print(f"report  → {res.report_md}")
    return 0 if res.verdict == "PASS" else 1


def _cmd_outages(args) -> int:
    """Phase 3 — outage ingestion/classification + λ/r matrix (step 2 / fig. 5)."""
    res = OutageService(OutageSettings(user=args.user)).run(
        args.workbook, out_db=args.out_db, report_dir=args.report_dir,
        project_name=args.project)
    print(res.report.to_markdown())
    print("\n— Six-class classification (TAV122 §10) —")
    for k, v in sorted(res.levels["class_summary"].items(), key=lambda kv: -kv[1]):
        print(f"  {k:28s} {v:6,}")
    print("\n— λ/r matrix of modeled feeders —")
    for f in res.lambda_r:
        print(f"  {f.feeder_key:5s} λ={f.lambda_per_year:6.2f}/yr "
              f"r={f.r_minutes:6.1f} min  U={f.u_hours:5.2f} h/yr "
              f"(random events={f.events_random})")
    if args.report_dir:
        print(f"\nreport → {args.report_dir}/phase3_outage_report.md")
    return 0 if res.verdict == "PASS" else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="switchloc",
        description="SwitchLoc — GIS data ingestion for switch placement "
                    "studies (TAV122-02/00 first-level method)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("import", help="Import GIS data from a folder into a SQLite project")
    pi.add_argument("source", help="GIS data folder (containing shp/geojson/gpkg/xlsx/csv)")
    pi.add_argument("--project", default="Unnamed", help="Project name")
    pi.add_argument("--user", default="cli-user")
    pi.add_argument("--out", help="Output SQLite database path")
    pi.add_argument("--snap-tol", type=float, default=0.5,
                    help="Snap tolerance in meters (default 0.5)")
    pi.add_argument("--auto-confirm", action="store_true",
                    help="Explicitly confirm the suggested mappings (CLI consent)")
    pi.add_argument("--report-json", help="Write the QC report to JSON")
    pi.set_defaults(func=_cmd_import)

    ps = sub.add_parser("inspect", help="Summarize a SQLite project")
    ps.add_argument("db")
    ps.set_defaults(func=_cmd_inspect)

    pt = sub.add_parser("topology",
                        help="Phase 2 — graph / feeders / ties / zones from a project or GIS data")
    pt.add_argument("db_or_source",
                    help="SQLite project (import output) or a GIS data folder")
    pt.add_argument("--project", default="Unnamed")
    pt.add_argument("--user", default="cli-user")
    pt.add_argument("--out-db", help="Persist the topology result into this SQLite")
    pt.add_argument("--report-dir", help="Write the topology JSON report into this folder")
    pt.add_argument("--unknown-blocks", action="store_true",
                    help="Switches with unknown state block traversal "
                         "(default TOPO-POL-01: pass with an Issue)")
    pt.add_argument("--fuses-bound-zones", action="store_true",
                    help="Fuse cut-outs also bound zones (TOPO-POL-03)")
    pt.set_defaults(func=_cmd_topology)

    po = sub.add_parser("outages",
                        help="Phase 3 — outage ingestion / classification + λ/r matrix")
    po.add_argument("workbook", help="Excel workbook with the outage list (1405 list)")
    po.add_argument("--project", default="Outage analysis")
    po.add_argument("--user", default="cli-user")
    po.add_argument("--out-db", help="Persist records and the λ/r matrix into this SQLite")
    po.add_argument("--report-dir", help="Write the MD/JSON report into this folder")
    po.set_defaults(func=_cmd_outages)

    pp = sub.add_parser("placement",
                        help="Phase 4 — n-1 (tables 13-15), ranking "
                             "(formula 1 / table 16), schemes (table 17), "
                             "CE/CN (table 18)")
    pp.add_argument("db", help="SQLite project (import output)")
    pp.add_argument("--user", default="cli-user")
    pp.add_argument("--outages", help="Outage workbook (xlsx) for the λ/r "
                                      "matrix; default: latest persisted "
                                      "outage run in the DB")
    pp.add_argument("--report-dir", help="Write the MD/JSON report into this folder")
    pp.add_argument("--max-feeders", type=int, default=3,
                    help="Top-ranked feeders to section (scheme الف)")
    pp.add_argument("--nc-sections", type=int, default=3,
                    help="Target zone count per feeder for the golden rule")
    pp.add_argument("--rated", help="Feeder rated capacities in kW, "
                                    "e.g. 'F1=20000,F2=15000'")
    pp.add_argument("--no-persist", action="store_true",
                    help="Do not write the placement run into the DB")
    pp.set_defaults(func=_cmd_placement)

    pr = sub.add_parser("report",
                        help="Phase 5 — Excel/Word/PDF/GIS exports of a "
                             "completed placement study")
    pr.add_argument("db", help="SQLite project with a persisted placement run")
    pr.add_argument("--out", default="reports/exports",
                    help="Output directory (default reports/exports)")
    pr.add_argument("--formats", default="xlsx,docx,pdf,gis",
                    help="Comma list from: xlsx,docx,pdf,gis")
    pr.add_argument("--user", default="cli-user")
    pr.set_defaults(func=_cmd_report)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
