# -*- coding: utf-8 -*-
"""Auditable zone-level U×P from explicitly confirmed event assignments."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class ZoneOutageMetric:
    zone_id: str
    load_kw: float
    outage_hours_total: float
    outage_hours_per_year: float
    up_mwh_per_year: float
    assigned_events: int
    basis: str = "confirmed-event-duration"


def calculate_zone_up(records: Iterable, event_to_zone: dict[str, str],
                      zone_load_kw: dict[str, float], exposure_years: float) -> dict[str, ZoneOutageMetric]:
    """Aggregate confirmed event durations by manually/geographically confirmed zone.

    Unassigned events are intentionally excluded (not spread across zones).
    This calculates observed assigned-zone interruption time, not the outage
    duration of every customer behind a feeder unless event impact is known.
    """
    if exposure_years <= 0:
        raise ValueError("exposure_years must be > 0")
    hours, counts = {}, {}
    for rec in records:
        if getattr(rec, "review_status", "auto") == "rejected":
            continue
        zid = event_to_zone.get(getattr(rec, "id", ""))
        dur = getattr(rec, "duration_min", None)
        if not zid or dur is None or dur < 0:
            continue
        hours[zid] = hours.get(zid, 0.0) + float(dur) / 60.0
        counts[zid] = counts.get(zid, 0) + 1
    out = {}
    for zid, load_kw in zone_load_kw.items():
        total = hours.get(zid, 0.0)
        annual = total / exposure_years
        up = (float(load_kw) / 1000.0) * annual
        out[zid] = ZoneOutageMetric(zid, float(load_kw), total, annual, up,
                                    counts.get(zid, 0))
    return out
