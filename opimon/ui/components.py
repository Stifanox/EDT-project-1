"""Wspólne komponenty GUI (P0). Plik współdzielony: tylko zmiany wstecznie zgodne."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import streamlit as st

from opimon.models import ScoredReview
from opimon.services import AppServices
from opimon.ui import nav

_FLASH_KEY = "_flash_messages"
ALL = "__all__"


def flash(message: str, kind: str = "success") -> None:
    """Komunikat, który przetrwa `st.rerun()` (pokaże go `show_flashes()` po przeładowaniu)."""
    st.session_state.setdefault(_FLASH_KEY, []).append((kind, message))


def show_flashes() -> None:
    for kind, message in st.session_state.pop(_FLASH_KEY, []):
        getattr(st, kind, st.info)(message)


def show_module_errors(services: AppServices) -> None:
    if services.module_errors:
        with st.expander(f"⚠️ Problemy modułów ({len(services.module_errors)})"):
            for module, error in services.module_errors.items():
                st.warning(f"**{module}**: {error}")


def page_header(services: AppServices, title: str, caption: str | None = None) -> None:
    st.title(title)
    if caption:
        st.caption(caption)
    show_flashes()
    show_module_errors(services)


def model_selector(services: AppServices, label: str = "Model sentymentu") -> str | None:
    """Wybór spośród GOTOWYCH modeli; wybór jest wspólny dla wszystkich widoków."""
    ready = services.ready_models()
    if not ready:
        st.warning("Żaden model nie jest gotowy – wytrenuj model w widoku „Modele”.")
        return None
    if st.session_state.get(nav.MODEL_KEY) not in ready:
        st.session_state[nav.MODEL_KEY] = ready[0]
    return st.selectbox(
        label, ready, key=nav.MODEL_KEY, format_func=lambda n: services.models[n].label
    )


def target_selector(
    services: AppServices, key: str, label: str = "Obiekt", allow_all: bool = True
) -> str | None:
    """Wybór monitorowanego celu; `None` = wszystkie."""
    options = ([ALL] if allow_all else []) + [t.id for t in services.repository.list_targets()]
    if not options:
        return None
    choice = st.selectbox(
        label,
        options,
        key=key,
        format_func=lambda tid: "Wszystkie" if tid == ALL else services.target_name(tid),
    )
    return None if choice == ALL else choice


def reviews_table(services: AppServices, rows: Sequence[ScoredReview]) -> pd.DataFrame:
    """Opinie -> tabela do `st.dataframe` (liczby jako liczby, daty jako daty)."""
    return pd.DataFrame(
        {
            "Data": [r.review.created_at for r in rows],
            "Obiekt": [services.target_name(r.review.target_id) for r in rows],
            "Sentyment": [
                f"{r.sentiment.icon} {r.sentiment.label_pl}" if r.sentiment else "–" for r in rows
            ],
            "P(pozytywny)": [r.score for r in rows],
            "Etykieta źródła": [r.review.label.label_pl if r.review.label else "–" for r in rows],
            "Treść": [r.review.text for r in rows],
            "id": [r.review.id for r in rows],
        }
    )


SCORE_COLUMN = st.column_config.ProgressColumn(
    "P(pozytywny)", min_value=0.0, max_value=1.0, format="%.2f"
)
