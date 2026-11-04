"""Interfejsy modułów (P0, KONTRAKT – plik zamrożony).

Każda implementacja musi przejść odpowiedni test w `tests/contracts/`.
Dozwolone są tylko zmiany wstecznie zgodne, z wpisem w PROGRESS.md -> „Dziennik decyzji”.

Interfejs -> właściciel -> fabryka w services.py -> test w tests/contracts/:
* ReviewSource         – O1 – `_make_sources()`       – test_source_contract.py
* ReviewRepository     – O1 – `_make_repository()`    – test_repository_contract.py
* SentimentModel       – O2 – `_make_models()`        – test_sentiment_model_contract.py
* TrainingDataProvider – O2 – `_make_training_data()` – test_training_data_contract.py
* OpinionAnalytics     – O3 – `_make_analytics()`     – test_analytics_contract.py
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from opimon.models import (
    Alert,
    Dataset,
    LabeledText,
    ModelInfo,
    Prediction,
    Review,
    ScoredReview,
    Sentiment,
    SentimentSummary,
    Target,
    TermStat,
)

if TYPE_CHECKING:
    import pandas as pd


@runtime_checkable
class ReviewSource(Protocol):
    """Źródło opinii z Internetu (API lub web scraping).

    Semantyka:
    * `find_targets(query)` – cele pasujące do zapytania (np. gry po nazwie), najwyżej `limit`;
      puste / białe zapytanie -> `[]`.
    * `fetch(target, limit, since)`:
      - zwraca najwyżej `limit` opinii, **od najnowszej**, bez powtórzeń `Review.id`;
      - każda opinia ma `source == self.name` i `target_id == target.id`;
      - `since` podane -> tylko opinie z `created_at > since` (pobieranie przyrostowe);
      - `text` oczyszczony (`textproc.clean_text`) i niepusty; puste opinie są pomijane;
      - `label` ustawiony, jeśli źródło podaje ocenę (np. Steam `voted_up`), inaczej None;
      - błędy sieci, limity, zmiana struktury strony, nieznany cel -> `SourceError`
        z czytelnym komunikatem po polsku (nigdy surowy wyjątek `requests` / `bs4`).
    * Implementacja szanuje `config.REQUEST_DELAY_S` i `config.HTTP_USER_AGENT`.
    """

    name: str     # identyfikator techniczny, np. "steam"; część `Review.id`
    label: str    # nazwa do GUI, np. "Steam – recenzje gier (API)"

    def find_targets(self, query: str, limit: int = 10) -> list[Target]: ...

    def fetch(
        self, target: Target, limit: int = 100, since: datetime | None = None
    ) -> list[Review]: ...


@runtime_checkable
class ReviewRepository(Protocol):
    """Trwałe przechowywanie celów, opinii i predykcji.

    Semantyka:
    * `add_reviews` – zapisuje opinie, których `id` jeszcze nie ma; istniejące są pomijane
      (nie nadpisywane). Zwraca liczbę NOWYCH opinii.
    * `list_reviews` – posortowane malejąco po `created_at`, przy remisie rosnąco po `id`;
      filtry `None` = brak filtra; `since` włącznie, `until` wyłącznie; `limit=None` = wszystkie.
    * `save_target` – upsert po `Target.id`. `list_targets` – posortowane po `name`.
    * `remove_target(id)` – usuwa cel, jego opinie i ich predykcje; nieznane id -> nic.
    * `latest_review_time(target_id)` – najnowsze `created_at` lub None (pobieranie przyrostowe).
    * `save_predictions` – upsert po (`review_id`, `model_name`).
    * `get_predictions(model, ids)` – `{review_id: Prediction}`; `ids=None` -> wszystkie dla modelu;
      pusty zbiór -> `{}`.
    * `delete_predictions(model)` – usuwa predykcje modelu (np. po ponownym treningu);
      zwraca ich liczbę.
    * `reviews_without_prediction(model, target_id)` – opinie bez predykcji danego modelu,
      w kolejności jak `list_reviews`.
    """

    def add_reviews(self, reviews: Iterable[Review]) -> int: ...

    def get_review(self, review_id: str) -> Review | None: ...

    def list_reviews(
        self,
        target_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[Review]: ...

    def count_reviews(self, target_id: str | None = None) -> int: ...

    def save_target(self, target: Target) -> None: ...

    def get_target(self, target_id: str) -> Target | None: ...

    def list_targets(self) -> list[Target]: ...

    def remove_target(self, target_id: str) -> None: ...

    def latest_review_time(self, target_id: str) -> datetime | None: ...

    def save_predictions(self, predictions: Iterable[Prediction]) -> None: ...

    def get_predictions(
        self, model_name: str, review_ids: Iterable[str] | None = None
    ) -> dict[str, Prediction]: ...

    def delete_predictions(self, model_name: str) -> int: ...

    def reviews_without_prediction(
        self, model_name: str, target_id: str | None = None
    ) -> list[Review]: ...


@runtime_checkable
class SentimentModel(Protocol):
    """Klasyfikator sentymentu (pozytywny / negatywny).

    Semantyka:
    * `predict_proba(texts)` – lista P(pozytywny) w [0, 1], **ta sama długość i kolejność**
      co `texts`; deterministyczna; `[]` -> `[]`; tekst pusty / same białe znaki -> 0.5.
    * Model z `requires_training=True` przed treningiem: `is_ready() == False`,
      a `predict_proba` rzuca `ModelNotReadyError`.
    * `train(data)` – po powrocie `is_ready() == True`. Dane z jedną klasą -> `ValueError`.
      Model może zapisać się w `config.MODELS_DIR / name` (czytaj config w chwili użycia),
      a `is_ready()` może leniwie wczytać zapisany model z dysku.
      Dla `requires_training=False` `train` nic nie robi.
    * Ciężkie biblioteki (`torch`, `transformers`) importuj leniwie (w metodzie, nie na górze
      pliku).
    """

    name: str     # np. "vader", "tfidf_lr", "distilbert"
    label: str    # do GUI, np. "TF-IDF + regresja logistyczna"
    requires_training: bool

    def is_ready(self) -> bool: ...

    def train(self, data: Sequence[LabeledText]) -> None: ...

    def predict_proba(self, texts: Sequence[str]) -> list[float]: ...

    def info(self) -> ModelInfo: ...


@runtime_checkable
class TrainingDataProvider(Protocol):
    """Zbiór treningowy (np. IMDB z Kaggle).

    Semantyka:
    * `load()` – deterministyczny podział train/test (stały seed), obie klasy w obu częściach,
      teksty oczyszczone jak w źródłach (`textproc.clean_text`).
    * `max_train` / `max_test` – ograniczenie liczności (zbalansowane klasowo, jeśli się da).
    * Brak danych lokalnie -> `DatasetUnavailableError` z instrukcją po polsku, jak je pobrać.
    """

    name: str
    label: str

    def load(self, max_train: int | None = None, max_test: int | None = None) -> Dataset: ...


@runtime_checkable
class OpinionAnalytics(Protocol):
    """Agregacje do dashboardu (czyste funkcje, bez Streamlit).

    Semantyka (dla wszystkich metod `rows` może być puste i zawierać opinie bez predykcji):
    * `summary` – liczności i średni score; opinie bez predykcji liczone w `unscored`.
    * `trend(rows, freq)` – DataFrame z kolumnami
      `period` (Timestamp UTC, początek okresu), `positive`, `negative`, `total` (int),
      `positive_share` (float 0–1 albo NaN); posortowany rosnąco po `period`; `freq` jak w pandas
      ("D", "W", "MS"). Puste `rows` -> pusty DataFrame z tymi kolumnami.
    * `compare_targets(rows)` – DataFrame: `target_id`, `total`, `positive`, `negative`,
      `positive_share`; posortowany malejąco po `total`.
    * `top_terms(rows, sentiment, n)` – najwyżej `n` termów charakterystycznych dla opinii
      o danym sentymencie (wg predykcji), malejąco wg `weight` (lub `count`), bez stop-słów.
    * `alerts(rows, now)` – alerty o spadku sentymentu (A5); `now=None` -> bieżący czas UTC.
    Liczby w DataFrame mają być liczbami (nie sformatowanymi stringami).
    """

    def summary(self, rows: Sequence[ScoredReview]) -> SentimentSummary: ...

    def trend(self, rows: Sequence[ScoredReview], freq: str = "D") -> pd.DataFrame: ...

    def compare_targets(self, rows: Sequence[ScoredReview]) -> pd.DataFrame: ...

    def top_terms(
        self, rows: Sequence[ScoredReview], sentiment: Sentiment, n: int = 20
    ) -> list[TermStat]: ...

    def alerts(
        self, rows: Sequence[ScoredReview], now: datetime | None = None
    ) -> list[Alert]: ...
