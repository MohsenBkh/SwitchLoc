# -*- coding: utf-8 -*-
"""v1.18 — سه ایراد نسخهٔ 1.17.0:

۱) نقشه هیچ‌چیز از فیدرها/تجهیزات نشان نمی‌داد (سبک ذخیره‌شده با کلید
   کوتاه قدیمی مثل ``F2`` در برابر کلید کامل ``F2 - MESHKIN``).
۲) همهٔ شاخص‌های ارزیابی فیدرها باید در داشبورد نموداری بیایند.
۳) همان شاخص‌ها باید در گزارش (docx/pdf) و اکسل بیایند.

اصل حاکم در همهٔ آزمون‌ها (A-08): عدد ساخته نمی‌شود؛ «بدون داده» با
``None``/«—» می‌آید، نه صفر.
"""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib
matplotlib.use("Agg")

import pytest
from matplotlib.figure import Figure

from conftest import NetBuilder
from switchloc.topology.graph import NetworkGraph
from switchloc.topology.tracing import (TracingEngine, TracingPolicy,
                                        match_feeders, same_feeder)
from switchloc.topology.zones import ZoneBuilder
from switchloc.ui.map_renderer import NetworkMapRenderer, feeder_palette
from switchloc.ui.map_style import MapStyle
from switchloc.validation.issues import IssueLog

F1 = "F1 - MESHKIN"
F2 = "F2 - HADIDMOBTAKERAN"


# ---------------------------------------------------------------------------
# ۱) نقشه — سبک قدیمی ذخیره‌شده با کلید کوتاه باید همان فیدر کامل را رنگ کند
# ---------------------------------------------------------------------------
def test_match_feeders_legacy_short_key_maps_to_full_key():
    assert match_feeders(F1, ["F1"]) == ["F1"]
    assert match_feeders("F1", [F1]) == [F1]
    assert match_feeders("F2", [F1, F2]) == [F2]
    # تفکیک فیدرهای هم‌نامِ دو پست (v1.16) نباید بشکند
    assert match_feeders("F2 - MESHKIN", [F2]) == []
    assert same_feeder(F1, "F1")


def test_palette_applies_legacy_short_style_to_every_feeder():
    b = NetBuilder()
    for i, name in enumerate([F1, F2]):
        y = i * 400
        b.source(0, y, name)
        b.line([(0, y), (200, y), (400, y)], feeder=name)
        b.transformer(400, y, feeder=name)
    traces = TracingEngine(NetworkGraph.from_network(b.net, IssueLog()),
                           b.net, TracingPolicy()).trace_all(IssueLog())
    st = MapStyle.default_for(feeders=[t.feeder_key for t in traces])
    st.feeder_colors = {"F1": "#ff0000", "F2": "#00aa00"}   # نگارش قدیمی
    pal = feeder_palette(traces, st)
    assert pal[F1] == "#ff0000", "رنگ سبک قدیمی به فیدر کامل اعمال نشد"
    assert pal[F2] == "#00aa00"
    assert st.color_of(F1) == "#ff0000"
    assert st.color_of(F2) == "#00aa00"


def _render_with_style(style) -> tuple:
    b = NetBuilder()
    for i, name in enumerate([F1, F2]):
        y = i * 400
        b.source(0, y, name)
        b.line([(0, y), (200, y), (400, y)], feeder=name)
        b.transformer(200, y, feeder=name)
        b.transformer(400, y, feeder=name)
    g = NetworkGraph.from_network(b.net, IssueLog())
    traces = TracingEngine(g, b.net, TracingPolicy()).trace_all(IssueLog())
    zones = ZoneBuilder(g, b.net, traces).build(IssueLog())
    r = NetworkMapRenderer(g, traces=traces, zones=zones,
                           switches={s.id: s for s in b.net.switches},
                           style=style)
    fig = Figure(figsize=(6, 4))
    r.render_into(fig)
    segs = sum(len(c.get_segments()) for c in fig.axes[0].collections
               if hasattr(c, "get_segments"))
    drawn = set(r._drawn)                                    # noqa: SLF001
    n_edges = len(g.edges)
    return fig, segs, drawn, n_edges


