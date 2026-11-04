"""Widok „Opinie” – przeglądarka (właściciel: O3, rozbudowa w A3)."""

import streamlit as st

from opimon.ui import nav
from opimon.ui.components import (
    SCORE_COLUMN,
    model_selector,
    page_header,
    reviews_table,
    target_selector,
)
from opimon.ui.state import get_services

st.set_page_config(page_title="Opinie", page_icon="📝", layout="wide")
services = get_services()
page_header(services, "📝 Opinie")

SENTIMENTS = ["all", "positive", "negative", "unscored"]
if (preset := nav.review_filters()) is not None:
    st.session_state["rev_target"] = preset.get("target_id") or "__all__"
    st.session_state["rev_sentiment"] = preset.get("sentiment") or "all"
    st.session_state["rev_term"] = preset.get("term") or ""
    nav.clear_review_filters()

c1, c2, c3, c4 = st.columns(4)
with c1:
    target_id = target_selector(services, key="rev_target")
with c2:
    model_name = model_selector(services)
sentiment = c3.selectbox("Sentyment", SENTIMENTS, key="rev_sentiment", format_func=lambda s: {
    "all": "Wszystkie", "positive": "🟢 pozytywne", "negative": "🔴 negatywne",
    "unscored": "bez predykcji"}[s])
term = c4.text_input("Zawiera słowo", key="rev_term")

rows = services.scored_reviews(target_id, model_name)
if sentiment == "unscored":
    rows = [r for r in rows if r.prediction is None]
elif sentiment != "all":
    rows = [r for r in rows if r.sentiment is not None and r.sentiment.value == sentiment]
if term.strip():
    rows = [r for r in rows if term.strip().lower() in r.review.text.lower()]

st.caption(f"{len(rows)} opinii")
st.dataframe(reviews_table(services, rows), hide_index=True, use_container_width=True,
             column_config={"P(pozytywny)": SCORE_COLUMN})
