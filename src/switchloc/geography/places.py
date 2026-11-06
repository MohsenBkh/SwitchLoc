# -*- coding: utf-8 -*-
"""Offline gazetteer for Persian place names.

The database is deliberately source-attributed. Import GeoJSON point/polygon
features or CSV records; no geocoder/network call is made at analysis time.
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def normalize_place_name(value: str | None) -> str:
    s = unicodedata.normalize("NFKC", str(value or ""))
    table = str.maketrans("يك٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "یک01234567890123456789")
    s = s.translate(table).replace("ـ", "")
    s = re.sub(r"[\u064B-\u065F\u0670]", "", s)
    s = re.sub(r"[^\w\s-]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip().casefold()
    for suffix in ("روستا", "روستای", "دهستان", "شهر", "ده"):
        if s.startswith(suffix + " "):
            s = s[len(suffix):].strip()
        if s.endswith(" " + suffix):
            s = s[:-len(suffix)-1].strip()
    return s


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
                    district TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'unknown'
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
            db.execute('PRAGMA foreign_keys=ON')

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
                db.execute('''INSERT INTO places VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(place_id) DO UPDATE SET name=excluded.name,
                    normalized_name=excluded.normalized_name, lat=excluded.lat,
                    lon=excluded.lon, place_type=excluded.place_type,
                    county=excluded.county, district=excluded.district, source=excluded.source''',
                    (p.place_id, p.name, normalize_place_name(p.name), p.lat, p.lon,
                     p.place_type, p.county, p.district, p.source))
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
        """Exact/token-contained name matching; safe for operational review."""
        q = normalize_place_name(text)
        if len(q) < 2:
            return []
        with self._connect() as db:
            rows = db.execute('''SELECT p.*, p.normalized_name AS matched_name, p.name AS matched_text
                FROM places p WHERE p.normalized_name=? OR instr(?,p.normalized_name)>0
                UNION ALL
                SELECT p.*, a.normalized_alias AS matched_name, a.alias AS matched_text
                FROM aliases a JOIN places p USING(place_id)
                WHERE a.normalized_alias=? OR instr(?,a.normalized_alias)>0
                LIMIT ?''', (q, q, q, q, max(limit*4, limit))).fetchall()
        found = {}
        for r in rows:
            key = r['place_id']
            # Exact normalized name/alias is high confidence. A place name
            # merely contained in a longer operational description is only a
            # candidate, never promoted to high confidence by substring alone.
            exact = r['matched_name'] == q
            score = 1.0 if exact else min(
                0.84, len(r['matched_name']) / max(1, len(q)))
            confidence = "زیاد" if exact else "متوسط"
            p = Place(r['place_id'], r['name'], r['lat'], r['lon'], r['place_type'],
                      r['county'], r['district'], (), r['source'])
            m = PlaceMatch(p, score, r['matched_text'], confidence)
            if key not in found or m.score > found[key].score:
                found[key] = m
        return sorted(found.values(), key=lambda x: (-x.score, x.place.name))[:limit]
