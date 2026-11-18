"""Cooperative cancellation and progress for long-running application tasks.

This module is deliberately UI-agnostic: services and algorithms can check a
request to stop without depending on Qt. Callers that do not run inside a
managed task retain the current behavior (the checks are no-ops).
"""
from __future__ import annotations

from contextvars import ContextVar
from threading import Event
from typing import Callable


class TaskCancelled(Exception):
    """Raised at a safe checkpoint after the user requests cancellation."""


class TaskControl:
    def __init__(self, progress_callback: Callable[[int, str], None] | None = None):
        self.cancel_event = Event()
        self._progress_callback = progress_callback

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def cancel(self) -> None:
        self.cancel_event.set()

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise TaskCancelled("Operation cancelled by user")

    def report_progress(self, percent: int | float, message: str = "") -> None:
        if self._progress_callback is not None:
            self._progress_callback(max(0, min(100, int(percent))), str(message))


_CURRENT: ContextVar[TaskControl | None] = ContextVar(
    "switchloc_task_control", default=None)


def current_task_control() -> TaskControl | None:
    return _CURRENT.get()


def activate_task(control: TaskControl):
    """Set the current control for this thread/context; return reset token."""
    return _CURRENT.set(control)


def deactivate_task(token) -> None:
    _CURRENT.reset(token)


def check_cancelled() -> None:
    control = _CURRENT.get()
    if control is not None:
        control.check_cancelled()


def report_progress(percent: int | float, message: str = "") -> None:
    control = _CURRENT.get()
    if control is not None:
        control.report_progress(percent, message)
