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
* While a task runs a busy ``QProgressDialog`` blocks input to the parent
  window (the services have no cancellation points, so no fake Cancel).
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

_log = get_logger("ui.worker")
_tls = threading.local()
_STATE: dict = {"busy": False, "keep": []}


class _GuiRequest:
    """A callable to run on the GUI thread plus its outcome slot."""

    def __init__(self, fn: Callable[[], Any]):
        self.fn = fn
        self.done = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None


def is_busy() -> bool:
    return bool(_STATE["busy"])


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
             title: str = "SwitchLoc", sync: bool | None = None) -> bool:
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
        _STATE["busy"] = True
        try:
            try:
                result = work()
            except Exception as exc:               # noqa: BLE001
                fail(exc)
                return True
            on_success(result)
        finally:
            _STATE["busy"] = False
        return True

    from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
    from PySide6.QtWidgets import QApplication, QProgressDialog

    class _Worker(QObject):
        finished = Signal(object)
        failed = Signal(object)
        gui_request = Signal(object)

        def __init__(self, fn):
            super().__init__()
            self._fn = fn

        @Slot()
        def run(self):
            _tls.emit_request = self.gui_request.emit
            try:
                self.finished.emit(self._fn())
            except BaseException as exc:           # noqa: BLE001 — marshalled
                self.failed.emit(exc)
            finally:
                _tls.emit_request = None

    class _Controller(QObject):
        """Lives in the GUI thread; receives every worker signal."""

        def __init__(self, dialog, thread):
            super().__init__()
            self.dialog = dialog
            self.thread = thread

        def _end(self):
            try:
                self.dialog.close()
                self.dialog.deleteLater()
            finally:
                self.thread.quit()
                self.thread.wait(5000)
                _STATE["busy"] = False
                if self in _STATE["keep"]:
                    _STATE["keep"].remove(self)
                QApplication.restoreOverrideCursor()

        @Slot(object)
        def on_finished(self, result):
            self._end()
            try:
                on_success(result)
            except Exception as exc:               # noqa: BLE001
                fail(exc)

        @Slot(object)
        def on_failed(self, exc):
            self._end()
            fail(exc)

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
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setMinimumDuration(0)
    dialog.setCancelButton(None)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)

    thread = QThread()
    worker = _Worker(work)
    worker.moveToThread(thread)
    controller = _Controller(dialog, thread)
    worker.finished.connect(controller.on_finished)
    worker.failed.connect(controller.on_failed)
    worker.gui_request.connect(controller.on_gui_request)
    thread.started.connect(worker.run)
    controller._worker = worker                    # keep alive with controller
    _STATE["keep"].append(controller)
    _STATE["busy"] = True
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
