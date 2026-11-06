# -*- coding: utf-8 -*-
"""Tests for the OSM background module (نیاز ۵) — tile math, mosaic
assembly with a MOCKED fetcher (offline-safe) and explicit failure."""
from __future__ import annotations

import io
import math
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest                                          # noqa: E402

from switchloc.ui.osm_tiles import (                    # noqa: E402
    ATTRIBUTION, OsmUnavailableError, choose_zoom, fetch_bbox_background,
    lonlat_to_tile)


def test_tile_math_roundtrip():
    # Khalkhal ≈ lon 48.52, lat 37.62 → zone 39N
    for zoom in (9, 12, 15):
        x, y = lonlat_to_tile(48.52, 37.62, zoom)
        assert 0 <= x < 2 ** zoom and 0 <= y < 2 ** zoom
    # identical input → identical tile; higher zoom → finer tile
    a = lonlat_to_tile(48.52, 37.62, 12)
    b = lonlat_to_tile(48.52 + 0.0001, 37.62, 12)
    assert a[0] in (b[0] - 1, b[0], b[0] + 1)


def test_choose_zoom_keeps_tile_budget():
    # a ~10 km bbox must find a zoom with ≤ 24 tiles
    z = choose_zoom(48.45, 48.60, 37.55, 37.70)
    x0, y0 = lonlat_to_tile(48.45, 37.70, z)
    x1, y1 = lonlat_to_tile(48.60, 37.55, z)
    n = (abs(x1 - x0) + 1) * (abs(y1 - y0) + 1)
    assert n <= 24
    # a huge bbox falls back to the minimum zoom
    z2 = choose_zoom(44.0, 54.0, 25.0, 40.0)
    assert z2 == 9


def _fake_fetcher(calls):
    def fetch(url, timeout=8.0):
        calls.append(url)
        # a valid 256x256 opaque blue PNG — bytes, like urlopen().read()
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGBA", (256, 256), (30, 120, 200, 255)).save(buf, "PNG")
        return buf.getvalue()
    return fetch


def test_fetch_mosaic_with_mocked_tiles():
    calls = []
    bg = fetch_bbox_background(400000.0, 460000.0, 4160000.0, 4220000.0,
                               crs=32639, max_tiles=24,
                               fetch_fn=_fake_fetcher(calls))
    assert calls and all("/tile.openstreetmap.org/" in c or
                         "tile.openstreetmap.org" in c for c in calls)
    assert bg.image.shape[2] == 4                        # RGBA
    x0, x1, y0, y1 = bg.extent
    assert x1 > x0 and y1 > y0                           # project-CRS extent
    assert bg.n_tiles >= 1 and bg.n_tiles <= 24
    assert ATTRIBUTION in bg.note


def test_extent_matches_project_crs_not_rotated():
    """چرخش ۹۰° حذف شد — پس‌زمینه همیشه در همان قاب مختصات پروژه است."""
    bg = fetch_bbox_background(400000.0, 460000.0, 4160000.0, 4220000.0,
                               crs=32639, max_tiles=24,
                               fetch_fn=_fake_fetcher([]))
    x0, x1, y0, y1 = bg.extent
    # the extent stays in UTM zone-39N metres: x ~ a few 1e5, y ~ 4.2e6.
    # A rotated frame would swap them (x ≈ 4.2e6) — that must not happen.
    assert 2.0e5 < x0 < x1 < 1.0e6
    assert 4.0e6 < y0 < y1 < 4.4e6
    assert not hasattr(bg, "rotated")


def test_offline_failure_is_explicit_not_silent():
    def broken(_url, timeout=8.0):
        raise ConnectionError("no network")
    with pytest.raises(OsmUnavailableError):
        fetch_bbox_background(400000.0, 460000.0,
                              4160000.0, 4220000.0, crs=32639,
                              fetch_fn=broken)


def test_empty_extent_refused():
    with pytest.raises(OsmUnavailableError):
        fetch_bbox_background(1.0, 1.0, 0.0, 0.0, crs=32639,
                              fetch_fn=_fake_fetcher([]))
