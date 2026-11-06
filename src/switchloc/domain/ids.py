# -*- coding: utf-8 -*-
"""Deterministic, reproducible entity ids (main prompt §19 reproducibility).

All internal ids are UUID-5 derived from stable, human-auditable parts
(layer, record id, slot, coordinates rounded) so that two identical study
runs produce byte-identical databases.
"""
from __future__ import annotations

import uuid

#: Fixed namespace so ids are stable across versions of the same dataset.
NAMESPACE = uuid.UUID("2f9a1d4e-6c6b-4f0e-9d20-5a11c0de0001")


def stable_id(*parts: object) -> str:
    """UUID-5 string from the given parts (None → '')."""
    key = "|".join("" if p is None else str(p) for p in parts)
    return str(uuid.uuid5(NAMESPACE, key))
