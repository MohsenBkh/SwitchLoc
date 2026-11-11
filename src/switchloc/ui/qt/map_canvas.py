# -*- coding: utf-8 -*-
"""Map canvas — interactive Qt map tab around the headless renderer.

The Qt canvas embeds the very same `NetworkMapRenderer` used for report
PNGs, so the on-screen map and the printed report can never diverge
(one rendering path — D-04 discipline).

Interactive zoom pack (plain Matplotlib events, no extra dependency):

  * mouse-wheel zoom, anchored at the cursor position
  * grab-and-drag panning with the left mouse button
  * double-click = zoom in at the cursor
  * «ذره‌بین» region zoom — drag a rectangle, the view fills it (نیاز ۴)
  * toolbar buttons: Zoom in / Zoom out / Fit view / Region zoom
  * zoom indicator on a 0–100 % scale (user feedback: «اسکیل زوم تا
    ۱۰۰ درصد») — 0 % = full view, 100 % = deepest zoom; the absolute
    magnification (×) is shown next to it
  * feeder filter combo + zone-labels checkbox (renderer parameters)
  * OSM background toggle (نیاز ۵) — raster UNDER the network (zorder 0)

True-geometry view (user feedback: «نمایش زاویه دار»): the 90° rotation
is REMOVED and the axes keep aspect EQUAL — the same undistorted,
perpendicular view as the printed report.  The axes still cover the
whole widget (tight margins) but the drawing itself letterboxes in one
dimension instead of being stretched, so angles and shapes on screen
match the report and the OSM tiles exactly.  A visible border marks the
displayable extent.

Discipline: the whole zoom/pan engine lives in the Qt-free
`MapCanvasMixin` (module level) — engineering logic is testable without
Qt (tests run it on a pure-Agg canvas).  Only the thin widget wrappers
(`MapCanvas`, `MapTab`) inside `make_map_canvas()` touch PySide6.
"""
from __future__ import annotations

from ...logging_setup import get_logger

_log = get_logger("ui.map")

from ..map_renderer import NetworkMapRenderer

#: zoom factor applied by one wheel notch / one click on Zoom in
WHEEL_STEP = 1.25
#: deepest zoom-IN vs the full extent: 10 000x (absolute 1 000 000 %).
#: raised 10x AGAIN on user feedback (the shipped 1000x cap «زوم ۱۰ برابر
#: بیشتر نیاز دارم»): individual service drops and single-transformer
#: zones stay inspectable.  The indicator itself reads a normalized
#: 0-100 % scale (see `zoom_level_pct`).
ZOOM_IN = 10000.0
#: deepest zoom-OUT vs the full extent — beyond 8x the whole network is
#: a dot in the middle of the canvas, the cap just avoids empty wandering
ZOOM_OUT = 8.0
#: absolute floor for the axis span (degenerate-limit guard, metres)
_MIN_SPAN = 1e-9
#: a rubber-band rectangle smaller than this many display pixels is
#: treated as a click, not a region selection (نیاز ۴)
_REGION_MIN_PX = 6.0


def zoom_limits(lo: float, hi: float, anchor: float,
                scale: float) -> tuple[float, float]:
    """New ``(lo, hi)`` after zooming by ``scale`` around ``anchor``.

    ``scale < 1`` zooms in (the span tightens), ``scale > 1`` zooms out;
    the point ``anchor`` keeps its relative position inside the interval
    (cursor-anchored zoom).
    """
    return anchor - (anchor - lo) * scale, anchor + (hi - anchor) * scale


def clamp_span(lo: float, hi: float, anchor: float,
               home_lo: float, home_hi: float) -> tuple[float, float]:
    """Snap a zoomed span back inside the allowed window (same anchor).

    Used by the engine when a requested step overshoots the cap: instead
    of refusing the whole step the span lands exactly on the limit, so
    the user can always reach the full 10 000x depth with wheel notches.
    """
    home = home_hi - home_lo
    span = hi - lo
    if span <= 0.0:
        return lo, hi
    span = min(max(span, home / ZOOM_IN), home * ZOOM_OUT)
    frac = (anchor - lo) / (hi - lo)
    lo2 = anchor - frac * span
    return lo2, lo2 + span


def span_ok(lo: float, hi: float, home_lo: float,
            home_hi: float) -> bool:
    """True when ``(lo, hi)`` is inside the allowed zoom window.

    The window is [full extent / ZOOM_IN ... full extent * ZOOM_OUT]
    plus an absolute floor — zooming never degenerates to a zero span.
    A relative 1e-9 tolerance absorbs the floating-point reconstruction
    error of ``clamp_span`` (``lo2 + span - lo2`` loses ~1e-10 on
    UTM-scale coordinates, which otherwise refuses the LAST wheel step
    exactly at the cap).
    """
    span = hi - lo
    home = home_hi - home_lo
    if span <= _MIN_SPAN:
        return False
    deep = home / ZOOM_IN
    wide = home * ZOOM_OUT
    return (deep - 1e-9 * deep) <= span <= (wide + 1e-9 * wide)


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


