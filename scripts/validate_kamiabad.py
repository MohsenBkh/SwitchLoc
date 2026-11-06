# -*- coding: utf-8 -*-
"""Kamiabad end-to-end validation (user request #7).

Runs the WHOLE SwitchLoc pipeline on the new kamiabad data:
  1. GIS import (10 ELW layers, UTM 38N)
  2. Topology (feeder tracing, zones, tie candidates)
  3. Per-feeder separation check — every feeder must have its own
     node/transformer counts (the critical separation bug must not
     re-appear on this dataset)
  4. Outage list (kamiabad.xlsx) — λ/r on the real data exposure
  5. Placement — ranking, schemes, acceptance
  6. Renders: full map + one PNG per feeder (full-frame, legend)
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path("/home/z/my-project/download/SwitchLoc")
sys.path.insert(0, str(ROOT / "src"))
OUT = Path("/home/z/my-project/download/kamiabad_validation")
OUT.mkdir(parents=True, exist_ok=True)
WORK = Path("/home/z/my-project/work/kamiabad_shp/kamiabad")

import matplotlib
matplotlib.use("Agg")

from switchloc.application.import_service import ImportService, ImportSettings
from switchloc.application.outage_service import OutageService, OutageSettings
from switchloc.application.placement_service import (
    PlacementAppSettings, PlacementService)
from switchloc.application.topology_service import (
    TopologyService, TopologySettings)
from switchloc.ui.map_renderer import NetworkMapRenderer

DB = ROOT / "projects" / "kamiabad_phase1.sqlite"
GIS_DIR = WORK / "Export_1404_08_17_10_31_56"
XLSX = Path("/home/z/my-project/upload/kamiabad.xlsx")


def main() -> int:
    lines = []

    def log(s=""):
        print(s)
        lines.append(str(s))

    # ---- 1. GIS import ------------------------------------------------
    if DB.exists():
        DB.unlink()
    settings = ImportSettings(project_name="کمی آباد — اعتبارسنجی فاز ۷",
                              user="kamiabad-check", snap_tol_m=0.5,
                              out_db=str(DB))
    svc = ImportService(settings)

    def confirm(suggestions, mapping, layers):
        for s in suggestions:
            if s.confidence != "high":
                s.slot_key = "unmapped"
        return True

    res = svc.run(GIS_DIR, confirm_fn=confirm)
    log("== 1) GIS import ==")
    log(f"verdict={res.report.verdict}  features={res.report.total_features}"
        f"  accepted={res.accepted}")
    log(f"layers: " + ", ".join(
        f"{k}:{v}" for k, v in sorted(res.report.layers.items())))
    net = res.network
    crs_list = [getattr(cd, "epsg", None) for cd in
                (getattr(net, "crs_definitions", None) or [])]
    log(f"CRS epsg in project: {crs_list}")
    log("")

    # ---- 2. topology ---------------------------------------------------
    topo = TopologyService(TopologySettings(user="kamiabad-check",
                                            persist=False)).run(net)
    log("== 2) topology ==")
    log(f"verdict={topo.verdict}  feeders={len(topo.traces)}  "
        f"zones={len(topo.zones.zones)}  ties={len(topo.ties)}")
    log("")

    # ---- 3. per-feeder separation (the critical check) -----------------
    log("== 3) per-feeder separation (must be DISTINCT) ==")
    rows = []
    for t in sorted(topo.traces, key=lambda t: t.feeder_key):
        tr_n = sum(1 for n in t.nodes
                   if topo.graph.transformer_ids_at.get(n))
        rows.append((t.feeder_key, len(t.nodes), len(t.edges),
                     t.length_m / 1000.0, tr_n))
    log(f"{'feeder':<14}{'nodes':>7}{'edges':>7}{'km':>9}{'TR':>6}")
    for k, n, e, km, tr in rows:
        log(f"{k:<14}{n:>7}{e:>7}{km:>9.2f}{tr:>6}")
    sig = {(n, e, round(km, 3)) for _k, n, e, km, _t in rows}
    distinct = len(sig) == len(rows)
    log(f"-> distinct feeder footprints: {distinct} "
        f"({len(sig)}/{len(rows)} unique node/edge/length sets)")
    log("")

    # ---- 4. outage list -------------------------------------------------
    log("== 4) outage list (kamiabad.xlsx) ==")
    ores = OutageService(OutageSettings(user="kamiabad-check", persist=True)
                         ).run(str(XLSX), out_db=str(DB), report_dir="reports",
                               project_name="kamiabad_validation")
    log(f"verdict={ores.verdict}  records={len(ores.records):,}")
    cov = getattr(ores, "levels", {}).get("coverage") or {}
    if cov.get("start"):
        miss = cov.get("missing_months") or []
        log(f"coverage {cov['start'][0]}/{cov['start'][1]:02d} .. "
            f"{cov['end'][0]}/{cov['end'][1]:02d} — "
            f"{len(cov.get('effective_months') or [])} months with data, "
            f"{cov.get('exposure_days')} days = "
            f"{cov.get('exposure_years'):.4f} yr")
        if miss:
            log(f"missing months (excluded): {', '.join(miss)}")
    for f in ores.lambda_r:
        log(f"  {f.feeder_key:<14} λ={f.lambda_per_year:>6.2f}/yr  "
            f"r={f.r_minutes:>6.1f} min  U={f.u_hours:>6.2f} h/yr")
    log("")

    # ---- 5. placement ----------------------------------------------------
    log("== 5) placement & acceptance ==")
    run = PlacementService(PlacementAppSettings(
        user="kamiabad-check", persist=True, report_dir="reports")).run(str(DB))
    snap = run.result.to_dict()
    for r in snap["ranking"]:
        log(f"  #{r['rank']} {r['feeder_key']:<14} score={r['score']:.4f}  "
            f"λ={r['lambda_per_year']:.1f}  EP={r['ep_percent']:.1f}%")
    log(f"schemes: {len(snap['schemes'])}")
    acc = sum(1 for r in snap["recommendation"]
              if r.get("status") == "accepted")
    cap = sum(1 for r in snap["recommendation"]
              if r.get("status") == "needs_capacity_confirmation")
    noj = sum(1 for r in snap["recommendation"]
              if r.get("status") == "no_justification")
    log(f"plans: {acc} accepted / {cap} need-capacity / {noj} not justified")
    for r in snap["recommendation"]:
        st = r.get("status_fa") or r.get("status")
        log(f"  {r['feeder_key']:<14} [{st}] "
            f"{r.get('scheme_kind') or '—'}")
    log("")

    # ---- 6. maps ----------------------------------------------------------
    log("== 6) rendered maps ==")
    rend = NetworkMapRenderer(
        topo.graph, traces=topo.traces, zones=topo.zones,
        switches={s.id: s for s in net.switches},
        tie_switch_ids={c.switch_id for c in topo.ties if c.switch_id})
    full = OUT / "map_all_feeders.png"
    rend.render(str(full), title="Kamiabad — all feeders",
                figsize=(14, 10), dpi=130)
    log(f"  {full.name}  ({full.stat().st_size // 1024} KB)")
    for t in sorted(topo.traces, key=lambda t: t.feeder_key):
        p = OUT / f"map_{t.feeder_key.replace(' ', '_')}.png"
        rend.render(str(p), title=f"Kamiabad — {t.feeder_key}",
                    feeder_filter=t.feeder_key, figsize=(14, 10), dpi=130)
        log(f"  {p.name}  ({p.stat().st_size // 1024} KB)")

    (OUT / "validation_report.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    log(f"\nreport saved: {OUT / 'validation_report.txt'}")
    return 0 if (distinct and res.accepted) else 1


if __name__ == "__main__":
    raise SystemExit(main())
