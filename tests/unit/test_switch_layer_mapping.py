# -*- coding: utf-8 -*-
"""ELWSEC is a sectionalizer layer, never a disconnector (DCS)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from switchloc.domain.enums import SwitchFamily
from switchloc.gis.mapping.slots import slot_for_layer_name
from switchloc.ui.map_renderer import switch_display_code


class _Switch:
    def __init__(self, family, raw="", layer=""):
        self.family = family
        self.switch_type_raw = raw
        self.layer = layer


def test_elwsec_layer_maps_to_sectionalizer_slot():
    assert slot_for_layer_name("ELWSEC").key == "sectionalizer"
    assert slot_for_layer_name("ELSEC").key == "sectionalizer"


def test_sectionalizer_is_not_rendered_as_disconnector():
    sw = _Switch(SwitchFamily.SECTIONALIZER)
    assert switch_display_code(sw) == "SEC"
    assert switch_display_code(_Switch(SwitchFamily.DISCONNECTOR)) == "DCS"


def test_legacy_elwsec_device_renders_as_sec_not_dcs():
    """DBs imported before the ELWSEC slot alias stored SEC devices as
    DISCONNECTOR; the layer name must still render them as SEC."""
    legacy = _Switch(SwitchFamily.DISCONNECTOR, raw="نامعلوم", layer="ELWSEC")
    assert switch_display_code(legacy) == "SEC"
    assert switch_display_code(_Switch(SwitchFamily.DISCONNECTOR, layer="ELWDCS")) == "DCS"
