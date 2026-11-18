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
    """آیا این فیدر در انتخاب فعلی است؟ (نگارش کوتاه/آراسته یکی است)

    انتخاب ممکن است از نسخه‌های قبل با کلید کوتاه («F1») ذخیره شده باشد؛
    مقایسهٔ دقیق آن را رد می‌کرد و نقشه هیچ فیدری نشان نمی‌داد.
    """
    from ..topology.tracing import same_feeder
    if selection is None:
        return True
    if isinstance(selection, (set, frozenset, list, tuple)):
        return any(same_feeder(feeder or "", str(k)) for k in selection)
    return same_feeder(feeder or "", str(selection))


def _palette_key_for_label(label: str, palette: dict[str, str]) -> str | None:
    """Resolve a GIS feeder label to one unambiguous palette key.

    GIS exports sometimes omit separators (``F8SOUTH`` vs ``F8 - SOUTH``).
    Match those spelling variants only when the compact label is unique; do
    not collapse distinct full feeder names that merely share a number.
    """
    label = str(label or "").strip()
    if not label:
        return None
    if label in palette:
        return label
    from ..topology.tracing import feeder_id, same_feeder
    matches = [key for key in palette if feeder_id(key) == feeder_id(label)]
    if not matches:
        matches = [key for key in palette if same_feeder(key, label)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        return None
    compact = re.sub(r"[^A-Z0-9\u0600-\u06ff]+", "", label.upper())
    compact_matches = [key for key in palette
                       if re.sub(r"[^A-Z0-9\u0600-\u06ff]+", "", key.upper())
                       == compact]
    return compact_matches[0] if len(compact_matches) == 1 else None


def feeder_palette(traces: list[FeederTrace],
                   style: MapStyle | None = None,
                   feeder_hints=None) -> dict[str, str]:
    """feeder → colour for traced feeders and explicit GIS line labels.

    Some GIS projects have incomplete source points, so tracing can fall
    back to one overlapping whole-network trace. Include branch feeder
    labels in the map palette so that this fallback cannot paint every
    conductor with the same feeder colour. Existing two-argument callers
    remain compatible.
    """
    keys = {t.feeder_key for t in traces if t.feeder_key}
    for hint in feeder_hints or ():
        hint = str(hint or "").strip()
        if hint and _palette_key_for_label(hint, {key: "" for key in keys}) is None:
            keys.add(hint)
    keys = sorted(keys)
    if style is not None:
        return style.palette_of(feeders=keys)
    from .map_style import auto_palette
    return auto_palette(feeders=keys)


def edge_color_of(graph: NetworkGraph, palette: dict[str, str],
                  unknown_color: str = UNKNOWN_COLOR) -> dict[str, str]:
    """edge_id → colour, preferring an explicit line feeder label.

    The GIS ``feeder_hint`` is the per-line attribution when topology
    tracing has ambiguous/flood-through overlaps (for example, incomplete
    feeder-head points). Use the traced feeder as a fallback for unlabeled
    lines; this changes visualization only, not topology analysis.
    """
    edge_feeder: dict[str, str] = {}
    for t in getattr(graph, "_traces", []):
        for eid in t.edges:
            edge_feeder.setdefault(eid, t.feeder_key)
    out = {}
    for eid, e in graph.edges.items():
        k = (_palette_key_for_label(e.feeder_hint, palette)
             or edge_feeder.get(eid, ""))
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
    # ELWSEC/ELSEC is the dedicated sectionalizer layer.  Projects imported
    # before the slot alias existed stored these devices as DISCONNECTOR
    # (DCS); the layer name is authoritative for display so legacy DBs
    # render SEC without requiring a re-import.
    layer = str(getattr(sw, "layer", "") or "").strip().upper()
    if layer in ("ELWSEC", "ELSEC"):
        return "SEC"
    raw = str(getattr(sw, "switch_type_raw", "") or "").upper()
    compact = re.sub(r"[^A-Z0-9\u0600-\u06FF]+", "", raw)
    aliases = (("FCT", ("FCT", "فیوز", "کات اوت", "کاتاوت")),
               ("SEC", ("SEC", "ELWSEC", "ELSEC", "سکشنالایزر",
                        "سکشنلایزر", "سکشنالیزر", "سكشنالایزر",
                        "سكشنلایزر")),
               ("DCS", ("DCS", "دیسکانکتور", "سکسیونر",
                        "سکسيونر", "سكسيونر")),
               ("CBR", ("CBR", "دژنکتور", "مدارشکن", "بریکر")),
               ("REC", ("REC", "ریکلوزر")))
    for code, words in aliases:
        if any(re.sub(r"\s+", "", w).upper() in compact for w in words):
            return code
    return {SwitchFamily.FUSE_CUTOUT: "FCT",
            SwitchFamily.DISCONNECTOR: "DCS",
            SwitchFamily.BREAKER: "CBR",
            SwitchFamily.RECLOSER: "REC",
            SwitchFamily.SECTIONALIZER: "SEC"}.get(sw.family, "UNK")


# ---- power-flow colour helpers (پخش بار) ------------------------------
def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = str(hex_color or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:  # noqa: BLE001
        return 0, 0, 0


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    r = max(0, min(255, int(round(r))))
    g = max(0, min(255, int(round(g))))
    b = max(0, min(255, int(round(b))))
    return f"#{r:02x}{g:02x}{b:02x}"


def _interpolate_hex(low: str, high: str, t: float) -> str:
    t = max(0.0, min(1.0, float(t)))
    lr, lg, lb = _hex_to_rgb(low)
    hr, hg, hb = _hex_to_rgb(high)
    return _rgb_to_hex(lr + (hr - lr) * t, lg + (hg - lg) * t, lb + (hb - lb) * t)


def _pf_voltage_color(pu: float | None, st) -> str | None:
    if pu is None or not math.isfinite(float(pu)):
        return None
    try:
        lo = float(st.pf_voltage_min_pu)
        hi = float(st.pf_voltage_max_pu)
    except Exception:  # noqa: BLE001
        return None
    if hi <= lo:
        return None
    t = (float(pu) - lo) / (hi - lo)
    return _interpolate_hex(st.pf_voltage_low_color, st.pf_voltage_high_color, t)


def _pf_loading_bucket(pct: float | None, st) -> tuple[str, float]:
    if pct is None or not math.isfinite(float(pct)):
        return st.pf_loading_normal_color, float(st.pf_loading_normal_width)
    p = float(pct)
    try:
        warn = float(st.pf_loading_warn_pct)
        ov = float(st.pf_loading_overload_pct)
    except Exception:  # noqa: BLE001
        warn, ov = 70.0, 100.0
    if p < warn:
        return st.pf_loading_normal_color, float(st.pf_loading_normal_width)
    if p < ov:
        return st.pf_loading_warn_color, float(st.pf_loading_warn_width)
    return st.pf_loading_overload_color, float(st.pf_loading_overload_width)


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
        #: برچسب‌های «نام (تعداد)» لایهٔ خاموشی که پس از نهایی‌شدن محدودهٔ
        #: محورها رسم می‌شوند (تا جداسازی عمودی برچسب‌ها دقیق باشد)
        self._pending_outage_labels: list = []
        #: افسانهٔ توزیع رنگی: [(color, label, edges)]
        self._heat_legend: list = []
        #: افسانهٔ پخش بار
        self._pf_legend: list = []
        #: دادهٔ پخش بار آخرین رندر (برای برچسب‌ها)
        self._pf_voltages: dict = {}
        self._pf_branch_loading: dict = {}

    # ------------------------------------------------------------------
    def render(self, path: str, title: str = "",
               feeder_filter=None,
               show_devices: bool = True, figsize=(14, 12),
               dpi: int = 150, zone_labels: bool | None = None,
               proposed_nodes=None, rotate: bool | None = None,
               manual_nodes=None, highlight_point=None,
               zone_load_kw: dict | None = None, selected_zone: str | None = None,
               hidden_switch_ids=None, zone_up_mwh: dict | None = None,
               zone_outage_hours: dict | None = None,
               outage_points=None, sectionalizer_nodes=None,
               hidden_outage_ids=None,
               pf_voltages=None, pf_branch_loading=None,
               pf_transformer_loading=None) -> str:
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
                             zone_outage_hours=zone_outage_hours,
                             outage_points=outage_points,
                             sectionalizer_nodes=sectionalizer_nodes,
                             hidden_outage_ids=hidden_outage_ids,
                             pf_voltages=pf_voltages,
                             pf_branch_loading=pf_branch_loading,
                             pf_transformer_loading=pf_transformer_loading)
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
                    manual_tie_pairs=None, zone_label_positions=None,
                    outage_points=None, sectionalizer_nodes=None,
                    hidden_outage_ids=None,
                    pf_voltages=None, pf_branch_loading=None,
                    pf_transformer_loading=None) -> None:
        """Draw onto an existing Matplotlib figure (Qt canvas shares this).

        ``proposed_nodes``: node ids of Phase-4 proposed switch locations
        (drawn as green stars so the placement output is visible on the
        very same rendering path — one rendering path, D-04).

        ``manual_nodes``: node ids of MANUALLY placed / evaluated switches
        (جایابی دستی — درخواست کاربر: «وقتی نقطه‌ای روی مپ پیک می‌شود و
        ارزیابی می‌شود روی نقشه نیز نمایش داده شود») — blue plus markers.

        ``style``: MapStyle override for THIS render (falls back to
        ``self.style``).

        ``outage_points``: رخدادهای خاموشیِ دارای مختصات در CRS پروژه —
        هر آیتم ``{"id", "x", "y", "label", "status", "feeder",
        "zone_x", "zone_y", "zone_label"}``. نمایش با رنگ وضعیت و
        (اختیاری) خط اتصال به مرکز زونِ متأثر؛ همهٔ پارامترهای نمایشی از
        ``MapStyle`` می‌آیند تا در تب «خاموشی‌ها» قابل تنظیم باشند.

        ``sectionalizer_nodes``: گره‌های پیشنهادی موتور بهینه‌سازی
        سکشنالایزر (نماد × بنفش، قابل خاموش‌کردن با
        ``style.show_opt_sectionalizers``).

        ``rotate``: منسوخ — چرخش ۹۰° حذف شد (بازخورد کاربر: منظور از
        landscape پر شدن «تمام فضای قاب» بود، نه چرخش تصویر). برای
        سازگاری پارامتر پذیرفته می‌شود ولی همیشه نادیده گرفته می‌شود."""
        rotate = False                     # rotation removed (user feedback)
        self._rotate = False
        st = self.style = (style or self.style or MapStyle())
        self._drawn = set()                # legend = what is actually drawn
        palette = feeder_palette(
            self.traces, st,
            feeder_hints=(edge.feeder_hint for edge in self.graph.edges.values()))
        edge_colors = edge_color_of(self.graph, palette, st.unknown_color)

        # ---- power-flow state -----------------------------------------
        self._pf_legend = []
        self._pf_voltages = {str(k): float(v) for k, v in (pf_voltages or {}).items()
                             if v is not None}
        self._pf_branch_loading = {str(k): float(v) for k, v in (pf_branch_loading or {}).items()
                                   if v is not None}
        self._pf_transformer_loading = {str(k): float(v) for k, v in (pf_transformer_loading or {}).items()
                                        if v is not None}
        pf_has_data = bool(self._pf_voltages or self._pf_branch_loading)
        pf_active = bool(getattr(st, "pf_enabled", False) and pf_has_data)
        pf_alpha = float(getattr(st, "pf_opacity", 0.88)) if pf_active else 0.92
        # fallback widths when pf not active
        _base_w = st.feeder_width_filtered if feeder_filter else st.feeder_width

        ax = fig.subplots(1, 1) if hasattr(fig, "subplots") else None
        if ax is None:
            ax = fig.add_subplot(111)
        segs, colors, widths = [], [], []
        # Resolve the feeder selection once, not for every edge × feeder × trace.
        selected_edges = None
        if feeder_filter is not None:
            selected_edges = set()
            for trace in self.traces:
                if _feeder_selected(trace.feeder_key, feeder_filter):
                    selected_edges.update(trace.edges)
        pf_voltage_min = float(getattr(st, "pf_voltage_min_pu", 0.95) or 0.95)
        pf_voltage_max = float(getattr(st, "pf_voltage_max_pu", 1.0) or 1.0)
        pf_mode = str(getattr(st, "pf_mode", "voltage") or "voltage")
        for eid, e in self.graph.edges.items():
            a = self._c(self.graph.nodes[e.a].coord)
            b = self._c(self.graph.nodes[e.b].coord)
            if a is None or b is None:
                continue
            if selected_edges is not None and eid not in selected_edges:
                continue
            segs.append((a, b))
            if pf_active:
                col = None
                w = _base_w
                # voltage-based colour
                if pf_mode in ("voltage", "combined"):
                    pu_a = self._pf_voltages.get(str(e.a))
                    pu_b = self._pf_voltages.get(str(e.b))
                    pu = None
                    if pu_a is not None and pu_b is not None:
                        pu = min(float(pu_a), float(pu_b))
                    elif pu_a is not None:
                        pu = float(pu_a)
                    elif pu_b is not None:
                        pu = float(pu_b)
                    vc = _pf_voltage_color(pu, st)
                    if vc is not None:
                        col = vc
                # loading-based appearance
                if pf_mode == "loading":
                    pct = self._pf_branch_loading.get(str(eid))
                    # also try branch_id fallback (edge.branch_id == eid in many cases)
                    if pct is None:
                        pct = self._pf_branch_loading.get(str(getattr(e, "branch_id", "")))
                    lc, lw = _pf_loading_bucket(pct, st)
                    if pct is not None:
                        col = lc
                        w = lw
                    elif col is None:
                        col = edge_colors.get(eid, st.unknown_color)
                elif pf_mode == "combined":
                    pct = self._pf_branch_loading.get(str(eid))
                    if pct is None:
                        pct = self._pf_branch_loading.get(str(getattr(e, "branch_id", "")))
                    _lc, lw = _pf_loading_bucket(pct, st)
                    if pct is not None:
                        w = lw
                    if col is None:
                        # no voltage available → fall back to loading colour
                        if pct is not None:
                            col = _lc
                        else:
                            col = edge_colors.get(eid, st.unknown_color)
                else:  # voltage only, width stays base
                    if col is None:
                        col = edge_colors.get(eid, st.unknown_color)
                colors.append(col or edge_colors.get(eid, st.unknown_color))
                widths.append(float(w))
            else:
                colors.append(edge_colors.get(eid, st.unknown_color))
                widths.append(_base_w)
        if segs:
            ax.add_collection(LineCollection(
                segs, colors=colors, linewidths=widths, alpha=pf_alpha,
                capstyle="round", zorder=1))
        # pf legend buckets (for loading mode we show three buckets, for
        # voltage we show gradient endpoints)
        if pf_active:
            self._drawn.add("powerflow")
            if pf_mode in ("loading", "combined"):
                # count per bucket for legend
                buckets = {"normal": 0, "warn": 0, "overload": 0}
                for eid, e in self.graph.edges.items():
                    if selected_edges is not None and eid not in selected_edges:
                        continue
                    pct = self._pf_branch_loading.get(str(eid))
                    if pct is None:
                        pct = self._pf_branch_loading.get(str(getattr(e, "branch_id", "")))
                    if pct is None:
                        continue
                    warn = float(getattr(st, "pf_loading_warn_pct", 70.0))
                    ov = float(getattr(st, "pf_loading_overload_pct", 100.0))
                    if pct < warn:
                        buckets["normal"] += 1
                    elif pct < ov:
                        buckets["warn"] += 1
                    else:
                        buckets["overload"] += 1
                self._pf_legend = [
                    (st.pf_loading_normal_color, f"بار خط < {warn:g}٪", buckets["normal"]),
                    (st.pf_loading_warn_color, f"بار خط {warn:g}–{ov:g}٪", buckets["warn"]),
                    (st.pf_loading_overload_color, f"بار خط ≥ {ov:g}٪", buckets["overload"]),
                ]
            else:
                self._pf_legend = [
                    (st.pf_voltage_low_color, f"Vmin ≤ {pf_voltage_min:g} pu", None),
                    (st.pf_voltage_high_color, f"Vmax ≥ {pf_voltage_max:g} pu", None),
                ]
            # optional voltage/loading labels at edge midpoints (sparse for large networks)
            if getattr(st, "pf_show_labels", False) and segs:
                max_labels = 120
                step = max(1, len(segs) // max_labels + 1) if len(segs) > max_labels else 1
                eids_ordered = [eid for eid, e in self.graph.edges.items()
                                if self.graph.nodes[e.a].coord is not None and self.graph.nodes[e.b].coord is not None
                                and (selected_edges is None or eid in selected_edges)]
                for idx, eid in enumerate(eids_ordered):
                    if idx % step != 0:
                        continue
                    e = self.graph.edges[eid]
                    a = self._c(self.graph.nodes[e.a].coord)
                    b = self._c(self.graph.nodes[e.b].coord)
                    if a is None or b is None:
                        continue
                    mx = (a[0] + b[0]) / 2.0
                    my = (a[1] + b[1]) / 2.0
                    label = None
                    if pf_mode == "loading":
                        pct = self._pf_branch_loading.get(str(eid))
                        if pct is None:
                            pct = self._pf_branch_loading.get(str(getattr(e, "branch_id", "")))
                        if pct is not None:
                            label = f"{pct:.0f}٪"
                    elif pf_mode == "voltage":
                        pu_a = self._pf_voltages.get(str(e.a))
                        pu_b = self._pf_voltages.get(str(e.b))
                        pu = None
                        if pu_a is not None and pu_b is not None:
                            pu = min(float(pu_a), float(pu_b))
                        elif pu_a is not None:
                            pu = float(pu_a)
                        elif pu_b is not None:
                            pu = float(pu_b)
                        if pu is not None:
                            label = f"{pu:.3f} pu"
                    else:  # combined → prefer loading pct, fallback to voltage
                        pct = self._pf_branch_loading.get(str(eid))
                        if pct is None:
                            pct = self._pf_branch_loading.get(str(getattr(e, "branch_id", "")))
                        if pct is not None:
                            label = f"{pct:.0f}٪"
                        else:
                            pu_a = self._pf_voltages.get(str(e.a))
                            pu_b = self._pf_voltages.get(str(e.b))
                            pu = None
                            if pu_a is not None and pu_b is not None:
                                pu = min(float(pu_a), float(pu_b))
                            elif pu_a is not None:
                                pu = float(pu_a)
                            elif pu_b is not None:
                                pu = float(pu_b)
                            if pu is not None:
                                label = f"{pu:.3f} pu"
                    if label:
                        ax.text(mx, my, label, fontsize=float(getattr(st, "pf_label_size", 5.0) or 5.0),
                                color=getattr(st, "pf_voltage_high_color", "#263238") if pf_mode == "voltage" else "#37474f",
                                ha="center", va="center", zorder=9,
                                bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.55))
        elif getattr(st, "pf_enabled", False):
            # enabled but no results yet
            self._drawn.add("powerflow_no_data")
            try:
                ax.text(0.5, 0.018, "پخش بار فعال است اما نتایج موجود نیست — ابتدا پخش بار/Level-2 را اجرا کنید",
                        transform=ax.transAxes, ha="center", va="bottom", fontsize=7, color="#b71c1c",
                        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#ef9a9a", alpha=0.85), zorder=30)
            except Exception:  # noqa: BLE001
                pass

        if show_devices:
            # None = «تصمیم پیش‌فرض رندرر» (فیوزها پنهان)؛ مجموعهٔ صریح
            # (حتی خالی) یعنی انتخاب کاربر/نقشهٔ تعاملی مقدم است.
            self._draw_devices(ax, feeder_filter,
                               hidden_switch_ids=(None if hidden_switch_ids is None
                                                  else set(hidden_switch_ids)))
        # ---- transformer loading overlay (pf) -------------------------
        if pf_active and self._pf_transformer_loading:
            _tf_pts = {"normal": [], "warn": [], "overload": []}
            for nid, nd in self.graph.nodes.items():
                if nd.coord is None:
                    continue
                if not self.graph.transformer_ids_at.get(nid):
                    continue
                if feeder_filter is not None and not any(self._node_in_feeder(nid, fk) for fk in
                        (feeder_filter if isinstance(feeder_filter, (set, frozenset, list, tuple)) else [feeder_filter])):
                    continue
                pct = self._pf_transformer_loading.get(str(nid))
                if pct is None:
                    continue
                c = self._c(nd.coord)
                warn = float(getattr(st, "pf_loading_warn_pct", 70.0))
                ov = float(getattr(st, "pf_loading_overload_pct", 100.0))
                if pct < warn:
                    _tf_pts["normal"].append(c)
                elif pct < ov:
                    _tf_pts["warn"].append(c)
                else:
                    _tf_pts["overload"].append(c)
            base_t = float(getattr(st, "transformer_size", 3.0) or 3.0)
            scale = float(getattr(st, "pf_transformer_scale", 1.6) or 1.6)
            if _tf_pts["overload"]:
                self._drawn.add("pf_transformer_overload")
                ax.scatter([p[0] for p in _tf_pts["overload"]], [p[1] for p in _tf_pts["overload"]],
                           s=base_t * scale * 4.0, marker=st.transformer_marker,
                           color=st.pf_loading_overload_color, alpha=0.92, zorder=5,
                           label="Transformer overload (pf)")
            if _tf_pts["warn"]:
                self._drawn.add("pf_transformer_warn")
                ax.scatter([p[0] for p in _tf_pts["warn"]], [p[1] for p in _tf_pts["warn"]],
                           s=base_t * scale * 2.4, marker=st.transformer_marker,
                           color=st.pf_loading_warn_color, alpha=0.88, zorder=4,
                           label="Transformer warn (pf)")
            # normal transformers already drawn by _draw_devices; no need to redraw

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

        # --- lایهٔ خاموشی‌های دارای مختصات (درخواست کاربر) --------------
        if outage_points and st.show_outages:
            # فهرست پنهان: پارامتر صریح، وگرنه همان انتخاب ذخیره‌شده در سبک
            # پروژه (تا گزارش‌های headless هم همان چیزی را بدهند که نقشه)
            hidden_out = {str(x) for x in
                          (hidden_outage_ids if hidden_outage_ids is not None
                           else (st.hidden_outage_ids or ()))}
            by_status: dict[str, list] = {}
            links = []
            visible: list[dict] = []
            for pt in outage_points:
                try:
                    pid = str(pt.get("id", ""))
                    if pid and pid in hidden_out:
                        continue
                    fk = str(pt.get("feeder", "") or "")
                    if feeder_filter is not None and fk and not _feeder_selected(
                            fk, feeder_filter):
                        continue
                    x, y = float(pt["x"]), float(pt["y"])
                except (KeyError, TypeError, ValueError):
                    continue
                status = str(pt.get("status", "") or "pending")
                by_status.setdefault(status, []).append((x, y, pt))
                visible.append(pt)
                zx, zy = pt.get("zone_x"), pt.get("zone_y")
                if st.show_outage_links and zx is not None and zy is not None:
                    try:
                        links.append(((x, y), (float(zx), float(zy))))
                    except (TypeError, ValueError):
                        pass
            if links:
                ax.add_collection(LineCollection(
                    links, colors=st.outage_link_color,
                    linewidths=st.outage_link_width,
                    alpha=st.outage_link_alpha, linestyles="dashed",
                    zorder=8, label="Outage → zone link"))
                self._drawn.add("outage_link")
            status_color = {
                "confirmed": st.outage_confirmed_color,
                "rejected": st.outage_rejected_color,
                "pending": st.outage_pending_color,
            }
            status_fa = {"confirmed": "تأیید مهندسی",
                         "rejected": "رد رخداد", "pending": "در انتظار بررسی"}
            for status in ("confirmed", "pending", "rejected", ""):
                items = by_status.get(status)
                if not items:
                    continue
                color = status_color.get(status, st.outage_color)
                ax.scatter([p[0] for p in items], [p[1] for p in items],
                           s=st.outage_size, marker=st.outage_marker,
                           facecolors=color, edgecolors="white",
                           linewidths=0.8, alpha=st.outage_alpha, zorder=11,
                           label=f"Outage — {status_fa.get(status, status or 'بدون وضعیت')}")
                self._drawn.add("outage")

            # --- توزیع رنگی مسیر فیدرها بر اساس تکرار خاموشی ------------
            if getattr(st, "outage_heat_enabled", False) and visible:
                try:
                    from ..application.outage_review import (
                        assign_heat_level, outage_heat_counts)
                    heat_points = [p for p in visible if feeder_filter is None
                                   or (p.get("feeder") and _feeder_selected(
                                       str(p["feeder"]), feeder_filter))]
                    counts = outage_heat_counts(
                        heat_points, self.graph,
                        radius_m=float(getattr(st, "outage_heat_radius_m", 300.0)),
                        edge_ids=selected_edges)
                except Exception:                 # noqa: BLE001
                    counts = {}
                seg_by_color: dict[str, list] = {}
                legend_by_color: dict[str, dict] = {}
                for eid, n in counts.items():
                    level = assign_heat_level(
                        n, getattr(st, "outage_heat_levels", []) or [])
                    if level is None:
                        continue
                    edge = self.graph.edges.get(eid)
                    if edge is None:
                        continue
                    a = self.graph.nodes.get(edge.a)
                    bb = self.graph.nodes.get(edge.b)
                    if a is None or bb is None:
                        continue
                    if a.coord is None or bb.coord is None:
                        continue
                    color = str(level.get("color") or "#c62828")
                    seg_by_color.setdefault(color, []).append(
                        (self._c(a.coord), self._c(bb.coord)))
                    legend_by_color.setdefault(color, {
                        "label": str(level.get("label") or ""),
                        "count": 0})
                    legend_by_color[color]["count"] += 1
                self._heat_legend = []
                for color, segments in seg_by_color.items():
                    ax.add_collection(LineCollection(
                        segments, colors=color,
                        linewidths=float(getattr(st, "outage_heat_width", 2.4)),
                        alpha=float(getattr(st, "outage_heat_alpha", 0.95)),
                        zorder=5.5))
                    self._drawn.add("outage_heat")
                for color, meta in legend_by_color.items():
                    self._heat_legend.append(
                        (color, meta["label"], meta["count"]))

            # برچسب‌ها یک‌بار به‌ازای هر مکان («نام (تعداد)») و پس از
            # نهایی‌شدن محدودهٔ محورها رسم می‌شوند تا روی هم نیفتند.
            if st.show_outage_labels and visible:
                from ..application.outage_review import outage_label_groups

                self._pending_outage_labels = outage_label_groups(visible)
            else:
                self._pending_outage_labels = []

        # --- سکشنالایزرهای پیشنهادی موتور EENS -------------------------
        if sectionalizer_nodes and st.show_opt_sectionalizers:
            sx, sy = [], []
            switch_types = set()
            for item in sectionalizer_nodes:
                try:
                    if isinstance(item, dict):
                        x, y = float(item["x"]), float(item["y"])
                        switch_types.add(str(item.get("switch_type") or ""))
                    else:
                        nd = self.graph.nodes.get(item)
                        if nd is None or nd.coord is None:
                            continue
                        x, y = map(float, nd.coord)
                except (KeyError, TypeError, ValueError):
                    continue
                sx.append(x)
                sy.append(y)
            if sx:
                self._drawn.add("opt_sectionalizer")
                names = {"recloser": "recloser", "sectionalizer": "sectionalizer", "disconnector": "disconnector"}
                labels = sorted({names.get(t, "switch") for t in switch_types} or {"switch"})
                self._opt_switch_label = "Proposed " + "/".join(labels) + " (EENS)"
                ax.scatter(sx, sy, s=st.opt_sec_size, marker=st.opt_sec_marker,
                           facecolors="none", edgecolors=st.opt_sec_color,
                           linewidths=1.6, zorder=13,
                           label=self._opt_switch_label)

        if highlight_point is not None:
            hx, hy = map(float, highlight_point)
            self._drawn.add("coordinate")
            ax.scatter([hx], [hy], s=st.coordinate_size, marker=st.coordinate_marker, color=st.coordinate_color,
                       edgecolors="white", linewidths=1.2, zorder=20,
                       label="Entered UTM coordinate")

        ax.autoscale(enable=True)
        ax.set_aspect("equal")
        ax.set_axis_off()
        if self._pending_outage_labels:
            self._draw_outage_labels(ax, st)
            self._pending_outage_labels = []
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
    @staticmethod
    def _data_per_point(ax, fontsize: float = 5.0) -> float:
        """اندازهٔ یک «نقطهٔ تایپوگرافی» بر حسب واحد دادهٔ محور.

        نقشه با ``aspect='equal'`` رسم می‌شود؛ در این حالت مقیاس هر دو
        محور یکی است و مقدار درست، بزرگ‌ترین نسبتِ «واحد داده به نقطه»
        (یعنی محور محدودکننده) است — برآورد محافظه‌کارانه که برچسب‌ها را
        کمی بزرگ‌تر از واقعیت می‌بیند و از هم‌پوشانی جلوگیری می‌کند.
        """
        try:
            (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
            pos = ax.get_position()
            fig_w, fig_h = ax.figure.get_size_inches()
        except Exception:                          # noqa: BLE001
            return 1.0
        scales = []
        if x1 > x0 and pos.width > 0:
            scales.append((x1 - x0) / max(pos.width * fig_w * 72.0, 1.0))
        if y1 > y0 and pos.height > 0:
            scales.append((y1 - y0) / max(pos.height * fig_h * 72.0, 1.0))
        return max(scales) if scales else 1.0

    @staticmethod
    def _label_offset_pt(k: int, step_pt: float) -> float:
        """فاصلهٔ عمودی k-اُم (نقطه) برای برچسب‌های هم‌مکان: 0, +s, −s, +2s…"""
        if k <= 0:
            return 0.0
        sign = 1.0 if k % 2 == 1 else -1.0
        return sign * step_pt * ((k + 1) // 2)

    _LABEL_DIRECTIONS = (
        (1.0, 0.0, "left", "center"),      # راست نقطه
        (1.0, 1.0, "left", "center"),      # راست-بالا
        (1.0, -1.0, "left", "center"),     # راست-پایین
        (-1.0, 0.0, "right", "center"),    # چپ نقطه
        (-1.0, 1.0, "right", "center"),
        (-1.0, -1.0, "right", "center"),
        (0.0, 1.4, "center", "bottom"),    # بالا
        (0.0, -1.4, "center", "top"),      # پایین
    )

    def _draw_outage_labels(self, ax, st) -> None:
        """برچسب خاموشی‌ها را **چسبیده به نقطهٔ خودشان** می‌چیند.

        دو شکست قبلی و راه‌حل واحد:

        * **روی‌هم‌افتادن** — نسخهٔ اول همهٔ برچسب‌ها را در یک ستون عمودی
          می‌گذاشت؛ با چند نقطهٔ نزدیک، متن‌ها هم‌پوشان می‌شدند.
        * **پراکندگی غیرواقعی** (تصویر ارسالی کاربر) — نسخهٔ دوم نردبان
          عمودی بی‌کران (۲۴ پله) داشت و برچسب را صدها متر از نقطه دور
          می‌کرد.

        راه‌حل: برای هر برچسب فقط **۸ جهتِ چسبیده به نقطه** در
        ``outage_label_max_levels`` حلقهٔ کوچک (پیش‌فرض ۳) آزمایش می‌شود؛
        اولین جای بدون هم‌پوشانی انتخاب می‌شود، وگرنه کم‌ترین هم‌پوشانی.
        هر جابه‌جایی (غیر از «راست نقطه») یک **خط راهنمای نازک** به نقطه
        می‌گیرد تا انتساب برچسب به نقطه گم نشود. برچسب‌های پرتکرار اول
        جای می‌گیرند.
        """
        groups = list(self._pending_outage_labels or [])
        if not groups:
            return
        try:
            fontsize = float(st.outage_label_size or 5.0)
        except (TypeError, ValueError):
            fontsize = 5.0
        per_pt = self._data_per_point(ax, fontsize)
        step_pt = max(fontsize * 1.35, 6.0)
        base_pt = float(getattr(st, "outage_label_offset_pt", 4.0))
        rings = max(0, int(getattr(st, "outage_label_max_levels", 3)))
        show_leader = bool(getattr(st, "outage_label_leader", True))
        try:
            leader_alpha = min(0.85, float(st.outage_label_alpha
                                           if st.outage_label_alpha is not None
                                           else 1.0))
        except (TypeError, ValueError):
            leader_alpha = 0.85

        groups = sorted(groups, key=lambda g: -int(g.get("count") or 0))
        placed: list[tuple[float, float, float, float]] = []

        def _overlaps(box) -> int:
            return sum(1 for b in placed
                       if box[0] < b[2] and box[2] > b[0] and
                       box[1] < b[3] and box[3] > b[1])

        for g in groups:
            text = str(g.get("text") or "")
            if not text:
                continue
            try:
                gx, gy = float(g["x"]), float(g["y"])
            except (KeyError, TypeError, ValueError):
                continue
            count = int(g.get("count") or 0)
            text_w = max(0.58 * fontsize * per_pt * len(text), per_pt * 2.0)
            text_h = 1.45 * fontsize * per_pt
            best = None            # (hits, dx_pt, dy_pt, ha, va, box)
            for ring in range(rings + 1):
                radius = base_pt + ring * step_pt
                for ux, uy, ha, va in self._LABEL_DIRECTIONS:
                    dx_pt, dy_pt = ux * radius, uy * radius
                    # کادر برچسب حول نقطهٔ لنگر (با توجه به ha/va)
                    left = gx + dx_pt * per_pt
                    left -= (text_w if ha == "right" else
                             0.0 if ha == "left" else text_w / 2.0)
                    mid_y = gy + dy_pt * per_pt
                    bottom = mid_y - (0.0 if va == "bottom" else
                                      text_h if va == "top" else text_h / 2.0)
                    box = (left, bottom, left + text_w, bottom + text_h)
                    hits = _overlaps(box)
                    if hits == 0:
                        best = (0, dx_pt, dy_pt, ha, va, box)
                        break
                    if best is None or hits < best[0]:
                        best = (hits, dx_pt, dy_pt, ha, va, box)
                if best is not None and best[0] == 0:
                    break
            if best is None:
                continue
            _hits, dx_pt, dy_pt, ha, va, box = best
            placed.append(box)
            displaced = abs(dx_pt) > 0.1 or abs(dy_pt) > 0.1
            arrow = None
            if show_leader and displaced:
                arrow = dict(arrowstyle="-", color=st.outage_label_color,
                             lw=0.45, alpha=leader_alpha,
                             shrinkA=0.5, shrinkB=3.0)
            ax.annotate(
                text, (gx, gy),
                xytext=(dx_pt, dy_pt), textcoords="offset points",
                fontsize=fontsize, color=st.outage_label_color,
                alpha=st.outage_label_alpha, zorder=12,
                ha=ha, va=va,
                bbox=dict(boxstyle="round,pad=0.12", fc="white",
                          ec="none", alpha=0.35 if count else 0.0),
                arrowprops=arrow)

    # ------------------------------------------------------------------
    def _c(self, coord):
        """Coordinate accessor — همه‌ی المان‌های ترسیم‌شده از اینجا رد
        می‌شوند. چرخش ۹۰° حذف شده است؛ مختصات پروژه عیناً استفاده
        می‌شود (قاب با aspect=auto کل فضا را پر می‌کند)."""
        return coord

    # ------------------------------------------------------------------
    def _edge_in_feeder(self, eid: str, feeder_key: str) -> bool:
        from ..topology.tracing import same_feeder
        for t in self.traces:
            if same_feeder(t.feeder_key, feeder_key) and eid in t.edges:
                return True
        return False

    def _draw_devices(self, ax, feeder_filter,
                      hidden_switch_ids: set[str] | None = None) -> None:
        st = self.style
        # فیوز کات‌اوت‌ها به‌صورت پیش‌فرض رسم نمی‌شوند (درخواست کاربر).
        # اگر فراخوان فهرست صریح کلیدهای پنهان را بدهد (نقشهٔ تعاملی)،
        # تصمیم او مقدم است و همین‌جا چیزی حذف نمی‌شود.
        hide_fuses = (not getattr(st, "show_fuse_cutouts", False)
                      and hidden_switch_ids is None)
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
                if hide_fuses and code == "FCT":
                    continue
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
            if nd.kind == NodeKind.SOURCE:
                # SOURCE objects remain distinct from attached trace junctions.
                if _feeder_selected(getattr(nd, "feeder_hint", ""), feeder_filter):
                    pts_src.append(self._c(nd.coord))
                continue
            if feeder_filter is not None and not any(self._node_in_feeder(nid, fk) for fk in
                    (feeder_filter if isinstance(feeder_filter, (set, frozenset, list, tuple)) else [feeder_filter])):
                continue
            c = self._c(nd.coord)
            if self.graph.transformer_ids_at.get(nid):
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
            if hide_fuses:
                # اگر تنها تجهیز این گره فیوز است و فیوزها پنهان‌اند،
                # نشانگر عمومی ترمینال ترانس هم نباید رسم شود.
                visible = [self.switches.get(sid) for sid in sids
                           if sid not in hidden_switch_ids]
                if visible and all(sw is not None and switch_display_code(sw) == "FCT"
                                   for sw in visible):
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
        from ..topology.tracing import same_feeder
        return any(same_feeder(t.feeder_key, feeder_key) and node in t.nodes
                   for t in self.traces)

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
        if "outage" in drawn:
            handles.append(Line2D([], [], color=st.outage_confirmed_color,
                                  marker=st.outage_marker, linestyle="None",
                                  markersize=8, label="Outage — تأیید مهندسی"))
            handles.append(Line2D([], [], color=st.outage_pending_color,
                                  marker=st.outage_marker, linestyle="None",
                                  markersize=8, label="Outage — در انتظار بررسی"))
            handles.append(Line2D([], [], color=st.outage_rejected_color,
                                  marker=st.outage_marker, linestyle="None",
                                  markersize=8, label="Outage — رد رخداد"))
        if "outage_link" in drawn:
            handles.append(Line2D([], [], color=st.outage_link_color,
                                  lw=max(1.0, st.outage_link_width),
                                  linestyle="dashed",
                                  label="Outage → affected zone"))
        for color, label, n_edges in (getattr(self, "_heat_legend", []) or []):
            handles.append(Line2D([], [], color=color,
                                  lw=max(1.5, st.outage_heat_width),
                                  label=f"Outage density — {label} "
                                        f"({n_edges} segments)"))
        if "opt_sectionalizer" in drawn:
            handles.append(Line2D([], [], color=st.opt_sec_color,
                                  marker=st.opt_sec_marker, linestyle="None",
                                  markersize=9, markerfacecolor="none",
                                  label=getattr(self, "_opt_switch_label", "Proposed switch (EENS)")))
        if "coordinate" in drawn:
            handles.append(Line2D([], [], color=st.coordinate_color, marker=st.coordinate_marker,
                                  linestyle="None", markersize=9,
                                  label="Entered UTM coordinate"))
        if manual:
            handles.append(Line2D([], [], color=st.manual_color,
                                  marker=st.manual_marker,
                                  linestyle="None", markersize=10,
                                  label="Manual switch (evaluated)"))
        # ---- power-flow legend (پخش بار) -------------------------------
        if "powerflow" in drawn:
            pf_mode_legend = getattr(st, "pf_mode", "voltage")
            if pf_mode_legend == "voltage":
                handles.append(Line2D([], [], color=st.pf_voltage_low_color, lw=3,
                                      label=f"PF voltage ≤ {float(getattr(st,'pf_voltage_min_pu',0.95)):g} pu (افت)"))
                handles.append(Line2D([], [], color=st.pf_voltage_high_color, lw=3,
                                      label=f"PF voltage ≥ {float(getattr(st,'pf_voltage_max_pu',1.0)):g} pu (نزدیک نامی)"))
                handles.append(Line2D([], [], color="#9e9e9e", lw=0.8, linestyle="dashed",
                                      label="PF: گرادیان ولتاژ بین دو رنگ (خط بر حسب پایین‌ترین ولتاژ دو سر)"))
            else:
                for color, label, count in (getattr(self, "_pf_legend", []) or []):
                    suffix = f" ({count} segments)" if count is not None else ""
                    lw = 3.0 if "≥" in label else 2.0
                    handles.append(Line2D([], [], color=color, lw=lw,
                                          label=f"PF {label}{suffix}"))
                if pf_mode_legend == "combined":
                    handles.append(Line2D([], [], color=st.pf_voltage_low_color, lw=2,
                                          label="PF combined: رنگ = ولتاژ، ضخامت = بار خط"))
            if "pf_transformer_overload" in drawn or "pf_transformer_warn" in drawn:
                handles.append(Line2D([], [], color=st.pf_loading_overload_color,
                                      marker=st.transformer_marker, linestyle="None", markersize=8,
                                      label="PF transformer overload"))
                handles.append(Line2D([], [], color=st.pf_loading_warn_color,
                                      marker=st.transformer_marker, linestyle="None", markersize=6,
                                      label="PF transformer warning"))
        if "powerflow_no_data" in drawn:
            handles.append(Line2D([], [], color="#b71c1c", lw=2, linestyle="dashed",
                                  label="PF enabled — no results yet (run powerflow/Level-2)"))
        return handles
