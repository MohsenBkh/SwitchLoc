# -*- coding: utf-8 -*-
"""v1.9 UI shell — Qt-free helpers (always run) + GUI smoke (offscreen)."""
import os
import re
import xml.dom.minidom as minidom
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

UI = Path(__file__).resolve().parents[2] / "src" / "switchloc" / "ui" / "qt"


# ---------------- pure helpers ----------------
def test_recent_list_helpers():
    from switchloc.ui.qt.chrome import MAX_RECENT, normalize_recent, push_recent
    assert normalize_recent(None) == []
    assert normalize_recent("a") == ["a"]            # QSettings single item
    assert normalize_recent(["a", "a", "", "b"]) == ["a", "b"]
    assert push_recent(["a", "b", "c"], "b") == ["b", "a", "c"]
    assert len(push_recent([str(i) for i in range(30)], "z")) == MAX_RECENT


def test_workflow_html_marks_states():
    from switchloc.ui.qt.chrome import WORKFLOW_ORDER, workflow_html
    from switchloc.ui.qt.theme import LIGHT
    html = workflow_html("Placement", LIGHT)
    assert html.count("&#10004;") == WORKFLOW_ORDER.index("Placement")
    assert html.count("&#9654;") == 1
    assert html.count("&#9675;") == len(WORKFLOW_ORDER) - 3


def test_icons_are_wellformed_svg():
    from switchloc.ui.qt import icons
    names = icons.available()
    assert len(names) >= 20
    for n in names:
        doc = minidom.parseString(icons.svg_text(n, "#123456"))
        assert doc.documentElement.tagName == "svg"
    for must in ("import", "topology", "placement", "dashboard", "map",
                 "settings", "export", "approve", "folder", "run", "outage",
                 "database", "moon", "help", "info"):
        assert must in names


def test_qss_balanced_for_both_themes():
    from switchloc.ui.qt.theme import THEMES, build_qss
    for mode, tokens in THEMES.items():
        q = build_qss(tokens)
        assert q.count("{") == q.count("}"), mode
        assert "{c[" not in q and "None" not in q


def test_theme_tokens_complete_and_distinct():
    from switchloc.ui.qt.theme import DARK, LIGHT
    assert set(LIGHT) == set(DARK)
    for k, v in LIGHT.items():
        if k != "name":
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", v), k
    assert LIGHT["bg"] != DARK["bg"]


def test_i18n_translation_and_fallback():
    from switchloc.ui.qt import i18n
    try:
        i18n.set_language("fa")
        assert i18n.t("Topology") == "توپولوژی"
        assert i18n.t("not in catalog") == "not in catalog"
        assert i18n.is_rtl()
        i18n.set_language("xx")                     # invalid -> English
        assert i18n.t("Topology") == "Topology" and not i18n.is_rtl()
    finally:
        i18n.set_language("en")


def test_every_chrome_string_has_a_persian_translation():
    """All literals passed to t(...) / act(...) in the shell must exist in the
    catalog so the Persian UI has no English holes in the chrome."""
    from switchloc.ui.qt.i18n import FA
    missing = set()
    for fname in ("chrome.py", "main_window.py"):
        src = (UI / fname).read_text(encoding="utf-8")
        for m in re.finditer(r'\bt\(\s*"([^"]+)"\s*\)', src):
            if m.group(1) not in FA:
                missing.add(m.group(1))
        if fname == "chrome.py":
            for m in re.finditer(r'\bact\(\s*"([^"]+)"', src):
                if m.group(1) not in FA:
                    missing.add(m.group(1))
    # tooltip-only phrase used as ``tip=`` is also translated through t()
    assert not missing, sorted(missing)


# ---------------- worker (sync mode, Qt-free) ----------------
def test_worker_sync_success_error_and_gui_call(monkeypatch):
    monkeypatch.setenv("SWITCHLOC_SYNC", "1")
    from switchloc.ui.qt import worker as w
    out = []
    assert w.run_task(None, "x", lambda: 5, lambda r: out.append(("ok", r)))
    w.run_task(None, "x", lambda: 1 / 0, lambda r: out.append(("ok", r)),
               on_error=lambda e: out.append(("err", type(e).__name__)))
    w.run_task(None, "x", lambda: w.call_in_gui(lambda: 7),
               lambda r: out.append(("gui", r)))
    assert out == [("ok", 5), ("err", "ZeroDivisionError"), ("gui", 7)]
    assert not w.is_busy()


def test_worker_success_callback_error_is_reported(monkeypatch):
    monkeypatch.setenv("SWITCHLOC_SYNC", "1")
    from switchloc.ui.qt import worker as w
    seen = []

    def boom(_r):
        raise RuntimeError("in-callback")
    with pytest.raises(RuntimeError):
        w.run_task(None, "x", lambda: 1, boom,
                   on_error=lambda e: seen.append(e))
    assert not w.is_busy()          # never stuck busy after a failure


