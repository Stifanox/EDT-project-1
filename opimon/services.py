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
from typing import TYPE_CHECKING, Literal, TypeVar

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
    Review,
    ScoredReview,
    Target,
)

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)
T = TypeVar("T")

ANALYZE_BATCH = 64


# --------------------------------------------------------------------------- #
# Fabryki – każda należy do jednej osoby
# --------------------------------------------------------------------------- #
def _make_repository() -> ReviewRepository:  # O1
    # TODO(D2): SqliteReviewRepository(config.DB_PATH) – ścieżkę czytaj tutaj, w chwili wywołania.
    from opimon.storage import InMemoryReviewRepository

    return InMemoryReviewRepository()


def _make_sources() -> dict[str, ReviewSource]:  # O1
    # TODO(D1/D3): dodaj SteamReviewSource i źródło scrapujące. Kolejność = kolejność w GUI.
    from opimon.sources import SampleSource

    return {"sample": SampleSource()}


def _make_models() -> dict[str, SentimentModel]:  # O2
    from opimon.sentiment import TfidfLogRegModel, TransformerModel, VaderModel

    return {"tfidf_lr": TfidfLogRegModel(), "vader": VaderModel(),
            "distilbert": TransformerModel()}


def _make_training_data() -> dict[str, TrainingDataProvider]:  # O2
    from opimon.sentiment import ImdbTrainingData, SampleTrainingData

    return {"imdb": ImdbTrainingData(), "sample_movies": SampleTrainingData()}


def _make_analytics() -> OpinionAnalytics:  # O3
    from opimon.analytics import SentimentAnalytics

    return SentimentAnalytics()


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
    def load_model(self, model_name: str, allow_download: bool = False) -> ModelInfo:
        """Jawne wczytanie opcjonalnych wag; odświeżenie GUI samo ich nie pobiera."""
        model = self.models[model_name]
        loader = getattr(model, "load", None)
        if loader is not None:
            loader(allow_download=allow_download)
        return model.info()

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
        source_name: str | None = None,
        force: bool = False,
    ) -> EvalResult:
        """`test` – część testowa zbioru treningowego; `live` – opinie z Internetu,
        które mają etykietę ze źródła (`Review.label`, np. Steam `voted_up`)."""
        from opimon.sentiment.evaluation import evaluate_cached

        examples, name, _ = self._evaluation_data(
            on, dataset_name, max_test, target_id, source_name
        )
        return evaluate_cached(self.models[model_name], examples, name, force=force).result

    def _evaluation_data(
        self, on: Literal["test", "live"], dataset_name: str | None = None,
        max_test: int | None = None, target_id: str | None = None,
        source_name: str | None = None,
    ) -> tuple[list[LabeledText], str, list[Review]]:
        """Te same dane i identyfikator dla metryk, błędów oraz porównań."""
        if max_test is not None and max_test < 0:
            raise ValueError("Limit przykładów nie może być ujemny.")
        if on == "test":
            provider = self._provider(dataset_name)
            return provider.load(max_test=max_test).test, provider.name, []
        if on != "live":
            raise ValueError("Wybierz dane test albo live.")
        reviews = [r for r in self.repository.list_reviews(target_id)
                   if r.label is not None and (source_name is None or r.source == source_name)]
        reviews = reviews[:max_test]
        if source_name is None:
            name = f"live:{target_id or 'all'}"
        else:
            prefix = "demo" if source_name == "sample" else "live"
            name = f"{prefix}:{source_name}" + (f":{target_id}" if target_id else "")
        return [LabeledText(r.text, r.label) for r in reviews], name, reviews

    def evaluation_sources(self, target_id: str | None = None) -> list[str]:
        """Źródła z co najmniej jedną oznaczoną opinią; próbka demo pozostaje jawna."""
        return sorted({r.source for r in self.repository.list_reviews(target_id)
                       if r.label is not None})

    def compare_models(
        self, on: Literal["test", "live"] = "test", dataset_name: str | None = None,
        max_test: int | None = None, target_id: str | None = None,
        source_name: str | None = None, force: bool = False,
    ) -> pd.DataFrame:
        """Porównaj gotowe modele na wspólnym zbiorze i zapisz wyniki w cache M5."""
        from opimon.sentiment.evaluation import compare_models

        examples, name, _ = self._evaluation_data(
            on, dataset_name, max_test, target_id, source_name
        )
        return compare_models(self.models, examples, name, force=force)

    def evaluation_details(
        self, on: Literal["test", "live"] = "test", dataset_name: str | None = None,
        max_test: int | None = None, target_id: str | None = None,
        source_name: str | None = None, limit: int = 20,
    ) -> dict:
        """Błędy modeli i niezgodności z tej samej próby co tabela porównawcza."""
        from opimon.sentiment.evaluation import disagreements, model_errors

        examples, name, reviews = self._evaluation_data(
            on, dataset_name, max_test, target_id, source_name
        )
        errors, warnings = [], []
        healthy = {}
        for model_name in self.ready_models():
            try:
                errors.extend(model_errors(self.models[model_name], examples, name,
                                           review_ids=[r.id for r in reviews] if reviews else None,
                                           limit=limit))
                healthy[model_name] = self.models[model_name]
            except Exception as exc:
                warnings.append(f"{model_name}: {exc}")
        differences = disagreements(healthy, reviews, limit=limit, dataset_name=name)
        return {"errors": errors, "disagreements": differences, "warnings": warnings}

    def explain_text(self, text: str, model_name: str, n: int = 10) -> list[tuple[str, float]]:
        """Opcjonalne wyjaśnienie modelu udostępnione przez fasadę dla M6 i A3."""
        explain = getattr(self.models[model_name], "explain", None)
        return explain(text, n=n) if explain is not None else []

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
