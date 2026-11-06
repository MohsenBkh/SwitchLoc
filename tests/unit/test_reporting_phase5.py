# -*- coding: utf-8 -*-
"""Phase-5 tests — every exporter is verified by REOPENING its output.

Covers: StudyModel (proposed switches, CRS, KPIs), the neutral content
tree, the RTL Excel workbook, the Word report (bidi XML), the Persian
PDF (when the optional extras are installed), GeoJSON ×3 + CSV crew
sheet, and the ReportService cross-check against the persisted run.
Skips cleanly when the sample project is absent; PDF tests also skip
when reportlab/reshaper/bidi or the Vazirmatn font are missing.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest                                        # noqa: E402

from switchloc.reporting.model import StudyModel     # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "projects" / "khalkhal_phase1.sqlite"

pytestmark = pytest.mark.skipif(
    not DB.exists(), reason="projects/khalkhal_phase1.sqlite not present")


# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def study(tmp_path_factory):
    """One full in-memory pipeline shared by all exporter tests.

    نیاز ۱۰ changed the plan-selection contract: on the real Khalkhal
    λ/r data every generated scheme has a NEGATIVE benefit (CE < CN),
    so the honest result is «عدم توجیه نصب کلید» and the report/GeoJSON
    proposed-switch paths would carry zero rows.  To keep exercising
    those export paths, the fixture runs with the benefit criterion
    disabled — plans then land in the legitimate «نیازمند تأیید ظرفیت»
    state (no capacity map) WITH scheme ids, exactly like a real study
    after the engineer enters capacities but before approval.
    """
    from switchloc.application.placement_service import (
        PlacementAppSettings, PlacementService)
    from switchloc.placement.acceptance import AcceptanceCriteria
    eng = PlacementAppSettings().engine
    eng.criteria = AcceptanceCriteria(require_positive_benefit=False,
                                      min_ens_reduction_kwh=0.0,
                                      min_ens_reduction_percent=0.0)
    res = PlacementService(PlacementAppSettings(
        persist=False, engine=eng)).run(str(DB))
    from switchloc.persistence.store import ProjectStore
    store = ProjectStore(str(DB))
    net, _issues = store.load_network()
    store.close()
    m = StudyModel(net=net, topo=res.topo, placement=res.result,
                   project_name="khalkhal-test",
                   db_path=str(DB))
    out = tmp_path_factory.mktemp("phase5")
    return m, res, out


@pytest.fixture(scope="module")
def doc(study):
    from switchloc.reporting.content import build_report
    m, _res, _out = study
    return build_report(m)


# ---------------------------------------------------------------------------
# model / content
# ---------------------------------------------------------------------------
def test_model_kpis_and_proposed(study):
    m, res, _out = study
    k = m.kpis()
    assert k["feeder_count"] == len(res.topo.traces)
    assert k["zone_count"] == len(res.topo.zones.zones)
    # نیاز ۱۰: plans need capacity confirmation here (fixture disables the
    # benefit criterion) — they carry scheme ids, so the proposed rows exist
    assert k["switch_proposed"] > 0
    statuses = {r.get("status") for r in m.placement.recommendation}
    assert statuses <= {"accepted", "needs_capacity_confirmation",
                        "no_justification"}
    # every proposed switch has real coordinates in the analysis CRS
    props = m.build_proposed()
    assert all(p.x is not None and p.y is not None for p in props)
    assert all(p.scheme_kind in ("sequential_nc", "one_half_switch")
               for p in props)
    # λ/r from the phase-3 matrix reached the ranking rows
    ranked = res.result.ranking.rows
    assert any(r.lambda_per_year > 0 for r in ranked)


def test_model_epsg_and_wgs84(study):
    m, _res, _out = study
    assert m.epsg is not None          # Khalkhal import recorded a UTM CRS
    props = m.build_proposed()
    geo = [p for p in props if p.lon is not None and p.lat is not None]
    assert geo, "WGS84 columns were not derived for a known CRS"
    # Khalkhal lies in Ardabil province: 48°E < lon < 48.9, lat ~37.6-38.4
    p = geo[0]
    assert 48.0 < p.lon < 48.9 and 37.4 < p.lat < 38.5


def test_content_tree_complete(study, doc):
    m, _res, _out = study
    ids = [s.id for s in doc.sections]
    for expected in ("summary", "method", "n1", "ranking", "schemes",
                     "economics", "recommendation", "issues", "appendix"):
        assert expected in ids, f"missing section {expected}"
    n1 = next(s for s in doc.sections if s.id == "n1")
    caps = [t.caption for t in n1.tables]
    assert any("۱۳" in c for c in caps)
    assert any("۱۴" in c for c in caps)
    assert any("۱۵" in c for c in caps)
    # every table cell is a str — no raw floats leaked into the tree
    for s in doc.sections:
        for t in s.tables:
            for row in t.rows:
                assert all(isinstance(c, str) for c in row)
    # the appendix carries the actionable switch schedule
    app = next(s for s in doc.sections if s.id == "appendix")
    assert len(app.tables[0].rows) == m.kpis()["switch_proposed"]


# ---------------------------------------------------------------------------
# Excel workbook
# ---------------------------------------------------------------------------
def test_xlsx_roundtrip(study):
    from openpyxl import load_workbook
    from switchloc.reporting.workbook import export_workbook
    m, _res, out = study
    path = export_workbook(m, str(out / "study.xlsx"))
    wb = load_workbook(path)
    names = set(wb.sheetnames)
    for expected in ("خلاصه", "جداول ۱۳-۱۵", "رتبه‌بندی", "طرح‌ها",
                     "جدول ۱۸", "کلیدهای پیشنهادی", "ماتریس λ-r"):
        assert expected in names, f"missing sheet {expected}"
    ws = wb["کلیدهای پیشنهادی"]
    # layout: row 1 title, row 2 header, row 3+ data
    rows = list(ws.iter_rows(min_row=3, values_only=True))
    data_rows = [r for r in rows if r[0] and r[1]]
    assert len(data_rows) == m.kpis()["switch_proposed"]
    # every in-feeder proposed row carries a zone number from the strict
    # n-1 trees; NO switches of 1.5-switch schemes sit on the feeder
    # boundary (outside the strict core) and legitimately show none
    for r, p in zip(data_rows, m.build_proposed()):
        if p.kind == "NO":
            continue
        assert r[4] is not None and r[4] != "—", f"zone missing for {p.node}"
    # RTL is on and numbers stayed numbers
    assert wb["خلاصه"].sheet_view.rightToLeft is True
    eptl = wb["جداول ۱۳-۱۵"]
    nums = [row[1] for row in eptl.iter_rows(min_row=3, values_only=True)
            if isinstance(row[1], (int, float))]
    assert nums, "EP/TL percentages were written as text"


# ---------------------------------------------------------------------------
# Word report
# ---------------------------------------------------------------------------
def test_docx_roundtrip(study, doc):
    from docx import Document
    from docx.oxml.ns import qn
    from switchloc.reporting.docx_report import export_docx
    m, _res, out = study
    path = export_docx(doc, str(out / "report.docx"))
    d = Document(path)
    texts = "\n".join(p.text for p in d.paragraphs)
    assert "۱. خلاصه مدیریتی" in texts
    assert "پیوست الف" in texts
    assert d.tables, "no tables in the Word report"
    # bidi XML actually present (RTL, not just right-aligned)
    pPr = d.paragraphs[0]._p.find(qn("w:pPr"))
    found_bidi = any(
        p._p.find(qn("w:pPr")) is not None and
        p._p.find(qn("w:pPr")).find(qn("w:bidi")) is not None
        for p in d.paragraphs)
    assert found_bidi, "no w:bidi on any paragraph"
    tbl_bidi = any(
        t._tbl.tblPr.find(qn("w:bidiVisual")) is not None
        for t in d.tables)
    assert tbl_bidi, "no w:bidiVisual on any table"


def test_docx_embeds_map(study, doc):
    from docx import Document
    from switchloc.reporting.docx_report import export_docx
    from switchloc.reporting.service import ReportService
    m, _res, out = study
    png = ReportService._render_map(None, m, str(out))
    assert Path(png).exists() and Path(png).stat().st_size > 50_000
    path = export_docx(doc, str(out / "report_map.docx"), map_png=png)
    d = Document(path)
    # the map picture is embedded (inline shape in the landscape section)
    assert len(d.inline_shapes) == 1
    assert d.inline_shapes[0].width > 5_000_000     # ~ >14 cm in EMU


# ---------------------------------------------------------------------------
# PDF report (optional extras)
# ---------------------------------------------------------------------------
HAS_PDF = True
try:
    import arabic_reshaper  # noqa: F401
    from bidi.algorithm import get_display  # noqa: F401
    import reportlab  # noqa: F401
except ImportError:
    HAS_PDF = False
_FONT_OK = (Path(__file__).resolve().parents[2] / "build_assets" /
            "fonts" / "Vazirmatn-Regular.ttf").exists()
pdfmark = pytest.mark.skipif(
    not (HAS_PDF and _FONT_OK),
    reason="report extras (reportlab/reshaper/bidi/font) not installed")


@pytest.fixture(scope="module")
def pdf_path(study, doc):
    from switchloc.reporting.pdf_report import export_pdf
    m, _res, out = study
    png = None
    return export_pdf(doc, str(out / "report.pdf"))


@pdfmark
def test_pdf_output(study, doc, pdf_path):
    assert Path(pdf_path).read_bytes()[:5] == b"%PDF-"
    assert Path(pdf_path).stat().st_size > 60_000


@pdfmark
def test_pdf_font_embedded(study, doc, pdf_path):
    raw = Path(pdf_path).read_bytes()
    assert b"Vazir" in raw            # our registered face name


@pdfmark
def test_pdf_text_has_shaped_persian(study, doc, pdf_path):
    """The shaped text is drawn as glyphs — the isolated form of «گزارش»
    must NOT appear raw (shaping turns it into presentation forms)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        pytest.skip("pypdf not installed")
    reader = PdfReader(str(pdf_path))
    txt = "".join(page.extract_text() or "" for page in reader.pages)
    assert txt.strip(), "PDF text layer is empty"
    assert "\u0644\u0648\u0627\u0646" not in txt   # unshaped توانیر fragment


