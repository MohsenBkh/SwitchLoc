# -*- coding: utf-8 -*-
"""تصاویر نموداری گزارش (Word/PDF) — همهٔ شاخص‌های ارزیابی فیدرها.

برچسب فیدرها لاتین است (مثل «F1 - MESHKIN») و عنوان‌ها انگلیسی/کوتاه،
چون Matplotlib متن فارسی را بدون reshaper/bidi برعکس و جدا رسم می‌کند.
همین نمودارها در داشبورد به‌صورت تعاملی و فارسی (QPainter) و در Excel
به‌صورت نمودار بومی Excel هم موجودند.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")

#: (کلید ردیف، عنوان انگلیسی پنل، واحد، مقیاس)
PANELS = (
    ("saidi", "SAIDI (min/yr)", "min/yr", 1.0),
    ("saifi", "SAIFI (int/yr)", "int/yr", 1.0),
    ("ens_per_year_kwh", "ENS (kWh/yr)", "kWh/yr", 1.0),
    ("lambda_per_year", "λ (1/yr)", "1/yr", 1.0),
    ("r_minutes", "r (min)", "min", 1.0),
    ("u_hours", "U = λr/60 (h/yr)", "h/yr", 1.0),
)


# رنگ‌های متمایز برای هر فیدر (تا 20 فیدر بدون تکرار)
_FEEDER_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
    "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5",
]


def _feeder_palette_for_keys(keys: list[str]) -> dict[str, str]:
    """رنگ ثابت برای هر فیدر — از map_style اگر موجود بود."""
    try:
        from ..ui.map_style import auto_palette
        return auto_palette(feeders=keys)
    except Exception:
        pass
    palette: dict[str, str] = {}
    for i, k in enumerate(keys):
        palette[k] = _FEEDER_PALETTE[i % len(_FEEDER_PALETTE)]
    return palette


def indices_figure(rows: list, path: str,
                   title: str = "Feeder indices — indicators of the study",
                   selected_feeders: list[str] | None = None,
                   ) -> str | None:
    """شکل ۳×۲ از شاخص‌های فیدرها؛ اگر داده نبود ``None``.

    فقط فیدرهای انتخاب‌شدهٔ مطالعه رسم می‌شوند (حذف نشده‌ها).
    رنگ هر فیدر در همهٔ پنل‌ها یکسان است و یک لجند کلی رنگ→فیدر در
    بالای شکل قرار می‌گیرد.
    """
    if not rows:
        return None
    # فیلتر به فیدرهای انتخاب‌شده (اگر داده شده)
    if selected_feeders:
        try:
            from ..topology.tracing import same_feeder
            sel = [str(s) for s in selected_feeders if str(s).strip()]
            if sel:
                filtered = []
                for r in rows:
                    fk = str(r.get("feeder_key") or "")
                    if any(same_feeder(fk, s) for s in sel):
                        filtered.append(r)
                if filtered:
                    rows = filtered
        except Exception:
            pass
    if not rows:
        return None

    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    keys = [str(r.get("feeder_key") or "?") for r in rows]
    palette = _feeder_palette_for_keys(keys)
    colors = [palette.get(k, _FEEDER_PALETTE[i % len(_FEEDER_PALETTE)])
              for i, k in enumerate(keys)]

    # ۳×۲ چیدمان با فضای بهینه
    fig, axs = plt.subplots(3, 2, figsize=(14, 11))
    flat = list(axs.ravel())
    try:
        from .workbook import _BODY_FONT  # noqa: F401
    except ImportError:  # pragma: no cover
        pass

    for ax, (key, label, _unit, scale) in zip(flat, PANELS, strict=False):
        values = []
        for r in rows:
            v = r.get(key)
            values.append(None if v is None else float(v) * scale)
        present = [v for v in values if v is not None]
        if not present:
            ax.text(0.5, 0.5, "no data", ha="center", va="center",
                    fontsize=11, color="#8a939e")
            ax.set_axis_off()
            ax.set_title(label, fontsize=12, pad=8)
            continue
        xs = range(len(keys))
        bar_colors = [colors[i] if v is not None else "#d9dde2"
                      for i, v in enumerate(values)]
        bars = ax.bar(xs, [(v or 0.0) for v in values],
                      color=bar_colors, edgecolor="white", linewidth=0.6)
        ax.set_title(label, fontsize=12, pad=6)
        ax.set_xticks(list(xs))
        ax.set_xticklabels(keys, rotation=30, ha="right", fontsize=8.5)
        ax.tick_params(axis="y", labelsize=9)
        ax.tick_params(axis="x", labelsize=8.5)
        ax.grid(axis="y", alpha=0.25)
        ax.set_axisbelow(True)
        top = max(present) if present else 0.0
        for b, v in zip(bars, values, strict=False):
            if v is None:
                continue
            txt = f"{v:,.1f}" if v < 100 else f"{v:,.0f}"
            ax.annotate(txt,
                        (b.get_x() + b.get_width() / 2, b.get_height()),
                        ha="center", va="bottom", fontsize=8, fontweight="bold",
                        color="#222",
                        xytext=(0, 2), textcoords="offset points")
        if top > 0:
            ax.set_ylim(0, top * 1.22)

    # لجند کلی رنگ→فیدر (بالای شکل، به‌جای عنوان ریز هر پنل)
    handles = [Patch(facecolor=palette.get(k, colors[i]), edgecolor="white", label=k)
               for i, k in enumerate(keys)]
    # تعداد ستون لجند بر اساس تعداد فیدرها
    ncols = min(len(keys), 4) if len(keys) > 4 else len(keys)
    fig.legend(handles=handles, loc="upper center",
               bbox_to_anchor=(0.5, 0.99), ncol=ncols,
               fontsize=9, frameon=True, fancybox=True, shadow=False,
               title="Feeders", title_fontsize=10)

    fig.suptitle(title, fontsize=13, y=0.96, fontweight="bold")
    # فضای کافی برای لجند و عنوان
    fig.tight_layout(rect=(0, 0, 1, 0.92), h_pad=1.2, w_pad=1.0)
    # اگر لجند خیلی بلند شد، کمی پایین‌تر بیاید
    try:
        fig.subplots_adjust(top=0.90, bottom=0.06, left=0.06, right=0.98)
    except Exception:
        pass
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return str(out)
