# -*- coding: utf-8 -*-
"""Tests for the capacity model (نیاز ۹) and the plan acceptance /
no-forced-plan selection (نیاز ۱۰)."""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest                                          # noqa: E402

from switchloc.placement.acceptance import (           # noqa: E402
    ST_ACCEPTED, ST_NEEDS_CAPACITY, ST_NO_JUSTIFICATION, AcceptanceCriteria,
    PlanApprovalError, approve_plan, evaluate_scheme, select_plans)
from switchloc.placement.capacity import (             # noqa: E402
    CAP_NEEDS_CONFIRMATION, CAP_OK, CAP_VIOLATED, FeederCapacity,
    check_scheme_capacity)


class Comp:
    """جدول ۱۸ row stand-in."""
    def __init__(self, sid="s1", e2=100.0, e1=40.0, ce=2e9, cn=1.5e9, n=2):
        self.scheme_id = sid
        self.e2_before_kwh = e2
        self.e1_after_kwh = e1
        self.ce_rials = ce
        self.cn_rials = cn
        self.n_switches = n


class Switch:
    def __init__(self, node, feeder, kind):
        self.node, self.feeder, self.kind = node, feeder, kind


class Scheme:
    def __init__(self, sid, switches, feeders):
        self.id, self.switches, self.feeders = sid, switches, feeders
        self.kind = "sequential_nc"        # real SwitchScheme kind field
        self.relations = []
        self.note = ""
        self.extra = {}


# ---------------------------------------------------------------------------
# نیاز ۹ — capacity model
# ---------------------------------------------------------------------------
def test_capacity_reserve_and_status():
    cap = FeederCapacity("F1", nominal_kw=400.0, peak_kw=250.0,
                         emergency_kw=500.0)
    assert cap.reserve_kw == 150.0
    assert cap.usable_reserve_kw == 150.0
    assert cap.status == "ok" and not cap.overloaded
    d = cap.as_dict()
    assert d["reserve_kw"] == 150.0 and d["status"] == CAP_OK


def test_capacity_overload_is_visible_not_hidden():
    cap = FeederCapacity("F2", nominal_kw=200.0, peak_kw=260.0)
    assert cap.reserve_kw == -60.0
    assert cap.overloaded and cap.usable_reserve_kw == 0.0
    assert cap.status == "ok"          # داده هست؛ اضافه‌بارداری صریح گزارش می‌شود


def test_capacity_unknown_needs_confirmation():
    cap = FeederCapacity("F3")
    assert cap.status == CAP_NEEDS_CONFIRMATION
    assert cap.reserve_kw is None


def test_scheme_without_transfer_needs_no_emergency():
    scheme = Scheme("sA", [Switch("n1", "F1", "NC")], ["F1"])
    caps = {"F1": FeederCapacity("F1", 400.0, 250.0)}
    chk = check_scheme_capacity(scheme, caps, {"F1": 250.0})
    assert chk.status == CAP_OK


def test_scheme_with_transfer_and_unknown_emergency_is_blocked():
    scheme = Scheme("sB", [Switch("n1", "F1", "NO")], ["F1", "F2"])
    caps = {"F1": FeederCapacity("F1", 400.0, 250.0),   # اضطراری نامشخص
            "F2": FeederCapacity("F2", 400.0, 250.0)}
    chk = check_scheme_capacity(scheme, caps, {"F1": 250.0, "F2": 250.0})
    assert chk.status == CAP_NEEDS_CONFIRMATION
    assert chk.is_blocking
    assert any("اضطراری" in r for r in chk.reasons)


def test_relation_11_violation_is_violated():
    scheme = Scheme("sC", [Switch("n1", "F1", "NO")], ["F1", "F2"])
    # بار ۳۰۰ از ⅔×۴۰۰=۲۶۶٫۷ بیشتر → نقض رابطه ۱۱
    caps = {"F1": FeederCapacity("F1", 400.0, 300.0, emergency_kw=400.0),
            "F2": FeederCapacity("F2", 400.0, 100.0, emergency_kw=400.0)}
    chk = check_scheme_capacity(scheme, caps, {"F1": 300.0, "F2": 100.0})
    assert chk.status == CAP_VIOLATED
    assert any("رابطه (۱۱)" in r for r in chk.reasons)


# ---------------------------------------------------------------------------
# نیاز ۱۰ — acceptance criteria
# ---------------------------------------------------------------------------
def test_negative_ens_reduction_is_rejected():
    d = evaluate_scheme(Comp(e2=100.0, e1=120.0), None, AcceptanceCriteria())
    assert d.status == "rejected"
    assert any("مثبت نیست" in r for r in d.reasons)


def test_insignificant_ens_reduction_is_rejected():
    # 0.2 kWh از 100 kWh = 0.2٪ < آستانه ۱٪ و < ۱ kWh
    d = evaluate_scheme(Comp(e2=100.0, e1=99.8), None, AcceptanceCriteria())
    assert d.status == "rejected"
    assert any("معنادار" in r for r in d.reasons)


def test_negative_benefit_is_rejected():
    d = evaluate_scheme(Comp(ce=1e9, cn=1.5e9), None, AcceptanceCriteria())
    assert d.status == "rejected"
    assert any("منفعت اقتصادی" in r for r in d.reasons)


def test_capacity_pending_gives_needs_capacity_not_accept():
    d = evaluate_scheme(Comp(), None, AcceptanceCriteria())
    # capacity_check = None → کنترل‌نشده → بدون تأیید ظرفیت
    assert d.status == ST_NEEDS_CAPACITY


