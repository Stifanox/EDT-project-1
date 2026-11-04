"""Fasada aplikacji: jedyne miejsce, w którym moduły są ze sobą łączone.

GUI korzysta WYŁĄCZNIE z `AppServices` (przez `opimon.ui.state.get_services()`) i nigdy
nie tworzy źródeł, modeli ani repozytoriów samodzielnie.

Podmiana zaślepki na prawdziwą implementację = edycja JEDNEJ funkcji-fabryki:
  * `_make_repository()`, `_make_sources()`     – właściciel O1 (D1, D2, D3)
  * `_make_models()`, `_make_training_data()`   – właściciel O2 (M1–M4)
  * `_make_analytics()`                         – właściciel O3 (A1, A4, A5)
Nie edytuj fabryk innych osób – unikamy konfliktów w git.

Odporność: wyjątek w fabryce -> zaślepka + wpis w `module_errors` (GUI to pokazuje);
wyjątek modelu podczas analizy -> wpis w `module_errors`, reszta aplikacji działa.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Literal, TypeVar

from opimon import config
from opimon.errors import OpimonError
from opimon.interfaces import (
    OpinionAnalytics,
    ReviewRepository,
    ReviewSource,
    SentimentModel,
    TrainingDataProvider,
)
from opimon.models import (
    EvalResult,
    FetchReport,
    LabeledText,
    ModelInfo,
    Prediction,
    ScoredReview,
    Target,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")

ANALYZE_BATCH = 64


# --------------------------------------------------------------------------- #
# Fabryki – każda należy do jednej osoby
# --------------------------------------------------------------------------- #
def _make_repository() -> ReviewRepository:  # O1
    # config.DB_PATH czytany w chwili wywołania – testy podmieniają go na bazę tymczasową
    from opimon.storage import SqliteReviewRepository

    return SqliteReviewRepository(config.DB_PATH)


def _make_sources() -> dict[str, ReviewSource]:  # O1
    # Kolejność = kolejność w GUI (pierwsze = domyślne). `sample` = tryb offline.
    from opimon.sources import MetacriticReviewSource, SampleSource, SteamReviewSource

    return {
        "steam": SteamReviewSource(),
        "metacritic": MetacriticReviewSource(),
        "sample": SampleSource(),
    }


def _make_models() -> dict[str, SentimentModel]:  # O2
    # TODO(M2–M4): VADER, TF-IDF + LR, transformer. PIERWSZY gotowy model = domyślny
    # (nim analizowane są nowo pobrane opinie).
    from opimon.sentiment import LexiconStubModel, WordCountModel

    return {"lexicon_stub": LexiconStubModel(), "wordcount_stub": WordCountModel()}


def _make_training_data() -> dict[str, TrainingDataProvider]:  # O2
    # TODO(M1): ImdbTrainingData. Pierwszy = domyślny.
    from opimon.sentiment import SampleTrainingData

    return {"sample_movies": SampleTrainingData()}


def _make_analytics() -> OpinionAnalytics:  # O3
    # TODO(A1/A4/A5): pełna implementacja.
    from opimon.analytics import BasicAnalytics

    return BasicAnalytics()


def _stub_factories() -> dict[str, Callable[[], object]]:
    """Zaślepki P0 – awaryjne, gdy fabryka właściciela rzuci wyjątek."""
    from opimon.analytics import BasicAnalytics
    from opimon.sentiment import LexiconStubModel, SampleTrainingData
    from opimon.sources import SampleSource
    from opimon.storage import InMemoryReviewRepository

    return {
        "repository": InMemoryReviewRepository,
        "sources": lambda: {"sample": SampleSource()},
        "models": lambda: {"lexicon_stub": LexiconStubModel()},
        "training_data": lambda: {"sample_movies": SampleTrainingData()},
        "analytics": BasicAnalytics,
    }


# --------------------------------------------------------------------------- #
# Fasada
# --------------------------------------------------------------------------- #
class AppServices:
    def __init__(
        self,
        repository: ReviewRepository,
        sources: dict[str, ReviewSource],
        models: dict[str, SentimentModel],
        training_data: dict[str, TrainingDataProvider],
        analytics: OpinionAnalytics,
        module_errors: dict[str, str] | None = None,
    ) -> None:
        self.repository = repository
        self.sources = sources
        self.models = models
        self.training_data = training_data
        self.analytics = analytics
        self.module_errors: dict[str, str] = dict(module_errors or {})

    # ----------------------------------------------------------- wspólne (P0)
    def ready_models(self) -> list[str]:
        """Nazwy gotowych modeli w kolejności z `_make_models()`."""
        ready = []
        for name, model in self.models.items():
            try:
                if model.is_ready():
                    ready.append(name)
            except Exception as exc:  # noqa: BLE001 – cudzy moduł nie może wywrócić GUI
                self._record_error(f"model:{name}", exc)
        return ready

    @property
    def default_model_name(self) -> str | None:
        ready = self.ready_models()
        return ready[0] if ready else None

    def analyze_pending(self, model_name: str | None = None, target_id: str | None = None) -> int:
        """Przeanalizuj opinie bez predykcji danego modelu (domyślnie: domyślnego).
        Zwraca liczbę zapisanych predykcji; model niegotowy lub błąd modelu -> 0."""
        name = model_name or self.default_model_name
        if name is None or name not in self.models:
            return 0
        model = self.models[name]
        pending = self.repository.reviews_without_prediction(name, target_id)
        saved = 0
        try:
            if not model.is_ready():
                return 0
            for i in range(0, len(pending), ANALYZE_BATCH):
                batch = pending[i : i + ANALYZE_BATCH]
                scores = model.predict_proba([r.text for r in batch])
                if len(scores) != len(batch):
                    raise RuntimeError(f"zwrócił {len(scores)} wyników dla {len(batch)} tekstów")
                self.repository.save_predictions(
                    Prediction(r.id, name, float(s)) for r, s in zip(batch, scores, strict=True)
                )
                saved += len(batch)
        except Exception as exc:  # noqa: BLE001
            self._record_error(f"model:{name}", exc)
        else:
            self.module_errors.pop(f"model:{name}", None)
        return saved

    def scored_reviews(
        self,
        target_id: str | None = None,
        model_name: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[ScoredReview]:
        """Opinie (od najnowszej) z predykcją wskazanego modelu (domyślnie: domyślnego)."""
        reviews = self.repository.list_reviews(target_id, since, until, limit)
        name = model_name or self.default_model_name
        preds = self.repository.get_predictions(name, [r.id for r in reviews]) if name else {}
        return [ScoredReview(r, preds.get(r.id)) for r in reviews]

    def target_name(self, target_id: str) -> str:
        target = self.repository.get_target(target_id)
        return target.name if target else target_id

    def load_samples_if_empty(self) -> int:
        """Pusta baza + `config.LOAD_SAMPLES_IF_EMPTY` -> wczytaj opinie z `SampleSource`."""
        if not config.LOAD_SAMPLES_IF_EMPTY or self.repository.count_reviews() > 0:
            return 0
        from opimon.sources import SampleSource

        source = self.sources.get("sample") or SampleSource()
        added = 0
        for target in source.targets():   # type: ignore[attr-defined]
            added += self.fetch_reviews(source.name, target, limit=10_000, source=source).new
        return added

    # ----------------------------------------------------------- O1: dane
    def fetch_reviews(
        self,
        source_name: str,
        target: Target,
        limit: int | None = None,
        incremental: bool = True,
        analyze: bool = True,
        source: ReviewSource | None = None,
    ) -> FetchReport:
        """Pobierz opinie celu, zapisz nowe, przeanalizuj domyślnym modelem.
        Błędy źródła trafiają do `FetchReport.errors` (nie są rzucane)."""
        start = time.perf_counter()
        report = FetchReport(target.id)
        src = source or self.sources.get(source_name)
        if src is None:
            report.errors.append(f"Nieznane źródło: {source_name}")
            return report
        since = self.repository.latest_review_time(target.id) if incremental else None
        try:
            reviews = src.fetch(target, limit or config.DEFAULT_FETCH_LIMIT, since)
        except OpimonError as exc:
            report.errors.append(str(exc))
            reviews = []
        except Exception as exc:  # noqa: BLE001
            logger.exception("Źródło %s rzuciło nieoczekiwany wyjątek", source_name)
            report.errors.append(f"Nieoczekiwany błąd źródła {source_name}: {exc}")
            reviews = []
        self.repository.save_target(target)
        report.fetched = len(reviews)
        report.new = self.repository.add_reviews(reviews)
        if analyze and report.new:
            report.analyzed = self.analyze_pending(target_id=target.id)
        report.seconds = time.perf_counter() - start
        return report

    def refresh_all(self, limit: int | None = None) -> list[FetchReport]:
        """Pobierz przyrostowo nowe opinie dla wszystkich zapisanych celów (D5 rozbudowuje)."""
        return [
            self.fetch_reviews(t.source, t, limit) for t in self.repository.list_targets()
        ]

    # ----------------------------------------------------------- O2: modele
    def model_infos(self) -> list[ModelInfo]:
        infos = []
        for name, model in self.models.items():
            try:
                infos.append(model.info())
            except Exception as exc:  # noqa: BLE001
                self._record_error(f"model:{name}", exc)
        return infos

    def train_model(
        self, model_name: str, dataset_name: str | None = None, max_train: int | None = None
    ) -> ModelInfo:
        """Trenuj model, usuń jego stare predykcje i przeanalizuj wszystkie opinie od nowa.
        Rzuca `DatasetUnavailableError` / `ValueError` – GUI pokazuje komunikat."""
        model = self.models[model_name]
        dataset = self._provider(dataset_name).load(max_train=max_train)
        model.train(dataset.train)
        self.repository.delete_predictions(model_name)
        self.analyze_pending(model_name)
        return model.info()

    def predict_text(self, text: str, model_name: str | None = None) -> float:
        """P(pozytywny) dla dowolnego tekstu („wypróbuj model”)."""
        name = model_name or self.default_model_name
        if name is None:
            raise OpimonError("Żaden model nie jest gotowy – wytrenuj model w widoku „Modele”.")
        return self.models[name].predict_proba([text])[0]

    def evaluate_model(
        self,
        model_name: str,
        on: Literal["test", "live"] = "test",
        dataset_name: str | None = None,
        max_test: int | None = None,
        target_id: str | None = None,
    ) -> EvalResult:
        """`test` – część testowa zbioru treningowego; `live` – opinie z Internetu,
        które mają etykietę ze źródła (`Review.label`, np. Steam `voted_up`)."""
        from opimon.sentiment import evaluate

        if on == "test":
            provider = self._provider(dataset_name)
            examples = provider.load(max_test=max_test).test
            name = provider.name
        else:
            examples = [
                LabeledText(r.text, r.label)
                for r in self.repository.list_reviews(target_id)
                if r.label is not None
            ][:max_test]
            name = f"live:{target_id or 'all'}"
        if not examples:
            raise ValueError("Brak opinii z etykietą do ewaluacji.")
        return evaluate(self.models[model_name], examples, name)

    # ----------------------------------------------------------- pomocnicze
    def _provider(self, dataset_name: str | None) -> TrainingDataProvider:
        if dataset_name is None:
            return next(iter(self.training_data.values()))
        return self.training_data[dataset_name]

    def _record_error(self, module: str, exc: BaseException) -> None:
        logger.exception("Błąd modułu %s", module, exc_info=exc)
        self.module_errors[module] = f"{type(exc).__name__}: {exc}"


def _build(name: str, factory: Callable[[], T], errors: dict[str, str]) -> T:
    try:
        return factory()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fabryka %s nie działa – używam zaślepki P0", name)
        errors[name] = f"{type(exc).__name__}: {exc} (użyto zaślepki)"
        return _stub_factories()[name]()  # type: ignore[return-value]


def build_services(load_samples: bool = True) -> AppServices:
    """Złóż aplikację z fabryk. Fabryki są wywoływane przez nazwę modułu (nie domknięcie),
    żeby testy mogły je podmieniać przez `monkeypatch.setattr(services, "_make_…", …)`."""
    import opimon.services as mod

    errors: dict[str, str] = {}
    services = AppServices(
        repository=_build("repository", mod._make_repository, errors),
        sources=_build("sources", mod._make_sources, errors),
        models=_build("models", mod._make_models, errors),
        training_data=_build("training_data", mod._make_training_data, errors),
        analytics=_build("analytics", mod._make_analytics, errors),
        module_errors=errors,
    )
    if load_samples:
        services.load_samples_if_empty()
    services.analyze_pending()
    return services
