# -*- coding: utf-8 -*-
"""Application chrome: menus, toolbar, side navigation, status bar,
recent projects, drag-and-drop open, theme/language switching.

The chrome contains NO engineering logic: it only wires callables handed
in by ``main_window.launch`` (``handlers``) and decorates the existing
widgets.  Qt is imported lazily so the pure helpers (``workflow_html``,
``normalize_recent``, ``push_recent``) are unit-testable headless.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ...logging_setup import get_logger, log_path
from . import icons
from .i18n import LANGS, get_language, t
from .theme import THEMES, apply_theme

_log = get_logger("ui.chrome")

MAX_RECENT = 8
ORG, APP = "SwitchLoc", "SwitchLoc"
WORKFLOW_ORDER = ["Import", "Topology", "Placement", "Exports"]


# ----------------------------------------------------------------------
# Qt-free helpers (unit-testable)
# ----------------------------------------------------------------------
def normalize_recent(raw) -> list[str]:
    """QSettings may hand back ``None``, a str (single item) or a list."""
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    out: list[str] = []
    for p in raw:
        p = str(p)
        if p and p not in out:
            out.append(p)
    return out[:MAX_RECENT]


def push_recent(current: list[str], path: str) -> list[str]:
    """Most-recent-first, de-duplicated, capped at ``MAX_RECENT``."""
    path = str(path)
    return normalize_recent([path] + [p for p in current if p != path])


def workflow_html(state_name: str, tokens: dict) -> str:
    """Stepper text for the workflow strip (rich text, colour-coded)."""
    idx = WORKFLOW_ORDER.index(state_name) \
        if state_name in WORKFLOW_ORDER else -1
    parts = []
    for i, name in enumerate(WORKFLOW_ORDER):
        label = t(name)
        if i < idx:
            parts.append(f'<span style="color:{tokens["ok"]};">'
                         f'&#10004; {label}</span>')
        elif i == idx:
            parts.append(f'<span style="color:{tokens["primary"]};'
                         f'font-weight:600;">&#9654; {label}</span>')
        else:
            parts.append(f'<span style="color:{tokens["text_muted"]};">'
                         f'&#9675; {label}</span>')
    sep = f'<span style="color:{tokens["border"]};">&nbsp;&nbsp;&#8594;&nbsp;&nbsp;</span>'
    return sep.join(parts)


# ----------------------------------------------------------------------
# the chrome object
# ----------------------------------------------------------------------
class Chrome:
    """Built once by :func:`install_chrome`; main_window keeps the handle."""

    def __init__(self):
        self.win = None
        self.app = None
        self.tabs = None
        self.tokens = THEMES["light"]
        self.mode = "light"
        self.assets_dir: Path | None = None
        self.central = None
        self.workflow_label = None
        self.workflow_state = "Import"
        self.lbl_project = self.lbl_feeders = self.lbl_crs = None
        self.recent_menu = None
        self._icon_refs: list = []       # (target, name, on_dark)
        self._open_project: Callable | None = None
        self._nav_buttons: list = []
        self._theme_actions: dict = {}

    # -- settings ------------------------------------------------------
    @staticmethod
    def settings():
        from PySide6.QtCore import QSettings
        return QSettings(ORG, APP)

    def recent(self) -> list[str]:
        try:
            return normalize_recent(self.settings().value("recent_projects"))
        except Exception:                          # noqa: BLE001
            _log.warning("recent list unreadable", exc_info=True)
            return []

    def add_recent(self, path: str) -> None:
        try:
            self.settings().setValue(
                "recent_projects", push_recent(self.recent(), str(path)))
        except Exception:                          # noqa: BLE001
            _log.warning("recent list not saved", exc_info=True)
        self._rebuild_recent_menu()

    def clear_recent(self) -> None:
        try:
            self.settings().remove("recent_projects")
        except Exception:                          # noqa: BLE001
            _log.warning("recent list not cleared", exc_info=True)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        m = self.recent_menu
        if m is None:
            return
        m.clear()
        items = [p for p in self.recent() if Path(p).exists()]
        if not items:
            a = m.addAction(t("(none)"))
            a.setEnabled(False)
            return
        for p in items:
            a = m.addAction(Path(p).name)
            a.setToolTip(p)
            a.setStatusTip(p)
            a.triggered.connect(
                lambda _checked=False, path=p: self._open_project(path))
        m.addSeparator()
        m.addAction(t("Clear list")).triggered.connect(
            lambda _checked=False: self.clear_recent())

    # -- icons / buttons -----------------------------------------------
    def _icon(self, name: str, kind: str = "normal"):
        """kind: normal | nav (on the dark sidebar) | primary (on the
        accent-coloured button) — each has its own contrast colour."""
        tk = self.tokens
        color = {"nav": tk["icon_on_dark"],
                 "primary": tk["primary_text"]}.get(kind, tk["icon"])
        return icons.icon(name, color, disabled_color=tk["icon_disabled"])

    def decorate(self, target, name: str, kind: str = "normal") -> None:
        """Give a button/action an icon and remember it for theme switches."""
        try:
            target.setIcon(self._icon(name, kind))
            self._icon_refs.append((target, name, kind))
        except Exception:                          # noqa: BLE001
            _log.debug("decorate(%s) failed", name, exc_info=True)

    def style_button(self, btn, icon_name: str | None = None,
                     primary: bool = False) -> None:
        if icon_name:
            self.decorate(btn, icon_name, "primary" if primary else "normal")
        if primary:
            btn.setProperty("primary", True)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _refresh_icons(self) -> None:
        icons.clear_cache()
        for target, name, kind in self._icon_refs:
            try:
                target.setIcon(self._icon(name, kind))
            except Exception:                      # noqa: BLE001
                pass

    # -- status ----------------------------------------------------------
    def status(self, text: str, ms: int = 5000) -> None:
        try:
            self.win.statusBar().showMessage(text, ms)
        except Exception:                          # noqa: BLE001
            pass

    def set_project_info(self, name: str = "", feeders: int | None = None,
                         crs: str = "") -> None:
        if self.lbl_project is None:
            return
        self.lbl_project.setText(
            f'{t("Project")}: {name}' if name else t("No project"))
        self.lbl_feeders.setText(
            f'{t("Feeders")}: {feeders}' if feeders is not None else "")
        self.lbl_crs.setText(f'{t("CRS")}: {crs}' if crs else "")
        title = "SwitchLoc — Switch Placement & Automation (TAV122-02/00)"
        self.win.setWindowTitle(f"{name} — {title}" if name else title)

    # -- workflow strip ------------------------------------------------------
    def set_workflow(self, state_name: str) -> None:
        self.workflow_state = state_name
        if self.workflow_label is not None:
            self.workflow_label.setText(workflow_html(state_name, self.tokens))

    # -- theme -----------------------------------------------------------------
    def set_theme(self, mode: str, persist: bool = True) -> None:
        mode = mode if mode in THEMES else "light"
        self.mode = mode
        self.tokens = apply_theme(self.app, mode, self.assets_dir)
        self._refresh_icons()
        self.set_workflow(self.workflow_state)
        for m, act in self._theme_actions.items():
            act.setChecked(m == mode)
        if persist:
            try:
                self.settings().setValue("theme", mode)
            except Exception:                      # noqa: BLE001
                _log.warning("theme not saved", exc_info=True)

    def toggle_theme(self) -> None:
        self.set_theme("dark" if self.mode == "light" else "light")


# ----------------------------------------------------------------------
# installation
# ----------------------------------------------------------------------
def install_chrome(win, app, tabs, workflow_label, handlers: dict,
                   assets_dir: Path | None, version: str = "") -> Chrome:
    """Build menus / toolbar / sidebar / status bar around ``tabs``.

    ``handlers`` keys: open_project(path|None), import_gis, import_outage,
    per_feeder, topology, placement, settings, exports, approve,
    map_style, help, about.  Returns the :class:`Chrome` handle whose
    ``central`` widget must become the window's central widget.
    """
    from PySide6.QtCore import QEvent, QObject, QSize, Qt, QUrl
    from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, \
        QKeySequence
    from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMessageBox,
                                   QSizePolicy, QToolBar, QToolButton,
                                   QVBoxLayout, QWidget)

    ch = Chrome()
    ch.win, ch.app, ch.tabs = win, app, tabs
    ch.assets_dir = assets_dir
    ch._open_project = handlers["open_project"]
    ch.workflow_label = workflow_label

    # theme (persisted) — applied first so every widget below is styled
    try:
        saved = str(Chrome.settings().value("theme") or "light")
    except Exception:                              # noqa: BLE001
        saved = "light"
    ch.mode = saved if saved in THEMES else "light"
    ch.tokens = apply_theme(app, ch.mode, assets_dir)
    workflow_label.setObjectName("WorkflowBar")
    workflow_label.setTextFormat(Qt.TextFormat.RichText)
    workflow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    workflow_label.setStyleSheet("")            # QSS (WorkflowBar) styles it
    ch.set_workflow("Import")

    def act(text, icon_name, slot, shortcut=None, tip=None, parent=None):
        a = QAction(t(text), parent or win)
        if tip or text:
            a.setToolTip(t(tip or text) + (f"  ({shortcut})" if shortcut else ""))
            a.setStatusTip(t(tip or text))
        if icon_name:
            ch.decorate(a, icon_name)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        a.triggered.connect(lambda _checked=False: slot())
        return a

    H = handlers
    a_new = act("New project…", "file-plus", H.get("new_project", lambda: None), "Ctrl+N")
    a_open = act("Open project…", "folder", lambda: H["open_project"](None),
                 "Ctrl+O")
    a_save = act("Save project", "save", H.get("save_project", lambda: None), "Ctrl+S")
    a_save_as = act("Save project as…", "save-as", H.get("save_project_as", lambda: None), "Ctrl+Shift+S")
    a_import = act("Import GIS data…", "import", H["import_gis"], "Ctrl+I")
    a_outage = act("Import outage list…", "outage", H["import_outage"],
                   "Ctrl+Shift+O")
    a_perf = act("Per-feeder outages", "file", H["per_feeder"])
    a_topo = act("Run topology", "topology", H["topology"], "Ctrl+T")
    a_plac = act("Run placement", "run", H["placement"], "Ctrl+R")
    a_set = act("Settings", "settings", H["settings"], "Ctrl+,",
                tip="Engineering settings…")
    a_exp = act("Exports…", "export", H["exports"], "Ctrl+E")
    a_appr = act("Approve plan", "approve", H["approve"])
    a_style = act("Map style…", "brush", H["map_style"])
    a_help = act("Help — study workflow", "help", H["help"], "F1")
    a_about = act("About SwitchLoc", "info", H["about"])
    a_exit = act("Exit", "exit", win.close, "Ctrl+Q")
    a_log = act("Open log folder", "log", lambda: _open_log_folder())
    a_theme = act("Toggle theme", "moon", ch.toggle_theme, "Ctrl+D")

    def _open_log_folder():
        p = log_path()
        if p:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(p).parent)))

    # ---------------- menus ----------------
    mbar = win.menuBar()
    m_file = mbar.addMenu(t("&File"))
    for a in (a_new, a_open, a_save, a_save_as):
        m_file.addAction(a)
    ch.recent_menu = m_file.addMenu(t("Recent projects"))
    m_file.addSeparator()
    for a in (a_import, a_outage, a_perf):
        m_file.addAction(a)
    m_file.addSeparator()
    m_file.addAction(a_exp)
    m_file.addSeparator()
    m_file.addAction(a_exit)
    ch._rebuild_recent_menu()

    m_study = mbar.addMenu(t("&Study"))
    for a in (a_topo, a_plac, a_set, a_appr):
        m_study.addAction(a)
    m_study.addSeparator()
    m_study.addAction(a_style)

    m_view = mbar.addMenu(t("&View"))
    for i in range(tabs.count()):
        # عنوان از خود تب خوانده می‌شود تا افزودن تب جدید (مثل
        # «Sectionalizer & EENS») هیچ نگهداری فهرست دستی نخواهد
        title = tabs.tabText(i)
        a = QAction(t(title), win)
        a.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
        a.triggered.connect(lambda _c=False, k=i: tabs.setCurrentIndex(k))
        m_view.addAction(a)
    m_view.addSeparator()
    ap = m_view.addMenu(t("Appearance"))
    grp = QActionGroup(win)
    for mode, label in (("light", "Light theme"), ("dark", "Dark theme")):
        a = QAction(t(label), win)
        a.setCheckable(True)
        a.setChecked(mode == ch.mode)
        grp.addAction(a)
        a.triggered.connect(lambda _c=False, m=mode: ch.set_theme(m))
        ap.addAction(a)
        ch._theme_actions[mode] = a
    m_view.addAction(a_theme)
    lm = m_view.addMenu(t("Language"))
    lgrp = QActionGroup(win)
    for code, label in LANGS.items():
        a = QAction(label, win)
        a.setCheckable(True)
        a.setChecked(code == get_language())
        lgrp.addAction(a)

        def _set_lang(_c=False, c=code):
            try:
                Chrome.settings().setValue("language", c)
            except Exception:                      # noqa: BLE001
                _log.warning("language not saved", exc_info=True)
            QMessageBox.information(
                win, t("Restart required"),
                t("The language change applies the next time SwitchLoc "
                  "starts."))
        a.triggered.connect(_set_lang)
        lm.addAction(a)

    m_help = mbar.addMenu(t("&Help"))
    for a in (a_help, a_log, a_about):
        m_help.addAction(a)

    # ---------------- toolbar ----------------
    tb = QToolBar("Main", win)
    tb.setObjectName("MainToolBar")
    tb.setMovable(False)
    tb.setFloatable(False)
    tb.setIconSize(QSize(22, 22))
    tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    for a in (a_open, a_import, a_outage):
        tb.addAction(a)
    tb.addSeparator()
    for a in (a_topo, a_plac):
        tb.addAction(a)
    tb.addSeparator()
    for a in (a_set, a_exp, a_appr, a_style):
        tb.addAction(a)
    spacer = QWidget()
    spacer.setSizePolicy(QSizePolicy.Policy.Expanding,
                         QSizePolicy.Policy.Preferred)
    tb.addWidget(spacer)
    tb.addAction(a_theme)
    tb.addAction(a_help)
    win.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

    # ---------------- sidebar ----------------
    side = QFrame()
    side.setObjectName("SideBar")
    side.setFixedWidth(92)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(0, 0, 0, 0)
    sl.setSpacing(0)
    brand = QLabel("SwitchLoc")
    brand.setObjectName("SideBrand")
    brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
    ver = QLabel(f"v{version}" if version else "")
    ver.setObjectName("SideVersion")
    ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sl.addWidget(brand)
    sl.addWidget(ver)
    # نماد ناوبری بر اساس عنوان تب — تب ناشناخته نماد «layers» می‌گیرد
    nav_icon_by_title = {
        "Data Import": "database", "Topology": "topology",
        "Placement": "placement", "Sectionalizer & EENS": "bolt",
        "Dashboard": "dashboard", "Map": "map",
    }
    tabs.tabBar().setVisible(False)
    for i in range(tabs.count()):
        title = tabs.tabText(i)
        b = QToolButton()
        b.setObjectName("NavButton")
        b.setText(t(title))
        b.setCheckable(True)
        b.setAutoExclusive(True)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        b.setIconSize(QSize(26, 26))
        b.setSizePolicy(QSizePolicy.Policy.Expanding,
                        QSizePolicy.Policy.Fixed)
        b.setToolTip(f"{t(title)}  (Ctrl+{i + 1})")
        ch.decorate(b, nav_icon_by_title.get(title, "layers"), "nav")
        b.clicked.connect(lambda _c=False, k=i: tabs.setCurrentIndex(k))
        sl.addWidget(b)
        ch._nav_buttons.append(b)
    sl.addStretch(1)
    tabs.currentChanged.connect(
        lambda k: ch._nav_buttons[k].setChecked(True)
        if 0 <= k < len(ch._nav_buttons) else None)
    if ch._nav_buttons:
        ch._nav_buttons[max(0, tabs.currentIndex())].setChecked(True)

    # ---------------- central widget ----------------
    central = QWidget()
    outer = QVBoxLayout(central)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addWidget(workflow_label)
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    row.addWidget(side)
    row.addWidget(tabs, 1)
    outer.addLayout(row, 1)
    ch.central = central

    # ---------------- status bar ----------------
    sb = win.statusBar()
    sb.setSizeGripEnabled(True)
    ch.lbl_project = QLabel(t("No project"))
    ch.lbl_project.setObjectName("StatusProject")
    ch.lbl_feeders = QLabel("")
    ch.lbl_crs = QLabel("")
    for w in (ch.lbl_project, ch.lbl_feeders, ch.lbl_crs):
        sb.addPermanentWidget(w)
    sb.showMessage(t("Ready"), 4000)

    # ---------------- drag & drop a project ----------------
    class _DropFilter(QObject):
        def eventFilter(self, obj, ev):            # noqa: N802
            et = ev.type()
            if et in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                md = ev.mimeData()
                if md is not None and md.hasUrls() and any(
                        u.toLocalFile().lower().endswith(".sqlite")
                        for u in md.urls()):
                    ev.acceptProposedAction()
                    ch.status(t("Drop a .sqlite project here to open it"),
                              2000)
                    return True
            elif et == QEvent.Type.Drop:
                md = ev.mimeData()
                if md is not None and md.hasUrls():
                    for u in md.urls():
                        p = u.toLocalFile()
                        if p.lower().endswith(".sqlite"):
                            ev.acceptProposedAction()
                            H["open_project"](p)
                            return True
            return False

    win.setAcceptDrops(True)
    ch._drop_filter = _DropFilter(win)
    win.installEventFilter(ch._drop_filter)

    ch._actions = {"new": a_new, "open": a_open, "save": a_save, "save_as": a_save_as, "import": a_import, "outage": a_outage,
                   "topology": a_topo, "placement": a_plac,
                   "settings": a_set, "exports": a_exp, "approve": a_appr}
    return ch