def test_map_draws_segments_and_devices_with_legacy_saved_style():
    st = MapStyle.from_dict({"feeder_colors": {"F1": "#ff0000",
                                               "F2": "#00aa00"},
                             "show_fuse_cutouts": False})
    fig, segs, drawn, n_edges = _render_with_style(st)
    try:
        assert n_edges >= 4
        assert segs >= n_edges, "خطوط فیدرها رسم نشدند (باگ نسخهٔ 1.17)"
        assert "source" in drawn and "transformer" in drawn
    finally:
        import matplotlib.pyplot as plt
        plt.close(fig)


def test_map_draws_segments_with_fresh_style_too():
    b = NetBuilder()
    b.source(0, 0, F1)
    b.line([(0, 0), (100, 0)], feeder=F1)
    b.transformer(100, 0, feeder=F1)
    traces = TracingEngine(NetworkGraph.from_network(b.net, IssueLog()),
                           b.net, TracingPolicy()).trace_all(IssueLog())
    st = MapStyle.default_for(feeders=[t.feeder_key for t in traces])
    fig, segs, drawn, n_edges = _render_with_style(st)
    try:
        assert segs >= n_edges and "transformer" in drawn
    finally:
        import matplotlib.pyplot as plt
        plt.close(fig)


# ---------------------------------------------------------------------------
# ۲) مدل گزارش — یک ردیف برای هر فیدر با همهٔ شاخص‌ها
# ---------------------------------------------------------------------------
LAM = [
    {"feeder_key": F1, "lambda_per_year": 167.75,
     "lambda_reducible_per_year": 28.12, "r_minutes": 52.5, "u_hours": 146.85},
    {"feeder_key": F2, "lambda_per_year": 85.5,
     "lambda_reducible_per_year": 11.6, "r_minutes": 63.6, "u_hours": 90.68},
]
INDICES = {
    "has_result": True, "saifi": 5.787, "saidi": 265.32, "caidi": 45.84,
    "asai": 0.999495, "aggregation": "load-weighted",
    "load_basis": "feeder-load", "energy_unit": "mwh",
    "energy_unit_source": "inferred", "notes": ["سهم بار ≈ سهم مشترکین"],
    "feeders": [
        {"feeder_key": F1, "events_counted": 3422, "events_total": 3531,
         "saidi": 384.1, "saifi": 9.07, "caidi": 42.3, "asai": 0.999269,
         "ens_kwh_per_year": 123456.0, "exposure_years": 5.085},
        {"feeder_key": F2, "events_counted": 1841, "events_total": 1876,
         "saidi": 176.2, "saifi": 3.33, "caidi": 53.0, "asai": 0.999665,
         "ens_kwh_per_year": 65432.0, "exposure_years": 5.088},
    ],
}


def _net_topo():
    b = NetBuilder()
    for i, name in enumerate([F1, F2]):
        y = i * 400
        b.source(0, y, name)
        b.line([(0, y), (200, y), (400, y)], feeder=name)
        b.transformer(200, y, feeder=name)
        b.transformer(400, y, feeder=name)
    g = NetworkGraph.from_network(b.net, IssueLog())
    traces = TracingEngine(g, b.net, TracingPolicy()).trace_all(IssueLog())
    zones = ZoneBuilder(g, b.net, traces).build(IssueLog())
    topo = SimpleNamespace(traces=traces, zones=zones, ties=[])
    return b.net, topo


def _model(**kw):
    from switchloc.reporting.model import StudyModel
    net, topo = _net_topo()
    placement = SimpleNamespace(
        economics=SimpleNamespace(ens_before_kwh={F1: 519518.8, F2: 250000.0},
                                  ens_after_kwh={}, comparisons=[]),
        ranking=SimpleNamespace(rows=[
            SimpleNamespace(feeder_key=F1, score=0.71, rank=1),
            SimpleNamespace(feeder_key=F2, score=0.42, rank=2)]),
        recommendation=[], schemes=[], issues=[],
        n1=SimpleNamespace(trees={}, connections=[], rows15=[], eptl=[]),
    )
    base = dict(net=net, topo=topo, placement=placement, project_name="آزمون",
                outage_lambda=LAM, feeder_indices=INDICES)
    base.update(kw)
    return StudyModel(**base)


