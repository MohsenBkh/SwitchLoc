# -*- coding: utf-8 -*-
"""Background execution for heavy services (topology, placement, outages,
import, exports) — the GUI thread never blocks.

Design (all Qt objects are created lazily so this module imports without
PySide6, and the Qt-free parts are unit-testable):

* ``run_task(parent, label, work, on_success, on_error=…)`` runs
  ``work()`` in a ``QThread``; ``on_success(result)`` / ``on_error(exc)``
  are ALWAYS invoked on the GUI thread (delivered through a controller
  ``QObject`` that lives in the GUI thread — never through a bare lambda,
  whose thread affinity differs between Qt bindings).
* While a task runs, editable project content is locked and a cooperative
  Stop action requests cancellation at service/algorithm checkpoints.
* ``call_in_gui(fn)`` lets code that runs in the worker (e.g. the GIS
  import's mapping-confirmation callback) execute a dialog on the GUI
  thread and wait for its result — no deadlock: the worker waits on a
  ``threading.Event`` while the GUI thread processes the request.
* One task at a time; a second request while busy is rejected with a
  message instead of racing on the project database.
* ``SWITCHLOC_SYNC=1`` (or ``sync=True``) runs everything inline on the
  calling thread — used by headless smoke tests and for debugging.

SQLite rule: every worker opens its own ``ProjectStore`` (connections are
never shared across threads).
"""
from __future__ import annotations

import os
import sys
import threading
import traceback
from typing import Any, Callable

from ...logging_setup import get_logger, log_path_text
from ...task_control import (TaskCancelled, TaskControl, activate_task,
                             deactivate_task)

_log = get_logger("ui.worker")
_tls = threading.local()
_STATE: dict = {"busy": False, "keep": [], "task_control": None,
                "dialog": None, "stop_action": None,
                "task_ui_handler": None}


class _GuiRequest:
    """A callable to run on the GUI thread plus its outcome slot."""

    def __init__(self, fn: Callable[[], Any]):
        self.fn = fn
        self.done = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None


def is_busy() -> bool:
    return bool(_STATE["busy"])


def register_stop_action(action) -> None:
    """Register the app-wide Stop action and mirror the current task state."""
    _STATE["stop_action"] = action
    if action is not None:
        action.setEnabled(bool(_STATE["busy"])
                          and not bool(getattr(_STATE.get("task_control"),
                                               "cancelled", False)))


def register_task_ui_handler(handler: Callable[[bool], None] | None) -> None:
    """Disable editable project content while a background task is active."""
    _STATE["task_ui_handler"] = handler


def _notify_task_ui(busy: bool) -> None:
    handler = _STATE.get("task_ui_handler")
    if handler is not None:
        handler(bool(busy))


def cancel_current_task() -> bool:
    """Request safe cooperative cancellation of the current background task."""
    control = _STATE.get("task_control")
    if not _STATE["busy"] or control is None or control.cancelled:
        return False
    control.cancel()
    dialog = _STATE.get("dialog")
    if dialog is not None:
        dialog.setLabelText("لغو درخواست شد؛ در انتظار توقف ایمن فرایند…")
        button = dialog.cancelButton()
        if button is not None:
            button.setEnabled(False)
    action = _STATE.get("stop_action")
    if action is not None:
        action.setEnabled(False)
    return True


def call_in_gui(fn: Callable[[], Any]) -> Any:
    """Run ``fn()`` on the GUI thread and return its result.

    Called from the worker thread; when there is no worker (sync mode or
    plain GUI thread) it simply calls ``fn()``.
    """
    emitter = getattr(_tls, "emit_request", None)
    if emitter is None:
        return fn()
    req = _GuiRequest(fn)
    emitter(req)
    req.done.wait()
    if req.error is not None:
        raise req.error
    return req.result


def _sync_mode(sync: bool | None) -> bool:
    if sync is not None:
        return bool(sync)
    return os.environ.get("SWITCHLOC_SYNC", "") not in ("", "0")


def _default_error(parent, title: str, exc: BaseException) -> None:
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.critical(
        parent, title,
        f"{exc}\n\nDetails were saved to:\n{log_path_text()}")


def error_box(parent, title: str) -> Callable[[BaseException], None]:
    """``on_error`` callback: a critical message box with the log path."""
    return lambda exc: _default_error(parent, title, exc)


