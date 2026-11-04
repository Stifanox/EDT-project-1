"""Test kontraktu ReviewSource – KAŻDE źródło musi go przejść.

O1: dopisz swoje źródło do SOURCE_CASES (D1, D3). Źródła sieciowe testuj OFFLINE:
podmień transport HTTP na nagrane odpowiedzi (fixture JSON/HTML w `tests/fixtures/`).
Wariant „na żywo” oznacz `marks=pytest.mark.network`.

Każdy przypadek: krotka (fabryka źródła, zapytanie, które coś znajduje).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from opimon.errors import SourceError
from opimon.interfaces import ReviewSource
from opimon.models import Target
from opimon.sources import SampleSource, SteamReviewSource
from tests.fixtures.steam.fake import make_offline_steam_source

SOURCE_CASES = [
    pytest.param((SampleSource, "starfall"), id="sample"),
    pytest.param((make_offline_steam_source, "dota"), id="steam-offline"),
    pytest.param((SteamReviewSource, "dota"), id="steam-live", marks=pytest.mark.network),
]


@pytest.fixture(params=SOURCE_CASES)
def case(request) -> tuple[ReviewSource, str]:
    factory, query = request.param
    return factory(), query


def test_implements_protocol(case):
    source, _ = case
    assert isinstance(source, ReviewSource)
    assert source.name and source.label


def test_find_targets(case):
    source, query = case
    targets = source.find_targets(query, limit=5)
    assert targets and len(targets) <= 5
    assert all(isinstance(t, Target) and t.source == source.name for t in targets)
    assert source.find_targets("") == [] and source.find_targets("   ") == []


def test_fetch_semantics(case):
    source, query = case
    target = source.find_targets(query)[0]
    reviews = source.fetch(target, limit=20)
    assert 0 < len(reviews) <= 20
    assert len({r.id for r in reviews}) == len(reviews), "powtórzone id"
    assert all(r.source == source.name and r.target_id == target.id for r in reviews)
    assert all(r.text.strip() and r.text == r.text.strip() for r in reviews)
    assert all(r.created_at.tzinfo is not None for r in reviews)
    times = [r.created_at for r in reviews]
    assert times == sorted(times, reverse=True), "opinie mają być od najnowszej"


def test_fetch_since_is_incremental(case):
    source, query = case
    target = source.find_targets(query)[0]
    reviews = source.fetch(target, limit=20)
    if len(reviews) < 2:
        pytest.skip("za mało opinii do sprawdzenia `since`")
    cut = reviews[len(reviews) // 2].created_at
    newer = source.fetch(target, limit=20, since=cut)
    assert newer and all(r.created_at > cut for r in newer)
    assert source.fetch(target, limit=20, since=reviews[0].created_at + timedelta(days=1)) == []


def test_unknown_target_raises_source_error(case):
    source, _ = case
    with pytest.raises(SourceError):
        source.fetch(Target(source.name, "no-such-target-0000", "?"), limit=5)
