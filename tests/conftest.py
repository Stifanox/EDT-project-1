"""Wspólne fixture'y testów."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("OPIMON_LOAD_SAMPLES", "0")   # testy nie wczytują danych samoczynnie
# Zabezpieczenie: nawet kod czytający config przy imporcie nie dotknie prawdziwego data/.
os.environ.setdefault("OPIMON_DATA_DIR", tempfile.mkdtemp(prefix="opimon-tests-"))

from opimon import config  # noqa: E402
from opimon.models import LabeledText, Review, Sentiment, Target  # noqa: E402

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Każdy test ma własny katalog na bazę, modele, zbiory i cache."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "opimon.db")
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(config, "DATASETS_DIR", tmp_path / "datasets")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", False)
    return tmp_path


def make_review(
    external_id: str,
    text: str,
    hours_ago: float = 1.0,
    target: str = "t1",
    label: Sentiment | None = None,
    source: str = "test",
) -> Review:
    return Review(
        source=source,
        external_id=external_id,
        target_id=f"{source}:{target}",
        text=text,
        created_at=NOW - timedelta(hours=hours_ago),
        label=label,
    )


@pytest.fixture
def tiny_reviews() -> list[Review]:
    """Mały, w pełni kontrolowany zbiór opinii (2 cele, z etykietami)."""
    P, N = Sentiment.POSITIVE, Sentiment.NEGATIVE
    return [
        make_review("r1", "Great game, I love the art and the music.", 1, "t1", P),
        make_review("r2", "Terrible performance, constant crashes. Waste of money.", 2, "t1", N),
        make_review("r3", "Fantastic story, excellent characters.", 30, "t1", P),
        make_review("r4", "Boring and repetitive grind.", 50, "t2", N),
        make_review("r5", "Beautiful and relaxing, highly recommended.", 80, "t2", P),
    ]


@pytest.fixture
def tiny_targets() -> list[Target]:
    return [Target("test", "t1", "Gra pierwsza"), Target("test", "t2", "Gra druga")]


@pytest.fixture
def tiny_training() -> list[LabeledText]:
    P, N = Sentiment.POSITIVE, Sentiment.NEGATIVE
    pos = ["great fun", "excellent and beautiful", "loved it, fantastic", "superb acting, great",
           "brilliant film, loved it", "fantastic and fun"]
    neg = ["boring and dull", "terrible waste of time", "awful, boring plot", "worst film ever",
           "dull and terrible", "awful waste"]
    return [LabeledText(t, P) for t in pos] + [LabeledText(t, N) for t in neg]
