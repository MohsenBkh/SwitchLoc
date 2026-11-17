# -*- coding: utf-8 -*-
"""GIS-to-DigSILENT type catalog resolution with explicit ambiguity reporting.

The workbook is a reference catalog, not a GIS source. A type is selected only
when the available GIS identity fields identify exactly one workbook row under
the documented matching rules below; no nearest-size or feeder-name guessing
is used.
"""
from __future__ import annotations

import math
import os
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

TYPES_CATALOG_ENV_VAR = "SWITCHLOC_TYPES_CATALOG"
_TYPES_CATALOG_RELATIVE = Path("data") / "catalog" / "types_override.xlsx"


def default_types_catalog_path() -> Path:
    """Find the type workbook in dev, PyInstaller onefile, or packaged dist."""
    override = os.environ.get(TYPES_CATALOG_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    candidates = []
    executable = getattr(sys, "executable", None)
    if executable:
        candidates.append(Path(executable).resolve().parent / _TYPES_CATALOG_RELATIVE)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / _TYPES_CATALOG_RELATIVE)
    candidates.append(Path(__file__).resolve().parents[3] / _TYPES_CATALOG_RELATIVE)
    return next((path for path in candidates if path.is_file()), candidates[-1])


DEFAULT_TYPES_CATALOG = default_types_catalog_path()


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ـ", "")
    return " ".join(re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).split())


