import sqlite3
from types import SimpleNamespace

from switchloc.application.outage_review import OutageReviewStore, suggest_event_places
from switchloc.geography.places import Place, PlaceGazetteer


def test_place_suggestions_are_only_suggestions(tmp_path):
    gaz = PlaceGazetteer(tmp_path / 'places.sqlite')
    gaz.upsert([Place('p1', 'زرج آباد', 38.1, 48.2)])
    rec = SimpleNamespace(id='e1', notes='خاموشی روستای زرج آباد', device_raw='')
    result = suggest_event_places([rec], gaz)
    assert result[0].event_id == 'e1'
    assert result[0].matches[0].place.place_id == 'p1'


def test_review_store_persists_only_explicit_confirmations(tmp_path):
    db = tmp_path / 'project.sqlite'
    store = OutageReviewStore(db)
    store.save('e1', 'z1', place_id='p1', place_name='زرج آباد', status='confirmed')
    store.save('e2', '', status='rejected')
    assert store.confirmed_event_to_zone() == {'e1': 'z1'}
    assert store.load()['e1']['place_name'] == 'زرج آباد'


def test_review_store_rejects_empty_zone_and_invalid_status(tmp_path):
    store = OutageReviewStore(tmp_path / 'project.sqlite')
    try:
        store.save('e1', '', status='confirmed')
        assert False, 'expected ValueError'
    except ValueError:
        pass
    try:
        store.save('e1', 'z1', status='auto')
        assert False, 'expected ValueError'
    except ValueError:
        pass


def test_suggestions_search_outage_substation_field_first(tmp_path):
    from types import SimpleNamespace
    from switchloc.geography.places import Place, PlaceGazetteer
    from switchloc.application.outage_review import suggest_event_places

    gaz = PlaceGazetteer(tmp_path / "places.sqlite")
    gaz.upsert([Place("p1", "عباس آباد", 38.1, 48.2, county="کوثر",
                      source="test")])
    rec = SimpleNamespace(id="event-1", substation="عباس آباد",
                          notes="برخورد پرنده", device_raw="کلید")
    suggestions = suggest_event_places([rec], gaz)
    assert len(suggestions) == 1
    assert suggestions[0].matches[0].place.place_id == "p1"


def test_substation_candidate_takes_precedence_over_notes(tmp_path):
    gaz = PlaceGazetteer(tmp_path / "places.sqlite")
    gaz.upsert([Place("station-place", "عباس آباد", 38.1, 48.2),
                Place("notes-place", "زرج آباد", 38.2, 48.3)])
    rec = SimpleNamespace(id="e2", substation="عباس آباد",
                          notes="خاموشی در زرج آباد", device_raw="")
    result = suggest_event_places([rec], gaz)
    assert [m.place.place_id for m in result[0].matches] == ["station-place"]
