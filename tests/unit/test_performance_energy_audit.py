import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from types import SimpleNamespace

from switchloc.gis.snap import CentroidIndex, ambiguous_device_candidates
from switchloc.reliability.indices import compute_service_indices
from switchloc.reliability.outages import OutageRecord


def test_centroid_index_exact_and_ordered():
    rng = random.Random(47)
    centroids = {str(i): (rng.uniform(-10, 10), rng.uniform(-10, 10)) for i in range(500)}
    centroids.update({"tie1": (0, 0), "tie2": (0.5, 0)})
    index = CentroidIndex(centroids, 0.5)
    for point in [(0, 0), (-0.5, 0), (0.5, 0)] + [(rng.uniform(-10, 10), rng.uniform(-10, 10)) for _ in range(300)]:
        assert index.candidates(point) == ambiguous_device_candidates(point, centroids, 0.5)


def test_energy_audit_independent_of_service_fraction():
    r = OutageRecord(sheet='s', row_ref=2, feeder_key='F1', in_model=True,
                     energy_kwh=12.5, duration_min=None, device_raw='فیوز')
    res = compute_service_indices([r], model_feeders=['F1'],
                                  lam=[SimpleNamespace(feeder_key='F1', exposure_years=2)],
                                  energy_unit='mwh')
    row = res.feeders[0]
    assert row.events_counted == 0
    assert row.energy_records == 1
    assert row.energy_raw_total == 12.5
    assert row.ens_kwh_per_year == 6250
    assert res.energy_unit_source == 'declared'


def test_map_panel_hides_both_layers():
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication
    from switchloc.ui.qt.map_canvas import make_map_canvas

    app = QApplication.instance() or QApplication([])
    tab = make_map_canvas()
    try:
        tab.show()
        app.processEvents()
        assert tab.switch_panel.isVisible() and tab.outage_panel.isVisible()
        tab.btn_switch_panel.click()
        assert not tab.switch_panel.isVisible() and not tab.outage_panel.isVisible()
        tab.btn_switch_panel.click()
        assert tab.switch_panel.isVisible() and tab.outage_panel.isVisible()
    finally:
        tab.close()
        app.processEvents()
