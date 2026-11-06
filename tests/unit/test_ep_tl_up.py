# -*- coding: utf-8 -*-
"""V-02 — EP/TL anchor (جدول ۱۴/۱۵ + مثال شکل‌های ۶-۷).

Directive example: total feeder load 2500 kW; one faulted zone sheds
1800 kW → EP = 72٪; restorable via automation ties 700 kW → TL = 28٪.
"""
import pytest

from switchloc.level1 import formulas as F


def _rows():
    return [F.ZoneFaultRow("Zone0", 1800, 700)]


def test_v02_ep_tl_directive_example():
    r = F.compute_ep_tl(_rows(), total_load_kw=2500)
    assert r.ep_percent == pytest.approx(72.0)
    assert r.tl_percent == pytest.approx(28.0)
    assert r.worst_zone == "Zone0"


def test_v02_multiple_zones_take_max():
    rows = [F.ZoneFaultRow("Z0", 1800, 700),
            F.ZoneFaultRow("Z1", 600, 400),
            F.ZoneFaultRow("Z2", 300, 400)]
    r = F.compute_ep_tl(rows, 2500)
    assert r.ep_percent == pytest.approx(72.0)
    assert r.tl_percent == pytest.approx(28.0)


def test_v02_total_load_must_be_positive():
    with pytest.raises(ValueError):
        F.compute_ep_tl(_rows(), 0)


def test_v03_up_rule_directive_sample():
    """V-03 — جدول ۲۶ sample: λ=6.33, r=36.63 min, P=2.53 MW → U×P ≈ 9.78 MWh."""
    z = F.ZoneUP(zone="F1", lambda_per_year=6.33, r_minutes=36.63, load_mw=2.53)
    assert z.u_hours == pytest.approx(3.866, abs=2e-3)
    assert z.ens_mwh == pytest.approx(9.78, abs=2e-2)


def test_v03_up_rule_deviation_zero_when_equal():
    zones = [F.ZoneUP("z1", 2.0, 30, 1.0), F.ZoneUP("z2", 1.0, 30, 2.0)]
    assert F.up_rule_deviation(zones) == pytest.approx(0.0, abs=1e-12)


def test_v03_ens_total_sums_zones():
    zones = [F.ZoneUP("z1", 2.0, 30, 1.0), F.ZoneUP("z2", 1.0, 60, 0.5)]
    # z1: U=1.0h, ENS=1.0 ; z2: U=1.0h, ENS=0.5
    assert F.ens_total(zones) == pytest.approx(1.5)
