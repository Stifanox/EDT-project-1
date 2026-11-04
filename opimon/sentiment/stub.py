"""Zaślepki modeli sentymentu (P0). Zastępują je M2 (VADER), M3 (TF-IDF + LR), M4 (transformer).

* `LexiconStubModel` – nie wymaga treningu: mała lista słów pozytywnych i negatywnych,
  bez obsługi negacji (celowo naiwny, przegrywa na „not bad at all”).
* `WordCountModel` – wymaga treningu: log-odds słów z danych treningowych (naiwny Bayes
  „na piechotę”), tylko w pamięci. Pokazuje w GUI ścieżkę trening -> predykcja.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from datetime import datetime

from opimon.errors import ModelNotReadyError
from opimon.models import LabeledText, ModelInfo, Sentiment, utcnow
from opimon.textproc import tokenize

_POSITIVE = frozenset(
    """love loved great best fantastic excellent amazing beautiful brilliant superb perfect
    perfectly fun charming smooth polished recommend recommended masterpiece enjoyable worth
    good outstanding gripping moving clever original warm funny addictive relaxing""".split()
)
_NEGATIVE = frozenset(
    """waste disappointing boring terrible awful worst bad broken bugs crash crashes crashed
    refunded clunky overpriced dull predictable poor lazy cheap forgettable joke ruined
    stuttering repetitive grind overhyped bored nonsense""".split()
)


class LexiconStubModel:
    requires_training = False

    def __init__(self, name: str = "lexicon_stub", label: str = "Słownik (zaślepka)") -> None:
        self.name = name
        self.label = label

    def is_ready(self) -> bool:
        return True

    def train(self, data: Sequence[LabeledText]) -> None:
        return None

    def predict_proba(self, texts: Sequence[str]) -> list[float]:
        out = []
        for text in texts:
            tokens = tokenize(text)
            pos = sum(t in _POSITIVE for t in tokens)
            neg = sum(t in _NEGATIVE for t in tokens)
            out.append((pos + 1) / (pos + neg + 2))    # wygładzenie Laplace'a; brak słów -> 0.5
        return out

    def info(self) -> ModelInfo:
        return ModelInfo(self.name, self.label, self.requires_training, ready=True,
                         notes="Lista ~60 słów, bez negacji. Zastąpi go VADER (M2).")


class WordCountModel:
    requires_training = True

    def __init__(
        self, name: str = "wordcount_stub", label: str = "Licznik słów (zaślepka, trenowany)"
    ) -> None:
        self.name = name
        self.label = label
        self._log_odds: dict[str, float] | None = None
        self._prior = 0.0
        self._trained_at: datetime | None = None
        self._train_size: int | None = None

    def is_ready(self) -> bool:
        return self._log_odds is not None

    def train(self, data: Sequence[LabeledText]) -> None:
        labels = {ex.label for ex in data}
        if labels != {Sentiment.POSITIVE, Sentiment.NEGATIVE}:
            raise ValueError("Dane treningowe muszą zawierać obie klasy.")
        pos, neg = Counter(), Counter()
        n_pos = 0
        for ex in data:
            tokens = set(tokenize(ex.text))
            if ex.label is Sentiment.POSITIVE:
                pos.update(tokens)
                n_pos += 1
            else:
                neg.update(tokens)
        n_neg = len(data) - n_pos
        vocab = set(pos) | set(neg)
        self._log_odds = {
            t: math.log((pos[t] + 1) / (n_pos + 2)) - math.log((neg[t] + 1) / (n_neg + 2))
            for t in vocab
        }
        self._prior = math.log(n_pos / n_neg)
        self._trained_at = utcnow()
        self._train_size = len(data)

    def predict_proba(self, texts: Sequence[str]) -> list[float]:
        if self._log_odds is None:
            raise ModelNotReadyError(f"Model „{self.label}” wymaga treningu.")
        out = []
        for text in texts:
            tokens = set(tokenize(text))
            if not tokens:
                out.append(0.5)
                continue
            z = self._prior + sum(self._log_odds.get(t, 0.0) for t in tokens)
            z = max(-30.0, min(30.0, z))
            out.append(1.0 / (1.0 + math.exp(-z)))
        return out

    def info(self) -> ModelInfo:
        return ModelInfo(self.name, self.label, self.requires_training, ready=self.is_ready(),
                         trained_at=self._trained_at, train_size=self._train_size,
                         notes="Tylko w pamięci – po restarcie trzeba wytrenować ponownie.")
