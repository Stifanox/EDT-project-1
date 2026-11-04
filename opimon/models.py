"""Wspólne modele danych (P0, KONTRAKT – plik zamrożony).

Dozwolone są tylko zmiany wstecznie zgodne (nowe pole z wartością domyślną, nowa
właściwość / funkcja), każda z wpisem w PROGRESS.md -> „Dziennik decyzji”.

Konwencje:
* wszystkie daty są świadome strefy czasowej (UTC), naiwne `datetime` -> `ValueError`;
* `score` to zawsze P(pozytywny) w przedziale [0, 1];
* identyfikatory: `Target.id = "<source>:<key>"`, `Review.id = "<source>:<external_id>"`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def utcnow() -> datetime:
    return datetime.now(UTC)


def _require_aware(value: datetime | None, field_name: str) -> None:
    if value is not None and value.tzinfo is None:
        raise ValueError(f"{field_name} musi mieć strefę czasową (UTC), dostano {value!r}")


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"

    @classmethod
    def from_score(cls, score: float, threshold: float = 0.5) -> Sentiment:
        """`score >= threshold` -> POSITIVE, w przeciwnym razie NEGATIVE."""
        return cls.POSITIVE if score >= threshold else cls.NEGATIVE

    @property
    def label_pl(self) -> str:
        return "pozytywny" if self is Sentiment.POSITIVE else "negatywny"

    @property
    def icon(self) -> str:
        return "🟢" if self is Sentiment.POSITIVE else "🔴"


@dataclass(frozen=True, slots=True)
class Target:
    """Monitorowany obiekt: gra, film, produkt… w konkretnym źródle.

    `key` to identyfikator w źródle (np. appid Steam, id filmu w IMDb).
    """

    source: str
    key: str
    name: str
    url: str | None = None

    @property
    def id(self) -> str:
        return f"{self.source}:{self.key}"


@dataclass(slots=True)
class Review:
    """Pojedyncza opinia pobrana z Internetu.

    `text` jest już oczyszczony (`textproc.clean_text`) i niepusty.
    `label` to etykieta pochodząca ze źródła (np. Steam `voted_up`, ocena >= 7/10),
    jeśli istnieje – służy do ewaluacji modeli na danych „na żywo” (M5). To NIE jest predykcja.
    """

    source: str
    external_id: str
    target_id: str
    text: str
    created_at: datetime
    author: str | None = None
    rating: float | None = None          # oryginalna ocena w skali źródła (jeśli jest)
    label: Sentiment | None = None
    url: str | None = None
    language: str = "en"
    fetched_at: datetime = field(default_factory=utcnow)
    extra: dict[str, Any] = field(default_factory=dict)  # dowolne metadane źródła (JSON-owalne)

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        _require_aware(self.fetched_at, "fetched_at")

    @property
    def id(self) -> str:
        return f"{self.source}:{self.external_id}"


@dataclass(frozen=True, slots=True)
class Prediction:
    """Wynik modelu dla jednej opinii. Klucz: (`review_id`, `model_name`)."""

    review_id: str
    model_name: str
    score: float                          # P(pozytywny) w [0, 1]
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score poza [0, 1]: {self.score}")
        _require_aware(self.created_at, "created_at")

    @property
    def sentiment(self) -> Sentiment:
        return Sentiment.from_score(self.score)


@dataclass(frozen=True, slots=True)
class LabeledText:
    """Przykład treningowy / testowy."""

    text: str
    label: Sentiment


@dataclass(slots=True)
class Dataset:
    """Zbiór z podziałem train/test (M1). Oba podzbiory zawierają obie klasy."""

    name: str
    train: list[LabeledText]
    test: list[LabeledText]
    description: str = ""


@dataclass(slots=True)
class ModelInfo:
    """Opis modelu dla GUI."""

    name: str
    label: str
    requires_training: bool
    ready: bool
    trained_at: datetime | None = None
    train_size: int | None = None
    notes: str = ""


@dataclass(slots=True)
class EvalResult:
    """Wynik ewaluacji binarnej (klasa pozytywna = POSITIVE)."""

    model_name: str
    dataset_name: str
    tp: int
    fp: int
    tn: int
    fn: int
    seconds: float = 0.0

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.n if self.n else 0.0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


@dataclass(slots=True)
class ScoredReview:
    """Opinia + predykcja wybranego modelu (None = jeszcze nie przeanalizowana)."""

    review: Review
    prediction: Prediction | None = None

    @property
    def sentiment(self) -> Sentiment | None:
        return self.prediction.sentiment if self.prediction else None

    @property
    def score(self) -> float | None:
        return self.prediction.score if self.prediction else None


@dataclass(slots=True)
class SentimentSummary:
    total: int
    positive: int
    negative: int
    unscored: int
    avg_score: float | None = None        # średni score przeanalizowanych opinii

    @property
    def positive_share(self) -> float | None:
        """Udział pozytywnych wśród przeanalizowanych (0–1) albo None, gdy brak predykcji."""
        scored = self.positive + self.negative
        return self.positive / scored if scored else None


@dataclass(frozen=True, slots=True)
class TermStat:
    term: str
    count: int
    sentiment: Sentiment
    weight: float = 0.0                   # np. log-odds / lift; 0 gdy nieużywane


class AlertLevel(StrEnum):
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class Alert:
    target_id: str
    level: AlertLevel
    message: str                          # komunikat po polsku, gotowy do GUI
    current_share: float | None = None
    baseline_share: float | None = None
    detected_at: datetime = field(default_factory=utcnow)


@dataclass(slots=True)
class FetchReport:
    """Wynik pobierania opinii (O1) – pokazywany w GUI."""

    target_id: str
    fetched: int = 0                      # ile zwróciło źródło
    new: int = 0                          # ile nowych zapisano w repozytorium
    analyzed: int = 0                     # ile przeanalizował domyślny model
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def duplicates(self) -> int:
        return self.fetched - self.new

    @property
    def ok(self) -> bool:
        return not self.errors
