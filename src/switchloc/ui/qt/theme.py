# -*- coding: utf-8 -*-
"""Professional light/dark theme (Fusion style + one stylesheet).

``build_qss(tokens)`` is pure string work (Qt-free, unit-testable);
``apply_theme(app, mode)`` installs the Fusion style, a matching
``QPalette`` and the stylesheet.  Colours live in ``LIGHT`` / ``DARK`` —
nothing else in the app hard-codes the look, so a theme switch is one call.
"""
from __future__ import annotations

from pathlib import Path

LIGHT = {
    "name": "light",
    "bg": "#F4F6F9", "surface": "#FFFFFF", "surface_alt": "#EEF2F6",
    "border": "#D5DCE4", "text": "#1F2933", "text_muted": "#5F6C7B",
    "primary": "#1565C0", "primary_hover": "#0F57A8", "primary_press": "#0B4A92",
    "primary_text": "#FFFFFF", "accent_soft": "#E3EEFB",
    "sidebar": "#16324F", "sidebar_text": "#C8D6E5", "sidebar_active": "#1E88E5",
    "toolbar": "#FFFFFF", "header": "#E8EDF3", "select": "#CFE3FA",
    "ok": "#2E7D32", "warn": "#E65100", "err": "#C62828",
    "icon": "#37474F", "icon_disabled": "#9AA5AB", "icon_on_dark": "#EAF2FB",
    "alt_row": "#F7F9FB",
}
DARK = {
    "name": "dark",
    "bg": "#14181D", "surface": "#1C2229", "surface_alt": "#232B33",
    "border": "#323C47", "text": "#E6EAEE", "text_muted": "#97A3B0",
    "primary": "#3B8EE8", "primary_hover": "#5AA2EE", "primary_press": "#2B78CC",
    "primary_text": "#0B1520", "accent_soft": "#1F3550",
    "sidebar": "#0E1318", "sidebar_text": "#9FB0C2", "sidebar_active": "#3B8EE8",
    "toolbar": "#1C2229", "header": "#2A333C", "select": "#294766",
    "ok": "#66BB6A", "warn": "#FFA726", "err": "#EF5350",
    "icon": "#C9D3DD", "icon_disabled": "#5B6671", "icon_on_dark": "#EAF2FB",
    "alt_row": "#20272E",
}
THEMES = {"light": LIGHT, "dark": DARK}


