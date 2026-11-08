"""Ręcznie policzone metryki, wersjonowanie cache i przykłady niezgodności."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from opimon import config
from opimon.models import LabeledText, ModelInfo, Sentiment
from opimon.sentiment.evaluation import (
    compare_models,
    disagreements,
    evaluate,
    evaluate_cached,
    model_errors,
)
from tests.conftest import make_review


class ControlledModel:
    requires_training = False
    label = "Kontrolowany"

    def __init__(self, name="controlled", scores=None):
        self.name = name
        self.scores = scores or [0.9, 0.8, 0.2, 0.1]
        self.calls = 0
        self.revision = "1"

    def is_ready(self):
        return True

    def info(self):
        return ModelInfo(self.name, self.label, False, True, notes=self.revision)

    def predict_proba(self, texts):
        self.calls += 1
        return self.scores[:len(texts)]


@pytest.fixture
def examples():
    return [LabeledText(str(i), label) for i, label in enumerate([
        Sentiment.POSITIVE, Sentiment.NEGATIVE, Sentiment.POSITIVE, Sentiment.NEGATIVE])]


def test_exact_confusion_metrics_and_numeric_comparison(examples):
    model = ControlledModel()
    result = evaluate(model, examples, "manual")
    assert (result.tp, result.fp, result.tn, result.fn) == (1, 1, 1, 1)
    assert (result.accuracy, result.precision, result.recall, result.f1) == (0.5,) * 4
    table = compare_models([model], examples, "manual")
    for column in ("accuracy", "precision", "recall", "f1", "seconds", "n"):
        assert pd.api.types.is_numeric_dtype(table[column])
    assert table.iloc[0]["majority_accuracy"] == 0.5


def test_cache_invalidation_and_corruption(examples, monkeypatch):
    model = ControlledModel()
    first = evaluate_cached(model, examples, "test")
    assert evaluate_cached(model, examples, "test") == first and model.calls == 1
    model.revision = "2"
    evaluate_cached(model, examples, "test")
    assert model.calls == 2
    monkeypatch.setattr(config, "POSITIVE_THRESHOLD", 0.85)
    assert evaluate_cached(model, examples, "test").result.fp == 0 and model.calls == 3
    changed = [LabeledText("changed", examples[0].label), *examples[1:]]
    evaluate_cached(model, changed, "test")
    assert model.calls == 4
    for path in (config.CACHE_DIR / "evaluation").glob("*.json"):
        path.write_text("corrupt")
    evaluate_cached(model, examples, "test")
    assert model.calls == 5
    evaluate_cached(model, examples, "test", force=True)
    assert model.calls == 6


@pytest.mark.parametrize("scores", [[0.1], [0.1, math.nan], [0.1, 1.1]])
def test_invalid_model_outputs_are_rejected(scores):
    rows = [LabeledText("a", Sentiment.POSITIVE), LabeledText("b", Sentiment.NEGATIVE)]
    with pytest.raises(ValueError):
        evaluate(ControlledModel(scores=scores), rows, "bad")


def test_errors_disagreements_and_unlabeled_reviews(examples):
    first = ControlledModel()
    second = ControlledModel("opposite", [0.1, 0.2, 0.8, 0.9])
    errors = model_errors(first, examples, "test", review_ids=["a", "b", "c", "d"])
    assert {row["review_id"] for row in errors} == {"b", "c"}
    assert model_errors(first, examples, "test", limit=0) == []
    assert first.calls == 1
    reviews = [make_review(str(i), ex.text, label=ex.label if i else None)
               for i, ex in enumerate(examples)]
    rows = disagreements([first, second], reviews)
    assert len(rows) == 4 and rows[0]["label"] is None
    assert set(rows[0]["scores"]) == {"controlled", "opposite"}
    calls = first.calls
    disagreements([first, second], reviews)
    assert first.calls == calls
    assert disagreements([first], reviews) == []


def test_broken_model_does_not_hide_other_results(examples, monkeypatch):
    broken, healthy = ControlledModel("broken"), ControlledModel()
    monkeypatch.setattr(broken, "predict_proba", lambda _: (_ for _ in ()).throw(
        RuntimeError("błąd predykcji")))
    table = compare_models([broken, healthy], examples, "test")
    assert table.iloc[0]["error"] == "błąd predykcji"
    assert table.iloc[1]["accuracy"] == 0.5
    with pytest.raises(ValueError, match="Brak"):
        compare_models([healthy], [], "empty")


def test_facade_filters_by_source_and_excludes_unlabeled():
    from opimon.services import build_services

    services = build_services(load_samples=False)
    reviews = [make_review("1", "great", label=Sentiment.POSITIVE, source="steam"),
               make_review("2", "awful", label=Sentiment.NEGATIVE, source="imdb"),
               make_review("3", "unknown", source="steam"),
               make_review("4", "great", label=Sentiment.POSITIVE, source="sample")]
    services.repository.add_reviews(reviews)
    assert services.evaluation_sources() == ["imdb", "sample", "steam"]
    live = services.compare_models(on="live", source_name="steam")
    assert list(live["n"]) == [1]
    assert set(live["dataset_name"]) == {"live:steam"}
    demo = services.compare_models(on="live", source_name="sample")
    assert set(demo["dataset_name"]) == {"demo:sample"}
    assert services.evaluation_details(on="live", source_name="imdb")["errors"] == []


def test_facade_reuses_cache_for_metrics_and_errors(monkeypatch):
    from opimon.services import build_services

    services = build_services(load_samples=False)
    result = services.evaluate_model("vader", dataset_name="sample_movies")
    monkeypatch.setattr(services.models["vader"], "predict_proba",
                        lambda _: pytest.fail("Nie użyto zapisanych predykcji"))
    assert services.evaluate_model("vader", dataset_name="sample_movies").n == result.n
    services.evaluation_details(dataset_name="sample_movies")
