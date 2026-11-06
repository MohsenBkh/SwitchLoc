# -*- coding: utf-8 -*-
"""v1.9 hardening: logging, schema versioning, outage headers, CRS, enums."""
import json
import re
import sqlite3
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"


# ---------------- logging ----------------
def test_logging_writes_to_env_dir(tmp_path, monkeypatch):
    import logging
    from switchloc import logging_setup as ls
    monkeypatch.setenv("SWITCHLOC_LOG_DIR", str(tmp_path))
    monkeypatch.setitem(ls._STATE, "path", None)
    root = logging.getLogger("switchloc")
    before = list(root.handlers)
    try:
        p = ls.setup_logging()
        assert p == tmp_path / ls.LOG_FILE_NAME
        ls.get_logger("t").warning("hello-log")
        for h in root.handlers:
            h.flush()
        assert "hello-log" in p.read_text(encoding="utf-8")
        try:
            1 / 0
        except ZeroDivisionError as exc:
            ls.log_exception(exc, "t", "ctx")
        for h in root.handlers:
            h.flush()
        assert "ZeroDivisionError" in p.read_text(encoding="utf-8")
    finally:
        for h in list(root.handlers):
            if h not in before:
                root.removeHandler(h)
                h.close()
        ls._STATE["path"] = None


# ---------------- schema versioning ----------------
def test_new_project_is_stamped(tmp_path):
    from switchloc.persistence.schema import SCHEMA_VERSION
    from switchloc.persistence.store import ProjectStore
    s = ProjectStore(tmp_path / "a.sqlite")
    try:
        assert s.schema_version() == SCHEMA_VERSION
    finally:
        s.close()


def test_legacy_project_is_adopted(tmp_path):
    from switchloc.persistence.schema import SCHEMA_VERSION
    from switchloc.persistence.store import ProjectStore
    p = tmp_path / "old.sqlite"
    ProjectStore(p).close()
    c = sqlite3.connect(p)
    c.execute("PRAGMA user_version = 0")
    c.commit()
    c.close()
    s = ProjectStore(p)
    try:
        assert s.schema_version() == SCHEMA_VERSION
    finally:
        s.close()


def test_newer_project_is_refused(tmp_path):
    from switchloc.persistence.store import ProjectStore, SchemaTooNewError
    p = tmp_path / "new.sqlite"
    ProjectStore(p).close()
    c = sqlite3.connect(p)
    c.execute("PRAGMA user_version = 999")
    c.commit()
    c.close()
    with pytest.raises(SchemaTooNewError):
        ProjectStore(p)
    # file untouched
    c = sqlite3.connect(p)
    assert c.execute("PRAGMA user_version").fetchone()[0] == 999
    c.close()


def test_migration_runs_with_backup(tmp_path, monkeypatch):
    import switchloc.persistence.store as st
    p = tmp_path / "m.sqlite"
    st.ProjectStore(p).close()
    monkeypatch.setattr(st, "SCHEMA_VERSION", 3)
    monkeypatch.setattr(st, "MIGRATIONS",
                        {3: "ALTER TABLE project_kv ADD COLUMN note TEXT;"})
    s = st.ProjectStore(p)
    try:
        assert s.schema_version() == 3
        cols = [r[1] for r in s.conn.execute("PRAGMA table_info(project_kv)")]
        assert "note" in cols
    finally:
        s.close()
    assert (tmp_path / "m.pre-migration-v2.sqlite").exists()


# ---------------- outage headers ----------------
def test_outage_header_normalisation():
    from switchloc.reliability.outages import normalize_header
    a = normalize_header("نام فيدر")          # Arabic yeh
    b = normalize_header("نام‌فیدر")          # Persian yeh + ZWNJ
    c = normalize_header("  نام   فیدر ")
    assert a == b == c


def _outage_book(path, headers):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "S"
    ws.append(headers)
    ws.append([1, 3, "1405/01/05", "00:30", "x"])
    wb.save(path)


def test_outage_reader_accepts_variant_spelling_and_flags_unknown(tmp_path,
                                                                  monkeypatch):
    from switchloc.reliability.outages import read_outage_workbook
    monkeypatch.delenv("SWITCHLOC_OUTAGE_COLUMNS", raising=False)
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "o.xlsx"
    _outage_book(p, ["شماره حادثه", "نام فیدر", "تاریخ حادثه", "مدت قطع",
                     "ستون ناشناخته"])
    recs, stats = read_outage_workbook(p)
    sh = stats["sheets"]["S"]
    assert {"feeder_raw", "date_raw", "duration_raw"} <= set(sh["columns_found"])
    assert sh["headers_unmapped"] == ["ستون ناشناخته"]
    assert sh["core_missing"] == []
    assert len(recs) == 1


