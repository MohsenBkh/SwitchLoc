# -*- coding: utf-8 -*-
"""v1.16 — هویت فیدر، فیدرهای هم‌شماره و ورودی بار P/Q.

سه اشکال گزارش‌شدهٔ کاربر روی دادهٔ مشگین‌شهر:

1. فیدر ۱ در فهرست فیدرها و توپولوژی دیده نمی‌شد؛ ریشه: چند نقطهٔ منبع
   (ELWFWT) به **یک** گره شینهٔ پست می‌رسیدند و نقشهٔ «گره → یک نام»
   فیدرهای بعدی را روی قبلی بازنویسی می‌کرد.
2. دو فیدر «F2 - MESHKIN» و «F2 - HADIDMOBTAKERAN» در فهرست یکی می‌شدند؛
   ریشه: شناسهٔ فیدر به «توکن کوتاه» (F2) کوتاه می‌شد.
3. در تحلیل EENS خطای «P/Q ورودی فیدرها خالی» با وجود ورود P_load/Q_load
   و محاسبه‌نشدن S_load/cosφ/K.
"""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from switchloc.domain.entities import CanonicalNetwork
from switchloc.reliability.load_model import scaling_plan
from switchloc.topology.graph import NetworkGraph
from switchloc.topology.tracing import (TracingEngine, TracingPolicy, feeder_id,
                                        feeder_key, resolve_feeder,
                                        same_feeder)
from switchloc.validation.issues import IssueLog

from conftest import NetBuilder


# ---------------------------------------------------------------------------
# ۱) هویت فیدر — نام کامل، نه توکن کوتاه
# ---------------------------------------------------------------------------
def test_feeder_id_keeps_the_full_decorated_name():
    assert feeder_id("f2 - meshkin") == "F2 - MESHKIN"
    assert feeder_id("F4- KOSAR") == "F4 - KOSAR"        # خط تیرهٔ چسبیده
    assert feeder_id("  F1  ") == "F1"
    # برخلاف feeder_key که برای مقایسهٔ کوتاه ساخته شده است
    assert feeder_key("F2 - MESHKIN") == "F2"


def test_same_feeder_bridges_short_and_decorated_but_not_two_feeders():
    assert same_feeder("F1", "F1 - MESHKIN") is True
    assert same_feeder("f1 - meshkin", "F1 - MESHKIN") is True
    assert same_feeder("F2 - MESHKIN", "F2 - HADIDMOBTAKERAN") is False
    assert same_feeder("", "F1") is False


def test_resolve_feeder_maps_only_unambiguous_names():
    cands = ["F1 - MESHKIN", "F2 - MESHKIN", "F2 - HADIDMOBTAKERAN"]
    assert resolve_feeder("f1", cands) == "F1 - MESHKIN"
    assert resolve_feeder("f1 - meshkin", cands) == "F1 - MESHKIN"
    # «F2» به دو فیدر می‌خورد → هیچ‌کدام انتخاب نمی‌شود (بدون ادغام)
    assert resolve_feeder("F2", cands) == "F2"
    assert resolve_feeder("F9", cands) == "F9"


# ---------------------------------------------------------------------------
# ۲) چند فیدر روی یک گرهٔ شینه — هیچ فیدری حذف نمی‌شود
# ---------------------------------------------------------------------------
def _two_sources_one_bus():
    b = NetBuilder()
    # دو نقطهٔ منبع با فاصلهٔ ناچیز از یک گره (همان شینهٔ پست)
    b.source(0.0, 0.0, "F1 - MESHKIN")
    b.source(0.3, 0.0, "F6 - MESHKIN")
    b.line([(0, 0), (100, 0)], feeder="F1 - MESHKIN")
    b.line([(0, 0), (0, 100)], feeder="F6 - MESHKIN")
    b.line([(0, 0), (-100, 0)], feeder="F2 - HADIDMOBTAKERAN")
    return b


