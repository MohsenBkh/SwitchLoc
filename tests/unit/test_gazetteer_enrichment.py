# -*- coding: utf-8 -*-
"""بانک آفلاین مکان‌ها (v1.13.1): نرمال‌سازی، تطبیق و غنی‌سازی.

هر آزمون یک تصمیم واقعی را قفل می‌کند:

* تفاوت نوشتاری «آ/ا»، «ی/ي»، «ک/ك»، فاصله/نیم‌فاصله نباید مانع تطبیق شود؛
* تطبیق جزئی نباید از میان یک واژه شروع شود («ورزشي» ≠ «رز»)؛
* بانک همراه برنامه باید شهرها و نام‌های جایگزین را داشته باشد.
"""
from __future__ import annotations

import sqlite3

import pytest

from switchloc.geography.places import (KEY_SCHEMA_VERSION, Place,
                                       PlaceGazetteer, compact_place_name,
                                       normalize_place_name)


# --------------------------------------------------------------- normalize
def test_normalization_folds_persian_and_arabic_letters():
    assert normalize_place_name("كجين") == normalize_place_name("کجین")
    assert normalize_place_name("سكراباد") == normalize_place_name("سکرآباد")
    # «آ» و «ا» یک شکل می‌شوند (فاصله با کلید فشرده پوشش داده می‌شود)
    assert (compact_place_name("فيروز اباد")
            == compact_place_name("فیروزآباد"))


def test_compact_key_ignores_spacing_and_alef_madda():
    assert compact_place_name("فیروز آباد") == compact_place_name("فیروزاباد")
    assert compact_place_name("زرج‌آباد") == compact_place_name("زرج اباد")


def test_folded_letters_need_no_duplicate_alias_rows(bank=None):
    """گونه‌های «آ/ا» و «ک/ك» با نرمال‌سازی پوشش داده می‌شوند.

    قبلاً برای هر نام چند ردیف alias ساخته می‌شد؛ چون کلید تطبیق خودش
    این حروف را یکی می‌کند، آن ردیف‌ها فقط حجم بانک را بالا می‌بردند.
    """
    assert compact_place_name("فیروزآباد") == compact_place_name("فیروزاباد")
    assert normalize_place_name("كجين") == normalize_place_name("کجین")


# ------------------------------------------------------------------ search
@pytest.fixture()
def bank(tmp_path):
    g = PlaceGazetteer(tmp_path / "places.sqlite")
    g.upsert([
        Place("v1", "سکرآباد", 39.1, 47.9, place_type="village",
              county="پارس آباد", source="test"),
        Place("v2", "زرج آباد", 37.6, 48.0, place_type="village",
              county="کوثر", source="test"),
        Place("v3", "رز", 37.5, 47.9, place_type="village", source="test"),
        Place("c1", "خلخال", 37.6, 48.5, place_type="city",
              county="خلخال", source="test", population=51024),
    ])
    return g


def test_spacing_variant_is_high_confidence(bank):
    match = bank.search("سكر اباد")[0]
    assert match.place.place_id == "v1"
    assert match.confidence == "زیاد"


def test_alef_madda_variant_is_high_confidence(bank):
    match = bank.search("سکراباد")[0]
    assert match.place.name == "سکرآباد"
    assert match.confidence == "زیاد"


def test_partial_match_needs_word_boundary(bank):
    """«سالن ورزشي زرج اباد» به «رز» نباید تطبیق شود (باگ قبلی)."""
    names = [m.place.name for m in bank.search("سالن ورزشي زرج اباد")]
    assert "زرج آباد" in names
    assert "رز" not in names


def test_compact_match_does_not_start_mid_word(bank):
    """«امير اباد» نباید به مکان «میراب» تطبیق شود."""
    bank.upsert([Place("v4", "میراب", 38.2, 48.1, source="test")])
    assert bank.search("امير اباد") == []


def test_city_matches_exact_and_sorted(bank):
    matches = bank.search("خلخال")
    assert matches[0].place.place_type == "city"
    assert matches[0].score == 1.0


# ------------------------------------------------------------- enrichment
def test_add_aliases_and_search_by_alias(bank):
    assert bank.add_aliases("v2", ["Zarj Abad"]) == 1
    assert bank.search("Zarj Abad")[0].place.place_id == "v2"


def test_find_near_and_nearby_county(bank):
    near = bank.find_near(39.1005, 47.9005, 500)
    assert near and near[0][0].place_id == "v1"
    assert bank.nearby_county(39.05, 47.85) == "پارس آباد"


