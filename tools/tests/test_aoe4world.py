import json

import pytest

from aoe4 import aoe4world
from aoe4.constants import UNITS


V1 = json.dumps({'data': [{'id': "scout"}]})
V2 = json.dumps({'data': [{'id': "scout"}, {'id': "spearman"}]})


@pytest.fixture
def upstream(tmp_path, monkeypatch):
    """Fake aoe4world: `state` holds the latest commit and file, `fetches` records each request"""
    state = {'commit': "c1", 'body': V1, 'etag': "e1"}
    fetches = []

    def fake_fetch(name, etag):
        fetches.append(etag)
        if etag == state['etag']:
            return None, etag
        return state['body'], state['etag']

    monkeypatch.setattr(aoe4world, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(aoe4world, "_INDEX_FILE", tmp_path / "index.json")
    monkeypatch.setattr(aoe4world, "_latest_commit", lambda: state['commit'])
    monkeypatch.setattr(aoe4world, "_fetch", fake_fetch)
    return state, fetches


def _ids():
    return [f['id'] for f in aoe4world.load_unified(UNITS, "english")]


def test_downloads_once_then_reuses_cache_until_a_new_commit(upstream):
    state, fetches = upstream
    assert _ids() == ["scout"]
    assert _ids() == ["scout"]
    assert fetches == [None]


def test_new_commit_with_unchanged_file_keeps_cache(upstream):
    state, fetches = upstream
    _ids()
    state['commit'] = "c2"
    assert _ids() == ["scout"]
    assert _ids() == ["scout"]
    assert fetches == [None, "e1"]


def test_new_commit_with_changed_file_redownloads(upstream):
    state, fetches = upstream
    _ids()
    state.update(commit="c2", body=V2, etag="e2")
    assert _ids() == ["scout", "spearman"]
    assert fetches == [None, "e1"]


def test_offline_uses_cache(upstream, monkeypatch):
    state, fetches = upstream
    _ids()
    monkeypatch.setattr(aoe4world, "_latest_commit", lambda: None)
    assert _ids() == ["scout"]
    assert fetches == [None]


@pytest.mark.parametrize("civ", ["../english", "english/../../x", "Eng"])
def test_civ_cannot_escape_cache_or_url(civ):
    with pytest.raises(aoe4world.Aoe4WorldError):
        aoe4world.load_unified(UNITS, civ)
