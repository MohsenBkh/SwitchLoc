# -*- coding: utf-8 -*-
"""Human-in-the-loop outage place/zone review with auditable SQLite storage.

سه نیاز این نسخه (درخواست کاربر)
--------------------------------
۱. **انتخاب خودکار زون هر ردیف** بر اساس فیدر رخداد و مختصات مکان
   پیشنهادی: مرز و هندسهٔ هر زون از همان گراف/زون‌بندی توپولوژی می‌آید
   (بدون تولید هندسهٔ حدسی). اگر مختصات در محدودهٔ تحمل نبود، قاعدهٔ
   «تک‌زون‌بودن فیدر» و سپس «نامشخص» اعمال می‌شود — هیچ زونی حدس زده
   نمی‌شود و مبنای انتخاب در ستون جدا ثبت می‌گردد (بند ۱۹).
۲. **مکان پیشنهادی در ابتدای فهرست** و انتخاب‌شده به‌صورت پیش‌فرض، هرگاه
   بانک آفلاین مکان برای «نام پست» تطبیقی پیدا کرده باشد.
۳. **وضعیت پیش‌فرض «تأیید مهندسی»** برای همهٔ ردیف‌ها، به‌جز ردیف‌هایی که
   هیچ زونی برایشان تعیین نشده است (تأیید بدون زون، انتساب حدسی است و
   مجاز نیست؛ آن ردیف‌ها «در انتظار بررسی» می‌مانند و صریح علامت می‌خورند).

منطق خالص (بدون Qt) در همین ماژول است و با pytest آزمون می‌شود؛ دیالوگ
Qt فقط `plan_review_rows` را رندر می‌کند.
"""
from __future__ import annotations
import math
import os
import sqlite3
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Iterable

from ..geography.places import PlaceGazetteer, PlaceMatch

#: نام متغیر محیطی برای مسیر جایگزین بانک آفلاین مکان‌ها
GAZETTEER_ENV_VAR = "SWITCHLOC_GAZETTEER"

_REPO_LAYOUT = ("data", "geography", "ardabil_places.sqlite")

#: فاصلهٔ پیش‌فرض (متر) از هندسهٔ زون که فراتر از آن انتساب خودکار رد می‌شود
DEFAULT_MAX_ZONE_DISTANCE_M = 2000.0

#: متن‌های مبنا (در ستون «مبنای زون» و راهنمای دیالوگ استفاده می‌شوند)
ZONE_BASIS_FA = {
    "saved-review": "بازبینی ذخیره‌شده",
    "point": "مختصات پیشنهادی",
    "single-zone-of-feeder": "تک‌زون فیدر",
    "unmatched": "یافتنشد (نیازمند بررسی)",
    "no-crs": "CRS پروژه نامشخص",
    "manual": "انتخاب دستی",
}


def default_gazetteer_path() -> Path | None:
    """مسیر بانک آفلاین مکان‌های اردبیل را بدون ایجاد هیچ فایلی پیدا می‌کند.

    ترتیب (مسیرها محدود و از پیش‌تعیین‌شده‌اند — هیچ گردش نامحدودی تا ریشهٔ
    فایل‌سیستم انجام نمی‌شود و هیچ فایلی ساخته/تغییر داده نمی‌شود):

    1. ``$SWITCHLOC_GAZETTEER`` — اگر تنظیم شده باشد، مسیر همان است؛
       اگر نبود، ``None`` برگردانده می‌شود (مسیر غلط سکوت نمی‌شود).
    2. کنار فایل اجرایی: ``<dir(exe)>/data/geography/ardabil_places.sqlite``
       (چیدمان نسخهٔ exe که BUILD.bat کنار خروجی کپی می‌کند).
    3. داخل بستهٔ PyInstaller: ``sys._MEIPASS/data/geography/...``.
    4. ریشهٔ مخزن (چیدمان src در توسعهٔ محلی).

    در غیر این صورت ``None`` — پیشنهاد مکان غیرفعال می‌شود، نه اینکه
    پایگاه خالی ساخته شود.
    """
    env = os.environ.get(GAZETTEER_ENV_VAR, "").strip()
    if env:
        env_path = Path(env)
        return env_path if env_path.is_file() else None
    candidates = []
    exe = getattr(sys, "executable", None)
    if exe:
        candidates.append(Path(exe).resolve().parent
                          .joinpath(*_REPO_LAYOUT))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass).joinpath(*_REPO_LAYOUT))
    candidates.append(Path(__file__).resolve().parents[3].joinpath(*_REPO_LAYOUT))
    for c in candidates:
        if c.is_file():
            return c
    return None


@dataclass(frozen=True)
class OutagePlaceSuggestion:
    event_id: str
    text: str
    matches: tuple[PlaceMatch, ...]


