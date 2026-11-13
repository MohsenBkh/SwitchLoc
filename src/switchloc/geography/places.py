# -*- coding: utf-8 -*-
"""Offline gazetteer for Persian place names.

The database is deliberately source-attributed. Import GeoJSON point/polygon
features or CSV records; no geocoder/network call is made at analysis time.
"""
from __future__ import annotations

import csv
import json
import math
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


#: حروف هم‌ارز فارسی/عربی → شکل استاندارد (آ→ا، ة→ه، ؤ→و، ئ→ی)
_LETTER_FOLD = str.maketrans({
    "آ": "ا", "أ": "ا", "إ": "ا", "ٱ": "ا",
    "ة": "ه", "ۀ": "ه", "ؤ": "و", "ئ": "ی",
})

#: نسخهٔ کلیدهای نرمال‌شده — با تغییر قاعده، بانک قدیمی بازسازی می‌شود
KEY_SCHEMA_VERSION = "2"


def normalize_place_name(value: str | None) -> str:
    s = unicodedata.normalize("NFKC", str(value or ""))
    table = str.maketrans("يك٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "یک01234567890123456789")
    s = s.translate(table).replace("ـ", "")
    # یکسان‌سازی حروف هم‌ارز: «آ/أ/إ → ا»، «ة/ۀ → ه»، «ؤ → و»، «ئ → ی».
    # بدون این کار «فيروز اباد» هیچ‌گاه به «فیروزآباد» نمی‌رسید — همان
    # تفاوتی که در متن خاموشی‌های واقعی بیشترین سهم را دارد.
    s = s.translate(_LETTER_FOLD)
    s = re.sub(r"[\u064B-\u065F\u0670]", "", s)
    s = re.sub(r"[^\w\s-]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip().casefold()
    for suffix in ("روستا", "روستای", "دهستان", "شهر", "ده"):
        if s.startswith(suffix + " "):
            s = s[len(suffix):].strip()
        if s.endswith(" " + suffix):
            s = s[:-len(suffix)-1].strip()
    return s


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """فاصلهٔ دو نقطه روی کره (متر) — برای نزدیک‌ترین مکان."""
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def compact_place_name(value: str | None) -> str:
    """کلید «بدون فاصله» برای مقایسهٔ نام‌ها.

    «فیروزآباد»، «فیروز آباد» و «فیروزاباد» یک مکان‌اند ولی در متن
    خاموشی‌ها به هر سه شکل نوشته می‌شوند؛ مقایسهٔ فشرده این تفاوت را از
    بین می‌برد.
    """
    return _compact_of(normalize_place_name(value))


def _compact_of(normalized: str) -> str:
    return str(normalized or "").replace(" ", "").replace("-", "")


#: حروفی که در نوشتار فارسی/عربی جای هم می‌آیند (ک/ك، ی/ي/ى، ه/هٔ)
_CHAR_FOLD = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه"})

#: آستانهٔ طول نام برای تطبیق «فشرده» (کوتاه‌تر از این، نویز می‌سازد)
_MIN_COMPACT_LEN = 4


@dataclass(frozen=True)
class Place:
    place_id: str
    name: str
    lat: float
    lon: float
    place_type: str = "settlement"
    county: str = ""
    district: str = ""
    aliases: tuple[str, ...] = ()
    source: str = "unknown"
    population: int = 0


@dataclass(frozen=True)
class PlaceMatch:
    place: Place
    score: float
    matched_text: str
    confidence: str


class PlaceGazetteer:
    """SQLite-backed offline place index; names and aliases are searchable."""
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS places (
                    place_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
                    place_type TEXT NOT NULL DEFAULT 'settlement', county TEXT NOT NULL DEFAULT '',
                    district TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'unknown',
                    compact_name TEXT NOT NULL DEFAULT '', population INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS aliases (
                    place_id TEXT NOT NULL REFERENCES places(place_id) ON DELETE CASCADE,
                    alias TEXT NOT NULL, normalized_alias TEXT NOT NULL,
                    PRIMARY KEY(place_id, normalized_alias)
                );
                CREATE INDEX IF NOT EXISTS idx_places_name ON places(normalized_name);
                CREATE INDEX IF NOT EXISTS idx_alias_name ON aliases(normalized_alias);
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')
            self._migrate(db)
            db.execute('CREATE INDEX IF NOT EXISTS idx_places_compact '
                       'ON places(compact_name)')
            db.execute("CREATE INDEX IF NOT EXISTS idx_alias_compact ON aliases(replace(replace(normalized_alias,' ',''),'-',''))")

    def _migrate(self, db) -> None:
        """افزودن ستون‌های نسخهٔ ۱.۱۳ به بانک‌های قدیمی (بدون حذف داده)."""
        cols = {r["name"] for r in db.execute("PRAGMA table_info(places)")}
        if "compact_name" not in cols:
            db.execute("ALTER TABLE places ADD COLUMN compact_name "
                       "TEXT NOT NULL DEFAULT ''")
        if "population" not in cols:
            db.execute("ALTER TABLE places ADD COLUMN population "
                       "INTEGER NOT NULL DEFAULT 0")
        current = db.execute(
            "SELECT value FROM metadata WHERE key='key_schema'").fetchone()
        needs_rebuild = (current is None
                         or str(current["value"]) != KEY_SCHEMA_VERSION)
        if needs_rebuild:
            # قاعدهٔ نرمال‌سازی عوض شده است؛ همهٔ نام‌ها از نو ساخته می‌شوند
            rows = db.execute(
                "SELECT place_id, name FROM places").fetchall()
            db.executemany(
                "UPDATE places SET normalized_name=?, compact_name=? "
                "WHERE place_id=?",
                [(normalize_place_name(r["name"]),
                  _compact_of(normalize_place_name(r["name"])), r["place_id"])
                 for r in rows])
            aliases = db.execute(
                "SELECT place_id, alias FROM aliases").fetchall()
            db.execute("DELETE FROM aliases")
            db.executemany(
                "INSERT OR IGNORE INTO aliases(place_id, alias, normalized_alias)"
                " VALUES(?,?,?)",
                [(r["place_id"], r["alias"],
                  normalize_place_name(r["alias"])) for r in aliases])
            db.execute("INSERT INTO metadata(key, value) VALUES('key_schema', ?)"
                       " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (KEY_SCHEMA_VERSION,))
        else:
            rows = db.execute("SELECT place_id, normalized_name FROM places "
                              "WHERE compact_name=''").fetchall()
            if rows:
                db.executemany(
                    "UPDATE places SET compact_name=? WHERE place_id=?",
                    [(_compact_of(r["normalized_name"]), r["place_id"])
                     for r in rows])

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def count(self) -> int:
        with self._connect() as db:
            return int(db.execute('SELECT COUNT(*) FROM places').fetchone()[0])

    def upsert(self, places: Iterable[Place]) -> int:
        count = 0
        with self._connect() as db:
            for p in places:
                if not p.name or not (-90 <= p.lat <= 90 and -180 <= p.lon <= 180):
                    continue
                normalized = normalize_place_name(p.name)
                db.execute('''INSERT INTO places(place_id, name, normalized_name,
                        lat, lon, place_type, county, district, source,
                        compact_name, population)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(place_id) DO UPDATE SET name=excluded.name,
                    normalized_name=excluded.normalized_name, lat=excluded.lat,
                    lon=excluded.lon, place_type=excluded.place_type,
                    county=excluded.county, district=excluded.district,
                    source=excluded.source, compact_name=excluded.compact_name,
                    population=excluded.population''',
                    (p.place_id, p.name, normalized, p.lat, p.lon,
                     p.place_type, p.county, p.district, p.source,
                     _compact_of(normalized), int(p.population or 0)))
                db.execute('DELETE FROM aliases WHERE place_id=?', (p.place_id,))
                for a in p.aliases:
                    n = normalize_place_name(a)
                    if n and n != normalize_place_name(p.name):
                        db.execute('INSERT OR IGNORE INTO aliases VALUES(?,?,?)', (p.place_id, a, n))
                count += 1
        return count

    def import_csv(self, path: str | Path, source: str = "user-import") -> int:
        """CSV columns: id,name,lat,lon[,type,county,district,aliases]."""
        rows = []
        with open(path, encoding="utf-8-sig", newline="") as f:
            for i, r in enumerate(csv.DictReader(f), 1):
                aliases = tuple(x.strip() for x in re.split(r"[|;،]", r.get("aliases", "")) if x.strip())
                try:
                    rows.append(Place(r.get("id") or f"csv:{i}", r["name"], float(r["lat"]),
                                      float(r["lon"]), r.get("type") or "settlement",
                                      r.get("county") or "", r.get("district") or "", aliases, source))
                except (KeyError, TypeError, ValueError):
                    continue
        return self.upsert(rows)

    def import_geojson(self, path: str | Path, source: str = "OpenStreetMap",
                       boundary_geojson: str | Path | None = None) -> int:
        """Import named Point features; optionally clip by an admin boundary GeoJSON."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        polygons = []
        if boundary_geojson:
            boundary = json.loads(Path(boundary_geojson).read_text(encoding="utf-8"))
            bfeatures = boundary.get("features", []) if boundary.get("type") == "FeatureCollection" else [boundary]
            for bf in bfeatures:
                geom = bf.get("geometry") or {}
                if geom.get("type") == "Polygon":
                    polygons.extend(geom.get("coordinates", [])[:1])
                elif geom.get("type") == "MultiPolygon":
                    for poly in geom.get("coordinates", []):
                        polygons.extend(poly[:1])
        def inside(lon, lat, ring):
            hit = False
            j = len(ring) - 1
            for i, (xi, yi, *_) in enumerate(ring):
                xj, yj = ring[j][:2]
                if ((yi > lat) != (yj > lat)) and lon < (xj-xi)*(lat-yi)/(yj-yi or 1e-30)+xi:
                    hit = not hit
                j = i
            return hit
        def in_boundary(lon, lat):
            return not polygons or any(inside(lon, lat, ring) for ring in polygons)
        features = data.get("features", []) if data.get("type") == "FeatureCollection" else [data]
        places = []
        for i, ft in enumerate(features):
            geom, prop = ft.get("geometry") or {}, ft.get("properties") or {}
            if geom.get("type") != "Point":
                continue
            coords = geom.get("coordinates") or []
            name = prop.get("name:fa") or prop.get("name") or prop.get("name:en")
            if not name or len(coords) < 2:
                continue
            if not in_boundary(float(coords[0]), float(coords[1])):
                continue
            aliases = []
            for k, v in prop.items():
                if k.startswith("alt_name") or k.startswith("name:"):
                    if isinstance(v, str) and v != name:
                        aliases.append(v)
            pid = str(ft.get("id") or prop.get("osm_id") or f"geojson:{i}")
            places.append(Place(pid, str(name), float(coords[1]), float(coords[0]),
                                str(prop.get("place") or prop.get("type") or "settlement"),
                                str(prop.get("county") or prop.get("addr:county") or ""),
                                str(prop.get("district") or ""), tuple(aliases), source))
        return self.upsert(places)

    def search(self, text: str, limit: int = 8) -> list[PlaceMatch]:
        """جست‌وجوی نام مکان: دقیق، «فشرده» (فاصله‌ناپذیر) و واژه‌ای.

        قاعده‌ها (برای بازبینی عملیاتی امن):

        * تطبیق **دقیق** نام یا نام جایگزین → اطمینان «زیاد».
        * تطبیق **فشرده** (با/بی‌فاصله و آ/ا) → همان مکان، «زیاد».
        * تطبیق **واژه‌ای**: نام باید به‌صورت واژهٔ کامل (با فاصله در دو
          طرف) در متن بیاید؛ زیررشتهٔ یک واژهٔ دیگر پذیرفته نمی‌شود
          (باگ قبلی: «سالن ورزشی زرج‌آباد» به مکان «رز» تطبیق می‌شد).
        * تطبیق فشرده‌ی جزئی فقط برای نام‌های ≥۴ حرف و با اطمینان «متوسط».
        """
        q = normalize_place_name(text)
        if len(q) < 2:
            return []
        q_compact = _compact_of(q)
        padded = f" {q} "
        # همهٔ «بازه‌های واژگانی» متن: تطبیق فشرده فقط روی همین‌ها مجاز است
        # تا نامی که از میانهٔ یک واژه شروع می‌شود پذیرفته نشود
        # (باگ: «امير اباد» به «میراب» تطبیق می‌شد).
        tokens = q.split()
        spans = set()
        for i in range(len(tokens)):
            for j in range(i + 1, len(tokens) + 1):
                spans.add(_compact_of(" ".join(tokens[i:j])))
        # Search indexed whole-token spans instead of scanning every place and
        # alias for every outage. All candidates are still scored below.
        names = {" ".join(tokens[i:j]) for i in range(len(tokens))
                 for j in range(i + 1, len(tokens) + 1)}
        compact = {_compact_of(n) for n in names if len(_compact_of(n)) >= _MIN_COMPACT_LEN}
        names.add(q)
        compact.add(q_compact)
        rows = []
        with self._connect() as db:
            for values, sql in (
                (names, "SELECT p.*, p.normalized_name AS matched_name, p.name AS matched_text FROM places p WHERE p.normalized_name IN ({})"),
                (compact, "SELECT p.*, p.normalized_name AS matched_name, p.name AS matched_text FROM places p WHERE p.compact_name IN ({})"),
                (names, "SELECT p.*, a.normalized_alias AS matched_name, a.alias AS matched_text FROM aliases a JOIN places p USING(place_id) WHERE a.normalized_alias IN ({})"),
                (compact, "SELECT p.*, a.normalized_alias AS matched_name, a.alias AS matched_text FROM aliases a JOIN places p USING(place_id) WHERE replace(replace(a.normalized_alias,' ',''),'-','') IN ({})"),
            ):
                values = sorted(values)
                for start in range(0, len(values), 400):
                    batch = values[start:start + 400]
                    rows.extend(db.execute(sql.format(",".join("?" for _ in batch)), batch).fetchall())
        found = {}
        for r in rows:
            matched = r['matched_name'] or ""
            matched_compact = _compact_of(matched)
            if matched == q:
                score, confidence = 1.0, "زیاد"
            elif matched_compact and matched_compact == q_compact:
                # تفاوت فقط در فاصله/آ-ا: همان مکان
                score, confidence = 0.97, "زیاد"
            elif f" {matched} " in padded:
                # واژهٔ کامل داخل متن؛ هرچه سهم بیشتری از متن را بگیرد
                # محتمل‌تر است (سقف ۰٫۸۴ تا با تطبیق دقیق اشتباه نشود)
                share = len(matched_compact) / max(1, len(q_compact))
                score, confidence = min(0.84, 0.45 + 0.39 * share), "متوسط"
            elif (len(matched_compact) >= _MIN_COMPACT_LEN
                  and matched_compact in spans):
                # تفاوت فقط در فاصله/آ-ا بوده است (بازهٔ واژگانی کامل)
                share = len(matched_compact) / max(1, len(q_compact))
                score, confidence = min(0.8, 0.4 + 0.4 * share), "متوسط"
            else:                                    # pragma: no cover
                continue
            p = Place(r['place_id'], r['name'], r['lat'], r['lon'],
                      r['place_type'], r['county'], r['district'], (),
                      r['source'], int(r['population'] or 0))
            m = PlaceMatch(p, score, r['matched_text'], confidence)
            key = r['place_id']
            if key not in found or m.score > found[key].score:
                found[key] = m
        return sorted(found.values(),
                      key=lambda x: (-x.score, -x.place.population,
                                     x.place.name))[:limit]

    # ------------------------------------------------------------------
    def add_aliases(self, place_id: str, aliases: Iterable[str]) -> int:
        """افزودن نام‌های جایگزین به یک مکان (بدون حذف نام‌های موجود)."""
        added = 0
        with self._connect() as db:
            row = db.execute("SELECT name FROM places WHERE place_id=?",
                             (place_id,)).fetchone()
            if row is None:
                return 0
            base = normalize_place_name(row["name"])
            for alias in aliases:
                text = str(alias or "").strip()
                normalized = normalize_place_name(text)
                if not normalized or normalized == base:
                    continue
                cur = db.execute(
                    "INSERT OR IGNORE INTO aliases(place_id, alias, normalized_alias)"
                    " VALUES(?,?,?)", (place_id, text, normalized))
                added += int(cur.rowcount or 0)
        return added

    def find_near(self, lat: float, lon: float,
                  max_distance_m: float = 2000.0,
                  name: str | None = None) -> list[tuple[Place, float]]:
        """مکان‌های نزدیک یک نقطه (مرتب بر اساس فاصله) — برای یکسان‌سازی."""
        key = compact_place_name(name) if name else ""
        out = []
        with self._connect() as db:
            for r in db.execute("SELECT * FROM places").fetchall():
                d = _haversine_m(lat, lon, r["lat"], r["lon"])
                if d <= max_distance_m and (not key
                                            or r["compact_name"] == key):
                    out.append((Place(r["place_id"], r["name"], r["lat"],
                                      r["lon"], r["place_type"], r["county"],
                                      r["district"], (), r["source"],
                                      int(r["population"] or 0)), d))
        return sorted(out, key=lambda x: x[1])

    def nearby_county(self, lat: float, lon: float,
                      max_distance_m: float = 40000.0) -> str:
        """نام شهرستان از نزدیک‌ترین مکانِ دارای شهرستان (برای داده‌های تازه)."""
        best, best_d = "", None
        with self._connect() as db:
            for r in db.execute("SELECT lat, lon, county FROM places "
                                "WHERE county<>''").fetchall():
                d = _haversine_m(lat, lon, r["lat"], r["lon"])
                if (best_d is None or d < best_d) and d <= max_distance_m:
                    best, best_d = r["county"], d
        return best

    def set_metadata(self, values: dict) -> None:
        with self._connect() as db:
            for key, value in (values or {}).items():
                db.execute("INSERT INTO metadata(key, value) VALUES(?,?) "
                           "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                           (str(key), str(value)))

    def metadata(self) -> dict:
        with self._connect() as db:
            return {r["key"]: r["value"]
                    for r in db.execute("SELECT key, value FROM metadata")}

    def stats(self) -> dict:
        """خلاصهٔ بانک برای گزارش/رابط (تعداد بر نوع، منبع و شهرستان)."""
        with self._connect() as db:
            by_type = {r[0]: r[1] for r in db.execute(
                "SELECT place_type, COUNT(*) FROM places GROUP BY place_type")}
            by_source = {r[0]: r[1] for r in db.execute(
                "SELECT source, COUNT(*) FROM places GROUP BY source")}
            by_county = {r[0] or "(بدون شهرستان)": r[1] for r in db.execute(
                "SELECT county, COUNT(*) FROM places GROUP BY county")}
            aliases = db.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
            with_pop = db.execute(
                "SELECT COUNT(*) FROM places WHERE population>0").fetchone()[0]
        return {"places": self.count(), "aliases": aliases,
                "with_population": with_pop, "by_type": by_type,
                "by_source": by_source, "by_county": by_county,
                "metadata": self.metadata()}