# ---------------- GUI smoke (needs PySide6; offscreen) ----------------
def _qapp():
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_icons_render_with_qt():
    app = _qapp()
    from switchloc.ui.qt import icons
    ic = icons.icon("run", "#112233", 24)
    assert ic is not None and not ic.isNull()
    assert app is not None


def test_theme_applies_both_modes():
    app = _qapp()
    from switchloc.ui.qt.theme import apply_theme
    for mode in ("light", "dark"):
        tokens = apply_theme(app, mode, None)
        assert tokens["name"] == mode
        assert app.styleSheet().strip()


def _shell():
    app = _qapp()
    from PySide6.QtWidgets import QLabel, QMainWindow, QTabWidget, QWidget
    from switchloc.ui.qt.chrome import install_chrome
    win = QMainWindow()
    tabs = QTabWidget()
    for n in ("Data Import", "Topology", "Placement", "Dashboard", "Map"):
        tabs.addTab(QWidget(), n)
    calls = []
    keys = ("import_gis", "import_outage", "per_feeder", "topology",
            "placement", "settings", "exports", "approve", "map_style",
            "help", "about")
    handlers = {k: (lambda k=k: calls.append(k)) for k in keys}
    handlers["open_project"] = lambda p=None: calls.append(("open", p))
    wf = QLabel("")
    ch = install_chrome(win, app, tabs, wf, handlers, None, "9.9.9")
    win.setCentralWidget(ch.central)
    return app, win, tabs, ch, calls


def test_chrome_builds_and_navigates():
    app, win, tabs, ch, calls = _shell()
    assert len(ch._nav_buttons) == 5
    ch._nav_buttons[2].click()
    assert tabs.currentIndex() == 2
    tabs.setCurrentIndex(3)
    assert ch._nav_buttons[3].isChecked()
    ch._actions["topology"].trigger()
    ch._actions["open"].trigger()
    assert "topology" in calls and ("open", None) in calls
    ch.set_project_info("demo", 7, "EPSG:32639")
    assert "demo" in win.windowTitle()
    ch.set_workflow("Topology")
    assert "Topology" in ch.workflow_label.text()


def test_chrome_theme_toggle_and_recent(tmp_path):
    app, win, tabs, ch, calls = _shell()
    from PySide6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.NativeFormat,
                      QSettings.Scope.UserScope, str(tmp_path))
    start = ch.mode
    ch.toggle_theme()
    assert ch.mode != start
    ch.toggle_theme()
    assert ch.mode == start
    proj = tmp_path / "p.sqlite"
    proj.write_bytes(b"")
    ch.add_recent(str(proj))
    assert str(proj) in ch.recent()
    ch.clear_recent()
    assert ch.recent() == []


def test_run_task_threaded_roundtrip_and_gui_call(monkeypatch):
    monkeypatch.delenv("SWITCHLOC_SYNC", raising=False)
    app = _qapp()
    from PySide6.QtCore import QEventLoop, QThread, QTimer
    from switchloc.ui.qt import worker as w
    main_thread = QThread.currentThread()
    got = {}

    def work():
        got["worker_thread"] = QThread.currentThread()
        return w.call_in_gui(lambda: QThread.currentThread())

    loop = QEventLoop()

    def done(res):
        got["gui_call_thread"] = res
        got["done_thread"] = QThread.currentThread()
        loop.quit()

    def fail(exc):
        got["error"] = exc
        loop.quit()

    assert w.run_task(None, "t", work, done, fail, sync=False)
    QTimer.singleShot(15000, loop.quit)             # never hang CI
    loop.exec()
    assert "error" not in got, got.get("error")
    assert got["worker_thread"] != main_thread       # really off the GUI thread
    assert got["gui_call_thread"] == main_thread     # dialog code on GUI thread
    assert got["done_thread"] == main_thread         # callbacks on GUI thread
    assert not w.is_busy()
    assert app is not None


def test_run_task_threaded_error_is_marshalled(monkeypatch):
    monkeypatch.delenv("SWITCHLOC_SYNC", raising=False)
    _qapp()
    from PySide6.QtCore import QEventLoop, QTimer
    from switchloc.ui.qt import worker as w
    got = {}
    loop = QEventLoop()
    w.run_task(None, "t", lambda: 1 / 0, lambda r: loop.quit(),
               lambda e: (got.setdefault("e", e), loop.quit()), sync=False)
    QTimer.singleShot(15000, loop.quit)
    loop.exec()
    assert isinstance(got.get("e"), ZeroDivisionError)
    assert not w.is_busy()