def suggest_event_places(records: Iterable, gazetteer: PlaceGazetteer,
                         limit: int = 5) -> list[OutagePlaceSuggestion]:
    """Suggest places from free-text descriptions; suggestions are never assignments."""
    out = []
    cache = {}
    def search(text):
        if text not in cache:
            cache[text] = gazetteer.search(text, limit=limit)
        return cache[text]
    for rec in records:
        # The outage workbook's «نام پست» is the primary location field
        # (often a village, farm, BTS site or other named place). Search it
        # first; notes/device are supplementary context, not substitutes.
        station = str(_attr_or_dict(rec, "substation") or "").strip()
        context = " ".join(x for x in (_attr_or_dict(rec, "notes"),
                                       _attr_or_dict(rec, "device_raw")) if x)
        # Prefer «نام پست» alone. Searching a concatenation of notes and
        # equipment first creates spurious substring matches for generic
        # words; contextual fallback is used only when the primary field has
        # no candidates.
        matches = search(station) if station else []
        text = station or context
        if not matches and context:
            text = " ".join(x for x in (station, context) if x)
            matches = search(text)
        out.append(OutagePlaceSuggestion(str(_attr_or_dict(rec, "id") or ""),
                                         text, tuple(matches)))
    return out


# ---------------------------------------------------------------------------
# هندسهٔ زون (برای انتساب خودکار مختصات → زون)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ZoneGeometry:
    """هندسهٔ سبک یک زون: نقاط گره‌های آن در CRS پروژه."""

    zone_id: str
    feeder: str
    zone_no: int
    points: tuple = ()

    @property
    def label(self) -> str:
        return f"{self.feeder or 'جزیره'} | Zone {self.zone_no} | {self.zone_id}"

    @property
    def centroid(self) -> tuple[float, float] | None:
        if not self.points:
            return None
        return (sum(p[0] for p in self.points) / len(self.points),
                sum(p[1] for p in self.points) / len(self.points))

    @property
    def bbox(self) -> tuple[float, float, float, float] | None:
        if not self.points:
            return None
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    def distance_to(self, point: tuple[float, float]) -> float:
        """کمترین فاصلهٔ اقلیدسی نقطه تا گره‌های زون (متر)."""
        px, py = float(point[0]), float(point[1])
        best = math.inf
        for x, y in self.points:
            d = (x - px) ** 2 + (y - py) ** 2
            if d < best:
                best = d
        return math.sqrt(best) if best != math.inf else math.inf

    def as_dict(self) -> dict:
        return {"zone_id": self.zone_id, "feeder": self.feeder,
                "zone_no": self.zone_no, "points": len(self.points),
                "centroid": self.centroid, "bbox": self.bbox}


def build_zone_geometries(graph, zones) -> dict[str, ZoneGeometry]:
    """``ZoneResult`` + گراف → هندسهٔ هر زون (نقاط گره‌های موجود)."""
    out: dict[str, ZoneGeometry] = {}
    if zones is None or graph is None:
        return out
    for z in getattr(zones, "zones", None) or []:
        pts = []
        for nid in getattr(z, "nodes", ()) or ():
            node = getattr(graph, "nodes", {}).get(nid)
            coord = getattr(node, "coord", None) if node is not None else None
            if coord is not None:
                pts.append((float(coord[0]), float(coord[1])))
        if not pts:
            continue
        out[str(z.id)] = ZoneGeometry(zone_id=str(z.id),
                                      feeder=str(getattr(z, "feeder", "") or ""),
                                      zone_no=int(getattr(z, "zone_no", 0) or 0),
                                      points=tuple(pts))
    return out


# ---------------------------------------------------------------------------
# انتساب خودکار زون
# ---------------------------------------------------------------------------
@dataclass
class ZonePick:
    """نتیجهٔ انتساب خودکار: زون + مبنای انتخاب (قابل حسابرسی)."""

    zone_id: str = ""
    basis: str = "unmatched"
    distance_m: float | None = None
    nearest_zone_id: str = ""
    nearest_distance_m: float | None = None

    @property
    def basis_fa(self) -> str:
        return ZONE_BASIS_FA.get(self.basis, self.basis)

    def as_dict(self) -> dict:
        return {"zone_id": self.zone_id, "basis": self.basis,
                "basis_fa": self.basis_fa,
                "distance_m": (None if self.distance_m is None
                               else round(self.distance_m, 3)),
                "nearest_zone_id": self.nearest_zone_id,
                "nearest_distance_m": (None if self.nearest_distance_m is None
                                       else round(self.nearest_distance_m, 3))}


def _bbox_lower_bound(bbox, point) -> float:
    """کمترین فاصلهٔ ممکن نقطه تا هر جایی داخل bbox (۰ = داخل)."""
    if bbox is None:
        return math.inf
    x0, y0, x1, y1 = bbox
    px, py = point
    dx = max(x0 - px, 0.0, px - x1)
    dy = max(y0 - py, 0.0, py - y1)
    return math.hypot(dx, dy)