def test_all_sources_on_a_shared_bus_produce_a_seed_each():
    b = _two_sources_one_bus()
    issues = IssueLog()
    g = NetworkGraph.from_network(b.net, issues)

    # هر دو منبع روی یک گره نشسته‌اند ولی هیچ‌کدام گم نمی‌شود
    assert len(g.sources_at) == 1
    assert sorted(g.sources_at[next(iter(g.sources_at))]) == [
        "F1 - MESHKIN", "F6 - MESHKIN"]
    assert g.stats["sources"] == 2 and g.stats["source_junctions"] == 1
    assert issues.by_code("TOPO-SOURCE-SHARED")     # ثبت صریح، نه سکوت

    traces = TracingEngine(g, b.net, TracingPolicy()).trace_all(issues)
    keys = sorted(t.feeder_key for t in traces)
    assert keys == ["F1 - MESHKIN", "F6 - MESHKIN"]
    by_key = {t.feeder_key: t for t in traces}
    assert len(by_key["F1 - MESHKIN"].edges) == 1
    assert len(by_key["F6 - MESHKIN"].edges) == 1


def test_two_feeders_with_the_same_number_stay_separate():
    """«F2 - MESHKIN» و «F2 - HADIDMOBTAKERAN» دو فیدرند، نه یکی."""
    b = NetBuilder()
    b.source(0, 0, "F2 - MESHKIN")
    b.source(500, 0, "F2 - HADIDMOBTAKERAN")
    b.line([(0, 0), (100, 0)], feeder="F2 - MESHKIN")
    b.line([(500, 0), (600, 0)], feeder="F2 - HADIDMOBTAKERAN")
    traces = TracingEngine(NetworkGraph.from_network(b.net, IssueLog()),
                           b.net, TracingPolicy()).trace_all(IssueLog())

    keys = sorted(t.feeder_key for t in traces)
    assert keys == ["F2 - HADIDMOBTAKERAN", "F2 - MESHKIN"]
    for t in traces:
        assert len(t.edges) == 1, "دروازهٔ برچسب باید دو فیدر هم‌شماره را جدا کند"


def test_label_gate_does_not_mix_two_feeders_sharing_a_bus():
    """شینهٔ مشترک نباید باعث شود خطوط F6 در مسیر F1 ردیابی شوند."""
    b = NetBuilder()
    b.source(0, 0, "F1 - MESHKIN")
    b.source(0.3, 0, "F6 - MESHKIN")
    b.line([(0, 0), (100, 0)], feeder="F1 - MESHKIN")
    b.line([(0, 0), (0, 100)], feeder="F6 - MESHKIN")
    traces = TracingEngine(NetworkGraph.from_network(b.net, IssueLog()),
                           b.net, TracingPolicy()).trace_all(IssueLog())

    by_key = {t.feeder_key: t for t in traces}
    assert by_key["F1 - MESHKIN"].length_m == pytest.approx(100.0)
    assert by_key["F6 - MESHKIN"].length_m == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# ۳) Load Scaling — کلیدهای قدیمی (کوتاه) هم پیدا می‌شوند
# ---------------------------------------------------------------------------
def test_scaling_plan_resolves_legacy_short_feeder_keys():
    b = NetBuilder()
    b.line([(0, 0), (100, 0)], feeder="F3 - KOSAR")
    b.transformer(100, 0, kva=1000, feeder="F3 - KOSAR")
    plan, warns = scaling_plan(b.net, {"F3": {"p_kw": 500, "q_kvar": 300}})

    row = plan["F3 - KOSAR"]
    assert row["p_kw"] == 500 and row["q_kvar"] == 300
    assert row["s_load_kva"] == pytest.approx(math.hypot(500, 300), rel=1e-6)
    assert row["cos_phi"] == pytest.approx(500 / math.hypot(500, 300), rel=1e-6)
    assert row["k_scale"] == pytest.approx(math.hypot(500, 300) / 1000.0,
                                           rel=1e-6)
    # هیچ هشدار «بدون ورودی» نباید برای این فیدر صادر شود
    assert not [w for w in warns if w[0] == "LOAD-SCALING-FEEDER-NO-INPUT"]


