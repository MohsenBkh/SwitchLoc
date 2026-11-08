# Ardabil offline gazetteer (data)

`ardabil_places.sqlite` — **2,220 places** with real WGS84 coordinates, read
offline at run time. Every row carries a `source`: `Village.shp` (user-provided
2009 national settlement shapefile) for 1,188 places, OSM / ODbL 1.0 for the
1,006 baseline settlements, GeoNames `cities1000` / CC BY 4.0 for 26 cities
with population. Official administrative names (AMAR, via the MIT-licensed
`ahmadazizi/iran-cities` dataset) are used only to validate spelling and fill
county/district — no coordinate is derived from it.

| version | places | official villages covered | official cities covered |
|---|---|---|---|
| 1.13 | 1,006 | ~54 % | — |
| 1.14 | 1,032 | 57.1 % | 21 rows |
| **1.15** | **2,220** | **76.2 %** (1,348 / 1,768) | **26 / 36** |

* `ardabil_boundary.geojson` — province polygon used to clip points
  (`ssepehrnoush/Iran-geojson-map-boundaries`, MIT).
* `official_ardabil_places.csv` — the official AMAR province list (1,895 rows:
  counties, districts, 1,768 unique villages, 36 cities) extracted from the MIT
  `ahmadazizi/iran-cities` dataset. **Names only — no coordinates**; used to
  validate spelling, pick the display form, fill county/district, and build the
  gap report without a network round-trip.
* `ardabil_missing_places.csv` — **430** officially listed places that are
  still missing coordinates (420 villages + 5 real cities + 5 "Ardabil 1..5"
  municipal districts, which are not settlements). `lat`/`lon` are left blank
  on purpose; fill them from an authoritative source and re-import with
  `PlaceGazetteer.import_csv`. No synthetic coordinates are ever bundled.

`village.rar` (RAR5, user-provided) unpacks to `village/Village.shp`: a
nationwide point layer of 110,588 settlements (WGS84; DBF encoding **cp1256**;
fields `NAME, R_DSTRC, UDISTRCT, PTYPE, IAUIE, RUR03–RUR10`). 2,063 points fall
inside the province polygon; 875 merged into existing places (same compact name
within a 3,000 m radius — no duplicate rows) and 1,188 were inserted. County
came from the official name match, otherwise from a majority vote of the
shapefile's `UDISTRCT` area code (≥3 votes, ≥60 %); 186 rows kept an empty
county rather than a guess.

Regenerate with `scripts/enrich_ardabil_gazetteer.py` (GeoNames + official
list), `scripts/enrich_ardabil_village_shp.py` (Village.shp) and
`scripts/ardabil_place_gap_report.py` (coverage gap). The shapefile ingest is
idempotent: a second run inserts 0 places and merges the same 2,063 points.
Full Persian documentation, licences and matching rules: see `README_FA.md`.

**Licensing note:** the 1,188 `Village.shp` rows come from a user-supplied
archive whose provenance/licence is not yet documented — settle that before
publishing the derived database; the ingest script itself is independent of the
data.
