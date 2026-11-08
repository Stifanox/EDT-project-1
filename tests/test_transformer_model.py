"""Szybkie testy adaptera bez wag, torch i połączeń sieciowych."""

from __future__ import annotations

import builtins
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from opimon import config
from opimon.errors import ModelNotReadyError
from opimon.sentiment.transformer import TransformerModel


def test_startup_is_lazy_and_missing_dependencies_are_readable(monkeypatch):
    real_import = builtins.__import__
    attempted = []

    def blocked(name, *args, **kwargs):
        if name in {"torch", "transformers"}:
            attempted.append(name)
            raise ImportError("brak biblioteki")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    model = TransformerModel()
    assert not model.is_ready() and not model.info().ready
    assert attempted == []
    assert not model.load(allow_download=True)
    assert attempted == ["transformers"]
    assert "Zainstaluj" in model.info().notes
    with pytest.raises(ModelNotReadyError):
        model.predict_proba(["good"])


def test_local_failure_is_not_repeated_and_never_downloads(monkeypatch):
    calls = []

    def unavailable(*args, **kwargs):
        calls.append(kwargs)
        raise OSError("brak lokalnych wag")

    fake = SimpleNamespace(from_pretrained=unavailable)
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(
        AutoTokenizer=fake, AutoModelForSequenceClassification=fake))
    (config.MODELS_DIR / "distilbert").mkdir(parents=True)
    model = TransformerModel()
    assert not model.is_ready()
    assert not model.is_ready()
    assert len(calls) == 1 and calls[0]["local_files_only"] is True
    assert "brak lokalnych wag" in model.info().notes


def test_batching_empty_positions_truncation_and_positive_index(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext))

    def tokenizer(texts, **kwargs):
        calls.append((texts, kwargs))
        return {"texts": texts}

    class Probabilities:
        def __init__(self, texts):
            self.texts = texts

        def __getitem__(self, key):
            assert key[1] == 0
            return [SimpleNamespace(item=lambda text=t: 0.9 if "good" in text else 0.1)
                    for t in self.texts]

    def classifier(texts):
        return SimpleNamespace(logits=SimpleNamespace(
            softmax=lambda dim: Probabilities(texts)))

    model = TransformerModel(batch_size=2)
    model._model, model._tokenizer, model._positive_index = classifier, tokenizer, 0
    assert model.predict_proba(["good", "", "bad", "<br />", "good " * 1000]) == [
        0.9, 0.5, 0.1, 0.5, 0.9]
    assert [len(texts) for texts, _ in calls] == [2, 1]
    assert all(options["max_length"] == 512 and options["truncation"]
               for _, options in calls)
    assert model.predict_proba([]) == []
