"""Widok „Dashboard” (O3, A2): KPI okresu, trend, rozkład, porównanie obiektów i przejścia."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from opimon.analytics import (
    PERIOD_OPTIONS,
    LabelAgreement,
    PeriodKpis,
    filter_period,
    label_agreement,
    period_kpis,
)
from opimon.models import ScoredReview, Sentiment, utcnow
from opimon.services import AppServices
from opimon.ui import nav
from opimon.ui.charts import compare_chart, distribution_chart, trend_chart
from opimon.ui.components import model_selector, page_header, target_selector

# Klucze okresu w `session_state` (stringi, bo `None` w selectbox jest niejednoznaczne).
PERIODS: dict[str, int | None] = {str(d) if d else "all": d for d in PERIOD_OPTIONS}
DEFAULT_PERIOD = "30"
FREQS = {"D": "Dziennie", "W": "Tygodniowo"}


def selected_customdata(event: Mapping[str, Any] | None) -> str | None:
    """`customdata` pierwszego zaznaczonego punktu wykresu plotly (`on_select`) albo None."""
    if not event:
        return None
    points = (event.get("selection") or {}).get("points") or []
    for point in points:
        value = point.get("customdata")
        if isinstance(value, list | tuple):
            value = value[0] if value else None
        if value not in (None, ""):
            return str(value)
    return None


def selected_row(event: Mapping[str, Any] | None) -> int | None:
    """Indeks zaznaczonego wiersza `st.dataframe` (`on_select`) albo None."""
    rows = ((event or {}).get("selection") or {}).get("rows") or []
    return int(rows[0]) if rows else None


def _pct(value: float | None) -> str:
    return "–" if value is None or math.isnan(value) else f"{value:.0%}"


def _render_kpis(kpis: PeriodKpis, agreement: LabelAgreement, days: int | None) -> None:
    current = kpis.current
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Opinie", current.total, delta=kpis.total_change,
              help="Zmiana względem poprzedniego okresu tej samej długości.")
    pp = kpis.share_change_pp
    m2.metric("Udział pozytywnych", _pct(current.positive_share),
              delta=None if pp is None else f"{pp:+.1f} p.p.",
              help="Wśród opinii z predykcją wybranego modelu; przedział ufności Wilsona 95%.")
    if current.positive_share is not None:
        m2.caption(f"95% CI: {_pct(kpis.ci_low)}–{_pct(kpis.ci_high)} "
                   f"(n={current.positive + current.negative})")
    m3.metric("Negatywne", current.negative, delta=kpis.negative_change, delta_color="inverse")
    m4.metric("Zgodność z etykietą źródła", _pct(agreement.share),
              help="Jak często predykcja modelu zgadza się z oceną autora (np. Steam „voted up”).")
    if agreement.n:
        m4.caption(f"{agreement.agree}/{agreement.n} · 95% CI: "
                   f"{_pct(agreement.ci_low)}–{_pct(agreement.ci_high)}")
    else:
        m4.caption("Brak opinii z etykietą źródła.")
    if days is not None and kpis.previous is not None and kpis.previous.total == 0:
        st.caption(f"Brak opinii w poprzednich {days} dniach – zmiany nie są liczone.")


def _render_trend(services: AppServices, rows: list[ScoredReview], target_id: str | None,
                  freq: str) -> None:
    st.subheader("Trend sentymentu")
    trend = services.analytics.trend(rows, freq)
    if trend.empty:
        st.info("Brak opinii w wybranym okresie.")
        return
    event = st.plotly_chart(trend_chart(trend), key="dash_trend_chart", on_select="rerun",
                            selection_mode="points")
    st.caption("Kliknij słupek, aby zobaczyć opinie o danym sentymencie.")
    if (value := selected_customdata(event)) in {"positive", "negative"}:
        nav.open_reviews(target_id, Sentiment(value))


def _render_distribution(services: AppServices, rows: list[ScoredReview],
                         target_id: str | None) -> None:
    st.subheader("Rozkład sentymentu")
    summary = services.analytics.summary(rows)
    if summary.total == 0:
        st.info("Brak opinii w wybranym okresie.")
    else:
        st.plotly_chart(distribution_chart(summary), key="dash_distribution_chart")
    b1, b2 = st.columns(2)
    for col, sentiment in zip((b1, b2), (Sentiment.POSITIVE, Sentiment.NEGATIVE), strict=True):
        if col.button(f"{sentiment.icon} Pokaż opinie: {sentiment.label_pl}",
                      key=f"dash_open_{sentiment.value}", width="stretch"):
            nav.open_reviews(target_id, sentiment)


def _render_comparison(services: AppServices, rows: list[ScoredReview]) -> None:
    st.subheader("Porównanie obiektów")
    cmp = services.analytics.compare_targets(rows)
    if cmp.empty:
        st.info("Brak opinii w wybranym okresie.")
        return
    event = st.plotly_chart(compare_chart(cmp, services.target_name), key="dash_compare_chart",
                            on_select="rerun", selection_mode="points")
    table = cmp.copy()
    table.insert(0, "Obiekt", table["target_id"].map(services.target_name))
    table = table.rename(columns={"total": "Opinie", "positive": "Pozytywne",
                                  "negative": "Negatywne", "positive_share": "Udział poz.",
                                  "ci_low": "CI od", "ci_high": "CI do"})
    pct = st.column_config.NumberColumn(format="percent")
    picked = st.dataframe(
        table.drop(columns=["target_id"]), hide_index=True, key="dash_compare_table",
        on_select="rerun", selection_mode="single-row",
        column_config={"Udział poz.": st.column_config.ProgressColumn(
                           "Udział poz.", min_value=0.0, max_value=1.0, format="percent"),
                       "CI od": pct, "CI do": pct},
    )
    st.caption("Kliknij obiekt na wykresie lub wiersz tabeli, aby otworzyć jego dashboard. "
               "Wąsy na wykresie = 95% przedział ufności (Wilson).")
    # Po przejściu sekcja porównania znika (dashboard obiektu), więc Streamlit czyści
    # zaznaczenie i przejście się nie powtarza.
    row = selected_row(picked)
    chosen = str(cmp.iloc[row]["target_id"]) if row is not None else selected_customdata(event)
    if chosen:
        nav.open_dashboard(chosen)


def _render_terms(services: AppServices, rows: list[ScoredReview]) -> None:
    st.subheader("Charakterystyczne słowa")
    cols = st.columns(2)
    for col, sentiment in zip(cols, (Sentiment.POSITIVE, Sentiment.NEGATIVE), strict=True):
        with col:
            st.markdown(f"{sentiment.icon} **{sentiment.label_pl}**")
            terms = services.analytics.top_terms(rows, sentiment, n=10)
            st.dataframe(pd.DataFrame({"Słowo": [t.term for t in terms],
                                       "Liczba": [t.count for t in terms]}),
                         hide_index=True, key=f"dash_terms_{sentiment.value}")


def render_dashboard_view(services: AppServices, now: datetime | None = None) -> None:
    page_header(services, "📊 Dashboard sentymentu")
    if (preset := nav.dashboard_target()) is not None:
        st.session_state["dash_target"] = preset
        nav.clear_dashboard_target()

    c1, c2, c3, c4 = st.columns([3, 3, 2, 2])
    with c1:
        target_id = target_selector(services, key="dash_target")
    with c2:
        model_name = model_selector(services)
    period = c3.selectbox("Okres", list(PERIODS), index=list(PERIODS).index(DEFAULT_PERIOD),
                          key="dash_period", format_func=lambda k: PERIOD_OPTIONS[PERIODS[k]])
    freq = c4.radio("Częstotliwość trendu", list(FREQS), key="dash_freq", horizontal=True,
                    format_func=FREQS.get)
    days = PERIODS[period]

    all_rows = services.scored_reviews(target_id, model_name)
    if not all_rows:
        st.info("Brak opinii. Pobierz je w widoku „Źródła danych”.")
        return
    now = now or utcnow()
    rows = filter_period(all_rows, days, now)
    _render_kpis(period_kpis(services.analytics, all_rows, days, now), label_agreement(rows),
                 days)

    for alert in services.analytics.alerts(all_rows, now):
        st.warning(f"**{services.target_name(alert.target_id)}**: {alert.message}")

    left, right = st.columns([2, 1])
    with left:
        _render_trend(services, rows, target_id, freq)
    with right:
        _render_distribution(services, rows, target_id)
    if target_id is None:
        _render_comparison(services, rows)
    _render_terms(services, rows)
