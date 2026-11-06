# -*- coding: utf-8 -*-
"""Phase-1 acceptance run: import the real Khalkhal 12-layer sample.

Produces:
  projects/khalkhal_phase1.sqlite          — deterministic project DB
  reports/phase1_import_report.md/.json    — QC report + acceptance verdict
  reports/phase1_mapping.json              — confirmed layer/field mapping

Acceptance criterion (ARCHITECTURE.md §۵ فاز ۱): 12 layers imported with
0 unresolved Error-class issues → QC verdict PASS.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from switchloc.application.import_service import ImportService, ImportSettings  # noqa: E402

SAMPLE = Path(os.environ.get(
    "SWITCHLOC_SAMPLE_DIR",
    "/home/z/my-project/work/sample_shp/Export_1404_08_17_12_34_09"))
OUT = ROOT


def main() -> int:
    db = OUT / "projects" / "khalkhal_phase1.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    settings = ImportSettings(
        project_name="خلخال — نمونه واقعی ۱۲ لایه (فاز ۱)",
        user="phase1-acceptance",
        snap_tol_m=0.5,
        out_db=str(db))
    svc = ImportService(settings)

    def confirm(suggestions, mapping, layers):
        """Explicit engineer consent for this acceptance run.

        Each suggestion is accepted only when the slot came from the
        documented layer-name catalog (high confidence); anything else
        would require a human decision and is forced to 'unmapped',
        which the assembler reports as GIS-MAPPING-UNCONFIRMED Error.
        """
        for s in suggestions:
            if s.confidence != "high":
                s.slot_key = "unmapped"
        return True

    res = svc.run(SAMPLE, confirm_fn=confirm)

    rep = res.report
    (OUT / "reports").mkdir(exist_ok=True)
    (OUT / "reports" / "phase1_import_report.md").write_text(
        rep.to_markdown(), encoding="utf-8")
    (OUT / "reports" / "phase1_import_report.json").write_text(
        __import__("json").dumps(rep.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8")
    res.mapping_service.save_json(OUT / "reports" / "phase1_mapping.json")

    print(rep.to_markdown())
    print(f"\nDB: {db}  run: {res.run_id}")
    print(f"inputs unchanged (GG-02): {res.unchanged}")
    print("\n— sample of Warning/Information codes —")
    for code, n in list(rep.code_counts.items())[:15]:
        print(f"  {code}: {n}")
    return 0 if res.accepted and res.unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