def test_scaling_plan_does_not_merge_two_feeders_sharing_a_number():
    net = CanonicalNetwork(project_name="two-f2")
    b = NetBuilder()
    b.line([(0, 0), (10, 0)], feeder="F2 - MESHKIN")
    b.transformer(10, 0, kva=100, feeder="F2 - MESHKIN")
    b.line([(0, 500), (10, 500)], feeder="F2 - HADIDMOBTAKERAN")
    b.transformer(10, 500, kva=200, feeder="F2 - HADIDMOBTAKERAN")
    net = b.net

    plan, warns = scaling_plan(net, {"F2": {"p_kw": 50, "q_kvar": 10}})
    # «F2» مبهم است → به هیچ‌کدام نسبت داده نمی‌شود و هر دو هشدار می‌گیرند
    assert plan["F2 - MESHKIN"]["p_kw"] == 0.0
    assert plan["F2 - HADIDMOBTAKERAN"]["p_kw"] == 0.0
    assert len([w for w in warns if w[0] == "LOAD-SCALING-FEEDER-NO-INPUT"]) == 2


# ---------------------------------------------------------------------------
# ۴) ری‌چک ورودی‌ها — P/Q، S_load، cosφ و K
# ---------------------------------------------------------------------------
def _preflight(load_model, feeders, s_rated=None):
    from switchloc.application.study_preflight import preflight_from_settings
    return preflight_from_settings(
        settings={"method": "uniform", "switch_type": "sectionalizer",
                  "total_failure_rate_per_year": 30, "repair_time_min": 50,
                  "restoration_time_min": 5, "max_sectionalizers": 2,
                  "min_candidate_depth": 1, "max_downstream_load_ratio": 0.5},
        load_model=load_model, load_total_kw=20000, feeders=list(feeders),
        all_feeders=list(feeders), s_rated_kva=s_rated or {})


def test_preflight_accepts_complete_pq_input():
    lm = {"level": "scaled",
          "feeder_pq": {"F2 - MESHKIN": {"p_kw": 12000, "q_kvar": 5000}}}
    rep = _preflight(lm, ["F2 - MESHKIN"], {"F2 - MESHKIN": 30000})

    assert not rep.blocking, [r.value + " " + r.note for r in rep.errors]
    row = next(r for r in rep.rows if r.item == "P/Q ورودی فیدرها")
    assert row.status == "ok"
    # S_load، cosφ و K باید محاسبه و نمایش داده شوند
    scale = next(r for r in rep.rows if r.item == "مقیاس فیدر «F2 - MESHKIN»")
    assert "13,000.0 kVA" in scale.value
    assert "0.9231" in scale.value
    assert "0.43333" in scale.value


def test_preflight_flags_missing_pq_per_feeder():
    lm = {"level": "scaled",
          "feeder_pq": {"F2 - MESHKIN": {"p_kw": 12000, "q_kvar": 5000}}}
    rep = _preflight(lm, ["F2 - MESHKIN", "F2 - HADIDMOBTAKERAN"])

    assert rep.blocking
    row = next(r for r in rep.rows if r.item == "P/Q ورودی فیدرها")
    assert row.status == "error" and "F2 - HADIDMOBTAKERAN" in row.note


def test_preflight_flags_empty_pq():
    rep = _preflight({"level": "scaled", "feeder_pq": {}}, ["F2 - MESHKIN"])
    row = next(r for r in rep.rows if r.item == "P/Q ورودی فیدرها")
    assert row.status == "error" and row.value == "خالی"