def _feeder_matches(label: str, feeder: str | None) -> bool:
    """همان فیدر؟ (نگارش کوتاه «F5» با «F5 - KOSAR» یکی است)"""
    from ..topology.tracing import same_feeder
    if not feeder:
        return True
    return same_feeder(label, feeder)


def nearest_zone(geometries: dict[str, ZoneGeometry], point,
                 feeder: str | None = None, feeder_only: bool = True
                 ) -> tuple[ZoneGeometry | None, float | None]:
    """نزدیک‌ترین زون به یک نقطه (با هرس bbox برای کارایی)."""
    pool = [g for g in geometries.values()
            if not (feeder_only and feeder) or _feeder_matches(g.feeder, feeder)]
    if not pool:
        pool = list(geometries.values())          # جزیره/برچسب دیگر
    best, best_d = None, math.inf
    for g in sorted(pool, key=lambda z: (z.feeder, z.zone_no, z.zone_id)):
        if g.bbox is None:
            continue
        lb = _bbox_lower_bound(g.bbox, point)
        if lb >= best_d:
            continue
        d = g.distance_to(point)
        if d < best_d:
            best, best_d = g, d
    if best is None:
        return None, None
    return best, best_d


def pick_zone(geometries: dict[str, ZoneGeometry], *,
              feeder: str = "", point: tuple[float, float] | None = None,
              max_distance_m: float = DEFAULT_MAX_ZONE_DISTANCE_M,
              feeder_only: bool = True,
              reason: str = "") -> ZonePick:
    """زون متناظر یک رخداد را از فیدر و مختصات تعیین می‌کند.

    قواعد (به ترتیب، هرگز حدس مطلق):
      1. اگر مختصات موجود باشد و نزدیک‌ترین هندسهٔ زونِ همان فیدر در
         ``max_distance_m`` باشد → همان زون، مبنا «مختصات پیشنهادی».
      2. اگر فیدر فقط **یک** زون داشته باشد → همان زون (انتساب قطعی)،
         مبنا «تک‌زون فیدر».
      3. در غیر این صورت هیچ زونی انتخاب نمی‌شود و نزدیک‌ترین فاصله
         برای راهنمای مهندس گزارش می‌گردد.
    """
    if reason == "no-crs":
        return ZonePick(basis="no-crs")
    pool_has_feeder = any(_feeder_matches(g.feeder, feeder)
                          for g in geometries.values()) if feeder else True
    if point is not None:
        z, d = nearest_zone(geometries, point, feeder=feeder,
                            feeder_only=feeder_only)
        if z is not None and d is not None:
            if d <= float(max_distance_m):
                return ZonePick(zone_id=z.zone_id, basis="point",
                                distance_m=d, nearest_zone_id=z.zone_id,
                                nearest_distance_m=d)
            same_zone = [g for g in geometries.values()
                         if _feeder_matches(g.feeder, feeder)]
            if feeder and len(same_zone) == 1:
                return ZonePick(zone_id=same_zone[0].zone_id,
                                basis="single-zone-of-feeder",
                                distance_m=d, nearest_zone_id=z.zone_id,
                                nearest_distance_m=d)
            return ZonePick(basis="unmatched", nearest_zone_id=z.zone_id,
                            nearest_distance_m=d)
    same_zone = [g for g in geometries.values()
                 if _feeder_matches(g.feeder, feeder)] if feeder else []
    if feeder and len(same_zone) == 1:
        return ZonePick(zone_id=same_zone[0].zone_id,
                        basis="single-zone-of-feeder")
    if feeder and not pool_has_feeder:
        return ZonePick(basis="unmatched")
    return ZonePick(basis="unmatched")


# ---------------------------------------------------------------------------
# برنامهٔ ردیف‌های بازبینی (Qt-free)
# ---------------------------------------------------------------------------
def place_options(suggestion: OutagePlaceSuggestion | None,
                  saved_place_id: str = "") -> list[dict]:
    """گزینه‌های «مکان پیشنهادی» — بهترین پیشنهاد **اول** فهرست.

    هرگاه بانک آفلاین مکان تطبیقی پیدا کرده باشد، بهترین تطبیق اولین
    گزینه و انتخاب پیش‌فرض است (درخواست کاربر)؛ «بدون مکان تأییدشده»
    آخرین گزینه می‌ماند تا اشتباهی انتخاب نشود.
    """
    opts = []
    matches = list(getattr(suggestion, "matches", ()) or ())
    for i, m in enumerate(matches):
        opts.append({
            "place_id": m.place.place_id,
            "label": (("★ " if i == 0 else "") +
                      f"{m.place.name} ({m.confidence}) — "
                      f"{m.place.lat:.5f}, {m.place.lon:.5f}"),
            "name": m.place.name, "lat": float(m.place.lat),
            "lon": float(m.place.lon),
            "confidence": m.confidence,
            "is_default": False,
        })
    opts.append({"place_id": "", "label": "بدون مکان تأییدشده",
                 "name": "", "lat": None, "lon": None,
                 "confidence": "", "is_default": False})
    if saved_place_id:
        for o in opts:
            if o["place_id"] == saved_place_id:
                o["is_default"] = True
                break
    elif opts and opts[0]["place_id"]:
        opts[0]["is_default"] = True
    elif opts:
        # هیچ تطبیقی نیست → تنها گزینه («بدون مکان تأییدشده») پیش‌فرض است
        opts[-1]["is_default"] = True
    return opts


