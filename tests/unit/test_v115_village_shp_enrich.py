# -*- coding: utf-8 -*-
"""v1.15 — آزمون غنی‌سازی بانک مکان از شیپ‌فایل ``Village.shp``.

شیپ‌فایل واقعی در مخزن نیست (ورودی کاربر)، پس این آزمون یک شیپ‌فایل
کوچک و قطعی می‌سازد و همان تابع ``enrich`` اسکریپت را روی **کپی** بانک
اجرا می‌کند تا قاعده‌های زیر قفل شوند:

* ادغام هم‌نام در شعاع ۳ کیلومتر (بدون رکورد تکراری) + ثبت املای دیگر؛
* هم‌نامِ دورتر از ۳ کیلومتر = مکان مستقل؛
* نقطهٔ بیرون مرز استان نادیده گرفته می‌شود؛
* شهرستان از فهرست رسمی، و در نبود آن از رأی اکثریت کد ناحیه (≥۳ رأی، ≥۶۰٪)؛
* منبع هر رکورد جدید ``Village.shp …`` است و هیچ مختصاتی ساخته نمی‌شود؛
* اجرای دوباره بی‌اثر است (idempotent).
"""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

warehouse = pytest.importorskip("shapefile")           # pyshp

from switchloc.geography.places import (Place, PlaceGazetteer,  # noqa: E402
                                        compact_place_name)

import enrich_ardabil_village_shp as village  # noqa: E402

BANK = ROOT / "data" / "geography" / "ardabil_places.sqlite"
SOURCE = village.SOURCE

# نام‌های آزمون فقط از حروفی ساخته شده‌اند که در cp1256 (کدگذاری DBF
# شیپ‌فایل واقعی) وجود دارند.
SEED_NAME = "آزمون آباد"
SEED_ID = "test:seed:village-shp"


# ---------------------------------------------------------------------------
# ابزارهای ساخت ورودی ساختگی
# ---------------------------------------------------------------------------
def _enc(text: str) -> str:
    """«ی/ک» فارسی → «ي/ك» عربی (حروف موجود در cp1256)."""
    return str(text).replace("\u06cc", "\u064a").replace("\u06a9", "\u0643")


def _write_boundary(path: Path) -> Path:
    """مربع بزرگ اردبیل (۴۷–۴۹ شرقی، ۳۷٫۵–۳۹٫۵ شمالی)."""
    ring = [[47.0, 37.5], [49.0, 37.5], [49.0, 39.5], [47.0, 39.5], [47.0, 37.5]]
    geo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {},
         "geometry": {"type": "Polygon", "coordinates": [ring]}}]}
    path.write_text(json.dumps(geo), encoding="utf-8")
    return path


def _write_shp(path: Path, rows) -> Path:
    """``rows`` = [(name, lat, lon, area_code), …]، DBF با cp1256."""
    w = warehouse.Writer(str(path.with_suffix("")), shapeType=warehouse.POINT,
                         encoding="cp1256", autoBalance=1)
    w.field("NAME", "C", 60)
    w.field("UDISTRCT", "C", 8)
    w.field("R_DSTRC", "C", 8)
    for name, lat, lon, code in rows:
        w.point(lon, lat)
        w.record(_enc(name), str(code), "1")
    w.close()
    return path.with_suffix(".shp")


def _official(path: Path, rows) -> Path:
    lines = ["name,kind,county,bakhsh,district,amar_code"]
    for name, kind, county in rows:
        lines.append(f"{_enc(name)},{kind},{county},بخش,دهستان,1")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture()
def env(tmp_path):
    bank_path = tmp_path / "bank.sqlite"
    shutil.copy2(BANK, bank_path)
    # یک مکان ثابت و قطعی برای آزمون ادغام/فاصله
    PlaceGazetteer(bank_path).upsert([Place(
        place_id=SEED_ID, name=SEED_NAME, lat=38.30, lon=48.30,
        place_type="village", county="شهرستان آزمون", district="",
        source="test-seed")])
    boundary = _write_boundary(tmp_path / "boundary.geojson")
    empty_official = _official(tmp_path / "empty.csv", [])
    return bank_path, boundary, tmp_path, empty_official


def _count(db_path: Path, sql: str, args=()) -> int:
    db = sqlite3.connect(db_path)
    try:
        return int(db.execute(sql, args).fetchone()[0])
    finally:
        db.close()


def _county(db_path: Path, name: str):
    db = sqlite3.connect(db_path)
    try:
        row = db.execute("SELECT county FROM places WHERE compact_name=?",
                         (compact_place_name(name),)).fetchone()
        return row[0] if row else "<missing>"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# ۱) ادغام هم‌نام نزدیک + ثبت املای دیگر به‌عنوان alias
# ---------------------------------------------------------------------------
def test_near_same_name_is_merged_and_alias_recorded(env):
    bank, boundary, tmp, official = env
    before = _count(bank, "SELECT COUNT(*) FROM places")

    shp = _write_shp(tmp / "v.shp", [
        ("آزمونآباد", 38.303, 48.30, "10"),        # ≈۳۳۰ متر، املای بی‌فاصله
    ])
    rep = village.enrich(bank, shp, boundary, official)

    assert rep["merged_into_existing"] == 1
    assert rep["added"] == 0
    assert rep["skipped_duplicates"] == 0
    assert _count(bank, "SELECT COUNT(*) FROM places") == before
    aliases = _count(bank, "SELECT COUNT(*) FROM aliases WHERE alias=?",
                     ("آزمونآباد",))
    assert aliases == 1, "املای دیگر حذف شد، نه ثبت به‌عنوان alias"


