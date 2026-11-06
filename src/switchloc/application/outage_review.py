# -*- coding: utf-8 -*-
"""Human-in-the-loop outage place/zone review with auditable SQLite storage."""
from __future__ import annotations
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..geography.places import PlaceGazetteer, PlaceMatch

#: نام متغیر محیطی برای مسیر جایگزین بانک آفلاین مکان‌ها
GAZETTEER_ENV_VAR = "SWITCHLOC_GAZETTEER"


def default_gazetteer_path() -> Path | None:
    """مسیر بانک آفلاین مکان‌های اردبیل را بدون ایجاد هیچ فایلی پیدا می‌کند.

    ترتیب: 1) ``$SWITCHLOC_GAZETTEER`` (اگر به فایل موجود اشاره کند) →
    ``data/geography/ardabil_places.sqlite`` کنار ریشهٔ مخزن/نصب →
    ``None`` (بانک همراه برنامه نیست — هرگز پایگاه خالی ساخته نمی‌شود).
    """
    env = os.environ.get(GAZETTEER_ENV_VAR, "").strip()
    if env:
        env_path = Path(env)
        if env_path.is_file():
            return env_path
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / "geography" / "ardabil_places.sqlite"
        if candidate.is_file():
            return candidate
    return None


@dataclass(frozen=True)
class OutagePlaceSuggestion:
    event_id: str
    text: str
    matches: tuple[PlaceMatch, ...]


def suggest_event_places(records: Iterable, gazetteer: PlaceGazetteer,
                         limit: int = 5) -> list[OutagePlaceSuggestion]:
    """Suggest places from free-text descriptions; suggestions are never assignments."""
    out = []
    for rec in records:
        # The outage workbook's «نام پست» is the primary location field
        # (often a village, farm, BTS site or other named place). Search it
        # first; notes/device are supplementary context, not substitutes.
        station = str(getattr(rec, "substation", "") or "").strip()
        context = " ".join(x for x in (getattr(rec, "notes", ""),
                                       getattr(rec, "device_raw", "")) if x)
        # Prefer «نام پست» alone. Searching a concatenation of notes and
        # equipment first creates spurious substring matches for generic
        # words; contextual fallback is used only when the primary field has
        # no candidates.
        matches = gazetteer.search(station, limit=limit) if station else []
        text = station or context
        if not matches and context:
            text = " ".join(x for x in (station, context) if x)
            matches = gazetteer.search(text, limit=limit)
        out.append(OutagePlaceSuggestion(str(getattr(rec, "id", "")), text,
                                         tuple(matches)))
    return out


class OutageReviewStore:
    """Persist engineer-confirmed event→place/zone decisions in project DB."""
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        with sqlite3.connect(self.db_path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS outage_event_review (
                event_id TEXT PRIMARY KEY, place_id TEXT NOT NULL DEFAULT '',
                place_name TEXT NOT NULL DEFAULT '', zone_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('confirmed','rejected')),
                reviewer TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")

    def save(self, event_id: str, zone_id: str, *, place_id: str = '',
             place_name: str = '', reviewer: str = '', note: str = '',
             status: str = 'confirmed') -> None:
        if not event_id or (status == 'confirmed' and not zone_id):
            raise ValueError('event_id and confirmed zone_id are required')
        if status not in ('confirmed', 'rejected'):
            raise ValueError('status must be confirmed or rejected')
        with sqlite3.connect(self.db_path) as db:
            db.execute("""INSERT INTO outage_event_review
                (event_id,place_id,place_name,zone_id,status,reviewer,note,updated_at)
                VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(event_id) DO UPDATE SET place_id=excluded.place_id,
                place_name=excluded.place_name,zone_id=excluded.zone_id,
                status=excluded.status,reviewer=excluded.reviewer,note=excluded.note,
                updated_at=CURRENT_TIMESTAMP""",
                (event_id, place_id, place_name, zone_id, status, reviewer, note))

    def load(self) -> dict[str, dict]:
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute('SELECT * FROM outage_event_review').fetchall()
        return {r['event_id']: dict(r) for r in rows}

    def confirmed_event_to_zone(self) -> dict[str, str]:
        return {eid: r['zone_id'] for eid, r in self.load().items()
                if r['status'] == 'confirmed'}