def zone_options(geometries: dict[str, ZoneGeometry], feeder: str,
                 point=None, feeder_only: bool = True) -> list[dict]:
    """گزینه‌های زون همان فیدر، مرتب بر اساس فاصله تا نقطه (نزدیک‌تر اول)."""
    pool = [g for g in geometries.values()
            if not (feeder_only and feeder) or g.feeder == feeder]
    if not pool:
        pool = list(geometries.values())
    rows = []
    for g in pool:
        d = g.distance_to(point) if point is not None else None
        rows.append({"zone_id": g.zone_id, "label": g.label,
                     "feeder": g.feeder, "zone_no": g.zone_no,
                     "distance_m": d})
    rows.sort(key=lambda r: (r["distance_m"] if r["distance_m"] is not None
                             else math.inf, r["feeder"], r["zone_no"]))
    return rows


@dataclass
class ReviewRowPlan:
    """برنامهٔ یک ردیف بازبینی — ورودی دیالوگ و خروجی آزمون‌ها."""

    event_id: str
    feeder_key: str = ""
    point: tuple[float, float] | None = None
    point_basis: str = ""            # suggestion | saved | none
    place_options: list = dc_field(default_factory=list)
    place_id: str = ""
    zone_options: list = dc_field(default_factory=list)
    zone_id: str = ""
    zone_basis: str = "unmatched"
    zone_note: str = ""
    status: str = "pending"
    nearest_zone_distance_m: float | None = None

    @property
    def zone_basis_fa(self) -> str:
        return ZONE_BASIS_FA.get(self.zone_basis, self.zone_basis)

    @property
    def needs_review(self) -> bool:
        return not self.zone_id

    def as_dict(self) -> dict:
        return {"event_id": self.event_id, "feeder_key": self.feeder_key,
                "point": self.point, "point_basis": self.point_basis,
                "place_id": self.place_id, "zone_id": self.zone_id,
                "zone_basis": self.zone_basis,
                "zone_basis_fa": self.zone_basis_fa,
                "status": self.status,
                "nearest_zone_distance_m": self.nearest_zone_distance_m}


