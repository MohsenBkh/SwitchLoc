"""Shared helpers for keeping template-specific report values coherent."""
from __future__ import annotations


FEEDER_VALUE_KEYS = frozenset({
    "جریان فیدر", "جریان بار", "P_load (kW)/1000", "P_load (kW)",
    "Q_load (kW)/1000", "Q_load (kW)", "طول فیدر",
    "مقدار EENS پایه", "EENS پایه", "مقدار EENS نهایی", "EENS نهایی",
    "درصد کاهش", "درصد کاهش EENS", "عدد نرخ خرابی", "زمان تعمیر",
    "تعداد کلید", "موقعیت نصب", "موقعیت", "مختصات کلیدی پیشنهادی",
})


def refresh_feeder_template_caches(
    generated: dict[str, object],
    defaults: dict[str, object],
    template_caches: dict[str, dict[str, str]],
    keys: set[str] | frozenset[str] = FEEDER_VALUE_KEYS,
) -> dict[str, str]:
    """Apply newly generated feeder-dependent values to defaults and caches.

    Values tied to the selected technical feeder must be refreshed in every
    template family: otherwise switching templates can resurrect data from the
    previously selected feeder. Unrelated/user-entered values are untouched.
    The returned mapping contains the fields that should be reflected in the
    currently visible editor controls.
    """
    refreshed: dict[str, str] = {}
    for key in keys:
        if key not in generated:
            continue
        value = str(generated[key])
        defaults[key] = value
        refreshed[key] = value
        for cache in template_caches.values():
            cache[key] = value
    return refreshed