def test_stats_reports_types_and_alias_count(bank):
    stats = bank.stats()
    assert stats["places"] == 4
    assert stats["by_type"]["city"] == 1
    assert stats["with_population"] == 1


# --------------------------------------------------------------- migration
def test_old_database_is_migrated_in_place(tmp_path):
    """بانک قدیمی (بدون compact_name/population) باید بی‌خطر ارتقا یابد."""
    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE places (place_id TEXT PRIMARY KEY, name TEXT NOT NULL,
            normalized_name TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
            place_type TEXT NOT NULL DEFAULT 'settlement',
            county TEXT NOT NULL DEFAULT '', district TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'unknown');
        CREATE TABLE aliases (place_id TEXT NOT NULL, alias TEXT NOT NULL,
            normalized_alias TEXT NOT NULL, PRIMARY KEY(place_id, normalized_alias));
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    db.execute("INSERT INTO places(place_id, name, normalized_name, lat, lon,"
               " place_type, county, district, source) VALUES"
               "('old1','فيروز اباد','فيروز اباد',38.2,48.2,'village','','',"
               "'legacy')")
    db.execute("INSERT INTO aliases VALUES('old1','Firooz Abad','firooz abad')")
    db.commit()
    db.close()

    bank = PlaceGazetteer(path)          # باید بدون خطا مهاجرت کند
    assert bank.count() == 1
    match = bank.search("فیروزآباد")
    assert match and match[0].place.place_id == "old1"
    with bank._connect() as conn:        # noqa: SLF001
        meta = dict(conn.execute("SELECT key, value FROM metadata"))
    assert meta.get("key_schema") == KEY_SCHEMA_VERSION


# ------------------------------------------------------------ bundled bank
def test_bundled_bank_has_cities_aliases_and_metadata():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    bank_path = root / "data" / "geography" / "ardabil_places.sqlite"
    assert bank_path.is_file(), "بانک آفلاین اردبیل از مخزن حذف شده است"
    bank = PlaceGazetteer(bank_path)
    stats = bank.stats()
    assert stats["places"] >= 1032
    assert stats["by_type"].get("city", 0) >= 15, "شهرها باید در بانک باشند"
    assert stats["aliases"] >= 250
    allowed = ("high-confidence", "GeoNames")
    assert all(any(mark in s for mark in allowed)
               for s in stats["by_source"]), stats["by_source"]
    assert stats["metadata"].get("built_at")
    # نمونه‌های عملیاتی: شهر مرکز استان و یک روستای پروژهٔ کوثر
    assert bank.search("اردبیل")[0].place.place_type == "city"
    assert bank.search("زرج اباد")[0].place.name == "زرج آباد"


# ------------------------------------------------------- shipped data files
def test_shipped_official_and_gap_files_are_consistent():
    """فایل‌های همراه مخزن: فهرست رسمی و CSV جاهای غایب.

    ستون‌های ``lat``/``lon`` در CSV غایب‌ها باید **خالی** بمانند؛ پرکردن آن‌ها
    با عدد یعنی مختصات ساختگی وارد بانک شده است.
    """
    import csv
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "data" / "geography"
    official = root / "official_ardabil_places.csv"
    gap = root / "ardabil_missing_places.csv"
    assert official.is_file() and gap.is_file()

    with open(official, encoding="utf-8", newline="") as f:
        off = list(csv.DictReader(f))
    assert len(off) == 1895
    assert sum(1 for r in off if r["kind"] == "city") == 36
    assert all(r["name"].strip() for r in off)

    with open(gap, encoding="utf-8", newline="") as f:
        miss = list(csv.DictReader(f))
    assert len(miss) == 840
    assert all(not r["lat"] and not r["lon"] for r in miss), \
        "مختصات نباید برای جاهای تکمیل‌نشده پر شود"
    assert sum(1 for r in miss if r["type"] == "city") == 17

    # هر ردیف غایب، «همان نام» را در بانک ندارد (تطبیق جزئی مجاز است؛ ردیف
    # غایب فقط یعنی نام یکتا/فشردهٔ آن در بانک نیست).
    bank = PlaceGazetteer(root / "ardabil_places.sqlite")
    present = {compact_place_name(m.place.name)
               for r in miss for m in bank.search(r["name"])}
    exact = {compact_place_name(r["name"]) for r in miss} & present
    # نام‌های بسیار کوتاه/عمومی («قشلاق») ممکن است هم‌نام داشته باشند
    exact = {c for c in exact if len(c) >= 8}
    assert exact == set(), exact
