"""A2: dashboard – KPI, okres, trend, porównanie obiektów, przejścia i wykresy."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from opimon import config
from opimon.analytics import SentimentAnalytics, period_kpis, previous_period
from opimon.models import Prediction, ScoredReview, SentimentSummary
from opimon.ui import nav
from opimon.ui.charts import compare_chart, distribution_chart, trend_chart
from opimon.ui.dashboard_view import selected_customdata, selected_row
from opimon.ui.state import get_services
from tests.conftest import NOW, make_review

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def fresh_services(monkeypatch):
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", True)
    get_services.clear()
    yield
    get_services.clear()


def open_dashboard() -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    at.switch_page(nav.PAGE_DASHBOARD).run()
    assert not at.exception, at.exception
    return at


def metric(at: AppTest, label: str):
    return next(m for m in at.metric if m.label == label)


def select_point(at: AppTest, key: str, customdata: str | list[str]) -> AppTest:
    at.session_state[key] = {"selection": {"points": [{"customdata": customdata}],
                                           "point_indices": [0], "box": [], "lasso": []}}
    return at.run()


# --------------------------------------------------------------------------- GUI
def test_kpis_period_and_label_agreement():
    at = open_dashboard()
    assert at.selectbox(key="dash_period").value == "30"
    labels = {m.label for m in at.metric}
    assert {"Opinie", "Udział pozytywnych", "Negatywne", "Zgodność z etykietą źródła"} <= labels
    assert any("95% CI" in c.value for c in at.caption)
    at.selectbox(key="dash_period").set_value("all").run()
    assert not at.exception, at.exception
    assert metric(at, "Opinie").value == "195"
    assert metric(at, "Opinie").delta is None or metric(at, "Opinie").delta == ""
    at.selectbox(key="dash_period").set_value("7").run()
    assert int(metric(at, "Opinie").value) < 195
    assert metric(at, "Udział pozytywnych").delta.endswith("p.p.")


def chart_keys(at: AppTest) -> set[str]:
    return {c.key for c in at.get("plotly_chart")}


def test_trend_frequency_and_charts():
    at = open_dashboard()
    assert chart_keys(at) == {"dash_trend_chart", "dash_distribution_chart", "dash_compare_chart",
                              "dash_terms_positive", "dash_terms_negative", "dash_emerging"}
    at.radio(key="dash_freq").set_value("W").run()
    assert not at.exception, at.exception


def test_model_switch_keeps_dashboard_working():
    at = open_dashboard()
    models = at.selectbox(key=nav.MODEL_KEY).options
    at.selectbox(key=nav.MODEL_KEY).set_value(models[-1]).run()
    assert not at.exception, at.exception


def test_compare_table_row_opens_target_dashboard():
    at = open_dashboard()
    at.session_state["dash_compare_table"] = {
        "selection": {"rows": [0], "columns": [], "cells": []}}
    at.run()
    assert not at.exception, at.exception
    target = at.session_state["dash_target"]
    assert target != "__all__" and target in {t.id for t in
                                              get_services().repository.list_targets()}
    assert "dash_compare_chart" not in chart_keys(at)         # dashboard jednego obiektu
    at.run()
    assert at.session_state["dash_target"] == target          # brak pętli przejść


def test_compare_chart_click_opens_target_dashboard():
    at = open_dashboard()
    target = get_services().repository.list_targets()[0].id
    select_point(at, "dash_compare_chart", target)
    assert not at.exception, at.exception
    assert at.session_state["dash_target"] == target


def test_trend_click_opens_reviews_and_works_again_after_return():
    at = open_dashboard()
    select_point(at, "dash_trend_chart", ["negative", "2026-10-26", "2026-11-01"])
    assert not at.exception, at.exception
    assert at.session_state["rev_sentiment"] == "negative"
    assert at.date_input(key="rev_date_from").value == date(2026, 10, 26)
    assert at.date_input(key="rev_date_to").value == date(2026, 11, 1)
    at.switch_page(nav.PAGE_DASHBOARD).run()
    assert not at.exception, at.exception
    assert at.selectbox(key="dash_period").value == "30"      # brak ponownego przejścia
    at.session_state["rev_sentiment"] = "all"
    select_point(at, "dash_trend_chart", "negative")
    assert at.session_state["rev_sentiment"] == "negative"


def test_term_click_opens_reviews_with_term_and_period():
    at = open_dashboard()
    select_point(at, "dash_terms_negative", "boring grind")
    assert not at.exception, at.exception
    assert at.session_state["rev_sentiment"] == "negative"
    assert at.text_input(key="rev_term").value == "boring grind"
    assert at.date_input(key="rev_date_from").value is not None     # okres 30 dni


def test_emerging_terms_on_starfall_and_click():
    at = open_dashboard()
    starfall = next(t.id for t in get_services().repository.list_targets()
                    if t.name == "Starfall Odyssey")
    at.selectbox(key="dash_target").set_value(starfall).run()
    emerging = next(c for c in at.get("plotly_chart") if c.key == "dash_emerging")
    terms = set(json.loads(emerging.proto.spec)["data"][0]["customdata"])
    assert {"patch", "update"} <= terms
    select_point(at, "dash_emerging", "patch")
    assert at.text_input(key="rev_term").value == "patch"
    assert at.session_state["rev_sentiment"] == "all"
    assert at.date_input(key="rev_date_from").value is not None


@pytest.mark.parametrize("sentiment", ["positive", "negative"])
def test_buttons_open_reviews_with_target(sentiment):
    at = open_dashboard()
    target = get_services().repository.list_targets()[0].id
    at.selectbox(key="dash_target").set_value(target).run()
    at.button(key=f"dash_open_{sentiment}").click().run()
    assert not at.exception, at.exception
    assert at.session_state["rev_sentiment"] == sentiment
    assert at.session_state["rev_target"] == target


def test_empty_database(monkeypatch):
    monkeypatch.setattr(config, "LOAD_SAMPLES_IF_EMPTY", False)
    get_services.clear()
    at = open_dashboard()
    assert any("Brak opinii" in i.value for i in at.info)


# ----------------------------------------------------------- logika bez Streamlit
def scored(external_id: str, hours_ago: float, score: float | None) -> ScoredReview:
    review = make_review(external_id, "x", hours_ago)
    return ScoredReview(review, None if score is None else Prediction(review.id, "m", score))


def test_period_kpis_against_previous_period():
    rows = [scored("a", 10, 0.9), scored("b", 20, 0.1), scored("c", 30, None),   # ostatnie 2 dni
            scored("d", 50, 0.9), scored("e", 60, 0.8), scored("f", 70, 0.9),    # 2–4 dni temu
            scored("g", 200, 0.1)]                                               # poza oknami
    assert [r.review.external_id for r in previous_period(rows, 2, NOW)] == ["d", "e", "f"]
    kpis = period_kpis(SentimentAnalytics(), rows, 2, NOW)
    assert (kpis.current.total, kpis.current.positive, kpis.current.negative) == (3, 1, 1)
    assert kpis.total_change == 0 and kpis.negative_change == 1
    assert kpis.share_change_pp == pytest.approx(-50.0)     # 50% teraz vs 100% wcześniej
    assert kpis.ci_low < 0.5 < kpis.ci_high
    everything = period_kpis(SentimentAnalytics(), rows, None, NOW)
    assert everything.current.total == 7 and everything.previous is None
    assert everything.total_change is None and everything.share_change_pp is None
    assert previous_period(rows, None, NOW) == []


def test_period_kpis_without_previous_predictions():
    kpis = period_kpis(SentimentAnalytics(), [scored("a", 1, 0.9)], 7, NOW)
    assert kpis.previous.total == 0 and kpis.share_change_pp is None


def test_selection_helpers():
    assert selected_customdata(None) is None
    assert selected_customdata({"selection": {"points": []}}) is None
    assert selected_customdata({"selection": {"points": [{"customdata": ["steam:1"]}]}}) \
        == "steam:1"
    assert selected_customdata({"selection": {"points": [{"customdata": "negative"}]}}) \
        == "negative"
    assert selected_row({"selection": {"rows": [2], "columns": [], "cells": []}}) == 2
    assert selected_row({"selection": {"rows": []}}) is None


def test_trend_chart_traces():
    rows = [scored("a", 1, 0.9), scored("b", 2, 0.1), scored("c", 50, 0.8)]
    trend = SentimentAnalytics().trend(rows, "D")
    fig = trend_chart(trend)
    names = [t.name for t in fig.data]
    assert names == ["Pozytywne", "Negatywne", "Udział pozytywnych",
                     "Udział pozytywnych (wygładzony)"]
    assert [c[0] for c in fig.data[0].customdata] == ["positive"] * len(trend)
    assert list(fig.data[0].customdata[-1]) == ["positive", "2026-11-01", "2026-11-01"]
    weekly = trend_chart(SentimentAnalytics().trend(rows, "W"), "W")
    assert list(weekly.data[1].customdata[0]) == ["negative", "2026-10-26", "2026-11-01"]
    assert list(fig.data[1].y) == list(trend["negative"])
    assert fig.layout.barmode == "stack"


def test_trend_chart_without_smoothed_column():
    trend = pd.DataFrame({"period": pd.to_datetime(["2026-11-01"], utc=True), "positive": [1],
                          "negative": [0], "total": [1], "positive_share": [1.0]})
    assert len(trend_chart(trend).data) == 3


def test_distribution_chart_skips_empty_parts():
    fig = distribution_chart(SentimentSummary(5, 3, 2, 0))
    assert list(fig.data[0].labels) == ["Pozytywne", "Negatywne"]
    assert list(fig.data[0].values) == [3, 2]


def test_compare_chart_error_bars():
    nan = float("nan")
    cmp = pd.DataFrame({"target_id": ["s:a", "s:b", "s:c"], "total": [10, 5, 1],
                        "positive": [8, 1, 0], "negative": [2, 4, 0],
                        "positive_share": [0.8, 0.2, nan],
                        "ci_low": [0.49, 0.04, nan], "ci_high": [0.94, 0.62, nan]})
    fig = compare_chart(cmp, name=lambda t: t.upper())
    bar = fig.data[0]
    assert list(bar.customdata) == ["s:b", "s:a"]           # rosnąco, bez obiektu bez predykcji
    assert list(bar.y) == ["S:B", "S:A"]
    assert list(bar.error_x.array) == pytest.approx([0.42, 0.14])
    assert list(bar.error_x.arrayminus) == pytest.approx([0.16, 0.31])


def test_trend_chart_on_empty_period_range():
    rows = [scored("a", 1, 0.9), scored("b", 24 * 5, 0.1)]
    trend = SentimentAnalytics().trend(rows, "D")
    assert len(trend) == 6 and len(trend_chart(trend).data[0].x) == 6
    assert NOW - timedelta(days=5) > trend["period"].iloc[0]
