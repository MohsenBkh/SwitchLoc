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
    btn = QPushButton("راهنما")
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


def _cell_text(table, i: int, j: int) -> str:
    """Cell text — cell widgets first (their shown text), else the item."""
    w = table.cellWidget(i, j)
    if w is not None:
        for attr in ("currentText", "text"):
            fn = getattr(w, attr, None)
            if callable(fn):
                try:
                    v = fn()
                except Exception:                       # noqa: BLE001
                    return ""
                return "" if v is None else str(v)
        return ""
    it = table.item(i, j)
    return it.text() if it is not None else ""


def _selected_rows(table) -> list:
    """Selection → row-wise TSV block.

    Excel-like behaviour: the copy covers the *bounding rectangle* of the
    selection (cells inside the rectangle that are not part of the
    selection are emitted as empty cells). Cell-widget columns (e.g.
    combo boxes) contribute their shown text.
    """
    rng = table.selectedRanges()
    if not rng:
        i, j = table.currentRow(), table.currentColumn()
        if 0 <= i < table.rowCount() and 0 <= j < table.columnCount():
            return [[_cell_text(table, i, j)]]
        return []
    r0, r1 = min(r.topRow() for r in rng), max(r.bottomRow() for r in rng)
    c0, c1 = (min(r.leftColumn() for r in rng),
              max(r.rightColumn() for r in rng))
    covered = set()
    for r in rng:
        for i in range(r.topRow(), r.bottomRow() + 1):
            for j in range(r.leftColumn(), r.rightColumn() + 1):
                covered.add((i, j))
    out = []
    for i in range(r0, r1 + 1):
        row = []
        for j in range(c0, c1 + 1):
            row.append(_cell_text(table, i, j) if (i, j) in covered else "")
        out.append(row)
    return out


def _paste_into_cell(table, i: int, j: int, val: str) -> bool:
    """Paste one cell: combo → closest match (text/data), editable item →
    set text. Returns True when the cell accepted the value."""
    from PySide6.QtCore import Qt
    w = table.cellWidget(i, j)
    if w is not None:
        if hasattr(w, "findText") and callable(getattr(w, "findText")):
            needle = str(val).strip()
            idx = w.findText(needle)   # تطبیق دقیق Qt (حساس به حروف)
            # — اگر پیدا نشد، حلقه‌های بعدی تطبیق بدون‌حساس به حروف و
            # سپس تطبیق زیررشته‌ای را انجام می‌دهند
            if idx < 0:
                low = needle.casefold()
                for k in range(w.count()):
                    if w.itemText(k).strip().casefold() == low:
                        idx = k
                        break
            if idx < 0 and low:
                for k in range(w.count()):
                    if low in w.itemText(k).strip().casefold():
                        idx = k
                        break
            if idx < 0 and hasattr(w, "findData"):
                idx = w.findData(needle)
            if idx >= 0:
                w.setCurrentIndex(idx)
                return True
            return False
        line = getattr(w, "lineEdit", None)
        if line is not None and callable(getattr(line, "setText", None)):
            line.setText(str(val))
            return True
        return False
    it = table.item(i, j)
    if it is not None and bool(it.flags() & Qt.ItemFlag.ItemIsEditable):
        it.setText(str(val))
        return True
    return False


def _paste_rows(table, rows: list) -> tuple[int, int]:
    """Paste TSV rows starting at the current cell (bounds-clipped).

    Returns (pasted, skipped) cell counts so the caller can report
    read-only/unmatched cells honestly."""
    pasted = skipped = 0
    if not rows:
        return (0, 0)
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
            if _paste_into_cell(table, i, j, val):
                pasted += 1
            else:
                skipped += 1
    return (pasted, skipped)


def enable_copy_paste(table, editable: bool = False,
                      on_paste=None) -> None:
    """Ctrl+C copies the selection as TSV; Ctrl+V pastes into editable
    cells from the current cell — applied to ALL tables (user request).

    Cell-widget columns (combo boxes etc.) copy/paste their shown text.
    When ``on_paste(pasted, skipped)`` is given it is called after a paste."""
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
            if ev.matches(QKeySequence.StandardKey.SelectAll):
                obj.selectAll()
                return True
            if editable and ev.matches(QKeySequence.StandardKey.Paste):
                txt = QGuiApplication.clipboard().text()
                pasted, skipped = _paste_rows(obj, tsv_to_rows(txt))
                if callable(on_paste):
                    on_paste(pasted, skipped)
                return True
            return False

    table._sw_copy_filter = _Filter(table)     # keep a reference alive
    table.installEventFilter(table._sw_copy_filter)