def test_all_criteria_pass_accepts():
    cap = FeederCapacity("F1", 400.0, 250.0, 500.0)
    chk = check_scheme_capacity(
        Scheme("s1", [Switch("n1", "F1", "NC")], ["F1"]),
        {"F1": cap}, {"F1": 250.0})
    d = evaluate_scheme(Comp(), chk, AcceptanceCriteria())
    assert d.status == ST_ACCEPTED


def test_switch_and_budget_caps():
    crit = AcceptanceCriteria(max_switches_per_scheme=1)
    d = evaluate_scheme(Comp(n=3), None, crit)
    assert d.status == ST_NEEDS_CAPACITY or d.status == "rejected"
    # ظرفیت کنترل‌شده → سقف کلید باعث رد می‌شود
    chk = check_scheme_capacity(
        Scheme("s1", [Switch("n1", "F1", "NC")], ["F1"]),
        {"F1": FeederCapacity("F1", 400.0, 250.0)}, {"F1": 250.0})
    d2 = evaluate_scheme(Comp(n=3), chk, crit)
    assert d2.status == "rejected"
    crit2 = AcceptanceCriteria(max_budget_rials=1e9)
    d3 = evaluate_scheme(Comp(cn=2e9), chk, crit2)
    assert d3.status == "rejected"


# ---------------------------------------------------------------------------
# نیاز ۱۰ — no forced plan + approval gate
# ---------------------------------------------------------------------------
def test_select_plans_no_forced_plan():
    """فیدر بدون طرح قابل قبول باید صریحاً «عدم توجیه» بگیرد، نه طرح اجباری."""
    scheme = Scheme("sX", [Switch("n1", "F1", "NC")], ["F1"])
    comps = [Comp(sid="sX")]
    decisions = {"sX": evaluate_scheme(
        comps[0],
        check_scheme_capacity(scheme,
                              {"F1": FeederCapacity("F1", 400, 250)},
                              {"F1": 250.0}),
        AcceptanceCriteria(require_positive_benefit=True))}
    comps[0].ce_rials, comps[0].cn_rials = 1e9, 3e9     # منفعت منفی
    decisions["sX"] = evaluate_scheme(
        comps[0],
        check_scheme_capacity(scheme,
                              {"F1": FeederCapacity("F1", 400, 250)},
                              {"F1": 250.0}),
        AcceptanceCriteria())
    ranking = [type("R", (), {"feeder_key": "F1", "rank": 1})()]
    plans = select_plans(comps, decisions, ranking, [scheme])
    assert plans[0]["status"] == ST_NO_JUSTIFICATION
    assert plans[0]["scheme_kind"] is None
    assert any("توجیه" in r for r in plans[0]["decision_reasons"])


def test_select_plans_picks_best_accepted():
    s1 = Scheme("sA", [Switch("n1", "F1", "NC")], ["F1"])
    s2 = Scheme("sB", [Switch("n2", "F1", "NC")], ["F1"])
    caps = {"F1": FeederCapacity("F1", 400.0, 250.0, 500.0)}
    chk1 = check_scheme_capacity(s1, caps, {"F1": 250.0})
    chk2 = check_scheme_capacity(s2, caps, {"F1": 250.0})
    c1 = Comp(sid="sA", ce=2e9, cn=1.0e9)      # CE/CN = 2
    c2 = Comp(sid="sB", ce=1.5e9, cn=1.0e9)    # CE/CN = 1.5
    dec = {"sA": evaluate_scheme(c1, chk1, AcceptanceCriteria()),
           "sB": evaluate_scheme(c2, chk2, AcceptanceCriteria())}
    ranking = [type("R", (), {"feeder_key": "F1", "rank": 1})()]
    plans = select_plans([c1, c2], dec, ranking, [s1, s2])
    assert plans[0]["status"] == ST_ACCEPTED
    assert plans[0]["scheme_id"] == "sA"       # بیشینه CE/CN


def test_approval_gate_blocks_unchecked_capacity():
    row = {"feeder_key": "F1", "status": ST_NEEDS_CAPACITY,
           "status_fa": "نیازمند تأیید ظرفیت"}
    with pytest.raises(PlanApprovalError):
        approve_plan(row, None)
    row2 = {"feeder_key": "F1", "status": ST_ACCEPTED, "status_fa": "ok",
            "switches": [{"node": "n1", "kind": "NC", "feeder": "F1"}]}
    with pytest.raises(PlanApprovalError):
        # طرح accepted اما ظرفیت فیدر کنترل نشده → تأیید نهایی ممنوع
        approve_plan(row2, {"F1": FeederCapacity("F1")})
    ok = approve_plan(row2, {"F1": FeederCapacity("F1", 400.0, 250.0)})
    assert ok["approved"] is True


def test_status_labels_are_explicit():
    from switchloc.placement.acceptance import STATUS_FA
    assert STATUS_FA[ST_NO_JUSTIFICATION] == "عدم توجیه نصب کلید"
    assert STATUS_FA[ST_NEEDS_CAPACITY] == "نیازمند تأیید ظرفیت"
    assert "تأیید" in STATUS_FA[ST_ACCEPTED]


def test_new_feeder_capacity_is_unknown_until_engineer_enters_it():
    from switchloc.ui.qt.settings_dialog import default_capacity_rows
    rows = default_capacity_rows(["F1", "F2"])
    assert [r["nominal_kw"] for r in rows] == [None, None]
    assert all(r["peak_kw"] is None and r["emergency_kw"] is None
               for r in rows)
    from switchloc.ui.qt.settings_dialog import parse_capacity_rows
    parsed = parse_capacity_rows(rows)
    assert all(r["nominal_source"] == "unknown" for r in parsed)
    from switchloc.placement.capacity import FeederCapacity
    assert all(not FeederCapacity.from_row(r).has_basic_data
               for r in parsed)
