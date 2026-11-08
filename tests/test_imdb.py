"""Walidacja IMDB, izolacja podziału oraz unieważnianie cache."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from opimon import config
from opimon.errors import DatasetUnavailableError
from opimon.models import Sentiment
from opimon.sentiment.imdb import ImdbTrainingData

FIXTURE = Path(__file__).parent / "fixtures" / "imdb_mini.csv"


def install_imdb_fixture() -> ImdbTrainingData:
    config.DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURE, config.DATASETS_DIR / "IMDB Dataset.csv")
    return ImdbTrainingData()


def test_cache_cleaning_limits_and_no_overlap(monkeypatch):
    provider = install_imdb_fixture()
    dataset = provider.load()
    assert not ({ex.text for ex in dataset.train} & {ex.text for ex in dataset.test})
    assert all("<br" not in ex.text for ex in dataset.train + dataset.test)
    monkeypatch.setattr(provider, "_read", lambda _: pytest.fail("Pominięto cache"))
    assert provider.load().test == dataset.test
    for n in (0, 1, 3, 6):
        limited = provider.load(max_train=n, max_test=n)
        for part in (limited.train, limited.test):
            assert len(part) <= n
            pos = sum(ex.label is Sentiment.POSITIVE for ex in part)
            assert abs(2 * pos - len(part)) <= 1
    with pytest.raises(ValueError):
        provider.load(max_train=-1)


def test_cache_changes_with_source():
    provider = install_imdb_fixture()
    first = provider.load()
    path = config.DATASETS_DIR / "IMDB Dataset.csv"
    path.write_text(path.read_text().replace("excellent", "exceptionally excellent"))
    second = provider.load()
    assert first.train + first.test != second.train + second.test
    assert len(list(config.CACHE_DIR.glob("imdb-*.json"))) == 2


def test_corrupt_cache_is_rebuilt():
    provider = install_imdb_fixture()
    first = provider.load()
    next(config.CACHE_DIR.glob("imdb-*.json")).write_text("broken")
    assert provider.load().test == first.test


def test_official_split_and_duplicate_isolation():
    config.DATASETS_DIR.mkdir(parents=True)
    with (config.DATASETS_DIR / "IMDB Dataset.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["review", "sentiment", "split"])
        for split in ("train", "test"):
            for sentiment in ("positive", "negative"):
                writer.writerow([f"{split} {sentiment} movie", sentiment, split])
                writer.writerow(["repeated movie", "positive", split])
    dataset = ImdbTrainingData().load()
    assert not ({ex.text for ex in dataset.train} & {ex.text for ex in dataset.test})
    assert any(ex.text == "test negative movie" for ex in dataset.test)


@pytest.mark.parametrize("content", ["text,label\nx,positive", "review,sentiment\nx,wrong"])
def test_invalid_csv_has_readable_error(content):
    config.DATASETS_DIR.mkdir(parents=True)
    (config.DATASETS_DIR / "IMDB Dataset.csv").write_text(content)
    with pytest.raises(DatasetUnavailableError, match="IMDB"):
        ImdbTrainingData().load()