def plan_review_rows(records: Iterable, *,
                     suggestions: dict | None = None,
                     saved: dict | None = None,
                     geometries: dict[str, ZoneGeometry] | None = None,
                     project_crs: str = "",
                     max_zone_distance_m: float = DEFAULT_MAX_ZONE_DISTANCE_M,
                     feeder_only: bool = True,
                     transform=None) -> list[ReviewRowPlan]:
    """برنامهٔ کامل بازبینی: مکان پیشنهادی، زون خودکار و وضعیت پیش‌فرض.

    ``transform``: تابع ``(lat, lon) -> (x, y)`` در CRS پروژه؛ پیش‌فرض
    ``gis.crs.transform_wgs84_to_project``. اگر CRS پروژه نامشخص باشد
    هیچ مختصاتی حدس زده نمی‌شود و مبنا «CRS پروژه نامشخص» ثبت می‌گردد.
    """
    from ..topology.tracing import feeder_id as normalize_feeder_key
    from ..topology.tracing import resolve_feeder

    geometries = geometries or {}
    model_feeders = sorted({g.feeder for g in geometries.values() if g.feeder})
    suggestions = suggestions or {}
    saved = saved or {}
    if transform is None and project_crs:
        # تبدیل پیش‌فرض باید CRS پروژه را داشته باشد؛ امضای تابع سه‌آرگومانی
        # است و پاس دادن خودِ تابع، همهٔ مختصات را بی‌صدا بی‌اثر می‌کرد.
        from ..gis.crs import transform_wgs84_to_project as _tr

        def transform(lat: float, lon: float):
            return _tr(lat, lon, project_crs)
    rows: list[ReviewRowPlan] = []
    pick_cache = {}
    options_cache = {}
    for rec in records:
        eid = str(getattr(rec, "id", "") or "")
        raw_feeder = str(getattr(rec, "feeder_key", "")
                         or getattr(rec, "feeder_raw", "") or "")
        feeder = normalize_feeder_key(raw_feeder) or raw_feeder.strip().upper()
        # نگارش کوتاه فایل خاموشی («F5») به شناسهٔ کامل فیدر مدل
        # («F5 - KOSAR») نگاشت می‌شود تا زون و برچسب نقشه یکی باشند؛ در
        # ابهام (دو فیدر F2) چیزی ادغام نمی‌شود.
        if feeder and model_feeders:
            feeder = resolve_feeder(feeder, model_feeders) or feeder
        old = saved.get(eid, {}) or {}
        sug = suggestions.get(eid)
        opts = place_options(sug, str(old.get("place_id", "") or ""))
        row = ReviewRowPlan(event_id=eid, feeder_key=feeder,
                            place_options=opts)

        # --- مختصات نقطهٔ رخداد -----------------------------------------
        point = None
        point_basis = "none"
        saved_x, saved_y = old.get("coord_x"), old.get("coord_y")
        if saved_x is not None and saved_y is not None:
            try:
                point = (float(saved_x), float(saved_y))
                point_basis = "saved"
            except (TypeError, ValueError):
                point = None
        if point is None:
            chosen = next((o for o in opts if o["place_id"]
                           and o["place_id"] == old.get("place_id")), None)
            if chosen is None:
                chosen = next((o for o in opts if o.get("is_default")), None)
            if chosen is not None and chosen.get("lat") is not None:
                if not project_crs:
                    row.zone_basis = "no-crs"
                    row.zone_note = ("CRS پروژه تعیین نشده است؛ مختصات "
                                     "پیشنهاد روی شبکه جای‌گذاری نشد.")
                elif transform is not None:
                    try:
                        point = tuple(transform(float(chosen["lat"]),
                                                float(chosen["lon"])))
                        point_basis = "suggestion"
                    except Exception:                   # noqa: BLE001
                        point = None
        row.point = point
        row.point_basis = point_basis

        # --- انتساب زون --------------------------------------------------
        if old.get("zone_id") and old.get("status") in ("confirmed", "rejected"):
            row.zone_id = str(old.get("zone_id") or "")
            row.zone_basis = "saved-review"
            row.status = str(old.get("status"))
            pick = None
        else:
            cache_key = (feeder, point, row.zone_basis == "no-crs")
            if cache_key not in pick_cache:
                pick_cache[cache_key] = pick_zone(
                    geometries, feeder=feeder, point=point,
                    max_distance_m=max_zone_distance_m, feeder_only=feeder_only,
                    reason=("no-crs" if row.zone_basis == "no-crs" else ""))
            pick = pick_cache[cache_key]
            row.zone_id = pick.zone_id
            row.zone_basis = pick.basis
            row.nearest_zone_distance_m = pick.nearest_distance_m
            # وضعیت پیش‌فرض: تأیید مهندسی هرگاه زون تعیین شده باشد
            row.status = "confirmed" if row.zone_id else "pending"
            if not row.zone_id and pick.nearest_distance_m is not None:
                row.zone_note = (
                    "نزدیک‌ترین زون {0:,.0f} متر دورتر از مختصات پیشنهادی "
                    "است (بیش از تحمل {1:,.0f} متر)؛ انتخاب دستی لازم است."
                ).format(pick.nearest_distance_m, max_zone_distance_m)
            elif not row.zone_id:
                row.zone_note = ("زون متناظر از فیدر/مختصات تعیین نشد؛ "
                                 "انتخاب دستی لازم است.")
        opt_key = (feeder, point)
        if opt_key not in options_cache:
            options_cache[opt_key] = zone_options(geometries, feeder, point=point,
                                                   feeder_only=feeder_only)
        row.zone_options = options_cache[opt_key]
        row.place_id = next((o["place_id"] for o in opts
                             if o.get("is_default")), "")
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# نقاط لایهٔ نقشه (خاموشی‌های دارای مختصات)
# ---------------------------------------------------------------------------
def outage_map_points(records: Iterable, *, geometries: dict | None = None,
                      saved: dict | None = None,
                      suggestions: dict | None = None,
                      transform=None,
                      max_distance_m: float = 2500.0) -> list[dict]:
    """رخدادهای دارای مختصات را به نقاط آمادهٔ نمایش روی نقشه تبدیل می‌کند.

    منبع مختصات، به ترتیب: مختصات ذخیره‌شدهٔ بازبینی (CRS پروژه) → مکان
    پیشنهادی بانک آفلاین تبدیل‌شده با ``transform``. رخدادی که هیچ مختصاتی
    ندارد وارد لایه نمی‌شود (شمارش آن در پنل نقشه گزارش می‌گردد). زون هر
    نقطه از بازبینی ذخیره‌شده یا انتساب خودکار ``pick_zone`` می‌آید و مرکز
    آن زون برای رسم خط اتصال برگردانده می‌شود.

    ``place``/``label`` نام مکان است (بازبینی ذخیره‌شده > بانک مکان‌ها >
    نام پست > شمارهٔ رخداد) تا برچسب نقشه بتواند رخدادهای یک مکان را در یک
    برچسب «نام (تعداد)» جمع کند — درخواست کاربر.
    """
    geometries = geometries or {}
    saved = saved or {}
    suggestions = suggestions or {}
    cache: dict = {}
    out: list[dict] = []
    for rec in records:
        eid = str(_attr_or_dict(rec, "id") or "")
        old = saved.get(eid) or {}
        matches = list(getattr(suggestions.get(eid), "matches", ()) or ())
        chosen = None
        if old.get("place_id"):
            chosen = next((m for m in matches
                           if m.place.place_id == old.get("place_id")), None)
        if chosen is None and matches:
            chosen = matches[0]

        # --- نام مکان برچسب -------------------------------------------------
        place_name = _clean_place_name(old.get("place_name"))
        if not place_name and chosen is not None:
            place_name = _clean_place_name(getattr(chosen.place, "name", ""))
        if not place_name:
            place_name = _clean_place_name(_attr_or_dict(rec, "substation"))
        if not place_name:
            place_name = _clean_place_name(_attr_or_dict(rec, "event_no"))
        place_name = place_name or eid[:8]

        # --- مختصات ---------------------------------------------------------
        point = None
        cx, cy = old.get("coord_x"), old.get("coord_y")
        if cx is not None and cy is not None:
            try:
                point = (float(cx), float(cy))
            except (TypeError, ValueError):
                point = None
        if point is None and chosen is not None and transform is not None:
            pid = chosen.place.place_id
            if pid not in cache:
                try:
                    cache[pid] = transform(float(chosen.place.lat),
                                           float(chosen.place.lon))
                except Exception:                   # noqa: BLE001
                    cache[pid] = None
            point = cache[pid]
        if point is None:
            continue

        fk = _feeder_of(rec, {g.feeder for g in geometries.values()})
        zone_id = str(old.get("zone_id") or "")
        if not zone_id:
            zone_id = pick_zone(geometries, feeder=fk, point=point,
                                max_distance_m=max_distance_m).zone_id
        geom = geometries.get(zone_id) if zone_id else None
        centroid = geom.centroid if geom is not None else None
        out.append({
            "id": eid,
            "x": float(point[0]), "y": float(point[1]),
            "label": place_name[:36],
            "place": place_name[:36],
            "place_full": place_name,
            "status": str(old.get("status") or "pending"),
            "feeder": fk,
            "zone_id": zone_id,
            "zone_x": (float(centroid[0]) if centroid else None),
            "zone_y": (float(centroid[1]) if centroid else None),
            "zone_label": (geom.label if geom is not None else ""),
        })
    return out


