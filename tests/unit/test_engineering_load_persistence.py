"""Persist feeder P/Q and model settings independently for each project."""
import sqlite3

import pytest

from switchloc.persistence.engineering_load import (
    load_load_model, merge_scoped_load_model, save_load_model,
)


def test_project_isolation_reopen_save_as_and_updates(tmp_path):
    a, b, clone = (tmp_path / name for name in ('a.sqlite', 'b.sqlite', 'clone.sqlite'))
    model = {'level': 'scaled', 'loading_factor': .7, 'substitute_factor': .4,
             'feeder_pq': {'F2 - MESHKIN': {'p_kw': 100, 'q_kvar': 0},
                           'F2 - HADIDMOBTAKERAN': {'p_kw': 200, 'q_kvar': 30}}}
    save_load_model(str(a), model)
    assert load_load_model(str(b)) == {}
    other = {'level': 'scaled', 'feeder_pq': {'F2 - MESHKIN': {'p_kw': 50, 'q_kvar': 5}}}
    save_load_model(str(b), other)
    assert load_load_model(str(a)) == model
    with sqlite3.connect(a) as src, sqlite3.connect(clone) as dest:
        src.backup(dest)
    assert load_load_model(str(clone)) == model
    updated = merge_scoped_load_model(model, {'level': 'scaled', 'feeder_pq': {}}, ['F2 - MESHKIN'])
    save_load_model(str(clone), updated)
    assert load_load_model(str(clone))['feeder_pq'] == {'F2 - HADIDMOBTAKERAN': {'p_kw': 200, 'q_kvar': 30}}
    assert load_load_model(str(a)) == model
    assert load_load_model(str(b)) == other


def test_scope_updates_one_feeder_without_collapsing_similar_tokens():
    old = {'feeder_pq': {'F2 - MESHKIN': {'p_kw': 1}, 'F2 - HADIDMOBTAKERAN': {'p_kw': 2}}}
    new = {'level': 'scaled', 'feeder_pq': {'F2 - MESHKIN': {'p_kw': 3, 'q_kvar': 0}}}
    got = merge_scoped_load_model(old, new, ['F2 - MESHKIN'])
    assert got['feeder_pq']['F2 - MESHKIN']['p_kw'] == 3
    assert got['feeder_pq']['F2 - HADIDMOBTAKERAN']['p_kw'] == 2
    assert old['feeder_pq']['F2 - MESHKIN']['p_kw'] == 1


def test_invalid_destination_reports_failure(tmp_path):
    with pytest.raises(sqlite3.Error):
        save_load_model(str(tmp_path / 'missing' / 'p.sqlite'), {'feeder_pq': {}})


def test_corrupt_model_is_not_silently_treated_as_missing(tmp_path):
    from switchloc.persistence.store import ProjectStore
    path = tmp_path / 'broken.sqlite'
    save_load_model(str(path), {'feeder_pq': {}})
    store = ProjectStore(path)
    store.conn.execute("UPDATE project_kv SET value_json = '{broken' WHERE key = ?", ('engineering_load_model_v1',))
    store.close()
    with pytest.raises(ValueError):
        load_load_model(str(path))
