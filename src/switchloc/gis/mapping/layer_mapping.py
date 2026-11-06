# -*- coding: utf-8 -*-
"""Layer/field mapping service (main prompt §۵-۳, ARCHITECTURE.md §۲).

Cycle:  suggest()  →  (user review)  →  confirm()  →  persistable JSON.

No automatic mapping is ever final: a suggestion is only a *proposal*
with a confidence and a reason; `confirm()` records who confirmed and
when.  Field maps are validated against the layer's real fields.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from datetime import datetime
from typing import Optional

from ..readers.base import LayerInfo
from . import field_catalog as fc
from .slots import EquipmentSlot, SLOTS, slot_for_layer_name


@dataclass
class MappingSuggestion:
    layer_name: str
    file_path: str
    slot_key: str
    confidence: str                     # high | medium | none
    reason_fa: str
    field_map: dict = dc_field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "layer_name": self.layer_name, "file_path": self.file_path,
            "slot_key": self.slot_key, "confidence": self.confidence,
            "reason_fa": self.reason_fa, "field_map": self.field_map,
        }


# semantic field roles a slot may need (validated on confirm)
_ROLE_FIELDS = {
    "record_id": fc.ID_FIELDS,
    "feeder": fc.FEEDER_FIELDS,
    "length": fc.LENGTH_FIELDS,
    "service": [fc.SERVICE_FIELD],
    "remote": [fc.REMOTE_CTRL_FIELD],
    "capacity": [fc.CAPACITY_FIELD],
    "rated_current": fc.RATED_CURRENT_FIELDS,
    "conductor": [fc.CONDUCTOR_FIELD],
    "section": [fc.SECTION_FIELD],
    "installation": [fc.NETTYPE_FIELD],
    "local_name": fc.LOCAL_NAME_FIELDS,
    "switch_type": fc.SWITCH_TYPE_FIELDS,
}


def default_field_map(fields: list[str]) -> dict:
    """Propose field_map: role → real field name (first present)."""
    upper = {f.upper(): f for f in fields}
    out = {}
    for role, candidates in _ROLE_FIELDS.items():
        for c in candidates:
            if c in fields:
                out[role] = c
                break
            cu = c.upper()
            if cu in upper:            # case-insensitive match
                out[role] = upper[cu]
                break
    return out


class LayerMappingService:
    """Suggest → confirm workflow, with JSON persistence for the project."""

    def __init__(self):
        self.confirmed: dict[str, LayerMappingLike] = {}
        # LayerMapping imported lazily to avoid a domain↔gis cycle at import
        from ...domain.entities import LayerMapping
        self._entity_cls = LayerMapping

    # -- suggestions --------------------------------------------------------
    def suggest(self, layers: list[LayerInfo]) -> list[MappingSuggestion]:
        out = []
        for li in layers:
            slot, conf, reason = self._suggest_slot(li)
            out.append(MappingSuggestion(
                layer_name=li.name, file_path=li.path, slot_key=slot.key,
                confidence=conf, reason_fa=reason,
                field_map=default_field_map(li.fields),
            ))
        return out

    def _suggest_slot(self, li: LayerInfo):
        hit = slot_for_layer_name(li.name)
        if hit is not None:
            return hit, "high", (
                f"نام لایه «{li.name}» با نام‌های مستند نمونه واقعی و کاتالوگ "
                f"نقش‌ها مطابقت دارد ({hit.label_fa}).")
        # field-signature heuristic (medium confidence)
        fset = {f.upper() for f in li.fields}
        if fc.CAPACITY_FIELD.upper() in fset:
            return (SLOTS["transformer"], "medium",
                    "حضور فیلد ظرفیت ترانس (T_strn) نشانه ترانسفورماتور است.")
        if fc.REMOTE_CTRL_FIELD.upper() in fset or fc.SWITCH_TYPE_FIELDS[0].upper() in fset:
            return (SLOTS["switch_manual"], "medium",
                    "فیلدهای نوع کلید/کنترل از راه دور نشانه لایه کلید هستند.")
        return (SLOTS["unmapped"], "none",
                "نام لایه و امضای فیلدها با هیچ نقش شناخته‌شده منطبق نشد؛ "
                "انتخاب نقش الزاماً توسط کاربر انجام شود.")

    # -- confirmation -------------------------------------------------------
    def confirm(self, layer: LayerInfo, slot_key: str, confirmed_by: str,
                field_map: Optional[dict] = None, enabled: bool = True):
        """Record the user's final decision; validates the field map."""
        if slot_key not in SLOTS:
            raise ValueError(f"Unknown mapping role: {slot_key}")
        if not confirmed_by:
            raise ValueError("Mapping confirmation requires the confirmer's "
                             "name (rule §5-3: no automatic mapping is final).")
        fm = field_map if field_map is not None else default_field_map(layer.fields)
        unknown = [v for v in fm.values() if v not in layer.fields]
        if unknown:
            raise ValueError(f"Fields outside layer '{layer.name}': {unknown}")
        ent = self._entity_cls(
            slot_key=slot_key, file_path=layer.path, layer_name=layer.name,
            field_map=fm, enabled=enabled,
            confirmed_by=confirmed_by,
            confirmed_at=datetime.now().isoformat(timespec="seconds"))
        self.confirmed[layer.name] = ent
        return ent

    def load(self, data: list[dict]) -> None:
        """Restore previously confirmed mappings from project JSON."""
        for d in data:
            ent = self._entity_cls(**d)
            self.confirmed[ent.layer_name] = ent

    def dump(self) -> list[dict]:
        out = []
        for ent in self.confirmed.values():
            out.append({
                "slot_key": ent.slot_key, "file_path": ent.file_path,
                "layer_name": ent.layer_name, "field_map": ent.field_map,
                "enabled": ent.enabled, "confirmed_by": ent.confirmed_by,
                "confirmed_at": ent.confirmed_at,
            })
        return out

    def save_json(self, path) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.dump(), fh, ensure_ascii=False, indent=2)

    @staticmethod
    def load_json(path) -> "LayerMappingService":
        svc = LayerMappingService()
        with open(path, encoding="utf-8") as fh:
            svc.load(json.load(fh))
        return svc


#: type alias (imported lazily in __init__)
LayerMappingLike = object
