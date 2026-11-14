#!/usr/bin/env python3
"""غنی‌سازی بانک آفلاین اردبیل از فایل برداری «village» (کاربر).

منبع: ``village.rar`` — یک Shapefile نقطه‌ای از آبادی‌های کشور
(``Village.shp`` با کدگذاری CP1256، WGS84، ۱۱۰٬۵۸۸ نقطه در کل ایران).

این اسکریپت:

1. نقاط را با چندضلعی استان اردبیل کلیپ می‌کند؛
2. برای هر نقطه، اگر مکانی با **همان نام فشرده** در شعاع ۳ کیلومتر در بانک
   باشد آن را «ادغام» می‌کند (همان آبادی، نه رکورد دوم) و نام دیگر را به
   عنوان ``alias`` ثبت می‌کند؛
3. در غیر این صورت مکان تازه با مختصات واقعی همان نقطه اضافه می‌کند؛
4. شهرستان/دهستان را از فهرست رسمی تقسیمات کشوری (``official_ardabil_places.csv``)
   و در صورت نبود، از کد ناحیهٔ همان فایل (اکثریتِ نام‌های شناخته‌شدهٔ همان
   کد) پر می‌کند — **بدون حدس**: هر جا نتیجه روشن نباشد خالی می‌ماند؛
5. منبع هر رکورد را در ستون ``source`` می‌نویسد.

هیچ مختصاتی ساخته یا درون‌یابی نمی‌شود؛ همه از همان Shapefile می‌آید.

نمونهٔ اجرا::

    python scripts/enrich_ardabil_village_shp.py \\
        --shp /path/to/village/Village.shp \\
        --database data/geography/ardabil_places.sqlite \\
        --report /tmp/village_enrich.json
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from switchloc.geography.places import (Place, PlaceGazetteer,  # noqa: E402
                                       compact_place_name)

SOURCE = ("Village.shp — بانک آبادی‌های کشور (۲۰۰۹، ورودی کاربر)")
#: فاصلهٔ یکسان‌انگاری: نام یکسان در این شعاع = همان آبادی
MERGE_RADIUS_M = 3000.0


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def load_official(path: Path) -> tuple[dict, dict]:
    """(نام فشرده → [(شهرستان، دهستان، نوع)]) و (کد ناحیه → نام) — بدون کد ناحیه."""
    by_name: dict[str, list[dict]] = defaultdict(list)
    if not path.is_file():
        return {}, {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            by_name[compact_place_name(name)].append({
                "name": name, "kind": row.get("kind") or "village",
                "county": row.get("county", ""),
                "district": row.get("district", "")})
    return dict(by_name), {}


def read_points(shp: Path, rings) -> list[dict]:
    """نقاط داخل استان (نام، مختصات، کد ناحیه)."""
    import shapefile                                  # pyshp
    from enrich_ardabil_gazetteer import point_in_rings

    points: list[dict] = []
    reader = shapefile.Reader(str(shp), encoding="cp1256")
    for sr in reader.iterShapeRecords():
        if not sr.shape.points:
            continue
        x, y = sr.shape.points[0]
        if not point_in_rings(x, y, rings):
            continue
        rec = sr.record.as_dict()
        name = str(rec.get("NAME") or "").strip()
        if not name:
            continue
        points.append({
            "name": name, "lat": float(y), "lon": float(x),
            "area_code": str(rec.get("UDISTRCT") or ""),
            "rural_code": str(rec.get("R_DSTRC") or ""),
        })
    return points


def build_area_counties(points, official_by_name) -> dict[str, str]:
    """کد ناحیه → نام شهرستان (اکثریت نام‌های شناخته‌شدهٔ همان کد)."""
    votes: dict[str, Counter] = defaultdict(Counter)
    for p in points:
        hits = official_by_name.get(compact_place_name(p["name"])) or []
        counties = {h["county"] for h in hits if h["county"]}
        if len(counties) == 1:
            votes[p["area_code"]][counties.pop()] += 1
    out: dict[str, str] = {}
    for code, counter in votes.items():
        if not counter:
            continue
        (name, n), = counter.most_common(1)
        total = sum(counter.values())
        if total >= 3 and n / total >= 0.6:      # اکثریت روشن، وگرنه خالی
            out[code] = name
    return out


def enrich(database: Path, shp: Path, boundary: Path,
           official_csv: Path | None, dry_run: bool = False) -> dict:
    from enrich_ardabil_gazetteer import load_boundary_rings

    rings = load_boundary_rings(boundary)
    points = read_points(shp, rings)
    official_by_name, _ = load_official(official_csv) if official_csv else ({}, {})
    area_counties = build_area_counties(points, official_by_name)

    bank = PlaceGazetteer(database)
    with bank._connect() as db:                        # noqa: SLF001
        rows = db.execute("SELECT place_id, name, lat, lon, county, district, "
                          "place_type FROM places").fetchall()
    existing = [{"place_id": r["place_id"], "name": r["name"],
                 "lat": float(r["lat"]), "lon": float(r["lon"]),
                 "county": r["county"], "district": r["district"],
                 "compact": compact_place_name(r["name"])} for r in rows]
    by_compact: dict[str, list[dict]] = defaultdict(list)
    for e in existing:
        by_compact[e["compact"]].append(e)

    new_places: list[Place] = []
    aliases: list[tuple[str, list[str]]] = []
    merged = 0
    skipped_same = 0
    added_by_name: set[str] = set()

    for p in sorted(points, key=lambda q: (q["name"], q["lat"])):
        cname = compact_place_name(p["name"])
        if not cname:
            continue
        hits = official_by_name.get(cname) or []
        county = (hits[0]["county"] if len({h["county"] for h in hits}) == 1
                  else area_counties.get(p["area_code"], ""))
        district = (hits[0]["district"] if len({h["district"] for h in hits}) == 1
                    else "")
        kind = ("city" if any(h["kind"] == "city" for h in hits)
                else "village")
        candidates = by_compact.get(cname, [])
        best = None
        for e in candidates:
            d = haversine_m(p["lat"], p["lon"], e["lat"], e["lon"])
            if best is None or d < best[0]:
                best = (d, e)
        if best and best[0] <= MERGE_RADIUS_M:
            e = best[1]
            if p["name"] != e["name"]:
                aliases.append((e["place_id"], [p["name"]]))
            merged += 1
            continue
        key = (cname, round(p["lat"], 3), round(p["lon"], 3))
        if key in added_by_name:
            skipped_same += 1
            continue
        added_by_name.add(key)
        pid = f"village:{p['area_code']}:{cname}:{round(p['lat'], 4)}:{round(p['lon'], 4)}"
        new_places.append(Place(
            place_id=pid, name=p["name"], lat=p["lat"], lon=p["lon"],
            place_type=kind, county=county, district=district, source=SOURCE))
        by_compact.setdefault(cname, []).append(
            {"place_id": pid, "name": p["name"], "lat": p["lat"],
             "lon": p["lon"], "county": county, "district": district,
             "compact": cname})

    aliases_added = 0
    if not dry_run:
        if new_places:
            bank.upsert(new_places)
        for pid, names in aliases:
            aliases_added += int(bank.add_aliases(pid, names))
        stats = bank.stats()
        meta = bank.metadata()
        # منابع از خودِ بانک خوانده می‌شوند (همیشه با واقعیت منطبق است)
        sources = sorted(stats.get("by_source") or {})
        try:
            previous_added = int(str(meta.get("village_shp_added", "0")) or 0)
        except ValueError:
            previous_added = 0
        from_source = int((stats.get("by_source") or {}).get(SOURCE, 0))
        bank.set_metadata({
            "sources": "; ".join(sources),
            "village_shp_places": str(from_source),
            "village_shp_added": str(max(from_source, previous_added)),
            "village_shp_merged": str(merged),
            "places_after": str(stats.get("places")),
            "aliases_after": str(stats.get("aliases")),
            "village_shp_built_at": __import__("datetime").datetime.now()
            .isoformat(timespec="seconds"),
        })
    else:
        stats = {"places": bank.count() + len(new_places)}

    return {
        "database": str(database),
        "dry_run": dry_run,
        "points_inside_province": len(points),
        "merged_into_existing": merged,
        "added": len(new_places),
        "skipped_duplicates": skipped_same,
        "aliases_added": (aliases_added if not dry_run
                          else sum(len(a) for _, a in aliases)),
        "placed_with_county": sum(1 for p in new_places if p.county),
        "placed_with_district": sum(1 for p in new_places if p.district),
        "area_codes_mapped": len(area_counties),
        "places_after": stats.get("places"),
        "source": SOURCE,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shp", required=True, type=Path,
                    help="مسیر Village.shp (کنار .dbf/.shx)")
    ap.add_argument("--boundary", type=Path,
                    default=Path("data/geography/ardabil_boundary.geojson"))
    ap.add_argument("--official-csv", type=Path,
                    default=Path("data/geography/official_ardabil_places.csv"))
    ap.add_argument("--database", type=Path,
                    default=Path("data/geography/ardabil_places.sqlite"))
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    rep = enrich(args.database, args.shp, args.boundary, args.official_csv,
                 dry_run=args.dry_run)
    text = json.dumps(rep, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        args.report.write_text(text, encoding="utf-8")
        print(f"report → {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
