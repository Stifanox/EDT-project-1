"""VADER: liniowe mapowanie compound na skalę P(pozytywny).

Score = (compound + 1) / 2. Jest to przybliżenie na wspólnej skali interfejsu,
nie empirycznie skalibrowane prawdopodobieństwo. Analizujemy całą recenzję,
zachowując negacje, interpunkcję i wielkość liter po wspólnym clean_text.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from opimon.errors import ModelNotReadyError
from opimon.models import LabeledText, ModelInfo
from opimon.textproc import clean_text


class VaderModel:
    name = "vader"
    label = "VADER (słownik i reguły)"
    requires_training = False

    def __init__(self) -> None:
        self._analyzer: Any = None
        self._attempted = False
        self._notes = "Cała recenzja; score = (compound + 1) / 2, bez kalibracji."

    def is_ready(self) -> bool:
        if not self._attempted:
            self._attempted = True
            try:
                from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

                self._analyzer = SentimentIntensityAnalyzer()
            except Exception as exc:
                self._notes = f"VADER niedostępny: {exc}. Zainstaluj vaderSentiment."
        return self._analyzer is not None

    def train(self, data: Sequence[LabeledText]) -> None:
        return None

    def predict_proba(self, texts: Sequence[str]) -> list[float]:
        if not self.is_ready():
            raise ModelNotReadyError(self._notes)
        return [float((self._analyzer.polarity_scores(clean_text(t))["compound"] + 1) / 2)
                if clean_text(t).strip() else 0.5 for t in texts]

    def info(self) -> ModelInfo:
        ready = self.is_ready()
        return ModelInfo(self.name, self.label, False, ready, notes=self._notes)
