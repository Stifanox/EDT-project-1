"""TF-IDF z regresją logistyczną, trwałym modelem i wkładami cech w logit."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from opimon import config
from opimon.errors import ModelNotReadyError
from opimon.models import LabeledText, ModelInfo, Sentiment, utcnow
from opimon.textproc import clean_text


class TfidfLogRegModel:
    name = "tfidf_lr"
    label = "TF-IDF + regresja logistyczna"
    requires_training = True

    def __init__(self) -> None:
        self._pipeline: Any = None
        self._trained_at: datetime | None = None
        self._train_size: int | None = None
        self._notes = "Wymaga treningu na IMDB lub próbce offline."
        self._load_key: tuple | None = None

    def is_ready(self) -> bool:
        if self._pipeline is not None:
            return True
        path = config.MODELS_DIR / self.name / "model.joblib"
        if not path.is_file():
            return False
        stat = path.stat()
        key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
        if key != self._load_key:
            self._load_key = key
            try:
                import joblib

                payload = joblib.load(path)
                pipeline = payload["pipeline"]
                if set(pipeline.classes_) != {s.value for s in Sentiment}:
                    raise ValueError("Model nie zawiera obu klas sentymentu.")
                trained_at = datetime.fromisoformat(payload["trained_at"])
                if trained_at.tzinfo is None:
                    raise ValueError("Data treningu musi zawierać strefę UTC.")
                self._pipeline = pipeline
                self._trained_at = trained_at
                self._train_size = int(payload["train_size"])
                self._notes = "Wczytano zapisany pipeline TF-IDF (1–2-gramy) + LR."
            except Exception as exc:
                self._notes = f"Nie można wczytać modelu: {exc}. Wytrenuj ponownie."
        return self._pipeline is not None

    def train(self, data: Sequence[LabeledText]) -> None:
        if {ex.label for ex in data} != set(Sentiment):
            raise ValueError("Dane treningowe muszą zawierać obie klasy.")
        try:
            import joblib
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import Pipeline
        except ImportError as exc:
            raise ModelNotReadyError(
                "Zainstaluj scikit-learn i joblib, aby trenować TF-IDF."
            ) from exc
        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True,
                                      min_df=2 if len(data) >= 100 else 1,
                                      max_features=150_000)),
            ("classifier", LogisticRegression(C=4.0, solver="liblinear", random_state=13,
                                               max_iter=1000)),
        ])
        pipeline.fit([clean_text(ex.text) for ex in data], [ex.label.value for ex in data])
        trained_at = utcnow()
        directory = config.MODELS_DIR / self.name
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=directory, suffix=".joblib.tmp")
        os.close(descriptor)
        try:
            joblib.dump({"pipeline": pipeline, "trained_at": trained_at.isoformat(),
                         "train_size": len(data)}, temporary)
            os.replace(temporary, directory / "model.joblib")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        # Podmiana w pamięci dopiero po udanym zapisie; błąd nie niszczy starego modelu.
        self._pipeline = pipeline
        self._trained_at = trained_at
        self._train_size = len(data)
        self._notes = "TF-IDF: 1–2-gramy, sublinear_tf; LR C=4; zachowane negacje."

    def predict_proba(self, texts: Sequence[str]) -> list[float]:
        if not self.is_ready():
            raise ModelNotReadyError(self._notes)
        cleaned = [clean_text(text) for text in texts]
        out = [0.5] * len(cleaned)
        indices = [i for i, text in enumerate(cleaned) if text.strip()]
        if indices:
            positive = list(self._pipeline.classes_).index(Sentiment.POSITIVE.value)
            scores = self._pipeline.predict_proba([cleaned[i] for i in indices])[:, positive]
            for i, score in zip(indices, scores, strict=True):
                out[i] = float(score)
        return out

    def explain(self, text: str, n: int = 10) -> list[tuple[str, float]]:
        """Największe wkłady TF-IDF × współczynnik w logit klasy pozytywnej."""
        if not self.is_ready():
            raise ModelNotReadyError(self._notes)
        if n <= 0:
            return []
        vectorizer = self._pipeline.named_steps["tfidf"]
        classifier = self._pipeline.named_steps["classifier"]
        vector = vectorizer.transform([clean_text(text)])
        names = vectorizer.get_feature_names_out()
        sign = 1 if classifier.classes_[1] == Sentiment.POSITIVE.value else -1
        contributions = [(str(names[i]), float(v * classifier.coef_[0, i] * sign))
                         for i, v in zip(vector.indices, vector.data, strict=True)]
        return sorted(contributions, key=lambda item: (-abs(item[1]), item[0]))[:n]

    def info(self) -> ModelInfo:
        ready = self.is_ready()
        return ModelInfo(self.name, self.label, True, ready, self._trained_at,
                         self._train_size, self._notes)
