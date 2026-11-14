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


def indices_figure(rows: list, path: str,
                   title: str = "Feeder indices — indicators of the study"
                   ) -> str | None:
    """شکل ۲×۳ از شاخص‌های فیدرها؛ اگر داده نبود ``None``."""
    if not rows:
        return None
    import matplotlib.pyplot as plt

    keys = [str(r.get("feeder_key") or "?") for r in rows]
    fig, axs = plt.subplots(2, 3, figsize=(15, 8.5))
    flat = list(axs.ravel())
    try:                                   # فونت مشترک پروژه (اختیاری)
        from .workbook import _BODY_FONT   # noqa: F401
    except ImportError:                    # pragma: no cover
        pass
    for ax, (key, label, _unit, scale) in zip(flat, PANELS, strict=False):
        values = []
        for r in rows:
            v = r.get(key)
            values.append(None if v is None else float(v) * scale)
        present = [v for v in values if v is not None]
        if not present:
            ax.text(0.5, 0.5, "no data", ha="center", va="center",
                    fontsize=9, color="#8a939e")
            ax.set_axis_off()
            ax.set_title(label, fontsize=9)
            continue
        xs = range(len(keys))
        bars = ax.bar(xs, [(v or 0.0) for v in values],
                      color=["#1f77b4" if v is not None else "#d9dde2"
                             for v in values])
        ax.set_title(label, fontsize=10)
        ax.set_xticks(list(xs))
        ax.set_xticklabels(keys, rotation=35, ha="right", fontsize=6.5)
        ax.tick_params(axis="y", labelsize=7)
        ax.grid(axis="y", alpha=0.25)
        ax.set_axisbelow(True)
        top = max(present) if present else 0.0
        for b, v in zip(bars, values, strict=False):
            if v is None:
                continue
            ax.annotate(f"{v:,.1f}" if v < 100 else f"{v:,.0f}",
                        (b.get_x() + b.get_width() / 2, b.get_height()),
                        ha="center", va="bottom", fontsize=6)
        if top > 0:
            ax.set_ylim(0, top * 1.18)
    fig.suptitle(title, fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return str(out)