def test_same_name_beyond_radius_becomes_separate_place(env):
    bank, boundary, tmp, official = env
    shp = _write_shp(tmp / "v.shp", [
        (SEED_NAME, 38.50, 48.30, "10"),           # ≈۲۲ کیلومتر
    ])
    rep = village.enrich(bank, shp, boundary, official)

    assert rep["added"] == 1
    assert rep["merged_into_existing"] == 0
    db = sqlite3.connect(bank)
    lat, lon, src = db.execute(
        "SELECT lat, lon, source FROM places WHERE name=? AND lat>38.4",
        (SEED_NAME,)).fetchone()
    assert lat == pytest.approx(38.50, abs=1e-6)
    assert lon == pytest.approx(48.30, abs=1e-6)
    assert src == SOURCE


# ---------------------------------------------------------------------------
# ۲) نقطهٔ بیرون مرز نادیده گرفته می‌شود
# ---------------------------------------------------------------------------
def test_outside_boundary_is_ignored(env):
    bank, boundary, tmp, official = env
    shp = _write_shp(tmp / "v.shp", [
        ("آباد بیرونی", 31.9, 54.3, "10"),         # یزد — بیرون استان
    ])
    rep = village.enrich(bank, shp, boundary, official)

    assert rep["points_inside_province"] == 0
    assert rep["added"] == 0


# ---------------------------------------------------------------------------
# ۳) شهرستان: از فهرست رسمی، و در نبود آن رأی اکثریت کد ناحیه
# ---------------------------------------------------------------------------
def test_county_from_official_and_area_code_majority(env):
    bank, boundary, tmp, _ = env
    official = _official(tmp / "official.csv", [
        ("الف اباد", "village", "شهرستان الف"),
        ("ب اباد", "village", "شهرستان الف"),
        ("ج اباد", "village", "شهرستان الف"),
        ("د اباد", "village", "شهرستان الف"),
    ])
    # کد ۷۷: سه نام شناخته‌شده با شهرستان یکسان ⇒ اکثریت روشن
    # کد ۹۹: فقط یک رأی ⇒ نباید شهرستان بگیرد
    shp = _write_shp(tmp / "v.shp", [
        ("الف اباد", 38.10, 48.10, "77"),
        ("ب اباد", 38.11, 48.11, "77"),
        ("ج اباد", 38.12, 48.12, "77"),
        ("نام ناشناس", 38.13, 48.13, "77"),
        ("د اباد", 38.20, 48.20, "99"),
        ("تنها رای", 38.21, 48.21, "99"),
    ])
    rep = village.enrich(bank, shp, boundary, official)

    assert rep["added"] == 6
    assert rep["placed_with_county"] == 5          # ۴ نام رسمی + نام ناشناس
    assert rep["area_codes_mapped"] == 1
    assert _county(bank, "نام ناشناس") == "شهرستان الف"
    assert _county(bank, "تنها رای") in ("", None)
    assert _county(bank, "الف اباد") == "شهرستان الف"


# ---------------------------------------------------------------------------
# ۴) اجرای دوباره بی‌اثر است
# ---------------------------------------------------------------------------
def test_second_run_is_idempotent(env):
    bank, boundary, tmp, official = env
    shp = _write_shp(tmp / "v.shp", [
        ("آباد تازه یک", 38.05, 48.05, "10"),
        ("آباد تازه دو", 38.06, 48.06, "10"),
    ])
    baseline = _count(bank, "SELECT COUNT(*) FROM places WHERE source=?",
                      (SOURCE,))
    first = village.enrich(bank, shp, boundary, official)
    second = village.enrich(bank, shp, boundary, official)

    assert first["added"] == 2
    assert second["added"] == 0
    assert second["merged_into_existing"] == 2
    assert _count(bank, "SELECT COUNT(*) FROM places WHERE source=?",
                  (SOURCE,)) == baseline + 2


# ---------------------------------------------------------------------------
# ۵) بانک همراه مخزن: تعداد، منبع، فراداده، محدودهٔ مختصات
# ---------------------------------------------------------------------------
def test_bundled_bank_contains_village_shp_places():
    assert BANK.is_file(), "بانک مکان‌های اردبیل همراه مخزن نیست"
    stats = PlaceGazetteer(BANK).stats()

    assert stats["places"] >= 2200
    assert stats["by_source"].get(SOURCE, 0) >= 1188
    assert stats["by_source"].get("GeoNames cities1000 (CC BY 4.0)") == 26
    assert stats["by_type"].get("city", 0) >= 32
    assert stats["by_type"].get("village", 0) >= 2100

    db = sqlite3.connect(BANK)
    try:
        assert db.execute("SELECT COUNT(*) FROM places WHERE source IS NULL "
                          "OR TRIM(source)=''").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM places WHERE (lat<37.0 OR "
                          "lat>39.8 OR lon<46.7 OR lon>48.9) AND place_type<>'substation'").fetchone()[0] == 0
    finally:
        db.close()

    meta = stats["metadata"]
    assert "Village.shp" in meta.get("sources", "; ")
    assert int(meta.get("village_shp_places", "0")) >= 1188
    assert int(meta.get("village_shp_merged", "0")) >= 2000


def test_merge_radius_is_three_km():
    assert village.MERGE_RADIUS_M == 3000.0