def build_qss(c: dict) -> str:
    """Application stylesheet for the token set ``c``."""
    return f"""
* {{ outline: 0; }}
QMainWindow, QDialog {{ background: {c['bg']}; }}
QWidget {{ color: {c['text']}; }}
QToolTip {{ background: {c['surface']}; color: {c['text']};
    border: 1px solid {c['border']}; padding: 4px 6px; }}

/* ---- menu bar / menus ---- */
QMenuBar {{ background: {c['toolbar']}; border-bottom: 1px solid {c['border']}; }}
QMenuBar::item {{ padding: 5px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: {c['accent_soft']}; border-radius: 4px; }}
QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 26px 6px 24px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c['accent_soft']}; color: {c['text']}; }}
QMenu::item:disabled {{ color: {c['text_muted']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}

/* ---- main toolbar ---- */
QToolBar#MainToolBar {{ background: {c['toolbar']};
    border: 0; border-bottom: 1px solid {c['border']}; spacing: 2px; padding: 4px 6px; }}
QToolBar#MainToolBar::separator {{ width: 1px; background: {c['border']}; margin: 6px 6px; }}
QToolBar#MainToolBar QToolButton {{ padding: 5px 9px; border: 1px solid transparent;
    border-radius: 6px; background: transparent; color: {c['text']}; }}
QToolBar#MainToolBar QToolButton:hover {{ background: {c['accent_soft']}; border-color: {c['border']}; }}
QToolBar#MainToolBar QToolButton:pressed {{ background: {c['select']}; }}
QToolBar#MainToolBar QToolButton:disabled {{ color: {c['text_muted']}; }}

/* ---- side navigation ---- */
QFrame#SideBar {{ background: {c['sidebar']}; border: 0; }}
QLabel#SideBrand {{ color: {c['icon_on_dark']}; font-weight: 700; font-size: 13px;
    padding: 12px 4px 2px 4px; background: transparent; }}
QLabel#SideVersion {{ color: {c['sidebar_text']}; font-size: 10px; padding: 0 4px 10px 4px;
    background: transparent; }}
QToolButton#NavButton {{ color: {c['sidebar_text']}; background: transparent; border: 0;
    border-left: 3px solid transparent; padding: 10px 4px; min-width: 76px; font-size: 11px; }}
QToolButton#NavButton:hover {{ background: rgba(255,255,255,8%); color: #FFFFFF; }}
QToolButton#NavButton:checked {{ background: rgba(255,255,255,15%); color: #FFFFFF;
    border-left: 3px solid {c['sidebar_active']}; font-weight: 600; }}

/* ---- workflow stepper ---- */
QLabel#WorkflowBar {{ background: {c['surface_alt']}; border-bottom: 1px solid {c['border']};
    padding: 6px 10px; color: {c['text_muted']}; }}

/* ---- pages / tabs (tab bar is hidden; the sidebar navigates) ---- */
QTabWidget::pane {{ border: 0; background: {c['bg']}; }}

/* ---- buttons ---- */
QPushButton {{ background: {c['surface']}; border: 1px solid {c['border']};
    border-radius: 6px; padding: 6px 14px; min-height: 20px; }}
QPushButton:hover {{ background: {c['accent_soft']}; border-color: {c['primary']}; }}
QPushButton:pressed {{ background: {c['select']}; }}
QPushButton:disabled {{ color: {c['text_muted']}; background: {c['surface_alt']};
    border-color: {c['border']}; }}
QPushButton[primary="true"] {{ background: {c['primary']}; color: {c['primary_text']};
    border: 1px solid {c['primary']}; font-weight: 600; }}
QPushButton[primary="true"]:hover {{ background: {c['primary_hover']}; }}
QPushButton[primary="true"]:pressed {{ background: {c['primary_press']}; }}
QPushButton[primary="true"]:disabled {{ background: {c['surface_alt']}; color: {c['text_muted']};
    border-color: {c['border']}; }}

/* ---- inputs ---- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QPlainTextEdit {{
    background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 5px;
    padding: 4px 6px; selection-background-color: {c['select']}; selection-color: {c['text']}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus,
QTextEdit:focus {{ border: 1px solid {c['primary']}; }}
QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border']};
    selection-background-color: {c['select']}; selection-color: {c['text']}; }}
QTextEdit {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px;
    padding: 4px; selection-background-color: {c['select']}; selection-color: {c['text']}; }}
QCheckBox, QRadioButton {{ spacing: 6px; }}
QGroupBox {{ border: 1px solid {c['border']}; border-radius: 8px; margin-top: 12px;
    padding: 10px 8px 8px 8px; background: {c['surface']}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {c['text_muted']};
    font-weight: 600; }}

/* ---- tables ---- */
QTableWidget, QTableView, QTreeView, QListView {{ background: {c['surface']};
    alternate-background-color: {c['alt_row']}; gridline-color: {c['border']};
    border: 1px solid {c['border']}; border-radius: 6px;
    selection-background-color: {c['select']}; selection-color: {c['text']}; }}
QHeaderView::section {{ background: {c['header']}; color: {c['text']}; padding: 6px 8px;
    border: 0; border-right: 1px solid {c['border']}; border-bottom: 1px solid {c['border']};
    font-weight: 600; }}
QTableCornerButton::section {{ background: {c['header']}; border: 0; }}

/* ---- scrollbars ---- */
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 28px; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 5px; min-width: 28px; }}
QScrollBar::handle:hover {{ background: {c['text_muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- splitter / progress / status ---- */
QSplitter::handle {{ background: {c['border']}; }}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:vertical {{ height: 2px; }}
QProgressBar {{ border: 1px solid {c['border']}; border-radius: 5px; text-align: center;
    background: {c['surface_alt']}; min-height: 14px; }}
QProgressBar::chunk {{ background: {c['primary']}; border-radius: 4px; }}
QStatusBar {{ background: {c['toolbar']}; border-top: 1px solid {c['border']}; color: {c['text_muted']}; }}
QStatusBar::item {{ border: 0; }}
QStatusBar QLabel {{ padding: 0 8px; color: {c['text_muted']}; }}
QLabel#StatusProject {{ color: {c['text']}; font-weight: 600; }}
QProgressDialog {{ background: {c['bg']}; }}
QMessageBox {{ background: {c['bg']}; }}
"""


def palette_for(c: dict):
    """A ``QPalette`` matching the tokens (so native-drawn bits agree)."""
    from PySide6.QtGui import QColor, QPalette
    pal = QPalette()
    role = QPalette.ColorRole
    pairs = {
        role.Window: c["bg"], role.WindowText: c["text"],
        role.Base: c["surface"], role.AlternateBase: c["alt_row"],
        role.Text: c["text"], role.Button: c["surface"],
        role.ButtonText: c["text"], role.ToolTipBase: c["surface"],
        role.ToolTipText: c["text"], role.Highlight: c["select"],
        role.HighlightedText: c["text"], role.PlaceholderText: c["text_muted"],
        role.Link: c["primary"],
    }
    for r, col in pairs.items():
        pal.setColor(r, QColor(col))
    return pal


def load_fonts(assets_dir: Path) -> list[str]:
    """Register bundled Vazirmatn fonts; returns the loaded family names."""
    from PySide6.QtGui import QFontDatabase
    fams: list[str] = []
    fdir = Path(assets_dir) / "fonts"
    if not fdir.is_dir():
        return fams
    for f in sorted(fdir.glob("*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(f))
        if fid >= 0:
            for fam in QFontDatabase.applicationFontFamilies(fid):
                if fam not in fams:
                    fams.append(fam)
    return fams


def apply_theme(app, mode: str = "light", assets_dir: Path | None = None,
                base_font_pt: int = 10) -> dict:
    """Install Fusion + palette + stylesheet + fonts; returns the tokens."""
    from PySide6.QtGui import QFont
    c = THEMES.get(mode, LIGHT)
    try:
        app.setStyle("Fusion")
    except Exception as exc:                       # noqa: BLE001
        from ...logging_setup import get_logger
        get_logger("ui.theme").warning("Fusion style unavailable: %s", exc)
    families: list[str] = []
    if assets_dir is not None:
        families = load_fonts(assets_dir)
    font = QFont()
    stack = (families[:1] if families else []) + ["Segoe UI", "Tahoma"]
    try:
        font.setFamilies(stack)
    except Exception:                              # noqa: BLE001
        font.setFamily(stack[0])
    font.setPointSize(base_font_pt)
    app.setFont(font)
    app.setPalette(palette_for(c))
    app.setStyleSheet(build_qss(c))
    return c
