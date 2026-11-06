# -*- coding: utf-8 -*-
"""OpenStreetMap raster background (نیاز ۵ — فعال/غیرفعال، زیر شبکه).

Behaviour:
  * the caller gives the CURRENT view bbox in the project CRS (UTM
    metres, e.g. EPSG:32639) — this module converts the
    bbox to WGS84 lon/lat with pyproj, picks a Web-Mercator tile zoom
    that keeps the tile count small (≤ 24 tiles), downloads the tiles
    and reprojects the mosaic corners back into the project CRS.
  * the returned ``(image, extent, note)`` is drawn by the map canvas
    with ``imshow(..., zorder=0)`` UNDER the network layer.
  * OFFLINE-safe: every failure raises ``OsmUnavailableError`` and the
    UI degrades to the plain network map with an explicit message —
    a missing basemap never breaks the study.

Attribution: «© OpenStreetMap contributors» is mandatory per the OSM
Tile Usage Policy and is returned as ``note`` (drawn on the map).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
ATTRIBUTION = "(c) OpenStreetMap contributors"
USER_AGENT = "SwitchLoc/1.5 (TAV122-02/00 switching-study tool; contact: planner)"
MAX_TILES = 24
_MIN_ZOOM, _MAX_ZOOM = 9, 18


class OsmUnavailableError(RuntimeError):
    """پس‌زمینه OSM در دسترس نیست (آفلاین/فیلترینگ/خطای شبکه) — صریح."""


@dataclass
class OsmBackground:
    """OSM mosaic ready for ``imshow`` in the project CRS."""
    image: object                     # (H, W, 4) uint8 RGBA numpy array
    extent: tuple                     # (x0, x1, y0, y1) in the project CRS
    note: str = ATTRIBUTION
    zoom: int = 0
    n_tiles: int = 0
    # (the old rotated() helper is gone — the 90° rotation was removed on
    #  user feedback; the raster now always lives in the raw project frame)


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """WGS84 (lon, lat) → Web-Mercator tile indices (slippy map)."""
    n = 2 ** zoom
    lat = max(-85.05112878, min(85.05112878, lat))
    xt = (lon + 180.0) / 360.0 * n
    yt = (1.0 - math.log(math.tan(math.radians(lat))
                         + 1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n
    return int(xt), int(yt)


def choose_zoom(lon_min: float, lon_max: float,
                lat_min: float, lat_max: float,
                max_tiles: int = MAX_TILES) -> int:
    """Highest zoom whose bbox tile count stays within ``max_tiles``."""
    for z in range(_MAX_ZOOM, _MIN_ZOOM - 1, -1):
        x0, y0 = lonlat_to_tile(lon_min, lat_max, z)
        x1, y1 = lonlat_to_tile(lon_max, lat_min, z)
        n = (abs(x1 - x0) + 1) * (abs(y1 - y0) + 1)
        if n <= max_tiles:
            return z
    return _MIN_ZOOM


def _fetch(url: str, timeout: float = 8.0) -> bytes:
    """Download helper — isolated for tests (mock target)."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_bbox_background(x0: float, x1: float, y0: float, y1: float,
                          crs: str | int | None = None,
                          max_tiles: int = MAX_TILES,
                          fetch_fn=None) -> OsmBackground:
    """OSM mosaic of the bbox (project CRS metres) → OsmBackground.

    Raises ``OsmUnavailableError`` on ANY failure (network, decoding,
    pyproj) — the caller shows a message and continues without tiles.
    """
    if crs is None or str(crs).strip() == "":
        # never assume a site default — a wrong CRS puts the tiles in the
        # wrong country; the project must declare its own CRS
        raise OsmUnavailableError(
            "the project has no declared CRS — OSM background needs it")
    try:
        from pyproj import Transformer
        import numpy as np
        from PIL import Image                              # noqa: F401
        import io
    except ImportError as exc:                             # pragma: no cover
        raise OsmUnavailableError(f"dependency missing: {exc}") from exc

    lox, hix = sorted((float(x0), float(x1)))
    loy, hiy = sorted((float(y0), float(y1)))
    if hix - lox <= 0 or hiy - loy <= 0:
        raise OsmUnavailableError("empty view extent")

    tf = Transformer.from_crs(crs, 4326, always_xy=True)
    lon_a, lat_a = tf.transform(lox, loy)
    lon_b, lat_b = tf.transform(hix, hiy)
    lon_min, lon_max = sorted((lon_a, lon_b))
    lat_min, lat_max = sorted((lat_a, lat_b))
    if not all(math.isfinite(v) for v in (lon_min, lon_max, lat_min, lat_max)):
        raise OsmUnavailableError("bbox is not transformable to WGS84")

    zoom = choose_zoom(lon_min, lon_max, lat_min, lat_max, max_tiles)
    tx0, ty0 = lonlat_to_tile(lon_min, lat_max, zoom)
    tx1, ty1 = lonlat_to_tile(lon_max, lat_min, zoom)
    xs = sorted((tx0, tx1))
    ys = sorted((ty0, ty1))
    nx, ny = xs[1] - xs[0] + 1, ys[1] - ys[0] + 1
    if nx * ny > max_tiles:
        raise OsmUnavailableError(
            f"tile count {nx * ny} exceeds the limit {max_tiles}")

    get = fetch_fn or _fetch
    tile_w = tile_h = 256
    mosaic = np.zeros((ny * tile_h, nx * tile_w, 4), dtype=np.uint8)
    got = 0
    for ty in range(ys[0], ys[1] + 1):
        for tx in range(xs[0], xs[1] + 1):
            url = TILE_URL.format(z=zoom, x=tx, y=ty)
            try:
                raw = get(url)
                img = Image.open(io.BytesIO(raw)).convert("RGBA")
                if img.size != (tile_w, tile_h):
                    img = img.resize((tile_w, tile_h))
            except Exception as exc:
                raise OsmUnavailableError(
                    f"tile {zoom}/{tx}/{ty} failed: {exc}") from exc
            r, c = ty - ys[0], tx - xs[0]
            mosaic[r * tile_h:(r + 1) * tile_h,
                   c * tile_w:(c + 1) * tile_w] = np.asarray(img)
            got += 1
    if got == 0:
        raise OsmUnavailableError("no tile could be downloaded")

    # pixel corners of the mosaic → mercator metres → project CRS
    # merc_x = (tile_x / n − 0.5) · 2πR  — the old code subtracted 2πR
    # instead of πR, which threw the raster ~10 000 km away from the
    # network (the user-visible «OSM does not match the feeder map» bug)
    n = 2.0 ** zoom
    merc_x0 = (xs[0] / n - 0.5) * 2.0 * math.pi * 6378137.0
    merc_x1 = ((xs[1] + 1) / n - 0.5) * 2.0 * math.pi * 6378137.0

    def merc_y(tile_y: int) -> float:
        return math.pi * 6378137.0 * (1.0 - 2.0 * tile_y / n)

    inv = Transformer.from_crs(3857, crs, always_xy=True)
    corners = []
    for mx, my in ((merc_x0, merc_y(ys[1] + 1)), (merc_x1, merc_y(ys[0]))):
        corners.append(inv.transform(mx, my))
    px0, py0 = corners[0]
    px1, py1 = corners[1]
    # extent in the PROJECT CRS: (x0, x1, y0, y1) — imshow convention
    return OsmBackground(image=mosaic,
                         extent=(min(px0, px1), max(px0, px1),
                                 min(py0, py1), max(py0, py1)),
                         note=ATTRIBUTION, zoom=zoom, n_tiles=got)
