"""Test kontraktu ReviewRepository. O1: dopisz SQLite do REPOSITORY_FACTORIES (D2).

Fabryki czytają `config.DB_PATH` w chwili wywołania – fixture `isolated_data_dir`
podmienia go na katalog tymczasowy.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from opimon import config
from opimon.interfaces import ReviewRepository
from opimon.models import Prediction, Target
from opimon.storage import InMemoryReviewRepository, SqliteReviewRepository
from tests.conftest import NOW, make_review

REPOSITORY_FACTORIES = [
    pytest.param(InMemoryReviewRepository, id="memory"),
    pytest.param(lambda: SqliteReviewRepository(config.DB_PATH), id="sqlite"),
]


@pytest.fixture(params=REPOSITORY_FACTORIES)
def repo(request, tiny_reviews, tiny_targets) -> ReviewRepository:
    r = request.param()
    for t in tiny_targets:
        r.save_target(t)
    assert r.add_reviews(tiny_reviews) == len(tiny_reviews)
    return r


def test_implements_protocol(repo):
    assert isinstance(repo, ReviewRepository)


def test_add_is_idempotent(repo, tiny_reviews):
    assert repo.add_reviews(tiny_reviews) == 0
    assert repo.count_reviews() == 5
    assert repo.count_reviews("test:t1") == 3


def test_get_review_roundtrip(repo, tiny_reviews):
    got = repo.get_review("test:r1")
    assert got is not None
    assert (got.text, got.created_at, got.label) == (
        tiny_reviews[0].text, tiny_reviews[0].created_at, tiny_reviews[0].label)
    assert repo.get_review("test:nope") is None


def test_list_order_and_filters(repo):
    ids = [r.id for r in repo.list_reviews()]
    assert ids == ["test:r1", "test:r2", "test:r3", "test:r4", "test:r5"]
    assert [r.id for r in repo.list_reviews("test:t2")] == ["test:r4", "test:r5"]
    assert len(repo.list_reviews(limit=2)) == 2
    since = NOW - timedelta(hours=30)              # włącznie
    assert [r.id for r in repo.list_reviews(since=since)] == ["test:r1", "test:r2", "test:r3"]
    until = NOW - timedelta(hours=30)              # wyłącznie
    assert [r.id for r in repo.list_reviews(until=until)] == ["test:r4", "test:r5"]


def test_targets(repo):
    assert [t.name for t in repo.list_targets()] == ["Gra druga", "Gra pierwsza"]
    repo.save_target(Target("test", "t1", "Gra pierwsza (zmieniona)"))
    assert repo.get_target("test:t1").name == "Gra pierwsza (zmieniona)"
    assert len(repo.list_targets()) == 2
    assert repo.latest_review_time("test:t1") == NOW - timedelta(hours=1)
    assert repo.latest_review_time("test:none") is None


def test_predictions_upsert_and_pending(repo):
    assert len(repo.reviews_without_prediction("m")) == 5
    repo.save_predictions([Prediction("test:r1", "m", 0.9), Prediction("test:r2", "m", 0.1)])
    repo.save_predictions([Prediction("test:r1", "m", 0.8)])           # upsert
    preds = repo.get_predictions("m")
    assert set(preds) == {"test:r1", "test:r2"} and preds["test:r1"].score == 0.8
    assert repo.get_predictions("m", ["test:r2", "test:r9"]).keys() == {"test:r2"}
    assert repo.get_predictions("m", []) == {}
    assert repo.get_predictions("other") == {}
    assert [r.id for r in repo.reviews_without_prediction("m")] == ["test:r3", "test:r4",
                                                                    "test:r5"]
    assert [r.id for r in repo.reviews_without_prediction("m", "test:t1")] == ["test:r3"]
    assert repo.delete_predictions("m") == 2
    assert repo.get_predictions("m") == {}


def test_remove_target_cascades(repo):
    repo.save_predictions([Prediction("test:r4", "m", 0.2)])
    repo.remove_target("test:t2")
    assert repo.get_target("test:t2") is None
    assert repo.count_reviews() == 3 and repo.count_reviews("test:t2") == 0
    assert repo.get_predictions("m") == {}
    repo.remove_target("test:unknown")             # bez wyjątku


def test_extra_and_optional_fields_roundtrip(repo):
    r = make_review("r9", "Tekst", 5)
    r.extra = {"playtime_hours": 12.5, "helpful": 3}
    r.rating = 8.0
    repo.add_reviews([r])
    got = repo.get_review("test:r9")
    assert got.extra == {"playtime_hours": 12.5, "helpful": 3} and got.rating == 8.0
    assert got.label is None
