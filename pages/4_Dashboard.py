"""Widok „Dashboard” (właściciel: O3, rozbudowa w A2)."""

import streamlit as st

from opimon.models import Sentiment
from opimon.ui import nav
from opimon.ui.components import model_selector, page_header, target_selector
from opimon.ui.state import get_services

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
services = get_services()
page_header(services, "📊 Dashboard sentymentu")

if (preset := nav.dashboard_target()) is not None:
    st.session_state["dash_target"] = preset
    nav.clear_dashboard_target()
c1, c2 = st.columns(2)
with c1:
    target_id = target_selector(services, key="dash_target")
with c2:
    model_name = model_selector(services)

rows = services.scored_reviews(target_id, model_name)
summary = services.analytics.summary(rows)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Opinie", summary.total)
m2.metric("Pozytywne", summary.positive)
m3.metric("Negatywne", summary.negative)
share = summary.positive_share
m4.metric("Udział pozytywnych", f"{share:.0%}" if share is not None else "–")

for alert in services.analytics.alerts(rows):
    st.warning(f"**{services.target_name(alert.target_id)}**: {alert.message}")

st.subheader("Trend (dziennie)")
trend = services.analytics.trend(rows, "D")
if trend.empty:
    st.info("Brak danych.")
else:
    st.line_chart(trend.set_index("period")[["positive", "negative"]])

if target_id is None:
    st.subheader("Porównanie obiektów")
    cmp = services.analytics.compare_targets(rows)
    cmp["target_id"] = cmp["target_id"].map(services.target_name)
    st.dataframe(cmp, hide_index=True, use_container_width=True)

st.subheader("Charakterystyczne słowa")
cols = st.columns(2)
for col, sentiment in zip(cols, (Sentiment.POSITIVE, Sentiment.NEGATIVE), strict=True):
    with col:
        st.markdown(f"{sentiment.icon} **{sentiment.label_pl}**")
        terms = services.analytics.top_terms(rows, sentiment, n=10)
        st.dataframe({"Słowo": [t.term for t in terms], "Liczba": [t.count for t in terms]},
                     hide_index=True, use_container_width=True)
        if st.button(f"Pokaż opinie: {sentiment.label_pl}", key=f"dash_open_{sentiment.value}"):
            nav.open_reviews(target_id, sentiment)