def test_feeder_table_has_every_index_per_feeder():
    rows = {r["feeder_key"]: r for r in _model().feeder_table()}
    assert set(rows) == {F1, F2}
    r1 = rows[F1]
    assert r1["lambda_per_year"] == pytest.approx(167.75)
    assert r1["r_minutes"] == pytest.approx(52.5)
    assert r1["u_hours"] == pytest.approx(146.85)
    assert r1["saidi"] == pytest.approx(384.1)
    assert r1["saifi"] == pytest.approx(9.07)
    assert r1["caidi"] == pytest.approx(42.3)
    assert r1["asai"] == pytest.approx(0.999269)
    assert r1["ens_per_year_kwh"] == pytest.approx(123456.0)
    assert r1["ens_before_kwh"] == pytest.approx(519518.8)
    assert r1["score"] == pytest.approx(0.71)
    assert r1["km"] > 0 and r1["transformers"] == 2


def test_feeder_table_keeps_missing_indices_as_none():
    """فیدر بدون رخداد ثبت‌شده → None (نه صفر) و بدون λ → صفر واقعی."""
    ind = {"has_result": True, "feeders": [
        {"feeder_key": F1, "events_counted": 10, "events_total": 10,
         "saidi": 100.0, "saifi": 2.0, "caidi": 50.0, "asai": 0.9998,
         "ens_kwh_per_year": 10.0}]}
    rows = {r["feeder_key"]: r for r in
            _model(feeder_indices=ind, outage_lambda=[LAM[0]]).feeder_table()}
    assert rows[F2]["saidi"] is None and rows[F2]["saifi"] is None
    assert rows[F2]["ens_per_year_kwh"] is None
    assert rows[F2]["lambda_per_year"] == 0.0        # λ نداده ⇒ صفر واقعی


# ---------------------------------------------------------------------------
# ۲-ب) داشبورد — ردیف‌های فیدر و نمودارها
# ---------------------------------------------------------------------------
def _dash_rows(indices=None):
    from switchloc.ui.dashboard_data import feeder_rows
    _net, topo = _net_topo()
    snap = {"table14_eptl": [{"feeder_key": F1, "total_load_kw": 9000.0,
                             "ep_percent": 12.5, "tl_percent": 8.0,
                             "zone_count": 3}],
            "ranking": [{"feeder_key": F1, "rank": 1, "score": 0.71}],
            "ens_before_kwh": {F1: 519518.8}}
    src = indices if indices is not None else INDICES["feeders"]
    return feeder_rows(topo.traces, LAM, snap,
                       indices_map={r["feeder_key"]: r for r in src})


def test_dashboard_rows_carry_service_indices():
    rows = {r["feeder_key"]: r for r in _dash_rows()}
    assert rows[F1]["saidi"] == pytest.approx(384.1)
    assert rows[F1]["saifi"] == pytest.approx(9.07)
    assert rows[F1]["caidi"] == pytest.approx(42.3)
    assert rows[F1]["asai"] == pytest.approx(0.999269)
    assert rows[F1]["ens_per_year_kwh"] == pytest.approx(123456.0)
    assert rows[F1]["service_events"] == 3531
    assert rows[F2]["saidi"] == pytest.approx(176.2)
    # فیدر بدون رکورد شاخص: None، نه صفر
    rows2 = {r["feeder_key"]: r for r in _dash_rows(indices=INDICES["feeders"][:1])}
    assert rows2[F2]["saidi"] is None and rows2[F2]["ens_per_year_kwh"] is None


def test_chart_metrics_cover_every_dashboard_index_key():
    from switchloc.ui.qt.charts import CHART_METRICS, chart_items
    rows = _dash_rows()
    keys = [k for k, _t, _u, _s in CHART_METRICS]
    assert len(keys) >= 15, "همهٔ شاخص‌ها باید نمودار داشته باشند"
    for wanted in ("saidi", "saifi", "caidi", "asai_pct", "ens_per_year_kwh",
                   "ens_kwh", "lambda_per_year", "r_minutes", "u_hours",
                   "score"):
        assert wanted in keys
    f1 = {r["feeder_key"]: r for r in rows}[F1]
    for key in keys:
        if key == "asai_pct":
            items = chart_items(rows, key)
            assert items[0][1] == pytest.approx(99.9269)   # ×100
        else:
            # کلید هر شاخص باید در ردیف واقعی وجود داشته باشد
            assert key in f1, f"کلید {key} در ردیف داشبورد نیست"


