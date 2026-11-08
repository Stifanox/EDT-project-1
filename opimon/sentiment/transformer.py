"""DistilBERT SST-2: jawne pobranie, lokalny cache, predykcja paczkami na CPU."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from opimon import config
from opimon.errors import ModelNotReadyError
from opimon.models import LabeledText, ModelInfo
from opimon.textproc import clean_text


class TransformerModel:
    name = "distilbert"
    label = "DistilBERT SST-2 (CPU)"
    requires_training = False

    def __init__(self, batch_size: int = 8) -> None:
        if batch_size < 1:
            raise ValueError("Rozmiar paczki musi być dodatni.")
        self.batch_size = batch_size
        self._model: Any = None
        self._tokenizer: Any = None
        self._positive_index: int | None = None
        self._attempted_local = False
        self._notes = "Wczytaj / pobierz model w widoku Modele; pierwsze pobranie wymaga sieci."

    def load(self, allow_download: bool = False) -> bool:
        """Wczytaj raz; sieć dozwolona wyłącznie po jawnym wywołaniu z True."""
        if self._model is not None:
            return True
        self._attempted_local = True
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            options = {"cache_dir": str(config.MODELS_DIR / self.name),
                       "local_files_only": not allow_download}
            tokenizer = AutoTokenizer.from_pretrained(config.TRANSFORMER_MODEL_NAME, **options)
            model = AutoModelForSequenceClassification.from_pretrained(
                config.TRANSFORMER_MODEL_NAME, **options
            ).to("cpu").eval()
            positive = [int(i) for i, label in model.config.id2label.items()
                        if str(label).upper() == "POSITIVE"]
            if len(positive) != 1 or model.config.num_labels != 2:
                raise ValueError("Model musi mieć dwie klasy i etykietę POSITIVE.")
            self._tokenizer = tokenizer
            self._positive_index = positive[0]
            self._model = model
            self._notes = (f"{config.TRANSFORMER_MODEL_NAME}; CPU, paczki {self.batch_size}, "
                           "maks. 512 tokenów; dłuższe teksty są obcinane.")
            return True
        except Exception as exc:
            self._notes = ("Nie można wczytać DistilBERT. Zainstaluj transformers i torch; "
                           f"przy pierwszym pobraniu sprawdź sieć. {type(exc).__name__}: {exc}")
            return False

    def is_ready(self) -> bool:
        if self._model is not None:
            return True
        if not self._attempted_local:
            directory = config.MODELS_DIR / self.name
            if directory.is_dir():
                return self.load(allow_download=False)
            self._attempted_local = True
        return False

    def train(self, data: Sequence[LabeledText]) -> None:
        return None

    def predict_proba(self, texts: Sequence[str]) -> list[float]:
        if not self.is_ready():
            raise ModelNotReadyError(self._notes)
        import torch

        cleaned = [clean_text(text) for text in texts]
        scores = [0.5] * len(cleaned)
        indices = [i for i, text in enumerate(cleaned) if text.strip()]
        with torch.inference_mode():
            for start in range(0, len(indices), self.batch_size):
                batch = indices[start:start + self.batch_size]
                tokens = self._tokenizer([cleaned[i] for i in batch], padding=True,
                                         truncation=True, max_length=512, return_tensors="pt")
                probabilities = self._model(**tokens).logits.softmax(dim=-1)
                for i, score in zip(batch, probabilities[:, self._positive_index], strict=True):
                    scores[i] = float(score.item())
        return scores

    def info(self) -> ModelInfo:
        ready = self.is_ready()
        return ModelInfo(self.name, self.label, False, ready, notes=self._notes)
