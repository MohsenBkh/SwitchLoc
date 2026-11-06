# -*- coding: utf-8 -*-
"""Network map renderer — Matplotlib headless (D-04, Phase 2).

Draws the NetworkGraph: edges coloured per feeder, boundary switches
marked (filled = closed/NC, hollow/open diamond = NO or out-of-service),
sources as squares, transformers as small dots, tie candidates starred.

Persian text is intentionally NOT drawn (see ui/__init__ — RTL shaping
limitation of Matplotlib); labels use technical codes only.  All Persian
reporting lives in the MD/JSON reports and the PySide6 shell.
"""
from __future__ import annotations

import re

import math

import matplotlib
matplotlib.use("Agg")                      # headless-safe
import matplotlib.pyplot as plt            # noqa: E402
from matplotlib.collections import LineCollection   # noqa: E402
from matplotlib.lines import Line2D        # noqa: E402

from ..domain.enums import NodeKind, SwitchState, SwitchFamily
from ..topology.graph import NetworkGraph
from ..topology.tracing import FeederTrace
from ..topology.zones import ZoneResult
from .map_style import (FEEDER_COLORS, MapStyle, UNKNOWN_COLOR)  # noqa: F401
# FEEDER_COLORS re-exported for dashboard_tab charts (backward compat)


def _feeder_selected(feeder: str | None, selection) -> bool:
    if selection is None:
        return True
    if isinstance(selection, (set, frozenset, list, tuple)):
        return feeder in selection
    return feeder == selection


def feeder_palette(traces: list[FeederTrace],
                   style: MapStyle | None = None) -> dict[str, str]:
    """feeder → colour — automatic palette overlaid with the user's
    MapStyle colours (تنظیمات نمایشی — درخواست کاربر). Kept as a module
    function for backward compatibility with existing callers/tests."""
    keys = sorted({t.feeder_key for t in traces if t.feeder_key})
    if style is not None:
        return style.palette_of(feeders=keys)
    from .map_style import auto_palette
    return auto_palette(feeders=keys)


def edge_color_of(graph: NetworkGraph, palette: dict[str, str],
                  unknown_color: str = UNKNOWN_COLOR) -> dict[str, str]:
    """edge_id → colour (traced feeders win over raw GIS hints).

    First claim wins — traces arrive sorted by feeder key, so the
    alphabetically-first feeder keeps the edge when several feeders'
    normal-state traces overlap (the A-09 flood-through), matching the
    global zone_of_edge rule in `topology.zones`.
    """
    edge_feeder: dict[str, str] = {}
    for t in getattr(graph, "_traces", []):
        for eid in t.edges:
            edge_feeder.setdefault(eid, t.feeder_key)
    out = {}
    for eid, e in graph.edges.items():
        k = edge_feeder.get(eid) or (e.feeder_hint.split(" ")[0]
                                     if e.feeder_hint else "")
        out[eid] = palette.get(k, unknown_color)
    return out


_SWITCH_CODE_LABELS = {
    "FCT": "FCT — فیوز کات‌اوت",
    "DCS": "DCS — دیسکانکتور/سکسیونر",
    "CBR": "CBR — دژنکتور/مدارشکن",
    "REC": "REC — ریکلوزر",
    "SEC": "SEC — سکشنالایزر",
    "UNK": "کلید با نوع نامشخص",
}


def switch_display_code(sw) -> str:
    """Resolve the actual GIS device subtype, preferring explicit raw code."""
    from ..domain.enums import SwitchFamily
    raw = str(getattr(sw, "switch_type_raw", "") or "").upper()
    compact = re.sub(r"[^A-Z0-9\u0600-\u06FF]+", "", raw)
    aliases = (("FCT", ("FCT", "فیوز", "کات اوت", "کاتاوت")),
               ("DCS", ("DCS", "دیسکانکتور", "سکسیونر")),
               ("CBR", ("CBR", "دژنکتور", "مدارشکن", "بریکر")),
               ("REC", ("REC", "ریکلوزر")),
               ("SEC", ("SEC", "سکشنالایزر", "سکشنالایزر")))
    for code, words in aliases:
        if any(re.sub(r"\s+", "", w).upper() in compact for w in words):
            return code
    return {SwitchFamily.FUSE_CUTOUT: "FCT",
            SwitchFamily.DISCONNECTOR: "DCS",
            SwitchFamily.BREAKER: "CBR",
            SwitchFamily.RECLOSER: "REC",
            SwitchFamily.SECTIONALIZER: "SEC"}.get(sw.family, "UNK")


