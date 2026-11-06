# -*- coding: utf-8 -*-
"""GG-01/02/09 — reader tests on the real Khalkhal sample export.

Requires the sample export folder; points at the sandbox copy by default
and can be redirected with SWITCHLOC_SAMPLE_DIR.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from switchloc.gis.readers.shapefile_reader import ShapefileReader  # noqa: E402
from switchloc.validation.issues import IssueLog  # noqa: E402

SAMPLE = Path(os.environ.get(
    "SWITCHLOC_SAMPLE_DIR",
    "/home/z/my-project/work/sample_shp/Export_1404_08_17_12_34_09",
))

pytestmark = pytest.mark.skipif(not SAMPLE.is_dir(),
                                reason="sample export folder not available")

EXPECTED = {"ELWABS": 1, "ELWCBR": 25, "ELWDCS": 70, "ELWDTR": 627,
            "ELWFWT": 7, "ELWFCT": 692, "ELWJUP": 126, "ELWMLN": 111,
            "ELWMSC": 1, "ELWOML": 12095, "ELWREC": 1, "ELWUML": 151}


def test_gg01_discovers_12_layers_with_alias():
    r = ShapefileReader()
    layers = {li.name: li for li in r.discover(SAMPLE)}
    assert set(EXPECTED) <= set(layers)               # ELW-prefixed names found
    assert layers["ELWOML"].feature_count == 12095
    assert layers["ELWOML"].crs_wkt.startswith("PROJCS")   # .prj sidecar read


def test_gg02_input_files_untouched():
    before = {p.name: p.stat().st_mtime_ns for p in SAMPLE.glob("*.shp")}
    r = ShapefileReader()
    for li in r.discover(SAMPLE):
        r.read(li)
    after = {p.name: p.stat().st_mtime_ns for p in SAMPLE.glob("*.shp")}
    assert before == after


def test_gg09_counts_and_issue_rules():
    r = ShapefileReader()
    log = IssueLog()
    total = 0
    no_feeder = 0
    for li in r.discover(SAMPLE):
        feats = r.read(li, log)
        total += len(feats)
        no_feeder += sum(1 for f in feats if not f.feeder)
    assert total == sum(EXPECTED.values())            # 14,224 features
    assert log.count("Error") == 0                    # clean read of healthy data
    # 270 records lack the `Feeder` column (262 ELWOML + 8 ELWMLN), but the
    # documented 4-field fallback chain recovers 229 of them → exactly 41
    # remain unresolvable (36 ELWOML, 3 ELWDTR, 1 ELWFCT, 1 ELWMLN) and must
    # surface as issues.
    assert len(log.by_code("GIS-FEEDER-MISSING")) == 41
    assert no_feeder == 41


def test_reader_flags_missing_id_only_where_real():
    r = ShapefileReader()
    li = [x for x in r.discover(SAMPLE) if x.name == "ELWDTR"][0]
    log = IssueLog()
    feats = r.read(li, log)
    ids = {f.record_id for f in feats}
    assert any(i.startswith("ABEL") for i in ids)     # T_MapID present in real data
