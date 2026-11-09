# -*- coding: utf-8 -*-
"""شاخص‌های پیوستگی (SAIDI / SAIFI / CAIDI / ASAI) از همان دادهٔ خاموشی.

منشأ داده همان دفتر خاموشی است (ستون‌های «مدت قطع»، «انرژی توزیع‌نشده»،
«قطع‌کننده»، «نام فیدر»). دادهٔ خاموشی ستون «تعداد مشترکین» ندارد (A-08)،
پس سهم مشترکینِ متأثر از **انرژی توزیع‌نشده** استنتاج می‌شود:

    f_i = E_i / (P_f · T_i)            (سهم بارِ قطع‌شدهٔ رخداد i از فیدر f)

که در آن E همان «انرژی توزیع‌نشده» (واحد: MWh یا kWh — خودکار تشخیص
داده می‌شود)، P بار فیدر (kW) و T مدت قطع (ساعت) است. سپس:

    SAIFI = Σ f_i / سال مواجهه      [قطع/مشترک/سال]
    SAIDI = Σ f_i · T_i / سال مواجهه [دقیقه/مشترک/سال]
    CAIDI = SAIDI / SAIFI            [دقیقه]
    ASAI  = 1 − SAIDI / 525600

سه محدودیت صریح (بدون آن‌ها عدد ساخته نمی‌شود):

* اگر بار فیدر (P) معلوم نباشد، سهم فقط برای رخدادهای «تمام‌فیدر»
  (بریکر پست فوق‌توزیع / ریکلوزر) برابر یک گرفته می‌شود و بقیه شمرده
  نمی‌شوند؛ در این حالت SAIDI **کف** (lower bound) است.
* اگر انرژی رخداد خالی یا صفر باشد، از قطع‌کننده استفاده می‌شود؛
  قطع‌کننده‌های جزئی (کات‌اوت سرخط/ترانس) بدون انرژی شمرده نمی‌شوند.
* فرض «سهم مشترکین ≈ سهم بار» است (توزیع یکنواخت بار روی مشترکین)؛
  اگر تعداد مشترکین هر فیدر معلوم باشد، همان اضافه می‌شود و فقط برای
  گزارش «مشترک-دقیقه» به‌کار می‌رود (SAIDI/SAIFI به آن نیاز ندارند).

شاخص «بدترین حالت» (worst case) هم گزارش می‌شود: هر رخداد = قطع کل فیدر.
این عدد به هیچ فرضی وابسته نیست و برای مقایسه/صحت‌سنجی می‌آید.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..topology.tracing import feeder_id

#: قطع‌کننده‌هایی که کل فیدر را بی‌برق می‌کنند
WHOLE_FEEDER_HINTS = ("بریکر", "ریکلوزر", "دیژنکتور")
#: قطع‌کننده‌های جزئی (شاخه/ترانس)
PARTIAL_HINTS = ("کات اوت", "کاتاوت", "فیوز")

MINUTES_PER_YEAR = 365 * 24 * 60


@dataclass
class FeederServiceIndices:
    """شاخص‌های یک فیدر برای پنجرهٔ مواجههٔ خودش."""
    feeder_key: str
    exposure_years: float = 0.0
    events_total: int = 0
    events_counted: int = 0          # رخداد با سهم قطعِ محاسبه‌شده
    events_skipped: int = 0          # رخداد بدون مدت/بدون سهم
    events_whole_feeder: int = 0
    saifi: float = 0.0               # قطع/مشترک/سال
    saidi: float = 0.0               # دقیقه/مشترک/سال
    caidi: float = 0.0
    asai: float = 1.0
    ens_kwh_per_year: float = 0.0
    saifi_random: float = 0.0
    saidi_random: float = 0.0
    worst_saifi: float = 0.0
    worst_saidi: float = 0.0
    customer_minutes: float | None = None
    customer_interruptions: float | None = None
    basis_counts: dict = field(default_factory=dict)
    by_device: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    @property
    def has_data(self) -> bool:
        """رخداد واقعی برای این فیدر ثبت شده است؟ (۰ ≠ «بدون داده»)"""
        return self.events_total > 0

    def as_dict(self) -> dict:
        d = asdict(self)
        d["has_data"] = self.has_data
        return d


@dataclass
class ServiceIndices:
    """مجموع سامانه + ردیف هر فیدر."""
    feeders: list = field(default_factory=list)
    saifi: float = 0.0
    saidi: float = 0.0
    caidi: float = 0.0
    asai: float = 1.0
    worst_saifi: float = 0.0
    worst_saidi: float = 0.0
    energy_unit: str = ""
    energy_unit_source: str = ""       # inferred | declared | none
    load_basis: str = ""               # feeder-load | device-only | none
    aggregation: str = ""              # load-weighted | simple-mean
    notes: list = field(default_factory=list)

    @property
    def has_result(self) -> bool:
        return any(f.events_counted for f in self.feeders)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["feeders"] = [f.as_dict() for f in self.feeders]
        d["has_result"] = self.has_result
        return d

    # ------------------------------------------------------------------
    def to_markdown(self) -> str:
        if not self.has_result:
            return ("| فیدر | SAIFI (قطع/سال) | SAIDI (دقیقه/سال) | CAIDI (دقیقه) "
                    "| ASAI |\n|---|---|---|---|---|\n"
                    "| — | — | — | — | — |\n\n> "
                    + ("؛ ".join(self.notes) if self.notes
                       else "برای محاسبهٔ SAIDI/SAIFI دادهٔ کافی نبود."))
        rows = []
        for f in self.feeders:
            if not f.has_data:
                rows.append(f"| {f.feeder_key} | — | — | — | بدون داده |")
                continue
            if not f.events_counted:
                rows.append(f"| {f.feeder_key} | — | — | — | دادهٔ ناکافی |")
                continue
            rows.append(
                f"| {f.feeder_key} | {f.saifi:.2f} | {f.saidi:,.1f} | "
                f"{f.caidi:.1f} | {f.asai * 100:.4f}% |")
        rows.append(f"| **سامانه** | **{self.saifi:.2f}** | **{self.saidi:,.1f}** "
                    f"| **{self.caidi:.1f}** | **{self.asai * 100:.4f}%** |")
        return ("| فیدر | SAIFI (قطع/سال) | SAIDI (دقیقه/سال) | CAIDI (دقیقه) "
                "| ASAI |\n|---|---|---|---|---|\n" + "\n".join(rows))


# ---------------------------------------------------------------------------
def _is_whole_feeder(device: str) -> bool:
    text = str(device or "")
    return any(h in text for h in WHOLE_FEEDER_HINTS)


def _is_partial(device: str) -> bool:
    text = str(device or "")
    return any(h in text for h in PARTIAL_HINTS)


def _fraction_of_event(rec, load_kw: float | None, unit: str
                       ) -> tuple[float | None, str]:
    """سهم بارِ قطع‌شده در یک رخداد + منشأ آن (قابل ردیابی)."""
    t_min = getattr(rec, "duration_min", None)
    energy = getattr(rec, "energy_kwh", None)
    device = getattr(rec, "device_raw", "") or ""
    if t_min is None or t_min <= 0:
        return None, "no-duration"
    if energy is not None and energy > 0 and load_kw:
        e_kwh = energy * 1000.0 if unit == "mwh" else float(energy)
        frac = e_kwh / (float(load_kw) * (t_min / 60.0))
        if frac <= 0:
            return None, "no-energy"
        if frac > 1.0:
            return 1.0, "energy-clamped"
        return frac, "energy"
    if _is_whole_feeder(device):
        return 1.0, "device-whole"
    if _is_partial(device):
        return None, "partial-without-energy"
    return None, "no-fraction"


def infer_energy_unit(records, feeder_load_kw: dict | None) -> str:
    """واحد «انرژی توزیع‌نشده» را از خود داده استنتاج می‌کند.

    واحد در منبع اعلام نشده است (A-08). با داشتن بار فیدر، تنها واحدی
    پذیرفته می‌شود که میانهٔ سهم قطع در بازهٔ (۰, ۱] بیفتد؛ اگر هیچ‌کدام
    نیفتاد، `kwh` (محافظه‌کارانه: سهم کوچک‌تر) انتخاب می‌شود تا SAIDI
    بزرگ‌نمایی نشود.
    """
    loads = {feeder_id(k): float(v) for k, v in (feeder_load_kw or {}).items()
             if v}
    if not loads:
        return "kwh"
    fracs = {"mwh": [], "kwh": []}
    for rec in records:
        if not getattr(rec, "in_model", False):
            continue
        load = loads.get(feeder_id(getattr(rec, "feeder_key", "")))
        if not load:
            continue
        t_min = getattr(rec, "duration_min", None)
        energy = getattr(rec, "energy_kwh", None)
        if not t_min or t_min <= 0 or not energy or energy <= 0:
            continue
        for unit, scale in (("mwh", 1000.0), ("kwh", 1.0)):
            fracs[unit].append(energy * scale / (load * (t_min / 60.0)))
    for unit in ("mwh", "kwh"):
        vals = sorted(fracs[unit])
        if not vals:
            continue
        median = vals[len(vals) // 2]
        if 0 < median <= 1.0:
            return unit
    return "kwh"


def compute_service_indices(records, *, model_feeders=(),
                            feeder_load_kw: dict | None = None,
                            lam: list | None = None,
                            coverage=None,
                            energy_unit: str = "auto",
                            customers: dict | None = None) -> ServiceIndices:
    """SAIDI/SAIFI/CAIDI/ASAI برای هر فیدر مدل و کل سامانه.

    ``lam`` (ردیف‌های λ/r) اگر داده شود، زمان مواجههٔ هر فیدر از همان
    مبنای λ گرفته می‌شود تا SAIDI و λ روی یک مخرج باشند.
    """
    from ..reliability.coverage import compute_coverage
    from ..topology.tracing import resolve_feeder

    model = [str(k) for k in (model_feeders or ())]
    loads = {feeder_id(k): float(v) for k, v in (feeder_load_kw or {}).items()
             if v}
    cust = {feeder_id(k): float(v) for k, v in (customers or {}).items() if v}

    unit = (energy_unit or "auto").strip().lower()
    unit_source = "declared"
    if unit not in ("mwh", "kwh"):
        in_model = [r for r in records if getattr(r, "in_model", False)]
        unit = infer_energy_unit(in_model, loads)
        unit_source = "inferred"

    by_feeder: dict[str, list] = {}
    for rec in records:
        if not getattr(rec, "in_model", False):
            continue
        raw = getattr(rec, "feeder_key", "")
        key = resolve_feeder(raw, model) if model else feeder_id(raw)
        by_feeder.setdefault(key, []).append(rec)

    exp_by_feeder: dict[str, float] = {}
    if lam:
        for row in lam:
            get = (row.get if isinstance(row, dict)
                   else lambda k, d=None, _r=row: getattr(_r, k, d))
            raw_key = str(get("feeder_key", "") or "")
            key = resolve_feeder(raw_key, model) if model else feeder_id(raw_key)
            years = float(get("exposure_years", 0.0) or 0.0)
            if not years:
                years = float(get("years_covered", 0) or 0)
            exp_by_feeder[key] = years

    rows: list[FeederServiceIndices] = []
    for key in sorted(set(by_feeder) | set(model)):
        evts = by_feeder.get(key, [])
        years = exp_by_feeder.get(key)
        if years is None:
            cov = compute_coverage(
                evts,
                start=getattr(coverage, "start", None),
                end=getattr(coverage, "end", None),
                force_cover=getattr(coverage, "forced_months", ()),
                force_exclude=getattr(coverage, "excluded_months", ()))
            years = getattr(cov, "exposure_years", 0.0) or 0.0
        load = loads.get(key)
        row = FeederServiceIndices(
            feeder_key=key, exposure_years=round(years, 6),
            events_total=len(evts))
        f_all = f_random = 0.0
        wt_all = wt_random = 0.0
        dur_all = dur_random = 0.0
        ens = 0.0
        basis: dict[str, int] = {}
        devices: dict[str, dict] = {}
        for rec in evts:
            frac, why = _fraction_of_event(rec, load, unit)
            basis[why] = basis.get(why, 0) + 1
            t_min = getattr(rec, "duration_min", None) or 0.0
            e = getattr(rec, "energy_kwh", None)
            if e and e > 0 and years:
                ens += (e * 1000.0 if unit == "mwh" else float(e))
            if frac is None:
                row.events_skipped += 1
                continue
            row.events_counted += 1
            if _is_whole_feeder(getattr(rec, "device_raw", "") or ""):
                row.events_whole_feeder += 1
            dev = str(getattr(rec, "device_raw", "") or "—").strip() or "—"
            slot = devices.setdefault(dev, {"events": 0, "f_sum": 0.0,
                                            "duration_min": 0.0})
            slot["events"] += 1
            slot["f_sum"] += frac
            slot["duration_min"] += t_min
            f_all += frac
            dur_all += frac * t_min
            if getattr(rec, "is_random", False):
                f_random += frac
                dur_random += frac * t_min
                wt_random += 1
            wt_all += 1
        if years:
            row.saifi = f_all / years
            row.saidi = dur_all / years
            row.saifi_random = f_random / years
            row.saidi_random = dur_random / years
            row.ens_kwh_per_year = ens / years
            row.worst_saifi = len(evts) / years
            row.worst_saidi = sum(getattr(r, "duration_min", None) or 0.0
                                  for r in evts) / years
        row.caidi = (row.saidi / row.saifi) if row.saifi else 0.0
        row.asai = max(0.0, 1.0 - row.saidi / MINUTES_PER_YEAR)
        if key in cust and row.events_counted:
            n = cust[key]
            row.customer_minutes = row.saidi * n
            row.customer_interruptions = row.saifi * n
        row.basis_counts = basis
        row.by_device = {k: {"events": v["events"],
                             "f_sum": round(v["f_sum"], 4),
                             "duration_min": round(v["duration_min"], 2)}
                         for k, v in sorted(devices.items(),
                                            key=lambda kv: -kv[1]["events"])}
        if row.events_skipped:
            row.notes.append(
                f"{row.events_skipped} رخداد بدون مدت معتبر یا بدون سهم قابل "
                "استنتاج شمرده نشد")
        if any(k == "energy-clamped" for k in basis):
            row.notes.append("سهم قطعِ برخی رخدادها > ۱ بود و روی ۱ بسته شد "
                             "(ناسازگاری انرژی/بار/مدت)")
        rows.append(row)

    res = ServiceIndices(feeders=rows, energy_unit=unit,
                         energy_unit_source=unit_source)
    if not loads:
        res.load_basis = "device-only"
        res.notes.append(
            "بار فیدر (kW) داده نشد؛ سهم قطع فقط برای رخدادهای تمام‌فیدر "
            "(بریکر/ریکلوزر) برابر یک گرفته شد و SAIDI کف واقعی است. برای "
            "شاخص کامل، بار هر فیدر یا P/Q مدل بار را وارد کنید.")
    else:
        res.load_basis = "feeder-load"
        res.notes.append(
            "سهم مشترکین از «انرژی توزیع‌نشده ÷ (بار فیدر × مدت)» استنتاج "
            "شد (فرض: سهم بار ≈ سهم مشترکین).")
    if unit_source == "inferred":
        res.notes.append(
            f"واحد «انرژی توزیع‌نشده» از خود داده استنتاج شد: {unit.upper()} "
            "(در منبع اعلام نشده — A-08).")
    if rows and all(not r.events_counted for r in rows):
        res.notes.append(
            "هیچ رخدادی سهم قطعِ قابل محاسبه نداشت؛ برای SAIDI/SAIFI بار "
            "فیدر را وارد کنید.")
    if customers:
        res.notes.append("تعداد مشترکین داده شد؛ مشترک-دقیقه و تعداد قطع "
                         "مشترکین هم گزارش شد (SAIDI/SAIFI مستقل از آن است).")

    # ---- جمع سامانه ----
    counted = [r for r in rows if r.events_counted and r.exposure_years]
    if counted:
        if loads and all(loads.get(r.feeder_key) for r in counted):
            total_load = sum(loads[r.feeder_key] for r in counted)
            res.saifi = sum(r.saifi * loads[r.feeder_key]
                            for r in counted) / total_load
            res.saidi = sum(r.saidi * loads[r.feeder_key]
                            for r in counted) / total_load
            res.aggregation = "load-weighted"
        else:
            res.saifi = sum(r.saifi for r in counted) / len(counted)
            res.saidi = sum(r.saidi for r in counted) / len(counted)
            res.aggregation = "simple-mean"
            res.notes.append(
                "جمع سامانه با میانگین سادهٔ فیدرها است (بار همهٔ فیدرها "
                "معلوم نبود)؛ برای جمع وزنی، بار همهٔ فیدرها را وارد کنید.")
        res.caidi = (res.saidi / res.saifi) if res.saifi else 0.0
        res.asai = max(0.0, 1.0 - res.saidi / MINUTES_PER_YEAR)
        res.worst_saifi = sum(r.worst_saifi for r in counted) / len(counted)
        res.worst_saidi = sum(r.worst_saidi for r in counted) / len(counted)
    else:
        res.notes.append("SAIDI/SAIFI محاسبه نشد: دادهٔ کافی نبود.")
    return res