class MapCanvasMixin:
    """Qt-free zoom/pan engine for a single-axes Matplotlib canvas.

    Expects from the host canvas: ``self.fig``, ``draw_idle()``,
    ``mpl_connect()`` and — optionally — ``setCursor()`` (guarded).
    """

    def _init_state(self) -> None:
        # NOTE: named `map_renderer`, NOT `renderer` — FigureCanvasAgg uses
        # `.renderer` for its own paint device and would overwrite it.
        self.map_renderer: NetworkMapRenderer | None = None
        self._home: tuple | None = None      # full extent ((x0,x1),(y0,y1))
        self._pan: tuple | None = None       # (px, py, xlim, ylim, ax)
        self.on_view_changed = None          # callback(zoom_pct | None)
        # نیاز ۴ — region-zoom («ذره‌بین») state
        self.region_mode = False             # when True drag = rubber band
        self._region: tuple | None = None    # (ax, x0, y0, patch)
        # جایابی دستی — pick mode: the next map click returns its project-CRS point
        self.pick_mode = False
        self.on_pick = None                  # callback(x_project, y_project)
        self.on_zone_pick = None             # callback(zone_id)
        self._zone_label_positions: dict[str, tuple[float, float]] = {}
        self._zone_drag = None  # (artist, press_x, press_y, moved, axes)

    def set_pick_mode(self, on: bool) -> None:
        """جایابی دستی: کلیک بعدی روی نقشه، مختصات آن را در CRS پروژه برمی‌گرداند."""
        self.pick_mode = bool(on)
        self._magnifier_cursor(on)

    def connect_events(self) -> None:
        self.mpl_connect("scroll_event", self._on_scroll)
        self.mpl_connect("button_press_event", self._on_press)
        self.mpl_connect("motion_notify_event", self._on_motion)
        self.mpl_connect("button_release_event", self._on_release)
        self.mpl_connect("pick_event", self._on_pick_event)

    # ---- rendering ---------------------------------------------------
    def show_network(self, renderer: NetworkMapRenderer, title: str = "",
                     feeder_key: str | None = None,
                     zone_labels: bool = False,
                     proposed_nodes=None,
                     rotate: bool | None = None,
                     osm_image=None, osm_extent=None,
                     osm_note: str = "",
                     manual_nodes=None, highlight_point=None,
                     zone_load_kw=None, selected_zone=None,
                     hidden_switch_ids=None, zone_up_mwh=None,
                     zone_outage_hours=None, manual_tie_pairs=None,
                     outage_points=None, sectionalizer_nodes=None,
                     hidden_outage_ids=None) -> None:
        del rotate                            # rotation removed (feedback)
        previous_renderer = self.map_renderer
        previous_highlight = getattr(self, "_last_highlight_point", None)
        previous_home = self._home
        previous_ax = self.main_ax()
        # Persist user-dragged zone callouts before clearing the figure.
        if previous_ax is not None:
            for artist in getattr(previous_ax, "texts", []):
                gid = artist.get_gid()
                if isinstance(gid, str) and gid.startswith("zone:"):
                    try:
                        self._zone_label_positions[gid.split(":", 1)[1]] = tuple(
                            float(v) for v in artist.get_position())
                    except Exception:
                        pass
        previous_view = ((previous_ax.get_xlim(), previous_ax.get_ylim())
                         if previous_ax is not None and previous_renderer is not None
                         and previous_renderer.graph is renderer.graph else None)
        self.map_renderer = renderer
        self.fig.clf()
        renderer.render_into(self.fig, title=title,
                             feeder_filter=feeder_key,
                             zone_labels=zone_labels,
                             proposed_nodes=proposed_nodes,
                             rotate=False,
                             manual_nodes=manual_nodes,
                             highlight_point=highlight_point,
                             zone_load_kw=zone_load_kw,
                             selected_zone=selected_zone,
                             hidden_switch_ids=hidden_switch_ids,
                             zone_up_mwh=zone_up_mwh,
                             zone_outage_hours=zone_outage_hours,
                             manual_tie_pairs=manual_tie_pairs,
                             outage_points=outage_points,
                             sectionalizer_nodes=sectionalizer_nodes,
                             hidden_outage_ids=hidden_outage_ids,
                             zone_label_positions=self._zone_label_positions)
        if not self.fig.get_constrained_layout():
            # the interactive map must use the WHOLE widget: matplotlib's
            # default margins (~11-12 % on each side) shrank the drawing
            # area to roughly half of the tab and the map looked tiny
            self.fig.subplots_adjust(left=0.004, right=0.996,
                                     top=0.982, bottom=0.004)
        ax = self.main_ax()
        if ax is not None:
            # true-geometry map (user feedback «نمایش زاویه دار») that
            # ALSO fills the whole widget (user feedback: the previous
            # letterboxed view left too much empty space around the map):
            # aspect stays EQUAL (undistorted) but with
            # adjustable="datalim" the DATA LIMITS expand to fill the
            # fixed axes box instead of the axes box shrinking — the map
            # becomes as large as the widget allows, geometry untouched.
            ax.set_aspect("equal", adjustable="datalim")
            try:
                ax.apply_aspect()             # expand limits NOW so the
            except Exception as exc:          # zoom home matches the view
                _log.debug("apply_aspect failed: %s", exc)
            self._style_map_frame(ax)
            if osm_image is not None and osm_extent is not None:
                # نیاز ۵ — OSM raster goes UNDER the network (zorder 0);
                # no aspect override — the raster must obey the same
                # equal-aspect frame as the feeders (no skew of its own)
                lim_before = (ax.get_xlim(), ax.get_ylim())
                ax.imshow(osm_image, extent=osm_extent, zorder=0,
                          interpolation="bilinear")
                ax.set_aspect("equal")
                if ax.get_xlim() != lim_before[0] or \
                        ax.get_ylim() != lim_before[1]:
                    ax.set_xlim(*lim_before[0])
                    ax.set_ylim(*lim_before[1])
                if osm_note:
                    ax.text(0.995, 0.01, osm_note, transform=ax.transAxes,
                            fontsize=5, ha="right", va="bottom", alpha=0.8,
                            zorder=30,
                            bbox=dict(boxstyle="round,pad=0.15",
                                      fc="white", ec="none", alpha=0.6))
            # store the base line widths — deep zoom scales them (below)
            self._base_lw = [list(lc.get_linewidths())
                             for lc in ax.collections]
            if highlight_point is not None:
                hx, hy = map(float, highlight_point)
                x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
                wx = max(x1-x0, 100.0); wy = max(y1-y0, 100.0)
                pad = max(wx, wy) * 0.02
                ax.set_xlim(min(x0, hx-pad), max(x1, hx+pad))
                ax.set_ylim(min(y0, hy-pad), max(y1, hy+pad))
        self._home = (ax.get_xlim(), ax.get_ylim()) if ax else None
        # A style/visibility/zone-label redraw must not reset a user's zoom
        # OR redefine the full-extent zoom limits as the current zoom window.
        if previous_view is not None and ax is not None and (
                highlight_point is None or tuple(highlight_point) == previous_highlight):
            ax.set_xlim(*previous_view[0]); ax.set_ylim(*previous_view[1])
            if previous_home is not None:
                self._home = previous_home
        if highlight_point is not None and ax is not None and (
                previous_view is None or tuple(highlight_point) != previous_highlight):
            hx, hy = map(float, highlight_point)
            span = max(self._home[0][1]-self._home[0][0],
                       self._home[1][1]-self._home[1][0])
            radius = max(span * 0.006, 80.0)
            self.zoom_to_region(ax, hx-radius, hy-radius, hx+radius, hy+radius)
        self._last_highlight_point = tuple(highlight_point) if highlight_point is not None else None
        self._notify()

    @staticmethod
    def _style_map_frame(ax) -> None:
        """Border of the displayable map area (user feedback: a frame
        must mark the visible map extent).  Ticks stay hidden — only the
        frame rectangle is drawn."""
        try:
            ax.set_axis_on()
            ax.tick_params(which="both", length=0,
                           labelbottom=False, labelleft=False,
                           bottom=False, left=False, top=False, right=False)
            for spine in ax.spines.values():
                spine.set_visible(True)
                spine.set_edgecolor("#0d47a1")
                spine.set_linewidth(1.6)
            ax.patch.set_facecolor("#fafbfc")
            ax.patch.set_alpha(1.0)
            ax.grid(False)
        except Exception:
            pass                              # decorative only — never fatal

    # -- deep-zoom legibility: hairline conductors become visible --------
    _LW_MAX_SCALE = 3.0

    def _scale_line_widths(self, pct: float | None) -> None:
        """Scale conductor widths with the zoom level (legibility).

        At 100 % the renderer widths are unchanged; at 100 000 % the
        width is up to 3x so single spans stay visible instead of
        collapsing into sub-pixel hairlines.
        """
        ax = self.main_ax()
        base = getattr(self, "_base_lw", None)
        if ax is None or not base:
            return
        scale = 1.0 if not pct else \
            max(1.0, min(self._LW_MAX_SCALE,
                         (max(pct, 100.0) / 100.0) ** 0.35))
        for lc, widths in zip(ax.collections, base):
            try:
                lc.set_linewidth([w * scale for w in widths])
            except Exception as exc:
                _log.debug("line-width rescale skipped: %s", exc)

    def main_ax(self):
        axes = self.fig.get_axes()
        return axes[0] if axes else None

    # ---- zoom / pan internals ----------------------------------------
    def _zoom_axes(self, ax, x: float, y: float, scale: float) -> bool:
        """Apply a cursor-anchored zoom; False when the step is refused.

        A step that overshoots the cap is snapped exactly onto the cap
        (returns True once); when already at the cap the step is refused
        so callers/loops see a real end of the zoom range.
        """
        if self._home is None or x is None or y is None:
            return False
        (hx0, hx1), (hy0, hy1) = self._home
        cur = (ax.get_xlim(), ax.get_ylim())
        nx = zoom_limits(*cur[0], x, scale)
        ny = zoom_limits(*cur[1], y, scale)
        if not (span_ok(*nx, hx0, hx1) and span_ok(*ny, hy0, hy1)):
            # overshoot -> snap exactly onto the cap instead of refusing
            if nx[1] - nx[0] <= 0.0 or ny[1] - ny[0] <= 0.0:
                return False
            nx = clamp_span(nx[0], nx[1], x, hx0, hx1)
            ny = clamp_span(ny[0], ny[1], y, hy0, hy1)
            if not (span_ok(*nx, hx0, hx1) and span_ok(*ny, hy0, hy1)):
                return False
            if _close(nx[1] - nx[0], cur[0][1] - cur[0][0]) and \
                    _close(ny[1] - ny[0], cur[1][1] - cur[1][0]):
                return False          # already at the cap — no real zoom
        ax.set_xlim(*nx)
        ax.set_ylim(*ny)
        self._notify()
        return True

    def _zoom_center(self, scale: float) -> None:
        ax = self.main_ax()
        if ax is None or self._home is None:
            return
        (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
        self._zoom_axes(ax, (x0 + x1) / 2.0, (y0 + y1) / 2.0, scale)

    def fit_view(self) -> None:
        """Restore the full-extent view (home limits)."""
        ax = self.main_ax()
        if ax is None or self._home is None:
            return
        ax.set_xlim(*self._home[0])
        ax.set_ylim(*self._home[1])
        self._notify()

    # ---- نیاز ۴: region zoom («ذره‌بین») ------------------------------
    def set_region_mode(self, on: bool) -> None:
        """Toggle the rubber-band region-zoom mode (magnifier tool)."""
        self.region_mode = bool(on)
        if not on and self._region is not None:
            self._discard_region()
        self._magnifier_cursor(on)

    def _discard_region(self) -> None:
        if self._region is None:
            return
        _ax, _x0, _y0, patch = self._region
        try:
            patch.remove()
        except Exception:
            pass                              # already gone with the axes
        self._region = None

    def region_rect_data(self) -> tuple | None:
        """((x0, x1), (y0, y1)) of the current rubber band (test hook)."""
        if self._region is None:
            return None
        _ax, x0, y0, patch = self._region
        w, h = patch.get_width(), patch.get_height()
        if not w or not h:
            return None
        return ((min(x0, x0 + w), max(x0, x0 + w)),
                (min(y0, y0 + h), max(y0, y0 + h)))

    def zoom_to_region(self, ax, x0: float, y0: float,
                       x1: float, y1: float) -> bool:
        """Fill the view with the given data-space rectangle (نیاز ۴).

        Degenerate rectangles (zero span after the display-pixel filter)
        are refused; the span caps of `span_ok` still apply, so a tiny
        marquee never degenerates the axes.
        """
        if self._home is None or ax is None:
            return False
        lox, hix = sorted((float(x0), float(x1)))
        loy, hiy = sorted((float(y0), float(y1)))
        if hix - lox <= _MIN_SPAN or hiy - loy <= _MIN_SPAN:
            return False
        (hx0, hx1), (hy0, hy1) = self._home
        # honour the zoom-out cap too (a huge marquee must not over-zoom)
        span_x = min(hix - lox, (hx1 - hx0) * ZOOM_OUT)
        span_y = min(hiy - loy, (hy1 - hy0) * ZOOM_OUT)
        cx, cy = (lox + hix) / 2.0, (loy + hiy) / 2.0
        # keep the TRUE-GEOMETRY ratio (aspect equal): expand the smaller
        # span to the home aspect ratio, otherwise the next draw would
        # re-stretch the limits and the marquee would not fill exactly
        home_ratio = ((hx1 - hx0) / (hy1 - hy0)) if (hy1 - hy0) > 0 else 1.0
        if span_y > 0 and span_x / span_y > home_ratio:
            span_y = span_x / home_ratio
        elif span_y > 0:
            span_x = span_y * home_ratio
        nx = (cx - span_x / 2.0, cx + span_x / 2.0)
        ny = (cy - span_y / 2.0, cy + span_y / 2.0)
        nx = clamp_span(nx[0], nx[1], cx, hx0, hx1)
        ny = clamp_span(ny[0], ny[1], cy, hy0, hy1)
        ax.set_xlim(*nx)
        ax.set_ylim(*ny)
        self._notify()
        return True

    def _on_region_press(self, ev) -> bool:
        """Start the rubber band; True when the event was consumed."""
        if not self.region_mode or ev.inaxes is None \
                or ev.xdata is None or ev.ydata is None or ev.button != 1:
            return False
        from matplotlib.patches import Rectangle
        ax = ev.inaxes
        self._discard_region()
        patch = Rectangle((ev.xdata, ev.ydata), 0, 0,
                          linewidth=1.2, edgecolor="#0d47a1",
                          facecolor="#1e88e5", alpha=0.18, zorder=20)
        ax.add_patch(patch)
        self._region = (ax, ev.xdata, ev.ydata, patch)
        return True

    def _on_region_motion(self, ev) -> bool:
        if self._region is None or ev.xdata is None or ev.ydata is None:
            return False
        ax, x0, y0, patch = self._region
        if ev.inaxes is not ax:
            return False
        patch.set_width(ev.xdata - x0)
        patch.set_height(ev.ydata - y0)
        self.draw_idle()
        return True

    def _on_region_release(self, ev) -> bool:
        """Finish the rubber band and zoom; True when consumed."""
        if self._region is None:
            return False
        ax, x0, y0, patch = self._region
        w_px = abs(patch.get_width()) * self._px_per_data_x(ax)
        h_px = abs(patch.get_height()) * self._px_per_data_y(ax)
        x1, y1 = (ev.xdata, ev.ydata) if ev.xdata is not None \
            else (x0, y0)
        self._discard_region()
        if w_px < _REGION_MIN_PX or h_px < _REGION_MIN_PX:
            self.draw_idle()
            return True                        # click, not a selection
        return self.zoom_to_region(ax, x0, y0, x1, y1)

    @staticmethod
    def _px_per_data_x(ax) -> float:
        try:
            span = ax.get_xlim()[1] - ax.get_xlim()[0]
            return (ax.get_window_extent().width / span) if span > 0 else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _px_per_data_y(ax) -> float:
        try:
            span = ax.get_ylim()[1] - ax.get_ylim()[0]
            return (ax.get_window_extent().height / span) if span > 0 else 0.0
        except Exception:
            return 0.0

    def _magnifier_cursor(self, on: bool) -> None:   # pragma: no cover
        try:
            from PySide6.QtCore import Qt
            self.setCursor(Qt.CursorShape.CrossCursor if on
                           else Qt.CursorShape.ArrowCursor)
        except Exception:
            pass                              # pure-Agg host / no Qt

    def _notify(self) -> None:
        self._scale_line_widths(self.zoom_pct())
        self.draw_idle()
        if self.on_view_changed is not None:
            self.on_view_changed(self.zoom_pct())

    def zoom_pct(self) -> float | None:
        """Current zoom level in % (100 = full extent)."""
        if self._home is None:
            return None
        ax = self.main_ax()
        if ax is None:
            return None
        home_w = self._home[0][1] - self._home[0][0]
        cur_w = ax.get_xlim()[1] - ax.get_xlim()[0]
        if cur_w <= 0:
            return None
        return round(home_w / cur_w * 100.0, 1)

    def zoom_level_pct(self) -> float | None:
        """Normalized zoom level 0-100 % on a log scale (user feedback:
        the zoom scale must display up to 100 %).  0 % = full view,
        100 % = the deepest zoom (ZOOM_IN); every wheel notch moves the
        needle uniformly."""
        if self._home is None:
            return None
        ax = self.main_ax()
        if ax is None:
            return None
        home_w = self._home[0][1] - self._home[0][0]
        cur_w = ax.get_xlim()[1] - ax.get_xlim()[0]
        if cur_w <= 0 or home_w <= 0:
            return None
        import math
        mag = home_w / cur_w                 # 1.0 at fit .. ZOOM_IN at cap
        frac = math.log(max(mag, 1e-12)) / math.log(ZOOM_IN)
        return round(max(0.0, min(100.0, frac * 100.0)), 1)

    # ---- Matplotlib event handlers ------------------------------------
    def _on_scroll(self, ev) -> None:
        if ev.inaxes is None or ev.xdata is None or ev.ydata is None:
            return
        scale = 1.0 / WHEEL_STEP if ev.button == "up" else WHEEL_STEP
        self._zoom_axes(ev.inaxes, ev.xdata, ev.ydata, scale)

    def _on_pick_event(self, ev) -> None:
        # Zone selection is finalized on mouse release. Handling it in
        # pick_event can redraw the axes before a drag handler captures text.
        return None

    @staticmethod
    def _zone_label_hit(ax, ev):
        if ax is None or ev is None:
            return None
        for artist in reversed(getattr(ax, "texts", [])):
            gid = artist.get_gid()
            if isinstance(gid, str) and gid.startswith("zone:"):
                try:
                    hit, _details = artist.contains(ev)
                except Exception:
                    hit = False
                if hit:
                    return artist
        return None

    def _on_press(self, ev) -> None:
        if self.pick_mode:
            # جایابی دستی — the click IS the pick (no pan/zoom side effect)
            if ev.inaxes is not None and ev.xdata is not None \
                    and ev.button == 1:
                self.pick_mode = False
                self._magnifier_cursor(False)
                if self.on_pick is not None:
                    self.on_pick(float(ev.xdata), float(ev.ydata))
            return
        if self._on_region_press(ev):
            return
        if ev.inaxes is None or ev.xdata is None:
            return
        if ev.dblclick:                       # double-click = zoom in
            self._zoom_axes(ev.inaxes, ev.xdata, ev.ydata,
                            1.0 / WHEEL_STEP)
            return
        if ev.button != 1:
            return
        # Drag the callout independently from the map. Its xy anchor stays
        # fixed on the zone; changing xytext moves the box and leader line.
        artist = self._zone_label_hit(ev.inaxes, ev)
        if artist is not None:
            self._zone_drag = (artist, float(ev.x), float(ev.y), False,
                               ev.inaxes)
            self._pan = None
            self._grab(True)
            return
        self._pan = (ev.x, ev.y, ev.inaxes.get_xlim(),
                     ev.inaxes.get_ylim(), ev.inaxes)
        self._grab(True)

    def _on_motion(self, ev) -> None:
        if self._on_region_motion(ev):
            return
        if self._zone_drag is not None:
            artist, px0, py0, moved, ax = self._zone_drag
            if ev.inaxes is not ax or ev.xdata is None or ev.ydata is None:
                return
            import math
            moved = moved or math.hypot(float(ev.x) - px0,
                                        float(ev.y) - py0) >= 3.0
            artist.set_position((float(ev.xdata), float(ev.ydata)))
            self._zone_drag = (artist, px0, py0, moved, ax)
            self.draw_idle()
            return
        if self._pan is None or ev.x is None or ev.y is None:
            return
        px0, py0, (lx0, lx1), (ly0, ly1), ax = self._pan
        # convert the press pixel and the current pixel through the
        # *current* transform — no drift while dragging
        inv = ax.transData.inverted()
        (xd0, yd0) = inv.transform((px0, py0))
        (xd1, yd1) = inv.transform((ev.x, ev.y))
        ax.set_xlim(lx0 + xd0 - xd1, lx1 + xd0 - xd1)
        ax.set_ylim(ly0 + yd0 - yd1, ly1 + yd0 - yd1)
        self._notify()

    def _on_release(self, ev):
        if self._region is not None:
            return self._on_region_release(ev)
        if self._zone_drag is not None:
            artist, _px0, _py0, moved, _ax = self._zone_drag
            gid = artist.get_gid() or ""
            if gid.startswith("zone:"):
                zone_id = gid.split(":", 1)[1]
                self._zone_label_positions[zone_id] = tuple(
                    float(v) for v in artist.get_position())
                if not moved and self.on_zone_pick is not None:
                    self.on_zone_pick(zone_id)
            self._zone_drag = None
            self._grab(False)
            self.draw_idle()
            return None
        if self._pan is not None:
            self._pan = None
            self._grab(False)
        return None

    def _grab(self, on: bool) -> None:        # pragma: no cover (cursor)
        try:
            from PySide6.QtCore import Qt
            self.setCursor(Qt.CursorShape.ClosedHandCursor if on
                           else Qt.CursorShape.ArrowCursor)
        except Exception:
            pass                              # pure-Agg host / no Qt


def make_map_canvas(parent=None, osm_fetch=None):
    """Return the interactive map tab widget (map + switch visibility panel).

    Switch visibility controls are per physical GIS switch ID.  Hiding a
    switch affects rendering only; the network graph, zone model and
    engineering calculations are never mutated.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction, QIcon, QStandardItem, QStandardItemModel
    from PySide6.QtWidgets import (QCheckBox, QComboBox, QGroupBox,
                                   QHBoxLayout, QLabel, QListWidget,
                                   QListWidgetItem, QPushButton, QSizePolicy,
                                   QVBoxLayout, QWidget, QToolButton, QMenu,
                                   QTreeWidget, QTreeWidgetItem, QFileDialog,
                                   QSplitter, QMessageBox, QScrollArea)
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure

    if osm_fetch is None:
        def osm_fetch(x0, x1, y0, y1, crs):
            from ..osm_tiles import fetch_bbox_background
            return fetch_bbox_background(x0, x1, y0, y1, crs=crs)

    class MapCanvas(MapCanvasMixin, FigureCanvasQTAgg):
        def __init__(self, parent_=None):
            self.fig = Figure(figsize=(13, 8))
            super().__init__(self.fig)
            self.setParent(parent_)
            self.setSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Expanding)
            self._init_state()
            self.connect_events()
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.customContextMenuRequested.connect(self._show_map_context_menu)

        def _show_map_context_menu(self, pos):
            menu = QMenu(self)
            act = menu.addAction("ذخیره تصویر نقشه…")
            chosen = menu.exec(self.mapToGlobal(pos))
            if chosen is act:
                path, _ = QFileDialog.getSaveFileName(
                    self, "ذخیره تصویر نقشه", "SwitchLoc_Map.png",
                    "PNG (*.png);;JPEG (*.jpg *.jpeg);;PDF (*.pdf);;SVG (*.svg)")
                if path:
                    try:
                        self.fig.savefig(path, dpi=300, bbox_inches="tight",
                                         facecolor="white")
                    except Exception as exc:
                        from PySide6.QtWidgets import QMessageBox
                        QMessageBox.warning(self, "ذخیره نقشه", str(exc))

    class MapTab(QWidget):
        """Map tab with per-switch visibility and zone selection/highlight."""
        def __init__(self, parent_=None):
            super().__init__(parent_)
            self._renderer = None
            self._title = ""
            self._proposed = None
            self._manual = None
            self._highlight = None
            self._crs = ""
            self._zone_load_kw = {}
            self._zone_up_mwh = {}
            self._zone_outage_hours = {}
            self._selected_zone = None
            self._manual_tie_pairs = []
            self._hidden_switch_ids: set[str] = set()
            # انتخاب صریح کاربر (برای اینکه پیش‌فرض «فیوزها پنهان» انتخاب
            # دستی او را در بازسازی فهرست از بین نبرد)
            self._switch_user_shown: set[str] = set()
            self._switch_user_hidden: set[str] = set()
            # لایهٔ خاموشی‌های دارای مختصات (درخواست کاربر)
            self._outage_points: list = []
            self._hidden_outage_ids: set[str] = set()
            self._opt_sec_nodes: list = []
            self.on_outages_changed = None
            self.on_style_request = None
            self.on_zone_selected = None
            self.on_feeders_changed = None
            self.on_clear_study = None
            self._osm_img = None
            self._osm_extent = None
            self._osm_note = ""
            self._osm_tried = False
            self.canvas = MapCanvas()
            self.canvas.on_view_changed = self._set_zoom_label
            self.canvas.on_zone_pick = self._on_zone_picked

            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            root = QHBoxLayout(self)
            root.setContentsMargins(4, 4, 4, 4)
            root.setSpacing(6)

            # Individual switches: checkbox list, scrollable for large feeders.
            switch_box = QGroupBox("Switch visibility — دسته‌بندی نوع کلید")
            switch_box.setMinimumWidth(220)
            switch_box.setMaximumWidth(340)
            sv = QVBoxLayout(switch_box)
            self.switch_count = QLabel("0 switches")
            sv.addWidget(self.switch_count)
            sbtn = QHBoxLayout()
            self.btn_switch_all = QPushButton("Show all")
            self.btn_switch_none = QPushButton("Hide all")
            self.btn_switch_all.clicked.connect(lambda: self._set_all_switches(True))
            self.btn_switch_none.clicked.connect(lambda: self._set_all_switches(False))
            sbtn.addWidget(self.btn_switch_all)
            sbtn.addWidget(self.btn_switch_none)
            sv.addLayout(sbtn)
            self.switch_list = QTreeWidget()
            self.switch_list.setHeaderHidden(True)
            self.switch_list.setToolTip(
                "با برداشتن تیک، فقط نماد همان کلید از نقشه حذف می‌شود؛ "
                "داده و محاسبات شبکه بدون تغییر باقی می‌ماند.")
            self.switch_list.itemChanged.connect(self._switch_item_changed)
            sv.addWidget(self.switch_list, 1)
            self.switch_panel = switch_box
            self.btn_switch_panel = QToolButton()
            self.btn_switch_panel.setText("Hide panel")
            self.btn_switch_panel.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            self.btn_switch_panel.clicked.connect(self._toggle_switch_panel)
            left_col_holder = QWidget()
            left_col = QVBoxLayout(left_col_holder)
            left_col.setContentsMargins(0, 0, 0, 0)
            left_col.setSpacing(4)
            # پنل‌ها در یک QSplitter عمودی می‌آیند تا مرزشان قابل جابه‌جایی باشد
            self.left_split = QSplitter(Qt.Orientation.Vertical)
            self.left_split.setChildrenCollapsible(True)
            self.left_split.addWidget(switch_box)

            # --- لایهٔ خاموشی‌های دارای مختصات --------------------------
            outage_box = QGroupBox("لایهٔ خاموشی‌ها — دارای مختصات")
            outage_box.setMinimumWidth(220)
            outage_box.setMaximumWidth(340)
            ov = QVBoxLayout(outage_box)
            self.chk_outages = QCheckBox("نمایش خاموشی‌ها روی نقشه")
            self.chk_outages.setToolTip(
                "روشن/خاموش کردن کل لایهٔ خاموشی‌های دارای مختصات؛ "
                "هر رکورد هم به‌صورت جداگانه قابل روشن/خاموش است.")
            self.chk_outages.toggled.connect(self._on_outages_master_toggle)
            ov.addWidget(self.chk_outages)
            self.outage_count = QLabel("0 خاموشی دارای مختصات")
            ov.addWidget(self.outage_count)
            obtn = QHBoxLayout()
            self.btn_outage_all = QPushButton("نمایش همه")
            self.btn_outage_none = QPushButton("پنهان کردن همه")
            self.btn_outage_all.clicked.connect(lambda: self._set_all_outages(True))
            self.btn_outage_none.clicked.connect(lambda: self._set_all_outages(False))
            obtn.addWidget(self.btn_outage_all)
            obtn.addWidget(self.btn_outage_none)
            ov.addLayout(obtn)
            self.btn_outage_rank = QPushButton("رتبه‌بندی مکان‌های خاموشی")
            self.btn_outage_rank.setToolTip(
                "جدول مکان‌های خاموشی بر اساس تعداد تکرار (درخواست کاربر)")
            self.btn_outage_rank.clicked.connect(self.show_outage_ranking)
            ov.addWidget(self.btn_outage_rank)
            self.outage_list = QTreeWidget()
            self.outage_list.setHeaderHidden(True)
            self.outage_list.setToolTip(
                "هر ردیف یک رخداد خاموشی است؛ برداشتن تیک فقط نمایش همان "
                "رخداد را حذف می‌کند و در تنظیمات نقشه ذخیره می‌شود.")
            self.outage_list.itemChanged.connect(self._outage_item_changed)
            ov.addWidget(self.outage_list, 1)
            self.left_split.addWidget(outage_box)
            self.left_split.setSizes([320, 280])
            left_col.addWidget(self.left_split, 1)
            self.outage_panel = outage_box
            self.layer_panel = left_col_holder

            map_pane = QWidget()
            lay = QVBoxLayout(map_pane)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            tools = QWidget()
            tools.setObjectName("MapTools")
            tools.setStyleSheet("QWidget#MapTools { background: #16324F; } "
                                "QWidget#MapTools QLabel, QWidget#MapTools QCheckBox { color: #C8D6E5; }")
            strip = QVBoxLayout(tools)
            strip.setContentsMargins(8, 8, 8, 8)
            strip.setSpacing(6)
            strip.addWidget(self.btn_switch_panel)
            strip.addWidget(QLabel("Feeder:"))
            self.feeder = QComboBox()
            self.feeder.setMinimumWidth(150)
            self.feeder.setToolTip("برای نمایش هم‌زمان یک یا چند فیدر، تیک فیدرها را فعال کنید")
            self._feeder_model = QStandardItemModel(self.feeder)
            self.feeder.setModel(self._feeder_model)
            # Stable empty-state entry: available immediately when the map
            # tab is created, before any network/renderer has been loaded.
            # It is replaced by real feeder rows in show_network().
            empty_feeder = QStandardItem("All feeders")
            empty_feeder.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
            empty_feeder.setData(None, Qt.ItemDataRole.UserRole)
            empty_feeder.setCheckState(Qt.CheckState.Checked)
            self._feeder_model.appendRow(empty_feeder)
            self._feeder_model.itemChanged.connect(self._on_feeder_item_changed)
            # QComboBox does not toggle checkable QStandardItems consistently
            # across Qt styles when clicked. Toggle explicitly on popup press.
            self.feeder.view().pressed.connect(self._toggle_feeder_index)
            self.feeder.setMinimumWidth(150)
            self.feeder.setMaximumWidth(150)
            strip.addWidget(self.feeder)
            strip.addWidget(QLabel("Zone:"))
            self.zone_filter = QComboBox()
            self.zone_filter.setMinimumWidth(180)
            self.zone_filter.setMaximumWidth(180)
            self.zone_filter.addItem("All zones", None)
            self.zone_filter.currentIndexChanged.connect(self._on_zone_filter_changed)
            strip.addWidget(self.zone_filter)

            from .icons import icon as _map_icon
            self.btn_zoom_feeder = QPushButton("Zoom to feeder")
            self.btn_zoom_feeder.setIcon(_map_icon("crosshair", size=18))
            self.btn_zoom_feeder.setMinimumHeight(32)
            self.btn_zoom_feeder.setToolTip("Zoom to feeder")
            self.btn_zoom_feeder.setEnabled(False)
            self.btn_zoom_feeder.clicked.connect(self._zoom_to_feeder)
            strip.addWidget(self.btn_zoom_feeder)

            self.zone_labels = QCheckBox("Zone labels")
            self.zone_labels.setFixedWidth(105)
            self.zone_labels.toggled.connect(self._on_zone_labels_toggle)
            strip.addWidget(self.zone_labels)

            self.btn_style = QPushButton("Map style…")
            self.btn_style.setFixedWidth(120)
            self.btn_style.clicked.connect(self._on_style_clicked)
            strip.addWidget(self.btn_style)
            self.btn_clear_study = QPushButton("پاک کردن مطالعهٔ EENS")
            self.btn_clear_study.setToolTip("پاک کردن نتیجهٔ جایابی کلید و علامت‌های آن، با تأیید کاربر")
            self.btn_clear_study.clicked.connect(
                lambda: self.on_clear_study() if self.on_clear_study else None)
            strip.addWidget(self.btn_clear_study)

            self.osm = QCheckBox("OSM background")
            self.osm.setFixedWidth(125)
            self.osm.toggled.connect(self._on_osm_toggle)
            strip.addWidget(self.osm)

            self.btn_region = QPushButton("Region zoom")
            self.btn_region.setIcon(_map_icon("search", size=18))
            self.btn_region.setMinimumHeight(32)
            self.btn_region.setToolTip("Region zoom (magnifier)")
            self.btn_region.setCheckable(True)
            self.btn_region.setToolTip(
                "ذره‌بین: با موس یک مستطیل بکشید — نمای همان محدوده را پر می‌کند")
            self.btn_region.toggled.connect(self._on_region_toggle)
            strip.addWidget(self.btn_region)

            self.btn_zoom_in = QPushButton("Zoom in")
            self.btn_zoom_out = QPushButton("Zoom out")
            self.btn_fit = QPushButton("Fit view")
            self.btn_zoom_in.clicked.connect(
                lambda: self.canvas._zoom_center(1.0 / WHEEL_STEP))
            self.btn_zoom_out.clicked.connect(
                lambda: self.canvas._zoom_center(WHEEL_STEP))
            self.btn_fit.clicked.connect(self.canvas.fit_view)
            for b, ico, tip in ((self.btn_zoom_in, "zoom-in", "Zoom in"),
                                (self.btn_zoom_out, "zoom-out", "Zoom out"),
                                (self.btn_fit, "maximize", "Fit view")):
                b.setIcon(_map_icon(ico, size=18)); b.setToolTip(tip)
                b.setMinimumHeight(32); strip.addWidget(b)
            self.zoom_label = QLabel("Zoom: 0 % (1×)")
            self.zoom_label.setMinimumWidth(120)
            self.zoom_label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            strip.addWidget(self.zoom_label)

            self.hint_label = QLabel(
                "برای جابه‌جایی کادر توضیح زون، آن را با ماوس بکشید؛ خط راهنما به محدوده زون متصل می‌ماند.")
            self.hint_label.setWordWrap(True)
            self.hint_label.setStyleSheet("color:#b26a00;")
            self.zone_info_label = QLabel(
                "برای مشاهده بار و محدوده، روی لیبل یک زون کلیک کنید.")
            self.zone_info_label.setWordWrap(True)
            self.zone_info_label.setStyleSheet(
                "padding:3px 6px; color:#37474f; background:#eceff1;")
            strip.addWidget(self.hint_label)
            strip.addWidget(self.zone_info_label)
            strip.addStretch(1)
            tool_scroll = QScrollArea()
            tool_scroll.setWidgetResizable(True)
            tool_scroll.setWidget(tools)
            tool_scroll.setFixedWidth(205)
            root.addWidget(tool_scroll, 0)
            root.addWidget(left_col_holder, 0)
            lay.addWidget(self.canvas, 1)
            root.addWidget(map_pane, 1)

        def _toggle_switch_panel(self):
            visible = not self.layer_panel.isHidden()
            self.layer_panel.setVisible(not visible)
            self.btn_switch_panel.setText("Show panel" if visible else "Hide panel")

        def show_network(self, renderer: NetworkMapRenderer,
                         title: str = "", proposed_nodes=None,
                         crs: str = "", manual_nodes=None,
                         highlight_point=None, feeder_filter=None,
                         zone_load_kw=None, zone_up_mwh=None,
                         zone_outage_hours=None, manual_tie_pairs=None,
                         outage_points=None, sectionalizer_nodes=None,
                         hidden_outage_ids=None) -> None:
            self._renderer = renderer
            if not self.zone_labels.isChecked():
                self._selected_zone = None
                self.zone_info_label.setText("برای مشاهده بار و محدوده، روی لیبل یک زون کلیک کنید.")
            self._title = title
            self._proposed = proposed_nodes
            self._manual = manual_nodes
            self._highlight = highlight_point
            self._crs = crs or ""
            self._zone_load_kw = dict(zone_load_kw or {})
            self._zone_up_mwh = dict(zone_up_mwh or {})
            self._zone_outage_hours = dict(zone_outage_hours or {})
            self._manual_tie_pairs = list(manual_tie_pairs or [])
            self._opt_sec_nodes = list(sectionalizer_nodes or [])
            if outage_points is not None:
                self.set_outage_points(outage_points)
            if hidden_outage_ids is not None:
                self._hidden_outage_ids = {str(x) for x in hidden_outage_ids}
            self._sync_outage_checks()
            keys = sorted({t.feeder_key for t in
                           getattr(renderer, "traces", []) if t.feeder_key})
            selected_before = getattr(self, "_selected_feeders", None)
            self._feeder_model.blockSignals(True)
            self._feeder_model.clear()
            from ...topology.tracing import match_feeders

            def _resolve_selection(raw) -> set:
                """انتخاب ذخیره‌شده/قبلی را به شناسه‌های فعلی نگاشت می‌کند.

                نسخه‌های قبل فیدرها را با کلید کوتاه («F1») ذخیره می‌کردند؛
                مقایسهٔ دقیق با شناسهٔ کامل («F1 - MESHKIN») مجموعهٔ خالی
                می‌ساخت و نقشه هیچ فیدری (و هیچ تجهیزی) نشان نمی‌داد.
                """
                out = set()
                for k in (raw or ()):
                    out.update(match_feeders(str(k), keys))
                return out

            if selected_before is None:
                style_visible = getattr(getattr(renderer, "style", None),
                                        "visible_feeders", None)
                if style_visible is not None:
                    self._selected_feeders = _resolve_selection(style_visible)
                    if style_visible and not self._selected_feeders:
                        # انتخاب ذخیره‌شده به هیچ فیدر فعلی نمی‌خورد →
                        # همه را نشان بده (نقشهٔ سفید راه‌حل نیست)
                        self._selected_feeders = set(keys)
                elif isinstance(feeder_filter, str) and feeder_filter:
                    resolved = _resolve_selection([feeder_filter])
                    self._selected_feeders = resolved or set(keys)
                else:
                    self._selected_feeders = set(keys)
            else:
                self._selected_feeders = _resolve_selection(selected_before)
                if selected_before and not self._selected_feeders:
                    self._selected_feeders = set(keys)
            if not keys:
                # Keep the feeder selector usable before a network is loaded
                # (and for a valid empty-graph renderer).  This is a display-
                # only sentinel: _current_feeder() deliberately ignores its
                # None UserRole so it can never become a real feeder filter.
                it = QStandardItem("All feeders")
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
                it.setData(None, Qt.ItemDataRole.UserRole)
                it.setCheckState(Qt.CheckState.Checked)
                self._feeder_model.appendRow(it)
            else:
                for k in keys:
                    it = QStandardItem(str(k))
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
                    it.setData(k, Qt.ItemDataRole.UserRole)
                    it.setCheckState(Qt.CheckState.Checked if k in self._selected_feeders else Qt.CheckState.Unchecked)
                    self._feeder_model.appendRow(it)
            self._feeder_model.blockSignals(False)
            self._update_feeder_caption()
            self._rebuild_zone_filter()
            self.btn_zoom_feeder.setEnabled(bool(keys))

            # Build a stable, per-switch checklist. Preserve user visibility
            # choices for IDs that remain in the current project.
            switch_rows = []
            for node, ids in sorted(renderer.graph.switch_ids_at.items()):
                for sid in sorted(ids):
                    sw = renderer.switches.get(sid)
                    if sw is None:
                        continue
                    from ..map_renderer import switch_display_code
                    from ...topology.tracing import feeder_key
                    fk = feeder_key(sw.feeder_name) or "?"
                    subtype = switch_display_code(sw)
                    title_part = (sw.local_name or sid[:12]).strip()
                    switch_rows.append((sid, f"{fk} | {subtype} | {title_part}"))
            valid_ids = {sid for sid, _ in switch_rows}
            self._hidden_switch_ids.intersection_update(valid_ids)
            self._switch_user_shown &= valid_ids
            self._switch_user_hidden &= valid_ids
            # پیش‌فرض: فیوز کات‌اوت‌ها نمایش داده نمی‌شوند (درخواست کاربر)؛
            # انتخاب صریح کاربر (روشن‌کردن از همین فهرست) بر پیش‌فرض مقدم است.
            style_now = getattr(renderer, "style", None)
            fuses_default_off = not bool(getattr(style_now, "show_fuse_cutouts",
                                                 False))
            fuse_ids = {sid for (sid, label) in switch_rows
                        if label.split(" | ")[1:2] == ["FCT"]} \
                if fuses_default_off else set()
            self._hidden_switch_ids = (
                (self._hidden_switch_ids - self._switch_user_shown)
                | (fuse_ids - self._switch_user_shown)
                | self._switch_user_hidden)
            self.switch_list.blockSignals(True)
            self.switch_list.clear()
            groups = {}
            for sid, label in switch_rows:
                parts = label.split(" | ", 2)
                category = parts[1] if len(parts) > 1 else "نامشخص"
                if category not in groups:
                    parent_item = QTreeWidgetItem([category])
                    parent_item.setFlags(parent_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
                    parent_item.setCheckState(0, Qt.CheckState.Checked)
                    self.switch_list.addTopLevelItem(parent_item)
                    groups[category] = parent_item
                item = QTreeWidgetItem([label])
                item.setData(0, Qt.ItemDataRole.UserRole, sid)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Unchecked if sid in self._hidden_switch_ids else Qt.CheckState.Checked)
                groups[category].addChild(item)
            self.switch_list.expandAll()
            self.switch_list.blockSignals(False)
            self.switch_count.setText(
                f"{len(switch_rows)} کلید | {len(switch_rows)-len(self._hidden_switch_ids)} قابل نمایش")

            if self._selected_zone is not None and renderer.zones is not None:
                if renderer.zones.zone_by_id(self._selected_zone) is None:
                    self._selected_zone = None
            self._osm_tried = False
            self._apply()

        def set_highlight_point(self, point) -> None:
            self._highlight = tuple(point) if point is not None else None
            self._apply()

        def _toggle_feeder_index(self, index) -> None:
            item = self._feeder_model.itemFromIndex(index)
            if item is None or item.data(Qt.ItemDataRole.UserRole) is None:
                return
            item.setCheckState(Qt.CheckState.Unchecked
                               if item.checkState() == Qt.CheckState.Checked
                               else Qt.CheckState.Checked)

        def _current_feeder(self):
            selected = set()
            for i in range(self._feeder_model.rowCount()):
                it = self._feeder_model.item(i)
                feeder_id = it.data(Qt.ItemDataRole.UserRole)
                if it.checkState() == Qt.CheckState.Checked and feeder_id is not None:
                    selected.add(str(feeder_id))
            return selected or set()

        def _on_feeder_item_changed(self, _item):
            self._update_feeder_caption()
            self._rebuild_zone_filter()
            if self._renderer is not None and self._renderer.style is not None:
                self._renderer.style.visible_feeders = sorted(self._current_feeder())
            if self.on_feeders_changed is not None:
                self.on_feeders_changed()
            self._apply()

        def _rebuild_zone_filter(self):
            current = self.zone_filter.currentData() if hasattr(self, "zone_filter") else None
            self.zone_filter.blockSignals(True)
            self.zone_filter.clear()
            self.zone_filter.addItem("All zones", None)
            if self._renderer is not None and self._renderer.zones is not None:
                selected = self._current_feeder()
                for z in self._renderer.zones.zones:
                    if z.feeder not in selected:
                        continue
                    self.zone_filter.addItem(
                        f"{z.feeder or 'Island'} / Z{z.zone_no}", z.id)
            ix = self.zone_filter.findData(current)
            self.zone_filter.setCurrentIndex(ix if ix >= 0 else 0)
            self.zone_filter.blockSignals(False)
            self._selected_zone = self.zone_filter.currentData()

        def _on_zone_filter_changed(self, _index):
            self._selected_zone = self.zone_filter.currentData()
            self._apply()

        def _update_feeder_caption(self):
            selected = self._current_feeder() if hasattr(self, "_feeder_model") else set()
            total = self._feeder_model.rowCount() if hasattr(self, "_feeder_model") else 0
            self.feeder.setToolTip("فیدرهای انتخاب‌شده: " + (", ".join(sorted(selected)) if selected else "هیچ‌کدام"))
            self.feeder.setEditable(True)
            self.feeder.lineEdit().setReadOnly(True)
            self.feeder.setEditText(f"فیدرها: {len(selected)} / {total}")

        def _apply(self) -> None:
            if self._renderer is None:
                return
            osm_img = osm_ext = None
            note = ""
            if self.osm.isChecked():
                if not self._osm_tried:
                    self._fetch_osm()
                if self._osm_img is not None:
                    osm_img, osm_ext, note = self._osm_img, self._osm_extent, self._osm_note
            self.canvas.show_network(
                self._renderer, title=self._title,
                feeder_key=self._current_feeder(),
                zone_labels=self.zone_labels.isChecked(),
                proposed_nodes=self._proposed,
                rotate=False, osm_image=osm_img, osm_extent=osm_ext,
                osm_note=note, manual_nodes=self._manual,
                highlight_point=self._highlight,
                zone_load_kw=self._zone_load_kw,
                selected_zone=self._selected_zone,
                hidden_switch_ids=self._hidden_switch_ids,
                zone_up_mwh=self._zone_up_mwh,
                zone_outage_hours=self._zone_outage_hours,
                manual_tie_pairs=self._manual_tie_pairs,
                outage_points=self._outage_points,
                sectionalizer_nodes=self._opt_sec_nodes,
                hidden_outage_ids=self._hidden_outage_ids)

        # ------------------------------------------------------------------
        # لایهٔ خاموشی‌های دارای مختصات
        # ------------------------------------------------------------------
        def set_outage_points(self, points) -> None:
            """رخدادهای دارای مختصات را در لایهٔ نقشه می‌گذارد.

            ``points``: فهرست دیکشنری با کلیدهای
            ``id``, ``x``, ``y``, ``label``, ``status``, ``feeder``,
            ``zone_x``, ``zone_y`` (همه در CRS پروژه).  فهرست خالی
            یعنی هیچ رخداد دارای مختصاتی وجود ندارد و پنل صریحاً همین
            را می‌گوید.
            """
            self._outage_points = [dict(p) for p in (points or [])]
            valid = {str(p.get("id", "")) for p in self._outage_points}
            self._hidden_outage_ids.intersection_update(valid)
            self._rebuild_outage_list()
            self._apply()

        def _rebuild_outage_list(self) -> None:
            self.outage_list.blockSignals(True)
            self.outage_list.clear()
            groups = {}
            for pt in self._outage_points:
                fk = str(pt.get("feeder", "") or "بدون فیدر")
                if fk not in groups:
                    top = QTreeWidgetItem([fk])
                    top.setFlags(top.flags() | Qt.ItemFlag.ItemIsUserCheckable
                                 | Qt.ItemFlag.ItemIsAutoTristate)
                    top.setCheckState(0, Qt.CheckState.Checked)
                    self.outage_list.addTopLevelItem(top)
                    groups[fk] = top
                pid = str(pt.get("id", ""))
                status_fa = {"confirmed": "تأیید مهندسی",
                             "rejected": "رد شده",
                             "pending": "در انتظار"}.get(
                                 str(pt.get("status", "")), "—")
                item = QTreeWidgetItem([f"{pt.get('label', pid)} — {status_fa}"])
                item.setData(0, Qt.ItemDataRole.UserRole, pid)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    0, Qt.CheckState.Unchecked if pid in self._hidden_outage_ids
                    else Qt.CheckState.Checked)
                groups[fk].addChild(item)
            self.outage_list.expandAll()
            self.outage_list.blockSignals(False)
            total = len(self._outage_points)
            self.outage_count.setText(
                f"{total} خاموشی دارای مختصات | "
                f"{total - len(self._hidden_outage_ids)} قابل نمایش")
            visible = (self._renderer is not None
                       and bool(getattr(self._renderer.style, "show_outages", True)))
            self.chk_outages.blockSignals(True)
            self.chk_outages.setChecked(visible)
            self.chk_outages.blockSignals(False)

        def _sync_outage_checks(self) -> None:
            self._rebuild_outage_list()

        def _outage_item_changed(self, item, column=0) -> None:
            pid = item.data(0, Qt.ItemDataRole.UserRole)
            if pid:
                if item.checkState(0) == Qt.CheckState.Checked:
                    self._hidden_outage_ids.discard(str(pid))
                else:
                    self._hidden_outage_ids.add(str(pid))
            else:
                # حالت «نیمه‌انتخاب» خودکارِ والد (AutoTristate) نباید به
                # فرزندان تحمیل شود؛ وگرنه خاموش‌کردن یک رخداد کل فیدر را
                # پنهان می‌کند.
                state = item.checkState(0)
                if state == Qt.CheckState.PartiallyChecked:
                    return
                for i in range(item.childCount()):
                    item.child(i).setCheckState(0, state)
            self._save_hidden_outages()
            total = len(self._outage_points)
            self.outage_count.setText(
                f"{total} خاموشی دارای مختصات | "
                f"{total - len(self._hidden_outage_ids)} قابل نمایش")
            self._apply()

        def _save_hidden_outages(self) -> None:
            if self._renderer is not None and \
                    self._renderer.style is not None:
                self._renderer.style.hidden_outage_ids = \
                    sorted(self._hidden_outage_ids)
            if self.on_outages_changed is not None:
                self.on_outages_changed()

        def show_outage_ranking(self) -> None:
            """جدول رتبه‌بندی مکان‌های خاموشی (درخواست کاربر — بند ۷)."""
            from .outage_ranking_dialog import show_outage_ranking_dialog
            points = [p for p in (self._outage_points or [])
                      if str(p.get("id", "")) not in self._hidden_outage_ids]
            if not points:
                QMessageBox.information(
                    self, "رتبه‌بندی مکان‌های خاموشی",
                    "هیچ خاموشی دارای مختصات و قابل نمایشی وجود ندارد.")
                return

            def _focus(x: float, y: float, row: dict) -> None:
                try:
                    self.set_highlight_point((x, y))
                except Exception:                   # noqa: BLE001
                    pass

            show_outage_ranking_dialog(self, points, on_focus=_focus)

        def _on_outages_master_toggle(self, on: bool) -> None:
            if self._renderer is not None and self._renderer.style is not None:
                self._renderer.style.show_outages = bool(on)
            self._save_hidden_outages()
            self._apply()

        def _set_all_outages(self, visible: bool) -> None:
            self.outage_list.blockSignals(True)
            hidden = set()
            for i in range(self.outage_list.topLevelItemCount()):
                parent = self.outage_list.topLevelItem(i)
                parent.setCheckState(0, Qt.CheckState.Checked if visible
                                     else Qt.CheckState.Unchecked)
                for j in range(parent.childCount()):
                    child = parent.child(j)
                    child.setCheckState(0, Qt.CheckState.Checked if visible
                                        else Qt.CheckState.Unchecked)
                    if not visible:
                        pid = child.data(0, Qt.ItemDataRole.UserRole)
                        if pid:
                            hidden.add(str(pid))
            self._hidden_outage_ids = hidden
            self.outage_list.blockSignals(False)
            if not visible:
                self.chk_outages.setChecked(True)   # پنهان‌کردن رکوردها، نه لایه
            self._save_hidden_outages()
            self._rebuild_outage_list()
            self._apply()

        def _switch_item_changed(self, item, column=0) -> None:
            sid = item.data(0, Qt.ItemDataRole.UserRole)
            if sid:
                if item.checkState(0) == Qt.CheckState.Checked:
                    self._hidden_switch_ids.discard(sid)
                    self._switch_user_shown.add(sid)
                    self._switch_user_hidden.discard(sid)
                else:
                    self._hidden_switch_ids.add(sid)
                    self._switch_user_hidden.add(sid)
                    self._switch_user_shown.discard(sid)
            else:
                # parent category: apply its state to all children — ولی نه
                # حالت نیمه‌انتخاب خودکار (AutoTristate) که Qt هنگام
                # تغییر یک فرزند می‌سازد
                state = item.checkState(0)
                if state == Qt.CheckState.PartiallyChecked:
                    return
                for i in range(item.childCount()):
                    child = item.child(i)
                    child.setCheckState(0, state)
            total = sum(self.switch_list.topLevelItem(i).childCount()
                        for i in range(self.switch_list.topLevelItemCount()))
            self.switch_count.setText(f"{total} کلید | {total-len(self._hidden_switch_ids)} قابل نمایش")
            self._apply()

        def _set_all_switches(self, visible: bool) -> None:
            self.switch_list.blockSignals(True)
            hidden = set()
            total = 0
            for i in range(self.switch_list.topLevelItemCount()):
                parent_item = self.switch_list.topLevelItem(i)
                parent_item.setCheckState(0, Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked)
                for j in range(parent_item.childCount()):
                    child = parent_item.child(j); total += 1
                    child.setCheckState(0, Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked)
                    if not visible: hidden.add(child.data(0, Qt.ItemDataRole.UserRole))
            self._hidden_switch_ids = hidden
            self._switch_user_shown = set() if not visible else {
                child.data(0, Qt.ItemDataRole.UserRole)
                for i in range(self.switch_list.topLevelItemCount())
                for child in (self.switch_list.topLevelItem(i).child(j)
                              for j in range(self.switch_list.topLevelItem(i).childCount()))}
            self._switch_user_hidden = set() if visible else set(hidden)
            self.switch_list.blockSignals(False)
            self.switch_count.setText(f"{total} کلید | {total-len(hidden)} قابل نمایش")
            self._apply()

        def _on_zone_picked(self, zone_id: str) -> None:
            if self._renderer is None or self._renderer.zones is None:
                return
            zone = self._renderer.zones.zone_by_id(zone_id)
            if zone is None:
                return
            self._selected_zone = zone_id
            ix = self.zone_filter.findData(zone_id)
            if ix >= 0:
                self.zone_filter.blockSignals(True)
                self.zone_filter.setCurrentIndex(ix)
                self.zone_filter.blockSignals(False)
            load = self._zone_load_kw.get(zone_id)
            load_txt = f"{load:,.1f} kW" if load is not None else "بار محاسبه نشده"
            up = self._zone_up_mwh.get(zone_id)
            up_txt = f"{up:,.3f} MWh/سال" if up is not None else "محاسبه نشده"
            outage_h = self._zone_outage_hours.get(zone_id)
            time_txt = f"{outage_h:,.2f} ساعت/سال" if outage_h is not None else "نامشخص"
            self.zone_info_label.setText(
                f"زون انتخاب‌شده: {zone.feeder or 'جزیره'} / Z{zone.zone_no}  |  "
                f"بار: {load_txt}  |  زمان خاموشی: {time_txt}  |  U×P: {up_txt}  |  "
                f"ترانس: {len(zone.transformer_ids)}  |  نقاط بار: {len(zone.load_ids)}  |  "
                f"طول شبکه: {zone.length_m/1000.0:.2f} km")
            self._apply()
            if self.on_zone_selected is not None:
                self.on_zone_selected(zone)

        def _on_zone_labels_toggle(self, enabled: bool) -> None:
            if not enabled:
                self._selected_zone = None
                self.zone_info_label.setText("برای مشاهده بار و محدوده، روی لیبل یک زون کلیک کنید.")
            self._apply()

        def _on_style_clicked(self) -> None:
            if self.on_style_request is not None:
                self.on_style_request()

        def _fetch_osm(self) -> None:
            self._osm_tried = True
            self._osm_img = self._osm_extent = None
            self._osm_note = ""
            try:
                xs = [nd.coord[0] for nd in self._renderer.graph.nodes.values()
                      if nd.coord is not None]
                ys = [nd.coord[1] for nd in self._renderer.graph.nodes.values()
                      if nd.coord is not None]
                if not xs:
                    raise RuntimeError("no coordinates in the project")
                if not self._crs:
                    raise RuntimeError("the project declares no CRS, so tiles cannot be placed")
                pad_x = (max(xs) - min(xs)) * 0.08 + 100.0
                pad_y = (max(ys) - min(ys)) * 0.08 + 100.0
                bg = osm_fetch(min(xs)-pad_x, max(xs)+pad_x,
                               min(ys)-pad_y, max(ys)+pad_y, self._crs)
                self._osm_img, self._osm_extent, self._osm_note = bg.image, bg.extent, bg.note
                self.hint_label.setText("")
            except Exception as exc:  # noqa: BLE001
                self.hint_label.setText(
                    "OSM background unavailable "
                    f"({type(exc).__name__}: {exc}) — the network map continues without tiles.")

        def _on_osm_toggle(self, on: bool) -> None:
            self._apply()

        def _on_region_toggle(self, on: bool) -> None:
            self.canvas.set_region_mode(bool(on))

        def _zoom_to_feeder(self) -> None:
            keys = self._current_feeder()
            ax = self.canvas.main_ax()
            if not keys or ax is None or self._renderer is None:
                return
            pts = []
            for trace in self._renderer.traces:
                if trace.feeder_key not in keys:
                    continue
                for eid in trace.edges:
                    e = self._renderer.graph.edges[eid]
                    a = self._renderer.graph.nodes[e.a].coord
                    b = self._renderer.graph.nodes[e.b].coord
                    if a is not None and b is not None:
                        pts.extend((self._renderer._c(a), self._renderer._c(b)))
            if not pts:
                return
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            pad_x = (max(xs)-min(xs))*0.05 + 50.0
            pad_y = (max(ys)-min(ys))*0.05 + 50.0
            self.canvas.zoom_to_region(ax, min(xs)-pad_x, min(ys)-pad_y,
                                       max(xs)+pad_x, max(ys)+pad_y)

        def _set_zoom_label(self, pct) -> None:
            level = self.canvas.zoom_level_pct()
            if pct is None or level is None:
                self.zoom_label.setText("Zoom: —")
            else:
                mult = pct / 100.0
                self.zoom_label.setText(f"Zoom: {level:.0f} % ({mult:,.0f}×)")
                self.zoom_label.setToolTip(
                    "Zoom level 0-100 %: 0 % = full view, 100 % = deepest zoom "
                    f"({ZOOM_IN:,.0f}×). The (N×) value is absolute magnification.")

    return MapTab(parent)

