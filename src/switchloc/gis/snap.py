# -*- coding: utf-8 -*-
"""Metric-tolerance snapping (main prompt §۵-۵; replaces GeoGrid's
decimal `round(x,3)` snap — audit §۷ decision, test GG-06).

Mechanism: single-linkage clustering of points on a uniform grid of
cell = tolerance, with neighbour-cell merging so border effects (the
documented weakness of decimal rounding) cannot split one cluster.

Outputs:
* cluster key per input point,
* cluster centroid (`coord_snapped`),
* ambiguity list (a device with 2+ cluster candidates inside tolerance).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field as dc_field


@dataclass
class SnapResult:
    point_keys: list[str]                 # cluster key per input point
    centroids: dict = dc_field(default_factory=dict)   # key → (x, y)
    members: dict = dc_field(default_factory=dict)     # key → [point idx]


def _cell(x: float, y: float, tol: float) -> tuple[int, int]:
    return (math.floor(x / tol), math.floor(y / tol))


def snap_points(points: list[tuple[float, float]], tol_m: float = 0.5
                ) -> SnapResult:
    """Single-linkage cluster of points within `tol_m` (metres).

    Pure Python (no scipy) so the offline desktop bundle stays light.
    Complexity O(n) over grid cells with 9-neighbour union passes.
    """
    if tol_m <= 0:
        raise ValueError("تلورانس snap باید مثبت باشد.")
    cells: dict[tuple[int, int], list[int]] = {}
    for i, (x, y) in enumerate(points):
        cells.setdefault(_cell(x, y, tol_m), []).append(i)

    parent = list(range(len(points)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # within-cell pairs
    for idxs in cells.values():
        for j in range(len(idxs)):
            for k in range(j + 1, len(idxs)):
                a, b = points[idxs[j]], points[idxs[k]]
                if math.dist(a, b) <= tol_m:
                    union(idxs[j], idxs[k])
    # neighbour cells (4-neighbourhood suffices for <=tol distances on a
    # grid of cell=tol: any pair within tol lies in same or adjacent cell)
    for (cx, cy), idxs in cells.items():
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            other = cells.get((cx + dx, cy + dy))
            if not other:
                continue
            for i in idxs:
                for j in other:
                    if math.dist(points[i], points[j]) <= tol_m:
                        union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(len(points)):
        groups.setdefault(find(i), []).append(i)

    keys: list[str] = [""] * len(points)
    res = SnapResult(point_keys=keys)
    for root, idxs in groups.items():
        cx = sum(points[i][0] for i in idxs) / len(idxs)
        cy = sum(points[i][1] for i in idxs) / len(idxs)
        key = f"{cx:.4f}|{cy:.4f}"
        res.centroids[key] = (cx, cy)
        res.members[key] = idxs
        for i in idxs:
            keys[i] = key
    return res


def ambiguous_device_candidates(point: tuple[float, float],
                                cluster_centroids: dict[str, tuple],
                                tol_m: float) -> list[str]:
    """All cluster centroids within tolerance of a device point (GG-05/06)."""
    out = []
    for key, (cx, cy) in cluster_centroids.items():
        if math.dist(point, (cx, cy)) <= tol_m:
            out.append(key)
    return out
