# -*- coding: utf-8 -*-
"""Import the supplied named substation GIS layers into the offline gazetteer.

Usage: python scripts/import_postzaminhava.py <directory> <gazetteer.sqlite>
Original shapefiles are read only. Polygon coordinates use the extent centre,
not a survey-grade location; each entry retains its layer and feature ID.
"""
from pathlib import Path
import sys
import shapefile
from pyproj import CRS, Transformer
from switchloc.geography.places import Place, PlaceGazetteer


def load_places(directory):
    for layer in ("ELWADS", "ELWGDS"):
        paths = list(Path(directory).rglob(layer + ".shp"))
        if len(paths) != 1:
            raise ValueError(f"Expected one {layer}.shp, found {len(paths)}")
        path = paths[0]
        crs = CRS.from_wkt(path.with_suffix('.prj').read_text(encoding='utf-8'))
        tr = Transformer.from_crs(crs, 'EPSG:4326', always_xy=True)
        reader = shapefile.Reader(str(path), encoding='utf-8', encodingErrors='replace')
        for feature in reader.iterShapeRecords():
            data = feature.record.as_dict()
            name = str(data.get('Name') or data.get('Label') or '').strip()
            ident = str(data.get('GlobalID') or data.get('OBJECTID') or '').strip()
            points = feature.shape.points
            if not name or not ident or not points or '\ufffd' in name:
                continue
            if len(points) == 1:
                x, y = points[0][:2]
            else:
                box = feature.shape.bbox
                x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            lon, lat = tr.transform(x, y)
            aliases = []
            for prefix in ('پست ', 'پست  '):
                if name.startswith(prefix) and len(name[len(prefix):].strip()) >= 4:
                    aliases.append(name[len(prefix):].strip())
            yield Place(f'post:{layer}:{ident}', name, lat, lon,
                        place_type='substation', aliases=tuple(aliases),
                        source=f'postzaminhava:{layer}')


if __name__ == '__main__':
    bank = PlaceGazetteer(sys.argv[2])
    places = list(load_places(sys.argv[1]))
    print('imported', bank.upsert(places), 'named substations')
