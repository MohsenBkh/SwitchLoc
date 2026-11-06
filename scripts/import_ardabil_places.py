#!/usr/bin/env python3
"""Populate the offline Ardabil gazetteer from named GeoJSON points."""
from __future__ import annotations
import argparse
from pathlib import Path
from switchloc.geography import PlaceGazetteer


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('places_geojson', type=Path, help='GeoJSON Point features (e.g. OSM place points)')
    ap.add_argument('--boundary', required=True, type=Path, help='GeoJSON Polygon/MultiPolygon of Ardabil Province')
    ap.add_argument('--database', type=Path, default=Path('data/geography/ardabil_places.sqlite'))
    ap.add_argument('--source', default='OpenStreetMap')
    args = ap.parse_args()
    bank = PlaceGazetteer(args.database)
    n = bank.import_geojson(args.places_geojson, source=args.source,
                            boundary_geojson=args.boundary)
    print(f'Imported/updated {n} settlements; total in gazetteer: {bank.count()}')

if __name__ == '__main__':
    main()
