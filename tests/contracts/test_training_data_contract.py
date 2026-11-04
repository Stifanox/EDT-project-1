"""Test kontraktu TrainingDataProvider. O2: dopisz IMDB do PROVIDER_FACTORIES (M1).

Pełny zbiór IMDB nie jest w repo – jego wariant oznacz `slow` albo testuj na małym
pliku-fixture w formacie oryginału (`tests/fixtures/imdb_mini.csv`).
"""

from __future__ import annotations

import pytest

from opimon.errors import DatasetUnavailableError
from opimon.interfaces import TrainingDataProvider
from opimon.models import Dataset, Sentiment
from opimon.sentiment import SampleTrainingData

PROVIDER_FACTORIES = [
    pytest.param(SampleTrainingData, id="sample_movies"),
]


@pytest.fixture(params=PROVIDER_FACTORIES)
def provider(request) -> TrainingDataProvider:
    return request.param()


def test_implements_protocol(provider):
    assert isinstance(provider, TrainingDataProvider)
    assert provider.name and provider.label


def test_split_has_both_classes_and_is_deterministic(provider):
    ds = provider.load()
    assert isinstance(ds, Dataset) and ds.train and ds.test
    for part in (ds.train, ds.test):
        assert {ex.label for ex in part} == {Sentiment.POSITIVE, Sentiment.NEGATIVE}
        assert all(ex.text.strip() for ex in part)
    again = provider.load()
    assert [ex.text for ex in again.test] == [ex.text for ex in ds.test]


def test_limits_are_balanced(provider):
    ds = provider.load(max_train=20, max_test=10)
    assert len(ds.train) <= 20 and len(ds.test) <= 10
    pos = sum(ex.label is Sentiment.POSITIVE for ex in ds.train)
    assert abs(pos - (len(ds.train) - pos)) <= 1


def test_missing_data_raises_readable_error(provider, monkeypatch, tmp_path):
    from opimon import config

    monkeypatch.setattr(config, "SAMPLE_DIR", tmp_path / "missing")
    monkeypatch.setattr(config, "DATASETS_DIR", tmp_path / "missing")
    with pytest.raises(DatasetUnavailableError):
        provider.load()
