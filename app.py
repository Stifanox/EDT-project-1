"""Punkt wejścia: `streamlit run app.py`."""

import streamlit as st

from opimon.ui import nav
from opimon.ui.components import page_header
from opimon.ui.state import get_services

st.set_page_config(page_title="Monitor opinii", page_icon="💬", layout="wide")

services = get_services()
page_header(
    services,
    "💬 Inteligentny system monitorowania opinii",
    "Pobieranie recenzji z Internetu (API / web scraping) · analiza sentymentu · dashboard",
)

summary = services.analytics.summary(services.scored_reviews())
c1, c2, c3, c4 = st.columns(4)
c1.metric("Monitorowane obiekty", len(services.repository.list_targets()))
c2.metric("Opinie w bazie", summary.total)
share = summary.positive_share
c3.metric("Udział pozytywnych", f"{share:.0%}" if share is not None else "–")
c4.metric("Gotowe modele", f"{len(services.ready_models())} / {len(services.models)}")

st.page_link(nav.PAGE_SOURCES, label="Źródła danych – pobieranie opinii", icon="🌐")
st.page_link(nav.PAGE_MODELS, label="Modele sentymentu – trening i test", icon="🧠")
st.page_link(nav.PAGE_EVALUATION, label="Ewaluacja i porównanie modeli", icon="📏")
st.page_link(nav.PAGE_DASHBOARD, label="Dashboard – monitoring sentymentu", icon="📊")
st.page_link(nav.PAGE_REVIEWS, label="Przeglądarka opinii", icon="📝")
