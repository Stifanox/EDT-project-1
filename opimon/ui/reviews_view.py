"""Widok „Opinie” (O3, A3): filtry, paginacja, szczegóły opinii i predykcje wszystkich modeli."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from opimon.analytics.filters import (
    SENTIMENT_FILTERS,
    ReviewQuery,
    apply_filters,
    highlight_html,
    paginate,
)
from opimon.analytics.report import reviews_to_csv
from opimon.models import Review, Sentiment
from opimon.services import AppServices
from opimon.ui import nav
from opimon.ui.components import (
    ALL,
    SCORE_COLUMN,
    model_selector,
    page_header,
    reviews_table,
    target_selector,
)

PAGE_SIZES = [25, 50, 100, 200]
DEFAULT_PAGE_SIZE = 50
SENTIMENT_LABELS = {"all": "Wszystkie", "positive": "🟢 pozytywne", "negative": "🔴 negatywne",
                    "unscored": "bez predykcji"}
# Stan zerowany przy przejściu z innego widoku i przy „Wyczyść filtry”.
_RESETTABLE = ("rev_date_from", "rev_date_to", "rev_score", "rev_wrong", "rev_page", "rev_table",
               "rev_focus")


def _reset_filters() -> None:
    for key in _RESETTABLE:
        st.session_state.pop(key, None)
    st.session_state["rev_sentiment"] = "all"
    st.session_state["rev_term"] = ""


def _apply_preset() -> None:
    """Filtry ustawione przez `nav.open_reviews(...)` w innym widoku."""
    preset = nav.review_filters()
    if preset is None:
        return
    _reset_filters()
    st.session_state["rev_target"] = preset.get("target_id") or ALL
    st.session_state["rev_sentiment"] = preset.get("sentiment") or "all"
    st.session_state["rev_term"] = preset.get("term") or ""
    for key in ("date_from", "date_to"):
        if preset.get(key) is not None:
            st.session_state[f"rev_{key}"] = preset[key]
    if preset.get("review_id"):
        st.session_state["rev_focus"] = preset["review_id"]
    nav.clear_review_filters()


def _render_filters(services: AppServices) -> tuple[str | None, str | None, ReviewQuery]:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        target_id = target_selector(services, key="rev_target")
    with c2:
        model_name = model_selector(services)
    sentiment = c3.selectbox("Sentyment", SENTIMENT_FILTERS, key="rev_sentiment",
                             format_func=SENTIMENT_LABELS.get)
    term = c4.text_input("Zawiera słowo", key="rev_term")
    d1, d2, d3, d4 = st.columns([2, 2, 3, 2])
    date_from = d1.date_input("Od dnia", value=None, key="rev_date_from", format="YYYY-MM-DD")
    date_to = d2.date_input("Do dnia", value=None, key="rev_date_to", format="YYYY-MM-DD")
    score = d3.slider("P(pozytywny) – zakres", 0.0, 1.0, (0.0, 1.0), step=0.05,
                      key="rev_score",
                      help="Zawężenie pokazuje tylko opinie z predykcją, np. 0,4–0,6 = niepewne.")
    d4.write("")
    only_wrong = d4.checkbox("Model się myli", key="rev_wrong",
                             help="Predykcja wybranego modelu ≠ etykieta ze źródła.")
    d4.button("Wyczyść filtry", key="rev_reset", on_click=_reset_filters)
    query = ReviewQuery(sentiment=sentiment, term=term, date_from=date_from, date_to=date_to,
                        score_min=score[0], score_max=score[1], only_wrong=only_wrong)
    return target_id, model_name, query


def _all_predictions(services: AppServices, review: Review) -> pd.DataFrame:
    """Predykcje wszystkich modeli: zapisane w bazie albo policzone teraz dla gotowych modeli."""
    ready = set(services.ready_models())
    cache: dict = st.session_state.setdefault("rev_live_predictions", {})
    rows = []
    for name, model in services.models.items():
        score, origin = None, "model niegotowy"
        stored = services.repository.get_predictions(name, [review.id]).get(review.id)
        if stored is not None:
            score, origin = stored.score, "zapisana"
        elif name in ready:
            key = (review.id, name)
            try:
                if key not in cache:
                    cache[key] = services.predict_text(review.text, name)
                score, origin = cache[key], "obliczona teraz"
            except Exception as exc:  # noqa: BLE001 – błąd modelu nie może wywrócić widoku
                origin = f"błąd: {exc}"
        sentiment = Sentiment.from_score(score) if score is not None else None
        agrees = None
        if sentiment is not None and review.label is not None:
            agrees = "✅ tak" if sentiment is review.label else "❌ nie"
        rows.append({
            "Model": model.label,
            "P(pozytywny)": score,
            "Sentyment": f"{sentiment.icon} {sentiment.label_pl}" if sentiment else "–",
            "Zgodny z etykietą": agrees or "–",
            "Predykcja": origin,
        })
    return pd.DataFrame(rows)


def _render_details(services: AppServices, review_id: str, model_name: str | None,
                    term: str, visible: bool) -> None:
    review = services.repository.get_review(review_id)
    st.subheader("Szczegóły opinii")
    if review is None:
        st.warning(f"Nie znaleziono opinii `{review_id}`.")
        return
    if not visible:
        st.caption("Ta opinia nie spełnia bieżących filtrów – pokazana, bo została wskazana.")
    left, right = st.columns([3, 2])
    with left:
        weights: list[tuple[str, float]] = []
        if model_name and st.checkbox("Podświetl słowa ważne dla modelu", value=True,
                                      key="rev_explain"):
            try:
                weights = services.explain_text(review.text, model_name, n=10)
            except Exception:  # noqa: BLE001 – wyjaśnienie jest opcjonalne
                weights = []
            if not weights:
                st.caption("Wybrany model nie udostępnia wyjaśnień.")
            else:
                st.caption("🟨 szukana fraza · 🟩 słowo za pozytywnym · 🟥 słowo za negatywnym")
        st.markdown(f"<div style='line-height:1.6'>{highlight_html(review.text, term, weights)}"
                    "</div>", unsafe_allow_html=True)
    with right:
        meta = {
            "Obiekt": services.target_name(review.target_id),
            "Źródło": review.source,
            "Autor": review.author or "–",
            "Data": review.created_at.strftime("%Y-%m-%d %H:%M UTC"),
            "Ocena w źródle": "–" if review.rating is None else f"{review.rating:g}",
            "Etykieta źródła": (f"{review.label.icon} {review.label.label_pl}"
                                if review.label else "–"),
            "id": review.id,
        }
        st.markdown("\n".join(f"- **{k}:** {v}" for k, v in meta.items()))
        if review.url:
            st.link_button("Otwórz w źródle", review.url)
    st.markdown("**Predykcje wszystkich modeli**")
    st.dataframe(_all_predictions(services, review), hide_index=True, key="rev_predictions",
                 column_config={"P(pozytywny)": SCORE_COLUMN})


def render_reviews_view(services: AppServices) -> None:
    page_header(services, "📝 Opinie")
    _apply_preset()
    target_id, model_name, query = _render_filters(services)

    rows = apply_filters(services.scored_reviews(target_id, model_name), query)
    c_info, c_dl = st.columns([4, 1])
    c_info.caption(f"{len(rows)} opinii")
    c_dl.download_button(
        "CSV (przefiltrowane)", data=reviews_to_csv(rows), file_name="opinie.csv",
        mime="text/csv", key="rev_csv", disabled=not rows, width="stretch",
    )
    p1, p2, _ = st.columns([1, 1, 4])
    size = p1.selectbox("Na stronie", PAGE_SIZES, index=PAGE_SIZES.index(DEFAULT_PAGE_SIZE),
                        key="rev_page_size")
    number = p2.number_input("Strona", min_value=1, value=1, step=1, key="rev_page")
    page = paginate(rows, int(number), size)
    if page.count > 1:
        st.caption(f"Strona {page.number} z {page.count} (opinie {page.start + 1}–"
                   f"{page.start + len(page.rows)})")

    event = st.dataframe(reviews_table(services, page.rows), hide_index=True, key="rev_table",
                         on_select="rerun", selection_mode="single-row",
                         column_config={"P(pozytywny)": SCORE_COLUMN})
    selected = (event or {}).get("selection", {}).get("rows") or []
    if selected and selected[0] < len(page.rows):
        st.session_state["rev_focus"] = page.rows[selected[0]].review.id
    focus = st.session_state.get("rev_focus")
    if focus:
        visible = any(r.review.id == focus for r in rows)
        _render_details(services, focus, model_name, query.term, visible)
    elif rows:
        st.caption("Zaznacz wiersz w tabeli, aby zobaczyć szczegóły opinii.")
