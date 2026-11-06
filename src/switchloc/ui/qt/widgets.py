# -*- coding: utf-8 -*-
"""Shared Qt widgets/helpers for the SwitchLoc shell (درخواست کاربر).

* explanation blocks with a distinct blue background («قسمت هایی که به
  عنوان توضیحات هستند با یک بک گراند مثلا آبی رنگ مشخص کن»)
* required-field marking with a red asterisk («فیلدهای الزامی ستاره‌دار»)
* every table sortable by its column headers («قابلیت سورتینگ بر اساس
  هر هدر ستون») with numeric-aware ordering (12 > 9, not "12" < "9")
* copy (Ctrl+C) / paste (Ctrl+V) on ALL input and output tables
  («قابلیت کپی کردن و پیست کردن را برای تمامی جداول فعال کن») —
  clipboard format is TSV so Excel/Word paste round-trips.

Discipline: the pure logic (`cmp_cells`, `rows_to_tsv`, `tsv_to_rows`,
`num_or_text`, `required_html`) is Qt-free and unit-tested; only the
thin glue touches PySide6.
"""
from __future__ import annotations

#: explanation-block style (blue background — user request)
EXPLAIN_QSS = ("QLabel { background: #e3f2fd; color: #0d47a1;"
               " border: 1px solid #90caf9; border-radius: 4px;"
               " padding: 6px 8px; }")

#: red asterisk for required fields
_REQ_MARK = '<span style="color:#c62828; font-weight:bold;">*</span>'


def num_or_text(s) -> float | None:
    """Parse a cell as a number (comma thousand separators tolerated)."""
    try:
        t = str(s).strip().replace(",", "").replace("٬", "")
        if t.endswith("%"):
            t = t[:-1].strip()
        return float(t)
    except (ValueError, TypeError):
        return None


def _natural_key(s: str) -> list:
    """Natural-sort key: digit runs compare as numbers (F2 < F10)."""
    import re
    return [int(p) if p.isdigit() else p.lower()
            for p in re.split(r"(\d+)", s)]


def cmp_cells(a: str, b: str) -> int:
    """Numeric-aware cell comparison for table sorting (-1/0/1).

    Two numbers compare as numbers; number < text; text compares
    case-insensitively with NATURAL digit runs — so «9» sorts before
    «12» and «F2» before «F10».
    """
    na, nb = num_or_text(a), num_or_text(b)
    if na is not None and nb is not None:
        return (na > nb) - (na < nb)
    if na is not None:
        return -1
    if nb is not None:
        return 1
    ka, kb = _natural_key(str(a).strip()), _natural_key(str(b).strip())
    return (ka > kb) - (ka < kb)


def required_html(text: str) -> str:
    """Label text with a red asterisk (required field, user request)."""
    return f"{_REQ_MARK} {text}"


def rows_to_tsv(rows: list) -> str:
    """Table selection → TSV text (clipboard-friendly, Excel round-trip)."""
    out = []
    for row in rows:
        out.append("\t".join("" if c is None else str(c) for c in row))
    return "\n".join(out)


def tsv_to_rows(text: str) -> list:
    """TSV text → rows of strings (paste source; handles CRLF)."""
    rows = []
    for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line == "" and len(rows) and rows[-1] == []:
            break
        rows.append(line.split("\t"))
    while rows and rows[-1] == [""]:
        rows.pop()
    return rows


# ---------------------------------------------------------------------------
# Qt glue (imported lazily — the module imports safely without PySide6)
# ---------------------------------------------------------------------------
def make_explain_label(text: str, parent=None):
    """Compact per-section Help control; long explanations open on demand.

    Kept under the historical function name so every existing section
    automatically gains the same space-saving help interaction.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QPushButton,
                                   QTextBrowser, QVBoxLayout)
    btn = QPushButton("ⓘ راهنما")
    btn.setFixedHeight(28)
    btn.setMaximumWidth(104)
    btn.setToolTip("برای مشاهده توضیحات و راهنمای این بخش کلیک کنید")
    btn.setAccessibleName("section help")

    def _show_help():
        dlg = QDialog(parent)
        dlg.setWindowTitle("راهنمای این بخش")
        dlg.resize(720, 520)
        dlg.setWindowFlags(dlg.windowFlags() |
                           Qt.WindowType.WindowMaximizeButtonHint |
                           Qt.WindowType.WindowMinimizeButtonHint)
        layout = QVBoxLayout(dlg)
        browser = QTextBrowser(dlg)
        browser.setOpenExternalLinks(True)
        browser.setHtml(str(text))
        layout.addWidget(browser, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)
        dlg.exec()
    btn.clicked.connect(_show_help)
    return btn


def make_required_label(text: str, parent=None):
    """Form label with the red required asterisk.

    NOTE (bug fix — switchloc_run_log.txt): ``setTextFormat(1)`` crashes
    on strict PySide6 builds («called with wrong argument types …
    setTextFormat(int)») — the argument MUST be the ``Qt.TextFormat``
    enum, never a bare int.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel
    lbl = QLabel(required_html(text), parent)
    lbl.setTextFormat(Qt.TextFormat.RichText)   # enum, NOT int (bug fix)
    return lbl


