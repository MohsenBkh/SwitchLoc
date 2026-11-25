# -*- coding: utf-8 -*-
"""Regression check: the worked v1.28.0 Help example matches the engine."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from switchloc.reliability.indices import compute_service_indices


class Event:
    def __init__(self, duration_min, energy_kwh, device_raw, feeder_key="F1"):
        self.feeder_key = feeder_key
        self.duration_min = duration_min
        self.energy_kwh = energy_kwh
        self.device_raw = device_raw
        self.in_model = True
        self.is_random = True


def test_two_event_example_matches_help_equations():
    events = [
        Event(30, 1200, "کات اوت سرخط"),  # f = 1200/(6000*0.5) = 0.4
        Event(60, None, "بریکر پست فوق توزیع"),  # whole-feeder f = 1
    ]
    result = compute_service_indices(
        events, model_feeders=["F1"], feeder_load_kw={"F1": 6000},
        lam=[{"feeder_key": "F1", "exposure_years": 2.0}],
        energy_unit="kwh", customers={"F1": 3000})
    row = result.feeders[0]

    assert row.saifi == pytest.approx(0.70)
    assert row.saidi == pytest.approx(36.0)
    assert row.caidi == pytest.approx(36.0 / 0.70)
    assert row.asai == pytest.approx(1 - 36 / 525600)
    assert row.ens_kwh_per_year == pytest.approx(600.0)
    assert row.saifi_random == pytest.approx(0.70)
    assert row.saidi_random == pytest.approx(36.0)
    assert row.worst_saifi == pytest.approx(1.0)
    assert row.worst_saidi == pytest.approx(45.0)
    assert row.customer_minutes == pytest.approx(108000.0)
    assert row.customer_interruptions == pytest.approx(2100.0)