def _number(value: Any) -> float | None:
    try:
        if value is None or not math.isfinite(float(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class TypeResolution:
    equipment_id: str
    feeder: str
    equipment: str
    status: str  # matched | ambiguous | unmatched | unsupported | unusable
    selected_type: str | None = None
    candidates: tuple[str, ...] = ()
    gis_identity: dict | None = None
    reason: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class EquipmentTypeCatalog:
    """Read workbook types and resolve GIS equipment without silent defaults."""

    def __init__(self, path: str | Path = DEFAULT_TYPES_CATALOG):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"فایل کاتالوگ تایپ تجهیزات پیدا نشد: {self.path}")
        workbook = load_workbook(self.path, read_only=True, data_only=True)
        try:
            self.lines = self._rows(workbook, "TypLne")
            self.transformers = self._rows(workbook, "TypTr2")
            self.fuses = self._rows(workbook, "TypFuse")
            self.loads = self._rows(workbook, "TypLod")
        finally:
            workbook.close()
        self.source = str(self.path)

    @staticmethod
    def _rows(workbook, sheet: str) -> list[dict]:
        if sheet not in workbook.sheetnames:
            return []
        values = workbook[sheet].iter_rows(values_only=True)
        headers = [str(x or "") for x in next(values, ())]
        return [dict(zip(headers, row, strict=False)) for row in values if row and row[0]]

    @staticmethod
    def _type_name(row: dict) -> str:
        return str(row.get("loc_name(a:40)") or "").strip()

    def line_ampacity_a(self, type_name: str) -> float | None:
        """Read continuous current Sline in kA and return amperes."""
        rows = [row for row in self.lines if self._type_name(row) == type_name]
        if len(rows) != 1:
            return None
        # Sline(r) is the continuous current rating in kA; Ithr is short-circuit current.
        value = _number(rows[0].get("sline(r)"))
        return value * 1000.0 if value is not None and value > 0 else None

    def _line_name_candidate(self, branch) -> tuple[str | None, str]:
        kind = getattr(getattr(branch, "kind", None), "value", getattr(branch, "kind", ""))
        conductor = _norm(getattr(branch, "conductor", ""))
        section = _number(getattr(branch, "section_mm2", None))
        installation = _norm(getattr(branch, "installation", ""))
        size = int(round(section)) if section is not None else None
        if kind == "line_underground":
            if size is None:
                return None, "کابل زمینی: سطح مقطع GIS ثبت نشده است."
            # Exact section + explicit material + underground GIS class. The
            # workbook identity distinguishes Cu and Al cable variants.
            if "مس" in conductor and size in {35, 50, 70, 95, 120, 150, 185, 240}:
                return f"N2XSY 1x{size}/16 (12/20kV)", "تطبیق دقیق مس/سطح مقطع/زمینی"
            if ("آلومینیوم" in conductor or "الومینیوم" in conductor) and size in {35, 50, 70, 95, 120, 150, 185, 240, 300}:
                return f"NA2XSY 1x{size}/16 (12/20kV)", "تطبیق دقیق آلومینیوم/سطح مقطع/زمینی"
            return None, "جنس یا سطح مقطع کابل در کاتالوگ متناظر نیست."
        if kind == "line_aerial":
            bare = any(word in installation for word in ("لخت", "bare", "uncovered"))
            if not bare:
                return None, "برای خط هوایی، هادی لخت به‌طور صریح در GIS مشخص نشده است."
            if ("acsr" in conductor or "فولاد" in conductor) and size in (35, 70):
                return f"{size}-Al_St", "تطبیق دقیق ACSR/آلومینیوم-فولاد/سطح مقطع/هوایی لخت"
            if "هاینا" in conductor or "hyena" in conductor:
                return "ACSR-HYENA", "نام هادی GIS با نام تایپ کاتالوگ منطبق است."
            return None, "برای این هویت هادی هوایی تایپ یکتای مستند در کاتالوگ وجود ندارد."
        return None, f"نوع شاخهٔ {kind or 'نامشخص'} در قواعد تطبیق خط پشتیبانی نمی‌شود."

    def resolve_branch(self, branch) -> TypeResolution:
        feeder = str(getattr(branch, "feeder_name", "") or "")
        branch_id = str(getattr(branch, "id", "") or "")
        identity = {
            "conductor": getattr(branch, "conductor", ""),
            "section_mm2": getattr(branch, "section_mm2", None),
            "installation": getattr(branch, "installation", ""),
            "kind": getattr(getattr(branch, "kind", None), "value", getattr(branch, "kind", "")),
        }
        conductor_tokens = _norm(getattr(branch, "conductor", "")).split()
        aliases = {"مینک": "mink", "سمور": "mink", "روباه": "fox",
                   "خرگوش": "rabbit", "راسوی": "weasel", "هاینا": "hyena",
                   "سگ": "dog", "وشق": "lynx"}
        conductor_tokens = [aliases.get(token, token) for token in conductor_tokens]
        conductor_name = " ".join(conductor_tokens)
        explicit_rows = [r for r in self.lines
                         if _norm(self._type_name(r))
                         and _norm(self._type_name(r)) in conductor_name]
        if not explicit_rows:
            animal_tokens = {"mink", "fox", "rabbit", "weasel", "hyena", "dog", "lynx"}
            identified = set(conductor_tokens) & animal_tokens
            if identified:
                explicit_rows = [r for r in self.lines
                                 if set(_norm(self._type_name(r)).split()) & identified]
        explicit_names = tuple(dict.fromkeys(self._type_name(r) for r in explicit_rows))
        if len(explicit_names) > 1:
            return TypeResolution(
                branch_id, feeder, "line", "ambiguous", candidates=explicit_names,
                gis_identity=identity,
                reason="نام هادی GIS با چند تایپ کاتالوگ سازگار است؛ نوع دقیق‌تر لازم است.")
        wanted, reason = self._line_name_candidate(branch)
        if len(explicit_names) == 1:
            wanted = explicit_names[0]
            reason = "نام تایپ صریح در فیلد هادی GIS با کاتالوگ منطبق شد."
        if not wanted:
            status = "unsupported" if "پشتیبانی" in reason else "unmatched"
            return TypeResolution(branch_id, feeder, "line", status,
                                  gis_identity=identity, reason=reason)
        rows = [r for r in self.lines if self._type_name(r) == wanted]
        names = tuple(self._type_name(r) for r in rows)
        if len(rows) != 1:
            return TypeResolution(branch_id, feeder, "line",
                                  "ambiguous" if rows else "unmatched",
                                  candidates=names, gis_identity=identity,
                                  reason=("چند ردیف با نام تایپ یکسان در workbook." if rows
                                          else f"تایپ پیشنهادی {wanted!r} در workbook پیدا نشد."))
        row = rows[0]
        r_ohm = _number(row.get("rline(r)"))
        x_ohm = _number(row.get("xline(r)"))
        if r_ohm is None or x_ohm is None or r_ohm <= 0 or x_ohm < 0:
            return TypeResolution(branch_id, feeder, "line", "unusable",
                                  candidates=(wanted,), gis_identity=identity,
                                  reason="ردیف تایپ R/X مثبت و قابل استفاده برای توالی مثبت ندارد؛ اعمال نشد.")
        return TypeResolution(branch_id, feeder, "line", "matched", wanted,
                              (wanted,), identity, reason)

    def resolve_transformer(self, transformer) -> TypeResolution:
        capacity = _number(getattr(transformer, "capacity_kva", None))
        identity = {"capacity_kva": capacity,
                    "kind_raw": getattr(transformer, "kind_raw", "")}
        feeder = str(getattr(transformer, "feeder_name", "") or "")
        tid = str(getattr(transformer, "id", "") or "")
        if capacity is None:
            return TypeResolution(tid, feeder, "transformer", "unmatched",
                                  gis_identity=identity, reason="ظرفیت GIS موجود نیست.")
        rows = [r for r in self.transformers
                if _number(r.get("strn(r)")) is not None
                and math.isclose(_number(r.get("strn(r)")) * 1000, capacity,
                                 rel_tol=0, abs_tol=0.5)]
        names = tuple(self._type_name(r) for r in rows)
        if len(rows) == 1:
            return TypeResolution(tid, feeder, "transformer", "matched", names[0],
                                  names, identity,
                                  "ظرفیت نامی دقیقاً برابر است و در workbook فقط یک کاندید دارد.")
        return TypeResolution(tid, feeder, "transformer",
                              "ambiguous" if rows else "unmatched",
                              candidates=names, gis_identity=identity,
                              reason=("چند تایپ با ظرفیت یکسان؛ GIS نوع سازنده/سری را مشخص نمی‌کند."
                                      if rows else "ظرفیت دقیق متناظر در workbook وجود ندارد."))

    def resolve_switch(self, switch, voltage_kv: float | None = 20.0) -> TypeResolution:
        family = getattr(getattr(switch, "family", None), "value", getattr(switch, "family", ""))
        rating = _number(getattr(switch, "rating_a", None))
        feeder = str(getattr(switch, "feeder_name", "") or "")
        sid = str(getattr(switch, "id", "") or "")
        identity = {"family": family, "rating_a": rating, "voltage_kv": voltage_kv,
                    "switch_type_raw": getattr(switch, "switch_type_raw", "")}
        if family != "fuse_cutout":
            return TypeResolution(sid, feeder, "switch", "unsupported",
                                  gis_identity=identity,
                                  reason="workbook فقط TypFuse دارد؛ برای این خانواده تایپ مرجع موجود نیست.")
        if rating is None:
            return TypeResolution(sid, feeder, "fuse", "unmatched",
                                  gis_identity=identity, reason="جریان نامی GIS موجود نیست.")
        rows = [r for r in self.fuses
                if _number(r.get("irat(r)")) is not None
                and math.isclose(_number(r.get("irat(r)")), rating, abs_tol=0.01)
                and (voltage_kv is None or (_number(r.get("urat(r)")) is not None
                     and math.isclose(_number(r.get("urat(r)")), voltage_kv, abs_tol=0.01)))]
        names = tuple(self._type_name(r) for r in rows)
        if len(rows) == 1:
            return TypeResolution(sid, feeder, "fuse", "matched", names[0], names,
                                  identity, "جریان و ولتاژ نامی دقیقاً منطبق است.")
        return TypeResolution(sid, feeder, "fuse", "ambiguous" if rows else "unmatched",
                              candidates=names, gis_identity=identity,
                              reason="تطبیق یکتا با جریان/ولتاژ GIS به‌دست نیامد.")

    def resolve_network(self, network, voltage_kv: float | None = 20.0) -> list[TypeResolution]:
        results = [self.resolve_branch(x) for x in (network.branches or [])]
        results.extend(self.resolve_transformer(x) for x in (network.transformers or []))
        results.extend(self.resolve_switch(x, voltage_kv) for x in (network.switches or []))
        return results


def resolution_report(resolutions: list[TypeResolution]) -> dict:
    by_feeder: dict[str, dict] = {}
    for resolution in resolutions:
        feeder = resolution.feeder or "(فیدر نامشخص)"
        item = by_feeder.setdefault(feeder, {"counts": {}, "items": []})
        item["counts"][resolution.status] = item["counts"].get(resolution.status, 0) + 1
        item["items"].append(resolution.as_dict())
    return {"feeders": by_feeder,
            "totals": {status: sum(x["counts"].get(status, 0) for x in by_feeder.values())
                       for status in ("matched", "ambiguous", "unmatched", "unsupported", "unusable")}}
