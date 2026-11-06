# -*- coding: utf-8 -*-
"""GIS field catalog — real field names of the utility's shapefile exports.

Provenance (recorded per main-prompt §5 legal rules):
* observed directly in the Khalkhal sample export (Export_1404_08_17_12_34_09),
* cross-checked against the *documented knowledge* of GeoGrid 4.2.0's
  config.json (reuse audit doc §10 "config.json").  No GeoGrid code is
  imported or copied; only the field-name knowledge is re-used as data.
"""
from __future__ import annotations

# --- attribute-name candidates, in fallback priority order -----------------
ID_FIELDS = ["T_MapID", "OBJECTID", "GlobalID"]                      # stable record id
FEEDER_FIELDS = ["Feeder", "T_FeederNa", "T_feader", "T_name_fdr"]   # documented chain
LENGTH_FIELDS = ["Shape_STLe", "T_FeatureL"]                         # metres
SERVICE_FIELD = "T__outserv"                                          # service state
REMOTE_CTRL_FIELD = "T_ctrl_otm"                                      # remote control
CONDUCTOR_FIELD = "T_jns_hadi"
SECTION_FIELD = "T_cod_sath"
NETTYPE_FIELD = "T_typ_shab"
CAPACITY_FIELD = "T_strn"                                             # transformer kVA
RATED_CURRENT_FIELDS = ["T_jar_nami", "T_jar_etsl"]                   # amps
LOCAL_NAME_FIELDS = ["T_nam_ght", "T_lname", "Name", "T_NAME"]
SWITCH_TYPE_FIELDS = ["T_type", "T_noe_sec", "T_noe_kld"]

#: values of T__outserv that mean "out of service".
_OUT_SERVICE_VALUES = {"1", "true", "خارج از مدار"}
#: values that mean "in service" (explicit).
_IN_SERVICE_VALUES = {"در مدار", "0", "false"}
#: values of T_ctrl_otm meaning "yes / remote controllable".
_YES_VALUES = {"بلي", "بله", "yes", "true", "1"}
_NO_VALUES = {"خير", "خیر", "no", "false", "0"}

UNKNOWN = ""  # canonical "missing" string value


def s(v) -> str:
    """Coerce a DBF attribute to a stripped string ('' for None)."""
    return "" if v is None else str(v).strip()


def first_value(rec: dict, fields, default=UNKNOWN):
    """First non-empty value among `fields`, else `default`."""
    for f in fields:
        v = s(rec.get(f))
        if v:
            return v
    return default


def record_id(rec: dict) -> str:
    return first_value(rec, ID_FIELDS)


def feeder_name(rec: dict) -> str:
    """Feeder name via the documented fallback chain."""
    return first_value(rec, FEEDER_FIELDS)


def service_state(rec: dict, field: str = SERVICE_FIELD) -> str:
    """Map T__outserv to 'in' | 'out' | 'unknown'.

    Provenance: GeoGrid 4.2.0 `Converter._switch_on` treats
    {'1','true','خارج از مدار'} as off; empty is treated as on there, but
    SwitchLoc keeps 'unknown' for empty to honour main-prompt rule
    «وضعیت نامشخص کلید» (QC item §7) — an empty value becomes an
    Information issue at reader level, not a silent assumption.
    """
    v = s(rec.get(field))
    if v == "":
        return "unknown"
    if v in _OUT_SERVICE_VALUES:
        return "out"
    if v in _IN_SERVICE_VALUES:
        return "in"
    return "unknown"


def remote_controlled(rec: dict, field: str = REMOTE_CTRL_FIELD) -> str:
    """Map T_ctrl_otm to 'yes' | 'no' | 'unknown'."""
    v = s(rec.get(field))
    if v == "":
        return "unknown"
    if v in _YES_VALUES:
        return "yes"
    if v in _NO_VALUES:
        return "no"
    return "unknown"


def w_prefix_alias(name: str):
    """ELWxxx <-> ELxxx layer-name alias.

    Provenance: this utility's exports are seen with and without the 'W'
    after 'EL' (GeoGrid 4.2.0 `shapefile_io._w_prefix_alias` behaviour,
    re-implemented independently).  Returns None if the name doesn't
    start with 'EL'.
    """
    if name.startswith("ELW"):
        return "EL" + name[3:]
    if name.startswith("EL"):
        return "ELW" + name[2:]
    return None
