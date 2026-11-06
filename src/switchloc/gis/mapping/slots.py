# -*- coding: utf-8 -*-
"""Equipment slot catalog (docs/DATA_MODEL.md §۵ + GeoGrid audit §۱۰).

Provenance: slot *pattern* follows GeoGrid 4.2.0 `EquipmentSlot` (audit
doc §۳-۲); the slot set is extended per main prompt §۳-۲ (۱۶+ device
types).  Layer aliases come from the Khalkhal real export + documented
GeoGrid config knowledge — data, not copied code.

A slot is a *semantic* role a GIS layer can play.  The mapping service
suggests slots for discovered layers, but nothing is final until the
user confirms (main prompt §۵-۳: «هیچ نگاشت خودکاری قطعی نیست»).
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field


@dataclass(frozen=True)
class EquipmentSlot:
    key: str
    label_fa: str
    category: str          # line | switch | fuse | transformer | source | other
    geometry: str          # point | line | any
    layer_aliases: tuple = ()      # observed layer-name aliases (ELW*/EL*)
    priority: int = 50             # suggestion ranking (lower = better)
    notes: str = ""


SLOTS: dict[str, EquipmentSlot] = {s.key: s for s in [
    # --- lines -------------------------------------------------------------
    EquipmentSlot("mv_line_aerial", "خط هوایی فشار متوسط", "line", "line",
                  ("ELWOML", "ELOML"), 10, "هادی هوایی اصلی (ACSR/...)"),
    EquipmentSlot("mv_line_underground", "خط زمینی/کابل فشار متوسط", "line", "line",
                  ("ELWUML", "ELUML"), 11, "کابل زمینی"),
    EquipmentSlot("mv_line_network", "خط شبکه فشار متوسط (سایر)", "line", "line",
                  ("ELWMLN", "ELMLN"), 12),
    EquipmentSlot("mv_jumper", "جمپر فشار متوسط", "line", "line",
                  ("ELWJUP", "ELJUP"), 13, "اتصال پرشی بین دو نقطه"),
    EquipmentSlot("mv_line_misc", "سایر خطوط فشار متوسط", "line", "line",
                  ("ELWMSC", "ELMSC"), 90),
    # --- devices -----------------------------------------------------------
    EquipmentSlot("transformer", "ترانسفورماتور توزیع", "transformer", "point",
                  ("ELWDTR", "ELDTR"), 20),
    EquipmentSlot("fuse_cutout", "کات اوت فیوز", "fuse", "point",
                  ("ELWFCT", "ELFCT"), 21),
    EquipmentSlot("switch_manual", "کلید سکسیونر (دستی/جردن)", "switch", "point",
                  ("ELWDCS", "ELDCS"), 22, "LBS/کندسوز؛ T_ctrl_otm=بلي → موتوردار"),
    EquipmentSlot("breaker", "بریکر/مدارشکن", "switch", "point",
                  ("ELWCBR", "ELCBR"), 23),
    EquipmentSlot("recloser", "ریکلوژر", "switch", "point",
                  ("ELWREC", "ELREC"), 24),
    EquipmentSlot("sectionalizer", "سکشنلایزر", "switch", "point",
                  (), 25, "لایه اختصاصی در صورت وجود"),
    EquipmentSlot("source_feeder", "منبع/کلید سرخط فیدر (پست)", "source", "point",
                  ("ELWFWT", "ELFWT"), 26),
    EquipmentSlot("booster", "اتوبوستر/تنظیم‌کننده ولتاژ", "other", "point",
                  ("ELWABS", "ELABS"), 27),
    EquipmentSlot("capacitor", "خازن فشار متوسط", "other", "point",
                  (), 28, "لایه اختصاصی در صورت وجود"),
    EquipmentSlot("dg_source", "تولید پراکنده", "source", "point",
                  (), 29, "لایه اختصاصی در صورت وجود"),
    EquipmentSlot("substation", "پست فوق‌توزیع/توزیع", "other", "point",
                  (), 30),
    # --- fallback ----------------------------------------------------------
    EquipmentSlot("unmapped", "بدون نقش (نیازمند تصمیم کاربر)", "other", "any",
                  (), 999),
]}

SLOT_BY_ALIAS: dict[str, EquipmentSlot] = {}
for _s in SLOTS.values():
    for _a in _s.layer_aliases:
        SLOT_BY_ALIAS[_a.upper()] = _s


def slot_for_layer_name(name: str) -> EquipmentSlot | None:
    """Resolve a slot from the layer base name (ELWxxx ↔ ELxxx aliasing)."""
    n = name.upper()
    return SLOT_BY_ALIAS.get(n)


def slot_for_unknown_layer(name: str) -> EquipmentSlot:
    return SLOTS["unmapped"]
