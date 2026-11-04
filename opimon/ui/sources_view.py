"""Logika widoku „Źródła danych” (D4, właściciel: O1) – bez elementów Streamlit, testowalna."""

from __future__ import annotations

import re

import pandas as pd

from opimon.errors import SourceError
from opimon.interfaces import ReviewSource
from opimon.models import FetchReport, ScoredReview, Target
from opimon.services import AppServices

_STEAM_URL_RE = re.compile(r"store\.steampowered\.com/app/(\d+)", re.I)

WATCHLIST_COLUMNS = ["Obiekt", "Źródło", "Opinie", "Najnowsza opinia", "Strona", "id"]
REVIEW_COLUMNS = ["Data", "Obiekt", "Źródło", "Sentyment", "P(pozytywny)", "Ocena autora",
                  "Etykieta źródła", "Treść", "Link", "id"]


def resolve_manual_target(source: ReviewSource, text: str) -> Target:
    """Identyfikator lub URL wpisany ręcznie -> cel. Nieznany -> `SourceError` po polsku.

    * Steam: appid (`570`) albo URL sklepu (`https://store.steampowered.com/app/570/...`);
    * pozostałe źródła: to, co rozumie `find_targets` (np. Metacritic: URL lub `movie/<slug>`),
      bierzemy pierwszy wynik.
    """
    value = text.strip()
    if not value:
        raise SourceError("Podaj identyfikator lub adres URL.")
    from_appid = getattr(source, "target_from_appid", None)
    if callable(from_appid):
        if m := _STEAM_URL_RE.search(value):
            return from_appid(m.group(1))
        if value.isdigit():
            return from_appid(value)
    found = source.find_targets(value, limit=1)
    if not found:
        raise SourceError(f"{source.label}: nie znaleziono obiektu „{value}”.")
    return found[0]


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
        rows.append({
            "Obiekt": t.name,
            "Źródło": source_label(services, t.source),
            "Opinie": services.repository.count_reviews(t.id),
            "Najnowsza opinia": services.repository.latest_review_time(t.id),
            "Strona": t.url,
            "id": t.id,
        })
    return pd.DataFrame(rows, columns=WATCHLIST_COLUMNS)


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
