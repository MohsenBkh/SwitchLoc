# -*- coding: utf-8 -*-
"""PySide6 shell (اختیاری — `requirements-qt.txt`).

This package imports PySide6 lazily: importing `switchloc.ui` alone must
never fail on a headless/offline machine (the engineering pipeline and
tests do not need Qt).  Use `qt_available()` to probe.
"""
from __future__ import annotations


def qt_available() -> bool:
    try:
        import PySide6  # noqa: F401
        return True
    except ImportError:
        return False
