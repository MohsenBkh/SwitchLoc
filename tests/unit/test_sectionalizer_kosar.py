# -*- coding: utf-8 -*-
"""آزمون پذیرش روش جایابی بهینهٔ کلید روی شبکهٔ واقعی کوثر.

شبکهٔ واقعی: ``Kosar GIS.sqlite`` (۵ فیدر F3/F4/F5/F6/F7، ۷٬۷۹۹ گره،
۸٬۰۸۹ خط). آزمون‌ها **فقط‌خواندنی** هستند: پروژه با ``persist=False``
اجرا می‌شود و هیچ ردیفی در پایگاه نوشته نمی‌شود.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from switchloc.application.sectionalizer_service import (
    KV_KEY, SectionalizerAppSettings, SectionalizerService)
from switchloc.application.topology_service import (TopologyService,
                                                   TopologySettings)
from switchloc.persistence.store import ProjectStore
from switchloc.reliability.load_model import LoadModelSettings, build_node_loads
from switchloc.reliability.sectionalizer import (SectionalizerEngine,
                                                 SectionalizerSettings)

DB = Path(__file__).resolve().parents[2] / "Kosar GIS.sqlite"

pytestmark = pytest.mark.skipif(
    not DB.is_file(), reason="پروژهٔ واقعی کوثر (Kosar GIS.sqlite) موجود نیست")


@pytest.fixture(scope="module")
def kosar():
    store = ProjectStore(str(DB))
    try:
        runs = store.runs()
        net, issues = store.load_network(runs[-1]["id"])
        lambda_rows = store.load_outages()["lambda_r"]
        kv_keys_before = sorted(
            {r[0] for r in store.conn.execute("SELECT key FROM project_kv")})
    finally:
        store.close()
    topo = TopologyService(TopologySettings(persist=False)).run(net, issues=issues)
    lm = build_node_loads(topo.graph, net, LoadModelSettings(level="estimated"))
    rates = {r["feeder_key"]: float(r["lambda_per_year"]) for r in lambda_rows
             if r.get("lambda_per_year") is not None}
    return {"net": net, "topo": topo, "node_load": dict(lm.node_kw),
            "rates": rates, "kv_keys_before": kv_keys_before}


def _study(kosar, **kwargs):
    settings = SectionalizerSettings(max_sectionalizers=3, **kwargs)
    return SectionalizerEngine(settings).run(
        kosar["topo"].graph, kosar["topo"].traces, kosar["node_load"],
        net=kosar["net"], failure_rates=kosar["rates"],
        failure_rate_source="outage")


def test_all_five_feeders_are_studied(kosar):
    study = _study(kosar)
    keys = [f.feeder_key for f in study.feeders]
    assert keys == ["F3", "F4", "F5", "F6", "F7"]
    for f in study.feeders:
        assert f.status == "ok"
        assert f.line_length_m > 0
        assert f.total_load_kw > 0
        assert f.baseline_eens_kwh > 0


def test_section_accounting_is_exact(kosar):
    """Σ بار و Σ طول قطعه‌ها = کل فیدر (هیچ باری/طولی گم یا دوبار شمرده نمی‌شود)."""
    study = _study(kosar)
    for f in study.feeders:
        for sections in ([f.baseline_sections] +
                         [s.sections for s in f.steps]):
            assert sum(s.load_kw for s in sections) == pytest.approx(
                f.total_load_kw, rel=1e-9, abs=1e-6)
            assert sum(s.length_m for s in sections) == pytest.approx(
                f.line_length_m, rel=1e-9, abs=1e-6)
            assert sum(s.lambda_per_year for s in sections) == pytest.approx(
                f.failure_rate_per_year, rel=1e-9)


def test_optimization_is_monotone_and_non_trivial(kosar):
    study = _study(kosar)
    assert study.total_selected > 0
    assert study.best_eens_kwh < study.baseline_eens_kwh
    assert 0.0 < study.improvement_percent < 100.0
    for f in study.feeders:
        eens = [f.baseline_eens_kwh] + [s.eens_kwh for s in f.steps]
        assert all(b <= a + 1e-6 for a, b in zip(eens, eens[1:]))
        assert f.best is not None and len(f.best.selected) >= 1


def test_real_lambdas_are_used_where_available(kosar):
    study = _study(kosar)
    f3 = study.feeder("F3")
    f5 = study.feeder("F5")
    assert f3.failure_rate_source == "outage-lambda"
    assert f3.failure_rate_per_year == pytest.approx(kosar["rates"]["F3"])
    assert f5.failure_rate_per_year == pytest.approx(kosar["rates"]["F5"])
    # فیدر بدون ماتریس λ/r واقعی → پیش‌فرض با منبع صریح
    f7 = study.feeder("F7")
    assert f7.failure_rate_source == "configured-default"


def test_existing_switches_make_the_baseline_better_than_one_section(kosar):
    with_switches = _study(kosar)
    without = _study(kosar, use_existing_switches=False)
    for a, b in zip(with_switches.feeders, without.feeders):
        assert a.baseline_eens_kwh <= b.baseline_eens_kwh + 1e-6
    busy = with_switches.feeder("F6")       # ۱۵ زون در توپولوژی
    assert len(busy.existing_cut_nodes) >= 1


def test_suggested_nodes_have_real_coordinates(kosar):
    study = _study(kosar)
    graph = kosar["topo"].graph
    for f in study.feeders:
        for c in f.best.selected:
            assert c.node in graph.nodes
            assert c.coord is not None
            assert c.coord == pytest.approx(graph.nodes[c.node].coord)
            assert 0.0 < c.downstream_ratio <= 0.80 + 1e-9


def test_engine_is_deterministic(kosar):
    first = _study(kosar)
    second = _study(kosar)
    for a, b in zip(first.feeders, second.feeders):
        assert [c.node for c in a.best.selected] == \
            [c.node for c in b.best.selected]
        assert a.best_eens_kwh == pytest.approx(b.best_eens_kwh)


def test_directional_model_is_conservative(kosar):
    uniform = _study(kosar)
    directional = _study(kosar, restoration_model="directional")
    assert directional.baseline_eens_kwh <= uniform.baseline_eens_kwh + 1e-6


def test_service_writes_report_without_touching_the_project(kosar, tmp_path):
    before = kosar["kv_keys_before"]
    res = SectionalizerService(SectionalizerAppSettings(
        user="pytest", persist=False,
        engine=SectionalizerSettings(max_sectionalizers=2),
        load_model={"level": "estimated"},
        failure_rate_source="outage",
        report_dir=str(tmp_path),
    )).run(str(DB))
    assert res.study.total_selected > 0
    assert Path(res.report_md).is_file()
    payload = json.loads((tmp_path / "sectionalizer_eens_report.json").read_text(
        encoding="utf-8"))
    assert payload["study"]["feeders"][0]["feeder_key"] == "F3"
    assert "جایابی بهینهٔ کلید" in Path(res.report_md).read_text(
        encoding="utf-8")
    # فقط‌خواندنی: هیچ کلید جدیدی در project_kv نوشته نشده است
    conn = sqlite3.connect(str(DB))
    try:
        keys = {r[0] for r in conn.execute("SELECT key FROM project_kv")}
    finally:
        conn.close()
    assert before == sorted(keys)
    assert KV_KEY not in keys


def test_persisted_study_roundtrip_on_a_project_copy(tmp_path):
    """ذخیره/بازیابی نتیجه در پروژه (روی نسخهٔ کپی — پروژهٔ اصلی دست‌نخورده)."""
    import shutil

    from switchloc.application.sectionalizer_service import load_persisted_study

    db = tmp_path / "kosar_copy.sqlite"
    shutil.copy2(DB, db)
    svc = SectionalizerService(SectionalizerAppSettings(
        user="pytest", persist=True,
        engine=SectionalizerSettings(max_sectionalizers=1),
        failure_rate_source="outage", report_dir=str(tmp_path)))
    first = svc.run(str(db))
    payload = load_persisted_study(str(db))
    assert payload is not None
    assert payload["study"]["feeders"][0]["feeder_key"] == "F3"
    assert payload["markdown"] and "جایابی بهینهٔ کلید" in payload["markdown"]
    assert payload["settings"]["user"] == "pytest"
    assert payload["algo_version"].startswith("SwitchLoc")
    # تنظیمات ران هم برای بازسازی وضعیت ذخیره شده است
    assert payload["settings"]["engine"]["max_sectionalizers"] == 1

    # اجرای دوم همان کلید را بازنویسی می‌کند (نه ردیف تکراری)
    second = svc.run(str(db))
    assert second.study.total_selected == first.study.total_selected
    conn = sqlite3.connect(str(db))
    try:
        n = conn.execute("SELECT COUNT(*) FROM project_kv WHERE key=?",
                         (KV_KEY,)).fetchone()[0]
    finally:
        conn.close()
    assert n == 1
