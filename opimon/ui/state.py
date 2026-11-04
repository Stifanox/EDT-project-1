"""Stan aplikacji Streamlit (P0). Jedna instancja `AppServices` na proces serwera.

Synchronizacja z innymi procesami (np. CLI `refresh` z D5 piszące do SQLite) nie wymaga
nic dodatkowego: fasada nie trzyma opinii w pamięci, każde odświeżenie czyta repozytorium.
"""

from __future__ import annotations

import streamlit as st

from opimon.services import AppServices, build_services


@st.cache_resource(show_spinner="Ładowanie modeli i opinii…")
def _cached_services() -> AppServices:
    return build_services()


def get_services() -> AppServices:
    return _cached_services()


get_services.clear = _cached_services.clear  # type: ignore[attr-defined]  # dla testów
