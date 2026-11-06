# -*- coding: utf-8 -*-
"""V-01 — normalization anchor from the directive's own worked example.

TAV122-02/00 بند ۷-۷-۵ (گام ۶، صفحه ۳۳ متن رسمی) prints the worked
example: connection counts 2, 0, 4, 1 → 0.085, 0.021, 0.851, 0.043.
⚠ Phase-1 image check of the official page shows this printed pair is
internally REVERSED (RTL typesetting): Norm(2,0,4,1) = 0.043, 0.851,
0.021, 0.085 — exactly the printed outputs reversed; the printed
outputs match inputs (1,4,0,2).  The RULE (Norm = Xi/ΣXi with inverse
zero = 10) is unambiguous; this test pins the self-consistent ordering
(1, 2, 0, 4 → 0.085, 0.043, 0.851, 0.021) also recorded by the HTML
راهنمای اجرایی.  See docs/TAV122_TRACEABILITY.md §۶.

Phase 1: the official PDF CONFIRMED the zero→10 policy verbatim, so the
default policy is 'confirmed'.  The Phase-0 'pending' lock remains
available as an explicit argument and is regression-tested here.
"""
import pytest

from switchloc.level1 import formulas as F


def test_v01_example_with_directive_zero_policy():
    vals = F.normalize([1, 2, 0, 4], inverse=True,
                       inverse_zero_policy="value", inverse_zero_value=10.0)
    assert vals == pytest.approx([0.085, 0.043, 0.851, 0.021], abs=5e-4)


def test_v01_confirmed_policy_is_now_default():
    # A-02 resolved: «معکوس مقادیر صفر برابر با مقدار 10 در نظر گرفته شود»
    # (بند ۷-۷-۵ صفحه ۳۳ PDF رسمی) — the default must reproduce V-01.
    vals = F.normalize([1, 2, 0, 4], inverse=True)
    assert vals == pytest.approx([0.085, 0.043, 0.851, 0.021], abs=5e-4)
    assert F.OFFICIAL_CONFIRMATIONS["inverse_zero"]["status"] == "confirmed"


def test_v01_pending_lock_still_available_explicitly():
    with pytest.raises(ValueError, match="CALC-POLICY-PENDING|تأیید"):
        F.normalize([1, 2, 0, 4], inverse=True, inverse_zero_policy="pending")


def test_v01_plain_normalization():
    assert F.normalize([2, 2, 4]) == pytest.approx([0.25, 0.25, 0.5])


def test_v01_zero_total_rejected():
    with pytest.raises(ValueError):
        F.normalize([0, 0])


def test_table16_weights_shape():
    # جدول ۱۶ (تأیید PDF رسمی): six criteria with weights (1,2,2,3,1,1)
    scored = F.score_feeders([(0.5, 0.1, 0.3, 0.2, 0.01, 30),
                              (0.2, 0.4, 0.6, 0.5, 0.02, 45)])
    assert scored[0]["rank"] + scored[1]["rank"] == 3  # ranks 1 and 2


def test_table16_weights_officially_confirmed():
    assert F.FEEDER_RANKING_WEIGHTS == [1, 2, 2, 3, 1, 1]
    assert F.OFFICIAL_CONFIRMATIONS["table16_weights"]["weights"] == [1, 2, 2, 3, 1, 1]
    assert F.OFFICIAL_CONFIRMATIONS["table12_priorities"]["values_fa"] == {
        "شهری": 2, "روستایی": 1, "کشاورزی": 1.5, "صنعتی": 1.5, "بار خاص": 4}
