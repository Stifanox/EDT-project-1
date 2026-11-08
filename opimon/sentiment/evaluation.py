"""Ewaluacja modeli (P0: podstawowa wersja; M5 rozbudowuje o porównanie i analizę błędów)."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pandas as pd

from opimon import config
from opimon.interfaces import SentimentModel
from opimon.models import EvalResult, LabeledText, Review, Sentiment, utcnow
from opimon.sentiment.cache import read_json, write_json_atomic


def evaluate(
    model: SentimentModel, examples: Sequence[LabeledText], dataset_name: str
) -> EvalResult:
    """Macierz pomyłek modelu na `examples` (klasa pozytywna = POSITIVE)."""
    start = time.perf_counter()
    scores = model.predict_proba([ex.text for ex in examples])
    return _result(model.name, examples, scores, dataset_name, time.perf_counter() - start)


def _result(
    model_name: str, examples: Sequence[LabeledText], scores: Sequence[float],
    dataset_name: str, seconds: float,
) -> EvalResult:
    if len(scores) != len(examples):
        raise ValueError("Liczba predykcji nie odpowiada liczbie przykładów.")
    if any(not math.isfinite(s) or not 0 <= s <= 1 for s in scores):
        raise ValueError("Model zwrócił wynik poza zakresem [0, 1].")
    tp = fp = tn = fn = 0
    for ex, score in zip(examples, scores, strict=True):
        predicted_pos = Sentiment.from_score(score, config.POSITIVE_THRESHOLD) is Sentiment.POSITIVE
        actual_pos = ex.label is Sentiment.POSITIVE
        if predicted_pos and actual_pos:
            tp += 1
        elif predicted_pos:
            fp += 1
        elif actual_pos:
            fn += 1
        else:
            tn += 1
    return EvalResult(model_name, dataset_name, tp, fp, tn, fn, seconds=seconds)


@dataclass
class EvaluationRecord:
    result: EvalResult
    scores: list[float]
    evaluated_at: str


def _cache_path(model: SentimentModel, examples: Sequence[LabeledText], name: str) -> Path:
    info = model.info()
    libraries = {}
    for package in ("scikit-learn", "vaderSentiment", "transformers", "torch"):
        try:
            libraries[package] = version(package)
        except PackageNotFoundError:
            pass
    identity = {"schema": 1, "class": f"{type(model).__module__}.{type(model).__qualname__}",
                "info": asdict(info), "dataset": name, "threshold": config.POSITIVE_THRESHOLD,
                "transformer": config.TRANSFORMER_MODEL_NAME, "libraries": libraries,
                "examples": [(ex.text, ex.label.value) for ex in examples]}
    key = hashlib.sha256(json.dumps(identity, default=str, ensure_ascii=False,
                                   sort_keys=True).encode()).hexdigest()
    return config.CACHE_DIR / "evaluation" / f"{key}.json"


def evaluate_cached(
    model: SentimentModel, examples: Sequence[LabeledText], dataset_name: str,
    *, force: bool = False,
) -> EvaluationRecord:
    """Wynik oraz predykcje; cache zależy od modelu, danych, etykiet i progu."""
    if not examples:
        raise ValueError("Brak opinii z etykietą do ewaluacji.")
    path = _cache_path(model, examples, dataset_name)
    if not force:
        try:
            payload = read_json(path)
            record = EvaluationRecord(EvalResult(**payload["result"]),
                                      payload["scores"], payload["evaluated_at"])
            if record.result.n == len(examples) and len(record.scores) == len(examples):
                return record
        except (OSError, ValueError, TypeError, KeyError):
            pass
    start = time.perf_counter()
    scores = [float(s) for s in model.predict_proba([ex.text for ex in examples])]
    result = _result(model.name, examples, scores, dataset_name, time.perf_counter() - start)
    record = EvaluationRecord(result, scores, utcnow().isoformat())
    write_json_atomic(path, asdict(record))
    return record


RESULT_COLUMNS = ["model_name", "dataset_name", "n", "accuracy", "precision", "recall", "f1",
                  "seconds", "tp", "fp", "tn", "fn", "positive_n", "majority_accuracy",
                  "evaluated_at", "error"]


def compare_models(
    models: Mapping[str, SentimentModel] | Sequence[SentimentModel],
    examples: Sequence[LabeledText], dataset_name: str, *, force: bool = False,
) -> pd.DataFrame:
    """Porównaj na tych samych danych; błąd jednego modelu nie zatrzymuje pozostałych."""
    if not examples:
        raise ValueError("Brak opinii z etykietą do ewaluacji.")
    rows = []
    positive = sum(ex.label is Sentiment.POSITIVE for ex in examples)
    for model in models.values() if isinstance(models, Mapping) else models:
        try:
            if not model.is_ready():
                continue
            record = evaluate_cached(model, examples, dataset_name, force=force)
            result = record.result
            rows.append({**asdict(result), "n": result.n, "accuracy": result.accuracy,
                         "precision": result.precision, "recall": result.recall, "f1": result.f1,
                         "positive_n": positive,
                         "majority_accuracy": max(positive, len(examples) - positive)
                         / len(examples),
                         "evaluated_at": record.evaluated_at, "error": ""})
        except Exception as exc:
            rows.append({"model_name": model.name, "dataset_name": dataset_name,
                         "error": str(exc), "n": len(examples)})
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


def model_errors(
    model: SentimentModel, examples: Sequence[LabeledText], dataset_name: str,
    *, review_ids: Sequence[str] | None = None, limit: int = 20,
) -> list[dict]:
    """Przykłady błędów, od najbardziej pewnych; predykcje pobierane z cache."""
    record = evaluate_cached(model, examples, dataset_name)
    ids = list(review_ids) if review_ids is not None else [None] * len(examples)
    errors = []
    for ex, score, review_id in zip(examples, record.scores, ids, strict=True):
        predicted = Sentiment.from_score(score, config.POSITIVE_THRESHOLD)
        if predicted != ex.label:
            errors.append({"model_name": model.name, "review_id": review_id, "text": ex.text,
                           "label": ex.label.value, "predicted": predicted.value, "score": score})
    return sorted(errors, key=lambda row: -abs(row["score"] - config.POSITIVE_THRESHOLD))[
        :max(0, limit)]


def disagreements(
    models: Mapping[str, SentimentModel] | Sequence[SentimentModel], reviews: Sequence[Review],
    *, limit: int = 20, dataset_name: str = "disagreements",
) -> list[dict]:
    """Niezgodności modeli także dla opinii bez etykiety źródła."""
    available = list(models.values()) if isinstance(models, Mapping) else list(models)
    predictions = {}
    examples = [LabeledText(r.text, r.label or Sentiment.POSITIVE) for r in reviews]
    if not examples:
        return []
    for model in available:
        if model.is_ready():
            predictions[model.name] = evaluate_cached(model, examples, dataset_name).scores
    rows = []
    for i, review in enumerate(reviews):
        scores = {name: values[i] for name, values in predictions.items()}
        labels = {Sentiment.from_score(s, config.POSITIVE_THRESHOLD) for s in scores.values()}
        if len(labels) > 1:
            rows.append({"review_id": review.id, "text": review.text, "source": review.source,
                         "label": review.label.value if review.label else None, "scores": scores})
    return rows[:max(0, limit)]
