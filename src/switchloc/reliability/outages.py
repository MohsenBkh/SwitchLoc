# -*- coding: utf-8 -*-
"""Outage-list ingestion (گام ۲ / بند ۷-۷-۳ — شکل ۵؛ A-08 data limits).

Reads the company outage workbook (لیست خاموشی‌های ۱۴۰۵ — دو شیت «پست
خلخال» و «پست کمی آباد») into canonical `OutageRecord`s.

Data facts established in Phase 0/1 profiling and honoured here:
  * ~half of the spreadsheet rows are *entirely empty* (895 + 1,103);
    they are skipped and counted, never classified.
  * no «تعداد مشترکین متأثر» and no «نوع خاموشی (با برنامه/بی‌برنامه)»
    column exists (A-08) → planned/unplanned is NOT guessed from free
    text beyond a narrow, audited pattern list (OUT-POL-02).
  * the unit of «انرژی توزیع نشده» is not declared (A-08) → kept as-is,
    reported as `energy_kwh` with the limitation note.
  * feeder values in the خلخال sheet are plain numbers (1..7) and map to
    the modelled feeders F1..F7; «کمی آباد» feeder names are not part of
    the modelled GIS sample → `in_model=False` (they still appear in the
    four review-level tables of شکل ۵, level 4 «محدوده»).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import time as dtime
from pathlib import Path

from ..domain.ids import stable_id

JALALI_DATE_RE = re.compile(r"^\s*(\d{3,4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*$")
_NUMERIC_FEEDER_RE = re.compile(r"^\s*0*(\d+)(?:\.0+)?\s*$")
#: «4كمي آ باد» / «12秘» — a LEADING feeder index followed by free text
#: (kamiabad-style outage lists); guarded by the modelled-feeder set so a
#: substation code can never silently become a feeder key
_PREFIX_FEEDER_RE = re.compile(r"^\s*0*(\d{1,3})(?![\d.])")
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
                                "01234567890123456789")

#: Excel header → canonical field (exact header spelling of the 1405 list).
OUTAGE_COLUMNS = {
    "شماره حادثه": "event_no",
    "نام پست": "substation",
    "نام فيدر": "feeder_raw",
    "تاريخ حادثه": "date_raw",
    "زمان حادثه": "time_raw",
    "مدت قطع": "duration_raw",
    "تاخير در وصل": "restore_raw",
    "علت قطع": "cause_raw",
    "قطع کننده": "device_raw",
    "انرژي توزيع نشده": "energy_raw",
    "جريان زمان قطع": "trip_current_raw",
    "توضيحات حادثه": "notes_raw",
}


_HEADER_FOLD = str.maketrans({
    "ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه",
    "\u200c": " ", "\u200d": "", "\u200e": "", "\u200f": "",
    "\u00a0": " ", "ـ": "",
})


def normalize_header(h) -> str:
    """Fold Arabic/Persian letter variants, ZWNJ, NBSP, tatweel and spaces
    so «نام فيدر» == «نام فیدر» == «نام‌فیدر»."""
    return re.sub(r"\s+", " ", str(h or "").translate(_HEADER_FOLD)).strip()


def load_column_aliases(path: str | Path | None = None) -> dict[str, str]:
    """Extra header→field aliases from a JSON file (company-specific lists).

    Looked up in ``path`` or ``$SWITCHLOC_OUTAGE_COLUMNS`` or
    ``outage_columns.json`` in the current directory; format:
    ``{"نام فیدر": "feeder_raw", "تاریخ": "date_raw", ...}``.  Unknown
    field names are ignored (with a log line), a broken file never aborts
    an import.
    """
    import json
    import os
    from ..logging_setup import get_logger
    log = get_logger("outages")
    cand = Path(path) if path else Path(
        os.environ.get("SWITCHLOC_OUTAGE_COLUMNS", "outage_columns.json"))
    if not cand.is_file():
        return {}
    try:
        raw = json.loads(cand.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("outage column aliases %s unreadable: %s", cand, exc)
        return {}
    valid = set(OUTAGE_COLUMNS.values())
    out: dict[str, str] = {}
    for k, v in (raw or {}).items():
        if v in valid:
            out[normalize_header(k)] = v
        else:
            log.warning("outage alias '%s' -> unknown field '%s' ignored", k, v)
    return out


def _column_lookup(extra: dict[str, str] | None = None) -> dict[str, str]:
    look = {normalize_header(k): v for k, v in OUTAGE_COLUMNS.items()}
    look.update(extra or {})
    return look


@dataclass
class OutageRecord:
    """One real outage event, cleaned and feeder-mapped."""
    sheet: str
    row_ref: int                       # Excel row number (header = row 1)
    id: str = ""                       # stable, deterministic
    event_no: str = ""
    substation: str = ""
    feeder_raw: str = ""
    feeder_key: str = ""               # F1..F7 when in the modelled network
    in_model: bool = False
    date_j: str = ""                   # «۱۴۰۴/۰۷/۰۱» (Jalali, as recorded)
    year: int | None = None
    month: int | None = None
    duration_min: float | None = None
    restore_delay_min: float | None = None
    cause_raw: str = ""
    device_raw: str = ""
    energy_kwh: float | None = None    # unit undeclared — A-08
    trip_current_raw: str = ""
    notes: str = ""
    # filled by classify() (reliability/classify.py)
    outage_class: str = ""
    rule_id: str = ""
    cause_group: str = ""
    review_status: str = "auto"        # auto | confirmed | rejected (بازبینی دستی)

    @property
    def is_random(self) -> bool:
        """Only classifiable in-scope unplanned events count as random.

        Unknown/insufficient and out-of-scope records must never inflate λ.
        """
        return self.outage_class in ("قابل کاهش با کلیدگذاری", "نیازمند تعمیر یا تعویض تجهیز", "ناشی از هماهنگی حفاظتی")

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# normalisation helpers
# ---------------------------------------------------------------------------
def clean_text(v) -> str:
    """Collapse whitespace incl. U+00A0; '' for None (the کمی آباد feeder
    names contain U+00A0 — «1كمي\xa0 آ باد»)."""
    if v is None:
        return ""
    return re.sub(r"[\s\u00a0]+", " ", str(v)).strip()


def parse_jalali_date(v) -> tuple[str, int | None, int | None]:
    """'1404/07/01' → ('1404/07/01', 1404, 7). Unparseable → ('', None, None)."""
    s = clean_text(v)
    m = JALALI_DATE_RE.match(s)
    if not m:
        return "", None, None
    y, mo = int(m.group(1)), int(m.group(2))
    return f"{y}/{mo:02d}/{int(m.group(3)):02d}", y, mo


def parse_duration_minutes(v) -> float | None:
    """Excel duration → minutes. Accepts datetime.time, 'HH:MM:SS',
    'HH:MM' or a plain number of minutes. None stays None."""
    if v is None:
        return None
    if isinstance(v, dtime):
        return v.hour * 60.0 + v.minute + v.second / 60.0
    if isinstance(v, (int, float)):
        return float(v)
    s = clean_text(v)
    if not s:
        return None
    parts = s.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        return nums[0] * 60 + nums[1] + nums[2] / 60.0
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    return nums[0]


def parse_energy(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = clean_text(v).replace("،", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def default_feeder_mapper(model_feeders: frozenset | set | None = None):
    """Return a (sheet, feeder_raw) → (feeder_key, in_model) mapper.

    Two accepted shapes (both guarded by the modelled-feeder set):
      * a bare number («1», «2.0») → ``F<n>`` — Khalkhal-style lists;
      * a leading index + free text («4كمي آ باد» — kamiabad-style) →
        ``F<n>``: the conventional leading feeder index of the Tavanir
        outage lists.  Persian/Arabic digits (۴، ٤) are normalized.
    Anything else stays unmapped with ``in_model=False`` — no silent
    invention (بند ۱۹); a substation code can never become a feeder key
    because ``F<n>`` must be one of the modelled feeders.
    """
    known = [str(k) for k in (model_feeders or {f"F{i}" for i in range(1, 8)})]
    from ..topology.tracing import same_feeder

    def _resolve(key: str) -> tuple[str, bool]:
        """کلید عددی (F2) را به شناسهٔ فیدر مدل نگاشت می‌کند.

        اگر چند فیدر مدل با همان شماره وجود داشته باشد («F2 - MESHKIN» و
        «F2 - HADIDMOBTAKERAN»)، ادغام نمی‌شود: رکورد ناشناس می‌ماند تا
        کاربر با ورود per-feeder صریح، فیدر را تعیین کند.
        """
        matches = [k for k in known if same_feeder(k, key)]
        if len(matches) == 1:
            return (matches[0], True)
        return (key, False)

    def mapper(sheet: str, feeder_raw: str) -> tuple[str, bool]:
        raw = (feeder_raw or "").translate(_PERSIAN_DIGITS)
        m = _NUMERIC_FEEDER_RE.match(raw)
        if m:
            return _resolve(f"F{int(m.group(1))}")
        m = _PREFIX_FEEDER_RE.match(raw)
        if m:
            return _resolve(f"F{int(m.group(1))}")
        return ("", False)

    return mapper


def fixed_feeder_mapper(feeder_key: str):
    """Mapper for a SINGLE-feeder outage workbook (ورود خاموشی per-feeder).

    وقتی کاربر فایل خاموشی «هر فیدر» را جداگانه وارد می‌کند، همه رکوردهای
    آن فایل به همان فیدر منسوب می‌شوند (صریح، توسط کاربر) — تشخیص عددی
    «شماره فیدر» دیگر لازم نیست؛ فایل حتی ممکن است ستون فیدر نداشته باشد.
    """
    key = (feeder_key or "").strip().upper()

    def mapper(sheet: str, feeder_raw: str) -> tuple[str, bool]:
        return (key, bool(key))

    return mapper


# ---------------------------------------------------------------------------
# workbook reader
# ---------------------------------------------------------------------------
def read_outage_workbook(path: str | Path,
                         feeder_mapper=None,
                         source_tag: str = "") -> tuple[list[OutageRecord], dict]:
    """Read the outage workbook into canonical records.

    Returns ``(records, reader_stats)``.  Entirely-empty spreadsheet rows
    are skipped and counted (they are not events); rows that carry at
    least one non-empty cell become records — the classifier decides
    whether they are usable events or «داده ناکافی» (A-08).

    ``source_tag``: شناسه منبع برای ورود چندفایلی (خاموشی per-feeder) —
    در شناسه پایدار رکوردها و آمار خواننده ثبت می‌شود تا رکوردهای دو
    فایل مختلف هرگز تداخل شناسه نداشته باشند.
    """
    import openpyxl                                   # runtime dep (requirements.txt)

    path = Path(path)
    mapper = feeder_mapper or default_feeder_mapper()
    records: list[OutageRecord] = []
    stats = {
        "file": str(path), "file_sha256": _sha256(path),
        "source_tag": source_tag,
        "sheets": {}, "rows_total": 0, "rows_empty_skipped": 0,
        "records": 0,
    }

    lookup = _column_lookup(load_column_aliases())
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            rows = ws.iter_rows(values_only=True)
            header_raw = next(rows, None)
            header = [clean_text(h) for h in (header_raw or [])]
            col_of = {}
            unmapped: list[str] = []
            for idx, h in enumerate(header):
                field = lookup.get(normalize_header(h))
                if field is not None and field not in col_of:
                    col_of[field] = idx
                elif field is None and h:
                    unmapped.append(h)

            sheet_rows = sheet_empty = sheet_records = 0
            for row_no, row in enumerate(rows, start=2):
                vals = list(row) + [None] * (len(header) + 1)
                nonempty = any(v is not None and clean_text(v) not in ("", "False")
                               for v in row)
                sheet_rows += 1
                if not nonempty:
                    sheet_empty += 1
                    continue

                def cell(key: str):
                    i = col_of.get(key)
                    return None if i is None else vals[i]

                date_j, year, month = parse_jalali_date(cell("date_raw"))
                rec = OutageRecord(
                    sheet=sheet, row_ref=row_no,
                    event_no=clean_text(cell("event_no")),
                    substation=clean_text(cell("substation")) or sheet,
                    feeder_raw=clean_text(cell("feeder_raw")),
                    date_j=date_j, year=year, month=month,
                    duration_min=parse_duration_minutes(cell("duration_raw")),
                    restore_delay_min=parse_duration_minutes(cell("restore_raw")),
                    cause_raw=clean_text(cell("cause_raw")),
                    device_raw=clean_text(cell("device_raw")),
                    energy_kwh=parse_energy(cell("energy_raw")),
                    trip_current_raw=clean_text(cell("trip_current_raw")),
                    notes=clean_text(cell("notes_raw")),
                )
                rec.feeder_key, rec.in_model = mapper(sheet, rec.feeder_raw)
                # back-compat: without source_tag the id is identical to
                # the single-workbook pipeline of phases 3-5 (deterministic)
                rec.id = (stable_id("outage", source_tag, sheet, row_no)
                          if source_tag
                          else stable_id("outage", sheet, row_no))
                records.append(rec)
                sheet_records += 1

            stats["sheets"][sheet] = {
                "rows": sheet_rows, "empty_skipped": sheet_empty,
                "records": sheet_records,
                "columns_found": sorted(col_of.keys()),
                # surfaced so a differently-worded list is never mapped
                # silently wrong: unknown headers + missing core fields
                "headers_unmapped": unmapped,
                "core_missing": [f for f in ("feeder_raw", "date_raw",
                                             "duration_raw")
                                 if f not in col_of],
            }
            stats["rows_total"] += sheet_rows
            stats["rows_empty_skipped"] += sheet_empty
            stats["records"] += sheet_records
    finally:
        wb.close()
    return records, stats


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()
