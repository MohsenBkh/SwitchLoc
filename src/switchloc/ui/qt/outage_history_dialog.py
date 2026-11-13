"""Read-only, model-backed inspection of saved outage events (no topology needed)."""
from __future__ import annotations


def show_outage_history(parent, records):  # pragma: no cover - Qt
    from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
    from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
    from PySide6.QtWidgets import QDialog, QMenu, QTableView, QVBoxLayout, QLabel

    columns = [('event_no', 'شماره رخداد'), ('feeder_key', 'فیدر'),
               ('date_j', 'تاریخ'), ('duration_min', 'مدت (دقیقه)'),
               ('cause_raw', 'علت قطع'), ('device_raw', 'قطع‌کننده'),
               ('substation', 'نام پست'), ('energy_kwh', 'انرژی خام'),
               ('notes', 'توضیحات'), ('outage_class', 'طبقه'),
               ('rule_id', 'قاعده')]

    class EventModel(QAbstractTableModel):
        def rowCount(self, parent=QModelIndex()):
            return 0 if parent.isValid() else len(records)

        def columnCount(self, parent=QModelIndex()):
            return 0 if parent.isValid() else len(columns)

        def data(self, index, role=Qt.ItemDataRole.DisplayRole):
            if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
                return None
            record = records[index.row()]
            key = columns[index.column()][0]
            value = record.get(key) if isinstance(record, dict) else getattr(record, key, None)
            return '—' if value is None or value == '' else str(value)

        def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
            if role != Qt.ItemDataRole.DisplayRole:
                return None
            if orientation == Qt.Orientation.Horizontal:
                return columns[section][1]
            return str(section + 1)

    dialog = QDialog(parent)
    dialog.setWindowTitle('سوابق خاموشی پردازش‌شده پروژه')
    dialog.resize(1200, 680)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(f'{len(records):,} رخداد؛ مقادیر انرژی عین مقدار فایل هستند. '
                            'این جدول مستقل از اجرای توپولوژی است.'))
    table = QTableView(dialog)
    model = EventModel(table)
    table.setModel(model)
    table.setAlternatingRowColors(True)
    table.setColumnWidth(8, 350)
    def copy_selection():
        selected = table.selectionModel().selectedIndexes()
        if not selected:
            return
        rows = sorted({i.row() for i in selected})
        cols = sorted({i.column() for i in selected})
        picked = {(i.row(), i.column()) for i in selected}
        text = "\n".join("\t".join(
            str(model.data(model.index(row, col)) or "") if (row, col) in picked else ""
            for col in cols) for row in rows)
        QGuiApplication.clipboard().setText(text)
    shortcut = QShortcut(QKeySequence.StandardKey.Copy, table)
    shortcut.activated.connect(copy_selection)
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    def context_menu(pos):
        menu = QMenu(table)
        copy = menu.addAction('کپی')
        paste = menu.addAction('چسباندن')
        paste.setEnabled(False)
        select = menu.addAction('انتخاب همه')
        action = menu.exec(table.viewport().mapToGlobal(pos))
        if action is copy:
            copy_selection()
        elif action is select:
            table.selectAll()
    table.customContextMenuRequested.connect(context_menu)
    layout.addWidget(table)
    dialog.exec()


def show_saved_workbooks(parent, db_path):  # pragma: no cover - Qt
    from pathlib import Path
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QLabel,
                                   QMessageBox, QPushButton, QTableWidget,
                                   QTableWidgetItem, QVBoxLayout)
    from ...persistence.outage_workbooks import COLLECTIVE_KEY, list_workbooks, export_workbook

    metadata = list_workbooks(str(db_path))
    dialog = QDialog(parent)
    dialog.setWindowTitle('فایل‌های اکسل ذخیره‌شده در پروژه')
    dialog.resize(800, 440)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel('فایل را انتخاب و برای دریافت نسخه اصلی روی «استخراج» کلیک کنید. '
                            'ذخیره فایل به معنی پردازش رخدادها نیست.'))
    table = QTableWidget(len(metadata), 3, dialog)
    table.setHorizontalHeaderLabels(['فیدر', 'نام فایل', 'اندازه (بایت)'])
    table.horizontalHeader().setStretchLastSection(True)
    for i, (key, info) in enumerate(sorted(metadata.items())):
        item = QTableWidgetItem('فایل جمعی' if key == COLLECTIVE_KEY else key)
        item.setData(Qt.ItemDataRole.UserRole, key)
        for col, cell in enumerate((item, QTableWidgetItem(info['filename']),
                                    QTableWidgetItem(str(info['size'])))):
            cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(i, col, cell)
    layout.addWidget(table)
    button = QPushButton('استخراج فایل انتخاب‌شده…', dialog)
    layout.addWidget(button)
    def extract():
        row = table.currentRow()
        if row < 0:
            QMessageBox.information(dialog, 'فایل خاموشی', 'ابتدا یک فایل انتخاب کنید.')
            return
        key = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        name = metadata[key]['filename']
        target, _ = QFileDialog.getSaveFileName(dialog, 'استخراج فایل خاموشی', name,
                                                'Excel (*.xlsx *.xlsm)')
        if not target:
            return
        try:
            # Require a meaningful extension; never overwrite the project itself.
            if Path(target).suffix.lower() not in ('.xlsx', '.xlsm'):
                target += Path(name).suffix
            if Path(target).resolve() == Path(db_path).resolve():
                raise ValueError('مسیر خروجی نباید خود فایل پروژه باشد.')
            export_workbook(str(db_path), key, target)
        except Exception as exc:
            QMessageBox.critical(dialog, 'استخراج ناموفق', str(exc))
    button.clicked.connect(extract)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()
