#!/usr/bin/env python3
"""گزارش «شکاف پوشش» بانک آفلاین مکان‌های اردبیل.

مقایسهٔ بانک موجود با فهرست رسمی تقسیمات کشوری (شهر/آبادی) استان و
ساخت یک CSV قابل تکمیل: هر آبادی/شهری که در فهرست رسمی هست ولی مختصاتش
در بانک نیست، با ستون‌های خالی ``lat``/``lon`` در CSV می‌آید تا تیم
محلی آن را از GIS خود پر کند و با
``switchloc.geography.places.PlaceGazetteer.import_csv`` وارد بانک شود.

نسخهٔ رسمی مورد استفاده در مخزن (``data/geography/official_ardabil_places.csv``)
به‌صورت زیرمجموعهٔ استان اردبیل از همان منبع ساخته شده است، بنابراین گزارش
بدون دانلود دوباره هم قابل تکرار است::

    python scripts/ardabil_place_gap_report.py \\
        --official-csv data/geography/official_ardabil_places.csv \\
        --database data/geography/ardabil_places.sqlite \\
        --csv data/geography/ardabil_missing_places.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from switchloc.geography.places import (PlaceGazetteer,  # noqa: E402
                                       compact_place_name)


def _rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    csv.field_size_limit(10 ** 9)
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def official_from_csv(path: Path) -> list[dict]:
    """فهرست رسمی ذخیره‌شده در مخزن (زیرمجموعهٔ استان)."""
    return [{"name": r["name"].strip(), "kind": r.get("kind", "village"),
             "county": r.get("county", ""), "district": r.get("district", ""),
             "amar_code": r.get("amar_code", "")}
            for r in _rows(path) if r.get("name", "").strip()]


def official_places(dir_path: Path, province: str = "اردبیل") -> list[dict]:
    ostan = {r["id"]: r["name"] for r in _rows(dir_path / "ostan.csv")}
    oid = next((k for k, v in ostan.items() if v.strip() == province), None)
    if oid is None:
        raise SystemExit(f"استان «{province}» در ostan.csv پیدا نشد")
    counties = {r["id"]: r["name"] for r in _rows(dir_path / "shahrestan.csv")
                if r.get("ostan") == oid}
    districts = {r["id"]: r["name"] for r in _rows(dir_path / "dehestan.csv")
                 if r.get("ostan") == oid}
    out = []
    for r in _rows(dir_path / "abadi.csv"):
        if r.get("ostan") != oid:
            continue
        out.append({"name": r["name"].strip(), "kind": "village",
                    "county": counties.get(r.get("shahrestan", ""), ""),
                    "district": districts.get(r.get("dehestan", ""), ""),
                    "amar_code": r.get("amar_code", "")})
    for r in _rows(dir_path / "shahr.csv"):
        if r.get("ostan") != oid:
            continue
        out.append({"name": r["name"].strip(), "kind": "city",
                    "county": counties.get(r.get("shahrestan", ""), ""),
                    "district": "", "amar_code": r.get("amar_code", "")})
    return out


def build_report(database: Path, official_dir: Path | None = None,
                 province: str = "اردبیل", csv_out: Path | None = None,
                 official_csv: Path | None = None) -> dict:
    bank = PlaceGazetteer(database)
    with bank._connect() as db:                        # noqa: SLF001
        rows = db.execute("SELECT place_id, name, county, district, "
                          "place_type, lat, lon FROM places").fetchall()
    have = {compact_place_name(r["name"]) for r in rows}
    if official_csv is not None:
        official = official_from_csv(official_csv)
    else:
        official = official_places(official_dir, province)
    official_names = {compact_place_name(p["name"]) for p in official}
    missing = [p for p in official if compact_place_name(p["name"]) not in have]
    # فقط یک ردیف برای هر نام (نام‌های تکراری استان با شهرستان جدا می‌شوند)
    seen, uniq_missing = set(), []
    for p in missing:
        key = (compact_place_name(p["name"]), compact_place_name(p["county"]))
        if key in seen:
            continue
        seen.add(key)
        uniq_missing.append(p)
    villages_official = len({compact_place_name(p["name"]) for p in official
                             if p["kind"] == "village"})
    cities_official = len({compact_place_name(p["name"]) for p in official
                           if p["kind"] == "city"})
    covered_villages = len({compact_place_name(p["name"]) for p in official
                            if p["kind"] == "village"} & have)
    covered_cities = len({compact_place_name(p["name"]) for p in official
                          if p["kind"] == "city"} & have)
    extra = sorted(compact_place_name(r["name"]) for r in rows
                   if compact_place_name(r["name"]) not in official_names)
    report = {
        "database": str(database),
        "official_source": str(official_csv or official_dir),
        "bank_places": len(rows),
        "official_places": len(official),
        "official_unique_names": len(official_names),
        "coverage": {
            "villages_official": villages_official,
            "villages_covered": covered_villages,
            "villages_percent": round(
                100.0 * covered_villages / villages_official, 1)
            if villages_official else 0.0,
            "cities_official": cities_official,
            "cities_covered": covered_cities,
            "cities_percent": round(100.0 * covered_cities / cities_official, 1)
            if cities_official else 0.0,
        },
        "missing_total": len(missing),
        "missing_unique": len(uniq_missing),
        "missing_by_kind": {
            "village": sum(1 for p in missing if p["kind"] == "village"),
            "city": sum(1 for p in missing if p["kind"] == "city"),
        },
        "bank_names_not_in_official_list": len(extra),
        "csv": str(csv_out) if csv_out else None,
    }
    if csv_out:
        csv_out.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_out, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "name", "lat", "lon", "type", "county",
                             "district", "aliases"])
            for p in uniq_missing:
                writer.writerow([
                    f"official:{p['amar_code'] or compact_place_name(p['name'])}",
                    p["name"], "", "", p["kind"], p["county"], p["district"], "",
                ])
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--official-dir", type=Path,
                     help="پوشهٔ CSVهای iran-cities (ostan/shahrestan/...)")
    src.add_argument("--official-csv", type=Path,
                     help="فهرست رسمی استان که در مخزن ذخیره شده است")
    ap.add_argument("--database", type=Path,
                    default=Path("data/geography/ardabil_places.sqlite"))
    ap.add_argument("--province", default="اردبیل")
    ap.add_argument("--csv", type=Path, default=None,
                    help="مسیر CSV خروجی برای تکمیل مختصات جاهای غایب")
    ap.add_argument("--report", type=Path, default=None)
    args = ap.parse_args(argv)
    rep = build_report(args.database, args.official_dir, args.province,
                       args.csv, official_csv=args.official_csv)
    text = json.dumps(rep, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        args.report.write_text(text, encoding="utf-8")
        print(f"report → {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
