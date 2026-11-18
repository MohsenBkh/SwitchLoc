from __future__ import annotations

import pytest

from conftest import NetBuilder
from switchloc.domain.entities import StudyRunMeta
from switchloc.persistence.store import ProjectStore
from switchloc.task_control import (TaskCancelled, TaskControl, activate_task,
                                    check_cancelled, current_task_control,
                                    deactivate_task, report_progress)
from switchloc.validation.issues import IssueLog


def test_check_cancelled_is_a_noop_without_managed_task():
    check_cancelled()
    report_progress(50, "outside task")
    assert current_task_control() is None


def test_task_control_reports_clamped_integer_progress_and_cancels():
    updates = []
    control = TaskControl(lambda percent, message: updates.append((percent, message)))
    token = activate_task(control)
    try:
        report_progress(-10, "start")
        report_progress(52.8, "working")
        report_progress(110, "done")
        assert updates == [(0, "start"), (52, "working"), (100, "done")]
        control.cancel()
        with pytest.raises(TaskCancelled):
            check_cancelled()
    finally:
        deactivate_task(token)
    assert current_task_control() is None


def test_cancelled_network_persist_rolls_back_partial_transaction(tmp_path):
    builder = NetBuilder()
    builder.source(0, 0, "F1")
    builder.line([(0, 0), (50, 0), (100, 0)], feeder="F1")
    store = ProjectStore(tmp_path / "cancelled.sqlite")
    run = StudyRunMeta(project_name="cancelled", started_at="2026-11-14T00:00:00Z",
                       user="test", algo_version="test")
    control = TaskControl()
    token = activate_task(control)
    control.cancel()
    try:
        with pytest.raises(TaskCancelled):
            store.save_network(builder.net, IssueLog(), run)
    finally:
        deactivate_task(token)
    assert store.runs() == []
    store.close()


def test_cancel_current_task_disables_progress_cancel_button_without_qt_dialog_api():
    from switchloc.ui.qt import worker

    class FakeButton:
        def __init__(self):
            self.enabled = True
            self.text = "لغو فرایند"

        def setEnabled(self, value):
            self.enabled = bool(value)

        def setText(self, value):
            self.text = value

    class FakeDialog:
        def __init__(self):
            self.label = ""
            self.cancel_removed = False

        def setLabelText(self, value):
            self.label = value

        def setCancelButton(self, button):
            assert button is None
            self.cancel_removed = True

    saved = worker._STATE.copy()

    worker._STATE.update(busy=True, task_control=TaskControl(),
                         dialog=FakeDialog(), progress_cancel_button=FakeButton())
    try:
        assert worker.cancel_current_task() is True
        assert worker._STATE["task_control"].cancelled is True
        assert worker._STATE["progress_cancel_button"].enabled is False
        assert worker._STATE["progress_cancel_button"].text == "لغو درخواست شد"
    finally:
        worker._STATE.clear()
        worker._STATE.update(saved)

    dialog = FakeDialog()
    worker._STATE.update(busy=True, task_control=TaskControl(),
                         dialog=dialog, progress_cancel_button=None)
    try:
        assert worker.cancel_current_task() is True
        assert dialog.cancel_removed is True
    finally:
        worker._STATE.clear()
        worker._STATE.update(saved)
