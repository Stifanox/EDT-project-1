"""Filtrowanie, paginacja i podświetlanie opinii dla przeglądarki „Opinie” (A3).

Czyste funkcje bez Streamlit. Obiekt i model wybiera się wcześniej
(`AppServices.scored_reviews(target_id, model_name)`), tutaj filtrujemy wynik.
"""

from __future__ import annotations

import html
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from opimon.models import ScoredReview
from opimon.textproc import content_tokens

SENTIMENT_FILTERS = ("all", "positive", "negative", "unscored")
TERM_STYLE = "background:#ffe066"
POSITIVE_STYLE = "background:#c9f2d5"
NEGATIVE_STYLE = "background:#f9d0cd"


@dataclass(frozen=True, slots=True)
class ReviewQuery:
    """Filtry przeglądarki. Wartości domyślne = brak filtra."""

    sentiment: str = "all"                # jeden z SENTIMENT_FILTERS
    term: str = ""                        # fraza (bez rozróżniania wielkości liter)
    date_from: date | None = None         # włącznie (UTC)
    date_to: date | None = None           # włącznie (cały dzień, UTC)
    score_min: float = 0.0                # zakres P(pozytywny); pełny zakres = brak filtra
    score_max: float = 1.0
    only_wrong: bool = False              # tylko opinie, w których predykcja ≠ etykieta źródła

    @property
    def score_filtered(self) -> bool:
        return self.score_min > 0.0 or self.score_max < 1.0


def matches_term(text: str, term: str) -> bool:
    """Podciąg (bez wielkości liter) albo – dla fraz ze słów kluczowych (A4) – kolejne słowa
    po usunięciu stop-słów: „waste money” pasuje do „waste of money”."""
    term = term.strip().lower()
    if not term or term in text.lower():
        return True
    words = content_tokens(term)
    if len(words) < 2:
        return False
    tokens = content_tokens(text)
    k = len(words)
    return any(tokens[i : i + k] == words for i in range(len(tokens) - k + 1))


def _term_pattern(phrase: str) -> str:
    words = phrase.split()
    if len(words) < 2:
        return re.escape(phrase)
    gap = r"(?:\W+[\w']+){0,3}?\W+"      # do 3 słów (np. stop-słów) między słowami frazy
    return re.escape(phrase) + "|" + r"\b" + gap.join(re.escape(w) for w in words) + r"\b"


def is_misclassified(row: ScoredReview) -> bool:
    """Predykcja modelu różni się od etykiety ze źródła (obie muszą istnieć)."""
    return (row.sentiment is not None and row.review.label is not None
            and row.sentiment is not row.review.label)


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def apply_filters(rows: Sequence[ScoredReview], query: ReviewQuery) -> list[ScoredReview]:
    """Opinie spełniające wszystkie filtry, w kolejności wejściowej.

    Zawężenie zakresu score wyklucza opinie bez predykcji (nie mają score)."""
    if query.sentiment not in SENTIMENT_FILTERS:
        raise ValueError(f"Nieznany filtr sentymentu: {query.sentiment!r}")
    start = _day_start(query.date_from) if query.date_from else None
    end = _day_start(query.date_to) + timedelta(days=1) if query.date_to else None
    out = []
    for r in rows:
        if query.sentiment == "unscored" and r.prediction is not None:
            continue
        if query.sentiment in {"positive", "negative"} and (
            r.sentiment is None or r.sentiment.value != query.sentiment
        ):
            continue
        if start is not None and r.review.created_at < start:
            continue
        if end is not None and r.review.created_at >= end:
            continue
        if query.score_filtered and (
            r.score is None or not query.score_min <= r.score <= query.score_max
        ):
            continue
        if query.only_wrong and not is_misclassified(r):
            continue
        if not matches_term(r.review.text, query.term):
            continue
        out.append(r)
    return out


@dataclass(frozen=True, slots=True)
class Page:
    rows: list[ScoredReview]
    number: int        # numer strony od 1 (po przycięciu do zakresu)
    count: int         # liczba stron (co najmniej 1)
    start: int         # indeks pierwszej opinii na stronie w całej liście (od 0)


def paginate(rows: Sequence[ScoredReview], page: int, size: int) -> Page:
    """Strona `page` (od 1) o rozmiarze `size`; numer spoza zakresu jest przycinany."""
    if size <= 0:
        raise ValueError(f"size musi być dodatnie, dostano {size}")
    count = max(1, math.ceil(len(rows) / size))
    number = min(max(1, page), count)
    start = (number - 1) * size
    return Page(list(rows[start : start + size]), number, count, start)


def highlight_html(
    text: str, term: str = "", weights: Sequence[tuple[str, float]] = ()
) -> str:
    """Tekst jako bezpieczny HTML z podświetleniem frazy `term` (żółte) i słów z wyjaśnienia
    modelu (`weights`: dodatnie = zielone, ujemne = czerwone). Bez rozróżniania wielkości liter."""
    styles: dict[str, str] = {}
    patterns: list[str] = []
    phrase = " ".join(term.split())
    if phrase:
        patterns.append(f"(?P<term>{_term_pattern(phrase)})")
    for word, weight in sorted(weights, key=lambda w: -len(w[0])):
        word = word.strip()
        if word and weight and word.lower() not in styles:
            patterns.append(r"\b" + re.escape(word) + r"\b")
            styles[word.lower()] = POSITIVE_STYLE if weight > 0 else NEGATIVE_STYLE
    if not patterns:
        return html.escape(text).replace("\n", "<br>")
    regex = re.compile("|".join(patterns), re.IGNORECASE)
    parts, pos = [], 0
    for m in regex.finditer(text):
        parts.append(html.escape(text[pos : m.start()]))
        if phrase and m.group("term"):
            style = TERM_STYLE
        else:
            style = styles.get(m.group(0).lower(), TERM_STYLE)
        parts.append(f'<mark style="{style}">{html.escape(m.group(0))}</mark>')
        pos = m.end()
    parts.append(html.escape(text[pos:]))
    return "".join(parts).replace("\n", "<br>")