def _clean_place_name(value) -> str:
    """نام مکان قابل نمایش روی نقشه.

    برچسب‌های بی‌معنی فایل خاموشی (مثل «Sheet1» که نام برگهٔ اکسل است)
    یا خط‌تیره‌ها حذف می‌شوند تا برچسب نقشه «Sheet1 (4)» نشود.
    """
    text = " ".join(str(value or "").split())
    if not text or text in {"—", "-", ".", "؟", "?"}:
        return ""
    low = text.lower().replace("_", "").replace("-", "")
    if low.startswith("sheet") and (low[5:].isdigit() or low[5:] == ""):
        return ""
    return text


def _cluster_points(points: list, distance_m: float) -> list[list]:
    """خوشه‌بندی تک‌پیوندی نقاط (نقاط نزدیک‌تر از آستانه یک برچسب می‌گیرند)."""
    clusters: list[list] = []
    for q in points:
        merged = [c for c in clusters
                  if any(math.dist(q, r) <= distance_m for r in c)]
        if not merged:
            clusters.append([q])
            continue
        base = merged[0]
        base.append(q)
        for extra in merged[1:]:
            base.extend(extra)
            clusters.remove(extra)
    return clusters


def outage_label_groups(points: Iterable[dict], *,
                        cluster_distance_m: float = 2000.0) -> list[dict]:
    """نقاط لایهٔ خاموشی → برچسب‌های «نام (تعداد)».

    چند رخداد در یک مکان یک برچسب می‌گیرند و تعداد خطاها داخل پرانتز
    می‌آید (درخواست کاربر: «کرندق (۴)»، «نوده (۶)») — به‌جای چند برچسب
    تکراری روی هم. اگر همان نام در نقاط دور از هم (بیش از
    ``cluster_distance_m``) ثبت شده باشد به برچسب‌های جدا شکسته می‌شود تا
    شمارش گمراه‌کننده نشود. مختصات هر برچسب = میانگین نقاط همان خوشه.
    """
    buckets: dict[tuple, list] = {}
    for p in points or ():
        try:
            x, y = float(p["x"]), float(p["y"])
        except (KeyError, TypeError, ValueError):
            continue
        name = _clean_place_name(p.get("place") or p.get("label"))
        if not name:
            continue
        buckets.setdefault((str(p.get("feeder") or ""), name), []).append((x, y))
    out: list[dict] = []
    for (feeder, name), pts in buckets.items():
        for cluster in _cluster_points(pts, float(cluster_distance_m)):
            n = len(cluster)
            out.append({
                "feeder": feeder, "name": name, "count": n,
                "x": sum(q[0] for q in cluster) / n,
                "y": sum(q[1] for q in cluster) / n,
                "text": f"{name} ({n})",
            })
    out.sort(key=lambda g: (g["feeder"], g["name"], g["x"], g["y"]))
    return out


