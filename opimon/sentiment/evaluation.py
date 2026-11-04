"""Ewaluacja modeli (P0: podstawowa wersja; M5 rozbudowuje o porównanie i analizę błędów)."""

from __future__ import annotations

import time
from collections.abc import Sequence

from opimon.interfaces import SentimentModel
from opimon.models import EvalResult, LabeledText, Sentiment


def evaluate(
    model: SentimentModel, examples: Sequence[LabeledText], dataset_name: str
) -> EvalResult:
    """Macierz pomyłek modelu na `examples` (klasa pozytywna = POSITIVE)."""
    start = time.perf_counter()
    scores = model.predict_proba([ex.text for ex in examples])
    tp = fp = tn = fn = 0
    for ex, score in zip(examples, scores, strict=True):
        predicted_pos = Sentiment.from_score(score) is Sentiment.POSITIVE
        actual_pos = ex.label is Sentiment.POSITIVE
        if predicted_pos and actual_pos:
            tp += 1
        elif predicted_pos:
            fp += 1
        elif actual_pos:
            fn += 1
        else:
            tn += 1
    return EvalResult(model.name, dataset_name, tp, fp, tn, fn,
                      seconds=time.perf_counter() - start)