def _select_line(table, is_column: bool, idx: int,
                 modifiers) -> None:
    """Header click → select the whole column/row (Excel-like).

    * plain click: select only that line
    * Ctrl+click: toggle that line in the selection
    * Shift+click: range from the last anchor (stored on the table)
    """
    from PySide6.QtCore import Qt
    from PySide6.QtCore import QItemSelection, QItemSelectionModel

    control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
    shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
    select = table.selectColumn if is_column else table.selectRow
    anchor_attr = "_sw_col_anchor" if is_column else "_sw_row_anchor"
    anchor = getattr(table, anchor_attr, idx)
    model = table.selectionModel()

    def _items_selected(line: int) -> bool:
        if is_column:
            idx_sel = QItemSelection(table.model().index(0, line),
                                     table.model().index(table.rowCount() - 1,
                                                         line))
        else:
            idx_sel = QItemSelection(table.model().index(line, 0),
                                     table.model().index(line,
                                                         table.columnCount() - 1))
        try:
            return all(model.isSelected(i) for i in idx_sel.indexes())
        except Exception:                              # noqa: BLE001
            return False

    if shift:
        lo, hi = sorted((anchor, idx))
        table.clearSelection()
        for n in range(lo, hi + 1):
            select(n)
        return
    if control:
        top_left = (table.model().index(0, idx) if is_column
                    else table.model().index(idx, 0))
        bot_right = (table.model().index(table.rowCount() - 1, idx)
                     if is_column
                     else table.model().index(idx, table.columnCount() - 1))
        sel = QItemSelection(top_left, bot_right)
        if _items_selected(idx):
            model.select(sel, QItemSelectionModel.SelectionFlag.Deselect)
        else:
            model.select(sel, QItemSelectionModel.SelectionFlag.Select)
        setattr(table, anchor_attr, idx)
        return
    table.clearSelection()
    select(idx)
    setattr(table, anchor_attr, idx)


def make_excel_like(table, *, paste: bool = True,
                    header_select: bool = True,
                    on_paste=None) -> None:
    """Make a review/result table behave like an Excel grid (user request):

    * extended range selection (click, Shift=range, Ctrl=toggle)
    * clicking a ROW or COLUMN header selects the entire line
      (Shift extends from the anchor, Ctrl toggles)
    * Ctrl+C / Ctrl+Ins copy the selection as TSV (Excel round-trip;
      combo-box columns contribute their shown text)
    * Ctrl+V / Shift+Ins paste TSV from the current cell
      (combo cells match by text/data; read-only cells are skipped and
      reported via ``on_paste(pasted, skipped)``)
    * Ctrl+A select all; Ctrl+Space = select column; Shift+Space = row

    Sorting is intentionally NOT enabled — callers rely on stable row
    order (e.g. review dialogs whose rows map 1:1 to source records).
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeySequence, QShortcut
    from PySide6.QtWidgets import (QAbstractItemView, QApplication)

    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    enable_copy_paste(table, editable=paste, on_paste=on_paste)

    if header_select:
        h = table.horizontalHeader()
        v = table.verticalHeader()
        h.setSectionsClickable(True)
        v.setSectionsClickable(True)
        h.sectionPressed.connect(
            lambda idx: _select_line(table, True, idx,
                                     QApplication.keyboardModifiers()))
        v.sectionPressed.connect(
            lambda idx: _select_line(table, False, idx,
                                     QApplication.keyboardModifiers()))

    def _space(is_column: bool):
        idx = (table.currentColumn() if is_column else table.currentRow())
        if idx >= 0:
            select = (table.selectColumn if is_column else table.selectRow)
            table.clearSelection()
            select(idx)

    col_sc = QShortcut(QKeySequence(
        Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_Space), table)
    col_sc.activated.connect(lambda: _space(True))
    row_sc = QShortcut(QKeySequence(
        Qt.KeyboardModifier.ShiftModifier | Qt.Key.Key_Space), table)
    row_sc.activated.connect(lambda: _space(False))
    table._sw_space_shortcuts = (col_sc, row_sc)


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