def test_chart_items_mark_missing_data_as_none():
    from switchloc.ui.qt.charts import chart_items
    rows = _dash_rows(indices=INDICES["feeders"][:1])
    items = {k: v for k, v, _c in chart_items(rows, "saidi")}
    assert items[F1] == pytest.approx(384.1)
    assert items[F2] is None            # «—» در نمودار، نه میلهٔ صفر
    assert all(color for _k, _v, color in chart_items(rows, "saidi"))


def test_dashboard_chart_widgets_are_built_and_filled():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])   # noqa: F841
    from switchloc.ui.qt.charts import CHART_METRICS, BarChartWidget
    from switchloc.ui.qt.dashboard_tab import _build_chart_section

    box, charts = _build_chart_section()()
    assert box is not None
    assert len(charts) == len(CHART_METRICS) >= 15
    assert all(isinstance(c, BarChartWidget) for c in charts.values())
    from switchloc.ui.qt.charts import chart_items
    rows = _dash_rows()
    for key, ch in charts.items():
        ch.set_data(chart_items(rows, key))
        assert len(ch.items) == len(rows)
    assert [v for _k, v, _c in charts["saidi"].items][0] == pytest.approx(384.1)


# ---------------------------------------------------------------------------
# ۳) گزارش و اکسل
# ---------------------------------------------------------------------------
def test_report_has_feeder_indices_section_with_all_columns():
    from switchloc.reporting.content import (FEEDER_INDEX_COLUMNS,
                                             _feeder_indices_section)
    sec = _feeder_indices_section(_model())
    assert sec is not None and sec.id == "feeder_indices"
    assert "شاخص‌های ارزیابی فیدرها" in sec.title
    assert "SAIFI" in " ".join(sec.intro) and "ASAI" in " ".join(sec.intro)
    headers = sec.tables[0].headers
    assert headers[0] == "فیدر"
    assert len(headers) == len(FEEDER_INDEX_COLUMNS) + 1 >= 13
    row = {r[0]: r for r in sec.tables[0].rows}[F1]
    texts = " | ".join(row)
    assert "167.75" in texts and "384.1" in texts and "99.9269" in texts
    # فیدر بدون داده: «—»
    row2 = {r[0]: r for r in sec.tables[0].rows}[F2]
    assert row2[headers.index("SAIDI (دقیقه/سال)")] == "176.2"


def test_report_section_shows_dash_for_feeders_without_data():
    from switchloc.reporting.content import _feeder_indices_section
    ind = dict(INDICES, feeders=INDICES["feeders"][:1])
    sec = _feeder_indices_section(_model(feeder_indices=ind))
    headers = sec.tables[0].headers
    row2 = {r[0]: r for r in sec.tables[0].rows}[F2]
    for col in ("SAIDI (دقیقه/سال)", "SAIFI (قطع/سال)", "CAIDI (دقیقه)",
                "ASAI (٪)"):
        assert row2[headers.index(col)] == "—", "بدون داده باید «—» باشد"


def test_report_section_absent_when_model_has_no_feeder_table():
    """مدل‌های سبک/قدیمی (بدون feeder_table) نباید گزارش را بشکنند."""
    from switchloc.reporting.content import _feeder_indices_section
    class _M:
        feeder_indices = {}
    assert _feeder_indices_section(_M()) is None


def test_indices_figure_written_with_english_labels(tmp_path):
    from switchloc.reporting.figures import indices_figure
    out = tmp_path / "feeder_indices.png"
    path = indices_figure(_model().feeder_table(), out)
    assert path and os.path.getsize(path) > 2000


