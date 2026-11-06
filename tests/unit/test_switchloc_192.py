from __future__ import annotations
import sys
from pathlib import Path
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path: sys.path.insert(0, str(SRC))

from switchloc.reliability.load_model import LoadModelSettings, LEVEL_SCALED
from switchloc.domain.enums import SwitchFamily, SwitchState, NodeKind
from switchloc.domain.entities import SwitchDev, Transformer
from switchloc.topology.graph import NetworkGraph, GraphNode, GraphEdge
from switchloc.topology.tracing import FeederTrace
from switchloc.topology.zones import ZoneBuilder, ZonePolicy
from switchloc.validation.issues import IssueLog
from switchloc.ui.map_renderer import switch_display_code

def test_default_load_model_is_load_scaling():
    assert LoadModelSettings().level == LEVEL_SCALED

def test_switch_code_distinguishes_five_device_families():
    pairs = [(SwitchFamily.FUSE_CUTOUT, "FCT", "FCT"),
             (SwitchFamily.DISCONNECTOR, "DCS", "DCS"),
             (SwitchFamily.BREAKER, "CBR", "CBR"),
             (SwitchFamily.RECLOSER, "REC", "REC"),
             (SwitchFamily.SECTIONALIZER, "SEC", "SEC")]
    for family, raw, expected in pairs:
        assert switch_display_code(SwitchDev(family=family, node_id="n", switch_type_raw=raw)) == expected

def test_transformer_terminal_switch_does_not_cut_zone():
    g = NetworkGraph()
    g.nodes["n0"] = GraphNode(id="n0", kind=NodeKind.SOURCE, coord=(0,0), feeder_hint="F1")
    g.nodes["n1"] = GraphNode(id="n1", kind=NodeKind.JUNCTION, coord=(100,0), feeder_hint="F1")
    g.nodes["n2"] = GraphNode(id="n2", kind=NodeKind.JUNCTION, coord=(200,0), feeder_hint="F1")
    for i,(a,b) in enumerate((("n0","n1"),("n1","n2"))):
        e=GraphEdge(id=f"e{i}", branch_id="b", seq=i, a=a,b=b,length_m=100,kind="overhead",feeder_hint="F1")
        g.edges[e.id]=e; g.adj[a].append((b,e.id)); g.adj[b].append((a,e.id))
    sw=SwitchDev(family=SwitchFamily.FUSE_CUTOUT,node_id="n1",normally_state="NC")
    g.switch_ids_at["n1"].append(sw.id)
    g.transformer_ids_at["n1"].append("t1")
    net=type("Net",(),{"switches":[sw],"transformers":[Transformer(node_id="n1",capacity_kva=100,id="t1")],"loads":[]})()
    trace=FeederTrace(feeder="F1",feeder_key="F1",source_node="n0",nodes={"n0","n1","n2"},edges={"e0","e1"})
    builder=ZoneBuilder(g,net,[trace],ZonePolicy())
    assert builder.node_is_cut("n1") is False


def test_utm_zone38_same_crs_is_exact():
    from switchloc.gis.crs import transform_utm_to_project
    x, y = transform_utm_to_project(500000, 3950000, 38, "EPSG:32638")
    assert abs(x-500000) < 1e-6 and abs(y-3950000) < 1e-6

def test_utm_zone39_to_zone38_is_transformed():
    from switchloc.gis.crs import transform_utm_to_project
    x, y = transform_utm_to_project(500000, 3950000, 39, "EPSG:32638")
    assert abs(x-500000) > 1000
    assert abs(y-3950000) < 100000

def test_invalid_utm_zone_is_rejected():
    import pytest
    from switchloc.gis.crs import transform_utm_to_project
    with pytest.raises(ValueError):
        transform_utm_to_project(500000, 3950000, 40, "EPSG:32638")


def test_scoped_feeder_keys_returns_only_selected_feeder():
    from switchloc.ui.inputs_model import scoped_feeder_keys
    assert scoped_feeder_keys(["F3", "F4", "F5"], "F4") == ["F4"]
    assert scoped_feeder_keys(["F3", "F4"], None) == ["F3", "F4"]
    assert scoped_feeder_keys(["F3", "F4"], "F9") == []

def test_outage_records_are_filtered_before_classification():
    from types import SimpleNamespace
    from switchloc.application.outage_service import filter_records_by_scope
    records = [SimpleNamespace(feeder_key="F3"),
               SimpleNamespace(feeder_key="F4"),
               SimpleNamespace(feeder_key="F4"),
               SimpleNamespace(feeder_key="F5")]
    kept, excluded = filter_records_by_scope(records, "F4")
    assert len(kept) == 2 and excluded == 2
    assert all(r.feeder_key == "F4" for r in kept)

def test_map_style_roundtrip_has_separate_device_symbols():
    from switchloc.ui.map_style import MapStyle
    st = MapStyle()
    st.fct_color = "#010203"; st.rec_marker = "D"
    out = MapStyle.from_dict(st.as_dict())
    assert out.fct_color == "#010203" and out.rec_marker == "D"


def test_load_scaling_input_validation_is_scope_aware():
    from switchloc.ui.inputs_model import missing_load_scaling_inputs
    pq = {"F3": {"p_kw": 1000, "q_kvar": 300},
          "F4": {"p_kw": 0, "q_kvar": 0},
          "F5": {"p_kw": 250, "q_kvar": 0},
          "F6": {"p_kw": 600}}
    assert missing_load_scaling_inputs(["F3"], pq) == []
    assert missing_load_scaling_inputs(["F4"], pq) == ["F4"]
    assert missing_load_scaling_inputs(["F3", "F4", "F5"], pq) == ["F4"]
    assert missing_load_scaling_inputs(["F6"], pq) == ["F6"]


def test_utm_conversion_rejects_non_metre_project_crs():
    import pytest
    from switchloc.gis.crs import transform_utm_to_project
    # EPSG:2263 is projected but uses US survey feet.
    with pytest.raises(ValueError):
        transform_utm_to_project(500000, 3950000, 38, "EPSG:2263")
