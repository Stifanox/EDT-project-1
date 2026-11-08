"""Trwałość, wkłady cech i nieudany ponowny trening TF-IDF."""

from __future__ import annotations

import pytest

from opimon import config
from opimon.models import LabeledText, Sentiment
from opimon.sentiment.tfidf import TfidfLogRegModel


def test_roundtrip_metadata_and_explanation(tiny_training):
    model = TfidfLogRegModel()
    model.train(tiny_training)
    texts = ["great fantastic", "awful boring", "", "<br />"]
    restored = TfidfLogRegModel()
    assert restored.is_ready()
    assert restored.predict_proba(texts) == model.predict_proba(texts)
    assert restored.info().trained_at == model.info().trained_at
    assert restored.info().trained_at.utcoffset().total_seconds() == 0
    assert restored.info().train_size == len(tiny_training)
    contributions = dict(model.explain("great awful"))
    assert contributions["great"] > 0 > contributions["awful"]
    assert model.explain("", 0) == []


def test_negations_remain_in_vocabulary():
    model = TfidfLogRegModel()
    data = [LabeledText("not good", Sentiment.NEGATIVE),
            LabeledText("really good", Sentiment.POSITIVE)] * 4
    model.train(data)
    assert "not good" in dict(model.explain("not good"))
    assert model.predict_proba(["not good"])[0] < 0.5


def test_corrupt_artifact_is_not_ready():
    directory = config.MODELS_DIR / "tfidf_lr"
    directory.mkdir(parents=True)
    (directory / "model.joblib").write_bytes(b"corrupt")
    model = TfidfLogRegModel()
    assert not model.is_ready()
    assert "Wytrenuj" in model.info().notes


def test_failed_retrain_preserves_model(tiny_training):
    model = TfidfLogRegModel()
    model.train(tiny_training)
    before = model.predict_proba(["great"])
    with pytest.raises(ValueError):
        model.train([LabeledText("", Sentiment.POSITIVE), LabeledText("", Sentiment.NEGATIVE)])
    assert model.predict_proba(["great"]) == before
