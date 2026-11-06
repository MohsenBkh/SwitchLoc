# -*- coding: utf-8 -*-
"""Phase-3 unit tests — outage ingestion, six-class classifier, λ/r, جدول ۱۲.

Anchors: بند ۱۰ پرامپت مادر (شش طبقه)، شکل ۵/A-11 (چهار سطح)، A-08
(محدودیت داده ۱۴۰۵)، OUT-POL-01/02، V-03 (U=λr/60 از جدول ۲۶).
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import openpyxl                                     # noqa: E402
import pytest                                       # noqa: E402

from switchloc.domain.enums import OUTAGE_CLASSES   # noqa: E402
from switchloc.level1.formulas import ZoneUP        # noqa: E402
from switchloc.reliability.classify import (        # noqa: E402
    CLASS_INSUFFICIENT, CLASS_NEEDS_REPAIR, CLASS_OUT_OF_SCOPE,
    CLASS_PLANNED, CLASS_PROTECTION_COORD, CLASS_REDUCIBLE_BY_SWITCHING,
    classify_all, classify_event, fault_type_group)
from switchloc.reliability.lambdar import (         # noqa: E402
    FeederLambdaR, feeder_lambda_r)
from switchloc.reliability.loads import (           # noqa: E402
    TABLE12_PRIORITIES, assign_priorities, feeder_priority_sums,
    resolve_category)
from switchloc.reliability.outages import (         # noqa: E402
    OutageRecord, default_feeder_mapper, parse_duration_minutes,
    parse_jalali_date, read_outage_workbook)

HEADER = ["شماره حادثه", "نام پست", "نام فيدر", "تاريخ حادثه", "زمان حادثه",
          "مدت قطع", "تاخير در وصل", "علت قطع", "قطع کننده",
          "انرژي توزيع نشده", "جريان زمان قطع", "توضيحات حادثه"]


def _row(event_no="1", feeder="1", date="1404/07/01", duration="00:30:00",
         cause="عیب گذرا", device="بریکر پست فوق توزیع", energy=1.5,
         notes=""):
    return [event_no, "پست خلخال", feeder, date, "08:00", duration,
            "00:05:00", cause, device, energy, "1.2", notes]


def _make_workbook(tmp_path, rows) -> Path:
    p = tmp_path / "outages.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "پست خلخال"
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    wb.save(p)
    return p


# ---------------------------------------------------------------------------
# reader
# ---------------------------------------------------------------------------
def test_reader_skips_empty_rows(tmp_path):
    p = _make_workbook(tmp_path, [_row(event_no="A1"), [None] * 12,
                                  [None] * 12, _row(event_no="A2")])
    recs, stats = read_outage_workbook(p)
    assert len(recs) == 2
    assert stats["rows_empty_skipped"] == 2
    assert stats["records"] == 2


def test_reader_parses_jalali_duration_energy(tmp_path):
    p = _make_workbook(tmp_path, [_row()])
    recs, _ = read_outage_workbook(p)
    r = recs[0]
    assert (r.date_j, r.year, r.month) == ("1404/07/01", 1404, 7)
    assert r.duration_min == 30.0
    assert r.restore_delay_min == 5.0
    assert r.energy_kwh == 1.5
    assert r.feeder_key == "F1" and r.in_model is True
    assert r.id                       # deterministic stable id assigned


def test_feeder_mapping_numeric_vs_out_of_model(tmp_path):
    rows = [_row(feeder="5"), _row(feeder="1كمي  آ باد"),
            _row(feeder="9")]
    p = _make_workbook(tmp_path, rows)
    recs, _ = read_outage_workbook(p)
    assert (recs[0].feeder_key, recs[0].in_model) == ("F5", True)
    # «1كمي آ باد» (leading index + free text — kamiabad-style lists)
    # maps to F1 and stays in-model; a pure number is still exact
    assert (recs[1].feeder_key, recs[1].in_model) == ("F1", True)
    # out-of-range number keeps its key for the audit trail but is NOT model
    assert (recs[2].feeder_key, recs[2].in_model) == ("F9", False)


def test_feeder_mapping_guard_against_codes(tmp_path):
    """A substation CODE (e.g. «110» inside a name) must never become a
    feeder key unless F<n> is modelled — the known-set guard."""
    rows = [_row(feeder="110"), _row(feeder="۱۲کمي"), _row(feeder="پست شماره ۳")]
    p = _make_workbook(tmp_path, rows)
    recs, _ = read_outage_workbook(p)
    assert (recs[0].feeder_key, recs[0].in_model) == ("F110", False)
    # Persian digits normalize: ۱۲ → 12 → F12, still out of the model set
    assert (recs[1].feeder_key, recs[1].in_model) == ("F12", False)
    # no leading index → unmapped
    assert (recs[2].feeder_key, recs[2].in_model) == ("", False)


def test_parse_helpers():
    assert parse_jalali_date("1405/1/2") == ("1405/01/02", 1405, 1)
    assert parse_jalali_date("") == ("", None, None)
    import datetime as dt
    assert parse_duration_minutes(dt.time(1, 1)) == 61.0
    assert parse_duration_minutes("02:05:00") == 125.0
    assert parse_duration_minutes(None) is None


# ---------------------------------------------------------------------------
# classifier — one test per mandatory class (بند ۱۰)
# ---------------------------------------------------------------------------
def _rec(**kw) -> OutageRecord:
    base = dict(sheet="پست خلخال", row_ref=2, feeder_raw="1",
                feeder_key="F1", in_model=True, date_j="1404/07/01",
                year=1404, month=7, duration_min=30.0,
                cause_raw="عیب گذرا", device_raw="بریکر پست فوق توزیع")
    base.update(kw)
    return OutageRecord(**base)


def test_class_reducible_by_switching():
    cls, rule = classify_event(_rec())
    assert cls == CLASS_REDUCIBLE_BY_SWITCHING and rule == "R-SWITCH-01"


def test_class_needs_repair():
    cls, rule = classify_event(
        _rec(cause_raw="اشکال در ترانسفورماتور", device_raw="کات اوت ترانس"))
    assert cls == CLASS_NEEDS_REPAIR and rule == "R-REP-01"


def test_class_protection_coordination():
    # dominant real cause: fuse cutout operated (downstream protective)
    cls, rule = classify_event(
        _rec(cause_raw="عملکرد یا اشکال در کات اوت فیوز",
             device_raw="کات اوت سرخط"))
    assert cls == "داده ناکافی" and rule == "R-NAK-01"


def test_class_out_of_scope():
    for cause in ("سرقت ترانسفورماتور", "اشکال در شبکه داخلی مشترکان",
                  "اشکال در لوازم اندازه گیری مشترکان دیماندی فشار متوسط"):
        cls, rule = classify_event(_rec(cause_raw=cause))
        assert cls == CLASS_OUT_OF_SCOPE and rule == "R-DOM-01", cause


def test_class_insufficient_data_a08():
    for kw in (dict(cause_raw=""), dict(feeder_raw="", feeder_key=""),
               dict(date_j="", year=None, month=None),
               dict(duration_min=None)):
        cls, rule = classify_event(_rec(**kw))
        assert cls == CLASS_INSUFFICIENT and rule == "R-NAK-01"


def test_class_planned_conservative_outpol02():
    # crew repair notes are NOT planned outages (real 1405-list pattern)
    cls, _ = classify_event(
        _rec(notes="(اضافه شده توسط اکیپ): تعویض فیوز لینگ ۱۰ آمپر"))
    assert cls == CLASS_REDUCIBLE_BY_SWITCHING
    # only explicit planned phrasing counts
    cls, rule = classify_event(_rec(notes="خاموشی برنامه‌ای برای سرویس خط"))
    assert cls == CLASS_PLANNED and rule == "R-PLAN-01"


def test_unmapped_cause_flagged():
    cls, rule = classify_event(_rec(cause_raw="علت کاملاً جدید و ناشناخته"))
    assert cls == CLASS_INSUFFICIENT and rule == "R-UNK-99"


def test_fault_type_group_level2():
    assert fault_type_group("برخورد پرندگان") == "جانداران"
    assert fault_type_group("باد و طوفان") == "شرایط جوی"
    assert fault_type_group("سرقت ترانسفورماتور") == "انسانی/خارجی"
    assert fault_type_group("اشکال در مقره (بشقابی ، سوزنی )") == \
        "تجهیز خط هوایی"
    assert fault_type_group("علت ناشناختهٔ جدید") == ""


# ---------------------------------------------------------------------------
# λ/r matrix
# ---------------------------------------------------------------------------
def test_lambda_r_v03_anchor_and_u_formula():
    # V-03 (جدول ۲۶ رسمی): λ=6.33، r=36.63 → U≈3.865 h/yr, U×P≈9.78 MWh
    zone = ZoneUP(zone="F1", lambda_per_year=6.33, r_minutes=36.63,
                  load_mw=2.53)
    row = FeederLambdaR(feeder_key="F1", lambda_per_year=6.33,
                        r_minutes=36.63)
    assert abs(row.u_hours - zone.u_hours) < 1e-9
    assert 3.86 < row.u_hours < 3.87
    assert abs(zone.ens_mwh - 9.78) < 0.02


def test_lambda_r_counts_and_zero_feeder_row():
    recs = []
    for year in (1404, 1405):                       # 2 years
        for _ in range(10):                         # 10 random events/yr
            recs.append(_rec(feeder_raw="2", feeder_key="F2",
                             year=year, month=3, duration_min=30.0))
    classify_all(recs)                              # fill outage_class first
    lam = feeder_lambda_r(recs, model_feeders=("F2", "F6"))
    d = {f.feeder_key: f for f in lam}
    assert d["F2"].events_random == 20
    assert d["F2"].years_covered == 2
    assert d["F2"].lambda_per_year == 10.0
    assert d["F2"].r_minutes == 30.0
    assert d["F2"].u_hours == 10.0 * 30.0 / 60.0
    # zero-event model feeder still present (explicit λ=0 → V-01 policy)
    assert d["F6"].events_total == 0
    assert d["F6"].lambda_per_year == 0.0


# ---------------------------------------------------------------------------
# جدول ۱۲ — load priority model
# ---------------------------------------------------------------------------
def test_table12_official_values():
    assert TABLE12_PRIORITIES == {"شهری": 2.0, "روستایی": 1.0,
                                  "کشاورزی": 1.5, "صنعتی": 1.5,
                                  "بار خاص": 4.0}
    assert resolve_category("بیمارستان") == "بار خاص"     # جدول ۸ / A-05


def test_assign_priorities_and_feeder_sums():
    from switchloc.domain.entities import (CanonicalNetwork, LoadPt, Node,
                                           Transformer)
    from switchloc.domain.enums import NodeKind
    from switchloc.validation.issues import IssueLog

    net = CanonicalNetwork(project_name="t12")
    n1 = Node(kind=NodeKind.JUNCTION, coord_original=(0, 0),
              coord_snapped=(0, 0), feeder_name="F1")
    n1.id = "n1"
    net.nodes.append(n1)
    tr = Transformer(node_id="n1", capacity_kva=100, feeder_name="F1")
    tr.id = "tr1"
    net.transformers.append(tr)
    ld1 = LoadPt(node_id="n1", transformer_id="tr1", p_kw=50.0,
                 category="شهری")
    ld1.id = "l1"
    ld2 = LoadPt(node_id="n1", transformer_id="tr1", p_kw=10.0,
                 category="درمانی")
    ld2.id = "l2"
    ld3 = LoadPt(node_id="n1", transformer_id="tr1", p_kw=5.0, category="")
    ld3.id = "l3"
    net.loads.extend([ld1, ld2, ld3])

    issues = IssueLog()
    s = assign_priorities(net, issues)
    assert ld1.priority_weight == 2.0
    assert ld2.priority_weight == 4.0                  # بار خاص (درمانی)
    assert ld3.priority_weight is None                 # هرگز حدس زده نمی‌شود
    assert s["assigned"] == 2 and s["unassigned"] == 1
    assert issues.count("Warning") == 1                # LOAD-PRI-UNASSIGNED

    sums = feeder_priority_sums(net)
    f1 = sums["F1"]
    assert f1["loads"] == 3 and f1["with_kw"] == 3
    assert abs(f1["priority_weighted_kw"] - (2.0 * 50 + 4.0 * 10)) < 1e-9
