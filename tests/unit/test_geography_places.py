from switchloc.geography.places import Place, PlaceGazetteer, normalize_place_name


def test_persian_name_normalization():
    assert normalize_place_name('روستای كُجين') == normalize_place_name('کجین')
    assert normalize_place_name('آبادی ۱۲') == normalize_place_name('آبادی 12')


def test_gazetteer_upsert_and_alias_search(tmp_path):
    db = PlaceGazetteer(tmp_path / 'places.sqlite')
    db.upsert([Place('osm:1', 'کجین', 38.1, 48.2, aliases=('كجين', 'روستای کجین'), source='test')])
    assert db.count() == 1
    found = db.search('خطای روستای کجین')
    assert found and found[0].place.place_id == 'osm:1'
    assert found[0].confidence == 'متوسط'  # substring candidate, not exact identity
    exact = db.search('کجین')
    assert exact[0].confidence == 'زیاد'


def test_csv_import(tmp_path):
    f = tmp_path / 'places.csv'
    f.write_text('id,name,lat,lon,type,county,district,aliases\n1,اردبیل,38.25,48.30,city,,,Ardabil\n', encoding='utf-8')
    db = PlaceGazetteer(tmp_path / 'places.sqlite')
    assert db.import_csv(f) == 1
    assert db.search('Ardabil')[0].place.name == 'اردبیل'


def test_bundled_ardabil_gazetteer_matches_release_claim():
    """سند انتشار ۱.۱۰.۱ ادعا می‌کند ۱٬۰۰۶ سکونتگاه با اطمینان بالا در
    بانک آفلاین مخزن وارد شده‌اند. این آزمون صرفاً بررسی فقط-خواندنی
    است و هیچ فایلی ایجاد/تغییر نمی‌کند."""
    import sqlite3
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    bank = root / "data" / "geography" / "ardabil_places.sqlite"
    assert bank.is_file(), "بانک آفلاین اردبیل از مخزن حذف شده است"
    with sqlite3.connect(f"file:{bank}?mode=ro", uri=True) as db:
        n, = db.execute("select count(*) from places").fetchone()
        beyond, = db.execute(
            "select count(*) from places "
            "where lat not between -90 and 90 or lon not between -180 and 180"
        ).fetchone()
        sources = [r[0] for r in db.execute(
            "select distinct source from places")]
    assert n >= 1006
    assert beyond == 0
    assert all("high-confidence" in s for s in sources)