def run_task(parent, label: str, work: Callable[[], Any],
             on_success: Callable[[Any], None],
             on_error: Callable[[BaseException], None] | None = None,
             title: str = "SwitchLoc", sync: bool | None = None,
             on_cancel: Callable[[], None] | None = None) -> bool:
    """Run ``work`` off the GUI thread; return False if rejected (busy)."""
    if _STATE["busy"]:
        _log.warning("task '%s' rejected: another task is running", label)
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                parent, title,
                "Another operation is still running — please wait for it "
                "to finish.")
        except Exception:                          # noqa: BLE001
            pass
        return False

    def fail(exc: BaseException) -> None:
        _log.error("task '%s' failed:\n%s", label, "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)))
        (on_error or (lambda e: _default_error(parent, title, e)))(exc)

    if _sync_mode(sync):
        control = TaskControl()
        _STATE.update(busy=True, task_control=control)
        _notify_task_ui(True)
        action = _STATE.get("stop_action")
        if action is not None:
            action.setEnabled(False)  # synchronous mode cannot process UI input
        token = activate_task(control)
        try:
            try:
                result = work()
                control.check_cancelled()
            except TaskCancelled:
                if on_cancel is not None:
                    on_cancel()
                return True
            except Exception as exc:               # noqa: BLE001
                fail(exc)
                return True
            on_success(result)
        finally:
            deactivate_task(token)
            _STATE.update(busy=False, task_control=None)
            _notify_task_ui(False)
            if action is not None:
                action.setEnabled(False)
        return True

    from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
    from PySide6.QtWidgets import QApplication, QProgressDialog

    class _Worker(QObject):
        finished = Signal(object)
        failed = Signal(object)
        cancelled = Signal()
        progress = Signal(int, str)
        gui_request = Signal(object)

        def __init__(self, fn, task_control):
            super().__init__()
            self._fn = fn
            self._task_control = task_control

        @Slot()
        def run(self):
            _tls.emit_request = self.gui_request.emit
            self._task_control._progress_callback = self.progress.emit
            token = activate_task(self._task_control)
            try:
                self._task_control.check_cancelled()
                result = self._fn()
                self._task_control.check_cancelled()
                self.finished.emit(result)
            except TaskCancelled:
                self.cancelled.emit()
            except BaseException as exc:           # noqa: BLE001 — marshalled
                self.failed.emit(exc)
            finally:
                deactivate_task(token)
                self._task_control._progress_callback = None
                _tls.emit_request = None

    class _Controller(QObject):
        """Lives in the GUI thread; receives every worker signal."""

        def __init__(self, dialog, thread):
            super().__init__()
            self.dialog = dialog
            self.thread = thread
            self._ending = False
            self._worker_signal_seen = False
            self._thread_stopped = False
            self._released = False
            self._after_stop = None

        def _request_end(self, callback):
            """Keep the app busy until QThread confirms it has actually exited."""
            self._after_stop = callback
            self._worker_signal_seen = True
            if not self._ending:
                self._ending = True
                self.dialog.close()
                self.dialog.deleteLater()
                self.thread.quit()
            self._maybe_release()

        def _maybe_release(self):
            if self._released or not (self._worker_signal_seen and self._thread_stopped):
                return
            self._released = True
            _STATE.update(busy=False, task_control=None, dialog=None)
            _notify_task_ui(False)
            action = _STATE.get("stop_action")
            if action is not None:
                action.setEnabled(False)
            if self in _STATE["keep"]:
                _STATE["keep"].remove(self)
            QApplication.restoreOverrideCursor()
            callback, self._after_stop = self._after_stop, None
            if callback is not None:
                callback()

        @Slot()
        def on_thread_stopped(self):
            self._thread_stopped = True
            self._maybe_release()

        @Slot(object)
        def on_finished(self, result):
            def deliver():
                try:
                    on_success(result)
                except Exception as exc:           # noqa: BLE001
                    fail(exc)
            self._request_end(deliver)

        @Slot(object)
        def on_failed(self, exc):
            self._request_end(lambda: fail(exc))

        @Slot()
        def on_cancelled(self):
            self._request_end(on_cancel or (lambda: None))

        @Slot(int, str)
        def on_progress(self, percent, message):
            if self.dialog.minimum() == self.dialog.maximum():
                self.dialog.setRange(0, 100)
            self.dialog.setValue(percent)
            if message:
                self.dialog.setLabelText(message)

        @Slot(object)
        def on_gui_request(self, req):
            # hide the busy dialog so the requested dialog is usable
            self.dialog.hide()
            try:
                req.result = req.fn()
            except BaseException as exc:           # noqa: BLE001
                req.error = exc
            finally:
                self.dialog.show()
                req.done.set()

    dialog = QProgressDialog(label, None, 0, 0, parent)
    dialog.setWindowTitle(title)
    # The main window is temporarily locked except for its universal Stop
    # action; a modeless dialog lets that toolbar button remain reachable.
    dialog.setWindowModality(Qt.WindowModality.NonModal)
    dialog.setMinimumDuration(0)
    dialog.setCancelButtonText("لغو فرایند")
    dialog.canceled.connect(cancel_current_task)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)

    thread = QThread()
    task_control = TaskControl()
    worker = _Worker(work, task_control)
    worker.moveToThread(thread)
    controller = _Controller(dialog, thread)
    thread.finished.connect(controller.on_thread_stopped)
    worker.finished.connect(controller.on_finished)
    worker.failed.connect(controller.on_failed)
    worker.cancelled.connect(controller.on_cancelled)
    worker.progress.connect(controller.on_progress)
    worker.gui_request.connect(controller.on_gui_request)
    thread.started.connect(worker.run)
    controller._worker = worker                    # keep alive with controller
    _STATE.update(busy=True, task_control=task_control, dialog=dialog)
    _notify_task_ui(True)
    action = _STATE.get("stop_action")
    if action is not None:
        action.setEnabled(True)
    _STATE["keep"].append(controller)
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    dialog.show()
    thread.start()
    return True


def install_excepthook(parent_getter: Callable[[], Any] | None = None) -> None:
    """Route uncaught exceptions (incl. those raised in Qt slots) to the log
    and a message box — a crash is never silent and never lost."""
    def hook(et, ev, tb):
        text = "".join(traceback.format_exception(et, ev, tb))
        _log.critical("uncaught exception:\n%s", text)
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                parent_getter() if parent_getter else None,
                "SwitchLoc — unexpected error",
                f"{et.__name__}: {ev}\n\nDetails were saved to:\n"
                f"{log_path_text()}")
        except Exception:                          # noqa: BLE001
            sys.__excepthook__(et, ev, tb)
    sys.excepthook = hook
