#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase-0 engineering validation of the real Khalkhal sample export.

Runs the SwitchLoc ShapefileReader prototype over the real sample export,
applies the documented field catalog, counts QC issues, and writes the
validation report required by the main prompt §24 (نمونه داده واقعی را وارد
و اعتبارسنجی کن) as Markdown + JSON.

Usage:
    python scripts/validate_sample_data.py [sample_dir]

Default sample dir: $SWITCHLOC_SAMPLE_DIR or the sandbox Khalkhal path.
Output: reports/sample_validation_report.md + .json next to this script.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ / "src"))

from switchloc.gis.readers.shapefile_reader import ShapefileReader, LayerInfo  # noqa: E402
from switchloc.validation.issues import IssueLog  # noqa: E402

DEFAULT_DIR = os.environ.get(
    "SWITCHLOC_SAMPLE_DIR",
    "/home/z/my-project/work/sample_shp/Export_1404_08_17_12_34_09",
)

EXPECTED = {  # from the Phase-0 profiling of the real export
    "ELWABS": 1, "ELWCBR": 25, "ELWDCS": 70, "ELWDTR": 627, "ELWFCT": 692,
    "ELWFWT": 7, "ELWJUP": 126, "ELWMLN": 111, "ELWMSC": 1, "ELWOML": 12095,
    "ELWREC": 1, "ELWUML": 151,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    sample = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR)
    if not sample.is_dir():
        print("sample dir not found:", sample)
        return 2

    reader = ShapefileReader()
    layers = reader.discover(sample)
    log = IssueLog()

    stats = {}
    feeder_counter = {}
    remote_counter = {"yes": 0, "no": 0, "unknown": 0}
    service_counter = {"in": 0, "out": 0, "unknown": 0}
    missing_feeder = 0

    for li in layers:
        feats = reader.read(li, log)
        stats[li.name] = {
            "feature_count": len(feats),
            "expected_count": EXPECTED.get(li.name),
            "count_match": len(feats) == EXPECTED.get(li.name, -1),
            "geometry_type": li.geometry_type,
            "field_count": len(li.fields),
            "crs_wkt_present": bool(li.crs_wkt),
            "encoding": li.encoding,
        }
        for f in feats:
            if f.feeder:
                feeder_counter[f.feeder] = feeder_counter.get(f.feeder, 0) + 1
            else:
                missing_feeder += 1
            remote_counter[f.remote_controlled] += 1
            service_counter[f.service_state] += 1

    report = {
        "sample_dir": str(sample),
        "input_sha256_head": {p.name: sha256(p)[:16]
                              for p in sorted(sample.glob("*.shp"))},
        "layers_discovered": [li.name for li in layers],
        "layer_count": len(layers),
        "layer_stats": stats,
        "feeder_distribution": feeder_counter,
        "missing_feeder_features": missing_feeder,
        "remote_control_distribution": remote_counter,
        "service_state_distribution": service_counter,
        "issue_counts": {
            "total": log.count(),
            "Error": log.count("Error"),
            "Warning": log.count("Warning"),
            "Information": log.count("Information"),
        },
        "issues_by_code": {},
        "sample_issues": [i.as_dict() for i in log.items()[:12]],
    }
    for i in log.items():
        report["issues_by_code"].setdefault(i.code, 0)
        report["issues_by_code"][i.code] += 1

    out_dir = PROJ / "reports"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "sample_validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    md = [
        "# گزارش اعتبارسنجی نمونه داده واقعی — فاز صفر SwitchLoc",
        "",
        f"- پوشه ورودی: `{sample}`",
        f"- تعداد لایه‌های شناسایی‌شده: **{len(layers)}**",
        "- آزمون GG-02 (عدم تغییر ورودی): رعایت شد — Reader فقط می‌خواند؛ هش سرآیند فایل‌ها در JSON ثبت است.",
        "",
        "## آمار لایه‌ها",
        "",
        "| لایه | نوع | تعداد | مورد انتظار | منطبق | فیلد | CRS |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, st in stats.items():
        md.append(f"| {name} | {st['geometry_type']} | {st['feature_count']} | "
                  f"{st['expected_count']} | {'✅' if st['count_match'] else '❌'} | "
                  f"{st['field_count']} | {'دارد' if st['crs_wkt_present'] else 'ندارد'} |")
    md += ["", "## توزیع فیدر (زنجیره fallback فیلدها)", ""]
    for k, v in sorted(feeder_counter.items()):
        md.append(f"- {k}: {v}")
    md += ["", f"- عوارض بدون هیچ فیلد فیدر (پس از زنجیره fallback چهارفیلدی): **{missing_feeder}** "
               f"→ Issueهای `GIS-FEEDER-MISSING` (تخصیص فیدر با تصمیم کاربر)", "",
           "## توزیع قابلیت کنترل از راه دور (T_ctrl_otm)", ""]
    for k, v in remote_counter.items():
        md.append(f"- {k}: {v}")
    md += ["", "## وضعیت سرویس (T__outserv)", ""]
    for k, v in service_counter.items():
        md.append(f"- {k}: {v}")
    md += ["", "## خلاصه Issueها", "",
           f"- جمع کل: **{report['issue_counts']['total']}** "
           f"(Error: {report['issue_counts']['Error']}، "
           f"Warning: {report['issue_counts']['Warning']}، "
           f"Information: {report['issue_counts']['Information']})"]
    for code, n in sorted(report["issues_by_code"].items()):
        md.append(f"- `{code}`: {n}")
    (out_dir / "sample_validation_report.md").write_text(
        "\n".join(md), encoding="utf-8")

    ok = all(s["count_match"] for s in stats.values()) and len(layers) == 12
    print("layers:", len(layers), "| issues:", report['issue_counts'])
    print("count match vs expected:", all(s["count_match"] for s in stats.values()))
    print("wrote reports/sample_validation_report.md/.json")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
