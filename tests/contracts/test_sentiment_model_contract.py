"""Test kontraktu SentimentModel – KAŻDY model musi go przejść.

O2: dopisz swój model do MODEL_FACTORIES (M2–M4). Modele wymagające ciężkich bibliotek
lub pobierania wag oznacz `marks=pytest.mark.slow`.
Modele z `requires_training=True` są trenowane na `tiny_training` (12 przykładów).
"""

from __future__ import annotations

import pytest

from opimon.errors import ModelNotReadyError
from opimon.interfaces import SentimentModel
from opimon.models import LabeledText, ModelInfo, Sentiment
from opimon.sentiment import LexiconStubModel, TfidfLogRegModel, VaderModel, WordCountModel

MODEL_FACTORIES = [
    pytest.param(LexiconStubModel, id="lexicon_stub"),
    pytest.param(WordCountModel, id="wordcount_stub"),
    pytest.param(VaderModel, id="vader"),
    pytest.param(TfidfLogRegModel, id="tfidf_lr"),
    # pytest.param(TransformerModel, id="distilbert", marks=pytest.mark.slow),
]

CLEAR = [("This was great, I loved it. Fantastic and excellent.", Sentiment.POSITIVE),
         ("Terrible, boring and awful. A waste of time.", Sentiment.NEGATIVE)]


@pytest.fixture(params=MODEL_FACTORIES)
def model(request, tiny_training) -> SentimentModel:
    m = request.param()
    if m.requires_training:
        assert not m.is_ready()
        with pytest.raises(ModelNotReadyError):
            m.predict_proba(["anything"])
        m.train(tiny_training)
    assert m.is_ready()
    return m


def test_implements_protocol(model):
    assert isinstance(model, SentimentModel)
    assert model.name and model.label
    info = model.info()
    assert isinstance(info, ModelInfo) and info.name == model.name and info.ready


def test_shape_range_and_determinism(model):
    texts = [t for t, _ in CLEAR] + ["ok", "The plot was about a ship."]
    a = model.predict_proba(texts)
    assert len(a) == len(texts)
    assert all(isinstance(x, float) and 0.0 <= x <= 1.0 for x in a)
    assert model.predict_proba(texts) == a
    assert model.predict_proba(list(reversed(texts))) == list(reversed(a)), "kolejność"


def test_empty_inputs(model):
    assert model.predict_proba([]) == []
    assert model.predict_proba(["", "   "]) == [0.5, 0.5]


def test_obvious_examples(model):
    scores = model.predict_proba([t for t, _ in CLEAR])
    assert [Sentiment.from_score(s) for s in scores] == [s for _, s in CLEAR]


def test_single_class_training_rejected(model):
    if not model.requires_training:
        pytest.skip("model bez treningu")
    with pytest.raises(ValueError):
        model.train([LabeledText("great", Sentiment.POSITIVE)] * 3)
