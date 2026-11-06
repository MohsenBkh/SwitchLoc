# -*- coding: utf-8 -*-
"""Test path bootstrap + synthetic network builders (Phase 2)."""
import math
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from switchloc.domain.entities import (Branch, CanonicalNetwork, LineSegment,  # noqa: E402
                                       LoadPt, Node, SourceRecord, SwitchDev,
                                       Transformer)
from switchloc.domain.enums import (BranchKind, NodeKind, SwitchFamily,       # noqa: E402
                                    SwitchState, YesNoUnknown)


class NetBuilder:
    """Deterministic synthetic MV network for topology tests.

    Coordinates are integers on a grid so the graph matcher (tolerance
    0.75 m default) always finds the exact junction nodes.
    """

    def __init__(self):
        self.net = CanonicalNetwork(project_name="synthetic")
        self._nodes: dict[tuple, Node] = {}
        self._rec = 0

    def _source_record(self, layer: str) -> SourceRecord:
        self._rec += 1
        src = SourceRecord(file_path="synthetic", file_sha256="0" * 64,
                           layer=layer, record_ref=f"R{self._rec}")
        self.net.source_records.append(src)
        return src

    def junction(self, x: float, y: float, feeder: str = "") -> Node:
        key = (round(float(x), 3), round(float(y), 3))
        if key not in self._nodes:
            nd = Node(kind=NodeKind.JUNCTION, coord_original=key,
                      coord_snapped=key, feeder_name=feeder)
            self.net.nodes.append(nd)
            self._nodes[key] = nd
        return self._nodes[key]

    def line(self, pts, feeder: str = "",
             kind: BranchKind = BranchKind.LINE_AERIAL,
             registered: float | None = None) -> Branch:
        """Mirror the Phase-1 assembler: EVERY polyline vertex becomes a
        junction node (all vertices enter the Phase-1 snap cloud)."""
        pts = [tuple(p) for p in pts]
        for p in pts:
            self.junction(*p)
        segs, geo = [], 0.0
        for i in range(len(pts) - 1):
            d = math.dist(pts[i], pts[i + 1])
            geo += d
            segs.append(LineSegment(a=pts[i], b=pts[i + 1], length_m=d))
        # distribute the registered length proportionally — same rule as
        # gis.segmentation.split_polyline (GG-03)
        base = registered if (registered is not None and registered > 0) else geo
        if geo > 0:
            for s in segs:
                s.length_m = base * (s.length_m / geo)
        br = Branch(
            kind=kind, node_a=self.junction(*pts[0]).id,
            node_b=self.junction(*pts[-1]).id,
            length_registered_m=(registered if registered is not None else geo),
            length_geometric_m=geo, segments=segs, feeder_name=feeder,
            source=self._source_record("TESTLINE"))
        self.net.branches.append(br)
        return br

    def switch(self, x, y, family=SwitchFamily.DISCONNECTOR,
               state=SwitchState.IN_SERVICE, normally: str = "",
               remote=YesNoUnknown.UNKNOWN, feeder: str = "",
               layer: str = "ELWDCS") -> SwitchDev:
        nd = self.junction(x, y)
        sw = SwitchDev(family=family, node_id=nd.id,
                       current_state=state, normally_state=normally,
                       remote_controlled=remote, feeder_name=feeder,
                       layer=layer, source=self._source_record(layer))
        self.net.switches.append(sw)
        return sw

    def transformer(self, x, y, kva: float = 400, feeder: str = ""):
        nd = self.junction(x, y)
        tr = Transformer(node_id=nd.id, capacity_kva=kva, feeder_name=feeder,
                         source=self._source_record("ELWDTR"))
        self.net.transformers.append(tr)
        self.net.loads.append(LoadPt(node_id=nd.id, transformer_id=tr.id,
                                     data_source="unassigned",
                                     source=self._source_record("ELWDTR")))
        return tr

    def source(self, x, y, feeder: str) -> Node:
        nd = Node(kind=NodeKind.SOURCE, coord_original=(float(x), float(y)),
                  coord_snapped=(float(x), float(y)), feeder_name=feeder)
        self.net.nodes.append(nd)
        return nd
