from types import SimpleNamespace
import pytest
from switchloc.reliability.zone_outages import calculate_zone_up


def test_confirmed_zone_outage_up_calculation():
    recs = [SimpleNamespace(id='a', duration_min=120, review_status='confirmed'),
            SimpleNamespace(id='b', duration_min=60, review_status='auto'),
            SimpleNamespace(id='c', duration_min=900, review_status='rejected')]
    m = calculate_zone_up(recs, {'a':'Z1','b':'Z1','c':'Z1'}, {'Z1':2000}, 2.0)['Z1']
    assert m.outage_hours_total == pytest.approx(3.0)
    assert m.outage_hours_per_year == pytest.approx(1.5)
    assert m.up_mwh_per_year == pytest.approx(3.0)
    assert m.assigned_events == 2


def test_unassigned_event_is_not_spread_to_zones():
    rec = SimpleNamespace(id='a', duration_min=60, review_status='confirmed')
    m = calculate_zone_up([rec], {}, {'Z1':1000}, 1)['Z1']
    assert m.up_mwh_per_year == 0
    assert m.assigned_events == 0


def test_exposure_must_be_positive():
    with pytest.raises(ValueError):
        calculate_zone_up([], {}, {}, 0)