class NetworkMapRenderer:
    """Feeder/zone map of the whole network or a single feeder."""

    def __init__(self, graph: NetworkGraph, traces: list[FeederTrace] | None = None,
                 zones: ZoneResult | None = None,
                 switches: dict | None = None,
                 tie_switch_ids: set[str] | None = None,
                 style: MapStyle | None = None):
        self.graph = graph
        self.traces = traces or []
        graph._traces = self.traces               # for edge_color_of
        self.zones = zones
        self.switches = switches or {}
        self.tie_switch_ids = tie_switch_ids or set()
        #: تنظیمات نمایشی (رنگ/ضخامت/مارکر) — None = پیش‌فرض (درخواست کاربر)
        self.style = style or MapStyle()
        self._rotate = False
        #: device categories actually drawn in the last render — the
        #: legend is built from it so it is complete AND accurate
        self._drawn: set[str] = set()

    # ------------------------------------------------------------------
    def render(self, path: str, title: str = "",
               feeder_filter=None,
               show_devices: bool = True, figsize=(14, 12),
               dpi: int = 150, zone_labels: bool | None = None,
               proposed_nodes=None, rotate: bool | None = None,
               manual_nodes=None, highlight_point=None,
               zone_load_kw: dict | None = None, selected_zone: str | None = None,
               hidden_switch_ids=None, zone_up_mwh: dict | None = None,
               zone_outage_hours: dict | None = None) -> str:
        """Render to a PNG file (headless Agg) and return the path."""
        fig = plt.figure(figsize=figsize, constrained_layout=True)
        try:
            self.render_into(fig, title=title, feeder_filter=feeder_filter,
                             show_devices=show_devices,
                             zone_labels=zone_labels,
                             proposed_nodes=proposed_nodes, rotate=rotate,
                             manual_nodes=manual_nodes,
                             highlight_point=highlight_point,
                             zone_load_kw=zone_load_kw,
                             selected_zone=selected_zone,
                             hidden_switch_ids=hidden_switch_ids,
                             zone_up_mwh=zone_up_mwh,
                             zone_outage_hours=zone_outage_hours)
            fig.savefig(path, dpi=dpi)
        finally:
            plt.close(fig)
        return path

    @staticmethod
    def network_is_portrait(graph: NetworkGraph) -> bool:
        """True وقتی محدوده شبکه بلندتر از پهناست (فقط اطلاعاتی).

        حذف چرخش ۹۰ درجه (بازخورد کاربر): منظور از landscape استفاده
        از «تمام فضای» قاب نقشه بود، نه چرخش تصویر — قاب با aspect
        خودکار (auto) پر می‌شود و هندسه جغرافیایی دست‌نخورده می‌ماند."""
        xs, ys = [], []
        for nd in graph.nodes.values():
            if nd.coord is not None:
                xs.append(nd.coord[0])
                ys.append(nd.coord[1])
        if len(xs) < 2:
            return False
        return (max(ys) - min(ys)) > (max(xs) - min(xs))

    def render_into(self, fig, title: str = "",
                    feeder_filter=None,
                    show_devices: bool = True,
                    zone_labels: bool | None = None,
                    proposed_nodes=None,
                    rotate: bool | None = None,
                    manual_nodes=None,
                    style: MapStyle | None = None,
                    highlight_point=None,
                    zone_load_kw: dict | None = None,
                    selected_zone: str | None = None,
                    hidden_switch_ids=None, zone_up_mwh: dict | None = None,
                    zone_outage_hours: dict | None = None,
                    manual_tie_pairs=None, zone_label_positions=None) -> None:
        """Draw onto an existing Matplotlib figure (Qt canvas shares this).

        ``proposed_nodes``: node ids of Phase-4 proposed switch locations
        (drawn as green stars so the placement output is visible on the
        very same rendering path — one rendering path, D-04).

        ``manual_nodes``: node ids of MANUALLY placed / evaluated switches
        (جایابی دستی — درخواست کاربر: «وقتی نقطه‌ای روی مپ پیک می‌شود و
        ارزیابی می‌شود روی نقشه نیز نمایش داده شود») — blue plus markers.

        ``style``: MapStyle override for THIS render (falls back to
        ``self.style``).

        ``rotate``: منسوخ — چرخش ۹۰° حذف شد (بازخورد کاربر: منظور از
        landscape پر شدن «تمام فضای قاب» بود، نه چرخش تصویر). برای
        سازگاری پارامتر پذیرفته می‌شود ولی همیشه نادیده گرفته می‌شود."""
        rotate = False                     # rotation removed (user feedback)
        self._rotate = False
        st = self.style = (style or self.style or MapStyle())
        self._drawn = set()                # legend = what is actually drawn
        palette = feeder_palette(self.traces, st)
        edge_colors = edge_color_of(self.graph, palette, st.unknown_color)

        ax = fig.subplots(1, 1) if hasattr(fig, "subplots") else None
        if ax is None:
            ax = fig.add_subplot(111)
        segs, colors, widths = [], [], []
        for eid, e in self.graph.edges.items():
            a = self._c(self.graph.nodes[e.a].coord)
            b = self._c(self.graph.nodes[e.b].coord)
            if a is None or b is None:
                continue
            if feeder_filter is not None and not any(
                    self._edge_in_feeder(eid, fk) for fk in
                    (feeder_filter if isinstance(feeder_filter, (set, frozenset, list, tuple)) else [feeder_filter])):
                continue
            segs.append((a, b))
            colors.append(edge_colors.get(eid, st.unknown_color))
            widths.append(st.feeder_width_filtered if feeder_filter
                          else st.feeder_width)
        if segs:
            ax.add_collection(LineCollection(
                segs, colors=colors, linewidths=widths, alpha=0.92,
                capstyle="round", zorder=1))

        if show_devices:
            self._draw_devices(ax, feeder_filter,
                               hidden_switch_ids=set(hidden_switch_ids or ()))

        # Highlight the complete selected zone on top of feeder lines. A
        # zone is a set of network edges, not a polygon; use the exact GIS
        # geometry as the highlight rather than inventing a filled boundary.
        if selected_zone and self.zones is not None:
            zsel = self.zones.zone_by_id(selected_zone)
            if zsel is not None and _feeder_selected(zsel.feeder, feeder_filter):
                hl = []
                for eid in sorted(zsel.edges):
                    e = self.graph.edges.get(eid)
                    if e is None:
                        continue
                    ca = self._c(self.graph.nodes[e.a].coord)
                    cb = self._c(self.graph.nodes[e.b].coord)
                    if ca is not None and cb is not None:
                        hl.append((ca, cb))
                if hl:
                    ax.add_collection(LineCollection(
                        hl, colors=st.zone_selected_color,
                        linewidths=st.zone_selected_width,
                        alpha=st.zone_selected_alpha,
                        capstyle="round", zorder=4))
                    self._drawn.add("selected_zone")

        if (st.show_zone_labels if zone_labels is None else zone_labels) and self.zones is not None:
            for z in self.zones.zones:
                if not _feeder_selected(z.feeder, feeder_filter):
                    continue
                pts = set()
                for eid in z.edges:
                    e = self.graph.edges[eid]
                    ca = self._c(self.graph.nodes[e.a].coord)
                    cb = self._c(self.graph.nodes[e.b].coord)
                    if ca is not None:
                        pts.add((float(ca[0]), float(ca[1])))
                    if cb is not None:
                        pts.add((float(cb[0]), float(cb[1])))
                if pts:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    load = (zone_load_kw or {}).get(z.id)
                    load_txt = f"\nبار: {float(load):,.0f} kW" if load is not None else "\nبار: —"
                    up = (zone_up_mwh or {}).get(z.id)
                    up_txt = f"\nU×P: {float(up):,.3f} MWh/سال" if up is not None else "\nU×P: نامشخص"
                    outage_h = (zone_outage_hours or {}).get(z.id)
                    time_txt = f"\nخاموشی: {float(outage_h):,.2f} ساعت/سال" if outage_h is not None else "\nخاموشی: نامشخص"
                    label = f"{z.feeder or 'ISLAND'} / Z{z.zone_no}{load_txt}{time_txt}{up_txt}"
                    anchor = (sum(xs) / len(xs), sum(ys) / len(ys))
                    position = (zone_label_positions or {}).get(z.id, anchor)
                    artist = ax.annotate(
                        label, xy=anchor, xytext=position, textcoords="data",
                        fontsize=st.zone_label_size, color=st.zone_label_color,
                        alpha=st.zone_label_alpha, ha="center", va="center",
                        zorder=9, picker=5,
                        bbox=dict(boxstyle="round,pad=0.30",
                                  facecolor=st.zone_label_background_color,
                                  edgecolor=st.zone_selected_color
                                  if z.id == selected_zone else "#616161",
                                  linewidth=1.5 if z.id == selected_zone else 0.65,
                                  alpha=st.zone_label_background_alpha),
                        arrowprops=dict(arrowstyle="-", color=st.zone_selected_color
                                        if z.id == selected_zone else "#616161",
                                        lw=0.9, shrinkA=4, shrinkB=3,
                                        connectionstyle="angle3,angleA=0,angleB=90"))
                    artist.set_gid(f"zone:{z.id}")
                    # MapCanvasMixin owns annotation drag and persistence.
                    self._drawn.add("zone_labels")

        if proposed_nodes:
            px, py = [], []
            for n in sorted(proposed_nodes):
                nd = self.graph.nodes.get(n)
                if nd is not None and nd.coord is not None:
                    c = self._c(nd.coord)
                    px.append(c[0])
                    py.append(c[1])
            if px:
                ax.scatter(px, py, s=st.proposed_size, marker=st.proposed_marker,
                           facecolors=st.proposed_color,
                           edgecolors=st.proposed_color,
                           linewidths=0.6, zorder=7,
                           label="Proposed new switch (Phase 4)")

        if manual_nodes:
            mx, my = [], []
            for n in sorted(set(manual_nodes)):
                nd = self.graph.nodes.get(n)
                if nd is not None and nd.coord is not None:
                    c = self._c(nd.coord)
                    mx.append(c[0])
                    my.append(c[1])
            if mx:
                self._drawn.add("manual")
                ax.scatter(mx, my, s=st.manual_size, marker=st.manual_marker,
                           facecolors=st.manual_color, edgecolors="white",
                           linewidths=0.7, zorder=8,
                           label="Manual switch (evaluated)")

        if manual_tie_pairs:
            tie_segments = []
            for na, nb in manual_tie_pairs:
                a = self.graph.nodes.get(na); b = self.graph.nodes.get(nb)
                if a is None or b is None or a.coord is None or b.coord is None:
                    continue
                tie_segments.append((self._c(a.coord), self._c(b.coord)))
            if tie_segments:
                ax.add_collection(LineCollection(
                    tie_segments, colors="#d81b60", linewidths=2.0,
                    linestyles="dashed", zorder=6, label="Manual inter-feeder tie"))
                self._drawn.add("manual_tie")

        if highlight_point is not None:
            hx, hy = map(float, highlight_point)
            self._drawn.add("coordinate")
            ax.scatter([hx], [hy], s=150, marker="X", color="#ff00aa",
                       edgecolors="white", linewidths=1.2, zorder=20,
                       label="Entered UTM coordinate")

        ax.autoscale(enable=True)
        ax.set_aspect("equal")
        ax.set_axis_off()
        ax.set_title(title or "SwitchLoc — Network Map", fontsize=12,
                     loc="left")
        if st.show_legend:
            ax.legend(handles=self._legend_handles(palette, feeder_filter,
                                                   proposed=bool(proposed_nodes),
                                                   manual=bool(manual_nodes)),
                      loc="lower left", fontsize=7, framealpha=0.85)
        else:
            leg = ax.get_legend()
            if leg is not None:
                leg.remove()

    # ------------------------------------------------------------------
    def _c(self, coord):
        """Coordinate accessor — همه‌ی المان‌های ترسیم‌شده از اینجا رد
        می‌شوند. چرخش ۹۰° حذف شده است؛ مختصات پروژه عیناً استفاده
        می‌شود (قاب با aspect=auto کل فضا را پر می‌کند)."""
        return coord

    # ------------------------------------------------------------------
    def _edge_in_feeder(self, eid: str, feeder_key: str) -> bool:
        for t in self.traces:
            if t.feeder_key == feeder_key and eid in t.edges:
                return True
        return False

    def _draw_devices(self, ax, feeder_filter,
                      hidden_switch_ids: set[str] | None = None) -> None:
        st = self.style
        hidden_switch_ids = set(hidden_switch_ids or ())
        pts_src, pts_tf = [], []
        by_code: dict[tuple[str, bool], list[tuple[float, float]]] = {}
        open_x, open_y = [], []
        for node, sids in sorted(self.graph.switch_ids_at.items()):
            gn = self.graph.nodes.get(node)
            coord = self._c(gn.coord if gn is not None else None)
            if coord is None:
                continue
            if feeder_filter is not None and not any(self._node_in_feeder(node, fk) for fk in
                    (feeder_filter if isinstance(feeder_filter, (set, frozenset, list, tuple)) else [feeder_filter])):
                continue
            visible_sids = [sid for sid in sorted(sids)
                            if sid not in hidden_switch_ids]
            for idx, sid in enumerate(visible_sids):
                sw = self.switches.get(sid)
                if sw is None:
                    continue
                code = switch_display_code(sw)
                is_open = ((sw.normally_state or "").strip().upper() == "NO"
                           or sw.current_state == SwitchState.OUT_OF_SERVICE
                           or sid in self.tie_switch_ids)
                # tiny deterministic offsets keep co-located unlike devices visible
                dx = (idx - (len(visible_sids)-1)/2.0) * 1.8
                pt = (coord[0] + dx, coord[1] + dx)
                by_code.setdefault((code, is_open), []).append(pt)
                if is_open:
                    open_x.append(pt[0]); open_y.append(pt[1])
        for nid, nd in sorted(self.graph.nodes.items()):
            if nd.coord is None:
                continue
            if feeder_filter is not None and not any(self._node_in_feeder(nid, fk) for fk in
                    (feeder_filter if isinstance(feeder_filter, (set, frozenset, list, tuple)) else [feeder_filter])):
                continue
            c = self._c(nd.coord)
            if nd.kind == NodeKind.SOURCE:
                pts_src.append(c)
            elif self.graph.transformer_ids_at.get(nid):
                pts_tf.append(c)

        terminal_x, terminal_y = [], []
        for (code, is_open), pts in sorted(by_code.items()):
            color = getattr(st, f"{code.lower()}_color", st.switch_color)
            size = getattr(st, f"{code.lower()}_size", st.switch_size)
            marker = getattr(st, f"{code.lower()}_marker", st.switch_marker)
            key = f"device_{code}"
            self._drawn.add(key)
            ax.scatter([p[0] for p in pts], [p[1] for p in pts],
                       s=size, marker=marker,
                       facecolors="none" if is_open else "white",
                       edgecolors=color, linewidths=1.0, zorder=5,
                       label=_SWITCH_CODE_LABELS.get(code, code))
        for node, sids in self.graph.switch_ids_at.items():
            if not any(sid not in hidden_switch_ids for sid in sids):
                continue
            if not self.graph.transformer_ids_at.get(node):
                continue
            gn = self.graph.nodes.get(node)
            if gn is None or gn.coord is None:
                continue
            if feeder_filter is not None and not any(self._node_in_feeder(node, fk) for fk in
                    (feeder_filter if isinstance(feeder_filter, (set, frozenset, list, tuple)) else [feeder_filter])):
                continue
            terminal_x.append(gn.coord[0]); terminal_y.append(gn.coord[1])
        if terminal_x:
            self._drawn.add("transformer_terminal_device")
            ax.scatter(terminal_x, terminal_y, s=42, marker="o",
                       facecolors="none", edgecolors="#616161",
                       linewidths=1.0, zorder=6,
                       label="Transformer-terminal device (not a feeder zone cut)")
        if open_x:
            self._drawn.add("no_tie")
            ax.scatter(open_x, open_y, s=st.no_tie_size, marker=st.no_tie_marker,
                       facecolors="none", edgecolors=st.no_tie_color,
                       linewidths=0.8, zorder=6,
                       label="Open / NO / Tie state")
        if pts_src:
            self._drawn.add("source")
            ax.scatter([p[0] for p in pts_src], [p[1] for p in pts_src],
                       s=st.source_size, marker=st.source_marker,
                       color=st.source_color, zorder=7,
                       label="Source (feeder head)")
        if pts_tf:
            self._drawn.add("transformer")
            ax.scatter([p[0] for p in pts_tf], [p[1] for p in pts_tf],
                       s=st.transformer_size, marker=st.transformer_marker,
                       color=st.transformer_color, alpha=0.7, zorder=2,
                       label="MV/LV transformer")

    def _node_in_feeder(self, node: str, feeder_key: str) -> bool:
        for t in self.traces:
            if t.feeder_key == feeder_key and node in t.nodes:
                return True
        return False

    def _legend_handles(self, palette: dict[str, str],
                        feeder_filter,
                        proposed: bool = False,
                        manual: bool = False) -> list[Line2D]:
        """لجند کامل: رنگ فیدرها + «همه‌ی نمادهای داخل نقشه» (بازخورد
        کاربر — مربع، دایره، لوزی، نقطه، ستاره). فقط دسته‌هایی که واقعا
        در همین رندر ترسیم شده‌اند می‌آیند تا لجند دقیق بماند."""
        st = self.style
        handles = []
        items = palette.items() if feeder_filter is None else \
            [(k, c) for k, c in palette.items() if _feeder_selected(k, feeder_filter)]
        for k, c in sorted(items):
            handles.append(Line2D([], [], color=c, lw=2, label=f"Feeder {k}"))
        handles.append(Line2D([], [], color=st.unknown_color, lw=1.2,
                              label="Untraced / no label"))
        drawn = getattr(self, "_drawn", set())
        if "transformer" in drawn:
            handles.append(Line2D([], [], color=st.transformer_color,
                                  marker=st.transformer_marker,
                                  linestyle="None", markersize=6,
                                  label="MV/LV transformer"))
        for code in ("FCT", "DCS", "CBR", "REC", "SEC", "UNK"):
            if f"device_{code}" in drawn:
                color = getattr(st, f"{code.lower()}_color", st.switch_color)
                marker = getattr(st, f"{code.lower()}_marker", st.switch_marker)
                handles.append(Line2D([], [], color=color, marker=marker,
                                      linestyle="None", markersize=7,
                                      markerfacecolor="white",
                                      label=_SWITCH_CODE_LABELS[code]))
        if "selected_zone" in drawn:
            handles.append(Line2D([], [], color=st.zone_selected_color,
                                  lw=max(1.5, st.zone_selected_width),
                                  alpha=st.zone_selected_alpha,
                                  label="Selected zone"))
        if "zone_labels" in drawn:
            handles.append(Line2D([], [], color=st.zone_label_color,
                                  marker="o", linestyle="None", markersize=4,
                                  label="Zone label (click for details)"))
        if "no_tie" in drawn:
            handles.append(Line2D([], [], color=st.no_tie_color,
                                  marker=st.no_tie_marker,
                                  linestyle="None", markersize=7,
                                  markerfacecolor="none",
                                  label="Open point / NO / Tie"))
        if "source" in drawn:
            handles.append(Line2D([], [], color=st.source_color,
                                  marker=st.source_marker,
                                  linestyle="None", markersize=8,
                                  label="Source (feeder head)"))
        if proposed:
            handles.append(Line2D([], [], color=st.proposed_color,
                                  marker=st.proposed_marker,
                                  linestyle="None", markersize=11,
                                  label="Proposed new switch (Phase 4)"))
        if "transformer_terminal_device" in drawn:
            handles.append(Line2D([], [], color="#616161", marker="o",
                                  markerfacecolor="none", linestyle="None",
                                  markersize=8,
                                  label="Transformer-terminal device (not a feeder zone cut)"))
        if "coordinate" in drawn:
            handles.append(Line2D([], [], color="#ff00aa", marker="X",
                                  linestyle="None", markersize=9,
                                  label="Entered UTM coordinate"))
        if manual:
            handles.append(Line2D([], [], color=st.manual_color,
                                  marker=st.manual_marker,
                                  linestyle="None", markersize=10,
                                  label="Manual switch (evaluated)"))
        return handles
