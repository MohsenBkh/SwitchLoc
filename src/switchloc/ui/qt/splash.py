# -*- coding: utf-8 -*-
"""Splash screen with a real progress bar (نیاز ۲ — نوار لودینگ).

A `QSplashScreen` drawn from the bundled splash image hosts a
`QProgressBar`; every start-up step (`step(msg, weight)`) advances the
bar and keeps the event loop alive.  The splash stays visible until the
main window is actually shown (`finish(win)`) — the bar never lies:
its weights sum to 100 % across the real init steps.

Qt lives only inside the factory (`make_splash`), the weights table is
Qt-free and testable (same discipline as map_canvas.py / dashboard_tab).
"""
from __future__ import annotations

#: start-up steps and their share of the progress bar (sums to 100)
SPLASH_STEPS: list[tuple[str, int]] = [
    ("Loading engineering modules…", 25),
    ("Building interface…", 15),
    ("Preparing map canvas…", 10),
    ("Opening project…", 20),
    ("Preparing dashboard…", 10),
    ("Ready — starting interface…", 20),
]


def cumulative_progress(done_steps: int) -> int:
    """Bar value (0-100) after ``done_steps`` completed steps."""
    done_steps = max(0, min(done_steps, len(SPLASH_STEPS)))
    return sum(w for _m, w in SPLASH_STEPS[:done_steps])


def make_splash(app):                                # pragma: no cover (Qt)
    """Return ``(splash, step_fn)``; ``(None, no-op)`` without assets."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QProgressBar, QSplashScreen

    from .main_window import _asset_dir

    splash_img = _asset_dir() / "splash.png"
    if not splash_img.exists():
        def _noop(_msg: str = "") -> None:
            return None
        return None, _noop

    splash = QSplashScreen(QPixmap(str(splash_img)))
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setTextVisible(False)
    bar.setFixedHeight(10)
    bar.setStyleSheet(
        "QProgressBar { background: rgba(255,255,255,60);"
        " border: 1px solid #90a4ae; border-radius: 4px; }"
        "QProgressBar::chunk { background: #1e88e5;"
        " border-radius: 3px; }")
    # QSplashScreen is a plain QWidget: a layout with a bottom margin
    # pins the bar over the lower part of the splash image
    from PySide6.QtWidgets import QVBoxLayout
    lay = QVBoxLayout(splash)
    lay.setContentsMargins(28, 0, 28, 52)
    lay.addStretch(1)
    lay.addWidget(bar)

    state = {"done": 0}

    def step(msg: str = "") -> None:
        """Advance the bar by one planned step and pump the UI."""
        state["done"] += 1
        bar.setValue(min(100, cumulative_progress(state["done"])))
        if msg:
            splash.showMessage(msg, Qt.AlignmentFlag.AlignBottom
                               | Qt.AlignmentFlag.AlignHCenter,
                               QColor("#FFFFFF"))
        app.processEvents()

    return splash, step