# ---------------------------------------------------------------------------
# ۵) پنجرهٔ تنظیمات — S_load / cosφ / K با ورود P و Q
# ---------------------------------------------------------------------------
@pytest.fixture()
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_settings_dialog_computes_s_load_cos_phi_and_k(qapp):
    from PySide6.QtWidgets import QTableWidget

    from switchloc.ui.qt.settings_dialog import make_settings_dialog

    keys = ["F2 - MESHKIN", "F2 - HADIDMOBTAKERAN"]
    cur = {"load_model": {"level": "scaled", "feeder_pq": {}},
           "capacity_rows": [], "cost_model": {}, "criteria": {},
           "coverage": {}}
    dlg = make_settings_dialog(
        None, keys, cur,
        feeder_s_rated={"F2 - MESHKIN": 30000.0,
                        "F2 - HADIDMOBTAKERAN": 20000.0})
    pq = next(t for t in dlg.findChildren(QTableWidget)
              if t.columnCount() == 7)

    pq.item(0, 1).setText("12000")
    pq.item(0, 2).setText("5000")
    qapp.processEvents()

    assert pq.item(0, 4).text() == "13,000.0"       # S_load
    assert pq.item(0, 5).text() == "0.9231"        # cos φ
    assert pq.item(0, 6).text() == "0.43333"       # K = S_load / ΣS_rated
    # ردیف دوم هنوز ورودی ندارد → نمایش «—» نه عدد ساختگی
    assert pq.item(1, 4).text() == "—"

    applied = dlg.apply()
    assert applied["load_model"]["feeder_pq"] == {
        "F2 - MESHKIN": {"p_kw": 12000.0, "q_kvar": 5000.0}}


def test_settings_dialog_repopulates_saved_values(qapp):
    """مقادیر ذخیره‌شده هنگام باز شدن پنجره دوباره محاسبه می‌شوند."""
    from PySide6.QtWidgets import QTableWidget

    from switchloc.ui.qt.settings_dialog import make_settings_dialog

    keys = ["F2 - MESHKIN"]
    cur = {"load_model": {"level": "scaled",
                          "feeder_pq": {"F2 - MESHKIN": {"p_kw": 8000,
                                                         "q_kvar": 6000}}},
           "capacity_rows": [], "cost_model": {}, "criteria": {},
           "coverage": {}}
    dlg = make_settings_dialog(None, keys, cur,
                               feeder_s_rated={"F2 - MESHKIN": 20000.0})
    pq = next(t for t in dlg.findChildren(QTableWidget)
              if t.columnCount() == 7)
    assert pq.item(0, 4).text() == "10,000.0"
    assert pq.item(0, 5).text() == "0.8000"
    assert pq.item(0, 6).text() == "0.50000"


# ---------------------------------------------------------------------------
# ۶) دادهٔ واقعی مشگین‌شهر — فهرست فیدرها از فیلد Feeder شیپ‌فایل
# ---------------------------------------------------------------------------
def test_real_export_has_two_f2_feeders_and_f1(tmp_path):
    import zipfile

    import shapefile

    src = ROOT / "MashkinshahrHaimotkaran.zip"
    if not src.is_file():
        pytest.skip("MashkinshahrHaimotkaran.zip در مخزن نیست")
    with zipfile.ZipFile(src) as zf:
        members = zf.namelist()
        wanted = ["ELWFWT", "ELWUML"]
        out = {}
        for stem in wanted:
            for ext in (".shp", ".shx", ".dbf"):
                fallback = next((m for m in members
                                 if Path(m).name == f"{stem}{ext}"), None)
                if fallback:
                    (tmp_path / f"{stem}{ext}").write_bytes(zf.read(fallback))
            reader = shapefile.Reader(str(tmp_path / stem), encoding="utf-8")
            fields = [f[0] for f in reader.fields[1:]]
            key = next(k for k in ("Feeder", "T_FeederNa", "T_feader",
                                   "T_name_fdr") if k in fields)
            out[stem] = {str(rec[key]).strip() for rec in reader.records()
                         if str(rec[key]).strip()}

    sources = out["ELWFWT"]
    assert "F1 - MESHKIN" in sources
    assert "F2 - MESHKIN" in sources and "F2 - HADIDMOBTAKERAN" in sources
    assert len(sources) == 12, sorted(sources)
    # هر دو فیدر F2 در لایهٔ خطوط هم جدا برچسب خورده‌اند
    assert {"F2 - MESHKIN", "F2 - HADIDMOBTAKERAN"} <= out["ELWUML"]