def make_table_item(text: str, editable: bool = False):
    """Cell item with numeric-aware sorting (user request: هر هدر ستون)."""
    from PySide6.QtWidgets import QTableWidgetItem

    class _NumItem(QTableWidgetItem):
        def __lt__(self, other):               # noqa: N802 (Qt naming)
            return cmp_cells(self.text(), other.text()) < 0

    it = _NumItem("" if text is None else str(text))
    if not editable:
        from PySide6.QtCore import Qt
        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return it


def enable_copy_paste(table, editable: bool = False) -> None:
    """Ctrl+C copies the selection as TSV; Ctrl+V pastes into editable
    cells from the current cell — applied to ALL tables (user request)."""
    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtGui import QGuiApplication, QKeySequence

    # NOTE: fully-scoped enums only (QEvent.Type.KeyPress,
    # QKeySequence.StandardKey.Copy) — the short aliases raise on strict
    # PySide6 builds, the same bug class as the earlier setTextFormat(int)
    # and setContextMenuPolicy(0) crashes.
    class _Filter(QObject):
        def eventFilter(self, obj, ev):        # noqa: N802 (Qt naming)
            if ev.type() != QEvent.Type.KeyPress:
                return False
            if ev.matches(QKeySequence.StandardKey.Copy):
                sel = _selected_rows(obj)
                if sel:
                    QGuiApplication.clipboard().setText(
                        rows_to_tsv(sel))
                return True
            if editable and ev.matches(QKeySequence.StandardKey.Paste):
                txt = QGuiApplication.clipboard().text()
                _paste_rows(obj, tsv_to_rows(txt))
                return True
            return False

    table._sw_copy_filter = _Filter(table)     # keep a reference alive
    table.installEventFilter(table._sw_copy_filter)


def _selected_rows(table) -> list:
    """Selected cells → row-wise values (a full row = one TSV row)."""
    rng = table.selectedRanges()
    if not rng:
        if table.currentItem() is not None:
            return [[table.currentItem().text()]]
        return []
    out = []
    for r in rng:
        for i in range(r.topRow(), r.bottomRow() + 1):
            row = []
            for j in range(r.leftColumn(), r.rightColumn() + 1):
                it = table.item(i, j)
                row.append(it.text() if it else "")
            out.append(row)
    return out


def _paste_rows(table, rows: list) -> None:
    """Paste TSV rows starting at the current cell (bounds-clipped)."""
    if not rows:
        return
    from PySide6.QtCore import Qt
    editable_flag = Qt.ItemFlag.ItemIsEditable
    i0 = max(0, table.currentRow())
    j0 = max(0, table.currentColumn())
    for di, row in enumerate(rows):
        i = i0 + di
        if i >= table.rowCount():
            break
        for dj, val in enumerate(row):
            j = j0 + dj
            if j >= table.columnCount():
                break
            it = table.item(i, j)
            if it is None:
                continue
            if bool(it.flags() & editable_flag):
                it.setText(str(val))


def fill_table(table, headers: list, rows: list,
               editable_cols: set | None = None,
               stretch_last: bool = True) -> None:
    """Fill a table with sortable, copyable, numeric-aware cells.

    ``rows``: list of string lists; ``editable_cols``: column indexes the
    user may edit.  Sorting is toggled off during the fill (Qt rule) and
    re-enabled afterwards — every header click sorts (user request).
    """
    table.blockSignals(True)
    table.setSortingEnabled(False)
    try:
        table.clearContents()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(list(headers))
        table.setRowCount(len(rows))
        editable_cols = editable_cols or set()
        for i, row in enumerate(rows):
            for j in range(len(headers)):
                v = row[j] if j < len(row) else ""
                it = make_table_item(v, editable=(j in editable_cols))
                table.setItem(i, j, it)
    finally:
        table.setSortingEnabled(True)
        table.blockSignals(False)
    if stretch_last:
        table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setVisible(False)
    enable_copy_paste(table, editable=bool(editable_cols))
