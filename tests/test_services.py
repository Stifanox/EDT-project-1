"""Testy fasady `AppServices` (P0): przepływ dane -> model -> analiza i odporność na błędy."""

from __future__ import annotations

import pytest

from opimon import config, services
from opimon.errors import SourceError
from opimon.models import Sentiment, Target
from opimon.services import build_services
from opimon.sources import SampleSource


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", True)
    return build_services()


def test_samples_loaded_and_analyzed(app):
    n = app.repository.count_reviews()
    assert n == 195
    assert len(app.repository.list_targets()) == 3
    assert app.default_model_name == "lexicon_stub"
    assert app.repository.reviews_without_prediction("lexicon_stub") == []
    rows = app.scored_reviews()
    assert len(rows) == n and all(r.prediction for r in rows)


def test_no_samples_when_disabled():
    app = build_services()
    assert app.repository.count_reviews() == 0


def test_fetch_is_incremental_and_deduplicated():
    app = build_services()
    target = SampleSource().find_targets("starfall")[0]
    first = app.fetch_reviews("sample", target, limit=10)
    assert (first.fetched, first.new, first.analyzed) == (10, 10, 10) and first.ok
    again = app.fetch_reviews("sample", target, limit=10)         # przyrostowo: nic nowszego
    assert again.fetched == 0 and again.new == 0
    full = app.fetch_reviews("sample", target, limit=1000, incremental=False)
    assert full.new == full.fetched - 10 and full.duplicates == 10


def test_fetch_source_error_is_reported_not_raised():
    app = build_services()
    report = app.fetch_reviews("sample", Target("sample", "nope", "?"))
    assert not report.ok and "Nieznany cel" in report.errors[0]
    report = app.fetch_reviews("missing-source", Target("x", "y", "z"))
    assert not report.ok


def test_train_reanalyzes_and_evaluates(app):
    assert "wordcount_stub" not in app.ready_models()
    info = app.train_model("wordcount_stub", "sample_movies")
    assert info.ready and info.train_size == 180
    assert app.repository.reviews_without_prediction("wordcount_stub") == []
    test_res = app.evaluate_model("wordcount_stub", on="test", dataset_name="sample_movies")
    live_res = app.evaluate_model("wordcount_stub", on="live", target_id="sample:starfall")
    assert test_res.n == 60 and test_res.accuracy > 0.8
    assert live_res.n == app.repository.count_reviews("sample:starfall")
    assert 0.0 <= live_res.f1 <= 1.0


def test_predict_text(app):
    assert Sentiment.from_score(app.predict_text("Great, fantastic, loved it")) is (
        Sentiment.POSITIVE)


def test_broken_factory_falls_back_to_stub(monkeypatch):
    def boom():
        raise RuntimeError("model nie wczytał wag")

    monkeypatch.setattr(services, "_make_models", boom)
    app = build_services()
    assert "lexicon_stub" in app.models
    assert "models" in app.module_errors


def test_broken_model_does_not_break_analysis(app, monkeypatch):
    model = app.models["lexicon_stub"]
    app.repository.delete_predictions("lexicon_stub")

    def broken(texts):
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(model, "predict_proba", broken)
    assert app.analyze_pending("lexicon_stub") == 0
    assert "model:lexicon_stub" in app.module_errors
    assert app.scored_reviews(limit=3)            # dane nadal dostępne


def test_sample_source_error_type():
    with pytest.raises(SourceError):
        SampleSource().fetch(Target("other", "starfall", "x"))