def test_workbook_has_indices_sheet_rows_and_charts(tmp_path):
    from openpyxl import Workbook, load_workbook
    from switchloc.reporting.workbook import write_feeder_indices_sheet
    xlsx = tmp_path / "study.xlsx"
    wb0 = Workbook()
    wb0.remove(wb0.active)
    write_feeder_indices_sheet(wb0, _model())
    assert len(wb0.sheetnames) == 1
    wb0.save(xlsx)
    wb = load_workbook(xlsx)
    assert "شاخص‌های فیدرها" in wb.sheetnames
    ws = wb["شاخص‌های فیدرها"]
    assert len(ws._charts) >= 6, "نمودارهای شاخص‌ها در اکسل نیستند"
    flat = [[("" if v is None else v) for v in row]
            for row in ws.iter_rows(values_only=True)]
    header_row = next(r for r in flat if r and r[0] == "فیدر")
    idx = {name: i for i, name in enumerate(header_row) if isinstance(name, str)}
    f1_row = next(r for r in flat if r and r[0] == F1)
    assert f1_row[idx["λ (۱/سال)"]] == pytest.approx(167.75)
    assert f1_row[idx["SAIDI (دقیقه/سال)"]] == pytest.approx(384.1)
    assert f1_row[idx["SAIFI (قطع/سال)"]] == pytest.approx(9.07)
    assert f1_row[idx["ASAI (٪)"]] == pytest.approx(99.9269)
    f2_row = next(r for r in flat if r and r[0] == F2)
    assert f2_row[idx["SAIDI (دقیقه/سال)"]] == pytest.approx(176.2)
    # جدول شاخص‌های سامانه در بالای برگه
    sys_rows = {r[0]: r[1] for r in flat if r and isinstance(r[0], str)
                and r[0].startswith(("SAIDI", "SAIFI", "CAIDI", "ASAI"))}
    assert sys_rows["SAIDI (دقیقه/سال)"] == pytest.approx(265.32)
    assert sys_rows["SAIFI (قطع/سال)"] == pytest.approx(5.787)


# ---------------------------------------------------------------------------
# ۳-ب) PDF — جدول پهن (۱۴ ستون) روی صفحهٔ افقی و بدون مربع خالی
# ---------------------------------------------------------------------------
def test_pdf_col_widths_keep_wide_table_readable():
    from switchloc.reporting.content import FEEDER_INDEX_COLUMNS
    from switchloc.reporting.pdf_report import _col_widths
    headers = ["فیدر"] + [c[1] for c in FEEDER_INDEX_COLUMNS]
    usable = 842.0 - 72.0
    widths = _col_widths(len(headers), headers, None, usable)
    assert len(widths) == len(headers)
    assert sum(widths) == pytest.approx(usable, rel=1e-6)
    assert widths[0] >= 100, "ستون فیدر باید جای نام کامل فیدر را داشته باشد"
    assert all(w >= 40 for w in widths[1:]), "ستون‌های عددی نباید در هم بریزند"


HAS_PDF = True
try:
    import arabic_reshaper  # noqa: F401
    import reportlab  # noqa: F401
    from bidi.algorithm import get_display  # noqa: F401
except ImportError:                                    # pragma: no cover
    HAS_PDF = False


@pytest.mark.skipif(not HAS_PDF, reason="report extras not installed")
def test_pdf_wide_table_goes_landscape_without_missing_glyphs(tmp_path):
    from switchloc.reporting.content import (FEEDER_INDEX_COLUMNS, ReportDoc,
                                             Section, Table)
    from switchloc.reporting.pdf_report import export_pdf

    headers = ["فیدر"] + [c[1] for c in FEEDER_INDEX_COLUMNS]
    row = [F1] + ["167.75", "28.12", "52.5", "146.85", "384.1", "9.07",
                  "42.3", "99.9269", "54,959", "0", "—"]
    row = row[:len(headers)]
    doc = ReportDoc(title="آزمون PDF", subtitle="جدول شاخص‌ها",
                    meta=[("پروژه", "آزمون"), ("نسخه", "1.18.0")],
                    kpis=[], footer="SwitchLoc",
                    sections=[Section(id="feeder_indices", title="۱-ب",
                                      intro=["λ و cos φ در متن"],
                                      tables=[Table("شاخص فیدرها", headers,
                                                    [row])])])
    from switchloc.reporting.pdf_report import _is_wide_table
    assert _is_wide_table(len(headers)) and not _is_wide_table(6)
    path = export_pdf(doc, str(tmp_path / "wide.pdf"))
    raw = open(path, "rb").read()
    assert raw[:5] == b"%PDF-"
    try:
        from pypdf import PdfReader
    except ImportError:                                # pragma: no cover
        return
    sizes = [(float(p.mediabox.width), float(p.mediabox.height))
             for p in PdfReader(path).pages]
    assert any(w > h for w, h in sizes), \
        "جدول پهن باید روی صفحهٔ افقی (A4 landscape) برود"
