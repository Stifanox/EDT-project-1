"""VADER: negacje, wspólne czyszczenie i odporność na brak biblioteki."""

from __future__ import annotations

import builtins

import pytest

from opimon.errors import ModelNotReadyError
from opimon.sentiment.vader import VaderModel


def test_negation_and_cleaning():
    model = VaderModel()
    good, bad, html = model.predict_proba(["good", "not good", "<b>good</b>"])
    assert good > 0.5 > bad
    assert html == good


def test_missing_library(monkeypatch):
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.startswith("vaderSentiment"):
            raise ImportError("brak pakietu")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    model = VaderModel()
    assert not model.is_ready()
    assert "Zainstaluj" in model.info().notes
    with pytest.raises(ModelNotReadyError):
        model.predict_proba(["good"])
