# -*- coding: utf-8 -*-
"""Polyline segmentation with registered-length distribution (test GG-03).

Provenance: the *behaviour* is documented from GeoGrid 4.2.0
`Converter._split_line_into_segments` (audit §۳-۴) — split a polyline
into 2-point pieces and distribute the registered length
(`Shape_STLe`/`T_FeatureL`) proportionally to the Euclidean vertex
distances.  Re-implemented independently; degenerate segments (both
ends the same vertex) are flagged, not silently dropped.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SegmentRow:
    a: tuple
    b: tuple
    euclid_m: float
    length_m: float            # distributed registered length
    degenerate: bool


def split_polyline(points: list[tuple[float, float]],
                   registered_length_m: float | None) -> tuple[list[SegmentRow], float]:
    """Split a polyline into 2-point segments.

    Returns (segments, geometric_length).  If `registered_length_m` is
    None/0 the geometric length is used for distribution (recorded by the
    assembler as an Information issue — an assumption, never silent).
    """
    if len(points) < 2:
        return [], 0.0
    euclids = [math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)]
    geo_len = sum(euclids)
    base = registered_length_m if (registered_length_m and registered_length_m > 0) else geo_len
    total_e = geo_len if geo_len > 0 else 1.0
    segs: list[SegmentRow] = []
    for i, e in enumerate(euclids):
        segs.append(SegmentRow(
            a=points[i], b=points[i + 1], euclid_m=e,
            length_m=base * (e / total_e) if total_e > 0 else 0.0,
            degenerate=e <= 1e-12))
    return segs, geo_len