def _attr_or_dict(rec, name: str):
    """رخداد ممکن است دیتاکلاس یا dict باشد (هر دو پشتیبانی می‌شوند)."""
    if isinstance(rec, dict):
        return rec.get(name)
    return getattr(rec, name, None)


def _feeder_of(rec, candidates=()) -> str:
    """شناسهٔ فیدر رخداد؛ در صورت امکان با نگاشت به شناسهٔ فیدر مدل.

    ``candidates`` (فیدرهای زون‌ها/شبکه) برای یکی‌دانستن نگارش کوتاه و
    آراسته است: «F5» فایل خاموشی → «F5 - KOSAR». در ابهام (دو فیدر F2)
    هیچ نگاشتی انجام نمی‌شود.
    """
    from ..topology.tracing import feeder_id as normalize
    from ..topology.tracing import resolve_feeder

    raw = (_attr_or_dict(rec, "feeder_key")
           or _attr_or_dict(rec, "feeder_raw") or "")
    key = normalize(raw) or str(raw).strip().upper()
    cands = [str(c) for c in (candidates or ()) if str(c)]
    if key and cands:
        return resolve_feeder(key, cands) or key
    return key


# ---------------------------------------------------------------------------
# ذخیره‌سازی بازبینی
# ---------------------------------------------------------------------------
class OutageReviewStore:
    """Persist engineer-confirmed event→place/zone decisions in project DB."""

    _COLUMNS = (
        ("place_id", "TEXT NOT NULL DEFAULT ''"),
        ("place_name", "TEXT NOT NULL DEFAULT ''"),
        ("zone_id", "TEXT NOT NULL DEFAULT ''"),
        ("status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("reviewer", "TEXT NOT NULL DEFAULT ''"),
        ("note", "TEXT NOT NULL DEFAULT ''"),
        ("coord_x", "REAL"),
        ("coord_y", "REAL"),
        ("zone_basis", "TEXT NOT NULL DEFAULT ''"),
    )

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        with sqlite3.connect(self.db_path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS outage_event_review (
                event_id TEXT PRIMARY KEY, place_id TEXT NOT NULL DEFAULT '',
                place_name TEXT NOT NULL DEFAULT '', zone_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('confirmed','rejected')),
                reviewer TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            # مهاجرت نرم: پایگاه‌های قدیمی بدون ستون‌های مختصات/مبنا
            existing = {r[1] for r in
                        db.execute("PRAGMA table_info(outage_event_review)")}
            for name, ddl in self._COLUMNS:
                if name in existing:
                    continue
                try:
                    db.execute(
                        f"ALTER TABLE outage_event_review ADD COLUMN {name} {ddl}")
                except sqlite3.OperationalError:
                    pass                          # ستون از قبل هست
            # وضعیت «pending» در پایگاه‌های قدیمی مجاز نبود؛ CHECK قدیمی
            # فقط confirmed/rejected را می‌پذیرد. برای سازگاری، ردیف‌های
            # pending ذخیره نمی‌شوند (مانند قبل) — هیچ داده‌ای حذف نمی‌شود.

    def save(self, event_id: str, zone_id: str, *, place_id: str = '',
             place_name: str = '', reviewer: str = '', note: str = '',
             status: str = 'confirmed', coord_x: float | None = None,
             coord_y: float | None = None, zone_basis: str = '') -> None:
        if not event_id or (status == 'confirmed' and not zone_id):
            raise ValueError('event_id and confirmed zone_id are required')
        if status not in ('confirmed', 'rejected'):
            raise ValueError('status must be confirmed or rejected')
        with sqlite3.connect(self.db_path) as db:
            cols = {r[1] for r in
                    db.execute("PRAGMA table_info(outage_event_review)")}
            payload = {
                "event_id": event_id, "place_id": place_id,
                "place_name": place_name, "zone_id": zone_id,
                "status": status, "reviewer": reviewer, "note": note,
                "coord_x": coord_x, "coord_y": coord_y,
                "zone_basis": zone_basis,
            }
            use = [c for c in payload if c in cols]
            placeholders = ",".join("?" for _ in use)
            updates = ",".join(f"{c}=excluded.{c}" for c in use
                               if c not in ("event_id",))
            db.execute(
                f"INSERT INTO outage_event_review ({','.join(use)}) "
                f"VALUES({placeholders}) ON CONFLICT(event_id) DO UPDATE SET "
                f"{updates}, updated_at=CURRENT_TIMESTAMP",
                tuple(payload[c] for c in use))

    def load(self) -> dict[str, dict]:
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute('SELECT * FROM outage_event_review').fetchall()
        return {r['event_id']: dict(r) for r in rows}

    def confirmed_event_to_zone(self) -> dict[str, str]:
        return {eid: r['zone_id'] for eid, r in self.load().items()
                if r['status'] == 'confirmed'}

# ---------------------------------------------------------------------------
# توزیع رنگی مسیر بر اساس تکرار خاموشی + رتبه‌بندی مکان‌ها
# ---------------------------------------------------------------------------
def _point_segment_distance(px: float, py: float, ax: float, ay: float,
                            bx: float, by: float) -> float:
    """کمترین فاصلهٔ نقطه تا پاره‌خط (واحد: متر)."""
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def outage_heat_counts(points: Iterable[dict], graph, *,
                       radius_m: float = 300.0, edge_ids=None) -> dict[str, int]:
    """تعداد خاموشی‌های نزدیک هر یال (متناسب با تکرار در طول فیدر).

    هر نقطهٔ خاموشی به **همهٔ** یال‌هایی که در شعاع ``radius_m`` آن هستند
    نسبت داده می‌شود (یک خاموشی می‌تواند روی چند یال مجاور اثر بگذارد);
    خروجی: ``{edge_id: count}``. یال‌های بدون مختصات نادیده گرفته می‌شوند.
    """
    pts: list[tuple[float, float]] = []
    for pt in points or ():
        try:
            pts.append((float(pt["x"]), float(pt["y"])))
        except (KeyError, TypeError, ValueError):
            continue
    out: dict[str, int] = {}
    if not pts or graph is None:
        return out
    radius = max(1.0, float(radius_m))
    bounds = (min(p[0] for p in pts), max(p[0] for p in pts),
              min(p[1] for p in pts), max(p[1] for p in pts))
    for eid, edge in (getattr(graph, "edges", {}) or {}).items():
        if edge_ids is not None and eid not in edge_ids:
            continue
        a = getattr(graph.nodes, "get", lambda *_: None)(edge.a)
        b = getattr(graph.nodes, "get", lambda *_: None)(edge.b)
        if a is None or b is None or a.coord is None or b.coord is None:
            continue
        ax, ay = float(a.coord[0]), float(a.coord[1])
        bx, by = float(b.coord[0]), float(b.coord[1])
        if max(ax, bx) + radius < bounds[0] or \
                min(ax, bx) - radius > bounds[1] or \
                max(ay, by) + radius < bounds[2] or \
                min(ay, by) - radius > bounds[3]:
            continue
        n = sum(1 for px, py in pts
                if _point_segment_distance(px, py, ax, ay, bx, by) <= radius)
        if n:
            out[str(eid)] = int(n)
    return out


def assign_heat_level(count: int, levels: Iterable[dict]) -> dict | None:
    """سطح رنگی متناظر با تعداد خاموشی (None = بدون رنگ)."""
    try:
        value = int(count)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    fallback = None
    for lvl in levels or ():
        top = lvl.get("max")
        if top is None:
            return dict(lvl)
        try:
            if value <= float(top):
                return dict(lvl)
        except (TypeError, ValueError):
            continue
        fallback = dict(lvl)
    return fallback


def outage_place_ranking(points: Iterable[dict], *,
                         limit: int | None = None) -> list[dict]:
    """رتبه‌بندی مکان‌های خاموشی (درخواست کاربر: جدول رتبه‌بندی).

    هر ردیف: رتبه، مکان، فیدر، تعداد خاموشی، سهم درصدی، توزیع وضعیت
    (تأیید/در انتظار/رد)، مرکز مختصات و شمارهٔ زون غالب.
    """
    groups: dict[tuple[str, str], dict] = {}
    total = 0
    for pt in points or ():
        try:
            x, y = float(pt["x"]), float(pt["y"])
        except (KeyError, TypeError, ValueError):
            continue
        total += 1
        name = str(pt.get("place") or pt.get("label") or "").strip() or "—"
        feeder = str(pt.get("feeder") or "").strip()
        key = (feeder, name)
        g = groups.setdefault(key, {
            "place": name, "feeder": feeder, "count": 0,
            "x_sum": 0.0, "y_sum": 0.0,
            "confirmed": 0, "pending": 0, "rejected": 0,
            "zones": {},
        })
        g["count"] += 1
        g["x_sum"] += x
        g["y_sum"] += y
        status = str(pt.get("status") or "pending")
        if status in ("confirmed", "pending", "rejected"):
            g[status] += 1
        zone_id = str(pt.get("zone_id") or "")
        if zone_id:
            g["zones"][zone_id] = g["zones"].get(zone_id, 0) + 1

    rows = []
    for g in groups.values():
        n = g["count"]
        zone_id = max(g["zones"], key=g["zones"].get) if g["zones"] else ""
        rows.append({
            "place": g["place"], "feeder": g["feeder"], "count": n,
            "share_percent": round(100.0 * n / total, 2) if total else 0.0,
            "x": round(g["x_sum"] / n, 3), "y": round(g["y_sum"] / n, 3),
            "confirmed": g["confirmed"], "pending": g["pending"],
            "rejected": g["rejected"], "zone_id": zone_id,
        })
    rows.sort(key=lambda r: (-r["count"], r["feeder"], r["place"]))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows[:int(limit)] if limit else rows

