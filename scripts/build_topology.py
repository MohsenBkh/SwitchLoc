# -*- coding: utf-8 -*-
"""Phase-2 acceptance run: topology on the real Khalkhal network.

Input : projects/khalkhal_phase1.sqlite (Phase-1 deterministic import).
        If missing, the sample is re-imported first (same rules).
Output: reports/phase2_topology_report.md / .json
        reports/maps/network_overview.png + reports/maps/feeder_*.png
        projects/khalkhal_phase1.sqlite  ← topo_run/zone/tie tables

Acceptance (ARCHITECTURE.md §۵ فاز ۲):
  * گراف کامل ساخته شود؛ اتصال تجهیزات نقطه‌ای (splice) درست باشد؛
  * فیدرهای واقعی (F1..F7) از منابع ELWFWT بازسازی شوند؛
  * زون‌بندی بر اساس کلیدها (تعریف ۵-۲۱) انجام شود؛
  * کاندیدهای NO/Tie (A-09) فهرست و ذخیره شوند؛
  * هیچ Issue از رده Error حل‌نشده نباشد → PASS.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from switchloc.application.import_service import ImportService, ImportSettings  # noqa: E402
from switchloc.application.topology_service import (TopologyService,           # noqa: E402
                                                    TopologySettings)
from switchloc.persistence.store import ProjectStore                            # noqa: E402
from switchloc.ui.map_renderer import NetworkMapRenderer                        # noqa: E402

DB = ROOT / "projects" / "khalkhal_phase1.sqlite"
SAMPLE = Path("/home/z/my-project/work/sample_shp/Export_1404_08_17_12_34_09")
REPORTS = ROOT / "reports"
MAPS = REPORTS / "maps"


def ensure_network():
    """Load the Phase-1 run; re-import the sample when the DB is absent."""
    if DB.exists():
        store = ProjectStore(DB)
        runs = store.runs()
        if runs:
            run_id = runs[-1]["id"]
            net, issues = store.load_network(run_id)
            store.close()
            return net, issues, run_id
    if not SAMPLE.is_dir():
        raise SystemExit("نه پایگاه فاز ۱ موجود است و نه نمونه واقعی برای "
                         "ورود مجدد (SWITCHLOC_SAMPLE_DIR).")
    DB.parent.mkdir(parents=True, exist_ok=True)
    svc = ImportService(ImportSettings(
        project_name="خلخال — نمونه واقعی ۱۲ لایه (فاز ۱)",
        user="phase2-acceptance", snap_tol_m=0.5, out_db=str(DB)))

    def confirm(suggestions, mapping, layers):
        for s in suggestions:
            if s.confidence != "high":
                s.slot_key = "unmapped"
        return True

    res = svc.run(SAMPLE, confirm_fn=confirm)
    if not res.accepted:
        raise SystemExit("ورود فاز ۱ پذیرفته نشد؛ توپولوژی متوقف شد.")
    return res.network, res.issues, res.run_id


def write_report(res, run_id: str, topo_run_id: str | None) -> None:
    REPORTS.mkdir(exist_ok=True)
    traces_md = "\n".join(
        f"| {t.feeder_key} | {t.feeder} | {len(t.nodes):,} | "
        f"{len(t.edges):,} | {t.length_m / 1000:,.2f} | "
        f"{len(t.transformer_ids):,} | {len(t.switch_nodes):,} | "
        f"{sum(len(v) for v in t.overlaps.values())} |"
        for t in sorted(res.traces, key=lambda x: x.feeder_key))
    zones_md = "\n".join(
        f"| {z.feeder or '(جزیره)'} | {z.zone_no} | {z.kind} | "
        f"{len(z.nodes):,} | {len(z.edges):,} | {z.length_m / 1000:,.2f} | "
        f"{len(z.transformer_ids):,} |"
        for z in sorted(res.zones.zones,
                        key=lambda z: (z.feeder, z.kind != "head", z.zone_no)))
    ties_md = "\n".join(
        f"| {c.feeder_a} ↔ {c.feeder_b} | {c.rule} | "
        f"{'کلید ' + c.switch_id[:8] + '…' if c.switch_id else 'بدون کلید'} | "
        f"{'بله' if c.automation_capable else 'خیر'} | {c.status} |"
        for c in res.ties) or "| — | — | — | — | — |"
    md = f"""# گزارش توپولوژی فاز ۲ — گراف، فیدرها، Tie و زون‌بندی

| مورد | مقدار |
|---|---|
| پروژه | {res.report.project} |
| اجرای مبنای ورود داده | `{run_id[:12]}…` |
| اجرای توپولوژی | `{(topo_run_id or '')[:12]}…` |
| نتیجه پذیرش | {'✅ PASS' if res.verdict == 'PASS' else '❌ FAIL'} — {res.report.verdict_reason_fa} |

## ۱. گراف و اتصال تجهیزات

| سنجه | مقدار |
|---|---|
| گره‌های گراف | {res.graph.stats['nodes']:,} |
| یال‌ها (شاخه‌های برش‌خورده در رأس تجهیزات) | {res.graph.stats['edges']:,} |
| شاخه‌های واردشده | {res.graph.stats['branches_kept']:,} (حذف‌شده excluded: {res.graph.stats['branches_skipped_excluded']:,}) |
| رأس‌های ادغام‌شده (snap همسایه) | {res.graph.stats['collapsed_vertex_pairs']:,} |
| کلید/ترانس/بار متصل | {res.graph.stats['switches_attached']:,} / {res.graph.stats['transformers_attached']:,} / {res.graph.stats['loads_attached']:,} |
| منابع متصل (ELWFWT) | {res.graph.stats['sources']} |

