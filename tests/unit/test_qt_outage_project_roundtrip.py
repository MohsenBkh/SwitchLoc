"""Real UI path: select a per-feeder workbook, Save As, reopen and process."""
from __future__ import annotations
import os
from pathlib import Path
import sqlite3
import shutil
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox, QPushButton, QTableWidget, QTextEdit
    HAS_QT = True
except ImportError:
    HAS_QT = False

pytestmark = pytest.mark.skipif(not HAS_QT, reason='PySide6.QtWidgets unavailable')


def test_select_save_as_reopen_process_and_view(tmp_path, monkeypatch):
    from switchloc.ui.qt import main_window, outage_history_dialog
    from switchloc.persistence.store import ProjectStore
    from switchloc.persistence.outage_workbooks import list_workbooks
    root = Path(__file__).resolve().parents[2]
    original = root / 'Kosar GIS.sqlite'
    source = root / '1.xlsx'
    source2 = root / '2.xlsx'
    if not original.exists() or not source.exists() or not source2.exists():
        pytest.skip('real input fixtures unavailable')
    first, copy, excel = tmp_path/'first.sqlite', tmp_path/'copy.sqlite', tmp_path/'input.xlsx'
    excel2 = tmp_path/'input2.xlsx'
    with sqlite3.connect(original) as src, sqlite3.connect(first) as dst: src.backup(dst)
    shutil.copyfile(source, excel)
    shutil.copyfile(source2, excel2)
    monkeypatch.setenv('SWITCHLOC_HOME', str(tmp_path))
    monkeypatch.setenv('SWITCHLOC_SYNC', '1')
    app = QApplication.instance() or QApplication([])
    windows = []
    real_show = QMainWindow.show
    def show(window):
        windows.append(window)
        return real_show(window)
    monkeypatch.setattr(QMainWindow, 'show', show)
    messages = []
    def information(*args):
        messages.append(str(args[-1])); return QMessageBox.StandardButton.Ok
    def critical(*args):
        raise AssertionError('dialog error: ' + str(args[-1]))
    monkeypatch.setattr(QMessageBox, 'information', information)
    monkeypatch.setattr(QMessageBox, 'warning', critical)
    monkeypatch.setattr(QMessageBox, 'critical', critical)
    selections = iter((str(excel), str(excel2)))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **k: (next(selections), ''))
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **k: (str(copy), ''))
    rounds = {'n': 0}
    def execute(_app):
        win = windows[-1]
        tables = [t for t in win.findChildren(QTableWidget)
                  if t.columnCount() == 2 and t.horizontalHeaderItem(1)
                  and t.horizontalHeaderItem(1).text() == 'Outage workbook (xlsx)']
        assert len(tables) == 1
        table = tables[0]
        if rounds['n'] == 0:
            row = next(i for i in range(table.rowCount()) if table.item(i, 0).text() == 'F3 - KOSAR')
            table.doubleClicked.emit(table.model().index(row, 0))
            assert 'input.xlsx' in table.item(row, 1).text()
            assert list_workbooks(str(first))['F3 - KOSAR']['filename'] == 'input.xlsx'
            row2 = next(i for i in range(table.rowCount()) if table.item(i, 0).text() == 'F5 - KOSAR')
            table.doubleClicked.emit(table.model().index(row2, 0))
            assert 'input2.xlsx' in table.item(row2, 1).text()
            actions = [a for a in win.findChildren(QAction) if 'Save project as' in a.text()]
            assert actions
            actions[0].trigger()
            assert copy.exists()
            excel.unlink()
            excel2.unlink()
        elif rounds['n'] == 1:
            row = next(i for i in range(table.rowCount()) if table.item(i, 0).text() == 'F3 - KOSAR')
            assert 'input.xlsx' in table.item(row, 1).text()
            row2 = next(i for i in range(table.rowCount()) if table.item(i, 0).text() == 'F5 - KOSAR')
            assert 'input2.xlsx' in table.item(row2, 1).text()
            buttons = [b for b in win.findChildren(QPushButton) if 'Process per-feeder outage files' in b.text()]
            assert buttons
            buttons[0].click()
            store = ProjectStore(str(copy))
            try: data = store.load_outages()
            finally: store.close()
            assert len(data['events']) == 5407
            captured = []
            monkeypatch.setattr(outage_history_dialog, 'show_outage_history',
                                lambda parent, rows: captured.extend(rows))
            view = next(b for b in win.findChildren(QPushButton) if b.text() == 'مشاهده سوابق خاموشی')
            view.click()
            assert len(captured) == 5407
        else:
            row = next(i for i in range(table.rowCount()) if table.item(i, 0).text() == 'F3 - KOSAR')
            assert 'input.xlsx' in table.item(row, 1).text()
            assert any('5,407' in t.toPlainText() for t in win.findChildren(QTextEdit))
            captured = []
            monkeypatch.setattr(outage_history_dialog, 'show_outage_history',
                                lambda parent, rows: captured.extend(rows))
            next(b for b in win.findChildren(QPushButton) if b.text() == 'مشاهده سوابق خاموشی').click()
            assert len(captured) == 5407
        rounds['n'] += 1
        return 0
    monkeypatch.setattr(QApplication, 'exec', execute)
    assert main_window.launch(str(first)) == 0
    assert main_window.launch(str(copy)) == 0
    assert main_window.launch(str(copy)) == 0
    assert rounds['n'] == 3


def test_history_view_retrieves_rows_without_topology(monkeypatch):
    from PySide6.QtWidgets import QDialog, QTableView
    from switchloc.ui.qt.outage_history_dialog import show_outage_history
    app = QApplication.instance() or QApplication([])
    captured = []
    def exec_dialog(dlg):
        table = dlg.findChild(QTableView)
        model = table.model()
        captured.append((model.rowCount(), model.index(0, 0).data(), model.index(0, 1).data()))
        return 0
    monkeypatch.setattr(QDialog, 'exec', exec_dialog)
    show_outage_history(None, [{'event_no': '42', 'feeder_key': 'F1 - MESHKIN'}])
    assert captured == [(1, '42', 'F1 - MESHKIN')]
