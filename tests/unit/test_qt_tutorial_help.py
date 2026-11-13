"""F1's Help action opens the packaged tutorial, not a legacy summary."""
import os
from pathlib import Path
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtGui import QAction, QDesktopServices
    from PySide6.QtWidgets import QApplication, QMainWindow
    HAS_QT = True
except ImportError:
    HAS_QT = False

pytestmark = pytest.mark.skipif(not HAS_QT, reason='Qt Widgets unavailable')


def test_help_opens_packaged_tutorial(monkeypatch, tmp_path):
    from switchloc.ui.qt import main_window
    from switchloc.ui.qt.i18n import t
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv('SWITCHLOC_HOME', str(tmp_path))
    windows, opened = [], []
    show = QMainWindow.show
    def capture(win):
        windows.append(win)
        return show(win)
    monkeypatch.setattr(QMainWindow, 'show', capture)
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url.toLocalFile()) or True)
    def run(_app):
        action = next(a for a in windows[-1].findChildren(QAction)
                      if a.text() == t('Help — study workflow'))
        action.trigger()
        return 0
    monkeypatch.setattr(QApplication, 'exec', run)
    assert main_window.launch(None) == 0
    assert len(opened) == 1
    pdf = Path(opened[0])
    assert pdf.name == 'SwitchLoc_Guide_FA.pdf'
    assert pdf.read_bytes().startswith(b'%PDF-')
