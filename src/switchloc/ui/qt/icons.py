# -*- coding: utf-8 -*-
"""Built-in vector icon set (24×24 line icons, drawn from SVG paths).

No image files to ship: each icon is an inline SVG string rendered with
``QSvgRenderer`` at the requested size/colour (HiDPI-aware).  ``icon()``
never raises — if ``QtSvg`` is unavailable it returns an empty ``QIcon``
and the UI simply shows text labels.
"""
from __future__ import annotations

_P = {
    "folder": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
    "import": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
    "outage": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "topology": '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.6" y1="13.5" x2="15.4" y2="17.5"/><line x1="15.4" y1="6.5" x2="8.6" y2="10.5"/>',
    "placement": '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
    "settings": '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
    "map": '<polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/>',
    "dashboard": '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    "run": '<polygon points="6 3 20 12 6 21 6 3"/>',
    "approve": '<path d="M22 11.1V12a10 10 0 1 1-5.9-9.1"/><polyline points="22 4 12 14 9 11"/>',
    "export": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
    "plus": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "trash": '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
    "crosshair": '<circle cx="12" cy="12" r="9"/><line x1="22" y1="12" x2="18" y2="12"/><line x1="6" y1="12" x2="2" y2="12"/><line x1="12" y1="6" x2="12" y2="2"/><line x1="12" y1="22" x2="12" y2="18"/>',
    "search": '<circle cx="10.8" cy="10.8" r="7.2"/><path d="m16.2 16.2 5 5"/>',
    "zoom-in": '<circle cx="10.8" cy="10.8" r="7.2"/><path d="m16.2 16.2 5 5M10.8 7.5v6.6M7.5 10.8h6.6"/>',
    "zoom-out": '<circle cx="10.8" cy="10.8" r="7.2"/><path d="m16.2 16.2 5 5M7.5 10.8h6.6"/>',
    "maximize": '<path d="M8 3H3v5M16 3h5v5M21 16v5h-5M3 16v5h5"/>',
    "layers": '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    "help": '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12" y2="17.1"/>',
    "info": '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="8.1"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.2" y1="4.2" x2="5.6" y2="5.6"/><line x1="18.4" y1="18.4" x2="19.8" y2="19.8"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.2" y1="19.8" x2="5.6" y2="18.4"/><line x1="18.4" y1="5.6" x2="19.8" y2="4.2"/>',
    "exit": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    "bolt": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.7-4 3-9 3s-9-1.3-9-3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/>',
    "brush": '<path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18z"/><path d="M2 2l7.6 7.6"/><circle cx="11" cy="11" r="2"/>',
    "refresh": '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15"/>',
    "log": '<path d="M4 4h16v16H4z"/><line x1="8" y1="9" x2="16" y2="9"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="12" y2="17"/>',
}


def available() -> list[str]:
    return sorted(_P)


def svg_text(name: str, color: str = "#37474F", stroke: float = 1.9) -> str:
    """Complete SVG document for an icon (Qt-free — testable)."""
    body = _P[name]
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'fill="none" stroke="{color}" stroke-width="{stroke}" '
            'stroke-linecap="round" stroke-linejoin="round">'
            f'{body}</svg>')


_CACHE: dict = {}


def icon(name: str, color: str = "#37474F", size: int = 24,
         disabled_color: str = "#9AA5AB"):
    """``QIcon`` for ``name`` (empty icon on any failure — never raises)."""
    key = (name, color, size, disabled_color)
    if key in _CACHE:
        return _CACHE[key]
    try:
        from PySide6.QtCore import QByteArray, QRectF, Qt
        from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
        from PySide6.QtSvg import QSvgRenderer
        if name not in _P:
            raise KeyError(name)
        dpr = 1.0
        try:
            scr = QGuiApplication.primaryScreen()
            dpr = float(scr.devicePixelRatio()) if scr else 1.0
        except Exception:                          # noqa: BLE001
            dpr = 1.0
        out = QIcon()
        for mode, col in ((QIcon.Mode.Normal, color),
                          (QIcon.Mode.Disabled, disabled_color)):
            renderer = QSvgRenderer(QByteArray(
                svg_text(name, col).encode("utf-8")))
            px = int(round(size * dpr))
            pm = QPixmap(px, px)
            pm.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pm)
            renderer.render(painter, QRectF(0, 0, px, px))
            painter.end()
            pm.setDevicePixelRatio(dpr)
            out.addPixmap(pm, mode)
    except Exception:                              # noqa: BLE001
        from ...logging_setup import get_logger
        get_logger("ui.icons").debug("icon '%s' unavailable", name,
                                     exc_info=True)
        try:
            from PySide6.QtGui import QIcon
            out = QIcon()
        except Exception:                          # noqa: BLE001
            out = None
    _CACHE[key] = out
    return out


def clear_cache() -> None:
    """Drop cached pixmaps (call after a theme switch)."""
    _CACHE.clear()
