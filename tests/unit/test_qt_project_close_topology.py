"""Exercise the toolbar, one-shot topology rendering and project close."""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget, QToolBar, QFileDialog
    from PySide6.QtGui import QAction
    HAS_QT = True
except ImportError:
    HAS_QT = False
pytestmark = pytest.mark.skipif(not HAS_QT, reason='Qt Widgets unavailable')


def test_topology_once_and_close_cancel_then_discard(tmp_path, monkeypatch):
    from switchloc.ui.qt import main_window
    from switchloc.ui.qt.i18n import t
    from switchloc.ui.qt import settings_dialog
    source = Path(__file__).resolve().parents[2] / 'Kosar GIS.sqlite'
    if not source.exists():
        pytest.skip('project fixture unavailable')
    project = tmp_path / 'project.sqlite'
    with sqlite3.connect(source) as src, sqlite3.connect(project) as dst:
        src.backup(dst)
    monkeypatch.setenv('SWITCHLOC_HOME', str(tmp_path))
    monkeypatch.setenv('SWITCHLOC_SYNC', '1')
    app = QApplication.instance() or QApplication([])
    windows = []
    show = QMainWindow.show
    def record_show(win):
        windows.append(win)
        return show(win)
    monkeypatch.setattr(QMainWindow, 'show', record_show)
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: QMessageBox.StandardButton.Ok)
    def fail(*args):
        raise AssertionError(str(args[-1]))
    monkeypatch.setattr(QMessageBox, 'critical', fail)
    monkeypatch.setattr(QMessageBox, 'warning', fail)
    answers = iter([QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Discard])
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: next(answers))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(project), ''))
    captured = []
    class Settings:
        def __init__(self, current):
            self.current = current
        def exec(self):
            return 1
        def apply(self):
            return {'load_model': {'level': 'scaled', 'loading_factor': .7,
                    'substitute_factor': .5, 'feeder_pq': {
                        'F3 - KOSAR': {'p_kw': 1234, 'q_kvar': 222}}},
                    'criteria': {}, 'coverage': {}, 'cost_model': {}, 'capacity_rows': []}
    def dialog(_parent, _keys, current, **kwargs):
        captured.append(current['load_model'])
        return Settings(current)
    monkeypatch.setattr(settings_dialog, 'make_settings_dialog', dialog)
    def exec_app(_app):
        win = windows[-1]
        toolbar = win.findChild(QToolBar, 'MainToolBar')
        save = next(a for a in toolbar.actions() if a.text() == t('Save project'))
        assert not save.icon().isNull()
        settings = next(a for a in toolbar.actions() if a.text() == t('Settings'))
        settings.trigger()
        tabs = next(x for x in win.findChildren(QTabWidget) if x.count() == 6
                    and x.tabText(5) == 'Map')
        m = tabs.widget(5)
        sec = tabs.widget(3)
        sec.sp_depth.setValue(sec.sp_depth.value() + 1)
        save.trigger()  # flush the pending debounced settings before checkpoint
        from switchloc.persistence.store import ProjectStore
        store = ProjectStore(project)
        saved_settings = store.get_kv('sectionalizer_settings')
        store.close()
        assert saved_settings['min_candidate_depth'] == sec.sp_depth.value()
        action = next(a for a in toolbar.actions() if a.text() == t('Run topology'))
        action.trigger()
        assert tabs.currentWidget() is m
        assert m._renderer is not None
        assert m.canvas.map_renderer is not None
        close = next(a for a in win.findChildren(QAction) if a.text() == t('Close project'))
        close.trigger()
        assert tabs.currentWidget() is m and m._renderer is not None  # Cancel
        close.trigger()
        assert tabs.currentIndex() == 0
        assert m._renderer is None and m.canvas.map_renderer is None
        assert not m.canvas.fig.axes
        assert win.isVisible()
        next(a for a in toolbar.actions() if a.text() == t('Open project…')).trigger()
        assert m._renderer is None
        settings.trigger()
        assert captured[-1]['feeder_pq']['F3 - KOSAR'] == {'p_kw': 1234, 'q_kvar': 222}
        return 0
    monkeypatch.setattr(QApplication, 'exec', exec_app)
    assert main_window.launch(str(project)) == 0