## ۲. بازسازی فیدرها (وضعیت عادی، TOPO-POL-01/02)

| فیدر | نام کامل GIS | گره | یال | طول (km) | ترانس | گره کلیددار | هم‌پوشانی |
|---|---|---|---|---|---|---|---|
{traces_md}

### ۲-۱. هسته قطعی فیدرها (سنجه کمکی A-09 — کلیدهای با وضعیت نامشخص = باز)

| فیدر | گره هسته | طول (km) |
|---|---|---|
""" + "\n".join(
        f"| {t.feeder_key} | {len(t.nodes):,} | {t.length_m / 1000:,.2f} |"
        for t in sorted(res.traces_strict, key=lambda x: x.feeder_key)) + f"""

> تا زمانی که نقاط NO واقعی (A-09) تأیید نشده‌اند، ردیابی عادی با عبور از
> کلیدهای نامشخص، ورود فیدرها به قلمرو یکدیگر را نشان می‌دهد (بند ۲).
> جدول بالا «هسته بدون ابهام» هر فیدر است و مبنای خوبی برای تصمیم مهندس.

## ۳. زون‌بندی (تعریف ۵-۲۱ — محدود به کلیدها)

{json.dumps(res.zones.as_dict(), ensure_ascii=False, indent=2)}

| فیدر | شماره زون | نوع | گره | یال | طول (km) | ترانس |
|---|---|---|---|---|---|---|
{zones_md}

## ۴. کاندیدهای NO/Tie (A-09 — قاعده پیشنهادی R1/R2، نیازمند تأیید مهندس)

| فیدرها | قاعده | کلید کاندید | اتوماسیون (T_ctrl_otm) | وضعیت |
|---|---|---|---|---|
{ties_md}

## ۵. سناریوی پایه و برق‌داری

```json
{json.dumps(res.connectivity.summary(), ensure_ascii=False, indent=2)}
```

## ۶. شمارش Issueهای توپولوژی

| کد | تعداد |
|---|---|
""" + "\n".join(f"| {c} | {n} |" for c, n in res.report.code_counts.most_common()) + """
"""
    (REPORTS / "phase2_topology_report.md").write_text(md, encoding="utf-8")
    payload = {
        "verdict": res.verdict,
        "verdict_reason_fa": res.report.verdict_reason_fa,
        "run_id": run_id,
        "topo_run_id": topo_run_id,
        "graph_stats": res.graph.stats,
        "traces": [t.as_dict() for t in res.traces],
        "traces_strict": [t.as_dict() for t in res.traces_strict],
        "zones": res.zones.as_dict(),
        "zone_details": [z.as_dict() for z in res.zones.zones],
        "ties": [c.as_dict() for c in res.ties],
        "connectivity": res.connectivity.summary(),
        "settings": res.settings,
        "issue_codes": dict(res.report.code_counts.most_common()),
    }
    (REPORTS / "phase2_topology_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")


def render_maps(res, net) -> None:
    MAPS.mkdir(parents=True, exist_ok=True)
    switches = {s.id: s for s in net.switches}
    renderer = NetworkMapRenderer(
        res.graph, traces=res.traces, zones=res.zones,
        switches=switches,
        tie_switch_ids={c.switch_id for c in res.ties if c.switch_id})
    renderer.render(str(MAPS / "network_overview.png"),
                    title="SwitchLoc Phase 2 - Khalkhal MV network / feeders")
    for t in sorted(res.traces, key=lambda x: x.feeder_key):
        renderer.render(str(MAPS / f"feeder_{t.feeder_key.replace(' ', '_')}.png"),
                        title=f"SwitchLoc - Feeder {t.feeder_key}",
                        feeder_filter=t.feeder_key, dpi=140)
    # zone-labelled sample map (largest feeder)
    if res.traces:
        biggest = max(res.traces, key=lambda t: len(t.edges))
        renderer.render(str(MAPS / f"zones_{biggest.feeder_key.replace(' ', '_')}.png"),
                        title=f"SwitchLoc - Zones of feeder {biggest.feeder_key}",
                        feeder_filter=biggest.feeder_key, zone_labels=True,
                        dpi=140)


def main() -> int:
    net, issues, run_id = ensure_network()
    res = TopologyService(TopologySettings(user="phase2-acceptance")).run(
        net, issues=issues, source_run_id=run_id, out_db=str(DB))
    write_report(res, run_id, res.topo_run_id)
    render_maps(res, net)

    # ---------------- acceptance checks --------------------------------
    keys = {t.feeder_key for t in res.traces}
    expected = {f"F{i}" for i in range(1, 8)}
    checks = [
        ("feeder keys F1..F7 rebuilt", expected <= keys),
        ("at least one zone per traced feeder",
         all(res.zones.zones_of_feeder(k) for k in sorted(keys))),
        ("no unresolved Error issues", res.verdict == "PASS"),
        ("topology persisted",
         res.topo_run_id is not None and DB.exists()),
        ("report + maps written",
         (REPORTS / "phase2_topology_report.md").exists()
         and (MAPS / "network_overview.png").exists()),
    ]
    print(res.report.to_markdown())
    print("\n— فیدرهای بازسازی‌شده —")
    for t in sorted(res.traces, key=lambda x: x.feeder_key):
        print(f"  {t.feeder_key:8s} nodes={len(t.nodes):6,} "
              f"edges={len(t.edges):6,} length={t.length_m / 1000:8.2f} km "
              f"transformers={len(t.transformer_ids):4,}")
    print(f"\nzones: {res.zones.as_dict()}")
    print(f"tie candidates (A-09): {len(res.ties)}")
    print(f"\ntopo_run: {res.topo_run_id}")
    print("\n— معیارهای پذیرش فاز ۲ —")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok &= passed
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
