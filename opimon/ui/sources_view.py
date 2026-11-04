"""Logika widoku „Źródła danych” (D4, właściciel: O1) – bez elementów Streamlit, testowalna."""

from __future__ import annotations

import pandas as pd

from opimon.models import FetchReport, ScoredReview
from opimon.services import AppServices
from opimon.sources.resolve import resolve_target
from opimon.storage import FetchLogEntry

WATCHLIST_COLUMNS = ["Obiekt", "Źródło", "Opinie", "Najnowsza opinia", "Ostatnie pobranie",
                     "Status", "Strona", "id"]
LOG_COLUMNS = ["Czas", "Obiekt", "Źródło", "Pobrano", "Nowe", "Przeanalizowano", "Czas [s]",
               "Błędy"]
REVIEW_COLUMNS = ["Data", "Obiekt", "Źródło", "Sentyment", "P(pozytywny)", "Ocena autora",
                  "Etykieta źródła", "Treść", "Link", "id"]


# Przeniesione do `opimon.sources.resolve` (używa też CLI z D5); nazwa zostaje dla zgodności.
resolve_manual_target = resolve_target


def fetch_summary(report: FetchReport, name: str) -> tuple[str, str]:
    """Raport pobierania -> (rodzaj komunikatu Streamlit, treść)."""
    msg = (f"{name}: pobrano {report.fetched}, nowych {report.new}, "
           f"duplikatów {report.duplicates}, przeanalizowano {report.analyzed} "
           f"({report.seconds:.1f} s).")
    if not report.ok:
        return "warning", msg
    if report.fetched == 0:
        return "info", f"{name}: brak nowych opinii od ostatniego pobrania."
    return "success", msg


def refresh_summary(reports: list[FetchReport]) -> tuple[str, str]:
    failed = [r for r in reports if not r.ok]
    msg = (f"Odświeżono {len(reports)} obiektów: nowych opinii {sum(r.new for r in reports)}, "
           f"przeanalizowano {sum(r.analyzed for r in reports)}.")
    if failed:
        return "warning", msg + f" Błędy: {len(failed)} (szczegóły poniżej)."
    return "success", msg


def source_label(services: AppServices, source_name: str) -> str:
    src = services.sources.get(source_name)
    return src.label if src else source_name


def watchlist_frame(services: AppServices, source_name: str | None = None) -> pd.DataFrame:
    """Monitorowane obiekty: liczba opinii (liczba, nie tekst) i data najnowszej opinii."""
    rows = []
    for t in services.repository.list_targets():
        if source_name is not None and t.source != source_name:
            continue
        last = services.fetch_log.last(t.id)
        rows.append({
            "Obiekt": t.name,
            "Źródło": source_label(services, t.source),
            "Opinie": services.repository.count_reviews(t.id),
            "Najnowsza opinia": services.repository.latest_review_time(t.id),
            "Ostatnie pobranie": last.started_at if last else None,
            "Status": status_text(last),
            "Strona": t.url,
            "id": t.id,
        })
    return pd.DataFrame(rows, columns=WATCHLIST_COLUMNS)


def status_text(entry: FetchLogEntry | None) -> str:
    if entry is None:
        return "–"
    return "✅ OK" if entry.ok else f"⚠️ {entry.errors[0]}"


def fetch_log_frame(services: AppServices, limit: int = 50) -> pd.DataFrame:
    """Dziennik pobrań (od najnowszego) – liczby jako liczby."""
    entries = services.fetch_log.history(limit=limit)
    return pd.DataFrame(
        [{
            "Czas": e.started_at,
            "Obiekt": services.target_name(e.target_id),
            "Źródło": source_label(services, e.source),
            "Pobrano": e.fetched,
            "Nowe": e.new,
            "Przeanalizowano": e.analyzed,
            "Czas [s]": round(e.seconds, 2),
            "Błędy": "; ".join(e.errors),
        } for e in entries],
        columns=LOG_COLUMNS,
    )


def latest_reviews(
    services: AppServices,
    source_name: str | None = None,
    target_id: str | None = None,
    limit: int = 50,
) -> list[ScoredReview]:
    """Najnowsze opinie z filtrem źródła i/lub obiektu (domyślny model)."""
    if source_name is None or target_id is not None:
        rows = services.scored_reviews(target_id, limit=limit)
        return [r for r in rows if source_name is None or r.review.source == source_name]
    rows = services.scored_reviews()
    return [r for r in rows if r.review.source == source_name][:limit]


def reviews_frame(services: AppServices, rows: list[ScoredReview]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Data": [r.review.created_at for r in rows],
            "Obiekt": [services.target_name(r.review.target_id) for r in rows],
            "Źródło": [source_label(services, r.review.source) for r in rows],
            "Sentyment": [f"{r.sentiment.icon} {r.sentiment.label_pl}" if r.sentiment else "–"
                          for r in rows],
            "P(pozytywny)": [r.score for r in rows],
            "Ocena autora": [r.review.rating for r in rows],
            "Etykieta źródła": [r.review.label.label_pl if r.review.label else "–" for r in rows],
            "Treść": [r.review.text for r in rows],
            "Link": [r.review.url for r in rows],
            "id": [r.review.id for r in rows],
        },
        columns=REVIEW_COLUMNS,
    )