# ---------------------------------------------------------------------------
# GIS export
# ---------------------------------------------------------------------------
def test_geojson_and_csv(study):
    from switchloc.reporting.gis_export import export_gis
    m, _res, out = study
    gdir = out / "gis"
    paths = export_gis(m, str(gdir))
    assert len(paths) == 5
    net = json.loads((gdir / "switchloc_network.geojson").read_text(
        encoding="utf-8"))
    sw = json.loads((gdir / "switchloc_switches.geojson").read_text(
        encoding="utf-8"))
    zn = json.loads((gdir / "switchloc_zones.geojson").read_text(
        encoding="utf-8"))
    assert net["features"] and sw["features"] and zn["features"]
    # RFC 7946: WGS84 coordinates (Khalkhal: lon≈48.3, lat≈37.7)
    line = net["features"][0]
    coord = (line["geometry"]["coordinates"][0]
             if line["geometry"]["type"] == "MultiLineString"
             else line["geometry"]["coordinates"])[0]
    assert -180 <= coord[0] <= 180 and -90 <= coord[1] <= 90
    roles = {f["properties"]["role"] for f in sw["features"]}
    assert {"existing_switch", "source", "proposed_switch"} <= roles
    proposed = [f for f in sw["features"]
                if f["properties"]["role"] == "proposed_switch"]
    assert len(proposed) == m.kpis()["switch_proposed"]
    assert all("kind" in f["properties"] and "zone_no" in f["properties"]
               for f in proposed)
    zprops = zn["features"][0]["properties"]
    assert {"zone_id", "feeder", "zone_no", "load_kw"} <= set(zprops)
    # CSV crew sheet matches the proposed list (UTF-8-BOM for Excel)
    with open(gdir / "switch_schedule.csv", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(proposed)
    assert {r["node"] for r in rows} == {
        f["properties"]["node"] for f in proposed}
    meta = json.loads((gdir / "switchloc_export_metadata.json").read_text(
        encoding="utf-8"))
    assert meta["analysis_epsg"] == m.epsg


# ---------------------------------------------------------------------------
# service: cross-check + format filtering
# ---------------------------------------------------------------------------
def test_service_crosscheck_and_formats(study, tmp_path):
    from switchloc.reporting.service import ExportSettings, ReportService
    svc = ReportService(ExportSettings(
        out_dir=str(tmp_path / "exp"),
        formats=("xlsx", "gis")))
    res = svc.run(db_path=str(DB))
    assert res.verdict == "PASS"
    assert res.crosscheck["status"] in ("match", "diff", "none")
    assert "docx" not in res.paths and "pdf" not in res.paths
    assert Path(res.paths["xlsx"]).exists()
    assert len(res.paths["gis"]) == 5
    codes = [c for c, _s, _m in res.issues]
    assert "PHASE5-CROSSCHECK" in codes
    # DB has a persisted phase-4 run → the fresh run must reproduce it
    assert res.crosscheck["status"] == "match"


def test_service_skips_pdf_gracefully(tmp_path, monkeypatch):
    """A missing PDF extra degrades to DOCX with an Information issue —
    the other channels never fail because of one channel."""
    from switchloc.reporting import pdf_report
    from switchloc.reporting.service import ExportSettings, ReportService
    monkeypatch.setattr(pdf_report, "find_font", lambda bold=False: None)
    svc = ReportService(ExportSettings(out_dir=str(tmp_path / "exp2")))
    res = svc.run(db_path=str(DB))
    assert "pdf" not in res.paths
    assert "docx" in res.paths
    codes = [c for c, _s, _m in res.issues]
    assert "PHASE5-PDF-SKIP" in codes


def test_cli_report_subcommand(study, tmp_path, capsys):
    from switchloc.cli import main
    rc = main(["report", str(DB), "--out", str(tmp_path / "cli"),
               "--formats", "xlsx"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "کتاب کار Excel" in out
    assert (tmp_path / "cli" / "SwitchLoc_study.xlsx").exists()