def test_outage_alias_file(tmp_path, monkeypatch):
    from switchloc.reliability.outages import read_outage_workbook
    js = tmp_path / "a.json"
    js.write_text(json.dumps({"ستون ناشناخته": "cause_raw"},
                             ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("SWITCHLOC_OUTAGE_COLUMNS", str(js))
    p = tmp_path / "o.xlsx"
    _outage_book(p, ["شماره حادثه", "نام فیدر", "تاریخ حادثه", "مدت قطع",
                     "ستون ناشناخته"])
    _recs, stats = read_outage_workbook(p)
    assert "cause_raw" in stats["sheets"]["S"]["columns_found"]
    assert stats["sheets"]["S"]["headers_unmapped"] == []


def test_outage_missing_core_is_reported(tmp_path, monkeypatch):
    from switchloc.reliability.outages import read_outage_workbook
    monkeypatch.delenv("SWITCHLOC_OUTAGE_COLUMNS", raising=False)
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "o.xlsx"
    _outage_book(p, ["a", "b", "c", "d", "e"])
    _recs, stats = read_outage_workbook(p)
    assert set(stats["sheets"]["S"]["core_missing"]) == {
        "feeder_raw", "date_raw", "duration_raw"}


# ---------------- CRS is never assumed ----------------
def test_osm_requires_declared_crs():
    from switchloc.ui.osm_tiles import OsmUnavailableError, fetch_bbox_background
    for crs in (None, ""):
        with pytest.raises(OsmUnavailableError):
            fetch_bbox_background(0.0, 10.0, 0.0, 10.0, crs=crs,
                                  fetch_fn=lambda *a, **k: b"")


def test_no_hardcoded_site_crs_in_ui():
    for rel in ("ui/osm_tiles.py", "ui/qt/map_canvas.py", "ui/qt/main_window.py"):
        code = (SRC / "switchloc" / rel).read_text(encoding="utf-8")
        code = re.sub(r'""".*?"""', "", code, flags=re.S)
        code = re.sub(r"#.*", "", code)
        assert "32639" not in code, rel


# ---------------- Qt enum discipline (static) ----------------
_BAD = [r"QEvent\.(KeyPress|KeyRelease|MouseButtonPress|Drop|DragEnter)\b",
        r"QKeySequence\.(Copy|Paste|Cut|Save|Open|Quit)\b",
        r"\bQt\.(AlignCenter|AlignLeft|AlignRight|AlignTop|AlignBottom|"
        r"AlignVCenter|AlignHCenter)\b",
        r"\bQt\.(UserRole|DisplayRole|ItemIsEditable|ItemIsEnabled|"
        r"ItemIsSelectable|RichText|PlainText|Horizontal|Vertical|"
        r"CustomContextMenu|NoContextMenu|WaitCursor|PointingHandCursor)\b",
        r"QMessageBox\.(Yes|No|Ok|Cancel|Save|Discard)\b",
        r"QAbstractItemView\.(SelectRows|SingleSelection|NoEditTriggers|"
        r"ExtendedSelection|MultiSelection)\b",
        r"QHeaderView\.(Stretch|ResizeToContents|Interactive|Fixed)\b",
        r"QDialog\.(Accepted|Rejected)\b",
        r"QSizePolicy\.(Expanding|Fixed|Preferred|Minimum|Maximum)\b",
        r"QFrame\.(NoFrame|StyledPanel|HLine|VLine)\b",
        r"QPalette\.(Window|Base|Text|Button|Highlight|AlternateBase)\b"]


def test_no_unscoped_qt_enums_in_ui_sources():
    """The shipped GUI crashed four times on short enum aliases that strict
    PySide6 builds removed — keep the whole ui/ tree on scoped enums."""
    offenders = []
    for f in (SRC / "switchloc" / "ui").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        for ln, line in enumerate(text.splitlines(), 1):
            code = line.split("#", 1)[0]
            for pat in _BAD:
                if re.search(pat, code):
                    offenders.append(f"{f.name}:{ln}: {line.strip()[:70]}")
    assert not offenders, "\n".join(offenders)
