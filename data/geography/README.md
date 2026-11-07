# Ardabil offline gazetteer (data)

`ardabil_places.sqlite` — 1,032 places with real WGS84 coordinates, read
offline at run time. Every row carries a `source` (OSM / ODbL 1.0 for 1,006
baseline settlements, GeoNames cities1000 / CC BY 4.0 for 26 cities with
population). Official administrative names (AMAR, via the MIT-licensed
`ahmadazizi/iran-cities` dataset) are used only to validate spelling and fill
county/district — no coordinate is derived from it.

* `ardabil_boundary.geojson` — province polygon used to clip points
  (`ssepehrnoush/Iran-geojson-map-boundaries`, MIT).
* `official_ardabil_places.csv` — the official AMAR province list (1,895 rows:
  counties, districts, 1,859 villages, 36 cities) extracted from the MIT
  `ahmadazizi/iran-cities` dataset. **Names only — no coordinates**; used to
  validate spelling, pick the display form, fill county/district, and build the
  gap report without a network round-trip.
* `ardabil_missing_places.csv` — 840 officially listed places that are still
  missing coordinates (833 villages + 17 cities). `lat`/`lon` are left blank on
  purpose; fill them from an authoritative source and re-import with
  `PlaceGazetteer.import_csv`. No synthetic coordinates are ever bundled.

Regenerate with `scripts/enrich_ardabil_gazetteer.py --official-csv
data/geography/official_ardabil_places.csv ...` and
`scripts/ardabil_place_gap_report.py --official-csv ...`. Rebuilding from the
committed baseline DB reproduces the same 1,032 places and 290 aliases. Full
Persian documentation and licences: see `README_FA.md`.
