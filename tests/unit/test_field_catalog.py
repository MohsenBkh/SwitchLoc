# -*- coding: utf-8 -*-
"""GG-07/GG-08 — field-catalog behaviour against real observed values."""
from switchloc.gis.mapping import field_catalog as fc


def test_feeder_fallback_chain_order():
    rec = {"T_name_fdr": "خلخال", "T_feader": "F5 - KHALKHAL", "T_FeederNa": ""}
    # priority: Feeder > T_FeederNa > T_feader > T_name_fdr
    assert fc.feeder_name(rec) == "F5 - KHALKHAL"
    rec2 = {"T_name_fdr": "خلخال", "Feeder": "F4 - HATCHTCHIN"}
    assert fc.feeder_name(rec2) == "F4 - HATCHTCHIN"


def test_feeder_all_empty():
    assert fc.feeder_name({"Feeder": None, "T_FeederNa": " "}) == ""


def test_service_state_real_values():
    assert fc.service_state({"T__outserv": "خارج از مدار"}) == "out"
    assert fc.service_state({"T__outserv": "در مدار"}) == "in"
    assert fc.service_state({"T__outserv": None}) == "unknown"   # no silent assumption
    assert fc.service_state({"T__outserv": "1"}) == "out"


def test_remote_control_real_values():
    assert fc.remote_controlled({"T_ctrl_otm": "بلي"}) == "yes"
    assert fc.remote_controlled({"T_ctrl_otm": "خير"}) == "no"
    assert fc.remote_controlled({"T_ctrl_otm": None}) == "unknown"


def test_w_prefix_alias():
    assert fc.w_prefix_alias("ELWOML") == "ELOML"
    assert fc.w_prefix_alias("ELOML") == "ELWOML"
    assert fc.w_prefix_alias("XLAYER") is None


def test_record_id_priority():
    assert fc.record_id({"T_MapID": "ABELDTR13000457", "OBJECTID": "1066"}) \
        == "ABELDTR13000457"
