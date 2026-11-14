"""Nawigacja między widokami (P0, KONTRAKT).

* `open_reviews(...)` – z dowolnego widoku (np. kliknięcie w dashboardzie, alert, słowo
  kluczowe) przejdź do „Opinii” z ustawionymi filtrami. Widok „Opinie” odczytuje je przez
  `review_filters()` i po zastosowaniu woła `clear_review_filters()`.
* `open_dashboard(target_id)` – np. ze „Źródeł danych” po pobraniu opinii.
  Dashboard odczytuje wybór przez `dashboard_target()`, potem `clear_dashboard_target()`.
* Wspólny wybór modelu między widokami: klucz `MODEL_KEY` w `session_state`
  (używa go `components.model_selector`).
"""

from __future__ import annotations

from datetime import date
from typing import TypedDict

import streamlit as st

from opimon.models import Sentiment

PAGE_HOME = "app.py"
PAGE_SOURCES = "pages/1_Zrodla_danych.py"
PAGE_MODELS = "pages/2_Modele.py"
PAGE_EVALUATION = "pages/3_Ewaluacja.py"
PAGE_DASHBOARD = "pages/4_Dashboard.py"
PAGE_REVIEWS = "pages/5_Opinie.py"

MODEL_KEY = "selected_model"
_REVIEW_FILTERS_KEY = "nav_review_filters"
_DASHBOARD_TARGET_KEY = "nav_dashboard_target"


class ReviewFilters(TypedDict, total=False):
    target_id: str | None
    sentiment: str | None       # Sentiment.value
    term: str | None            # słowo do wyszukania / podświetlenia
    review_id: str | None       # konkretna opinia do pokazania
    date_from: date | None      # zakres dat (UTC, włącznie); dodane w A3
    date_to: date | None


def open_reviews(
    target_id: str | None = None,
    sentiment: Sentiment | None = None,
    term: str | None = None,
    review_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> None:
    st.session_state[_REVIEW_FILTERS_KEY] = ReviewFilters(
        target_id=target_id,
        sentiment=sentiment.value if sentiment else None,
        term=term,
        review_id=review_id,
        date_from=date_from,
        date_to=date_to,
    )
    st.switch_page(PAGE_REVIEWS)


def review_filters() -> ReviewFilters | None:
    return st.session_state.get(_REVIEW_FILTERS_KEY)


def clear_review_filters() -> None:
    st.session_state.pop(_REVIEW_FILTERS_KEY, None)


def open_dashboard(target_id: str | None = None) -> None:
    st.session_state[_DASHBOARD_TARGET_KEY] = target_id
    st.switch_page(PAGE_DASHBOARD)


def dashboard_target() -> str | None:
    return st.session_state.get(_DASHBOARD_TARGET_KEY)


def clear_dashboard_target() -> None:
    st.session_state.pop(_DASHBOARD_TARGET_KEY, None)
