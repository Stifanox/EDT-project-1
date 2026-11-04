"""Testy `SqliteReviewRepository` poza kontraktem (D2): trwałość, schemat, wątki, procesy."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from opimon import config, services
from opimon.models import Prediction, Sentiment, Target
from opimon.storage import SqliteReviewRepository
from opimon.storage.db import SCHEMA_VERSION, connect, from_db_time, to_db_time
from tests.conftest import NOW, make_review

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def repo() -> SqliteReviewRepository:
    r = SqliteReviewRepository(config.DB_PATH)
    yield r
    r.close()


def test_data_survives_restart(tiny_reviews, tiny_targets):
    with SqliteReviewRepository(config.DB_PATH) as first:
        for t in tiny_targets:
            first.save_target(t)
        first.add_reviews(tiny_reviews)
        first.save_predictions([Prediction("test:r1", "m", 0.75)])
    with SqliteReviewRepository(config.DB_PATH) as second:          # „restart aplikacji”
        assert second.count_reviews() == 5
        assert [t.id for t in second.list_targets()] == ["test:t2", "test:t1"]
        assert second.get_predictions("m")["test:r1"].score == 0.75
        assert second.get_review("test:r2").label is Sentiment.NEGATIVE


def test_schema_indexes_and_pragmas(repo):
    conn = sqlite3.connect(config.DB_PATH)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert {"targets", "reviews", "predictions"} <= names
    assert {"ix_reviews_target_created", "ix_reviews_created", "ix_predictions_model"} <= names
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    conn.close()


def test_newer_schema_is_rejected(tmp_path):
    path = tmp_path / "future.db"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(RuntimeError, match="nowszy schemat"):
        connect(path)


def test_missing_directory_is_created(tmp_path):
    path = tmp_path / "a" / "b" / "opimon.db"
    with SqliteReviewRepository(path) as r:
        assert r.count_reviews() == 0
    assert path.exists()


def test_factory_reads_db_path_at_call_time(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "other" / "x.db")
    repo = services._make_repository()
    assert isinstance(repo, SqliteReviewRepository) and repo.path == tmp_path / "other" / "x.db"
    repo.close()


def test_dates_are_utc_aware_and_ordered_across_timezones(repo):
    warsaw = timezone(timedelta(hours=1))
    a = make_review("a", "text a", 0)
    a.created_at = datetime(2026, 11, 1, 13, 0, tzinfo=warsaw)        # = 12:00 UTC
    b = make_review("b", "text b", 0)
    b.created_at = datetime(2026, 11, 1, 12, 30, tzinfo=UTC)          # nowsza
    repo.add_reviews([a, b])
    got = repo.list_reviews()
    assert [r.external_id for r in got] == ["b", "a"]
    assert got[1].created_at == datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    assert all(r.created_at.tzinfo is not None and r.fetched_at.tzinfo is not None for r in got)
    assert repo.latest_review_time("test:t1") == b.created_at


def test_time_format_sorts_lexicographically():
    early = to_db_time(datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC))
    late = to_db_time(datetime(2026, 1, 2, 3, 4, 5, 1, tzinfo=UTC))
    assert len(early) == len(late) and early < late
    assert from_db_time(late) == datetime(2026, 1, 2, 3, 4, 5, 1, tzinfo=UTC)
    with pytest.raises(ValueError):
        to_db_time(datetime(2026, 1, 1))


def test_unicode_extra_and_nulls_roundtrip(repo):
    r = make_review("u", "Zażółć gęślą jaźń 🎮 – „cudzysłów”", 3)
    r.extra = {"nested": {"a": [1, 2]}, "flag": True, "none": None}
    r.author, r.url, r.rating = None, None, None
    repo.add_reviews([r])
    got = repo.get_review("test:u")
    assert got.text == r.text and got.extra == r.extra
    assert (got.author, got.url, got.rating, got.label) == (None, None, None, None)


def test_get_predictions_with_many_ids(repo):
    reviews = [make_review(f"m{i}", f"tekst {i}", i / 10) for i in range(1200)]
    repo.add_reviews(reviews)
    repo.save_predictions(Prediction(r.id, "m", 0.5) for r in reviews[::2])
    ids = [r.id for r in reviews] + ["test:missing"]
    assert len(repo.get_predictions("m", ids)) == 600
    assert len(repo.reviews_without_prediction("m")) == 600


def test_failed_write_is_rolled_back(repo, tiny_reviews):
    """Błąd w środku zapisu (NOT NULL) -> cała paczka wycofana, baza nadal działa."""
    repo.add_reviews(tiny_reviews[:2])
    broken = make_review("broken", "x", 1)
    broken.text = None                       # narusza NOT NULL dopiero w SQLite
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_reviews([tiny_reviews[2], broken])
    assert repo.count_reviews() == 2 and repo.get_review("test:r3") is None
    assert repo.add_reviews([tiny_reviews[2]]) == 1


def test_concurrent_threads(repo):
    errors: list[BaseException] = []

    def worker(n: int) -> None:
        try:
            for i in range(25):
                rid = f"w{n}-{i}"
                repo.add_reviews([make_review(rid, f"opinia {rid}", i)])
                repo.save_predictions([Prediction(f"test:{rid}", "m", 0.6)])
                repo.list_reviews(limit=5)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert repo.count_reviews() == 200 and len(repo.get_predictions("m")) == 200


def test_second_process_sees_writes(repo, tiny_targets):
    """Drugi proces (jak CLI z D5) zapisuje do tej samej bazy; GUI widzi to bez restartu."""
    repo.save_target(tiny_targets[0])
    assert repo.count_reviews() == 0
    code = (
        "import sys; from opimon.storage import SqliteReviewRepository; "
        "from tests.conftest import make_review; "
        "r = SqliteReviewRepository(sys.argv[1]); "
        "print(r.add_reviews([make_review(f'p{i}', 'z innego procesu', i) for i in range(3)]))"
    )
    out = subprocess.run([sys.executable, "-c", code, str(config.DB_PATH)], cwd=ROOT,
                         capture_output=True, text=True, timeout=60, check=True)
    assert out.stdout.strip() == "3"
    assert repo.count_reviews("test:t1") == 3
    assert repo.latest_review_time("test:t1") == NOW - timedelta(hours=0)


def test_target_upsert_keeps_reviews(repo, tiny_reviews):
    repo.save_target(Target("test", "t1", "Stara nazwa"))
    repo.add_reviews(tiny_reviews)
    repo.save_target(Target("test", "t1", "Nowa nazwa", "https://example.com"))
    assert repo.get_target("test:t1") == Target("test", "t1", "Nowa nazwa", "https://example.com")
    assert repo.count_reviews("test:t1") == 3


def test_services_persist_between_builds(monkeypatch):
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", True)
    first = services.build_services()
    n = first.repository.count_reviews()
    assert n == 195
    second = services.build_services()                  # restart: nie wczytuje próbek ponownie
    assert second.repository.count_reviews() == n
    assert second.repository.reviews_without_prediction("lexicon_stub") == []
