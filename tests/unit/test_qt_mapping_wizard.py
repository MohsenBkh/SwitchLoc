# -*- coding: utf-8 -*-
"""Regression: Qt dialog-code enums must be accessed in scoped form.

The shipped GUI crashed on 'OK' with
  AttributeError: 'PySide6.QtWidgets.QDialog' object has no attribute
  'Accepted'
because instance-level unscoped enum access was removed in recent
PySide6 releases.  These tests pin the fixed behaviour of
MappingWizardPage.exec(); they are skipped automatically when PySide6
is not installed (headless CI without Qt).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                    # noqa: E402

QtWidgets = pytest.importorskip("PySide6.QtWidgets")   # noqa: E402


def test_dialogcode_accepted_is_scoped():
    from PySide6.QtWidgets import QDialog
    assert int(QDialog.DialogCode.Accepted) == 1
    assert int(QDialog.DialogCode.Rejected) == 0


@pytest.mark.parametrize("code,expected", [(1, True), (0, False)])
def test_wizard_exec_maps_dialog_code(monkeypatch, code, expected):
    from switchloc.ui.qt.mapping_wizard import MappingWizardPage
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    page = MappingWizardPage([], None, [], None)
    monkeypatch.setattr(type(page.dialog), "exec", lambda self: code)
    assert page.exec() is expected
