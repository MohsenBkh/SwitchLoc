# -*- coding: utf-8 -*-
"""Bulk import feeder P/Q values from Excel workbooks."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import math
import re

from ..topology.tracing import feeder_id


@dataclass
class FeederLoadImportResult:
    """Parsed feeder loads and non-fatal row warnings."""
    feeder_pq: dict[str, dict[str, float]] = field(default_factory=dict)
    rows_read: int = 0
    warnings: list[str] = field(default_factory=list)


def _norm_header(value) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", " ", text.replace("ي", "ی").replace("ك", "ک"))


def _find_columns(values: tuple) -> tuple[int, int, int] | None:
    """Recognize the provided Persian headers and common English labels."""
    headers = [_norm_header(v) for v in values]
    feeder_col = p_col = q_col = None
    for i, h in enumerate(headers):
        if ("نام فیدر" in h or "feeder name" in h or h in {"feeder", "feeder_key"}):
            feeder_col = i
        if ("توان اکتیو" in h or "active power" in h or "p_load" in h
                or h.startswith("p (")):
            p_col = i
        if ("توان راکتیو" in h or "reactive power" in h or "q_load" in h
                or h.startswith("q (")):
            q_col = i
    if feeder_col is None or p_col is None or q_col is None:
        return None
    return feeder_col, p_col, q_col


def _to_float(value) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, str):
        value = value.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
                                               "01234567890123456789"))
        value = value.replace(",", "").strip()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _unit_scale(header: str, power_kind: str) -> float:
    """Convert a column to kW/kvar. Headers without units mean kW/kvar."""
    h = _norm_header(header).replace(" ", "")
    if power_kind == "p" and ("mw" in h or "مگاوات" in h):
        return 1000.0
    if power_kind == "q" and ("mvar" in h or "mvar" in h or "مگاوار" in h):
        return 1000.0
    return 1.0


def read_feeder_load_workbook(path: str) -> FeederLoadImportResult:
    """Read feeder name, active and reactive power columns from an xlsx.

    Values in MW/MVAr are converted to kW/kvar. Conflicting duplicate
    feeder rows are excluded (rather than silently picking/summing a value)
    and described in ``warnings`` so the user can resolve them manually.
    """
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    result = FeederLoadImportResult()
    parsed: dict[str, list[tuple[int, str, float, float]]] = defaultdict(list)
    found_header = False
    try:
        for sheet in workbook.worksheets:
            header_row = None
            columns = None
            for row_num, values in enumerate(sheet.iter_rows(values_only=True), 1):
                columns = _find_columns(values)
                if columns is not None:
                    header_row = row_num
                    header_values = values
                    found_header = True
                    break
            if header_row is None:
                continue
            feeder_col, p_col, q_col = columns
            p_scale = _unit_scale(str(header_values[p_col] or ""), "p")
            q_scale = _unit_scale(str(header_values[q_col] or ""), "q")
            for row_num, values in enumerate(
                    sheet.iter_rows(min_row=header_row + 1, values_only=True),
                    header_row + 1):
                if feeder_col >= len(values):
                    continue
                name = str(values[feeder_col] or "").strip()
                if not name:
                    continue
                result.rows_read += 1
                p = _to_float(values[p_col] if p_col < len(values) else None)
                q = _to_float(values[q_col] if q_col < len(values) else None)
                if p is None or p <= 0 or q is None or q < 0:
                    result.warnings.append(
                        f"{sheet.title}!{row_num}: مقدار P/Q نامعتبر است؛ "
                        f"ردیف «{name}» وارد نشد.")
                    continue
                key = feeder_id(name)
                if not key:
                    result.warnings.append(
                        f"{sheet.title}!{row_num}: شناسهٔ فیدر خالی/نامعتبر است.")
                    continue
                parsed[key].append((row_num, name, p * p_scale, q * q_scale))
    finally:
        workbook.close()

    if not found_header:
        raise ValueError(
            "سرستون‌های لازم پیدا نشدند. فایل باید ستون نام فیدر، توان اکتیو "
            "و توان راکتیو داشته باشد.")

    for key, entries in sorted(parsed.items()):
        unique_values = {(round(p, 9), round(q, 9)) for _, _, p, q in entries}
        if len(unique_values) > 1:
            locations = ", ".join(
                f"ردیف {row}: {name} (P={p:g}, Q={q:g})"
                for row, name, p, q in entries)
            result.warnings.append(
                f"فیدر تکراری با مقادیر متعارض وارد نشد ({locations}); "
                "مقدار آن را دستی تعیین کنید.")
            continue
        _, _, p, q = entries[0]
        result.feeder_pq[key] = {"p_kw": p, "q_kvar": q}
    return result
