# -*- coding: utf-8 -*-
"""Map style model — نمایش قابل‌تنظیم نقشه (درخواست کاربر).

Everything the map draws (feeder colours/thickness, switch / source /
open-point / transformer / proposed / manual markers) comes from ONE
`MapStyle` object, so:

  * the on-screen map and the report PNG stay identical (D-04);
  * the engineer can tune colours & marker sizes in the GUI
    («رنگ و ضخامت فیدرها، سایز/مارکر/نماد کلیدها، سورس، open point…»);
  * the DEFAULT feeder colour of every feeder in the style dialog is the
    very colour the renderer would assign automatically (per-feeder
    distinct palette — «رنگ اولیه که برای هر فیدر تخصیص می‌دهی را در
    map style هم اعمال کن»), never one shared default code;
  * named styles (multi-style book) are plain dicts — the project store
    persists them under the ``map_styles`` project key (بستن/بازکردن
    پروژه همان تنظیمات را برمی‌گرداند).

Discipline: Qt-free and matplotlib-free (pure data + pure functions,
unit-tested); the dialog glue lives in ui/qt/map_style_dialog.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields, asdict

#: deterministic qualitative palette (feeder index → colour) — the SAME
#: palette the renderer has always used, now the single source of truth
FEEDER_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e",
                 "#8c564b", "#e377c2", "#17becf", "#bcbd22", "#7f7f7f",
                 "#aec7e8", "#ffbb78", "#98df8a", "#c5b0d5", "#c49c94"]
UNKNOWN_COLOR = "#7f7f7f"

#: سطوح پیش‌فرض «توزیع رنگی مسیر بر اساس تکرار خاموشی»
#: هر سطح: حد بالای تعداد خاموشی (``max``؛ None = بی‌نهایت) و رنگ آن.
DEFAULT_OUTAGE_HEAT_LEVELS = [
    {"max": 2, "color": "#2e7d32", "label": "< ۲ خاموشی"},
    {"max": 10, "color": "#ef6c00", "label": "۲ تا ۱۰ خاموشی"},
    {"max": None, "color": "#c62828", "label": "> ۱۰ خاموشی"},
]

def _clean_heat_levels(value) -> list[dict]:
    """سطوح توزیع رنگی را اعتبارسنجی می‌کند (حد بالا + رنگ معتبر)."""
    out: list[dict] = []
    for item in list(value or []):
        if not isinstance(item, dict):
            continue
        color = str(item.get("color") or "").strip()
        if not color.startswith("#") or len(color) not in (4, 7):
            continue
        raw_max = item.get("max")
        try:
            top = None if raw_max in (None, "", "None") else float(raw_max)
        except (TypeError, ValueError):
            continue
        out.append({"max": top, "color": color,
                    "label": str(item.get("label") or "").strip()
                    or ("همهٔ تکرارها" if top is None
                        else f"≤ {top:g} خاموشی")})
    return out or [dict(x) for x in DEFAULT_OUTAGE_HEAT_LEVELS]


#: valid Matplotlib marker codes offered in the style dialog
MARKER_CHOICES = ("o", "s", "D", "d", "^", "v", "<", ">", "P", "X", "*",
                  "p", "h", "H", "8", ".")


def auto_palette(traces=None, feeders=None) -> dict[str, str]:
    """feeder_key → the automatic deterministic colour (feeder_palette).

    ``traces`` may be FeederTrace objects (with ``feeder_key``) or plain
    strings; ``feeders`` overrides the extracted key set outright.
    """
    if feeders is None:
        feeders = [getattr(t, "feeder_key", t) for t in (traces or [])]
    keys = sorted({str(k) for k in feeders if k})
    return {k: FEEDER_COLORS[i % len(FEEDER_COLORS)]
            for i, k in enumerate(keys)}


@dataclass
class MapStyle:
    """Every tunable visual parameter of the network map."""
    # -- feeders ------------------------------------------------------
    feeder_colors: dict = field(default_factory=dict)   # feeder → #rrggbb
    visible_feeders: list | None = None  # None=all; []=none; persisted with map style
    feeder_width: float = 0.6            # conductor width, whole network
    feeder_width_filtered: float = 1.0   # width in single-feeder view
    unknown_color: str = UNKNOWN_COLOR   # untraced / no-label edges
    # -- devices ------------------------------------------------------
    switch_color: str = "#444444"
    switch_size: float = 6.0
    switch_marker: str = "o"
    # نماد مستقل انواع کلید موجود در GIS (کدهای FCT/DCS/CBR/REC/SEC)
    fct_color: str = "#c62828"
    fct_size: float = 24.0
    fct_marker: str = "v"
    dcs_color: str = "#1565c0"
    dcs_size: float = 24.0
    dcs_marker: str = "o"
    cbr_color: str = "#6a1b9a"
    cbr_size: float = 28.0
    cbr_marker: str = "s"
    rec_color: str = "#ef6c00"
    rec_size: float = 30.0
    rec_marker: str = "D"
    sec_color: str = "#00897b"
    sec_size: float = 27.0
    sec_marker: str = "^"
    #: نمایش فیوز کات‌اوت‌ها روی نقشه — پیش‌فرض **خاموش** (درخواست کاربر):
    #: فیوزها فقط وقتی دیده می‌شوند که کاربر صریحاً روشن کند (از فهرست
    #: کلیدهای نقشه یا از پنجرهٔ تنظیمات نمایشی). رندر گزارش هم همین
    #: پیش‌فرض را دارد، مگر اینکه فهرست صریح کلیدهای پنهان داده شود.
    show_fuse_cutouts: bool = False
    unknown_device_color: str = "#424242"
    unknown_device_size: float = 18.0
    unknown_device_marker: str = "P"
    no_tie_color: str = "#c62828"
    no_tie_size: float = 26.0
    no_tie_marker: str = "D"
    source_color: str = "#111111"
    coordinate_size: float = 150.0
    coordinate_marker: str = "X"
    coordinate_color: str = "#ff00aa"
    source_size: float = 70.0
    source_marker: str = "s"
    transformer_color: str = "#555555"
    transformer_size: float = 3.0
    transformer_marker: str = "."
    # -- overlay markers ----------------------------------------------
    proposed_color: str = "#2e7d32"
    proposed_size: float = 52.0
    proposed_marker: str = "*"
    manual_color: str = "#1565c0"
    manual_size: float = 60.0
    manual_marker: str = "P"
    # -- optimized sectionalizers (Sectionalizer/EENS engine output) ----
    show_opt_sectionalizers: bool = True
    opt_sec_color: str = "#6a1b9a"
    opt_sec_size: float = 110.0
    opt_sec_marker: str = "X"
    # -- outages with coordinates (لایهٔ خاموشی) ------------------------
    show_outages: bool = True
    outage_color: str = "#e53935"
    outage_size: float = 48.0
    outage_marker: str = "o"
    outage_alpha: float = 0.9
    outage_confirmed_color: str = "#2e7d32"
    outage_pending_color: str = "#ef6c00"
    outage_rejected_color: str = "#c62828"
    outage_label_size: float = 5.0
    outage_label_color: str = "#37474f"
    outage_label_alpha: float = 0.95
    show_outage_labels: bool = True
    show_outage_links: bool = False
    # -- توزیع رنگی مسیر فیدرها بر اساس تکرار خاموشی (DIgSILENT-style) ----
    outage_heat_enabled: bool = False
    #: شعاع اثر هر خاموشی بر یال‌های فیدر (متر) — پیش‌فرض ۵۰۰۰ و **بدون
    #: سقف** (درخواست کاربر: عدد بزرگ‌تر از ۵۰۰۰ هم پذیرفته می‌شود).
    outage_heat_radius_m: float = 5000.0
    outage_heat_width: float = 2.4
    outage_heat_alpha: float = 0.95
    outage_heat_levels: list = field(
        default_factory=lambda: [dict(x) for x in DEFAULT_OUTAGE_HEAT_LEVELS])
    # -- چیدمان برچسب‌ها (فاصلهٔ کم و خط راهنما به‌جای پراکندگی) ----------
    outage_label_offset_pt: float = 4.0
    outage_label_max_levels: int = 3
    outage_label_leader: bool = True
    outage_link_color: str = "#8e24aa"
    outage_link_width: float = 1.0
    outage_link_alpha: float = 0.55
    #: شناسهٔ رخدادهایی که کاربر پنهان کرده است (روشن/خاموش تک‌تک)
    hidden_outage_ids: list | None = None
    # -- zone display --------------------------------------------------
    zone_label_size: float = 5.0
    zone_label_color: str = "#263238"
    zone_label_alpha: float = 0.92
    zone_label_background_color: str = "#ffffff"
    zone_label_background_alpha: float = 0.72
    zone_selected_color: str = "#ffb300"
    zone_selected_width: float = 4.0
    zone_selected_alpha: float = 0.95
    show_zone_labels: bool = False
    # -- misc ----------------------------------------------------------
    show_legend: bool = True

    # ------------------------------------------------------------------
    @classmethod
    def default_for(cls, traces=None, feeders=None) -> "MapStyle":
        """Style whose feeder colours ARE the automatic per-feeder
        palette (user request — no shared default code in the dialog)."""
        st = cls()
        st.feeder_colors = dict(auto_palette(traces, feeders))
        return st

    def palette_of(self, traces=None, feeders=None) -> dict[str, str]:
        """Effective feeder palette: automatic palette overlaid with the
        user-chosen colours (a feeder added later still gets a colour).

        رنگ‌های ذخیره‌شده در نسخه‌های قبل با کلید کوتاه («F1») نوشته
        شده‌اند؛ آن‌ها روی شناسهٔ کامل فعلی («F1 - MESHKIN») نگاشت
        می‌شوند تا رنگ انتخابی کاربر گم نشود، و انتخاب مبهم («F2» با دو
        فیدر) روی هر دو فیدر اعمال می‌شود.
        """
        pal = auto_palette(traces, feeders)
        from ..topology.tracing import match_feeders
        known = list(pal)
        for k, c in (self.feeder_colors or {}).items():
            if not c:
                continue
            hits = match_feeders(k, known)
            if hits:
                for h in hits:
                    pal[h] = c
            else:
                pal[k] = c          # فیدری که فعلاً در شبکه نیست — می‌ماند
        return pal

    def color_of(self, feeder_key: str) -> str:
        """Colour of one feeder (style override first, then palette)."""
        c = (self.feeder_colors or {}).get(feeder_key or "")
        if c:
            return c
        keys = sorted(self.feeder_colors or {})
        if feeder_key in keys:
            return self.feeder_colors[feeder_key]
        # نگارش قدیمی (کلید کوتاه) → همان رنگ کاربر
        from ..topology.tracing import match_feeders
        for k in match_feeders(feeder_key, keys):
            if self.feeder_colors.get(k):
                return self.feeder_colors[k]
        # deterministic fallback identical to the auto palette
        known = [k for k in keys]
        try:
            idx = known.index(feeder_key)
        except ValueError:
            return self.unknown_color
        return FEEDER_COLORS[idx % len(FEEDER_COLORS)]

    # ------------------------------------------------------------------
    def as_dict(self) -> dict:
        """JSON-safe dict (project store / style book)."""
        d = asdict(self)
        d["feeder_colors"] = {str(k): str(v)
                              for k, v in (self.feeder_colors or {}).items()}
        if self.hidden_outage_ids is not None:
            d["hidden_outage_ids"] = sorted({str(x)
                                             for x in self.hidden_outage_ids})
        return d

    @classmethod
    def from_dict(cls, d: dict | None) -> "MapStyle":
        """Rebuild from ``as_dict`` — unknown keys ignored, bad values
        fall back to defaults (a future field can never break the load)."""
        st = cls()
        if not d:
            return st
        valid = {f.name for f in fields(cls)}
        for k, v in dict(d).items():
            if k not in valid:
                continue
            cur = getattr(st, k)
            if isinstance(cur, dict):
                setattr(st, k, {str(a): str(b) for a, b in (v or {}).items()})
            elif k == "outage_heat_levels":
                try:
                    st.outage_heat_levels = _clean_heat_levels(v)
                except Exception:                  # noqa: BLE001
                    pass                      # keep the default
            elif k in ("visible_feeders", "hidden_outage_ids"):
                setattr(st, k, None if v is None else
                        sorted({str(x) for x in v}))
            elif isinstance(cur, bool):
                setattr(st, k, bool(v))
            elif isinstance(cur, (int, float)):
                try:
                    setattr(st, k, type(cur)(float(v)))
                except (TypeError, ValueError):
                    pass                      # keep the default
            else:
                setattr(st, k, str(v or type(cur)()))
        # marker sanity — an invalid code would raise at render time
        for name in ("switch_marker", "fct_marker", "dcs_marker",
                     "cbr_marker", "rec_marker", "sec_marker",
                     "unknown_device_marker", "no_tie_marker", "source_marker", "coordinate_marker",
                     "transformer_marker", "proposed_marker", "manual_marker",
                     "outage_marker", "opt_sec_marker"):
            if getattr(st, name) not in MARKER_CHOICES:
                setattr(st, name, MapStyle().__dict__[name])
        return st


def merge_style_book(book: dict | None, traces=None, feeders=None
                     ) -> tuple[MapStyle, str]:
    """(styles book from the project) → (active style, active name).

    The book is ``{name: style_dict}``; the ACTIVE entry is whichever
    ``_active`` key the caller kept — this helper only guarantees a
    usable default when the book is empty or corrupt.
    """
    book = {str(k): MapStyle.from_dict(v)
            for k, v in (book or {}).items() if isinstance(v, dict)}
    if not book:
        return MapStyle.default_for(traces, feeders), "پیش‌فرض"
    name = next(iter(sorted(book)))
    return book[name], name
