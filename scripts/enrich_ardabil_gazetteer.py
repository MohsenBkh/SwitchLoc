#!/usr/bin/env python3
"""غنی‌سازی بانک آفلاین مکان‌های استان اردبیل.

منابع (همه آفلاین و دارای مجوز/انتساب):

* **GeoNames** — فایل ``cities1000.json`` بستهٔ ``geonamescache`` (نسخهٔ
  دادهٔ GeoNames، مجوز CC BY 4.0). شهرها/شهرستان‌ها و سکونتگاه‌های
  بزرگ‌تر از ۱۰۰۰ نفر + نام‌های جایگزین فارسی/لاتین.
* **مرز استان اردبیل** — GeoJSON از مخزن
  ``ssepehrnoush/Iran-geojson-map-boundaries`` (MIT، مبتنی بر OSM).
  فقط نقاط داخل مرز وارد می‌شوند.
* **بانک موجود** — ۱٬۰۰۶ سکونتگاه OSM؛ نام‌های موجود حفظ می‌شوند و
  برای همهٔ آن‌ها گونه‌های نوشتاری (آ/ا، ک/ك، ی/ي) به‌عنوان alias
  ساخته می‌شود.

خروجی: همان فایل ``ardabil_places.sqlite`` (به‌روزرسانی در جا، بدون
حذف داده) + متادیتای ساخت (تاریخ، منابع، شمارش‌ها) برای ردیابی.

نمونهٔ اجرا::

    python scripts/enrich_ardabil_gazetteer.py \\
        --geonames /tmp/gnc/geonamescache/data/cities1000.json \\
        --boundary data/geography/ardabil_boundary.geojson \\
        --database data/geography/ardabil_places.sqlite --report /tmp/enrich.json
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from switchloc.geography.places import (Place, PlaceGazetteer,  # noqa: E402
                                       compact_place_name)

PERSIAN = re.compile(r"[\u0600-\u06FF]")
ARABIC_STYLE = re.compile(r"[يك]")          # نشانهٔ نوشتار عربی
DIACRITICS = re.compile(r"[\u064B-\u0652\u0670]")
ADMIN_PREFIX = ("شهرستان", "بخش", "دهستان", "استان")

GEONAMES_SOURCE = "GeoNames cities1000 (CC BY 4.0)"
OSM_SOURCE_MARK = "high-confidence"
OFFICIAL_SOURCE = "AMAR official divisions (ahmadazizi/iran-cities v3, MIT)"


def _csv_rows(path: Path) -> list[dict]:
    if not Path(path).is_file():
        return []
    csv.field_size_limit(10 ** 9)
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_official(dir_path: Path, province: str = "اردبیل") -> dict:
    """تقسیمات کشوری رسمی استان (شهر/آبادی + شهرستان + دهستان).

    منبع: مخزن ``ahmadazizi/iran-cities`` نسخهٔ ۳ (MIT) که از فایل‌های
    مرکز آمار ساخته شده است. خروجی برای «اعتبارسنجی نام» و «تکمیل
    شهرستان/دهستان» استفاده می‌شود؛ مختصات ندارد.
    """
    def rows(name: str) -> list[dict]:
        path = dir_path / name
        if not path.is_file():
            return []
        csv.field_size_limit(10 ** 9)
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    ostan = {r["id"]: r["name"] for r in rows("ostan.csv")}
    oid = next((k for k, v in ostan.items() if v.strip() == province), None)
    if oid is None:
        return {"province_id": None, "by_name": {}, "villages": 0,
                "cities": 0, "counties": [], "enabled": False}
    counties = {r["id"]: r["name"] for r in rows("shahrestan.csv")
                if r.get("ostan") == oid}
    dehestans = {r["id"]: r["name"] for r in rows("dehestan.csv")
                 if r.get("ostan") == oid}
    by_name: dict[str, list[dict]] = {}
    n_village = n_city = 0
    for r in rows("abadi.csv"):
        if r.get("ostan") != oid:
            continue
        n_village += 1
        key = compact_place_name(r["name"])
        by_name.setdefault(key, []).append({
            "name": r["name"], "kind": "village",
            "county": counties.get(r.get("shahrestan", ""), ""),
            "district": dehestans.get(r.get("dehestan", ""), "")})
    for r in rows("shahr.csv"):
        if r.get("ostan") != oid:
            continue
        n_city += 1
        key = compact_place_name(r["name"])
        by_name.setdefault(key, []).append({
            "name": r["name"], "kind": "city",
            "county": counties.get(r.get("shahrestan", ""), ""),
            "district": ""})
    return {"province_id": oid, "by_name": by_name, "villages": n_village,
            "cities": n_city, "counties": sorted(counties.values()),
            "enabled": bool(by_name)}


def load_official_csv(path: Path) -> dict:
    """همان ساختار ``load_official`` از فهرست رسمی ذخیره‌شده در مخزن."""
    by_name: dict[str, list[dict]] = {}
    n_village = n_city = 0
    counties: set[str] = set()
    for r in _csv_rows(path):
        name = (r.get("name") or "").strip()
        if not name:
            continue
        kind = r.get("kind") or "village"
        n_village += kind == "village"
        n_city += kind == "city"
        counties.add(r.get("county", ""))
        by_name.setdefault(compact_place_name(name), []).append({
            "name": name, "kind": kind, "county": r.get("county", ""),
            "district": r.get("district", "")})
    return {"province_id": "csv", "by_name": by_name, "villages": n_village,
            "cities": n_city, "counties": sorted(c for c in counties if c),
            "enabled": bool(by_name)}


# --------------------------------------------------------------------------
def load_boundary_rings(path: Path) -> list[list[tuple[float, float]]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    feats = (data.get("features") if data.get("type") == "FeatureCollection"
             else [data]) or []
    rings: list[list[tuple[float, float]]] = []
    for ft in feats:
        geom = (ft or {}).get("geometry") or {}
        gtype = geom.get("type")
        if gtype == "Polygon":
            polys = [geom.get("coordinates") or []]
        elif gtype == "MultiPolygon":
            polys = geom.get("coordinates") or []
        else:
            continue
        for poly in polys:
            if poly:
                rings.append([(float(p[0]), float(p[1])) for p in poly[0]])
    return rings


def point_in_rings(lon: float, lat: float,
                   rings: list[list[tuple[float, float]]]) -> bool:
    for ring in rings:
        hit, j = False, len(ring) - 1
        for i, (xi, yi) in enumerate(ring):
            xj, yj = ring[j]
            if ((yi > lat) != (yj > lat)) and lon < ((xj - xi) * (lat - yi)
                                                     / ((yj - yi) or 1e-30) + xi):
                hit = not hit
            j = i
        if hit:
            return True
    return not rings


def persian_name(entry: dict, official: dict | None = None) -> tuple[str, list[str]]:
    """انتخاب نام فارسی و فهرست نام‌های جایگزین از یک رکورد GeoNames.

    اگر تقسیمات رسمی در دسترس باشد، نامی انتخاب می‌شود که **در فهرست
    رسمی استان هست** (مثلاً «پارس آباد» به‌جای «فارس آباد»).
    """
    alts = [str(a).strip() for a in (entry.get("alternatenames") or [])
            if str(a).strip()]
    fa = [a for a in alts if PERSIAN.search(a)]
    plain = [a for a in fa if not a.startswith(ADMIN_PREFIX)]
    pool = plain or fa
    if not pool:
        return "", alts
    names = (official or {}).get("by_name") or {}
    official_hits = [a for a in pool if compact_place_name(a) in names]
    if official_hits:
        # شکل نمایشی = همان املای رسمی تقسیمات کشوری (ی/ک فارسی، بی‌اعراب)
        rows = names[compact_place_name(official_hits[0])]
        city_row = next((h for h in rows if h["kind"] == "city"), None)
        chosen = (city_row or rows[0])["name"].strip()
        return chosen, [a for a in alts if a != chosen]

    def rank(name: str):
        return (len(ARABIC_STYLE.findall(name)),      # نوشتار فارسی مقدم
                len(DIACRITICS.findall(name)),        # بدون اعراب
                name.startswith(ADMIN_PREFIX),        # نه «شهرستان …»
                len(name))

    chosen = sorted(pool, key=rank)[0]
    aliases = [a for a in alts if a != chosen]
    return chosen, aliases


def place_type_for(population: int) -> str:
    if population >= 5000:
        return "city"
    if population >= 1000:
        return "town"
    return "village"


# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geonames", required=True, type=Path,
                    help="cities1000.json از بستهٔ geonamescache")
    ap.add_argument("--boundary", required=True, type=Path,
                    help="GeoJSON مرز استان (Polygon/MultiPolygon)")
    ap.add_argument("--database", type=Path,
                    default=Path("data/geography/ardabil_places.sqlite"))
    ap.add_argument("--country", default="IR", help="کد کشور GeoNames")
    ap.add_argument("--min-population", type=int, default=0)
    ap.add_argument("--merge-distance-m", type=float, default=1500.0,
                    help="فاصلهٔ یکسان‌سازی مکان تکراری (متر)")
    ap.add_argument("--county-radius-m", type=float, default=40000.0)
    ap.add_argument("--official-csv", type=Path, default=None,
                    help="فهرست رسمی استان ذخیره‌شده در مخزن "
                         "(data/geography/official_ardabil_places.csv)")
    ap.add_argument("--official-dir", type=Path, default=None,
                    help="پوشهٔ CSV تقسیمات رسمی (ostan/shahrestan/dehestan/"
                         "shahr/abadi) — برای اعتبارسنجی نام و تکمیل دهستان")
    ap.add_argument("--province", default="اردبیل")
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    rings = load_boundary_rings(args.boundary)
    if args.official_csv:
        official = load_official_csv(args.official_csv)
    elif args.official_dir:
        official = load_official(args.official_dir, args.province)
    else:
        official = {"enabled": False, "by_name": {}}
    if official.get("enabled"):
        print(f"تقسیمات رسمی: {official['cities']} شهر، "
              f"{official['villages']} آبادی، {len(official['counties'])} شهرستان")
    data = json.loads(Path(args.geonames).read_text(encoding="utf-8"))
    entries = data.values() if isinstance(data, dict) else data

    inside = []
    for e in entries:
        if str(e.get("countrycode") or "").upper() != args.country.upper():
            continue
        lat, lon = float(e.get("latitude") or 0), float(e.get("longitude") or 0)
        if not point_in_rings(lon, lat, rings):
            continue
        if int(e.get("population") or 0) < args.min_population:
            continue
        name, aliases = persian_name(e, official)
        if not name:
            continue
        inside.append((e, name, aliases))

    if not args.database.is_file():
        print(f"ERROR: بانک مکان یافت نشد: {args.database}")
        return 2
    bank = PlaceGazetteer(args.database)
    before = bank.stats()

    added, merged = [], []
    for e, name, aliases in inside:
        lat, lon = float(e["latitude"]), float(e["longitude"])
        population = int(e.get("population") or 0)
        variants = list(aliases)
        near = bank.find_near(lat, lon, args.merge_distance_m,
                              name=name)
        if near:
            existing, distance = near[0]
            merged.append({"geonames": e.get("name"), "name": name,
                           "into": existing.name,
                           "place_id": existing.place_id,
                           "distance_m": round(distance, 1)})
            if not args.dry_run:
                bank.add_aliases(existing.place_id, variants)
            continue
        county = bank.nearby_county(lat, lon, args.county_radius_m)
        place = Place(
            place_id=f"geonames:{e.get('geonameid') or compact_place_name(name)}",
            name=name, lat=lat, lon=lon,
            place_type=place_type_for(population),
            county=county, district="", aliases=tuple(variants),
            source=GEONAMES_SOURCE, population=population)
        added.append({"geonameid": e.get("geonameid"), "name": name,
                      "latin": e.get("name"), "population": population,
                      "type": place.place_type, "county": county,
                      "lat": lat, "lon": lon,
                      "aliases": len(variants)})
        if not args.dry_run:
            bank.upsert([place])

    # ---- تکمیل شهرستان/دهستان و نام رسمی از تقسیمات کشوری --------------
    official_filled = {"district": 0, "county": 0, "city_type": 0}
    coverage = {"official_cities": official.get("cities", 0),
                "official_villages": official.get("villages", 0),
                "bank_cities_matched": 0, "bank_places_matched": 0}
    if official.get("enabled") and not args.dry_run:
        names = official["by_name"]
        with bank._connect() as db:                     # noqa: SLF001
            rows = db.execute("SELECT place_id, name, county, district, "
                              "place_type FROM places").fetchall()
        for r in rows:
            key = compact_place_name(r["name"])
            hits = names.get(key) or []
            if not hits:
                continue
            coverage["bank_places_matched"] += 1
            city_hit = next((h for h in hits if h["kind"] == "city"), None)
            if city_hit:
                coverage["bank_cities_matched"] += 1
            # ابهام‌زدایی با شهرستانِ ثبت‌شدهٔ همان مکان؛ اگر باز هم چند
            # گزینه بماند، دهستان پر نمی‌شود (حدس نزنیم).
            same_county = [
                h for h in hits
                if r["county"] and compact_place_name(h["county"])
                == compact_place_name(r["county"])]
            pool = same_county or hits
            districts = {compact_place_name(h["district"]) for h in pool}
            unique = pool[0] if len(pool) == 1 or len(districts) == 1 else None
            updates = []
            if unique:
                if not (r["district"] or "").strip() and unique["district"]:
                    updates.append(("district", unique["district"]))
                if not (r["county"] or "").strip() and unique["county"]:
                    updates.append(("county", unique["county"]))
            if city_hit and r["place_type"] != "city":
                updates.append(("place_type", "city"))
            for column, value in updates:
                with bank._connect() as db:             # noqa: SLF001
                    db.execute(f"UPDATE places SET {column}=? WHERE place_id=?",
                               (value, r["place_id"]))
                if column == "district":
                    official_filled["district"] += 1
                elif column == "county":
                    official_filled["county"] += 1
                elif column == "place_type":
                    official_filled["city_type"] += 1
            with bank._connect() as db:                 # noqa: SLF001
                for hit in hits:
                    bank.add_aliases(r["place_id"], [hit["name"]])

    after = bank.stats()
    if not args.dry_run:
        bank.set_metadata({
            "built_at": dt.datetime.now().isoformat(timespec="seconds"),
            "province": "استان اردبیل",
            "population_status": "official-name-validated",
            "coordinate_crs": "EPSG:4326",
            "sources": "; ".join([OSM_SOURCE_MARK, GEONAMES_SOURCE]),
            "boundary_source": "ssepehrnoush/Iran-geojson-map-boundaries (MIT, OSM)",
            "geonames_inside": len(inside),
            "geonames_added": len(added),
            "geonames_merged": len(merged),
            "places_after": after["places"],
            "aliases_after": after["aliases"],
            "official_source": OFFICIAL_SOURCE if official.get("enabled") else "",
            "official_coverage": json.dumps(coverage, ensure_ascii=False),
            "license": "OSM/ODbL + GeoNames/CC BY 4.0 + iran-cities/MIT "
                       "(انتساب الزامی است)",
        })

    report = {
        "database": str(args.database),
        "dry_run": bool(args.dry_run),
        "geonames_inside_boundary": len(inside),
        "added": len(added),
        "merged": len(merged),
        "official_enabled": bool(official.get("enabled")),
        "official_filled": official_filled,
        "coverage": coverage,
        "places_before": before["places"], "places_after": after["places"],
        "aliases_before": before["aliases"], "aliases_after": after["aliases"],
        "by_type_after": after["by_type"],
        "by_source_after": after["by_source"],
        "added_sample": added[:15],
        "merged_sample": merged[:15],
    }
    print(json.dumps({k: v for k, v in report.items()
                      if not k.endswith("_sample")}, ensure_ascii=False, indent=2))
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        print(f"report → {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
