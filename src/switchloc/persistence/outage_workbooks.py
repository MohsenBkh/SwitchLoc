"""Portable, project-local source workbooks for outage processing.

XLSX is already a ZIP archive. Store its bytes intact, with a digest, so
Save As uses SQLite's normal backup and no external path is required.
"""
from __future__ import annotations

import hashlib
import sqlite3
import zipfile
from pathlib import Path

_TABLE = '''CREATE TABLE IF NOT EXISTS outage_workbook (
    feeder_key TEXT PRIMARY KEY, filename TEXT NOT NULL,
    sha256 TEXT NOT NULL, content BLOB NOT NULL)'''
COLLECTIVE_KEY = '__collective__'


def save_workbook(db_path: str, feeder_key: str, source: str | Path) -> dict:
    path = Path(source)
    if path.suffix.lower() not in ('.xlsx', '.xlsm') or not zipfile.is_zipfile(path):
        raise ValueError('فایل باید یک کتاب‌کار معتبر xlsx یا xlsm باشد.')
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    with sqlite3.connect(str(db_path), timeout=15) as conn:
        conn.execute(_TABLE)
        conn.execute('INSERT OR REPLACE INTO outage_workbook VALUES (?,?,?,?)',
                     (str(feeder_key), path.name, digest, data))
    return {'filename': path.name, 'sha256': digest, 'size': len(data)}


def list_workbooks(db_path: str) -> dict:
    with sqlite3.connect(str(db_path), timeout=15) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='outage_workbook'").fetchone():
            return {}
        return {key: {'filename': name, 'sha256': digest, 'size': size}
                for key, name, digest, size in conn.execute(
                    'SELECT feeder_key, filename, sha256, length(content) FROM outage_workbook')}


def export_workbook(db_path: str, feeder_key: str, target: str | Path) -> Path:
    with sqlite3.connect(str(db_path), timeout=15) as conn:
        row = conn.execute('SELECT filename, sha256, content FROM outage_workbook WHERE feeder_key=?',
                           (str(feeder_key),)).fetchone()
    if row is None:
        raise ValueError(f'فایل خاموشی {feeder_key} در پروژه وجود ندارد.')
    name, digest, content = row
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError(f'فایل خاموشی {name} در پروژه آسیب دیده است (SHA-256).')
    target = Path(target)
    target.write_bytes(content)
    return target
